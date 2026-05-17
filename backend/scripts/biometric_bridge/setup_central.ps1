# إعداد الوكيل المركزي (عدة فروع من PC واحد)
# يثبّت Python تلقائياً إن لم يكن موجوداً
# PowerShell: cd backend\scripts\biometric_bridge  ثم  .\setup_central.ps1

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
Set-Location $Here

. (Join-Path $Here 'ensure_python.ps1')

Write-Host '=== إعداد وكيل البصمة المركزي ===' -ForegroundColor Cyan

$pyInfo = Ensure-PythonForHrAgent

if (-not (Test-Path 'config.env')) {
    if (Test-Path 'config.example.env') {
        Copy-Item 'config.example.env' 'config.env'
        Write-Host 'تم إنشاء config.env — عدّل AGENT_API_KEY و SERVER_URL' -ForegroundColor Yellow
    } else {
        Write-Host 'ملف config.example.env غير موجود' -ForegroundColor Red
        exit 1
    }
}

$cfg = Get-Content 'config.env' -Raw
if ($cfg -match 'AGENT_API_KEY=ضع_المفتاح' -or $cfg -notmatch 'AGENT_API_KEY=\S+') {
    Write-Host 'افتح config.env وضع AGENT_API_KEY (نفس Dokploy: ATTENDANCE_AGENT_API_KEY)' -ForegroundColor Yellow
    notepad config.env
    Read-Host 'بعد الحفظ اضغط Enter للمتابعة'
}

Write-Host 'تثبيت الحزم...' -ForegroundColor Cyan
Invoke-PythonModule -PythonInfo $pyInfo -Arguments @('-m', 'pip', 'install', '-q', '-r', 'requirements.txt')

Write-Host 'جلب قائمة الأجهزة من السيرفر...' -ForegroundColor Cyan
Invoke-PythonModule -PythonInfo $pyInfo -Arguments @((Join-Path $Here 'agent.py'), '--sync-list')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'فحص الشبكة (يجب نجاح كل جهاز من هذا PC):' -ForegroundColor Cyan
Invoke-PythonModule -PythonInfo $pyInfo -Arguments @((Join-Path $Here 'agent.py'), '--probe')
$probeOk = ($LASTEXITCODE -eq 0)

Write-Host ''
if ($probeOk) {
    Write-Host 'تشغيل مزامنة واحدة...' -ForegroundColor Cyan
    Invoke-PythonModule -PythonInfo $pyInfo -Arguments @((Join-Path $Here 'agent.py'), '--once')
    Write-Host ''
    Write-Host 'للتشغيل التلقائي كل 5 دقائق (كمسؤول):' -ForegroundColor Green
    $pyExe = if ($pyInfo.UsePyLauncher) { (Get-Command python).Source } else { $pyInfo.Executable }
    Write-Host "  .\install_windows_agent_task.ps1 -PythonExecutable `"$pyExe`""
} else {
    Write-Host 'بعض الأجهزة غير متاحة من هذا PC.' -ForegroundColor Yellow
    Write-Host 'الحلول:' -ForegroundColor Yellow
    Write-Host '  1) Tailscale + Subnet Router في كل فرع'
    Write-Host '  2) VPN لكل فرع'
    Write-Host '  3) وكيل منفصل في كل فرع: install_branch.bat'
    Write-Host ''
    Write-Host 'بعد إصلاح الشبكة: python agent.py --probe'
}

Write-Host ''
Write-Host 'أوامر مفيدة:' -ForegroundColor Cyan
Write-Host '  python agent.py --sync-list'
Write-Host '  python agent.py --probe'
Write-Host '  python agent.py --once'
