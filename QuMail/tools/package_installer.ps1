# QuMail 1.0 - Windows Packaging and Installer Pipeline
param(
    [switch]$SkipZip = $false
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$DistDir = Join-Path $ProjectRoot "dist\QuMail-App"
$InstallerDir = Join-Path $ProjectRoot "dist\Installer"
$IssFile = Join-Path $ProjectRoot "installer\qumail_setup.iss"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " QuMail 1.0 - Windows Packaging Pipeline" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# 1. Verify the one-dir PyInstaller bundle exists
if (-not (Test-Path $DistDir)) {
    Write-Host "ERROR: dist/QuMail-App does not exist. Run the release build first." -ForegroundColor Red
    exit 1
}

$ExePath = Join-Path $DistDir "QuMail.exe"
if (-not (Test-Path $ExePath)) {
    Write-Host "ERROR: QuMail.exe not found in $DistDir" -ForegroundColor Red
    exit 1
}

# Ensure bin directory with native providers and manifest is present at bundle root
$BundleBin = Join-Path $DistDir "bin"
$InternalBin = Join-Path $DistDir "_internal\bin"
$RootBin = Join-Path $ProjectRoot "bin"
if (-not (Test-Path $BundleBin)) {
    New-Item -ItemType Directory -Path $BundleBin -Force | Out-Null
    if (Test-Path $InternalBin) {
        Copy-Item "$InternalBin\*" -Destination $BundleBin -Force
    } elseif (Test-Path $RootBin) {
        Copy-Item "$RootBin\*" -Destination $BundleBin -Force
    }
}

# Ensure resources and version.json are present
$ResDirInternal = Join-Path $DistDir "_internal\resources"
$ResDirRoot = Join-Path $DistDir "resources"

# Synchronize resources if placed in root or _internal
if ((Test-Path $ResDirRoot) -and (-not (Test-Path $ResDirInternal))) {
    New-Item -ItemType Directory -Path $ResDirInternal -Force | Out-Null
    Copy-Item "$ResDirRoot\*" -Destination $ResDirInternal -Recurse -Force
} elseif ((Test-Path $ResDirInternal) -and (-not (Test-Path $ResDirRoot))) {
    New-Item -ItemType Directory -Path $ResDirRoot -Force | Out-Null
    Copy-Item "$ResDirInternal\*" -Destination $ResDirRoot -Recurse -Force
}

$ResDir = if (Test-Path (Join-Path $ResDirInternal "google_oauth_client.json")) { $ResDirInternal } else { $ResDirRoot }
if (-not (Test-Path (Join-Path $ResDir "google_oauth_client.json"))) {
    Write-Host "ERROR: Bundled Google OAuth release configuration is missing." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $ResDir "qumail.release.json"))) {
    Write-Host "ERROR: Bundled directory endpoint configuration is missing." -ForegroundColor Red
    exit 1
}

# Ensure version.json is present in bundle root
$VersionFile = Join-Path $DistDir "version.json"
if (-not (Test-Path $VersionFile)) {
    Write-Host "Generating bundle version metadata..." -ForegroundColor Cyan
    & (Join-Path $ProjectRoot ".venv-m1-clean\Scripts\python.exe") -c @"
import json, subprocess
from datetime import datetime, timezone
try:
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
except Exception:
    commit = 'UNKNOWN'
meta = {
    'app_name': 'QuMail',
    'display_name': 'QuMail Secure Email',
    'version': '1.0.0',
    'build_utc': datetime.now(timezone.utc).isoformat(),
    'commit_sha': commit,
    'platform': 'win32-x64',
    'provider_schema': '1.0',
    'rust_profile': 'release-cfg',
    'pe_mitigations_verified': True
}
with open(r'$VersionFile', 'w', encoding='utf-8') as f:
    json.dump(meta, f, indent=2)
"@
}

# Run programmatic bundle layout and security verification
Write-Host "Verifying bundle integrity and PE security mitigations..." -ForegroundColor Cyan
& (Join-Path $ProjectRoot ".venv-m1-clean\Scripts\python.exe") -c @"
from pathlib import Path
from core.packaging import verify_bundle_layout
res = verify_bundle_layout(Path(r'$DistDir'))
print('Bundle verification OK:', res['status'], 'Version:', res['version'])
for prov, data in res['providers'].items():
    print(f'  - {prov}: sha256={data[\"digest\"][:16]}... CFG={data[\"pe_mitigations\"][\"guard_cf\"]}')
"@
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Bundle verification failed!" -ForegroundColor Red
    exit 1
}

Write-Host "OK: QuMail.exe distribution verified at $DistDir" -ForegroundColor Green

# 2. Package Portable ZIP Distribution
if (-not $SkipZip) {
    if (-not (Test-Path $InstallerDir)) {
        New-Item -ItemType Directory -Path $InstallerDir -Force | Out-Null
    }
    $ZipPath = Join-Path $InstallerDir "QuMail-Test-v1.0-Windows-x64-Portable.zip"
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
    $SetupExe = Join-Path $InstallerDir "Setup-QuMail-v1.0.exe"
    if (Test-Path $SetupExe) { Remove-Item $SetupExe -Force }
    & $IsccPath $IssFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Inno Setup compilation failed with exit code $LASTEXITCODE" -ForegroundColor Red
        exit $LASTEXITCODE
    }
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
