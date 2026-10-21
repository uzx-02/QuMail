# Current Windows M6 assessment — 2026-10-21

**M6 PARTIAL, with one remaining Windows engineering blocker.** Continued from
actual clean tracked `6f4d5fcb62ae0fbae7be68739e0242a4468d750d`. Bounded DNS/OAuth,
TCP/TLS cancellation, shutdown cleanup and keyboard/busy/error corrections pass
65 M6 tests (54.93 s), including 13 focused tests (16.78 s); affected M3 regression
54 passes (11.19 s). Zero skips/warnings. Tests are local Windows fixtures, not Google.

Settings native/vault work, including enrollment/restore commits after OAuth, is
still synchronous. Its finite 30 s helper and 5 s SQLite waits do not establish
responsive UI/<1 s cancellation. This is a locally actionable engineering gap,
separate from live Google and deferred independent/human review. Next: stage slow
Settings work safely off UI with generation/transaction/recovery-secret tests.

See the [current acceptance table, exact commands and limits](m6-windows-validation.md),
[hash-identified evidence](evidence/m6-windows/input-hashes.json) and the
[single live Google checklist](m6-google-acceptance.md). Previous assessments below
remain historical; this entry supersedes their connection/usability status.

## Preserved assessment at 6f4d5fc

# M6 integrated mail workflow continuation — 2026-10-21

**Bounded workflow engineering implemented and locally validated; full M6 PARTIAL.**
Actual starting branch `codex/m6-gmail-inbox`, HEAD
`2c0eed635bb66740f8365ee89b81e04470a7f515`. Initial tracked tree was clean; the
untracked PDF, user launcher and reviewer draft were preserved/excluded. M1 hosted
baseline and M2 committed proof remain as recorded below; neither was reopened.
ADR 004/006 development exceptions remain; independent review is not fabricated.

## Current acceptance assessment

| Requested M6 criterion / specification reference | Executable evidence | Assessment / remaining gate |
|---|---|---|
| Account-scoped compose/outbox; §54 M6, T07/T12 | Real encrypted draft save/edit, prepare, frozen SMTP digest, durable Accepted; Qt compose/archive integration and confirmed UI submission | Pass locally; no fixture controller in application path |
| Current recipient policy; QM-MAIL-007 / QM-UX-002 | Changed contact blocks prepare/retry; all recipients validated by M5; explicit Bcc-disabled UI | Pass for qualified 3-recipient profile; existing M5 multi-recipient/Bcc regressions pass |
| Cancellation, retry and interrupted submission; T07/T12 | Real stalled final SMTP response cancelled/locked/switched in <1 s after connection; original account records Unknown; duplicate acknowledgment, identical retry bytes; synthetic crash-state recovery | Pass for tested phases; synthetic intent injection is not a new process-crash proof (M4 regressions retain that evidence) |
| Separately configured Gmail adapter; explicit provider configuration | Fixed endpoint asserted; actual STARTTLS/XOAUTH2 with Gmail-name fixture certificate, redirected loopback sockets; success/lost-final/rejection/challenge; wrong-host/expired/untrusted/missing-TLS reject before AUTH | Locally qualified; live Google OAuth/IMAP/SMTP acceptance pending. No external sends |
| Safe attachments; QM-MAIL-006 / QM-PERF-001 | Real signed/encrypted attachment round trip and sender-archive export; size/aggregate limits; traversal/ADS/device/trailing-dot paths, overwrite and unverified export reject; failed persistence removes partial output | Pass at existing M5 small limits; no automatic open/execute. Larger release-scale limits unqualified |
| Reply/forward; §43 / T07 | Real new protected reply verifies inner reference; forward re-prepares attachments with explicit recipients and no endorsement claim; conventional recipient confirmation and unverified label; changed current key blocks new preparation | Pass bounded workflows; reply-all, HTML, conventional attachment processing excluded |
| Basic threading; §43 / §54 M6 | Protected thread root derived only from verified identity's inner references; Qt groups opened page by that root; conventional outer forged references cannot establish group | Pass page-local identification/grouping; not a durable full-conversation index |
| Header-first / UID / unread invariants; QM-MAIL-005 / T07 | Retained real TLS IMAP tests: account/INBOX/UIDVALIDITY/UID, rollover/deletion/paging, BODY.PEEK and explicit read/unread | Pass locally; no sync/open automatically marks Seen |
| Signer resolution and safe display; QM-UX-001 / T12 | Local certificate hint still goes through real M5 verification; malformed modern message fails; unverified conventional plain text; late inbox/composer results suppressed | Pass bounded rendering; full usable-security/accessibility walkthrough pending |
| Account switch/lock/cancel; T12 / QM-PERF-002 | Two-account isolation, delayed UI completion, actual in-flight SMTP cancellation, cleared compose/attachments/display | Pass tested interactions; initial DNS/connect, OAuth HTTP and SQLite phases do not establish universal <1 s cancellation |
| Metadata disclosure/documentation; QM-PRIV-002/003 | UI labels identity/signature/transport separately; guide documents routing/timing/size and exported plaintext; bounded vault metadata | Implemented; human walkthrough remains an M6 acceptance gate |

