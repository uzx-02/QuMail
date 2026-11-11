@echo off
set "SSLKEYLOGFILE="
set "SSL_CERT_FILE="
set "REQUESTS_CA_BUNDLE="
set "CURL_CA_BUNDLE="
set "__CONDA_OPENSLL_CERT_FILE_SET="
title QuMail Secure Email
echo Launching QuMail Desktop...
if exist "%~dp0dist\QuMail-App\QuMail.exe" (
    start "" "%~dp0dist\QuMail-App\QuMail.exe" %*
) else if exist "%~dp0dist\QuMail-Modern\QuMail.exe" (
    start "" "%~dp0dist\QuMail-Modern\QuMail.exe" %*
) else (
    start "" "%~dp0dist\QuMail\QuMail.exe" %*
)
