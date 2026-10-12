# Current M4 qualification

Updated 2026-10-12. [Controlled SMTP/TLS validation and acceptance](m4-smtp-tls-validation.md)
is the current record, with a new tested-source manifest under `evidence/m4/tls/`.
The bounded transport/development integration is complete. Full M4 remains PARTIAL
while legacy compose still uses F07 ordering; live Google and independent review
retain ADR 004/005's exceptions and release gates.

## Preserved b833e8b baseline report

The report below describes the earlier 40-case simulation-only snapshot. Its
claims about no SMTP adapter, coarse writer locking and GC cleanup are historical.
It is preserved with its original input/output evidence, not overwritten.

# M4 durable outbox validation

Date: 2026-10-11 (Asia/Calcutta). **Bounded engineering proof complete; M4 PARTIAL
for full milestone acceptance.** No real SMTP/TLS or live Google acceptance,
production MIME, independent approval or F07 remediation of legacy send is claimed.
The owner's explicit ordering exception is [ADR 005](../adrs/005-m4-development-ordering-and-outbox.md).

## Actual handoff and scope

Actual initial checkout was `codex/m3-identity-vault` at
`1af13a1ee8a58016bdca2dfa25055eb689ec7fd8`, with no tracked changes. Only the
reference PDF and `docs/operations/m2-reviewer-request.md` were untracked. M3's
24 source inputs, four retained outputs, helper/library hashes and reviewer draft
matched the retained manifest. Created local `codex/m4-durable-outbox` from that
exact checkpoint. M1/M2/M3 branches, canonical specification, proof source/locks,
previous evidence, default entry point, user data and reviewer draft remain intact.

New behavior is in `experiments/m4`, using existing M3 vault/provider interfaces.
No production module imports it; the demonstration requires `--simulate`.
No package/native input changed. No credentials or generated binaries are committed.

## Acceptance table

| M4 criterion and canonical reference | Executed evidence | Disposition |
|---|---|---|
| Typed account-scoped preparation/submission; Ã‚Â§Ã‚Â§47, 54 | Qt-independent Protocols, frozen envelopes/bindings, coherent selection lease; cross-account and stale/cancel tests | Pass, development boundary |
| Verified recipients and usable keys; Ã‚Â§50, I06 | Wrong/locked account, unknown/unverified/changed/revoked recipient, expired sender key, wrong key/profile, real root replacement and same-root subkey rotation block; prior M3 provider expiry cases retained | Pass for local pinned trust; no online revocation freshness claim |
| Complete encrypted bytes/key references before transport; Ã‚Â§Ã‚Â§43/46, QM-MAIL-004, I03 | Real provider payload decrypts at separate recipient; SQLite persisted draft/envelope/Message-ID/profile/recipients/root/subkeys/archive refs; preparation commit denial prevents submit | Pass for authorized raw-provider fixture; full wire MIME/headers belong to M5 |
| Sensitive content/metadata protected; Ã‚Â§46 | Actual M3 AES-GCM/Windows store, raw SQLite lacks draft/base64/address/token literals; account ownership and authenticated aggregate | Pass within inherited M3 threat limits; no raw content key saved |
| Stable operation/retry bytes; I09, Ã‚Â§50 | Equality of complete PreparedEnvelope after reopening, every retry and ten process crash boundaries; changed capabilities block without replacement bytes | Pass |
| Durable honest state/attempts; Ã‚Â§50, QM-REL-001 | Draft/Prepared/Submitting/Accepted/Unknown/Failed transitions; two commits; actual process termination, real SQLite COMMIT denial and SQLITE_FULL; final result commit failure returns uncertainty | Pass for measured process/SQLite failures, not physical power-loss certification |
| Concurrent submission and restart; T07/T09 | Competing workers/recovery serialize; only one simulated call; no auto-resend after restart; recovery-before-transport gap checked in source and state guard | Pass for coarse development locking |
| Explicit Unknown retry/reconciliation; Ã‚Â§50 | Duplicate-risk acknowledgment mandatory; observer cannot interpret absent/rejected lookup as proof of no prior acceptance; reconciliation never resends | Pass with synthetic observations; no provider reconciliation claim |
| Bounded cancellation/retries; QM-REL-003, T09 | Three-attempt cap, cancelled/expired leases, selection during prepare/transport, fixed storage/input bounds | Pass for explicit single-attempt simulation; automatic transient backoff/jitter is not implemented or claimed |
| Optional receipt failure cannot change Accepted; Ã‚Â§54 M4 | Injected export failure and actual child termination before/after writing optional receipt preserve Accepted | Pass |
| TLS before credentials / actual SMTP semantics; QM-MAIL-001, T07 | No real adapter exists; non-simulation adapter is rejected; tests disable network connections | **Pending future bounded M4 transport qualification**, not inferred from simulations |
| Account/provider acceptance and independent review | M3 Google test-client acceptance absent; ADR 004/005 development exceptions preserved | Pending live-provider evidence; review deferred before production/security release |
| Legacy F07 | Legacy regression characterization still passes; unchanged `_SendWorker` still submits before all persistence | Not fixed across legacy entry points; no global remediation claim |

## Commands, environment and final retained results

Executed on Windows 11 `10.0.26200`, x64, Python 3.12.14 MSC v1944, SQLite 3.53.1.
Same locked Python environment: cryptography 50.0.2, google-auth 2.49.1,
google-auth-oauthlib 1.3.0, PyQt6 6.10.2, pytest 8.4.2. Legacy regression uses
liboqs-python 0.16.0.1/native 0.16.0 research lane, not the unavailable 0.14.1 artifact.

