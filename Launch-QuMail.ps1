# QuMail 1.0 — Windows Desktop Launcher
$ErrorActionPreference = 'Stop'
Remove-Item Env:SSLKEYLOGFILE -ErrorAction SilentlyContinue
Remove-Item Env:SSL_CERT_FILE -ErrorAction SilentlyContinue
Remove-Item Env:REQUESTS_CA_BUNDLE -ErrorAction SilentlyContinue
Remove-Item Env:CURL_CA_BUNDLE -ErrorAction SilentlyContinue
Remove-Item Env:__CONDA_OPENSLL_CERT_FILE_SET -ErrorAction SilentlyContinue
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$appExe = Join-Path $ScriptDir "dist\QuMail-App\QuMail.exe"
if (Test-Path $appExe) {
    Write-Host "[INFO] Starting QuMail 1.0 Production Binary ($appExe)..." -ForegroundColor Cyan
    if ($args -and $args.Count -gt 0) {
        Start-Process -FilePath $appExe -WorkingDirectory $ScriptDir -ArgumentList $args
    } else {
        Start-Process -FilePath $appExe -WorkingDirectory $ScriptDir
    }
    exit 0
}

$venvPy = Join-Path $ScriptDir ".venv-m1-clean\Scripts\python.exe"
$pyCmd = if (Test-Path $venvPy) { $venvPy } else { "python" }

Write-Host "[INFO] Starting QuMail 1.0 Desktop via Python ($pyCmd)..." -ForegroundColor Cyan
if ($args -and $args.Count -gt 0) {
    & $pyCmd (Join-Path $ScriptDir "main.py") @args
} else {
    & $pyCmd (Join-Path $ScriptDir "main.py")
}
