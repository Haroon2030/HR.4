@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
for /f "delims=" %%P in ('"%~dp0_hr_python.cmd"') do set "HRPY=%%P"
if not defined HRPY (
    echo [%date% %time%] ERROR: Python not found. Run fix_python.bat >> agent_scheduled.log
    exit /b 1
)
if /I "!HRPY!"=="py -3.12" (
    py -3.12 agent.py --once >> agent_scheduled.log 2>&1
) else (
    "!HRPY!" agent.py --once >> agent_scheduled.log 2>&1
)
exit /b %errorlevel%
