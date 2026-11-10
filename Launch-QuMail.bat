@echo off
set "SSLKEYLOGFILE="
title QuMail Secure Email
echo Launching QuMail Desktop...
if exist "%~dp0dist\QuMail-App\QuMail.exe" (
    start "" "%~dp0dist\QuMail-App\QuMail.exe" %*
) else if exist "%~dp0dist\QuMail-Modern\QuMail.exe" (
    start "" "%~dp0dist\QuMail-Modern\QuMail.exe" %*
) else (
    start "" "%~dp0dist\QuMail\QuMail.exe" %*
)
