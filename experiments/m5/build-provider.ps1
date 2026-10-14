$ErrorActionPreference = 'Stop'
$env:RUSTUP_HOME = Join-Path $PWD 'tmp/m2/rustup'
$env:CARGO_HOME = Join-Path $PWD 'tmp/m2/cargo'
$env:CARGO_TARGET_DIR = Join-Path $PWD 'tmp/m2/target'
$env:LIBCLANG_PATH = Join-Path $PWD 'tmp/m2/libclang/libclang-18.1.1.data/platlib/clang/native'
$env:OPENSSL_DIR = Join-Path $PWD 'tmp/m2/openssl-install'
$env:OPENSSL_STATIC = '1'
$env:OPENSSL_NO_VENDOR = '1'
if ((Get-FileHash "$env:OPENSSL_DIR/lib/libcrypto.lib" -Algorithm SHA256).Hash -ne '5CEB47B86BEC9B3B8D6E666E718947391C59F8763BE1347B0E3C2A692E022241') {
    throw 'M2 audited native input changed'
}
& ./tmp/m2/cargo/bin/cargo.exe build --manifest-path experiments/m5/provider/Cargo.toml --locked --offline
if ($LASTEXITCODE -ne 0) { throw 'M5 build failed' }
& ./tmp/m2/cargo/bin/cargo.exe test --manifest-path experiments/m5/provider/Cargo.toml --locked --offline -- --test-threads=1
if ($LASTEXITCODE -ne 0) { throw 'M5 provider tests failed' }
