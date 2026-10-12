# M4 controlled SMTP/TLS and development integration

Updated 2026-10-12 (Asia/Calcutta); work began 2026-10-11. The bounded engineering
and controlled SMTP/TLS qualification are complete, supported by the final evidence
below. **M4 remains PARTIAL for the full application milestone**: the production
compose entry point still uses legacy F07 ordering. This is not a claim of live
Google/SMTP-provider acceptance, production MIME support or independent approval.
The explicit ADR 004/005 development exceptions remain in force. M5 has not begun.

## Actual checkpoint and preservation

Initial and resumed HEAD: `b833e8b38892ba84bc0be3e0ab5cf29607c6d479`, branch
`codex/m4-durable-outbox`. At initial handoff the tracked tree was clean; only the
reference PDF and reviewer draft were untracked. Baseline M4 input/output hashes
matched. Current work continues on that branch without rewriting earlier evidence.
M1/M2/M3 checkpoint refs, canonical specification, native inputs/locks, older
validation output and reviewer draft are preserved. No user database/cache was read
or migrated. All new vaults, accounts, certificates and network endpoints are
disposable fixtures. Certificate private files remain in ignored temporary paths.

**One M3 source file changes:** `experiments/m3/vault.py`. `Vault.create` now closes
the creation connection with `contextlib.closing` around its transaction manager.
`Vault.connection` closes even if setup/PRAGMA fails. The GC workaround is removed
from the M4 harness. Existing M3 evidence is historical, not relabeled as execution
on this changed file. Its complete 54-case suite was rerun. Dedicated success and
exception tests retain connection objects, assert they are closed, and rename the
database immediately on Windows without garbage collection.

## Acceptance and evidence table

| Criterion / specification | Executed evidence | Decision |
|---|---|---|
| Â§54 M4 preparation/keys before SMTP; QM-MAIL-004 | Persisted provider-generated payload, frozen sender/recipients/profile/keys and Message-ID precede claim and actual SMTP connection | Pass in opt-in path |
| QM-MAIL-001 TLS before credential/AUTH | Actual STARTTLS negotiation; missing/rejected STARTTLS, untrusted/expired/wrong-host certificates all yield zero resolver/AUTH calls; fresh encrypted EHLO required | Pass on controlled Windows loopback; not live-provider support |
| Â§Â§47/50 typed identity/transport | Scoped credential handle, frozen sender match, no password/cache fallback; identity-only OAuth scope fails before AUTH | Pass; synthetic resolvers confined to fixtures |
| Â§50 honest protocol progress | Real AUTH/RCPT/DATA/final-DATA rejection, disconnect after DATA, final-response loss; final 2xx Accepted; later close exception does not replace it | Pass; server acceptance is not delivery/decryption |
| Â§43/I09 frozen bytes and recipients | Actual server compares unframed DATA digest with persisted bytes on retry; dot-stuffing test; rejection of the second required recipient results in no DATA | Pass; no reduced recipient set |
| T09 deadlines/cancellation/resource bounds | Real stalled greeting, EHLO, TLS, fresh EHLO, AUTH, MAIL, RCPT, DATA and final response; timeout/cancel cases; oversized reply rejection | Pass; no external DNS/destination permitted |
| QM-REL-001 durable worker ownership | Nonblocking OS per-operation lock plus durable random attempt ID, short SQLite claim/result commits; real competing process cannot recover/submit active worker | Pass; no timeout-based stealing |
| T07/T09 no account-wide network lock | Account and other-account mutations succeed while actual DATA response is pending | Pass; network I/O holds only operation ownership |
| T07 crash/result-commit failures | Kill sender during actual final-response wait or after response before commit; actual SQLite commit denial after server payload reception; reopen Unknown without resubmission | Pass; combined socket/process/SQLite observations |
| QM-REL-003 bounded retry | Explicit single attempts, three-attempt maximum, cancellation and deadline checks; no automatic authentication retry or scheduler | Pass in development scope; no automatic retry/jitter policy is claimed |
| Â§54 export isolation | Original export failure and ten child-crash cases retained; panel/CLI optional receipt failure preserves Accepted | Pass |
| Development interface | Real offscreen Qt timer advances during network wait; coherent M3 context, selection/lock discards late results; inspection, recovery, duplicate-risk retry and receipt controls | Pass on Windows; default/legacy paths unchanged |
| Shutdown/resource closure | Panel closes nonblocking, outer teardown joins cancelled workers before deleting disposable storage; OS ownership released; deterministic SQLite closure | Pass |
| Â§54 migration boundary | Existing user data and historical sent records are untouched; no historical record is inferred to be an SMTP receipt | Preserved |
| Full application migration / F07 | Legacy compose remains unchanged as required; no old record is reinterpreted as a submission receipt | Remaining full M4 integration task; bounded task complete |
| Later/inherited gates | Live Google/provider account acceptance, independent review, licensing/distribution; production MIME/protected headers belong to M5 | Separate gates, not a reason to stop authorized development |

