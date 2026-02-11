#!/usr/bin/env python3
import argparse
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import smtplib
from email.message import EmailMessage
from typing import Optional, Dict

try:
    import tomllib  # py3.11+
except Exception:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
    except Exception:
        tomllib = None

MONEY_RE_COMMA = re.compile(r"(-?\d[\d\s]*,\d{2})\s*$")
MONEY_RE_DOT = re.compile(r"(-?\d[\d\s]*\.\d{2})\s*$")
RECEIPT_RE = re.compile(r"^Kvito Nr\.\s+(\d+)/(\d+)/(\d+)")
ZNUM_RE = re.compile(r"Z(?: ataskaitos)? numeris\s+(\d+)", re.IGNORECASE)
ZNUM_RE_ALT = re.compile(r"Z numeris\s+(\d+)", re.IGNORECASE)
DATE_RE = re.compile(r"Ataskaitos prad\w+\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})")
DATE_END_RE = re.compile(r"Ataskaitos pabaig\w+\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})")


@dataclass
class EKJData:
    z_number: Optional[int]
    report_date: Optional[str]
    total_sales: Optional[Decimal]
    fiscal_receipts_count: Optional[int]
    receipt_totals: Dict[str, Decimal]


@dataclass
class OLDData:
    total_sales: Decimal
    receipt_totals: Dict[str, Decimal]


def read_text(path: Path) -> str:
    data = path.read_bytes()
    text = data.decode("latin-1", errors="ignore")
    # Replace control characters but keep printable/whitespace
    cleaned = []
    for ch in text:
        o = ord(ch)
        if ch in ("\n", "\r", "\t") or o >= 32:
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    return "".join(cleaned)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


def parse_money_comma(line: str) -> Optional[Decimal]:
    m = MONEY_RE_COMMA.search(line)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_money_dot(line: str) -> Optional[Decimal]:
    m = MONEY_RE_DOT.search(line)
    if not m:
        return None
    raw = m.group(1).replace(" ", "")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_ekj(path: Path) -> EKJData:
    text = read_text(path)
    lines = [ln.rstrip("\r") for ln in text.split("\n")]

    z_number = None
    report_date = None
    total_sales = None
    fiscal_receipts_count = None

    # Find Z number and report date
    for ln in lines:
        ln_norm = norm(ln)
        if z_number is None:
            m = ZNUM_RE.search(ln) or ZNUM_RE_ALT.search(ln)
            if m:
                z_number = int(m.group(1))
        if report_date is None:
            m = DATE_END_RE.search(ln)
            if m:
                report_date = m.group(1)
        if z_number is not None and report_date is not None:
            break

    # Find totals after Z block
    if z_number is not None:
        try:
            z_idx = next(i for i, ln in enumerate(lines) if ZNUM_RE.search(ln) or ZNUM_RE_ALT.search(ln))
        except StopIteration:
            z_idx = 0
        for ln in lines[z_idx:z_idx + 500]:
            ln_norm = norm(ln)
            if total_sales is None and ln_norm.startswith("dienos pardavimai"):
                total_sales = parse_money_comma(ln)
            if fiscal_receipts_count is None and ln_norm.startswith("fiskaliniu kvitu skaicius"):
                # last token should be integer
                parts = ln_norm.split()
                if parts:
                    try:
                        fiscal_receipts_count = int(parts[-1])
                    except ValueError:
                        pass
            if total_sales is not None and fiscal_receipts_count is not None:
                break

    # Receipt totals
    receipt_totals: dict[str, Decimal] = {}
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = RECEIPT_RE.match(ln.lstrip())
        if not m:
            i += 1
            continue
        receipt_id = f"{m.group(1)}/{m.group(2)}"
        # scan forward until next receipt
        j = i + 1
        last_total = None
        while j < len(lines):
            ln2 = lines[j]
            if RECEIPT_RE.match(ln2.lstrip()):
                break
            ln2_norm = norm(ln2)
            if ln2_norm.lstrip().startswith("mok"):
                amt = parse_money_comma(ln2)
                if amt is not None:
                    last_total = amt
            j += 1
        if last_total is not None:
            receipt_totals[receipt_id] = last_total
        i = j

    return EKJData(
        z_number=z_number,
        report_date=report_date,
        total_sales=total_sales,
        fiscal_receipts_count=fiscal_receipts_count,
        receipt_totals=receipt_totals,
    )


