# Windows M6 Settings completion — 2026-10-21

Starting checkout: `codex/m6-gmail-inbox` at
`f39bc5429658ec3009b9ce10c3f1cd39c21db3ef`, clean tracked tree. The reference PDF,
user launcher and M2 reviewer draft are preserved and excluded. Earlier evidence
is unchanged. No live account, external mail, dependency/provider upgrade or data
migration. This record supersedes the synchronous-Settings blocker in the prior
Windows assessment, not its historical results.

## Acceptance

| Requirement | Executable evidence / result |
|---|---|
| Enrollment/restore, vault reads, certificate import/verification/export, activation/replacement, rotation/revocation and backup/transfer off GUI | `core.settings_operations`: frozen owner/path/identity/generation requests; one admitted request, one worker, no queued destructive work. Real disposable vault tests exercise these paths. No mutable IdentityService or widget is executed by the worker. Each SQLite connection opens and closes on that worker. |
| Responsive selection/Cancel/Lock/close | Controlled delayed read plus a running Qt timer; real SQLite write contention; slow native generation/restore; cancellation/selection/Lock/close return within 1 s in the tested phases. Cached account selection and asynchronous contact loading remove synchronous notification reads. |
| Synchronized authorization and accurate commit handling | Short session-mutex reservation immediately before COMMIT/file persistence; all expensive work/I/O is outside that mutex. Tests pause before/after reservation. Before reservation cancellation rolls back; afterward the original authorized effect may finish. Its encrypted account receipt survives stale publication. |
| Account isolation/stale results | Requests capture original account/vault and generation. Read-only requests compare generation without incrementing it. Two-account tests suppress late UI results, verify receipts land only in the owning account, and preserve compose/outbox completion while background reads run. |
| Recovery-secret custody | No file before explicit secret acknowledgment. Wrong acknowledgment rejects; cancelled/closed/display-failed ceremony leaves no package. Acknowledged secret restores the actual package after locking/cancelling or a real SQLite COMMIT denial. No plaintext-secret persistence is introduced. |
| Transfer failure/restore/history | Failed write, cancellation before final commit and denied COMMIT leave source active. Success suspends only after persisted package. Async restore stays archive-only, unchanged-root activation preserves fingerprint, replacement changes it. Native rotation/revocation retain historical secret snapshots; existing M3 recovery/decryption regressions pass. |
| Bounded admission and cleanup | Duplicate operation rejected; controls disabled while busy; cancelled results and private stages released. Disposal drops completed private results and drains the single worker. Actual SQLite lock can be reacquired after cancellation. |
| Existing M6 boundaries | Affected full M6 suite retains real crypto, UID/PEEK, explicit read flags, safe plaintext display, attachment/reply/forward, frozen outbox and Accepted/Failed/Unknown checks. No production pipeline redesign. |

**Decision: the requested local Windows M6 engineering blocker is resolved.**
Live Google browser/refresh/IMAP/SMTP acceptance and human usable-security/
accessibility walkthrough remain pending. Independent cryptographic/enrollment/
MIME review remains deferred under ADR 004/006, not approved. Existing qualified
limits, historical compatibility, licensing, distribution and release gates remain.
No M7/M8 or new platform requirement is added.

## Commit/outcome contract

`ScopedVault` uses the existing vault transactions through a small `Vault.commit`
seam; default callers retain the original SQL COMMIT behavior. It encrypts an
operation ID/type/state receipt into the affected account in the same transaction.
No SQLite connection crosses threads. Guard reservation and GUI invalidation share
the session mutex. Reservation authorizes that specific irreversible step; it does
not hold the GUI lock during disk commit. Cancellation after reservation is not a
promise of rollback. Final publication checks ownership/generation again.

Unlock/select the original account and **Inspect outcomes** to see the last 16
committed receipts. Export intents are retained separately, up to 16 per account;
the bound rejects another export instead of deleting history. An intent does not
prove file completion. Inspection compares the selected file's SHA-256 and reports
the current source lifecycle. Missing/inaccessible/changed files report no match,
not automatic retry. Enrollment/restore/creation may require Unlock to discover a
new committed account/vault after cancellation. No receipt is a transport-delivery
claim. Recent-operation receipts replace only older receipt metadata, not user
keys, ciphertext or event history.

Filesystem and SQLite effects are not atomic together. Backup/public export intent
is committed first; file write is separately authorized, exclusive and flushed;
final receipt and any transfer suspension commit afterward. Failed/partial files
are left for explicit inspection, never silently overwritten. A file may exist
with only an intent receipt and an active source. The acknowledged recovery secret
still opens a complete matching backup. No cancellation recalls external effects.

## Recovery ceremony and exact retention policy

