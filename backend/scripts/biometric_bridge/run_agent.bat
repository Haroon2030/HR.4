@echo off
cd /d "%~dp0"
if not exist config.env (
    echo انسخ config.example.env الى config.env وعدّل القيم
    exit /b 1
)
if not exist devices.list (
    if exist devices.list.example (
        echo تنبيه: انسخ devices.list.example الى devices.list
        echo   أو شغّل: python agent.py --sync-list
    )
)
python agent.py %*
