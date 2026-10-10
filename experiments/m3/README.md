# Isolated M3 identity/vault development

Owner exception: [ADR 004](../../docs/adrs/004-m3-development-exception.md).
M2 is still pending independent expert review. The disabled-by-default
`--dev-identity` Settings path now uses this boundary. The default desktop and
production sender do not import it. No real mail, user keys or credentials are used.

Use the M1 locked Python environment and M2 pinned Windows native inputs. See
[M2 reproduction](../m2/README.md) for exact Rust/native prerequisites. M3's
ordinary lock adds direct serde_json 1.0.151 already present in M2 transitives.
No diagnostic Sequoia patch is used in this helper. The helper's certificate
shape differs from M2 and has separate independent-peer tests.

From repository root in PowerShell:

```powershell
./experiments/m3/build-provider.ps1
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests --reverse
$env:OQS_INSTALL_PATH = Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q
```

The native script checks M2's audited libcrypto hash and builds/tests with locked
offline Cargo inputs. Binaries/cache remain under ignored tmp/m2/target. The
provider checks the expected native runtime on each IPC request. No installer or
native binary is tracked. The Python suite requires a real Windows interactive
user credential set; restricted sandbox/network logon sessions may deny access.
Do not skip or replace the real-store tests to call this criterion passed.
Run in a normal local terminal when authorized. Temporary directories use unique
names under ignored tmp; generated key material is held in memory or authenticated
encrypted SQLite/recovery records. Every created OS entry has a random
`QuMail-M3-Development/<opaque UUID>` target and a cleanup assertion. Failed test
logs may be private: inspect/redact before retaining outputs. No generic credential
enumeration is used. Cleanup uses only the exact disposable entry created.

The reviewer draft `docs/operations/m2-reviewer-request.md` is separate and must
remain uncommitted and unchanged. Do not stage reference PDFs, environments,
generated vault databases, recovery packages/secrets, binaries or private logs.

## Interface and limits

- `types.py`: distinct user/account/device/SAE/email/root/opaque-handle concepts.
  All external record IDs are validated UUID hex strings, never paths.
- `identity.py`: google-auth signature verification plus binding checks; synthetic
  issuer tests do not establish real OAuth acceptance. The development Google
  external-browser/PKCE implementation is in transport/development_google.py.
  Yahoo explicitly fails. Authorized aliases are not invented.
- `secure_store.py`: direct Windows Cred APIs only. No cache/file fallback.
- `vault.py`: authenticated account aggregates and transactional lifecycle/trust.
  AccountContext is a trusted in-process authorization input, not an IPC login or
  an unforgeable capability against hostile Python code. OS master key fetched
  for each operation. Internal underscored methods are not production endpoints.
- `provider.py`: one request per subprocess, bounded anonymous pipes, 30-second
  timeout, no secret argv or forwarded stderr; generic errors, no fallback.
  Provider material necessarily enters Python memory for wrapping. No perfect
  zeroization, OS job-object memory ceiling or crash-dump exclusion is claimed.
- `seal_for_test`/`open_for_test`: isolated cryptographic validation, not mail.
  Sealing requires locally verified contact trust. Opening verifies the supplied
  signer cryptographically but does not establish a production identity/display
  result; those supplied test public keys are not a replacement for M5 identity
  and message provenance checks. Provider buffers until integrity/signature EOF.

One active device per account; 1 MiB provider message/key input, 8 MiB JSON pipe/
encrypted account payload; 32 KiB OAuth record. SQLite FULL/BEGIN IMMEDIATE protects
atomicity, not full-database rollback or a hostile same-user path replacement.
Initial existing symlinks/reparse points are rejected; path-race/ACL qualification
and account-count/aggregate database budgets remain later hardening. Device/root
keys remain a provider certificate bundle in one owned opaque record; public
exports go through provider public serialization. Signing/encryption fingerprints
and purposes remain distinct metadata.

Test evidence and limitations: [M3 validation](../../docs/operations/m3-validation.md).
Recovery procedure: [M3 recovery](../../docs/operations/m3-recovery.md).

## Current development application integration

See [Settings and Google setup](../../docs/operations/m3-development-settings.md).
Account session/service interfaces are in core/account_session.py and
core/identity_service.py; the separate Settings view is ui/identity_settings.py.
No send service is exposed. Backup and explicitly confirmed transfer are separate;
restore defaults to archive-only and unchanged-root activation is an explicit
prior-device-retirement acknowledgment. Root replacement requires re-verification.
The original 32-case snapshot is historical at ef4b308; use the current integration
audit/evidence for changed sources. Do not attribute its old hashes to this tree.
