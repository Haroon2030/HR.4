@echo off
title HR - Fix Python (skip ZKBioTime)
cd /d "%~dp0"
echo.
echo  Installs or finds Python 3.12 and writes python_path.txt
echo  (ZKBioTime Python on PATH is ignored - it causes SRE module mismatch)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  ". .\ensure_python.ps1; $p = Ensure-PythonForHrAgent; Write-HrPythonPathFile -BridgeDir (Get-Location) -PythonInfo $p; ^
   if ($p.UsePyLauncher) { Write-Host 'Saved: py -3.12' -ForegroundColor Green } else { Write-Host ('Saved: ' + $p.Executable) -ForegroundColor Green }"
if %errorlevel% neq 0 (
    echo.
    echo FAILED. Install Python 3.12 from https://www.python.org/downloads/
    echo Check "Add python.exe to PATH", then run this again.
    pause
    exit /b 1
)
echo.
for /f "delims=" %%P in ('"%~dp0_hr_python.cmd"') do set "HRPY=%%P"
echo Test: "%HRPY%" agent.py --probe
"%HRPY%" agent.py --probe
echo.
pause
