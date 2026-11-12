@echo off
set "SSLKEYLOGFILE="
set "SSL_CERT_FILE="
set "REQUESTS_CA_BUNDLE="
set "CURL_CA_BUNDLE="
set "__CONDA_OPENSLL_CERT_FILE_SET="
setlocal
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"
if exist "%SCRIPT_DIR%dist\QuMail-App\QuMail.exe" (
    echo [INFO] Starting QuMail 1.0 Production Binary...
    start "" /d "%SCRIPT_DIR%" "%SCRIPT_DIR%dist\QuMail-App\QuMail.exe" %*
    exit /b 0
)
if exist "%SCRIPT_DIR%.venv-m1-clean\Scripts\python.exe" (
    echo [INFO] Starting QuMail 1.0 Desktop via Python...
    start "" /d "%SCRIPT_DIR%" "%SCRIPT_DIR%.venv-m1-clean\Scripts\python.exe" "%SCRIPT_DIR%main.py" %*
    exit /b 0
)
python "%SCRIPT_DIR%main.py" %*
