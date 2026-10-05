# Run from repository root after fetching the pinned sources in inputs.json.
# Development build only; never installs outside tmp/m2 or publishes artifacts.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path .).Path
$source = Join-Path $root 'tmp/m2/openssl-3.5.9'
$prefix = Join-Path $root 'tmp/m2/openssl-install'
$perl = Join-Path $root 'tmp/m2/perl/perl/bin/perl.exe'
$hash = (Get-FileHash 'tmp/m2/openssl-3.5.9.tar.gz' -Algorithm SHA256).Hash
if ($hash -ne '603F5602E2EEF00D77FBD429D34DCD5822BB301757A1BC9CDB24C670F1EB859A') {
    throw 'OpenSSL source archive hash mismatch'
}
$vs = & "${env:ProgramFiles(x86)}/Microsoft Visual Studio/Installer/vswhere.exe" -latest -products '*' -property installationPath
Import-Module (Join-Path $vs 'Common7/Tools/Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vs -SkipAutomaticLocation -DevCmdArguments '-arch=amd64 -host_arch=amd64'
Push-Location $source
try {
    & $perl Configure VC-WIN64A no-shared no-tests no-module no-comp no-asm "--prefix=$prefix" '--libdir=lib'
    if ($LASTEXITCODE -ne 0) { throw 'OpenSSL configure failed' }
    & nmake /nologo build_libs
    if ($LASTEXITCODE -ne 0) { throw 'OpenSSL build failed' }
    & nmake /nologo install_dev
    if ($LASTEXITCODE -ne 0) { throw 'OpenSSL install failed' }
} finally { Pop-Location }
