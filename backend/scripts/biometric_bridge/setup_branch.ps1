# تثبيت وكيل فرع واحد — يثبّت Python تلقائياً ويضيفه إلى PATH إن لم يكن موجوداً
#
#   .\setup_branch.ps1 -DeviceId 2 -DeviceIp 192.168.24.59 -BranchName alwaha -ApiKey "..." -InstallTask
#   .\setup_branch.ps1 -SkipPythonInstall   # إذا Python مثبت مسبقاً

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

Write-Host '=== تثبيت وكيل بصمة — فرع واحد ===' -ForegroundColor Cyan

Write-Host 'التحقق من Python...' -ForegroundColor Cyan
$script:HrPython = Ensure-PythonForHrAgent -SkipInstall:$SkipPythonInstall

if (-not $DeviceId) {
    $raw = Read-Host 'معرّف الجهاز في HR (مثال 2 للوحة)'
    if (-not [int]::TryParse($raw, [ref]$DeviceId) -or $DeviceId -lt 1) {
        Write-Host 'معرّف غير صالح' -ForegroundColor Red
        exit 1
    }
}
if (-not $DeviceIp) {
    $DeviceIp = Read-Host 'IP جهاز البصمة (مثال 192.168.24.59)'
}
if (-not $BranchName) {
    $BranchName = Read-Host 'اسم الفرع (لاتيني، مثال alwaha)'
}
if (-not $ApiKey) {
    $ApiKey = Read-Host 'AGENT_API_KEY (نفس ATTENDANCE_AGENT_API_KEY في Dokploy)'
}
$urlIn = Read-Host "رابط السيرفر [$ServerUrl]"
if ($urlIn) { $ServerUrl = $urlIn.TrimEnd('/') }

$configPath = Join-Path $Here 'config.env'
@(
    "# وكيل فرع — لا ترفع هذا الملف إلى Git",
    "SERVER_URL=$ServerUrl",
    "AGENT_API_KEY=$ApiKey",
    "AGENT_ID=branch-$BranchName",
    "DEVICE_ID=$DeviceId",
    "DEVICE_IP=$DeviceIp",
    "DEVICE_PORT=$DevicePort",
    "COMM_KEY=$CommKey",
    "DEVICE_LABEL=$BranchName",
    "POLL_INTERVAL_SEC=300",
    "TIMEOUT_SEC=20",
    "INCREMENTAL=true"
) -join "`n" | Set-Content -Path $configPath -Encoding UTF8

$listPath = Join-Path $Here 'devices.list'
if (Test-Path $listPath) {
    $bak = "$listPath.bak.$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    Move-Item $listPath $bak -Force
    Write-Host "تم نسخ devices.list القديم إلى $bak" -ForegroundColor Yellow
}

Write-Host 'تثبيت حزم Python (requests, pyzk)...' -ForegroundColor Cyan
$pipCode = Invoke-PythonModule -PythonInfo $script:HrPython -Arguments @(
    '-m', 'pip', 'install', '-r', (Join-Path $Here 'requirements.txt')
)
if ($pipCode -ne 0) {
    Write-Host 'فشل pip install — تحقق من الإنترنت' -ForegroundColor Red
    exit $pipCode
}

if (-not $SkipProbe) {
    Write-Host 'فحص الجهاز...' -ForegroundColor Cyan
    $probeCode = Invoke-Agent @('--probe')
    if ($probeCode -ne 0) {
        Write-Host 'الفحص فشل — ping + Comm Key=0 + نفس شبكة LAN' -ForegroundColor Yellow
    } else {
        Write-Host 'مزامنة واحدة...' -ForegroundColor Cyan
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
    if ($pyExe -and (Test-Path -LiteralPath $pyExe)) {
        & (Join-Path $Here 'install_windows_agent_task.ps1') -PythonExecutable $pyExe
    } else {
        & (Join-Path $Here 'install_windows_agent_task.ps1')
    }
} else {
    Write-Host ''
    Write-Host 'للتشغيل التلقائي كل 5 دقائق (كمسؤول):' -ForegroundColor Green
    Write-Host '  .\setup_branch.ps1 ... -InstallTask'
}

Write-Host ''
Write-Host 'تم الإعداد.' -ForegroundColor Green
Write-Host "  python agent.py --once --device $DeviceId" -ForegroundColor Cyan