OpenPGP helper is the unchanged M3 Windows MSVC build: Sequoia 2.4.1/OpenSSL 3.5.9,
with rPGP 0.21.0 existing interop proof. Source references, ordinary/diagnostic locks
and exact native flags remain in M2/M3 records. No native rebuild occurred here;
the helper SHA-256 and native library SHA-256 match the M3 manifest. Python storage
cryptography's bundled backend remains distinct. No Linux execution is claimed.

```powershell
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.harness --simulate
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.run_tests
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.run_tests --reverse
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests
$env:OQS_INSTALL_PATH = Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q
uv --cache-dir tmp/m4-uv-cache pip check --python .venv-m1-clean/Scripts/python.exe
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.audit_snapshot
```

| Retained output | Result |
|---|---|
| [Harness](evidence/m4/harness.txt) | Prepared; interrupted committed intent; restart Unknown; explicit retry Accepted; identical bytes; export failure preserves Accepted; disposable cleanup succeeds |
| [Normal](evidence/m4/normal.txt) | 40 passed, 35.98 s, zero skips/warnings |
| [Reverse](evidence/m4/reverse.txt) | Same 40 distinct cases, 40 passed, 34.87 s; zero skips/warnings |
| [M3 regression](evidence/m4/m3-regression.txt) | 54 passed, 12.26 s, zero skips/warnings |
| [Legacy](evidence/m4/legacy.txt) | 37 passed, 5 existing datetime warnings, 2.40 s; zero skips |
| [Dependencies](evidence/m4/dependencies.txt) | 47 packages checked; all installed packages compatible (394 ms) |
| [Input/output attribution](evidence/m4/input-hashes.json) | Current working-tree hashes, same distinct forward/reverse cases, preserved M2/M3 inputs/output/helper; this commit contains those tested bytes |

Real Windows credential tests run in the normal desktop logon environment with
random disposable entries and cleanup. The initial sandboxed legacy command
could not clean its isolated temporary directory (WinError 5); rerunning unchanged
tests in the normal environment passed. `python -m pip check` was unavailable
because this uv-managed environment has no pip module; use the recorded uv check.
The first uv check also hit a sandbox cache-directory permission error; the final command uses an explicit writable cache under ignored tmp/. These environment failures are not represented as successful test runs.

Initial development suite: 33 passed. Review added same-root subkey binding,
cancellation/reconciliation and receipt-crash cases; expanded suite: 39 passed.
The first harness invocation failed deleting its disposable SQLite file on Windows
because the unchanged M3 creation context manager leaves an unreachable connection
until collection. Harness cleanup now explicitly collects it before temporary-file
removal; the 40th test checks opt-in and cleanup. M3 source was not silently changed.

## Failure-evidence distinctions and review notes

- **Real provider behavior:** generated recipient-owned keys, sealing/decryption
  and rotated subkeys through unchanged native helper. M4 does not rerun or claim
  new independent interoperability; retained M3/M2 evidence remains authoritative.
- **Real persistence/process behavior:** Windows credential access, SQLite writer
  serialization, authorizer-denied COMMIT, max_page_count-induced SQLITE_FULL,
  child kill at ten points and authenticated reopening. Ten points are before/
  after preparation commit, intent commit, simulated transport observation,
  result commit and optional receipt persistence. The transport's server acceptance
  itself is simulated, not evidence from a real SMTP server.
- **Mock/controlled behavior:** issuer/credentials, token expiry, provider failure,
  deterministic acceptance/rejection/loss, reconciliation and optional export
  exceptions. The harness interruption is explicitly simulated; the suite's child
  termination is real. No live mail server or existing cache was accessed.
- **Source inspection/design:** a writer lock spans simulated transport/result
  persistence, so active recovery cannot steal ownership. Race in the unlocked
  gap is conservatively blocked by status/attempt recheck. Same-user hostile code,
  physical power loss, database rollback and arbitrary injected adapter timeouts
  are not proven safe by these tests. Do not describe this review as independent.

Remaining production/integration questions: dedicated outbox scheduling instead of
the coarse vault lock; cancellation/deadline enforcement in an actual transport;
TLS certificate/hostname failures before credential access; actual SMTP DATA loss
and provider reconciliation; mail-scope OAuth; UI result generation checks; M5
complete MIME/header/archive profile; restored outbox ownership/reconciliation;
platform and release qualification. Existing native warnings, panic/fallback,
constant-time assurance, original-provider/historical compatibility and licensing
gates remain unchanged. No warnings were suppressed to pass these tests.

## Exit and next bounded step

The requested isolated durable-preparation/outbox/transport-boundary engineering
is complete. M4 remains PARTIAL for full acceptance, chiefly real transport/TLS
and application integration evidence; this is distinct from the authorized M5
deferral of comprehensive MIME. M2/M3 are not promoted to complete.

Recommended next task: qualify an opt-in M4 transport adapter against a controlled
loopback SMTP/TLS fixture, including certificate/hostname rejection before auth,
DATA acceptance-loss and bounded cancellation, without real credentials or mail.
Separately, provision M3 Google test-client accounts for the documented user-driven
browser acceptance. Independent review remains due before production/security
release and does not repeatedly halt explicitly authorized development.

Stop here: no M5, real send, migration, publication, push, merge or release.
