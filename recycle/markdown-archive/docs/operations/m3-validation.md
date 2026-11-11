# M3 bounded development validation

## Current bounded integration decision — 2026-10-10

**Bounded M3 development integration engineering is complete and locally tested.**
M3 remains **PARTIAL for milestone acceptance** because real provider acceptance
is unavailable and independent cryptographic/enrollment/recovery review is deferred
until before production enablement/security release. ADR 004 authorizes continued
development in the meantime; no independent approval is claimed or required to
finish this bounded engineering work. Sending remains disabled; M4 has not begun.

At handoff, actual HEAD was M2 checkpoint
`1fc4e55f09e173cec7634d0b2dc776097b552063`, with 27 uncommitted M3 files. Their
retained input hashes matched. They were explicitly staged and locally preserved
as **`ef4b3086d8eac16fd65a3a34f107e75ad4966ec4`** before integration. This corrects
any assumption that a prior M3 checkpoint already existed. Branch remains
`codex/m3-identity-vault`. M1/M2 branches, evidence, canonical specification,
legacy data, reference PDF and uncommitted M2 reviewer request are preserved.
The final integration checkpoint is a descendant of ef4b308; its actual SHA is
reported with the local Git commit receipt. Tests below belong to the exact
[working-tree input manifest](evidence/m3/integration/input-hashes.json), not to
unchanged parent HEAD or the earlier 32-case snapshot.

### Acceptance separation

| Remaining M3 criterion | Executable evidence / disposition | Status |
|---|---|---|
| Explicit development application boundary; §54 M3, QM-SEC-004 | Opt-in `--dev-identity`, separate Settings/service/session; default and mutual-exclusion tests; no send API or legacy account installation | Engineering satisfied; no production enablement |
| Coherent account context and same-provider isolation; QM-ID-001/002, T06 | Immutable snapshot installed before notifications; selection/lock/cancel generation checks; two-account and stale-success/error scenarios; no tokens in views | Engineering satisfied |
| Settings creation/selection, lock/unlock, trust, recovery; §54 M3 | Real offscreen Qt controls; account selection and late worker test; unverified/verified/changed/revoked display; expired UI fixture plus actual native expired-certificate status test | Engineering satisfied on Windows; no broad accessibility/platform qualification claimed |
| Google authorization and refresh implementation; QM-ID-002, T06 | Maintained S256 PKCE flow; actual loopback listener; strict path/Host/port/state/code cases; maintained synthetic signature tests; nonce/issuer/audience/subject/expiry/authority rejection; refreshed userinfo identity binding | Engineering satisfied with controlled fixtures; **real Google acceptance pending**, Yahoo unavailable |
| Atomic enrollment / account-scoped credential persistence; QM-KEY-001/002, T08 | Credentials included in enrollment/restore transaction; real Windows credential access; simulated commit denial and unavailable store leave no partial account; stale results cannot persist | Engineering satisfied |
| Backup versus transfer; QM-KEY-004/005, T08 | Ordinary export retains lifecycle; explicit transfer persists before suspension; fsync and SQLite commit failure keep source active; post-commit display failure still returns recovery secret; actual Settings controls tested | Engineering satisfied |
| Safe restore, unchanged/replaced roots; §§39–40, T04/T08 | Historical decrypt retained; archive-only default; unchanged-root explicit retirement acknowledgment retains fingerprint; replacement changes root and contact verification required | Engineering satisfied for one-device local policy; cannot detect/erase offline clones |
| Existing provider/interop and lifecycle proof | Three native tests include prior fresh/rotated separate-signing-subkey exchanges plus real active/revoked/expired statuses; wrong-key and malformed cases retained | Satisfied for measured provisional Windows provider |
| Live-provider acceptance | No explicitly provisioned Google client/test account was supplied; no existing caches/configurations searched; no human browser interaction attempted | Unavailable evidence; precise setup/acceptance steps supplied |
| Independent M2 crypto and M3 enrollment/recovery review | ADR 004 exception retained; no AI/test result labeled expert approval | Deferred before production enablement/security release; **not an engineering stop** |

[Usable workflows and exact Google setup/acceptance](m3-development-settings.md),
[backup/transfer/recovery policy](m3-recovery.md) and amended ADR 004 are current.
Only an explicitly selected Google Desktop-client JSON is read. Authorization
requests identity scopes, not Gmail SMTP/IMAP access; no transport support is claimed.

### Exact integrated execution and attribution

Same Windows/Rust/Python/provider/lock inputs as the preserved baseline below.
Third-party Cargo versions/source/checksums and native libcrypto hash still match
M2. No new dependency, provider substitution or native library rebuild occurred.
The helper is rebuilt from the changed M3 source; its binary hash is recorded but
its generated binary is excluded from Git. Python storage crypto remains a separate
backend from Sequoia/OpenSSL. Original M2 native warnings/assurance limits remain.