Implementation: `mailbox_client/workflows.py`, `smtp.py`, extended display/opening
model, `ui/mail_actions.py` and mailbox controls. M4 changes are a shared SMTP engine,
empty OAuth-challenge response, optional offline transport plus explicit external
opt-in, and narrowly extended test fixture. M3/M5 cryptography, account/session,
legacy readers, dependencies, helpers and native library are unchanged. No migration.
See [ADR 008](../adrs/008-m6-mail-workflows.md) and [guide](m6-gmail-inbox.md).

## Exact executed commands and retained outputs

From repository root, existing environment; no downloads, upgrades or native rebuild:

```powershell
./.venv-m1-clean/Scripts/python.exe -m experiments.m6.run_tests *> tmp/m6-workflows/normal.txt
./.venv-m1-clean/Scripts/python.exe -m experiments.m6.run_tests --reverse *> tmp/m6-workflows/reverse.txt
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.run_tests *> tmp/m6-workflows/m4.txt
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.run_tests *> tmp/m6-workflows/m5.txt
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests *> tmp/m6-workflows/m3.txt
$env:OQS_INSTALL_PATH=Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q *> tmp/m6-workflows/legacy.txt
./.venv-m1-clean/Scripts/python.exe -m compileall -q mailbox_client ui/mail_actions.py ui/mailbox_window.py experiments/m6
./.venv-m1-clean/Scripts/python.exe -m experiments.m6.audit_workflows > docs/operations/evidence/m6-workflows/input-hashes.json
```

| Retained output | Exact result |
|---|---|
| [M6 normal](evidence/m6-workflows/normal.txt) | 52 passed in 51.75 s; 52 distinct identities; zero skips/warnings |
| [M6 reverse](evidence/m6-workflows/reverse.txt) | Same 52 passed in 58.97 s; exact reverse identity order; zero skips/warnings |
| [M4 regression](evidence/m6-workflows/m4.txt) | 85 passed in 98.96 s; zero skips/warnings |
| [M5 regression](evidence/m6-workflows/m5.txt) | 55 passed in 95.89 s; zero skips/warnings |
| [M3 regression](evidence/m6-workflows/m3.txt) | 54 passed in 13.23 s; zero skips/warnings |
| [Legacy checkpoint](evidence/m6-workflows/legacy.txt) | 37 passed, 5 existing datetime deprecation warnings in 3.26 s; zero skips |

An earlier 48-pass development run is retained as `initial-48.txt`, before final
forward/export/UI refinements. A later development run had 50 passes/1 failure
(`initial-order-assumption.txt`): the assertion assumed a newly saved operation was
the last dictionary row. Authenticated serialization sorts opaque IDs. Tests now
select/assert the exact operation ID; no assertion about delivery state was weakened.
Final runs above supersede those development results.

Runtime: Windows 11 build 26200 x64; CPython 3.12.14 MSC 1944; PyQt6 6.10.2;
pytest 8.4.2; google-auth 2.49.1; google-auth-oauthlib 1.3.0; SQLite 3.53.1.
Python TLS reports OpenSSL 3.5.8 (25 Aug 2026). The unchanged cryptographic helper
uses the separately pinned Sequoia 2.4.1 / native OpenSSL 3.5.9 research build;
these are distinct TLS/native libraries. Original helper/lock hashes are retained.

Results describe the **modified working-tree input hashes**, not unchanged parent
HEAD. [Manifest](evidence/m6-workflows/input-hashes.json) records source, locks,
helpers, environment, docs and outputs. Its audit verifies preserved baseline paths
and the exact reverse test identity set. Audit/docs were completed after execution;
they are not additional cryptographic tests. The local commit receipt identifies
which commit contains this hash-identified proof. `audit_snapshot.py` still describes
the original inbox checkpoint; use `audit_workflows.py` for this continuation.

All protocol connections were local controlled fixtures; credentials/enrollment
identities are synthetic, vault/Windows secure storage and cryptography are real.
Delayed UI workers and crash-state injection are explicitly synthetic. No authentic
Gmail inbox data was substituted by a sample application inbox. An empty locked UI
was also rendered offscreen with installed Segoe UI (1000x720 mailbox, 900x800
compose); that is layout inspection, not native interactive or accessibility approval.

