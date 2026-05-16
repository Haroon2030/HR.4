# سحب البصمة من جهاز الفرع (شبكة محلية) وحفظها في قاعدة الإنتاج عبر SSH.
# الاستخدام: عدّل المتغيرات بالأسفل ثم شغّل PowerShell كمسؤول عادي:
#   cd backend\scripts
#   .\sync_attendance_production.ps1

$ErrorActionPreference = "Stop"

$VpsHost      = "72.61.107.230"
$SshUser      = "root"
$LocalDbPort  = 15433
$RemotePgPort = 15432   # socat على VPS يوجّه إلى Postgres الداخلي
$DeviceId     = 1
$BackendRoot  = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (Test-Path (Join-Path (Split-Path $PSScriptRoot -Parent) "manage.py")) {
    $BackendRoot = Split-Path $PSScriptRoot -Parent
}

# من .env الإنتاج — لا ترفع كلمات المرور إلى Git
$DbUser = $env:PROD_DB_USER
$DbPass = $env:PROD_DB_PASSWORD
$DbName = if ($env:PROD_DB_NAME) { $env:PROD_DB_NAME } else { "hr" }
if (-not $DbUser -or -not $DbPass) {
    Write-Host "عيّن PROD_DB_USER و PROD_DB_PASSWORD قبل التشغيل." -ForegroundColor Red
    exit 1
}

Write-Host "==> فتح نفق SSH إلى Postgres الإنتاج ($VpsHost)..." -ForegroundColor Cyan
$tunnel = Start-Process ssh -ArgumentList @(
    "-o", "BatchMode=yes",
    "-N",
    "-L", "${LocalDbPort}:127.0.0.1:${RemotePgPort}",
    "${SshUser}@${VpsHost}"
) -PassThru -WindowStyle Hidden

Start-Sleep -Seconds 2
try {
    $encPass = [uri]::EscapeDataString($DbPass)
    $env:DJANGO_ENV = "production"
    $env:DEBUG = "False"
    $env:SECRET_KEY = "local-attendance-sync-only"
    $env:ALLOWED_HOSTS = "localhost"
    $env:USE_HTTPS = "false"
    $env:USE_R2 = "False"
    $env:DATABASE_URL = "postgresql://${DbUser}:${encPass}@127.0.0.1:${LocalDbPort}/${DbName}?sslmode=disable"
    $env:BIOMETRIC_MOCK_MODE = "false"

    Set-Location $BackendRoot
    Write-Host "==> سحب من جهاز البصمة (يجب أن يكون PC على شبكة الفرع)..." -ForegroundColor Cyan
    python manage.py pull_biometric_attendance --device $DeviceId --real
}
finally {
    if ($tunnel -and -not $tunnel.HasExited) {
        Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
    }
}
