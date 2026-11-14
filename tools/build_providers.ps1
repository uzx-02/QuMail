<#
.SYNOPSIS
    Builds the QuMail native Rust cryptographic providers in Release mode with Windows security mitigations.

.DESCRIPTION
    Compiles qumail-m3-provider and qumail-m5-provider with MSVC Control Flow Guard,
    copies the release artifacts to bin/, and updates bin/manifest.json with SHA-256 digests.
#>

param(
    [switch]$EnablePeerVerification
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repoRoot

$env:RUSTUP_HOME = Join-Path $repoRoot 'tmp/m2/rustup'
$env:CARGO_HOME = Join-Path $repoRoot 'tmp/m2/cargo'
$env:CARGO_TARGET_DIR = Join-Path $repoRoot 'tmp/m2/target'
$env:LIBCLANG_PATH = Join-Path $repoRoot 'tmp/m2/libclang/libclang-18.1.1.data/platlib/clang/native'
$env:OPENSSL_DIR = Join-Path $repoRoot 'tmp/m2/openssl-install'
$env:OPENSSL_STATIC = '1'
$env:OPENSSL_NO_VENDOR = '1'
$env:RUSTFLAGS = '-C control-flow-guard'

$cargo = Join-Path $env:CARGO_HOME 'bin/cargo.exe'
if (!(Test-Path $cargo)) {
    throw "Cargo executable not found at $cargo"
}

# Verify audited OpenSSL input hash
$libcrypto = Join-Path $env:OPENSSL_DIR 'lib/libcrypto.lib'
if (!(Test-Path $libcrypto)) {
    throw "OpenSSL library not found at $libcrypto"
}
$expectedOpenSslHash = '5CEB47B86BEC9B3B8D6E666E718947391C59F8763BE1347B0E3C2A692E022241'
$actualOpenSslHash = (Get-FileHash $libcrypto -Algorithm SHA256).Hash
if ($actualOpenSslHash -ne $expectedOpenSslHash) {
    throw "Audited OpenSSL 3.5.9 input hash mismatch: expected $expectedOpenSslHash, got $actualOpenSslHash"
}

$featureArgs = if ($EnablePeerVerification) { @('--features', 'peer-verification') } else { @() }

Write-Host "Building qumail-vault-provider (Release, CFG-enabled)..." -ForegroundColor Cyan
& $cargo build --manifest-path (Join-Path $repoRoot 'native/vault_provider/Cargo.toml') --locked --offline --release @featureArgs
if ($LASTEXITCODE -ne 0) { throw "Build of qumail-vault-provider failed with exit code $LASTEXITCODE" }

Write-Host "Building qumail-crypto-provider (Release, CFG-enabled)..." -ForegroundColor Cyan
& $cargo build --manifest-path (Join-Path $repoRoot 'native/crypto_provider/Cargo.toml') --locked --offline --release @featureArgs
if ($LASTEXITCODE -ne 0) { throw "Build of qumail-crypto-provider failed with exit code $LASTEXITCODE" }

# Destination bin directory
$binDir = Join-Path $repoRoot 'bin'
if (!(Test-Path $binDir)) { New-Item -ItemType Directory -Path $binDir | Out-Null }

$vaultSrc = Join-Path $env:CARGO_TARGET_DIR 'release/qumail-vault-provider.exe'
$cryptoSrc = Join-Path $env:CARGO_TARGET_DIR 'release/qumail-crypto-provider.exe'

Copy-Item $vaultSrc (Join-Path $binDir 'qumail-vault-provider.exe') -Force
Copy-Item $cryptoSrc (Join-Path $binDir 'qumail-crypto-provider.exe') -Force

Write-Host "Updating bin/manifest.json with binary digests..." -ForegroundColor Cyan
& python -c @"
import hashlib, json, os, struct
from datetime import datetime, timezone

def inspect_pe(path):
    with open(path, 'rb') as f: data = f.read(4096)
    pe_offset = struct.unpack('<I', data[0x3c:0x40])[0]
    opt_offset = pe_offset + 24
    dll_char_offset = opt_offset + 70
    dll_characteristics = struct.unpack('<H', data[dll_char_offset:dll_char_offset+2])[0]
    return {
        'high_entropy_va_64bit_aslr': bool(dll_characteristics & 0x0020),
        'dynamic_base_aslr': bool(dll_characteristics & 0x0040),
        'nx_compat_dep': bool(dll_characteristics & 0x0100),
        'guard_cf_control_flow_guard': bool(dll_characteristics & 0x4000),
        'terminal_server_aware': bool(dll_characteristics & 0x8000),
        'dll_characteristics_hex': hex(dll_characteristics),
    }

def get_hash(p):
    with open(p, 'rb') as f: return hashlib.sha256(f.read()).hexdigest()

manifest = {
    'schema_version': '1.0',
    'generated_utc': datetime.now(timezone.utc).isoformat(),
    'compiler': 'rustc 1.99.0 / cargo 1.99.0',
    'toolchain': 'nightly-x86_64-pc-windows-msvc',
    'crypto_libraries': {
        'sequoia_openpgp': '2.4.1',
        'openssl': '3.5.9 (29 Sep 2026)',
        'ml_dsa': '0.1.2',
        'rsa': '0.10.0',
        'crypto_bigint': '0.7.11'
    },
    'build_profile': 'release',
    'rustflags': '-C control-flow-guard',
    'providers': {
        'qumail-vault-provider': {
            'binary': 'qumail-vault-provider.exe',
            'version': '0.1.0',
            'purpose': 'Identity, root/subkey lifecycle, certification, Windows DPAPI vault backend',
            'size_bytes': os.path.getsize('bin/qumail-vault-provider.exe'),
            'sha256': get_hash('bin/qumail-vault-provider.exe'),
            'pe_mitigations': inspect_pe('bin/qumail-vault-provider.exe'),
        },
        'qumail-crypto-provider': {
            'binary': 'qumail-crypto-provider.exe',
            'version': '0.1.0',
            'purpose': 'RFC 3156 / RFC 9980 OpenPGP-PQ message encryption, composite signing, decryption, verification',
            'size_bytes': os.path.getsize('bin/qumail-crypto-provider.exe'),
            'sha256': get_hash('bin/qumail-crypto-provider.exe'),
            'pe_mitigations': inspect_pe('bin/qumail-crypto-provider.exe'),
        }
    }
}
with open('bin/manifest.json', 'w', encoding='utf-8') as f:
    json.dump(manifest, f, indent=2)
print('Updated bin/manifest.json successfully.')
"@

Write-Host "Native providers successfully built and staged in bin/:" -ForegroundColor Green
Get-ChildItem $binDir -Filter *.exe | Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize
