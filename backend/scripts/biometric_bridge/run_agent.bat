@echo off
cd /d "%~dp0"
if not exist config.env (
    echo انسخ config.example.env الى config.env وعدّل القيم
    exit /b 1
)
python agent.py %*
