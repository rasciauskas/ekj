# EKJ vs OLD tikrintuvas (Windows Server 2025)

Trumpai: skriptas palygina EKJ (kasos cekių žurnalą) su OLD pardavimų failais pagal Z numerį ir dieną, ir sukuria TXT ataskaitą.

## Kaip veikia
- Iš EKJ failo paima:
  - Z numerį
  - ataskaitos datą
  - „Dienos pardavimai“ sumą
  - fiskalinių kvitų skaičių
  - kvitų sąrašą ir jų sumas
- Iš OLD failų paima visus kvitus, kurių `I06_DOK_NR` baigiasi `/Z` ir atitinka dienos datą
  - Naudojami tik `riv_sales_*.old` failai (ne `riv_invoices_*.old`)
- Palygina:
  - dienos sumą
  - kvitų skaičių
  - kvitų sąrašą (trūksta / perteklius)
  - kvitų sumas (jei nesutampa)
- Rezultatą visada įrašo į TXT failą kataloge `C:\Users\kasos\Desktop\Pardavimu analize`
- EKJ TXT failų ieško rekursiškai: ir `EKJ` kataloge, ir visuose jo poaplankiuose (pvz. `11_Pusele`, `12_Papartis` ir t. t.)

## Diegimas (Python variantas)
1. Įdiekite Python 3.11+ (jei nėra).
2. Nukopijuokite `config.example.toml` į `config.toml` ir užpildykite kelius.
   - `email_enabled = false` jau nustatytas pagal nutylėjimą.
3. Testas:
```powershell
python C:\path\to\ekj_checker\main.py --config C:\path\to\ekj_checker\config.toml --dry-run
```

## Task Scheduler (kasdien 07:00 darbo dienomis)
1. Atidarykite **Task Scheduler**.
2. Create Task…
3. Trigger: Weekly, Mon–Fri, 07:00.
4. Action: Start a program
   - Program/script: `python`
   - Add arguments: `C:\path\to\ekj_checker\main.py --config C:\path\to\ekj_checker\config.toml`
   - Start in: `C:\path\to\ekj_checker`

## Pastabos
- EKJ faile turi būti Z ataskaitos blokas (Z numeris, dienos pardavimai).
- OLD failų pavadinime pageidautina data `dYYYYMMDD` (pvz. `riv_sales_d20260208_230000_950_a.old`).
- Jei reikia, galima paleisti su `--ekj-file` ar `--old-file` konkretiems failams.
- Jei kada nors reikės el. pašto, nustatykite `email_enabled = true` ir užpildykite `[email]` sekciją.

## EXE variantas (be Python Task Scheduler vykdyme)
1. Windows serveryje atidarykite PowerShell tame pačiame kataloge, kur yra `main.py`.
2. Paleiskite:
```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows_exe.ps1
```
3. Bus sugeneruota:
   - `dist\ekj_checker.exe`
   - `run_checker.bat` (jau paruoštas paleidimui su `config.toml`)

## Task Scheduler su EXE (rekomenduojama)
1. Atidarykite **Task Scheduler**.
2. Create Task...
3. Trigger: Weekly, Mon-Fri, 07:00.
4. Action: Start a program
   - Program/script: `C:\kelias\iki\ekj_checker\run_checker.bat`
   - Start in: `C:\kelias\iki\ekj_checker`