```powershell
./experiments/m3/build-provider.ps1
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests --reverse
$env:OQS_INSTALL_PATH = Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.audit_integration
```

| Retained execution | Exact final result |
|---|---|
| [Native](evidence/m3/integration/native.txt) | 3 passed, 0 failed/ignored/measured/filtered, 1.16 s |
| [Normal](evidence/m3/integration/normal.txt) | 54 passed, 11.23 s; zero skips/warnings; discovered and executed identities match |
| [Reverse](evidence/m3/integration/reverse.txt) | Same 54 distinct tests in reverse, 54 passed, 11.42 s; zero skips/warnings |
| [Legacy](evidence/m3/integration/legacy.txt) | 37 passed, 5 existing datetime warnings, 1.14 s; zero skips |
| [Audit](evidence/m3/integration/input-hashes.json) | M2 15-input preservation; ordinary Cargo equality; same native libcrypto; source/script/lock/test/helper hashes; same distinct normal/reverse identities |

Credential Manager checks used the normal Windows logon session outside the
restricted sandbox with random disposable M3 entries and cleanup. OAuth HTTP
callbacks were real **loopback-only** fixtures; issuer/token/userinfo responses
were synthetic or mocked, labeled in tests. Signature verification also retains
its real maintained-library synthetic signed-token fixture. No live Google/Yahoo
claim follows. Native output retains path-canonicalization/hard-link-cache warnings;
no warnings were suppressed. Only local filesystem paths were redacted in retained
text. Final app/library/test source was unchanged after execution; subsequent
changes were documentation and the separately executed read-only audit tools.

The first 49-case integration run passed with a warning because the mocked HTTP
session lacked close(); fixture cleanup was corrected. Expanded runs added real
transfer/commit failure boundaries and a post-commit display-failure correction.
Explicit Desktop-client URI allowlist compatibility was tested before the final
54-case run. Prior 32-case evidence is preserved, not relabeled as these results.
The old audit_snapshot command now rejects changed inputs instead of attributing
historical test output to new code.

No M4, mail sending, migration, push, merge, deployment or release. Next bounded
step: provision a Google Desktop test client and two owner-controlled test accounts,
then have the user complete the documented browser/refresh/cancellation acceptance.
Deferred expert review remains required before production/security release; it
need not halt additional explicitly authorized development.

## Preserved isolated baseline record (ef4b308; superseded integration state)

The following is historical evidence and assessment from 2026-10-05–06. Its
statements about missing Settings/browser integration and transfer-only backup
have been superseded by the current section and ADR 004 amendment above.


Updated 2026-10-06 (Asia/Calcutta); work began 2026-10-05.
**M3 PARTIAL: isolated Windows engineering implemented; live authorization,
application integration and independent review remain pending.**
M2 remains PARTIAL: engineering proof complete; external review pending.
[ADR 004](../adrs/004-m3-development-exception.md) records the owner's explicit
development-order exception. The canonical specification is unchanged.

## Provenance and preservation

Local branch `codex/m3-identity-vault` starts at preserved M2 checkpoint
`1fc4e55f09e173cec7634d0b2dc776097b552063`. All results below were obtained on the
M3 working-tree snapshot, not the unchanged parent HEAD. The subsequent local
checkpoint preserves the [exact inputs](evidence/m3/input-hashes.json). Its SHA
is reported in the checkpoint receipt after committing; no execution claim is
attributed merely to a commit number.

All 15 M2 input hashes still match the retained M2 audit. The ordinary M2 and M3
Cargo locks have identical third-party versions, sources and checksums; only the
local package/dependency edges differ. M3 directly names already-locked serde_json
1.0.151. M1 files, evidence and branch; M2 experiment/evidence/ADR; canonical
Markdown; reference PDF and legacy data are preserved. The M2 reviewer draft
remains separately uncommitted, SHA-256
`9da71cac40f75a9c4fcf8bfd5f84dcf5364c95c5264e1d307309b5451049df47`.
No production entry point imports M3, and no mail, enrollment of real accounts,
publication, push, merge, migration, deployment or release occurred.

## Actual M3 acceptance

