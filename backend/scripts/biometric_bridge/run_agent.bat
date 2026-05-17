@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
if not exist config.env (
    echo انسخ config.example.env الى config.env وعدّل القيم
    exit /b 1
)
if not exist devices.list (
    if exist devices.list.example (
        echo تنبيه: انسخ devices.list.example الى devices.list
        echo   أو شغّل: run_agent.bat --sync-list
    )
)
for /f "delims=" %%P in ('"%~dp0_hr_python.cmd"') do set "HRPY=%%P"
if not defined HRPY (
    echo Python not found. Run fix_python.bat
    exit /b 1
)
if /I "!HRPY!"=="py -3.12" (
    py -3.12 agent.py %*
) else (
    "!HRPY!" agent.py %*
)
exit /b %errorlevel%
