# Test suite for tools/start_google_acceptance.ps1
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$launcher = Join-Path $repoPath 'tools\start_google_acceptance.ps1'

Write-Host "Running Launcher Preflight Test Suite..." -ForegroundColor Cyan

# Test 1: Syntax parsing validation
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput((Get-Content $launcher -Raw), [ref]$tokens, [ref]$errors)
if ($errors.Count -ne 0) {
    throw "Syntax error in $launcher : $($errors | Out-String)"
}
Write-Host "PASS: Test 1 - Launcher script syntax is valid PowerShell."

# Test 2: Missing Vault parameter (mandatory in non-interactive mode)
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'SilentlyContinue'
$errFile = Join-Path $repoPath 'tmp\test_mandatory_param_err.txt'
$proc = Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile -NonInteractive -File `"$launcher`" -CheckOnly" -NoNewWindow -Wait -PassThru -RedirectStandardError $errFile
$code = $proc.ExitCode
$errContent = if (Test-Path $errFile) { Get-Content $errFile -Raw } else { "" }
Remove-Item -Force -Path $errFile -ErrorAction SilentlyContinue
$ErrorActionPreference = $prevEAP
if ($code -eq 0 -or $errContent -notmatch "Vault") {
    throw "FAIL: Test 2 - Launcher did not mandate -Vault parameter in non-interactive mode. Code: $code, Err: $errContent"
}
Write-Host "PASS: Test 2 - Missing -Vault parameter correctly rejected."

# Test 3: Directory specified as Vault path
$tempDir = Join-Path $repoPath 'tmp\test_launcher_dir'
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
try {
    $caught = $false
    try {
        & $launcher -Vault $tempDir -CheckOnly 2>$null
    } catch {
        if ($_.Exception.Message -match "names an existing directory") { $caught = $true }
    }
    if (-not $caught) { throw "FAIL: Test 3 - Directory as vault was not rejected." }
    Write-Host "PASS: Test 3 - Vault path naming a directory correctly rejected."
} finally {
    Remove-Item -Force -Recurse -Path $tempDir -ErrorAction SilentlyContinue
}

# Test 4: Non-existent vault without -AllowNewVault
$nonExistentVault = Join-Path $repoPath 'tmp\test_nonexistent_vault.sqlite'
$caught = $false
try {
    & $launcher -Vault $nonExistentVault -CheckOnly 2>$null
} catch {
    if ($_.Exception.Message -match "Existing vault is missing or inaccessible") { $caught = $true }
}
if (-not $caught) { throw "FAIL: Test 4 - Missing vault without -AllowNewVault was not rejected." }
if (Test-Path -LiteralPath $nonExistentVault) { throw "FAIL: Test 4 - Database file was unexpectedly created." }
Write-Host "PASS: Test 4 - Missing vault without -AllowNewVault rejected; no file created."

# Test 5: Missing parent directory without -AllowNewVault
$nestedMissingVault = Join-Path $repoPath 'tmp\missing_parent_dir\vault.sqlite'
$caught = $false
try {
    & $launcher -Vault $nestedMissingVault -CheckOnly 2>$null
} catch {
    if ($_.Exception.Message -match "Vault parent directory does not exist") { $caught = $true }
}
if (-not $caught) { throw "FAIL: Test 5 - Missing parent directory without -AllowNewVault was not rejected." }
Write-Host "PASS: Test 5 - Missing parent directory without -AllowNewVault rejected."

# Test 6: Mutually exclusive -DryRun and -EnableGmailSubmit
$caught = $false
try {
    & $launcher -Vault $nonExistentVault -AllowNewVault -DryRun -EnableGmailSubmit -CheckOnly 2>$null
} catch {
    if ($_.Exception.Message -match "mutually exclusive") { $caught = $true }
}
if (-not $caught) { throw "FAIL: Test 6 - -DryRun and -EnableGmailSubmit mutual exclusion was not enforced." }
Write-Host "PASS: Test 6 - Mutually exclusive -DryRun and -EnableGmailSubmit rejected."

# Test 7: Mutually exclusive -SettingsOnly and -EnableGmailSubmit
$caught = $false
try {
    & $launcher -Vault $nonExistentVault -AllowNewVault -SettingsOnly -EnableGmailSubmit -CheckOnly 2>$null
} catch {
    if ($_.Exception.Message -match "mutually exclusive") { $caught = $true }
}
if (-not $caught) { throw "FAIL: Test 7 - -SettingsOnly and -EnableGmailSubmit mutual exclusion was not enforced." }
Write-Host "PASS: Test 7 - Mutually exclusive -SettingsOnly and -EnableGmailSubmit rejected."