| Criterion / reference | Evidence | Assessment / remaining action |
|---|---|---|
| M2 dependency and independent review, §54 | Checkpoint/input comparison; ADR 004 owner exception | **Partial:** ordering exception permits development only; independent M2 cryptographer/protocol review still required before production crypto/security release |
| Distinct account/device/root/addresses/key handles; QM-ID-001; §§39–40 | Executed typed-ID, two same-provider accounts, wrong-context/device/handle tests | **Satisfied within isolated boundary.** Trusted in-process account contexts are not network authentication |
| Provider issuer/subject and authorized addresses; QM-ID-002; T06 | Maintained google-auth validates synthetic signed token; state/nonce/issuer/audience/subject/expiry/hosted-domain rejection, encrypted per-account OAuth records | **Partial:** no real Google/Yahoo authorization; browser PKCE/callback/session/Settings adapter pending. Yahoo fails closed; aliases without provider evidence refused |
| Recipient-owned certificate and first contact; QM-ID-003, QM-PQC-002; T04 | Local provider generation, public-only export, certified address check, independent fingerprint confirmation, substitution/changed-root/old-subkey rollback blocks | **Satisfied within isolated boundary.** The confirmation input models an explicit human ceremony, not proof that a human performed one in synthetic tests |
| Root/device lifecycle; QM-ID-004/005, QM-KEY-002/003; §54 | Provider-certified signing/encryption subkeys, foreign unbound subkey rejection, expiry, additive rotation, signed revocation, local lifecycle transaction tests | **Satisfied within one-device development scope.** No directory freshness service/global device erasure; Settings UX and independent enrollment/reset/backup review pending |
| Multi-device or explicit limitation; §§39,54 | One device per local account, duplicate binding rejection; recovery archive-only and fresh-root activation | **Satisfied by explicit one-device limitation.** Simultaneous devices and selection/interop deferred. Copies of an offline vault cannot be remotely disabled |
| Exact changed certificate shape works with independent peer; §§39/41 and M2 compatibility gate | Two Rust tests: fresh separate-signing-subkey certificate exchanged both ways with rPGP; rotated certificates sign/verify/decrypt across peers | **Satisfied on measured Windows build.** Common Sequoia policy selects active fingerprints for the peer; this is independent crypto processing, not independent selection policy or MUA evidence |
| OS-protected master secret, no file fallback; QM-KEY-001, I17; T08 | Actual CredWriteW/CredReadW/CredDeleteW operations, readback and deletion checks; absent credential blocks access/enrollment; mocked denial separately labeled | **Satisfied on this Windows logon session.** Sandbox denied storage and was not counted as a pass; no Linux or network-logon support claimed |
| No private key in directory/backend; QM-SEC-004, QM-KEY-006; §54 | No directory/backend calls; public export reserializes through provider and rejects secret import; output/code inspection | **Satisfied for implemented boundary.** Private keys traverse anonymous helper pipes into Python for wrapping; hostile in-process code/crash dumps are not contained |
| Transactional authenticated account/device records; QM-KEY-002/006; T08 | Real SQLite concurrent writes, abrupt process exit, FULL error, commit-denied restore; tamper/cross-account swap rejection; hostile IDs | **Satisfied for tested cases.** Filesystem TOCTOU/ACL hardening, OS-store/DB atomicity, whole-database rollback resistance not claimed |
| Encrypted backup, clean restore and historical keys; QM-KEY-004/005; T08 | Actual provider-generated keys encrypt prior envelope; clean restore decrypts it; wrong secret/tamper/subject blocked; source suspended; restore archive-only; explicit destruction tested | **Satisfied for local development ceremony.** Recovery UI/media usability and independent threat-model review pending; backups/copies are not erased by local destruction |
| Documentation, review and migration; QM-DOC-001/002; §54 M3 | ADR 004, recovery/support instructions, architecture/status and retained outputs | **Partial:** independent enrollment/root-reset/backup review outstanding; no legacy migration or integrated Settings flow claimed |

The bounded authorized implementation is reviewable, but this is not a completed
production M3 experience. No M4 sending/outbox work has begun. Later platform,
packaging/license, distribution, historical-OQS compatibility and release gates
are separate from the local tests and remain unresolved.

## Exact environment and provider inputs

- Windows 11 10.0.26200 x64; Python 3.12.14, MSC v.1944 64-bit; SQLite 3.53.1.
- Rust 1.99.0 (`b940084d7`, 2026-09-28), x86_64-pc-windows-msvc, unoptimized
  dev/test profiles with debuginfo. Same native MSVC cl19.50.35728.0 input as M2.
- Sequoia 2.4.1/OpenSSL 3.5.9 and rPGP 0.21.0, defaults disabled; Sequoia
  `crypto-openssl`, rPGP `pqc`. Exact sources/archives remain in M2 inputs.json.
  No diagnostic accessor patch is used. OpenSSL static native configuration:
  `VC-WIN64A no-shared no-tests no-module no-comp no-asm --libdir=lib`, /O2 /MT
  /W3 /wd4090. Native libcrypto hash unchanged:
  `5ceb47b86bec9b3b8d6e666e718947391c59f8763be1347b0e3c2a692e022241`.
