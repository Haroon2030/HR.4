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
            Write-Host 'ERROR: python.exe not found. Reopen CMD after setup.' -ForegroundColor Red
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

Write-Host "Python: $Python" -ForegroundColor Cyan
Write-Host "Agent:  $AgentScript" -ForegroundColor Cyan
Write-Host "WorkDir: $Here" -ForegroundColor Cyan

# Remove old task if exists
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
schtasks /Delete /TN $TaskName /F 2>$null | Out-Null

$registered = $false
try {
    $Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$AgentScript`" --once" -WorkingDirectory $Here
    $startAt = (Get-Date).AddMinutes(1)
    $Trigger = New-ScheduledTaskTrigger -Once -At $startAt -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
    $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'HR ZKTeco sync' -Force | Out-Null
    $registered = $true
    Write-Host "OK: Task '$TaskName' registered (every 5 minutes)." -ForegroundColor Green
} catch {
    Write-Host "Register-ScheduledTask failed: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host 'Trying schtasks fallback...' -ForegroundColor Yellow
}

if (-not $registered) {
    $tr = "`"$Python`" `"$AgentScript`" --once"
    $result = schtasks /Create /TN $TaskName /TR $tr /SC MINUTE /MO 5 /RU SYSTEM /F 2>&1
    if ($LASTEXITCODE -ne 0) {
        $result = schtasks /Create /TN $TaskName /TR $tr /SC MINUTE /MO 5 /F 2>&1
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: schtasks failed: $result" -ForegroundColor Red
        exit 1
    }
    Write-Host "OK: Task '$TaskName' registered via schtasks (every 5 minutes)." -ForegroundColor Green
}

Write-Host ''
Write-Host 'Verify: schtasks /Query /TN HR-BiometricBridge' -ForegroundColor Cyan
Write-Host 'Run now:  schtasks /Run /TN HR-BiometricBridge' -ForegroundColor Cyan
Write-Host 'Test:     cd /d C:\biometric_bridge && python agent.py --once' -ForegroundColor Cyan
