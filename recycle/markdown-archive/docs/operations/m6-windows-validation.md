# Windows M6 continuation — 2026-10-21

**M6 remains PARTIAL, including one identified Windows engineering gap.** Actual
starting branch `codex/m6-gmail-inbox`, clean tracked HEAD
`6f4d5fcb62ae0fbae7be68739e0242a4468d750d`. The reference PDF, user launcher and M2
reviewer draft remain untracked/excluded. Earlier evidence, dependencies, native
helpers, cryptographic inputs and legacy readers are preserved.

## Acceptance assessment

| Criterion / canonical reference | Evidence and disposition |
|---|---|
| Safe rendering; trust distinct from transport; §54 M6, QM-SEC-003, QM-UX-001/002 | Pass locally: real M5 verification/inbox regressions retained, plain-text status, actionable errors, no automatic trust, plaintext fallback or retry. Accepted means server acceptance only. |
| Responsive/cancellable network/mail work; §54 M6, QM-PERF-002, T12/T15 | New tests cover isolated DNS/OAuth, setup deadline, TCP/TLS cancellation, actual process reaping, pipe/thread cleanup and close during blocked refresh. Tested cancellation phases <1 s; stale-account suppression retained. Mailbox crypto already uses workers. |
| Complete Settings responsiveness; same criterion | **Engineering gap:** `IdentitySettings.poll → accept_authorization` performs enrollment/restore commits synchronously; import, activation/replacement, rotation, backup and vault reads also run synchronously. Per-call native timeout 30 s and SQLite wait 5 s are finite but do not satisfy universal responsive/<1 s UI behavior. Source inspection, not a slow-Settings acceptance test. Safely stage expensive work off UI while preserving account-generation/transaction/recovery-secret guarantees. No credentials or reviewer needed for this next local task. |
| Keyboard/error/busy states; §54 M6 review, QM-UX-002 | 13 focused Windows Qt/process tests: accessible names, Tab order, Space activation, Enter cannot submit accidentally, Escape clears/cancels, outbox selection disabled while busy, lifecycle/state controls, Settings reopening. Automated evidence is not human accessibility approval. Cross-platform QM-UX-003 belongs to M8. |
| UID/stale results/attachments/reply/forward; T07/T12/T15 | Final 65-test M6 suite passes: real disposable vault/crypto, local TLS, UID/PEEK/explicit Seen, isolation, frozen outbox/Unknown, export safety and protected references. No sample provider inbox. |
| Functionality/metadata documentation; §54 M6, QM-PRIV-002/003 | Controls and qualified limits documented; one live checklist. No release-scale or platform claims added. |
| Live Google browser/refresh/IMAP/SMTP | Pending separately: no provisioned client/browser interaction or external message. Local TLS and synthetic OAuth are not live evidence. |
| Usable-security/accessibility review; §54 M6 | Human walkthrough pending; independent cryptographic/enrollment/MIME review remains deferred under ADR 004/006. Neither is fabricated nor a reason to stop local engineering. |

## Changes and achievable bounds

`transport.bounded_worker` uses bounded private stdin/stdout (1 MiB), hidden child
processes and 50 ms polling. DNS/OAuth cannot indefinitely hold the mailbox pool
inside OS resolution/HTTP. Secrets are not arguments, files or diagnostics. Child
processes and pipes are reaped/closed on cancellation; tests assert no worker-thread
leak. DNS admits only fixed Gmail endpoints. TCP connect and verified TLS handshake
are nonblocking. IMAP DNS/TCP/TLS/greeting shares an 8 s setup deadline clamped to
the operation deadline; Gmail SMTP DNS/TCP has the same cap. The existing SMTP engine
retains verified STARTTLS and Unknown after possible DATA side effects. Numeric
loopback restrictions remain in fixture adapters.

Application Google authorization runs the unchanged M3 verifier in the child:
210 s total browser authorization budget, 30 s refresh clamped to remaining caller
budget. State/PKCE/issuer/audience/nonce/subject/address checks remain unchanged.
Child termination closes callback/network resources but cannot undo remote consent
or refresh, close every browser tab, or establish memory zeroization. No password
fallback, custom RNG, dependency upgrade or credential-cache discovery.

