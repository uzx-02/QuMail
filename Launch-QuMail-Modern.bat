@echo off
set "SSLKEYLOGFILE="
title QuMail 1.0 — Post-Quantum Secure Desktop (React 19 + Edge WebView2)
echo =====================================================================
echo  QuMail 1.0 — Post-Quantum Secure Corporate Email Client
echo  Modern React 19 + Microsoft Edge WebView2 + Physical TRNG Engine
echo =====================================================================
echo.

cd /d "%~dp0"

:: 1. If standalone .exe is compiled, launch it directly
if exist "dist\QuMail-App\QuMail.exe" (
    echo [INFO] Launching standalone QuMail.exe...
    start "" "dist\QuMail-App\QuMail.exe" %*
    exit /b 0
)
if exist "dist\QuMail-Modern\QuMail.exe" (
    echo [INFO] Launching standalone QuMail.exe...
    start "" "dist\QuMail-Modern\QuMail.exe" %*
    exit /b 0
)

:: 2. Otherwise ensure frontend bundle is built and launch via Python
if not exist "frontend\dist\index.html" (
    echo [INFO] Building modern React frontend bundle...
    cd frontend
    call npm run build
    cd ..
    echo [INFO] Build completed.
    echo.
)

if exist ".venv-m1-clean\Scripts\python.exe" (
    echo [INFO] Starting QuMail Modern Desktop via .venv-m1-clean...
    start "" ".venv-m1-clean\Scripts\python.exe" launch_react_desktop.py %*
) else (
    echo [INFO] Starting QuMail Modern Desktop via system Python...
    start "" python launch_react_desktop.py %*
)

exit /b 0
