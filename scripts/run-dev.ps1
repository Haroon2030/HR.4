# تشغيل موقع HR محلياً — يبقى حتى تغلق النافذة أو Ctrl+C
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\backend"

$env:DJANGO_ENV = "development"
$env:CSRF_TRUSTED_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"

$Python = "$Root\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Host "HR dev server: http://127.0.0.1:8000/" -ForegroundColor Cyan
Write-Host "اضغط Ctrl+C للإيقاف" -ForegroundColor DarkGray

& $Python manage.py runserver 127.0.0.1:8000
