# Register Windows scheduled task: HR biometric agent every 5 minutes
# MUST run as Administrator

param([string]$PythonExecutable = '')

$ErrorActionPreference = 'Stop'
$TaskName = 'HR-BiometricBridge'
$Here = $PSScriptRoot

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    Write-Host 'ERROR: Run as Administrator.' -ForegroundColor Red
    Write-Host 'Right-click install_task.bat -> Run as administrator' -ForegroundColor Yellow
    exit 1
}

Set-Location $Here
. (Join-Path $Here 'ensure_python.ps1')

if ($PythonExecutable -and (Test-Path -LiteralPath $PythonExecutable)) {
    $Python = (Resolve-Path -LiteralPath $PythonExecutable).Path
} else {
    $info = Ensure-PythonForHrAgent -Quiet
    if ($info.UsePyLauncher) {
        Refresh-SessionPath
        $resolved = Get-Command python -ErrorAction SilentlyContinue
        if (-not $resolved) {
            Write-Host 'ERROR: python.exe not found.' -ForegroundColor Red
            exit 1
        }
        $Python = $resolved.Source
    } else {
        $Python = $info.Executable
    }
}

$configPath = Join-Path $Here 'config.env'
if (-not (Test-Path $configPath)) {
    Write-Host "ERROR: Missing $configPath" -ForegroundColor Red
    exit 1
}

$AgentScript = Join-Path $Here 'agent.py'
if (-not (Test-Path $AgentScript)) {
    Write-Host "ERROR: Missing $AgentScript" -ForegroundColor Red
    exit 1
}

Write-Host "Python:  $Python" -ForegroundColor Cyan
Write-Host "Agent:   $AgentScript" -ForegroundColor Cyan
Write-Host "WorkDir: $Here" -ForegroundColor Cyan

schtasks /Delete /TN $TaskName /F 2>$null | Out-Null

# schtasks is reliable on Windows 10 (Register-ScheduledTask duration often fails)
$tr = "`"$Python`" `"$AgentScript`" --once"
$runUser = $env:USERNAME

Write-Host "Creating task (every 5 min) as user: $runUser" -ForegroundColor Cyan
$result = schtasks /Create /TN $TaskName /TR $tr /SC MINUTE /MO 5 /RU $runUser /RL HIGHEST /F 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Retry without HIGHEST..." -ForegroundColor Yellow
    $result = schtasks /Create /TN $TaskName /TR $tr /SC MINUTE /MO 5 /RU $runUser /F 2>&1
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: schtasks failed:" -ForegroundColor Red
    Write-Host $result
    exit 1
}

Write-Host "OK: Task '$TaskName' runs every 5 minutes." -ForegroundColor Green
Write-Host ''
schtasks /Query /TN $TaskName /FO LIST | Select-String -Pattern 'TaskName|Status|Next Run|Last Run'
Write-Host ''
Write-Host 'Run now: schtasks /Run /TN HR-BiometricBridge' -ForegroundColor Cyan