# Test 8: -EnableGmailSubmit without GoogleClient
$caught = $false
try {
    & $launcher -Vault $nonExistentVault -AllowNewVault -EnableGmailSubmit -CheckOnly 2>$null
} catch {
    if ($_.Exception.Message -match "-EnableGmailSubmit requires an explicitly configured Google client JSON") { $caught = $true }
}
if (-not $caught) { throw "FAIL: Test 8 - -EnableGmailSubmit without -GoogleClient was not rejected." }
Write-Host "PASS: Test 8 - -EnableGmailSubmit without -GoogleClient rejected."

# Test 9: Positive -CheckOnly with -AllowNewVault and valid Desktop Client JSON
$tempClient = Join-Path $repoPath 'tmp\test_desktop_client.json'
$dummyClientJson = @{
    installed = @{
        client_id = "test-client-id.apps.googleusercontent.com"
        client_secret = "test-secret"
        auth_uri = "https://accounts.google.com/o/oauth2/auth"
        token_uri = "https://oauth2.googleapis.com/token"
        redirect_uris = @("http://127.0.0.1", "http://localhost")
    }
} | ConvertTo-Json
Set-Content -LiteralPath $tempClient -Value $dummyClientJson -Encoding utf8

$testNewVaultDir = Join-Path $repoPath 'tmp\test_new_vault_dir'
$testNewVaultFile = Join-Path $testNewVaultDir 'acceptance.sqlite'
try {
    $out = & $launcher -Vault $testNewVaultFile -GoogleClient $tempClient -AllowNewVault -CheckOnly
    if (-not (Test-Path -LiteralPath $testNewVaultDir -PathType Container)) {
        throw "FAIL: Test 9 - Parent directory was not created."
    }
    if (Test-Path -LiteralPath $testNewVaultFile) {
        throw "FAIL: Test 9 - Database file was unexpectedly created in -CheckOnly mode."
    }
    if ($out -notmatch "Explicit NEW-vault mode") {
        throw "FAIL: Test 9 - Did not report Explicit NEW-vault mode."
    }
    if ($out -notmatch "Desktop client configuration: valid") {
        throw "FAIL: Test 9 - Did not validate Desktop client JSON."
    }
    Write-Host "PASS: Test 9 - Positive -CheckOnly with -AllowNewVault created parent dir but NO database file."
} finally {
    Remove-Item -Force -Recurse -Path $testNewVaultDir -ErrorAction SilentlyContinue
    Remove-Item -Force -Path $tempClient -ErrorAction SilentlyContinue
}

# Test 10: Positive -CheckOnly in Settings-only offline mode (no Google client)
$testOfflineVaultDir = Join-Path $repoPath 'tmp\test_offline_vault_dir'
$testOfflineVaultFile = Join-Path $testOfflineVaultDir 'acceptance.sqlite'
try {
    $out = & $launcher -Vault $testOfflineVaultFile -AllowNewVault -SettingsOnly -CheckOnly
    if ($out -notmatch "Desktop client configuration: omitted \(offline / identity-only mode\)") {
        throw "FAIL: Test 10 - Did not report client omitted in offline mode."
    }
    if (Test-Path -LiteralPath $testOfflineVaultFile) {
        throw "FAIL: Test 10 - Database file was unexpectedly created."
    }
    Write-Host "PASS: Test 10 - Positive -CheckOnly in Settings-only offline mode succeeded."
} finally {
    Remove-Item -Force -Recurse -Path $testOfflineVaultDir -ErrorAction SilentlyContinue
}

# Test 11: Positive -CheckOnly on an existing database file
$testExistingVault = Join-Path $repoPath 'tmp\test_existing_vault.sqlite'
Set-Content -LiteralPath $testExistingVault -Value "dummy database header" -Encoding utf8
try {
    $out = & $launcher -Vault $testExistingVault -CheckOnly
    if ($out -notmatch "Existing vault found. In Settings choose Unlock") {
        throw "FAIL: Test 11 - Did not recognize existing vault."
    }
    Write-Host "PASS: Test 11 - Positive -CheckOnly on existing vault correctly recognized."
} finally {
    Remove-Item -Force -Path $testExistingVault -ErrorAction SilentlyContinue
}

Write-Host "`nALL 11 LAUNCHER PREFLIGHT TESTS PASSED SUCCESSFULLY!" -ForegroundColor Green
