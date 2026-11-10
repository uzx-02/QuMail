@echo off
title QuMail Secure Email
echo Launching QuMail Desktop...
if exist "%~dp0dist\QuMail-Modern\QuMail.exe" (
    start "" "%~dp0dist\QuMail-Modern\QuMail.exe" %*
) else (
    start "" "%~dp0dist\QuMail\QuMail.exe" %*
)
