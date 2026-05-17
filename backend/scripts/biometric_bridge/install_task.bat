@echo off
title HR - Install scheduled task (Admin required)
cd /d "%~dp0"

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo  ERROR: Not running as Administrator.
    echo  Right-click this file - Run as administrator
    echo.
    pause
    exit /b 1
)

echo Registering task HR-BiometricBridge ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_windows_agent_task.ps1"
set ERR=%errorLevel%
echo.
if %ERR% neq 0 (
    echo FAILED exit code %ERR%
) else (
    echo SUCCESS
    schtasks /Query /TN HR-BiometricBridge /FO LIST | findstr /I "TaskName Status Next"
)
echo.
pause
exit /b %ERR%