def parse_old(path: Path, z_number: int, report_date: Optional[str]) -> OLDData:
    text = path.read_text(errors="ignore")
    blocks = text.split("<I06>")
    receipt_totals: dict[str, Decimal] = {}
    total_sales = Decimal("0.00")

    for block in blocks[1:]:
        block_text = block.split("</I06>")[0]
        m_nr = re.search(r"<I06_DOK_NR>(.*?)</I06_DOK_NR>", block_text)
        m_sum = re.search(r"<I06_MOK_SUMA>(.*?)</I06_MOK_SUMA>", block_text)
        m_date = re.search(r"<I06_OP_DATA>(.*?)</I06_OP_DATA>", block_text)
        if not m_nr or not m_sum:
            continue
        dok_nr = m_nr.group(1).strip()
        # filter by Z number
        if not dok_nr.endswith(f"/{z_number}"):
            continue
        if report_date and m_date:
            if m_date.group(1).strip().replace(".", "-") != report_date:
                continue
        amt = None
        try:
            amt = Decimal(m_sum.group(1).strip())
        except InvalidOperation:
            continue
        receipt_totals[dok_nr] = amt
        total_sales += amt

    return OLDData(total_sales=total_sales, receipt_totals=receipt_totals)


def find_latest_ekj(ekj_dir: Path) -> Optional[Path]:
    # Search recursively because EKJ files are stored in shop subfolders.
    candidates = [p for p in ekj_dir.rglob("*.txt") if p.is_file()]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def find_old_files(old_dir: Path, report_date: Optional[str]) -> list[Path]:
    files = list(old_dir.glob("*.old"))
    if report_date:
        yyyymmdd = report_date.replace("-", "")
        files = [p for p in files if f"d{yyyymmdd}" in p.name.lower()]
    return files


def load_config(path: Path) -> dict:
    if tomllib is None:
        raise RuntimeError("Python 3.11+ required (or install tomli)")
    with path.open("rb") as f:
        return tomllib.load(f)


def send_email(cfg: dict, subject: str, body: str):
    msg = EmailMessage()
    msg["From"] = cfg["from"]
    msg["To"] = ", ".join(cfg["to"])
    msg["Subject"] = subject
    msg.set_content(body)

    host = cfg["smtp_host"]
    port = int(cfg.get("smtp_port", 587))
    use_tls = bool(cfg.get("smtp_starttls", True))
    username = cfg.get("smtp_user")
    password = cfg.get("smtp_pass")

    with smtplib.SMTP(host, port, timeout=30) as s:
        if use_tls:
            s.starttls()
        if username:
            s.login(username, password)
        s.send_message(msg)


