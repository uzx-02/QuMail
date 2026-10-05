# Isolated M2 provider proof

Test-only Rust crate (`#![cfg(test)]`, `publish = false`). No production QuMail
imports. Never use this harness to process user keys/mail. Generated plaintext
and secret keys remain in memory; no debug dump of either is permitted.

See `docs/operations/m2-validation.md` for results/limitations and ADR 003 for the
proposed contract. A passing harness is not M2 sign-off or production approval.

## Inputs and reproduction

Run from repository root. `inputs.json` records exact release/source/archive
hashes, native flags and build prerequisites. Cargo.lock records registry
checksums for all Rust dependencies; use `--locked` and never silently update a
provider to satisfy dependency resolution. `kem = 0.3.0-pre.0` matches rPGP's
published dependency lock; final 0.3.0 is not compatible with its ml-kem version.

All downloads/builds belong under ignored `tmp/m2`, not the source tree or system
installation. This proof was built on Windows only. It does not supply a Linux
binary, executable, installer or native library in Git.

Preparation performed for this environment:

1. Install exact Rust 1.99.0 for x86_64-pc-windows-msvc with isolated
   `RUSTUP_HOME=<REPO>/tmp/m2/rustup`, `CARGO_HOME=<REPO>/tmp/m2/cargo`; no PATH
   modification. Rustup downloaded the official toolchain with its normal checks.
2. Fetch OpenSSL 3.5.9 and compare the archive SHA-256 in inputs.json and its
   official release .sha256. Extract to `tmp/m2/openssl-3.5.9`. Signature-file
   verification remains unperformed. Extract pinned portable Perl under
   `tmp/m2/perl`; extract the libclang wheel under `tmp/m2/libclang`.
3. Use an installed Visual Studio C++ x64 build toolchain. The build script
   discovers it with vswhere; record the selected compiler version because the
   discovery itself is not an immutable compiler lock. Run `./experiments/m2/build-native.ps1`.
4. With those Cargo/Rustup paths set, run
   `./tmp/m2/cargo/bin/cargo.exe fetch --manifest-path experiments/m2/Cargo.toml --locked`.
   Subsequent tests use `--locked --offline`.
5. Run `./experiments/m2/prepare-probe.ps1` to extract the verified Sequoia
   archive under tmp/m2 and add the diagnostic-only context accessor. The
   separate backend-probe manifest/lock records this local copy; neither the
   registry source nor native implementation is edited.
6. Run `./experiments/m2/run.ps1`, then `./experiments/m2/run.ps1 -Order reverse`.
   Native inputs and four published vector files are checked before executing.
   Default runs both lanes: 12 ordinary tests and five isolated backend probes.
   `-Lane Main` or `-Lane Backend` selects focused checks. Each order verifies
   actual executed identities against discovered names and rejects ignored tests.
7. Run `./.venv-m1-clean/Scripts/python.exe experiments/m2/audit-inputs.py` after
   retaining stdout/stderr as tmp/m2/20261005-normal.log and ...-reverse.log.
   The audit asserts exact diagnostic changes, identical transitive versions,
   unchanged native hash and the same 17 test identities; emits input hashes.

`run.ps1` uses registry-cached rPGP source for the RFC vectors, not an untracked
hand-edited fixture copy. `M2_PUBLIC_VECTORS` is set to its tests/pqc directory;
it contains public RFC test material, including a **publicly published test
secret**, not a user credential. Those upstream source files are not added to
this repository. No test secret or plaintext is emitted into retained logs.
If directly invoking Cargo, supply the same environment and validated vector
directory. Never reuse an arbitrary system OpenSSL: runtime version is asserted.

## Profile and evidence boundary

Experimental profile: `M2-EXPERIMENT-RFC9980-AES256-GCM`; v6 keys/PKESK/signatures,
ML-KEM-768+X25519, ML-DSA-65+Ed25519, SHA-512 for generated messages,
AES-256/GCM/SEIPDv2/4 KiB chunks, uncompressed. rPGP-generated certificates need
explicit v6, certify/sign flags and `feature_seipd_v2(true)`. Providers own all
cryptographic encodings, randomness, combiners and nonce rules.

The common Sequoia outer-packet precheck and common mailparse/armor fixture are
not independent parser implementations. Both OpenPGP providers independently
decrypt/verify. Both return helpers buffer plaintext until final integrity and
signature verification; do not refactor them into streaming UI output.

Tests retain synthetic exchanges, multiple recipients, each signature component,
published vectors and headers. New contract tests prove structured fail-closed
policy and no returned unverified staging; native probes exercise selected
Sequoia/OpenSSL failures in fresh child processes via its real private context.
Empty TEST-RAND fails random-source nonce acquisition; nonexistent provider
properties cause errors/panics. These are not mocked adapter errors or direct
Windows entropy-source outages. The default provider has no self-test callback;
its return of 1 cannot establish FIPS/KAT assurance. Detailed trace and controls
are in docs/operations/m2-external-review.md.

The standalone diagnostic crate imports the experiment as tests but executes
only its five native probes; the 12 inherited tests are intentionally filtered
there and execute against unmodified Sequoia in the main lane. Its feature and
context accessor are never used by production. Expected native panics appear
in captured diagnostic output and are asserted to become structured failures;
none of those logs contains generated keys or plaintext. No assertion is weakened.

No identity enrollment, OS-keystore custody, production MIME/SMTP, Linux, Python
IPC/process limits or constant-time qualification. Abort/OOM/segfault cannot be
contained by Rust unwind catching; the future helper must fail closed on exit.

Do not commit `tmp/m2`, environments, private logs, generated native binaries,
test-generated messages/keys or the reference PDF. Reviewable results are redacted
text summaries/output under `docs/operations/evidence/m2` and input/source hashes.
