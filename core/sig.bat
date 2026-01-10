@echo off
setlocal

:: Folder where this BAT lives
set "SIG_DIR=%~dp0"

:: Path to Sigil executable
set "SIG_EXE=%SIG_DIR%sigil.exe"

:: Safety check
if not exist "%SIG_EXE%" (
    echo sigil.exe not found in:
    echo %SIG_DIR%
    pause
    exit /b 1
)

:: No arguments → open GUI
if "%~1"=="" (
    start "" "%SIG_EXE%"
    exit /b
)

:: With arguments (sig <file.sig>, drag & drop, etc.)
:: Forward all args to sigil.exe
start "" "%SIG_EXE%" %*
exit /b
