@echo off
REM Example: Al-Waha branch (device id 2) - edit AGENT_API_KEY before run
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_branch.ps1" -DeviceId 2 -DeviceIp 192.168.24.59 -BranchName alwaha -ApiKey "PUT_YOUR_KEY_HERE" -InstallTask
pause
