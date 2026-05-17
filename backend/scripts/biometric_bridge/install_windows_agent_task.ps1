# تسجيل مهمة Windows لتشغيل وكيل البصمة كل 5 دقائق (PC مركزي أو فرع).
# الاستخدام (PowerShell كمسؤول):
#   .\install_windows_agent_task.ps1
#   .\install_windows_agent_task.ps1 -PythonExecutable "C:\...\python.exe"

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
            Write-Host 'لم يُعثر على python.exe — شغّل setup_branch.ps1 أولاً أو أعد تشغيل CMD' -ForegroundColor Red
            exit 1
        }
        $Python = $resolved.Source
    } else {
        $Python = $info.Executable
    }
}

if (-not (Test-Path (Join-Path $Here 'config.env'))) {
    Write-Host 'انسخ config.example.env إلى config.env وعدّل القيم أولاً.' -ForegroundColor Red
    exit 1
}

$AgentScript = Join-Path $Here 'agent.py'
$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$AgentScript`" --once" -WorkingDirectory $Here
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description 'HR: سحب بصمة ZKTeco ورفعها للسيرفر' -Force | Out-Null
Write-Host "تم تسجيل المهمة '$TaskName' — كل 5 دقائق." -ForegroundColor Green
Write-Host "  Python: $Python" -ForegroundColor Cyan
Write-Host 'اختبار: run_probe.bat ثم python agent.py --once' -ForegroundColor Cyan
