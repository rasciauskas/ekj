@echo off
setlocal
set SCRIPT_DIR=%~dp0
"%SCRIPT_DIR%dist\ekj_checker.exe" --config "%SCRIPT_DIR%config.toml"
endlocal
