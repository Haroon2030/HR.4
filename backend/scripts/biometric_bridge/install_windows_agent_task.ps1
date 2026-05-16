# تسجيل مهمة Windows لتشغيل وكيل البصمة كل 5 دقائق (مرة واحدة على PC الفرع).
# يتطلب: VPN إلى شبكة الجهاز + config.env + pip install -r requirements.txt
# الاستخدام (PowerShell كمسؤول):
#   cd backend\scripts\biometric_bridge
#   .\install_windows_agent_task.ps1

$ErrorActionPreference = 'Stop'
$TaskName = 'HR-BiometricBridge'
$Here = $PSScriptRoot
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    Write-Host 'لم يُعثر على python في PATH.' -ForegroundColor Red
    exit 1
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
Write-Host "تم تسجيل المهمة '$TaskName' — كل 5 دقائق (python agent.py --once)." -ForegroundColor Green
Write-Host 'تأكد من اتصال VPN (Vigor) قبل التشغيل. اختبار: python agent.py --once' -ForegroundColor Cyan
