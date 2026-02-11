$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Nerastas 'py' paleidiklis. Idiekite Python 3.11 (su Python Launcher)."
}

Write-Host 'Installing build tools...'
py -3.11 -m pip install --upgrade pip
py -3.11 -m pip install pyinstaller tomli

Write-Host 'Building EXE...'
py -3.11 -m PyInstaller --onefile --name ekj_checker --distpath .\dist --workpath .\build --specpath .\build .\main.py

Write-Host 'Done. EXE: .\\dist\\ekj_checker.exe'
