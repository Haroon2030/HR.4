@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
if not exist "%~dp0_hr_python.cmd" (
    echo ERROR: Missing _hr_python.cmd - copy full biometric_bridge folder from HR repo.
    exit /b 1
)
if not exist config.env (
    echo ERROR: config.env missing. Copy from config.example.env
    exit /b 1
)
if not exist devices.list if exist devices.list.example (
    echo NOTE: optional devices.list - branch setup uses config.env only
)
set "HRPY="
for /f "delims=" %%P in ('"%~dp0_hr_python.cmd" 2^>nul') do set "HRPY=%%P"
if not defined HRPY (
    echo.
    echo ERROR: No working Python. ZKBioTime python cannot be used.
    echo Run: fix_python.bat
    echo Or: winget install Python.Python.3.12
    echo.
    exit /b 1
)
echo Using: !HRPY!
if /I "!HRPY!"=="py -3.12" (
    py -3.12 agent.py %*
) else (
    "!HRPY!" agent.py %*
)
exit /b %errorlevel%
