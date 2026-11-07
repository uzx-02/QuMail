# Build, run, test and troubleshoot

Run commands from the repository root in Windows PowerShell. These are inspected
existing recipes; **not rerun as part of the documentation handover** unless the
specific check is named in [STATUS_AND_ROADMAP](STATUS_AND_ROADMAP.md). No command
below grants authorization to send mail or create/replace an existing vault.

## Existing environment and offline checks

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
$pythonPath = (Resolve-Path .\.venv-m1-clean\Scripts\python.exe).Path
& $pythonPath --version
& $pythonPath main.py --help
```

Historical M7 environment: Windows 11 build 26200 x64, Python 3.12.14/MSVC1944,
pytest 8.4.2, PyQt6 6.10.2, cryptography 50.0.2, google-auth 2.49.1,
google-auth-oauthlib 1.3.0, SQLite 3.53.1. Use current reporting when executing anew.
Python may have been installed without pip; do not infer dependency consistency
from `pip check` if that command cannot run. M1 hosted consistency results remain
separate. Do not upgrade dependencies merely to obtain a familiar command.

| Backend purpose | Exact retained input / provenance |
|---|---|
| Legacy research OQS | liboqs-python **0.16.0.1** / liboqs **0.16.0**; `packaging/native-research.json`, ADR 002. Original declared **0.14.1 remains unavailable**. No substitution claim. |
| Modern native helper | Sequoia **2.4.1**, OpenSSL **3.5.9** static build; independent peer rPGP **0.21.0** with pqc; `experiments/m2/inputs.json` and per-crate Cargo locks. |
| Python SMTP/IMAP/HTTP TLS | Python ssl reported **OpenSSL 3.5.8** in M7 evidence. This is not the linked modern crypto helper. |
| Vault AEAD | Python **cryptography 50.0.2** wheel/backend, not the helper or Python ssl. Its underlying backend version must be measured separately if claimed. |
| Diagnostic M2 provider | Separate source copy/context accessor and backend-probe lock; ordinary helper must not be replaced by it. |

Existing native inputs, checked during handover (SHA-256):

```text
tmp/m2/target/debug/qumail-m3-provider.exe
f0b3c683d8afcbafb4b0043e46fb11d88fa98780fd3ffe2477afd1b9e03ca516
tmp/m2/target/debug/qumail-m5-provider.exe
a07bec89fa06a172688f7565911554256b82c5db4d048900dd6d91643fc699f8
tmp/m2/openssl-install/lib/libcrypto.lib
5ceb47b86bec9b3b8d6e666e718947391c59f8763be1347b0e3c2a692e022241
```

These are local artifact identities, not signed releases or cross-machine
bit-reproducibility guarantees. Binaries/environments remain ignored, not in Git.

## Fresh environment and native rebuild (only if necessary)

Network required unless all exact packages/sources are already cached:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r packaging/requirements-dev.lock
.\.venv\Scripts\python.exe -m pip check
```

Use a provisioned CPython 3.12; `.venv` above is a deliberate new environment, not
an instruction to overwrite `.venv-m1-clean`. Runtime lock is smaller; it does not
by itself qualify native legacy Level 3. Hash locks include Python versions/markers.
No application startup may download/build a missing provider.

M1 native recipe: [native-research.md](../operations/native-research.md),
[CI](../../.github/workflows/m1.yml). It pins OQS source; Windows local GCC and hosted
MSVC/Ubuntu hashes differ legitimately. Do not copy a Windows binary into Linux.

M2/M3/M5 require x64 Visual Studio C++ tools, isolated Rust **1.99.0**, pinned
portable Perl/libclang and OpenSSL source from `experiments/m2/inputs.json`.
Exact preparatory downloads/checks are in [M2 README](../../experiments/m2/README.md).
Network fetch is explicit; archives must match recorded hashes. OpenSSL release
signature verification was not performed in historical proof. Scripts assume root
working directory and existing isolated caches. Use an x64 C++ build environment.

```powershell
# After obtaining/checking inputs; do not run to solve a launch-path issue:
powershell -NoProfile -File .\experiments\m2\build-native.ps1
# Cargo fetch requires network if its exact locked registry cache is absent.
# Set RUSTUP_HOME/CARGO_HOME as described in experiments/m2/README.md first.
powershell -NoProfile -File .\experiments\m3\build-provider.ps1
powershell -NoProfile -File .\experiments\m5\build-provider.ps1
```

The latter scripts set RUSTUP_HOME/CARGO_HOME/CARGO_TARGET_DIR under tmp/m2,
LIBCLANG_PATH, OPENSSL_DIR, OPENSSL_STATIC=1 and OPENSSL_NO_VENDOR=1; enforce the
audited libcrypto hash, then Cargo build/test `--locked --offline`. Missing cache
is an explicit preparation failure, not permission to update the lock/provider.
OpenSSL flags: `VC-WIN64A no-shared no-tests no-module no-comp no-asm --libdir=lib`.
Keep ordinary and diagnostic locks/build outputs distinct. `no-asm` is not
constant-time assurance. Rebuilt binary hashes/results need fresh attribution.