def write_report(output_dir: Path, z_number: int, report_date: Optional[str], body: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_part = report_date or datetime.now().strftime("%Y-%m-%d")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"analize_Z{z_number}_{date_part}_{ts}.txt"
    out_path = output_dir / name
    out_path.write_text(body, encoding="utf-8")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--ekj-file")
    ap.add_argument("--old-file")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    ekj_dir = Path(cfg["paths"]["ekj_dir"])
    old_dir = Path(cfg["paths"]["old_dir"])
    output_dir = Path(
        cfg["paths"].get("output_dir", r"C:\Users\kasos\Desktop\Pardavimu analize")
    )

    ekj_file = Path(args.ekj_file) if args.ekj_file else None
    if ekj_file is None:
        ekj_file = find_latest_ekj(ekj_dir)
    if ekj_file is None or not ekj_file.exists():
        print("ERROR: EKJ file not found", file=sys.stderr)
        sys.exit(2)

    ekj = parse_ekj(ekj_file)
    if ekj.z_number is None:
        print("ERROR: Z number not found in EKJ", file=sys.stderr)
        sys.exit(2)

    old_files = []
    if args.old_file:
        old_files = [Path(args.old_file)]
    else:
        old_files = find_old_files(old_dir, ekj.report_date)

    if not old_files:
        print("ERROR: No OLD files found", file=sys.stderr)
        sys.exit(2)

    old_totals = Decimal("0.00")
    old_receipts: dict[str, Decimal] = {}
    for f in old_files:
        data = parse_old(f, ekj.z_number, ekj.report_date)
        old_totals += data.total_sales
        old_receipts.update(data.receipt_totals)

    tolerance = Decimal(str(cfg.get("tolerance", "0.01")))
    mismatches = []

    if ekj.total_sales is None:
        mismatches.append("Nepavyko rasti 'Dienos pardavimai' EKJ faile.")
    else:
        diff = (ekj.total_sales - old_totals).copy_abs()
        if diff > tolerance:
            mismatches.append(
                f"Dienos pardavimai nesutampa: EKJ {ekj.total_sales} vs OLD {old_totals} (skirtumas {diff})."
            )

    if ekj.fiscal_receipts_count is not None:
        if ekj.fiscal_receipts_count != len(old_receipts):
            mismatches.append(
                f"Fiskaliniu kvitu skaicius nesutampa: EKJ {ekj.fiscal_receipts_count} vs OLD {len(old_receipts)}."
            )

    ekj_receipts = set(ekj.receipt_totals.keys())
    old_receipt_ids = set(old_receipts.keys())
    missing_in_old = sorted(ekj_receipts - old_receipt_ids)
    missing_in_ekj = sorted(old_receipt_ids - ekj_receipts)

    if missing_in_old:
        mismatches.append(f"Truksta OLD: {', '.join(missing_in_old[:50])}" + (" ..." if len(missing_in_old) > 50 else ""))
    if missing_in_ekj:
        mismatches.append(f"Truksta EKJ: {', '.join(missing_in_ekj[:50])}" + (" ..." if len(missing_in_ekj) > 50 else ""))

    # receipt totals diff
    receipt_diffs = []
    for rid in sorted(ekj_receipts & old_receipt_ids):
        e_amt = ekj.receipt_totals.get(rid)
        o_amt = old_receipts.get(rid)
        if e_amt is None or o_amt is None:
            continue
        if (e_amt - o_amt).copy_abs() > tolerance:
            receipt_diffs.append(f"{rid}: EKJ {e_amt} vs OLD {o_amt}")
            if len(receipt_diffs) >= 50:
                break
    if receipt_diffs:
        mismatches.append("Kvitu sumu skirtumai (pirmi 50): " + "; ".join(receipt_diffs))

    subject = f"EKJ vs OLD patikra: Z {ekj.z_number}"
    if ekj.report_date:
        subject += f" {ekj.report_date}"

    if mismatches:
        body = "Rasti neatitikimai:\n\n" + "\n".join(f"- {m}" for m in mismatches)
        body += f"\n\nEKJ failas: {ekj_file}\nOLD failai: {', '.join(str(p) for p in old_files)}"
        if args.dry_run:
            print(body)
        else:
            report_path = write_report(output_dir, ekj.z_number, ekj.report_date, body)
            if cfg.get("email_enabled", True):
                send_email(cfg["email"], subject, body)
            print(f"Report written: {report_path}")
    else:
        ok_body = "Neatitikimu nerasta."
        if args.dry_run:
            print(ok_body)
        else:
            report_path = write_report(output_dir, ekj.z_number, ekj.report_date, ok_body)
            if cfg.get("email_on_ok", False) and cfg.get("email_enabled", True):
                send_email(cfg["email"], subject, ok_body)
            print(f"Report written: {report_path}")


if __name__ == "__main__":
    main()
