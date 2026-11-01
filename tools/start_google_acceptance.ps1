param(
    [Parameter(Mandatory = $true)][string]$GoogleClient,
    [Parameter(Mandatory = $true)][string]$Vault,
    [switch]$CheckOnly,
    [switch]$AllowNewVault
)

$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $repoPath '.venv-m1-clean\Scripts\python.exe'
$clientPath = [System.IO.Path]::GetFullPath($GoogleClient)
$vaultPath = [System.IO.Path]::GetFullPath($Vault)
foreach ($requiredPath in @($pythonPath, $clientPath,
        (Join-Path $repoPath 'tmp\m2\target\debug\qumail-m3-provider.exe'),
        (Join-Path $repoPath 'tmp\m2\target\debug\qumail-m5-provider.exe'))) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required file is missing or inaccessible: $requiredPath. Use the actual provisioned path, not C:\chosen placeholders."
    }
}
if (Test-Path -LiteralPath $vaultPath -PathType Container) {
    throw "Vault path names a directory, not a database file: $vaultPath"
}
$vaultExists = Test-Path -LiteralPath $vaultPath -PathType Leaf
if (-not $vaultExists -and -not $AllowNewVault) {
    throw "Existing vault is missing or inaccessible: $vaultPath. Nothing was created. Confirm its location before proceeding. Use -AllowNewVault only for an intentionally NEW disposable vault; it cannot recover old accounts or keys."
}

Push-Location -LiteralPath $repoPath
$oldQtPlatform = $env:QT_QPA_PLATFORM
try {
    & $pythonPath -c 'import sys; from transport.development_google import client_configuration; client_configuration(sys.argv[1])' $clientPath
    if ($LASTEXITCODE -ne 0) { throw 'Desktop-client validation failed. Select the downloaded Desktop-app JSON, not a placeholder or another client type.' }
    Write-Host 'Desktop client configuration: valid (contents hidden)'
    Write-Host "Vault: $vaultPath"
    if ($vaultExists) {
        Write-Host 'Existing vault found. In Settings choose Unlock, not Create vault.'
    } else {
        Write-Host 'Explicit NEW-vault mode. In Settings choose Create vault. No database has been created by this launcher.'
    }
    if ($CheckOnly) {
        Write-Host 'Preflight passed. Application not launched; vault contents not read; no authorization started.'
        return
    }
    Write-Host 'Close any prior QuMail instance. Only the three designated A/B test sends are authorized.'
    $env:QT_QPA_PLATFORM = 'windows'
    & $pythonPath main.py --dev-mailbox --dev-gmail-submit --dev-vault $vaultPath --google-client $clientPath
    if ($LASTEXITCODE -ne 0) { throw "QuMail exited with code $LASTEXITCODE" }
} finally {
    $env:QT_QPA_PLATFORM = $oldQtPlatform
    Pop-Location
}
