@echo off
title HR - Install Python only
cd /d "%~dp0"
echo Installing Python and adding to PATH...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& { . '%~dp0ensure_python.ps1'; Ensure-PythonForHrAgent; Write-Host ''; Write-Host 'Close CMD and open again, then: python --version' -ForegroundColor Green }"
pause