## Protocol and ownership contract

The adapter uses installed Python 3.12.14 `smtplib`, `ssl`, `socket` and threading,
with no new dependency. Checked current official
[3.12 SMTP documentation](https://docs.python.org/3.12/library/smtplib.html),
[SSL guidance](https://docs.python.org/3/library/ssl.html),
[SQLite context-manager semantics](https://docs.python.org/3.12/library/sqlite3.html#how-to-use-the-connection-context-manager)
and [Windows file locking](https://docs.python.org/3.12/library/msvcrt.html#msvcrt.locking).
The docs currently display later patch releases; execution uses the exact installed
version above. Python's SMTP TLS backend is **OpenSSL 3.5.8**, distinct from
the unchanged Sequoia/OpenSSL **3.5.9** crypto helper and Python storage backend.

Only numeric IPv4 loopback is accepted, with explicit ephemeral port; no DNS or
remote hostname resolution. System verification is the default. A supplied fixture
CA is confined to the explicit fixture context and never installed in OS trust.
CERT_REQUIRED, hostname checking and TLS >=1.2 are enforced. STARTTLS capability
and positive negotiation precede TLS; capability state is discarded and EHLO is
repeated. Only then can the account-scoped resolver run and XOAUTH2 AUTH occur.
The vault resolver requires Google mail scope and the matching authorized sender;
no live token is used to test it. No token/body/server-response contents are logged.

Replies are limited to 1024 bytes/line, 32 lines and 32768 aggregate bytes. Socket
reads/writes and nonblocking TLS handshake readiness poll cancellation and an absolute deadline; a watcher also interrupts
blocked connection/handshake work. Buffered file reads were replaced after actual
Windows cancellation failures. Payload input is bounded to 1 MiB, canonical CRLF,
ASCII lines <=998 bytes. Invalid framing is rejected instead of rewriting stored
bytes. The fixture builder uses a standard MIME base64 container holding the
existing provider's ciphertext. It is explicitly a test transport envelope, not
M5's protected-header/PGP-MIME profile. SMTP dot transparency is undone by the
server before comparing hashes. No QUIT result is used to decide acceptance.

Claim and final-result persistence are short transactions. An OS byte-range lock
on a stable opaque per-operation lock file spans the network attempt. Files are
never unlinked on unlock; there is no lease expiry. Recovery acquires that same
lock nonblocking, then rechecks durable state. Crash releases the kernel handle;
the interrupted Submitting record becomes Unknown. Attempt UUID comparison prevents
stale result persistence. Local account switching cancels I/O, but observed results
are persisted for the original authenticated account; GUI generation checks prevent
displaying that result in another account. No global credential/display assignment.

Assurance limits: cooperative workers must use the same canonical local vault path;
hostile same-user file aliasing/removal, network filesystems, machine power loss and
rollback resistance are not proven. The POSIX lock branch is inspected, not executed.
No exactly-once SMTP claim follows from a local lock or operation ID. Fixtures do
not prove live-provider token semantics, anti-abuse behavior or delivery.

Earlier disposable M4 prepared records without a frozen sender are not silently
upgraded: envelope loading fails closed; inspection preserves their original state
and bytes. No production/user data migration is performed.

## Exact execution and retained evidence

Windows 11 10.0.26200 x64; Python 3.12.14 MSC v1944; SQLite 3.53.1.
Same locked packages/native inputs as the baseline. No provider rebuild or version
substitution. The historical M4 manifest is checked against b833e8b's Git blobs;
current hashes are in the new [TLS manifest](evidence/m4/tls/input-hashes.json).

```powershell
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.run_tests
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.run_tests --reverse
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests
$env:OQS_INSTALL_PATH = Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q
uv --cache-dir tmp/m4-uv-cache pip check --python .venv-m1-clean/Scripts/python.exe
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.audit_tls
```

| Retained output | Final result |
|---|---|
| [Normal](evidence/m4/tls/normal.txt) | 85 passed, 91.35 s; zero skips/warnings |
| [Reverse](evidence/m4/tls/reverse.txt) | 85 passed, 90.53 s; zero skips/warnings |
| [M3 regression](evidence/m4/tls/m3.txt) | 54 passed, 12.56 s; zero skips/warnings |
| [Legacy](evidence/m4/tls/legacy.txt) | 37 passed, 5 existing datetime warnings, 1.94 s; zero skips |
| [Dependencies](evidence/m4/tls/dependencies.txt) | 47 packages compatible, 26 ms |
| [Source/inputs/outputs](evidence/m4/tls/input-hashes.json) | Same distinct normal/reverse cases; explicit changed M3 file; historical evidence and helper hashes preserved |

Retained output only normalizes line endings and redacts local workspace/user-profile
path prefixes when present; commands, observations and result counts are preserved.
Normal/reverse outputs retain secret-free `SOCKET_OBSERVATION` and
`PROCESS_SOCKET_OBSERVATION` summaries. They label actual socket/TLS behavior;
resolvers/identities remain synthetic. Tests create disposable CA/server keys,
never commit them or print them. Real Windows credential entries are temporary
and cleaned up. Provider private material stays in the established private pipe/
encrypted vault boundary. No existing credential cache was opened.

Development runs exposed seven Windows buffered-read cancellation failures
(71 other cases passed). After bounded polling reads, the 40 focused socket/TLS
cases passed in 47.84 s, and four panel cases passed in 7.44 s. Expanded 84-case
normal/reverse runs passed; final review then added deterministic worker-join
cleanup and its fifth panel case (5 passed in 7.59 s). The final 85-case snapshot
is the one retained above; earlier successful runs are not attributed to that
later code. A subsequent 85-case reverse run exposed an intermittent blocking TLS
handshake cancellation failure (1 failed, 84 passed, 88.40 s). The owner thread now
uses nonblocking handshake/readiness polling; cross-thread shutdown alone is not
its cancellation guarantee. The unchanged 18 stage timeout/cancellation cases then
passed (27.23 s, 22 deselected), followed by both full orders on the corrected source.
The failed pre-fix run and focused result are retained separately as
[pre-fix reverse](evidence/m4/tls/reverse-before-handshake-fix.txt) and
[focused stage checks](evidence/m4/tls/handshake-focused.txt). The focused command was:
`./.venv-m1-clean/Scripts/python.exe -m pytest experiments/m4/tests/test_smtp.py -q -k real_stage_deadline_and_cancellation --basetemp=tmp/m4-handshake-focused`.
Final normal/reverse commands above were rerun after this fix and the explicit
AccountUnit sender type declaration. Native warning/panic/constant-time and historical-provider/fixture
limitations remain unchanged; functional success is not independent review.

## Workflows and next step

See [M4 instructions](../../experiments/m4/README.md) for the opt-in panel and
headless Accepted/Failed/Unknown/retry workflows. No default startup changes.
The requested controlled SMTP/TLS and bounded development integration is complete.
Remaining full M4 work is deliberate integration of these durable services at the
eventual compose boundary; legacy F07 remains explicitly open. The next bounded
development task is to agree that opt-in compose-routing scope. Live Google
test-account acceptance can proceed separately when explicitly provisioned; it
does not block authorized development under ADR 004/005. Independent review stays
required before production/security release. M5 MIME integration is a separately authorized milestone, not started here.
No real external mail, user migration, push, merge, deployment or release.
