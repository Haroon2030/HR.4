@echo off
REM Prints one line: full path to a working python.exe (never ZKBioTime).
setlocal EnableDelayedExpansion
set "HERE=%~dp0"

if exist "%HERE%python_path.txt" (
    set /p OUT=<"%HERE%python_path.txt"
    if defined OUT call :TryEcho "!OUT!"
    if defined OUT if /I not "!OUT!"=="INVALID" (
        echo !OUT!
        exit /b 0
    )
)

for %%V in (312 313 311 310) do (
    set "OUT="
    set "CAND=%LocalAppData%\Programs\Python\Python%%V\python.exe"
    if exist "!CAND!" call :TryEcho "!CAND!"
    if defined OUT if /I not "!OUT!"=="INVALID" (
        echo !OUT!
        exit /b 0
    )
)

for %%V in (312 313) do (
    set "OUT="
    set "CAND=%ProgramFiles%\Python%%V\python.exe"
    if exist "!CAND!" call :TryEcho "!CAND!"
    if defined OUT if /I not "!OUT!"=="INVALID" (
        echo !OUT!
        exit /b 0
    )
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%E in ('py -0p 2^>nul') do (
        set "CAND=%%E"
        set "CAND=!CAND:"=!"
        call :TryEcho "!CAND!"
        if defined OUT if /I not "!OUT!"=="INVALID" (
            echo !OUT!
            exit /b 0
        )
    )
    py -3.12 -c "import re" >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "delims=" %%E in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do (
            call :TryEcho "%%E"
            if defined OUT if /I not "!OUT!"=="INVALID" (
                echo !OUT!
                exit /b 0
            )
        )
        echo py -3.12
        exit /b 0
    )
)

exit /b 1

:TryEcho
set "OUT=%~1"
if /I "!OUT!"=="py -3.12" (
    py -3.12 -c "import re" >nul 2>&1
    if !errorlevel! neq 0 set "OUT=INVALID"
    exit /b 0
)
echo !OUT! | findstr /I "ZKBioTime" >nul
if !errorlevel! equ 0 set "OUT=INVALID" & exit /b 0
if not exist "!OUT!" set "OUT=INVALID" & exit /b 0
"!OUT!" -c "import re" >nul 2>&1
if !errorlevel! neq 0 set "OUT=INVALID"
exit /b 0
