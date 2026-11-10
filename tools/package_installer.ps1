# QuMail 1.0 - Windows Packaging and Installer Pipeline
param(
    [switch]$SkipZip = $false
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$DistDir = Join-Path $ProjectRoot "dist\QuMail"
$InstallerDir = Join-Path $ProjectRoot "dist\installer"
$IssFile = Join-Path $ProjectRoot "installer\qumail_setup.iss"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " QuMail 1.0 - Windows Packaging Pipeline" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# 1. Verify dist\QuMail exists
if (-not (Test-Path $DistDir)) {
    Write-Host "ERROR: dist/QuMail does not exist. Run PyInstaller first." -ForegroundColor Red
    exit 1
}

$ExePath = Join-Path $DistDir "QuMail.exe"
if (-not (Test-Path $ExePath)) {
    Write-Host "ERROR: QuMail.exe not found in $DistDir" -ForegroundColor Red
    exit 1
}

# Ensure resources and version.json are present
$ResDir = Join-Path $DistDir "resources"
if (-not (Test-Path $ResDir)) {
    New-Item -ItemType Directory -Path $ResDir -Force | Out-Null
    Copy-Item (Join-Path $ProjectRoot "resources\*") -Destination $ResDir -Recurse -Force
}
Copy-Item (Join-Path $ProjectRoot "version.json") -Destination $DistDir -Force

Write-Host "OK: QuMail.exe distribution verified at $DistDir" -ForegroundColor Green

# 2. Package Portable ZIP Distribution
if (-not $SkipZip) {
    if (-not (Test-Path $InstallerDir)) {
        New-Item -ItemType Directory -Path $InstallerDir -Force | Out-Null
    }
    $ZipPath = Join-Path $InstallerDir "QuMail-v1.0-Windows-x64-Portable.zip"
    Write-Host "INFO: Creating portable ZIP archive: $ZipPath..." -ForegroundColor Yellow
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    Compress-Archive -Path "$DistDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal
    $ZipSizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 2)
    Write-Host "SUCCESS: Portable ZIP package created successfully ($ZipSizeMB MB)" -ForegroundColor Green
}

# 3. Locate Inno Setup Compiler (ISCC.exe)
$IsccCandidates = @(
    "iscc",
    "C:\Program Files\Inno Setup 7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 7\ISCC.exe",
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

$IsccPath = $null
foreach ($cand in $IsccCandidates) {
    if (Get-Command $cand -ErrorAction SilentlyContinue) {
        $IsccPath = $cand
        break
    } elseif (Test-Path $cand) {
        $IsccPath = $cand
        break
    }
}

if ($IsccPath) {
    Write-Host "INFO: Compiling Windows Installer with Inno Setup..." -ForegroundColor Yellow
    & $IsccPath $IssFile
    $SetupExe = Join-Path $InstallerDir "Setup-QuMail-v1.0.exe"
    if (Test-Path $SetupExe) {
        $SetupSizeMB = [math]::Round((Get-Item $SetupExe).Length / 1MB, 2)
        Write-Host "SUCCESS: Windows Setup Wizard compiled: $SetupExe ($SetupSizeMB MB)" -ForegroundColor Green
    }
} else {
    Write-Host "NOTE: Inno Setup (ISCC.exe) was not found in standard paths." -ForegroundColor Yellow
    Write-Host "      Installer script is ready at: $IssFile" -ForegroundColor Cyan
    Write-Host "      To compile Setup-QuMail-v1.0.exe, install Inno Setup from https://jrsoftware.org/isdl.php" -ForegroundColor Cyan
}

Write-Host "`nPackaging Pipeline Complete." -ForegroundColor Green
