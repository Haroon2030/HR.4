# تثبيت Python وإضافته لـ PATH — يُستدعى من setup_branch.ps1 و setup_central.ps1
# Usage: . .\ensure_python.ps1; $py = Ensure-PythonForHrAgent

function Refresh-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = @($machine, $user) -join ';'
}

function Find-PythonExecutables {
    $found = [System.Collections.Generic.List[string]]::new()
    foreach ($cmd in @('python', 'py')) {
        $c = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($c -and $c.Source -and ($found -notcontains $c.Source)) {
            $found.Add($c.Source)
        }
    }
    $roots = @(
        "$env:LocalAppData\Programs\Python",
        "${env:ProgramFiles}\Python312",
        "${env:ProgramFiles}\Python313",
        "${env:ProgramFiles(x86)}\Python312"
    )
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        Get-ChildItem -Path $root -Filter 'python.exe' -Recurse -ErrorAction SilentlyContinue |
            ForEach-Object {
                if ($found -notcontains $_.FullName) { $found.Add($_.FullName) }
            }
    }
    return $found
}

function Add-DirectoryToUserPath {
    param([string]$Directory)
    if (-not $Directory -or -not (Test-Path $Directory)) { return $false }
    $normalized = ([System.IO.Path]::GetFullPath($Directory)).TrimEnd('\')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $userPath) { $userPath = '' }
    $parts = $userPath -split ';' | Where-Object { $_ }
    $already = $parts | Where-Object {
        ([System.IO.Path]::GetFullPath($_)).TrimEnd('\') -eq $normalized
    }
    if ($already) { return $false }
    $newPath = if ($userPath) { "$normalized;$userPath" } else { $normalized }
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    return $true
}

function Register-PythonOnPath {
    param([string]$PythonExe)
    $pythonDir = Split-Path -Parent $PythonExe
    $scriptsDir = Join-Path $pythonDir 'Scripts'
    $changed = Add-DirectoryToUserPath -Directory $pythonDir
    if (Test-Path $scriptsDir) {
        if (Add-DirectoryToUserPath -Directory $scriptsDir) { $changed = $true }
    }
    Refresh-SessionPath
    return $changed
}

function Install-PythonViaWinget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host 'winget غير متوفر — ثبّت Python يدوياً من python.org مع خيار Add to PATH' -ForegroundColor Red
        return $false
    }
    Write-Host 'تثبيت Python 3.12 (قد يستغرق دقائق)...' -ForegroundColor Cyan
    $wingetArgs = @(
        'install', '--id', 'Python.Python.3.12', '-e', '--source', 'winget',
        '--accept-package-agreements', '--accept-source-agreements'
    )
    & winget @wingetArgs
    if ($LASTEXITCODE -gt 1) {
        Write-Host "winget أنهى بالرمز $LASTEXITCODE (قد يكون مثبتاً مسبقاً)" -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 2
    Refresh-SessionPath
    return $true
}

function Ensure-PythonForHrAgent {
    param(
        [switch]$SkipInstall,
        [switch]$Quiet
    )

    $existing = Find-PythonExecutables
  foreach ($exe in $existing) {
        if ($exe -eq 'py') { continue }
        if ($exe -like '*\py.exe') { continue }
        Register-PythonOnPath -PythonExe $exe | Out-Null
        if (-not $Quiet) {
            $ver = & $exe --version 2>&1
            Write-Host "Python موجود: $exe ($ver)" -ForegroundColor Green
        }
        return @{ Executable = $exe; UsePyLauncher = $false }
    }

    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $ver = & py --version 2>&1
        if (-not $Quiet) { Write-Host "Python (py launcher): $ver" -ForegroundColor Green }
        return @{ Executable = 'py'; UsePyLauncher = $true }
    }

    if ($SkipInstall) {
        throw 'Python غير مثبت. شغّل التثبيت بدون -SkipPythonInstall أو ثبّت من python.org'
    }

    if (-not (Install-PythonViaWinget)) {
        throw 'تعذّر تثبيت Python تلقائياً'
    }

    $after = Find-PythonExecutables | Where-Object { $_ -ne 'py' -and $_ -notlike '*\py.exe' }
    if (-not $after -or $after.Count -eq 0) {
        throw 'تم تشغيل المثبت لكن python.exe غير ظاهر — أعد تشغيل CMD كمسؤول أو سجّل خروج وادخل ويندوز'
    }

    $exe = $after[0]
    Register-PythonOnPath -PythonExe $exe | Out-Null
    if (-not $Quiet) {
        $ver = & $exe --version 2>&1
        Write-Host "تم تثبيت Python وإضافته لـ PATH: $exe ($ver)" -ForegroundColor Green
    }
    return @{ Executable = $exe; UsePyLauncher = $false }
}

function Invoke-PythonModule {
    param(
        [hashtable]$PythonInfo,
        [string[]]$Arguments
    )
    if ($PythonInfo.UsePyLauncher) {
        & py @Arguments
    } else {
        & $PythonInfo.Executable @Arguments
    }
    return $LASTEXITCODE
}
