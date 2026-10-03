# Explicit native research build

This is an opt-in development build, never an application startup/install hook.
It validates the **different research pair** in ADR 002; the original 0.14.1
provider and historical ciphertext compatibility remain blocked/unverified.

Pinned native source, flags and wrapper digest: `packaging/native-research.json`.
Python wheels, CMake 3.31.6 and Ninja 1.11.1.3: development hash lock.
Local Windows build used MSYS2 UCRT64 GCC 15.2.0 at `C:/msys64/ucrt64/bin/gcc.exe`.
That compiler is an external prerequisite, not installed by QuMail. CI uses
Visual Studio 2022 on Windows instead; that lane has not been executed here.

Run from the repository root after installing the development lock:

```powershell
git clone --branch 0.16.0 --depth 1 https://github.com/open-quantum-safe/liboqs.git tmp/liboqs-src
git -C tmp/liboqs-src rev-parse HEAD
# MUST equal 5a1a854b0dc9f2141bdc771c555ee60c37950183; stop on mismatch.
$prefix = Join-Path (Get-Location) 'tmp/oqs-install'
$ninja = Join-Path (Get-Location) '.venv/Scripts/ninja.exe'
.venv/Scripts/cmake.exe -S tmp/liboqs-src -B tmp/liboqs-build -G Ninja "-DCMAKE_MAKE_PROGRAM=$ninja" -DCMAKE_C_COMPILER=C:/msys64/ucrt64/bin/gcc.exe "-DCMAKE_INSTALL_PREFIX=$prefix" -DBUILD_SHARED_LIBS=ON -DOQS_BUILD_ONLY_LIB=ON -DOQS_MINIMAL_BUILD=KEM_ml_kem_768 -DOQS_USE_OPENSSL=OFF -DOQS_DIST_BUILD=ON -DCMAKE_WINDOWS_EXPORT_ALL_SYMBOLS=TRUE
.venv/Scripts/cmake.exe --build tmp/liboqs-build --parallel 4
.venv/Scripts/cmake.exe --install tmp/liboqs-build
$env:OQS_INSTALL_PATH = $prefix
.venv/Scripts/python.exe -m crypto.legacy_provider --research
```

Check each command's exit code. Reuse a verified existing clone/build only when
its source and flags match; do not overwrite another build or user data. With
`.venv-m1-clean`, substitute that environment name in commands.

Observed local native DLL SHA-256:
`bc4199a54ec5e79d62d3d0deb7bebb0310d287266889b63122866fa1e8aa07fd`.
This identifies the local build, not an expectation that MSVC/Linux outputs have
the same hash or that builds are byte-for-byte reproducible. Source, compiler,
flags and generated binary must all accompany eventual artifact provenance.

The CI workflow contains the Linux/MSVC build recipes and verifies the immutable
source commit before CMake. Its native clone is an explicit build step; missing
native libraries during app operations cannot trigger a build/download.
