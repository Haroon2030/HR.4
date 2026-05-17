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
set AGENT_DIR=%~dp0
set AGENT_DIR=%AGENT_DIR:~0,-1%

if not exist "%AGENT_DIR%\config.env" (
    echo ERROR: config.env not found in %AGENT_DIR%
    pause
    exit /b 1
)
if not exist "%AGENT_DIR%\agent.py" (
    echo ERROR: agent.py not found
    pause
    exit /b 1
)

where python >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: python not in PATH. Reopen CMD or run setup_branch.ps1
    pause
    exit /b 1
)

for /f "delims=" %%P in ('where python') do set PYTHON=%%P & goto :gotpy
:gotpy
echo Python: %PYTHON%
echo Folder: %AGENT_DIR%

schtasks /Delete /TN %TASK% /F >nul 2>&1

set TR="%PYTHON%" "%AGENT_DIR%\agent.py" --once
echo Creating task every 5 minutes...
schtasks /Create /TN %TASK% /TR %TR% /SC MINUTE /MO 5 /RU "%USERNAME%" /F
if %errorLevel% neq 0 (
    echo FAILED to create task.
    pause
    exit /b 1
)

echo.
echo SUCCESS - task %TASK% created.
schtasks /Query /TN %TASK% /FO LIST | findstr /I "TaskName Status Next"
echo.
echo Test now: schtasks /Run /TN %TASK%
echo.
pause
exit /b 0
