# Central HR biometric agent (multiple branches from one PC)
# ASCII-only for Windows PowerShell 5.1

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
Set-Location $Here

. (Join-Path $Here 'ensure_python.ps1')

Write-Host '=== HR Biometric Central Setup ===' -ForegroundColor Cyan

$pyInfo = Ensure-PythonForHrAgent

if (-not (Test-Path 'config.env')) {
    if (Test-Path 'config.example.env') {
        Copy-Item 'config.example.env' 'config.env'
        Write-Host 'Created config.env - edit AGENT_API_KEY and SERVER_URL' -ForegroundColor Yellow
    } else {
        Write-Host 'config.example.env not found' -ForegroundColor Red
        exit 1
    }
}

$cfg = Get-Content 'config.env' -Raw
if ($cfg -notmatch 'AGENT_API_KEY=\S+' -or $cfg -match 'AGENT_API_KEY=PUT_') {
    Write-Host 'Edit config.env: set AGENT_API_KEY (= ATTENDANCE_AGENT_API_KEY on server)' -ForegroundColor Yellow
    notepad config.env
    Read-Host 'Press Enter after saving'
}

Write-Host 'Installing packages...' -ForegroundColor Cyan
Invoke-PythonModule -PythonInfo $pyInfo -Arguments @('-m', 'pip', 'install', '-q', '-r', 'requirements.txt')

Write-Host 'Syncing device list from server...' -ForegroundColor Cyan
Invoke-PythonModule -PythonInfo $pyInfo -Arguments @((Join-Path $Here 'agent.py'), '--sync-list')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'Probing devices (this PC must reach each IP):' -ForegroundColor Cyan
Invoke-PythonModule -PythonInfo $pyInfo -Arguments @((Join-Path $Here 'agent.py'), '--probe')
$probeOk = ($LASTEXITCODE -eq 0)

Write-Host ''
if ($probeOk) {
    Write-Host 'Running one sync...' -ForegroundColor Cyan
    Invoke-PythonModule -PythonInfo $pyInfo -Arguments @((Join-Path $Here 'agent.py'), '--once')
    Write-Host ''
    Write-Host 'Auto sync every 5 min (as Admin):' -ForegroundColor Green
    $pyExe = if ($pyInfo.UsePyLauncher) { (Get-Command python).Source } else { $pyInfo.Executable }
    Write-Host "  .\install_windows_agent_task.ps1 -PythonExecutable `"$pyExe`""
} else {
    Write-Host 'Some devices unreachable from this PC.' -ForegroundColor Yellow
    Write-Host 'Options:' -ForegroundColor Yellow
    Write-Host '  1) Tailscale subnet router per branch'
    Write-Host '  2) VPN per branch'
    Write-Host '  3) Branch agent per site: install_branch.bat'
}

Write-Host ''
Write-Host 'Commands:' -ForegroundColor Cyan
Write-Host '  python agent.py --sync-list'
Write-Host '  python agent.py --probe'
Write-Host '  python agent.py --once'
