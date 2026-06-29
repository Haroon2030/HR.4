# HR biometric branch agent setup (ASCII-only for Windows PowerShell 5.1)
#
#   .\setup_branch.ps1 -DeviceId 2 -DeviceIp 192.168.24.59 -BranchName alwaha -ApiKey "KEY" -InstallTask

param(
    [int]$DeviceId = 0,
    [string]$DeviceIp = '',
    [int]$DevicePort = 4370,
    [int]$CommKey = 0,
    [string]$BranchName = '',
    [string]$ServerUrl = 'http://72.61.107.230:8082',
    [string]$ApiKey = '',
    [switch]$SkipPythonInstall,
    [switch]$InstallTask,
    [switch]$SkipProbe
)

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
Set-Location $Here

. (Join-Path $Here 'ensure_python.ps1')

function Invoke-Agent {
    param([string[]]$AgentArgs)
    $allArgs = @((Join-Path $Here 'agent.py')) + $AgentArgs
    return Invoke-PythonModule -PythonInfo $script:HrPython -Arguments $allArgs
}

Write-Host '=== HR Biometric Branch Setup ===' -ForegroundColor Cyan

Write-Host 'Checking Python...' -ForegroundColor Cyan
$script:HrPython = Ensure-PythonForHrAgent -SkipInstall:$SkipPythonInstall
Write-HrPythonPathFile -BridgeDir $Here -PythonInfo $script:HrPython

if (-not $DeviceId) {
    $raw = Read-Host 'Device ID in HR (example: 2 for Al-Waha)'
    if (-not [int]::TryParse($raw, [ref]$DeviceId) -or $DeviceId -lt 1) {
        Write-Host 'Invalid device ID' -ForegroundColor Red
        exit 1
    }
}
if (-not $DeviceIp) {
    $DeviceIp = Read-Host 'Device IP (example: 192.168.24.59)'
}
if (-not $BranchName) {
    $BranchName = Read-Host 'Branch name (latin, example: alwaha)'
}
if (-not $ApiKey) {
    $ApiKey = Read-Host 'AGENT_API_KEY (per-device key from HR: Biometric devices page)'
}
$urlIn = Read-Host "Server URL [$ServerUrl]"
if ($urlIn) { $ServerUrl = $urlIn.TrimEnd('/') }

$configPath = Join-Path $Here 'config.env'
@(
    '# Branch agent - do not commit to Git',
    "SERVER_URL=$ServerUrl",
    "AGENT_API_KEY=$ApiKey",
    "AGENT_ID=branch-$BranchName",
    "DEVICE_ID=$DeviceId",
    "DEVICE_IP=$DeviceIp",
    "DEVICE_PORT=$DevicePort",
    "COMM_KEY=$CommKey",
    "DEVICE_LABEL=$BranchName",
    'POLL_INTERVAL_SEC=300',
    'TIMEOUT_SEC=20',
    'SYNC_ON_REQUEST_ONLY=false',
    'INCREMENTAL=true',
    'INGEST_BATCH_SIZE=150',
    'INGEST_MAX_BODY_KB=600'
) -join "`n" | Set-Content -Path $configPath -Encoding UTF8

$listPath = Join-Path $Here 'devices.list'
if (Test-Path $listPath) {
    $bak = "$listPath.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Move-Item $listPath $bak -Force
    Write-Host "Backed up old devices.list to $bak" -ForegroundColor Yellow
}

function Test-AgentPythonPackages {
    # Single-line string: PowerShell 5.1 treats "from" as reserved inside @() arrays.
    $check = 'import requests; from zk import ZK'
    $code = Invoke-PythonModule -PythonInfo $script:HrPython -Arguments @('-c', $check)
    return ($code -eq 0)
}

if (Test-AgentPythonPackages) {
    Write-Host 'Python packages OK (requests, pyzk).' -ForegroundColor Green
} else {
    Write-Host 'Installing pip packages (requests, pyzk)...' -ForegroundColor Cyan
    $pipArgs = @(
        '-m', 'pip', 'install', '--disable-pip-version-check',
        'requests>=2.31.0', 'pyzk==0.9'
    )
    $pipCode = Invoke-PythonModule -PythonInfo $script:HrPython -Arguments $pipArgs
    if ($pipCode -ne 0) {
        $pipCode = Invoke-PythonModule -PythonInfo $script:HrPython -Arguments @(
            '-m', 'pip', 'install', '--disable-pip-version-check',
            '-r', (Join-Path $Here 'requirements.txt')
        )
    }
    if (-not (Test-AgentPythonPackages)) {
        Write-Host 'pip install failed - but try manually:' -ForegroundColor Yellow
        Write-Host '  python -m pip install requests pyzk==0.9' -ForegroundColor Yellow
        Write-Host 'Then: python agent.py --probe' -ForegroundColor Yellow
        exit 1
    }
    Write-Host 'Python packages installed.' -ForegroundColor Green
}

if (-not $SkipProbe) {
    Write-Host 'Probing device...' -ForegroundColor Cyan
    $probeCode = Invoke-Agent @('--probe')
    if ($probeCode -ne 0) {
        Write-Host 'Probe failed - check ping, Comm Key=0, same LAN' -ForegroundColor Yellow
    } else {
        Write-Host 'Running one sync...' -ForegroundColor Cyan
        Invoke-Agent @('--once') | Out-Null
    }
}

if ($InstallTask) {
    $pyExe = $script:HrPython.Executable
    if ($script:HrPython.UsePyLauncher -or $pyExe -eq 'py') {
        Refresh-SessionPath
        $resolved = Get-Command python -ErrorAction SilentlyContinue
        if ($resolved) { $pyExe = $resolved.Source }
    }
    & (Join-Path $Here 'install_task.bat')
} else {
    Write-Host ''
    Write-Host 'For auto sync every 5 min (run as Admin):' -ForegroundColor Green
    Write-Host '  install_task.bat'
}

Write-Host ''
Write-Host 'Done.' -ForegroundColor Green
Write-Host ('  python agent.py --once --device ' + $DeviceId) -ForegroundColor Cyan
