@echo off
REM سحب حضور من جهاز ZKTeco — مثال uFace 800
cd /d "%~dp0.."
set DJANGO_ENV=development

REM جهازك (عدّل IP إن لزم)
python manage.py pull_biometric_attendance --ip 192.168.51.3 --port 4370 --real --import-db --export-dir exports\attendance

pause