Settings close hides/cancels/locks while retaining its timer/executor for reopening;
final app shutdown disposes it. Mail controls now have accessible names, explicit
focus order, busy/state guards and typed error remedies. Escape clears compose.
No visual redesign. The synchronous Settings native/vault limitation above remains.

Cancellation timings start after reaching controlled blocking paths. They do not
establish hard real-time scheduling, bounded OS process creation/termination under
failure, filesystem latency or Google availability. Process shutdown still relies
on normal OS kill/reap behavior. Python memory is not securely zeroized.

## Execution evidence

Commands ran from repository root using the installed environment. Verbose output
was redirected; disposable Windows Credential Manager checks used normal approval.

```powershell
./.venv-m1-clean/Scripts/python.exe -m experiments.m6.run_tests *> tmp/m6-windows/m6.txt
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests *> tmp/m6-windows/m3.txt
@'
import uuid,pytest
from experiments.m3.run_tests import Results
results=Results(False)
code=pytest.main(['experiments/m6/test_windows.py','-q','--tb=short','-rP','--basetemp=tmp/m6-windows-focused-'+uuid.uuid4().hex],plugins=[results])
assert not code and not results.skipped and set(results.passed)==set(results.discovered)
print('IDENTITY CHECK:',len(results.passed),'distinct tests passed; zero skips')
for name in results.passed: print('EXECUTED:',name)
'@ | & .venv-m1-clean/Scripts/python.exe - *> tmp/m6-windows/focused-final.txt
./.venv-m1-clean/Scripts/python.exe -m experiments.m6.run_tests *> tmp/m6-windows/final-m6.txt
./.venv-m1-clean/Scripts/python.exe -m experiments.m6.audit_windows > docs/operations/evidence/m6-windows/input-hashes.json
```

| Retained output | Result and attribution |
|---|---|
| [Final M6](evidence/m6-windows/normal.txt) | **65 passed in 54.93 s**, 65 distinct identities; zero skips/warnings; final runtime bytes |
| [Final focused](evidence/m6-windows/focused.txt) | **13 passed in 16.78 s**, 13 distinct identities, all included above; zero skips/warnings |
| [Affected M3](evidence/m6-windows/m3.txt) | **54 passed in 11.19 s**, zero skips/warnings; before final outbox-table disabling line/two added M6 cases, which do not affect M3 |
| [Earlier M6](evidence/m6-windows/initial-63.txt) | 63 passed in 51.65 s; superseded by final 65, before final focused additions/table refinement |

No failing test executions occurred in this continuation. One requested rerun was
blocked before execution by an automatic-approval usage limit; normal retry later
succeeded. That was not a test result. Earlier failed-run records remain preserved.
Unchanged M4 85, M5 55 and legacy 37-pass checkpoint results were reused, not rerun.
The historical 52-test reverse run remains historical: no claim that the new 65-test
suite ran in reverse. No broad full-repository rerun was necessary.

New tests distinguish actual child/pipes and local TLS cancellation from synthetic
pending TCP and injected blocking OAuth HTTP. IPC success injects a synthetic
provider result: serialization/account ownership evidence, not live authentication.
Existing M3 tests retain synthetic identity-verification coverage. Windows secure
storage and selected crypto helpers are real disposable instances.

[Manifest](evidence/m6-windows/input-hashes.json) records source/test/doc/log hashes,
preserved paths and runtime versions. Results belong to these working-tree bytes,
not unchanged parent HEAD; the local Git receipt identifies the containing commit.
Windows 11 build 26200 x64, Python 3.12.14, PyQt6 6.10.2, pytest 8.4.2,
google-auth 2.49.1, google-auth-oauthlib 1.3.0, SQLite 3.53.1. Python TLS OpenSSL
3.5.8 is distinct from unchanged Sequoia 2.4.1/native OpenSSL 3.5.9 helpers.

**Next engineering task:** isolate slow Settings native/vault preparation and commit
from UI, testing cancelled/late completion, original-account durable outcomes and
recovery-secret delivery. Moving the mutable service wholesale to a thread is not
safe. In parallel, the user can provide configuration/browser time for the
[controlled Google checklist](m6-google-acceptance.md). No ports, packaging, M7/M8,
migration, external mail, push, merge or release in this continuation.
