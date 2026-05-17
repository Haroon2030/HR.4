@echo off
cd /d "%~dp0"
if not exist config.env (
    echo انسخ config.example.env الى config.env
    exit /b 1
)
python agent.py --probe %*