## Remaining M6 and release gates

Finish live Google test-account acceptance when explicitly provisioned/authorized,
including refresh and controlled submission; qualify initial-connection cancellation
limits, supported desktop/platform behavior and usable-security/accessibility.
Independent MIME-peer qualification and cryptographic/enrollment/recovery review
remain pre-production gates under existing ADRs. Qualified small limits, INBOX-only
manual paging, page-local threads and 16 retained outbox operations are explicit
engineering boundaries, not complete general-client claims. Larger limits require
separate performance/parser qualification; no silent budget expansion here.

Original-provider reproduction/historical compatibility, native warning assurance,
project/provider/Qt licensing, restricted-scope distribution and production/release
approval remain separate gates. No M7/M8, external mail, migration, push or release.
Next bounded work: M6 usable-security/accessibility and connection-phase/platform
qualification; live Google acceptance only when a test configuration is provisioned
and external sending is separately authorized. No repeated credential request.

## Preserved inbox checkpoint validation (2c0eed6)

# M6 Gmail-first slice validation

2026-10-20, Asia/Calcutta. **Bounded Gmail-first engineering slice implemented and
locally tested; full M6 PARTIAL. Live Google acceptance not executed.**
See [ADR 007](../adrs/007-m6-gmail-mailbox-slice.md) and
[setup/limits](m6-gmail-inbox.md). No M7/M8, real sending, cloud changes or migration.

## Verified handoff

- Actual parent `b96abc45d975c208d37c03bed80e87f6b68c04c2`, on the preserved
  `codex/m5-protected-compose` branch. New branch `codex/m6-gmail-inbox`.
  Its only changes from `219dc97…` were the presentation panel and demo guide;
  no subsequent tracked changes existed. The untracked launcher, reference PDF
  and reviewer request remain excluded and untouched.
