@echo off
title HR - Fix Python (skip ZKBioTime)
cd /d "%~dp0"
echo.
echo HR Biometric Bridge - fix Python
echo Clears PYTHONPATH for agent runs (ZKBioTime causes SRE module mismatch).
if defined PYTHONPATH echo Current PYTHONPATH=%PYTHONPATH%
echo.

if exist python_path.txt del /f /q python_path.txt

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  ". .\ensure_python.ps1; $p = Ensure-PythonForHrAgent; Write-HrPythonPathFile -BridgeDir (Get-Location) -PythonInfo $p; Write-Host ('Saved: ' + (Get-Content python_path.txt -Raw)) -ForegroundColor Green"
if %errorlevel% neq 0 (
    echo.
    echo Install Python 3.12: https://www.python.org/downloads/
    echo Check "Add python.exe to PATH", close CMD, run this again.
    echo Or: winget install Python.Python.3.12
    pause
    exit /b 1
)

echo.
call "%~dp0run_agent.bat" --probe
echo.
pause
