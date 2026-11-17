param(
    [Parameter(Mandatory = $false)][string]$GoogleClient,
    [Parameter(Mandatory = $true)][string]$Vault,
    [switch]$CheckOnly,
    [switch]$DryRun,
    [switch]$AllowNewVault,
    [switch]$EnableGmailSubmit,
    [switch]$SettingsOnly
)

$ErrorActionPreference = 'Stop'

if ($DryRun -and $EnableGmailSubmit) {
    throw "-DryRun and -EnableGmailSubmit are mutually exclusive. Dry-run mode strictly disables Gmail SMTP submission."
}
if ($SettingsOnly -and $EnableGmailSubmit) {
    throw "-SettingsOnly and -EnableGmailSubmit are mutually exclusive. Settings-only mode has no mail submission capability."
}

$repoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $repoPath '.venv-m1-clean\Scripts\python.exe'
$vaultHelper = Join-Path $repoPath 'bin\qumail-vault-provider.exe'
$cryptoHelper = Join-Path $repoPath 'bin\qumail-crypto-provider.exe'
$vaultPath = [System.IO.Path]::GetFullPath($Vault)

foreach ($requiredPath in @($pythonPath, $vaultHelper, $cryptoHelper)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Required runtime component is missing or inaccessible: $requiredPath."
    }
}

$hasClient = -not [string]::IsNullOrWhiteSpace($GoogleClient)
$clientPath = $null
if ($hasClient) {
    $clientPath = [System.IO.Path]::GetFullPath($GoogleClient)
    if (-not (Test-Path -LiteralPath $clientPath -PathType Leaf)) {
        throw "Google client JSON file is missing or inaccessible: $clientPath. Use the actual downloaded desktop client JSON path."
    }
} elseif ($EnableGmailSubmit) {
    throw "-EnableGmailSubmit requires an explicitly configured Google client JSON file via -GoogleClient."
}

if (Test-Path -LiteralPath $vaultPath -PathType Container) {
    throw "Vault path names an existing directory, not a database file: $vaultPath"
}

$vaultDir = Split-Path -Parent $vaultPath
if (-not [string]::IsNullOrWhiteSpace($vaultDir) -and -not (Test-Path -LiteralPath $vaultDir -PathType Container)) {
    if ($CheckOnly) {
        Write-Host "Vault parent directory does not exist yet: $vaultDir"
    } elseif ($AllowNewVault) {
        try {
            New-Item -ItemType Directory -Force -Path $vaultDir | Out-Null
            Write-Host "Created parent directory for new vault: $vaultDir"
        } catch {
            throw "Failed to create parent directory for new vault '$vaultDir': $($_.Exception.Message)"
        }
    } else {
        throw "Vault parent directory does not exist: $vaultDir. Confirm path or specify -AllowNewVault for a new vault location."
    }
}

$vaultExists = Test-Path -LiteralPath $vaultPath -PathType Leaf
if (-not $vaultExists -and -not $CheckOnly -and -not $AllowNewVault) {
    throw "Existing vault is missing or inaccessible: $vaultPath. Nothing was created. Confirm its location before proceeding. Use -AllowNewVault only for an intentionally NEW disposable vault; it cannot recover old accounts or keys."
}

Push-Location -LiteralPath $repoPath
$oldQtPlatform = $env:QT_QPA_PLATFORM
$oldQtPluginPath = $env:QT_PLUGIN_PATH
try {
    if ($hasClient) {
        & $pythonPath -c 'import sys; from transport.development_google import client_configuration; client_configuration(sys.argv[1])' $clientPath
        if ($LASTEXITCODE -ne 0) { throw 'Desktop-client validation failed. Select the downloaded Desktop-app JSON, not a placeholder or another client type.' }
        Write-Host 'Desktop client configuration: valid (contents hidden)'
    } else {
        Write-Host 'Desktop client configuration: omitted (offline / identity-only mode)'
    }

    Write-Host "Vault path: $vaultPath"
    if ($vaultExists) {
        Write-Host 'Existing vault found. In Settings choose Unlock, not Create vault.'
    } elseif ($AllowNewVault) {
        Write-Host 'Explicit NEW-vault mode. In Settings choose Create vault. No database has been created by this launcher.'
    } else {
        Write-Host 'Target vault does not exist yet (pre-vault check mode). In Settings choose Create vault when initialized with -AllowNewVault.'
    }

    if ($CheckOnly) {
        Write-Host 'Preflight passed. Application not launched; Google client configuration validated; no user tokens accessed; no vault database, directory, or Credential Manager entry created or accessed.'
        return
    }

    $appArgs = @('main.py')
    if ($SettingsOnly) {
        $appArgs += @('--dev-identity', '--dev-vault', $vaultPath)
        if ($hasClient) { $appArgs += @('--google-client', $clientPath) }
        Write-Host '[MODE: SETTINGS-ONLY] Launching isolated Identity Settings. Mailbox and sending are completely disabled.'
    } else {
        $appArgs += @('--dev-mailbox', '--dev-vault', $vaultPath)
        if ($hasClient) { $appArgs += @('--google-client', $clientPath) }
        if ($EnableGmailSubmit) {
            Write-Host '[MODE: LIVE SUBMISSION] Close any prior QuMail instance. Live Gmail submission is explicitly enabled.'
            $appArgs += @('--dev-gmail-submit')
        } else {
            Write-Host '[MODE: DRY-RUN / INSPECTION] Gmail SMTP submission is DISABLED. You can safely explore the mailbox UI and Settings without any risk of sending mail.'
        }
    }

    $env:QT_QPA_PLATFORM = 'windows'
    $env:QT_PLUGIN_PATH = Join-Path $repoPath '.venv-m1-clean\Lib\site-packages\PyQt6\Qt6\plugins'
    & $pythonPath @appArgs
    if ($LASTEXITCODE -ne 0) { throw "QuMail exited with code $LASTEXITCODE" }
} finally {
    $env:QT_QPA_PLATFORM = $oldQtPlatform
    $env:QT_PLUGIN_PATH = $oldQtPluginPath
    Pop-Location
}