M2 proof reproduction, not needed for a launcher change:

```powershell
powershell -NoProfile -File .\experiments\m2\prepare-probe.ps1
powershell -NoProfile -File .\experiments\m2\run.ps1
powershell -NoProfile -File .\experiments\m2\run.ps1 -Order reverse
```

Normal lane uses unmodified Sequoia; backend lane uses the diagnostic copy. See
`audit-inputs.py` for expected retained-log locations and exact 651-file patch audit.
It is not an independent cryptographic review.

## Launch and the unresolved desktop mismatch

**Do not repeat the private old launcher as a known-working desktop recipe.**
`tmp/m7/Start-GoogleAcceptance.ps1` still chooses the inaccessible old desktop
vault path. The current ignored `.lnk` dry-run shortcut is also untested. Full
incident/pause state is in STATUS_AND_ROADMAP; no new vault was created.

The reusable versioned launcher is safe only with deliberately selected paths:

```powershell
$clientPath = Read-Host 'Full path to your provisioned Google Desktop JSON (path only)'
$vaultPath = Read-Host 'Full path to the intentionally selected disposable vault'

# Preflight check only (no application launch, no database creation):
powershell -NoProfile -File .\tools\start_google_acceptance.ps1 -GoogleClient $clientPath -Vault $vaultPath -AllowNewVault -CheckOnly

# Dry-run launch (submission strictly disabled; safe for desktop verification and Settings exploration):
powershell -NoProfile -File .\tools\start_google_acceptance.ps1 -GoogleClient $clientPath -Vault $vaultPath -AllowNewVault -DryRun

# Settings-only launch (isolated identity Settings; no mailbox window, sending disabled):
powershell -NoProfile -File .\tools\start_google_acceptance.ps1 -Vault $vaultPath -AllowNewVault -SettingsOnly
```

For an existing accessible vault, omit `-AllowNewVault` and choose **Unlock** in Settings.
For a genuinely NEW, distinct test vault, explicitly append `-AllowNewVault`. This ensures the parent directory exists and permits startup; **Settings → Create vault** remains the explicit user creation action. Never use this switch to recover or overwrite old keys.

Live Gmail submission requires the explicit `-EnableGmailSubmit` switch instead of `-DryRun` (mutually exclusive with `-DryRun` and `-SettingsOnly`):
```powershell
powershell -NoProfile -File .\tools\start_google_acceptance.ps1 -GoogleClient $clientPath -Vault $vaultPath -EnableGmailSubmit
```
Paths from Read-Host should be entered without surrounding quote characters.

The immediate successor task stops before Create vault/auth/send; owner will test.
Use the owner's normal desktop/logon. Tool shell LOCALAPPDATA/filesystem views may
differ, even if identity strings match or an escalation succeeds. Validate the actual
desktop visibility and GUI before claiming a remedy. No cache/credential search.
Windows Credential Manager must be available to that logon; absence fails closed.
Do not copy the DB plus raw master key to make it work. Orphan create artifacts need
explicit diagnosis, not bulk deletion. Existing data and credential entries survive.

Direct modes (configuration variables above must refer to actual selected paths):

```powershell
# Mailbox with sending disabled:
& $pythonPath main.py --dev-mailbox --dev-vault $vaultPath --google-client $clientPath
# Separate isolated identity UI, no mailbox/sending:
& $pythonPath main.py --dev-identity --dev-vault $vaultPath --google-client $clientPath
```

For explicit authorized sends only, add `--dev-gmail-submit` to mailbox mode.
`main.py` without development options opens legacy UI, not the modern path.
`--dev-simulator` is a separate legacy lab option, never needed for modern Gmail.
Close Settings to lock; while testing mail, minimize/switch windows instead.

## Google acceptance and manual handoff

