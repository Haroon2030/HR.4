# Register Windows scheduled task: HR biometric agent every 5 minutes
# Run as Administrator:
#   .\install_windows_agent_task.ps1

param([string]$PythonExecutable = '')

$ErrorActionPreference = 'Stop'
$TaskName = 'HR-BiometricBridge'
$Here = $PSScriptRoot

. (Join-Path $Here 'ensure_python.ps1')

if ($PythonExecutable -and (Test-Path -LiteralPath $PythonExecutable)) {
    $Python = (Resolve-Path -LiteralPath $PythonExecutable).Path
} else {
    $info = Ensure-PythonForHrAgent -Quiet
    if ($info.UsePyLauncher) {
        Refresh-SessionPath
        $resolved = Get-Command python -ErrorAction SilentlyContinue
        if (-not $resolved) {
            Write-Host 'python.exe not found. Run setup_branch.ps1 first, then reopen CMD.' -ForegroundColor Red
            exit 1
        }
        $Python = $resolved.Source
    } else {
        $Python = $info.Executable
    }
}

if (-not (Test-Path (Join-Path $Here 'config.env'))) {
    Write-Host 'Copy config.example.env to config.env and edit values first.' -ForegroundColor Red
    exit 1
}

$AgentScript = Join-Path $Here 'agent.py'
$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$AgentScript`" --once" -WorkingDirectory $Here
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'HR ZKTeco sync to cloud' -Force | Out-Null
Write-Host "Task '$TaskName' registered (every 5 minutes)." -ForegroundColor Green
Write-Host "  Python: $Python" -ForegroundColor Cyan
Write-Host 'Test: run_probe.bat then python agent.py --once' -ForegroundColor Cyan
