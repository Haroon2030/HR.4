# Install Python and add to PATH (ASCII-only for Windows PowerShell 5.1)
# Usage: . .\ensure_python.ps1; $py = Ensure-PythonForHrAgent

function Refresh-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = @($machine, $user) -join ';'
}

function Test-PythonExecutable {
    param([string]$Exe)
    if (-not $Exe -or -not (Test-Path -LiteralPath $Exe)) { return $false }
    if ($Exe -match '\\ZKBioTime\\') { return $false }
    try {
        $null = & $Exe -c "import re, site" 2>&1
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

function Find-PythonExecutables {
    $found = [System.Collections.Generic.List[string]]::new()
    foreach ($cmd in @('python', 'py')) {
        $c = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($c -and $c.Source -and ($found -notcontains $c.Source)) {
            if ($c.Source -notmatch '\\ZKBioTime\\') {
                $found.Add($c.Source)
            }
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
                if ($_.FullName -match '\\ZKBioTime\\') { return }
                if ($found -notcontains $_.FullName) { $found.Add($_.FullName) }
            }
    }
    return $found
}

function Write-HrPythonPathFile {
    param(
        [string]$BridgeDir,
        [hashtable]$PythonInfo
    )
    $out = Join-Path $BridgeDir 'python_path.txt'
    $line = $PythonInfo.Executable
    if ($PythonInfo.UsePyLauncher) {
        $resolved = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($resolved) {
            $line = $resolved.Trim()
        } else {
            $line = 'py -3.12'
        }
    }
    $line | Set-Content -Path $out -Encoding ASCII -NoNewline
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
    $null = Add-DirectoryToUserPath -Directory $pythonDir
    if (Test-Path $scriptsDir) {
        $null = Add-DirectoryToUserPath -Directory $scriptsDir
    }
    Refresh-SessionPath
}

function Install-PythonViaWinget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host 'winget not found. Install Python 3.12 from python.org (check Add to PATH).' -ForegroundColor Red
        return $false
    }
    Write-Host 'Installing Python 3.12 via winget (may take a few minutes)...' -ForegroundColor Cyan
    $wingetArgs = @(
        'install', '--id', 'Python.Python.3.12', '-e', '--source', 'winget',
        '--accept-package-agreements', '--accept-source-agreements'
    )
    & winget @wingetArgs
    if ($LASTEXITCODE -gt 1) {
        Write-Host "winget exit code $LASTEXITCODE (may already be installed)" -ForegroundColor Yellow
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
        if (-not (Test-PythonExecutable -Exe $exe)) {
            if (-not $Quiet) {
                Write-Host "Skip broken Python (ZKBioTime?): $exe" -ForegroundColor Yellow
            }
            continue
        }
        Register-PythonOnPath -PythonExe $exe
        if (-not $Quiet) {
            $ver = & $exe --version 2>&1
            Write-Host "Python OK: $exe ($ver)" -ForegroundColor Green
        }
        return @{ Executable = $exe; UsePyLauncher = $false }
    }

    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $py312 = & py -3.12 -c "import re" 2>&1
        if ($LASTEXITCODE -eq 0) {
            if (-not $Quiet) {
                $ver = & py -3.12 --version 2>&1
                Write-Host "Python OK (py -3.12): $ver" -ForegroundColor Green
            }
            return @{ Executable = 'py'; UsePyLauncher = $true }
        }
    }

    if ($SkipInstall) {
        throw 'Python not found. Run without -SkipPythonInstall or install from python.org'
    }

    if (-not (Install-PythonViaWinget)) {
        throw 'Could not install Python automatically'
    }

    $after = Find-PythonExecutables | Where-Object { $_ -ne 'py' -and $_ -notlike '*\py.exe' }
    if (-not $after -or $after.Count -eq 0) {
        throw 'Installer finished but python.exe not found. Close CMD, open Admin CMD, try again.'
    }

    $exe = $null
    foreach ($candidate in $after) {
        if (Test-PythonExecutable -Exe $candidate) {
            $exe = $candidate
            break
        }
    }
    if (-not $exe) {
        throw 'Python found but broken (often ZKBioTime on PATH). Install Python 3.12 from python.org'
    }
    Register-PythonOnPath -PythonExe $exe
    if (-not $Quiet) {
        $ver = & $exe --version 2>&1
        Write-Host "Python installed and added to PATH: $exe ($ver)" -ForegroundColor Green
    }
    return @{ Executable = $exe; UsePyLauncher = $false }
}

function Invoke-PythonModule {
    param(
        [hashtable]$PythonInfo,
        [string[]]$Arguments
    )
    if ($PythonInfo.UsePyLauncher) {
        & py -3.12 @Arguments
    } else {
        & $PythonInfo.Executable @Arguments
    }
    return $LASTEXITCODE
}
