@echo off
title HR Branch Agent Setup
cd /d "%~dp0"
echo.
echo  HR Biometric Branch Setup
echo  - Installs Python if missing (winget)
echo  - Adds Python to PATH
echo  - Pulls from device and uploads to server
echo.
echo  Right-click - Run as administrator
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_branch.ps1" %*
echo.
pause
