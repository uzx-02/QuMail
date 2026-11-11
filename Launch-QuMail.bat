@echo off
set "SSLKEYLOGFILE="
set "SSL_CERT_FILE="
set "REQUESTS_CA_BUNDLE="
set "CURL_CA_BUNDLE="
set "__CONDA_OPENSLL_CERT_FILE_SET="
title QuMail 1.0 — Post-Quantum Secure Desktop (React 19 + Edge WebView2)

cd /d "%~dp0"

if exist "dist\QuMail-App\QuMail.exe" (
    echo [INFO] Launching standalone QuMail.exe...
    start "" "dist\QuMail-App\QuMail.exe" %*
    exit /b 0
)

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
    start "" ".venv-m1-clean\Scripts\python.exe" main.py %*
) else (
    echo [INFO] Starting QuMail Modern Desktop via system Python...
    start "" python main.py %*
)

exit /b 0