**Encrypted backup / Transfer device** now prepares a package and random 32-byte
secret in worker memory only. Transfer still requires explicit initial confirmation.
**Complete backup** shows the secret locally. The owner saves it offline separately,
re-enters the complete secret and clicks **I saved the secret separately; write
package**. Only that acknowledgment admits persistence. It is an operator custody
assertion, not proof that the human actually saved a durable copy.

Before acknowledgment, Cancel/Lock/account switch/close clears the stage and secret
widgets; no package has been written. A display failure can be retried while the
same current stage exists. After acknowledgment, no worker request needs the secret:
only encrypted package bytes, destination, transfer flag and expected account
revision are sent. Private stage/widgets are cleared. A revision change rejects
export and requires preparing/acknowledging a fresh package. Cancellation/display
failure after persistence cannot remove the owner's already acknowledged copy.

QuMail still does **not** save the recovery secret in the vault, logs, arguments,
clipboard, temporary files or escrow. The policy change is disclosure/acknowledgment
**before**, instead of after, file persistence, with short in-memory retention until
acknowledgment/cancel/lock/close. Python/Qt memory is not securely zeroized. OAuth
tokens and local Settings receipts/export paths are excluded from new packages.
The established packet/recovery format, archive-only restore, historical keys and
root verification requirements remain unchanged. Old packages remain readable.

## Limits and assurance

One Settings worker and one admitted request bound concurrency and retained private
results. Work has a 120 s stage deadline (240 s for authorization pipelines), checked
between phases and before irreversible reservations. Original native calls retain
their 30 s timeout; SQLite busy waits remain at most 5 s. Google uses the existing
bounded child (210 s enrollment, 30 s refresh). Cancellation keeps the GUI responsive
and prevents later unauthorized phases; it does not forcibly interrupt an in-flight
native call, filesystem syscall or authorized SQLite COMMIT. Final process shutdown
may wait for such a worker. No universal subsecond OS/process-exit promise.

Qt tests use the existing offscreen fixture on Windows. They are automated event,
keyboard and ownership evidence, not independent screen-reader/human approval.
Native keys/vault/Windows secure storage and local mail TLS are real disposable
instances; Google authorization is synthetic. No personal caches were consulted.

## Reproduction and retained outputs

From the repository root, existing environment/helpers, normal Windows secure-store
permissions. Exact final commands:

```powershell
@'
import uuid,pytest
from experiments.m3.run_tests import Results
r=Results(True)
code=pytest.main(['experiments/m6/test_settings.py','-q','--tb=short','--basetemp=tmp/m6-settings-focused-'+uuid.uuid4().hex],plugins=[r])
assert not code and not r.skipped and len(set(r.discovered))==len(r.discovered) and set(r.passed)==set(r.discovered)
print('IDENTITY CHECK: reverse',len(r.passed),'distinct tests passed; zero skips')
for name in r.passed: print('EXECUTED:',name)
'@ | & .venv-m1-clean/Scripts/python.exe - *> tmp/m6-settings/focused-final.txt
./.venv-m1-clean/Scripts/python.exe -m experiments.m6.run_tests *> tmp/m6-settings/normal.txt
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests *> tmp/m6-settings/m3.txt
./.venv-m1-clean/Scripts/python.exe -m experiments.m6.audit_settings > docs/operations/evidence/m6-settings/input-hashes.json
```

Final results and hashes are recorded in the current M6 validation/status entry and
[manifest](evidence/m6-settings/input-hashes.json). They apply to recorded final
working-tree runtime bytes, not unchanged parent HEAD. Audit/docs were written after
tests. M1/M2 and prior M6 evidence remain historical, not relabeled as new execution.
Unchanged M4/M5/legacy suites were not repeated; affected M3/M6 checks were.

Development failures are retained: missing explicit Qt fixture import (11 setup
errors); nondeterministic fixture account-order assumption (2 failures/9 passes);
incorrect expected trust label (1/13); old immediate-export UI assumption (1/53);
and the real background-read generation bug suppressing two mail completions
(2/79). Fixes preserve assertions: select the distinct owner explicitly, assert
`independently_verified`, require secret acknowledgment, and give read-only work
non-mutating generation checks. Intermediate passing runs predate final synchronized
cancel/path checks and are not final-snapshot evidence. No unexplained skips.
Retained outputs normalize line endings and replace the local workspace prefix
with `<WORKSPACE>`; original command output remains in ignored `tmp/m6-settings`.
No test identities, counts, failure messages or outcomes were removed.

Next user step: provide explicitly provisioned client path/two controlled accounts
and browser time using the [existing Google checklist](m6-google-acceptance.md).
Retrieval authorization is distinct from permission for its bounded test sends.
