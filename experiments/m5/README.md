# M5 protected compose/open development

Explicit disposable Windows development path. No default startup changes, external
mail, real credentials, existing credential caches or user-data migration. Read
[ADR 006](../../docs/adrs/006-m5-development-message-boundary.md) and the
[qualification record](../../docs/operations/m5-validation.md) before interpreting
the results as compatibility or security approval.

## Build and validate

Use the M1 locked Python environment and M2's pinned Rust/native prerequisites.
`build-provider.ps1` builds offline and locked against the existing audited static
OpenSSL input; it does not fetch dependencies or install a system library. The new
helper is `tmp/m2/target/debug/qumail-m5-provider.exe`; the M3 binary is preserved.

```powershell
./experiments/m5/build-provider.ps1
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.run_tests
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.run_tests --reverse
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.run_tests
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests
$env:OQS_INSTALL_PATH = Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q
```

Normal and reverse runs verify the same distinct Python test identities and reject
skips. Separate native tests exercise independent multi-recipient/archive exchanges,
forbidden algorithms, unsigned/truncated messages and native receive limits.
No generated keys, certificate private files, vaults or binaries are committed.

## Disposable compose/open workflow

```powershell
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.demo --loopback
```

The fixture creates sender, recipient and second recipient with separate keys in
disposable Windows secure storage and a disposable encrypted vault. Its contact
pins and OAuth identities are explicitly synthetic. The server binds an ephemeral
loopback port with a disposable test CA; nothing is added to system trust.

1. Keep the sender selected; fill To, Cc, Subject and Body. Bcc is unavailable.
   The checked archive option adds the sender as a cryptographic recipient.
2. Save draft, then Prepare. Both are worker operations. Prepared means the entire
   signed/encrypted PGP/MIME message is durably stored before SMTP is possible.
3. Inspect, then Submit loopback. Accepted means the fixture server accepted DATA,
   not recipient delivery. Receipt export is separate and contains status only.
4. Select a recipient and Open copy. Select the sender and Open copy to exercise
   actual archive decryption. This opens the persisted ciphertext copy; it is not
   an IMAP receive claim. Server payload hashes establish transport byte identity.
5. Lock/switch/cancel clears content and prevents stale worker publication. Select
   or unlock again after cancellation. Closing joins workers before deleting the
   disposable vault and OS credential entry.

Use `--scenario auth-reject` or `--scenario final-loss` to see Failed or Unknown.
Recover never resends. Retry requires explicit duplicate-risk confirmation and
returns to Prepared; Submit is a separate action. An unchanged rejecting fixture
continues to reject. Drafts/operations in this demo are intentionally deleted on exit.

For automated end-to-end scenarios:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.demo --loopback --smoke
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.demo --loopback --smoke --scenario auth-reject
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.demo --loopback --smoke --scenario final-loss
```

Smoke runs authorize retry explicitly and change the fixture to success; output
contains only outcomes/counts, never message content. A plain-text test view shows
verified results and identity/replay warnings. There is no HTML, inbox sync,
attachment execution or automatic action. Attachments and reply references are
supported by the typed service/tests; their full user workflow belongs to M6.

## Qualified experimental limits

| Boundary | Enforced limit |
|---|---|
| Body | 8 KiB UTF-8 |
| Attachments | Four; 16 KiB aggregate decoded bytes; safe ASCII names <=64 characters |
| Intended recipients | Three total To/Cc; Bcc rejected; up to four encryption packets including sender archive |
| Inner MIME | 64 KiB; text/plain UTF-8/base64, optionally one multipart/mixed containing body plus attachments |
| MIME structure | Six parts, depth two, 8 KiB aggregate headers, lines <=998 bytes; duplicate controls rejected |
| Outer PGP/MIME | 256 KiB; exactly two parts; provider ASCII armor <=192 KiB |
| Native / IPC | 64 KiB accepted plaintext; inherited decoder reads at most 1 MiB before M5 output cap; 8 MiB JSON pipe cap; explicit 8 MiB stack |
| Work | 30-second shared operation deadline for helper/identity inspection; cancellation polling; existing SQLite busy waits can add up to five seconds per contended DB acquisition before a deadline recheck |
| Persistence | Existing 8 MiB authenticated account aggregate, 16 outbox operations, three attempts; 256 replay identities, then fail closed |

Limits are combined constraints, not a promise that every maximum fits an account
with unlimited key history. No §42 25 MiB message/15 MiB attachment claim is made.
Native heap/CPU instruction caps, Linux execution and production packaging remain
unqualified. Signature validity is distinct from verified identity; outer fields
do not override protected fields. Exact replay/conflict detection survives reopen;
backup rollback cannot be ruled out.

The experimental marker is `QM-OPENPGP-PQ-1-EXPERIMENT-M5`. Algorithm/provider inputs
are unchanged from the provisional M2/M3 profile. Real independent mail clients
and independent expert approval remain gates. Legacy F07 remains open at unchanged
legacy entry points; the new opt-in compose path demonstrates durable ordering.