The owner already provisioned an External/Testing **Desktop app** client and both
controlled accounts as test users. Read only explicitly supplied configuration paths;
do not paste/store JSON or tokens in handover. Modern scopes are `openid`,
`https://www.googleapis.com/auth/userinfo.email`, and for mail
`https://mail.google.com/`. Identity-only consent cannot be reused for IMAP/SMTP.
No Yahoo enrollment or password fallback. [Google desktop guidance](https://developers.google.com/identity/protocols/oauth2/native-app).

Actual success/failure record: [Google acceptance](../operations/m6-google-acceptance.md).
Manual controls and result template: [manual checklist](../operations/google-manual-acceptance.md).
Do not treat the browser callback page as enrollment success; verify account/root
and refresh in Settings. The <=20-second not-yet-valid-token wait reruns full
signature/audience/time verification with zero skew; signature/expiry failures
must not be “fixed” by relaxing checks. Never log callback URLs.

The only currently authorized sends are controlled A→B small attachment + archive,
B→A protected reply and B→A explicit forward. A/B addresses remain owner/private
configuration, not committed identifiers. The user now wants to perform tests
manually; don't initiate them during launcher handoff. Unknown means investigate,
not automatic retry. Sanitized records use aliases, step/outcome, source SHA,
message UID identity and Seen change; omit bodies/subjects/keys/tokens/private logs.

## Proportionate tests and retained evidence

Offline means no internet accounts, but local TLS sockets and disposable Windows
Credential Manager operations are real. Run in a context permitted to use them;
do not mock secure storage just to get a pass. Fixtures clean only their owned keys.

```powershell
New-Item -ItemType Directory -Force tmp/handover-checks | Out-Null
& $pythonPath -m pytest experiments/m6/test_settings.py -q *> tmp/handover-checks/settings.log
# Inspect exit code, then the short tail; preserve failures.
$LASTEXITCODE
Get-Content tmp/handover-checks/settings.log -Tail 8
```

| Change | Appropriate checks (after selecting installed interpreter) |
|---|---|
| Launcher/docs only | PowerShell parse/preflight positive/negative cases with no database creation; actual desktop GUI launch if claiming it. Links/path/hash checks; no whole milestone rerun. |
| Google verifier/transport | `-m pytest experiments/m6/test_google_diagnostics.py experiments/m3/tests/test_integration.py -q` plus affected connection tests; controlled fixtures do not prove live consent. |
| Settings/session/recovery | `-m pytest experiments/m6/test_settings.py experiments/m3/tests -q`; affected M6 checkpoint regressions. |
| Mailbox/workflows/UI | `-m pytest experiments/m6 -q`; M3/M4/M5 affected cases when contracts change. |
| M3/M4/M5 ordered suites | `-m experiments.m3.run_tests`, `-m experiments.m4.run_tests`, `-m experiments.m5.run_tests`; add `--reverse` for actual inverse-order identity checks. |
| M6 ordered runner | `-m experiments.m6.run_tests [--reverse]` covers four original M6 modules, **excludes later test_google_diagnostics.py**. Use explicit full directory or retained command list for current complete M6 scope. |
| Local relay | `-m pytest experiments/m7 -q -rA`; Windows/native helpers and actual local mTLS required. |
| Combined latest checkpoint | `-m pytest experiments/m7 experiments/m6 experiments/m3/tests -q -rA` (historical 163). Reverse exact 27 IDs/argv are in retained checkpoint-commands.json; do not pretend that subset reverses all 163. |
| Legacy compatibility | Set OQS_INSTALL_PATH to verified `tmp/oqs-install`, then `-m pytest tests -q`, with `--test-order reverse`/`20261003` where needed. Missing native crypto fails; deselection is explicitly partial. |

To replay the exact **final 27-case reverse subset** after a relevant change:

```powershell
$recordedCommands = Get-Content docs/operations/evidence/m7/checkpoint-commands.json -Raw | ConvertFrom-Json
$reverseArgs = @($recordedCommands.reverse)
& $pythonPath @reverseArgs
```

This is the retained reverse argv, not a reversal of all 163 combined cases. Earlier
M7 historical command descriptions are commented to avoid running angle-bracket
placeholders as PowerShell. The original logs and JSON commands are unchanged.

`pytest.ini:testpaths=tests`: plain pytest omits modern experiment suites. Check
exit codes before stating success. Historical order/count correspondence comes
from logs/manifests, not test-name inspection. [M7 evidence](../operations/evidence/m7)
contains final commands, node IDs, normal/reverse output and source/native hashes;
[M6 Settings evidence](../operations/evidence/m6-settings) and older milestone
directories retain their original inputs. Compare file SHA-256 using raw bytes,
including line endings. A changed manifest input needs affected checks, not reused
results. Keep generated private data/verbose logs in ignored paths; commit sanitized
evidence only after review.

## Local relay operations

QuMail does not autostart relay. Simplest reproduction is the relay test command
above; fixtures provision their temporary dedicated CA, TLS keys and database.
For an explicitly configured service, [m7-relay.md](../operations/m7-relay.md) is
the single API/quotas/retention reference. Its `C:\chosen` paths are placeholders,
not runnable provisioned configuration. Equivalent parameterized invocation:

```powershell
# Set these to deliberately provisioned local paths before running; no cloud discovery.
& $pythonPath -m services.relay --database $relayDatabase --create
& $pythonPath -m services.relay --database $relayDatabase --server-cert $serverCert --server-key $serverKey --relay-client-ca $clientCa --registry $publicRegistry --port 8443
```

Create is only for a new path with existing parent; it exits after initialization.
Do not rerun it on an existing store. Service binds loopback, validates client
certificates/allowlist; server cert must authenticate 127.0.0.1. Ctrl+C performs
bounded draining. No network filesystem WAL, public deployment, Google credentials
as relay authentication or in-memory fallback. No live relay configuration was
supplied; local test qualification is the complete approved backend scope.
