# Run from repository root. Build prerequisites/inputs are documented, not fetched here.
param([ValidateSet('normal','reverse')][string]$Order = 'normal', [ValidateSet('Main','Backend','All')][string]$Lane = 'All')
$ErrorActionPreference = 'Stop'
$env:RUSTUP_HOME = Join-Path $PWD 'tmp/m2/rustup'
$env:CARGO_HOME = Join-Path $PWD 'tmp/m2/cargo'
$env:CARGO_TARGET_DIR = Join-Path $PWD 'tmp/m2/target'
$env:LIBCLANG_PATH = Join-Path $PWD 'tmp/m2/libclang/libclang-18.1.1.data/platlib/clang/native'
$env:OPENSSL_DIR = Join-Path $PWD 'tmp/m2/openssl-install'
$env:OPENSSL_STATIC = '1'
$env:OPENSSL_NO_VENDOR = '1'
$registry = Get-ChildItem "$env:CARGO_HOME/registry/src" -Directory
$vectorRoot = @($registry | ForEach-Object { Join-Path $_.FullName 'pgp-0.21.0/tests/pqc' } | Where-Object { Test-Path $_ })
if ($vectorRoot.Count -ne 1) { throw 'Exactly one pinned rPGP source with public RFC vectors is required' }
$env:M2_PUBLIC_VECTORS = $vectorRoot[0]
$vectors = @{
    'v6-mldsa-65-sample-pk.asc' = '4880DEAD81E043038DF20E961AB74A7C61F14245371D6A229C1888BE79813764'
    'v6-mldsa-65-sample-signature.asc' = 'AF8689111EE427D9F78E5BCA17D1D2227AE8787071ADF8B1DED66E36A6058C0C'
    'v6-mldsa-65-sample-sk.asc' = '515C09226777ED771AC0171576911D395D101DD1D9BE094BBAEFA4E5E1E03F19'
    'v6-mldsa-65-sample-message.asc' = 'DC75363621276AD6F50F16FAEA3F4D33DA8400D4253C5BDD8DACAB5D4354A976'
}
foreach ($name in $vectors.Keys) {
    if ((Get-FileHash (Join-Path $env:M2_PUBLIC_VECTORS $name) -Algorithm SHA256).Hash -ne $vectors[$name]) {
        throw 'Public RFC vector input hash mismatch'
    }
}
if (!(Select-String -Path "$env:OPENSSL_DIR/include/openssl/opensslv.h" -SimpleMatch 'OPENSSL_VERSION_STR "3.5.9"' -Quiet)) {
    throw 'The explicit OpenSSL 3.5.9 input is required'
}
function Invoke-Proof([string]$Manifest, [string]$Filter, [int]$Count) {
    $base = @('test','--manifest-path',$Manifest,'--locked','--offline','--lib')
    $listing = & ./tmp/m2/cargo/bin/cargo.exe @base $Filter -- --list
    if ($LASTEXITCODE -ne 0) { throw 'Test discovery failed' }
    $names = @($listing | Where-Object { $_ -match '^.+: test$' } | ForEach-Object { $_ -replace ': test$','' } | Sort-Object)
    if ($names.Count -ne $Count) { throw 'Review expected corpus after changing tests' }
    $executed = @()
    $runs = if ($Order -eq 'normal') { @($Filter) } else { @($names | Sort-Object -Descending) }
    foreach ($name in $runs) {
        $argsForTest = @('--test-threads=1')
        if ($Order -eq 'reverse') { $argsForTest += '--exact' }
        if ($Filter -eq 'backend_probe') { $argsForTest += '--nocapture' }
        $output = @(& ./tmp/m2/cargo/bin/cargo.exe @base $name -- @argsForTest 2>&1 | ForEach-Object { "$_" })
        $exitCode = $LASTEXITCODE
        $output | Write-Output
        if ($exitCode -ne 0) { throw 'M2 test run failed' }
        if (!($output -match 'test result: ok\..* 0 failed; 0 ignored;')) { throw 'Missing successful zero-skip result' }
        $executed += @($output | Where-Object { $_ -match '^test (.+) \.\.\. ok$' } | ForEach-Object { $_ -replace '^test (.+) \.\.\. ok$','$1' })
    }
    if ($executed.Count -ne $Count -or @(Compare-Object $names @($executed | Sort-Object)).Count -ne 0) { throw 'Executed test identities differ from discovery' }
    Write-Output "IDENTITY CHECK: $Order $Manifest : $Count distinct tests passed; no missing, extra or ignored tests."
    $executed | ForEach-Object { Write-Output "EXECUTED: $_" }
}
if ($Lane -in @('Main','All')) { Invoke-Proof 'experiments/m2/Cargo.toml' '' 12 }
if ($Lane -in @('Backend','All')) { Invoke-Proof 'experiments/m2/backend-probe/Cargo.toml' 'backend_probe' 5 }