- Vault/recovery AEAD uses existing locked cryptography **50.0.2**, whose wheel
  reports **OpenSSL 4.0.3 29 Sep 2026**. This is a distinct storage backend, not a
  substitution for the selected OpenPGP provider's native OpenSSL 3.5.9.
- Existing google-auth **2.49.1** validates token signatures. No new Python
  dependency or change to M1 locks was made. Official API guidance is in ADR 004.

Root is v6 algorithm30 certification-only, three-year validity. Separate device
signing subkey algorithm30 and encryption subkey algorithm35 have one-year
validity. Rotation retains root and revoked historical subkeys, generating a new
active pair. Profile keeps v6 PKESK/signatures, SHA-512 generated signatures,
SEIPDv2 AES-256/GCM, 4096-byte chunks. Provider owns crypto encoding and randomness.

## Commands and retained results

PowerShell at repository root; no secrets passed in arguments:

```powershell
./experiments/m3/build-provider.ps1
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests --reverse
$env:OQS_INSTALL_PATH = Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.audit_snapshot
```

Build script commands are exact `cargo build --manifest-path
experiments/m3/provider/Cargo.toml --locked --offline` and `cargo test
--manifest-path experiments/m3/provider/Cargo.toml --locked --offline --
--test-threads=1`, with explicit M2 local toolchain/native environment.
Python runner invokes pytest with `experiments/m3/tests -q --tb=short` and a unique
ignored `--basetemp=tmp/m3-pytest-<random UUID>`; it sorts actual node IDs in each
order, compares discovered/executed sets and rejects skips/missing tests.

| Retained output | Exact result |
|---|---|
| [Native helper](evidence/m3/native.txt) | 2 passed; 0 failed/ignored/measured/filtered; 1.14 s |
| [Normal](evidence/m3/normal.txt) | 32 passed; 14.80 s; no warnings/skips; 32 distinct identities checked |
| [Reverse](evidence/m3/reverse.txt) | Same 32 distinct tests, reverse order; 32 passed; 14.74 s; no warnings/skips |
| [Legacy](evidence/m3/legacy.txt) | 37 passed; 5 existing datetime.utcnow deprecation warnings; 2.68 s; zero skips |
| [Snapshot audit](evidence/m3/input-hashes.json) | Source/lock/script/test hashes, native/helper binary hashes, M2 preservation, distinct test identity correspondence |

Real-store tests ran outside the restricted sandbox in the authorized user logon
session and used only disposable randomly named M3 credentials. Cleanup deletes
each created entry; the main fixture checks subsequent reads fail. The test suite
does not enumerate unrelated credentials. SQLite FULL is injected through
`max_page_count`; commit denial through SQLite's authorizer; abrupt interruption
uses a child process exiting 17 while a transaction is uncommitted. These are
executed engine failure paths. The separate `Failing` OS-store stub only proves
adapter error propagation. OAuth signatures use real google-auth/RSA verification
with a synthetic in-memory issuer key response, never live Google evidence.

## Development failures and assurance limits

- Initial native compilation rejected two invalid key fingerprint calls and a
  temporary borrow during rotation. Corrected API use; final native tests pass.
- Sandbox trial: 2 failed, 14 passed, 11 errors. Windows credential access and
  temporary-directory creation were denied. The other failure was the synthetic
  HTTP fixture accepting keyword-only arguments while google-auth passed a URL
  positionally. Normal-logon trial had 26 passed/1 fixture failure; fixture was
  fixed, then 29 passed. No assertion or backend check was removed.
- Direct script runner initially shadowed stdlib `types`; package-module execution
  fixes the import boundary. A 30-test normal/reverse run and 37-test legacy run
  then passed. Official Google guidance led to explicit third-party address-
  authority rejection and two more cases; final 32-case outputs above supersede
  those earlier counts and belong to the final source hashes.
- Retained native output includes sandbox path-canonicalization and incremental
  hard-link/copy warnings. No new native library build or warning suppression
  occurred. M2's diagnostic categories, mandatory-hash panic, allocation-context
  fallback and constant-time uncertainties remain unchanged and unresolved.
- No claim of production Python IPC qualification, secure zeroization, FIPS,
  anti-rollback storage, independent human review, native primitive KATs, Linux
  execution, real mail-provider support or simultaneous multi-device support.

The exact next bounded work is M3 external-browser/PKCE/session integration and
real provider acceptance using owner-controlled test accounts, plus independent
enrollment/recovery and M2 crypto/protocol review. It requires a new task; this
continuation stops at the local M3 checkpoint and does not begin M4.
