# Isolated diagnostic source copy, never edits the registry cache or native build.
$ErrorActionPreference = 'Stop'
$cache = @(Get-ChildItem tmp/m2/cargo/registry/cache -Recurse -Filter sequoia-openpgp-2.4.1.crate)
if ($cache.Count -ne 1 -or (Get-FileHash $cache[0].FullName).Hash -ne '0FBC8F9818A6FAD141D85993777BA298EE52C80A09BD23D45DDA461A6B7C83CB') { throw 'Sequoia archive hash mismatch' }
$unpack = Join-Path $PWD 'tmp/m2/probe-source'
New-Item -ItemType Directory -Force $unpack | Out-Null
& tar.exe -xf $cache[0].FullName -C $unpack
if ($LASTEXITCODE -ne 0) { throw 'Pinned source extraction failed' }
$source = Join-Path $unpack 'sequoia-openpgp-2.4.1'
$dest = Join-Path $PWD 'tmp/m2/probe-sequoia'
New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $dest -Recurse -Force
$manifest = Get-Content (Join-Path $dest 'Cargo.toml') -Raw
$manifest = $manifest.Replace('[features]', "[features]`nqumail-m2-fault-probe = []")
Set-Content (Join-Path $dest 'Cargo.toml') $manifest -Encoding utf8
$accessor = @'

/// QuMail isolated M2 diagnostic accessor. No algorithm/RNG/verification changes.
#[cfg(feature = "qumail-m2-fault-probe")]
pub fn qumail_m2_probe_context() -> *mut std::ffi::c_void {
    crypto::backend::context().ptr().cast()
}
'@
Add-Content (Join-Path $dest 'src/lib.rs') $accessor -Encoding utf8
Write-Output 'Prepared isolated Sequoia context accessor; ordinary crate cache unchanged.'