- M1 retained run JSON confirms head `023c941ec2ef284f6be28b5a9605f1dca9c28787`,
  completed/success and both platform jobs successful. Both retained job outputs
  contain three full 37-pass orders. This verifies existing evidence, not a rerun:
  [run 37128055379](https://github.com/uzx-02/QuMail/actions/runs/37128055379).
  Baseline M1 completion remains intact.
- M2 proof commit `1fc4e55f09e173cec7634d0b2dc776097b552063` has parent `5880dd4…`.
  The latter is not the engineering-proof checkpoint. Existing review gates persist.
- M3/M4/M5 experiment source, core account-session adapter, provider inputs/helpers,
  native library and earlier evidence are unchanged from the parent. M5's historical
  source manifest continues to describe its own original snapshot; it is not
  rewritten to pretend the later presentation panel was originally tested.

## Acceptance table

| Bounded criterion / canonical reference | Actual executable evidence | Decision |
|---|---|---|
| Account-scoped provider retrieval; §§43/47, T07 | Real local TLS IMAP/XOAUTH2 wire exchange, two synthetic Google-account contexts using the same UID, separate encrypted header cache | Pass locally; Gmail live acceptance pending |
| Header-first listing/on-demand body; §43 M6 | EXAMINE + header-only UID FETCH; UI test verifies selection does not fetch; explicit Open issues PEEK full fetch | Pass; manual INBOX only |
| Mailbox identity; T07/I13 | UIDVALIDITY rollover rejects old reference and replaces cache; deleted UID rejected; paginated windows return 35 unique UIDs over two pages; account mismatch rejected before fetch | Pass scoped to INBOX |
| Read/unread semantics | Refresh/open leave server Seen false; explicit writable STORE toggles then confirms; no CLOSE/EXPUNGE; UI mirrors flags without implicit STORE | Pass; interrupted STORE outcome requires refresh |
| Safe display/trust separation; T12/QM-MAIL-006/QM-UX-001 | HTML-only placeholder, literal markup in QPlainTextEdit, unverified conventional status; explicit signer selection; real M5 verification via TLS retrieval; damaged modern ciphertext rejected without fallback | Pass for plain-text slice; attachment/reply/forward work deferred |
| Session generation/cancellation; I13/T12 | Delayed workers discarded on account switch, selection change, lock and cancel; real blocked TLS FETCH cancellation under one second and no cache commit; cancelled refresh cannot install token | Pass tested phase; DNS/connect/OAuth timing limitations explicit |
| Google mail scope/identity | Synthetic authorization checks exact additional scope and rejects missing grant; identity-only token cannot access mailbox; existing real-library M3 verification/refresh tests rerun | Pass controlled tests; synthetic claims are not live acceptance |
| Resource bounds; T15/I18 | Header/message caps, pre-allocation literal rejection, 30-row paging, real oversized fetch rejection; inherited M5 budgets and encrypted vault limits | Pass stated limits; no full product-size/performance benchmark claim |
| Removal of presentation behavior | Application import check excludes M5 demo/presentation panel and SMTP fixture; no sample rows, shared prepared-copy opening or fabricated account enrollment in inbox | Pass; historical fixture harness retained separately |
| Review/platform/product completion; §54 M6 | No independent usability/accessibility sign-off, Linux run or live Google acceptance | Pending; full M6 remains PARTIAL, not production approved |

## Commands and results

Existing Windows 11 build 26200 x64 environment, Python 3.12.14, PyQt6 6.10.2,
pytest 8.4.2. No dependency upgrade/download, native rebuild or new dependency.
OpenPGP still uses Sequoia 2.4.1/OpenSSL 3.5.9, with preserved rPGP 0.21.0 peer;
Python's TLS backend is separately OpenSSL 3.5.8. Source/helper hashes and exact
environment are in [input-hashes.json](evidence/m6/input-hashes.json). Results belong
to that working-tree snapshot, not unchanged parent HEAD. The local Git receipt
identifies the commit containing it; docs/audit were completed after runtime tests.

Executed from repository root:

```powershell
./.venv-m1-clean/Scripts/python.exe -m experiments.m6.run_tests *> tmp/m6-normal.log
./.venv-m1-clean/Scripts/python.exe -m experiments.m6.run_tests --reverse *> tmp/m6-reverse.log
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.run_tests *> tmp/m6-m5-regression.log
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.run_tests *> tmp/m6-m4-regression.log
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests *> tmp/m6-m3-regression.log
$env:OQS_INSTALL_PATH=Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q *> tmp/m6-legacy-regression.log
```

| Retained result | Outcome |
|---|---|
| [M6 normal](evidence/m6/normal.txt) | 21 passed, 9.76 s; zero skips/warnings |
| [M6 reverse](evidence/m6/reverse.txt) | Same 21 distinct tests, inverse order; 21 passed, 8.61 s; zero skips/warnings |
| [M5 checkpoint](evidence/m6/m5.txt) | 55 passed, 87.09 s; zero skips/warnings, includes the b96abc4 frontend controller |
| [M4 checkpoint](evidence/m6/m4.txt) | 85 passed, 92.33 s; zero skips/warnings |
| [M3 affected checkpoint](evidence/m6/m3.txt) | 54 passed, 11.72 s; zero skips/warnings |
| [Legacy checkpoint](evidence/m6/legacy.txt) | 37 passed, 2.30 s; five existing datetime deprecations, zero skips |

Additional affected modules passed py_compile. Application import check confirmed
no presentation/mail-server fixture imports. Prior helper/native hashes matched.
Retained output replaces local workspace/user-path prefixes and normalizes line
endings; tokens, keys, credential caches, generated binaries and message bodies
are excluded. Fixture literal strings in test source are synthetic, not user mail.

Initial focused run: 16 passed / 1 failed (19.10 s), retained in
[initial-cancellation.txt](evidence/m6/initial-cancellation.txt). Cross-thread socket
shutdown did not interrupt a Windows TLS read within the test's timeout. Replaced
post-connect I/O with nonblocking read/write cancellation polling, keeping validated
TLS and assertions. A corrected 17-case focused run passed; later UI/scope/default
MIME cases expanded this to the final 21. Failure evidence is historical, not
attributed to final source. No tests were weakened or skipped to obtain a pass.

## Evidence distinctions and next task

Real: local TLS sockets/hostname and CA checks, IMAP commands, disposable Windows
secure storage/encrypted vault, generated M5 keys and cryptographic verification.
Controlled/synthetic: IMAP mailbox contents and account credentials, OAuth claim
fixtures, delayed worker responses. No external Gmail mailbox was accessed; no
provisioned test-client/account configuration was supplied or discovered elsewhere.
Local tests cannot prove Google's consent, refresh policy or server compatibility.

Exact next bounded task: provision an authorized Google test client/account and
follow the live acceptance checklist in the setup guide, recording results without
private data. Independent protocol/enrollment/recovery review remains required
before production/security release under the existing development exceptions.
Full M6 attachment/reply/forward/accessibility work and other-platform validation
remain separately scoped. Restricted-scope distribution policy, provider/project/Qt
licensing and historical compatibility gates remain unchanged. No M7/M8 work.
