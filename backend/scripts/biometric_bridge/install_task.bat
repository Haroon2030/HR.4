@echo off
title HR - Install scheduled task (Admin required)
cd /d "%~dp0"

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo  ERROR: Run as Administrator.
    echo  Right-click install_task.bat - Run as administrator
    echo.
    pause
    exit /b 1
)

set TASK=HR-BiometricBridge
set RUNNER=%~dp0run_scheduled.bat

if not exist "%~dp0config.env" (
    echo ERROR: config.env not found
    pause
    exit /b 1
)
if not exist "%RUNNER%" (
    echo ERROR: run_scheduled.bat not found
    pause
    exit /b 1
)

where python >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: python not in PATH
    pause
    exit /b 1
)

echo Runner: %RUNNER%
schtasks /Delete /TN %TASK% /F >nul 2>&1

schtasks /Create /TN %TASK% /TR "%RUNNER%" /SC MINUTE /MO 5 /RU "%USERNAME%" /F
if %errorLevel% neq 0 (
    echo FAILED to create task.
    pause
    exit /b 1
)

echo.
echo SUCCESS - task %TASK% every 5 minutes.
schtasks /Query /TN %TASK% /FO LIST | findstr /I "TaskName Status Next"
echo Log file: %~dp0agent_scheduled.log
echo.
echo Test: schtasks /Run /TN %TASK%
echo.
pause
exit /b 0
