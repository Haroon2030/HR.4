@echo off
chcp 65001 >nul
cd /d "%~dp0backend"
set DJANGO_ENV=development
set CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
set PYTHONIOENCODING=utf-8
echo HR dev server: http://127.0.0.1:8000/
echo Press Ctrl+C to stop.
"%~dp0.venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
