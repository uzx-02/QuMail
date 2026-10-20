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
