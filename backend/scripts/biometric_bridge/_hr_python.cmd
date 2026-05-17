@echo off
REM Prints one line: full path to python.exe OR "py -3.12" for the launcher.
REM Skips ZKBioTime bundled Python (often broken: SRE module mismatch).
setlocal EnableDelayedExpansion
set "HERE=%~dp0"
set "OUT="

if exist "%HERE%python_path.txt" (
    set /p OUT=<"%HERE%python_path.txt"
    if defined OUT (
        echo !OUT!
        exit /b 0
    )
)

for %%V in (312 313 311) do (
    set "CAND=%LocalAppData%\Programs\Python\Python%%V\python.exe"
    if exist "!CAND!" (
        "!CAND!" -c "import re" >nul 2>&1
        if !errorlevel! equ 0 (
            echo !CAND!
            exit /b 0
        )
    )
)

where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3.12 -c "import re" >nul 2>&1
    if !errorlevel! equ 0 (
        echo py -3.12
        exit /b 0
    )
)

exit /b 1
