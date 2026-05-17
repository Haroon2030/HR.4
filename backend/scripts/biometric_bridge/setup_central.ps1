# إعداد الوكيل المركزي (عدة فروع من PC واحد)
# PowerShell: cd backend\scripts\biometric_bridge  ثم  .\setup_central.ps1

$ErrorActionPreference = 'Stop'
$Here = $PSScriptRoot
Set-Location $Here

Write-Host '=== إعداد وكيل البصمة المركزي ===' -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host 'ثبّت Python 3.12+ وأضفه إلى PATH' -ForegroundColor Red
    exit 1
}

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
python -m pip install -q -r requirements.txt

Write-Host 'جلب قائمة الأجهزة من السيرفر...' -ForegroundColor Cyan
python agent.py --sync-list
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host 'فحص الشبكة (يجب نجاح كل جهاز من هذا PC):' -ForegroundColor Cyan
python agent.py --probe
$probeOk = ($LASTEXITCODE -eq 0)

Write-Host ''
if ($probeOk) {
    Write-Host 'تشغيل مزامنة واحدة...' -ForegroundColor Cyan
    python agent.py --once
    Write-Host ''
    Write-Host 'للتشغيل التلقائي كل 5 دقائق (كمسؤول):' -ForegroundColor Green
    Write-Host '  .\install_windows_agent_task.ps1'
} else {
    Write-Host 'بعض الأجهزة غير متاحة من هذا PC.' -ForegroundColor Yellow
    Write-Host 'الحلول:' -ForegroundColor Yellow
    Write-Host '  1) Tailscale على PC المكتب + جهاز داخل كل فرع (Subnet Router)'
    Write-Host '  2) VPN منفصل لكل فرع قبل التشغيل'
    Write-Host '  3) أو وكيل منفصل في كل فرع بدون Tailscale'
    Write-Host ''
    Write-Host 'بعد إصلاح الشبكة: python agent.py --probe'
}

Write-Host ''
Write-Host 'أوامر مفيدة:' -ForegroundColor Cyan
Write-Host '  python agent.py --sync-list   # بعد إضافة جهاز في HR'
Write-Host '  python agent.py --probe'
Write-Host '  python agent.py --once'
