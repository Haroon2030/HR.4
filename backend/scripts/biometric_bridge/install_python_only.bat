@echo off
title HR - تثبيت Python فقط
cd /d "%~dp0"
echo تثبيت Python واضافته الى PATH...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . '%~dp0ensure_python.ps1'; Ensure-PythonForHrAgent; Write-Host ''; Write-Host 'اغلق CMD وافتحه من جديد ثم: python --version' -ForegroundColor Green }"
pause
