# M5 protected-message and compose validation

Date: 2026-10-14 (Asia/Calcutta); development began 2026-10-12.
**Bounded M5 development engineering complete; full M5 PARTIAL.**
This is an opt-in disposable Windows application path, not production enablement.
[ADR 006](../adrs/006-m5-development-message-boundary.md) preserves the owner's
development-ordering exception and the later live-provider/review/release gates.
No independent approval is claimed. M6 has not begun.

## Checkpoint and attribution

Verified parent: `b00693cbaba92037b3dec8c9e35d866650a5018f` on preserved branch
`codex/m4-durable-outbox`; new local branch `codex/m5-protected-compose`.
Initial tracked tree was clean. The reference PDF and private reviewer-request
draft were untracked and remain excluded. M1/M2/M3/M4 branch references, source,
locks, evidence, canonical specification, legacy readers and data are preserved.

Results below belong to the M5 working-tree source in
[input-hashes.json](evidence/m5/input-hashes.json), not unchanged parent HEAD.
The local commit receipt identifies the checkpoint containing those exact bytes.
Runtime source was unchanged between the final native/Python runs and hash audit;
the audit script, README and decision documentation were completed afterward.
The manifest hashes every M5 source/lock/script, reused M3 provider source, M2
inputs, account-session adapter, canonical specification, retained output and
current decision document. It also records the actual M5 helper binary hash,
preserved M3 helper/native library hashes and environment. Binaries are not committed.
`python -m experiments.m5.audit_snapshot` checks earlier manifests and that the
new lock/manifest differ from M3 only in the root package name.

## Acceptance and requirement traceability

| Actual M5 criterion / reference | Executable evidence and limits | Assessment / remaining action |
|---|---|---|
| Standard signed/encrypted preparation and decoding; §§41–43, §54 M5, QM-MAIL-002 | `test_multi_recipient_archive_loopback_retry_and_replay`, two independent exchange cases, native tests: standard packets in two-part armored RFC 3156; RFC 9788 direct protected MIME | Satisfied for experimental path; no production profile approval |
| Remote recipient decrypts without sender secrets; §54 M5, QM-INT-001 | Separate generated sender/recipient/CC keys; receiver gets own secret and sender public certificate only; sender encryption receives recipient public material only; Sequoia→rPGP and reverse, all three decryptors | Satisfied as independent crypto exchange; shared MIME/armor/policy wrappers explicitly not independent mail-client evidence |
| Protected metadata verified; §42, QM-MAIL-003, I07/I08 | Body/attachments/references round trip; false From/unintended recipient/unknown marker rejected; authenticated malformed header corpus; outer Subject and injected Cc discrepancies retained separately | Satisfied for declared narrow profile; protocol/parser review outstanding |
| Recipient trust/capabilities and archive; §42, T04, owner scope | Every-recipient missing/unverified/changed/expired/revoked cases block whole draft; real archive decryption and explicit no-archive failure; unchanged M3 current-certificate checks; Bcc rejected | Satisfied for local verified fixture trust; no real human enrollment or online revocation freshness claim |
| Structured verified/unverified result; §54 M5, QM-CRYPTO-005 | Frozen `OpenedMessage`; signature, identity, mismatch, replay fields separate; wrong keys/signers, tamper/truncation, malformed/forbidden suite/unsigned messages, mocked incomplete verification return no message | Satisfied; unknown signer stays unverified. Mocked response tests prove adapter behavior only |
| Persistent replay/conflict and legacy isolation; §42, T05 | Reopen yields duplicate; same protected identity/different content yields conflict without overwriting original; replay-cap and real SQLite commit denial fail closed; legacy classifier preserves exact bytes with unverified label | Satisfied bounded engineering. Backup includes replay map by source inspection, not a new M5 restore execution. Whole-backup rollback remains residual risk; no notifications/actions exist here |
| Durable complete envelope before SMTP, identical retry; §§43/50, QM-MAIL-004, I09 | Real loopback TLS DATA hash matches stored envelope twice; final response loss→Unknown→explicit retry→Accepted; receipt failure preserves Accepted; 85 unchanged M4 regressions | Satisfied in new compose. Legacy F07 at unchanged entry points remains open; no global fix claim |
| Controlled compose integration; owner scope, T07/T09 | Three GUI smoke scenarios: Accepted, Failed and Unknown; worker heartbeat/stale switch/lock/cancel tests; coherent M3 lease; no default import | Satisfied opt-in development. Disposable view reads persisted copy, not IMAP; M6 inbox/rendering not implemented |
| Malformed inputs and limits; §42, T01/T02/T05, I18 | Duplicate parts/parameters/control/profile, unknown critical field, depth/parts/headers/wire/body/attachment/recipient bounds; native five-recipient and oversized-inner rejection; cancellation and persistent-history capacity | Satisfied within published smaller limits, not §42 proposed product sizes or OS-level heap containment; ongoing adversarial/fuzz and other-platform qualification remains |
| No custom TQR outbound production path; §54 M5 | M5 source imports no TQR, simulator or portal; provider owns standard serialization; production write profile remains disabled; legacy characterization unchanged | Satisfied isolation for this authorized path. Full application migration/default routing is not done or silently enabled |
| Email protocol/parser review; §54 M5 | Source and retained corpus ready for review | Pending independent review under ADR 006 before production/security release; not a recurring development stop |
| Wire documentation, compatibility and dual-read boundary; §54 M5 | This profile table, README, ADR and read-only classifier; no in-place conversion | Satisfied scoped documentation/classification. Existing legacy readers retained, not rewired into a new production decoder |

Full M5 is not marked complete: the canonical milestone describes shipping the
new profile, and the current result is the explicitly authorized experimental
integration with provisional upstream milestone approvals and pending protocol
review. Independent mail-client interoperability is unexecuted; it is not inferred
from independent cryptographic processing, nor silently added as a new universal
M5 acceptance rule. Live Google, review and licensing are separately tracked gates.

## Exact wire profile and compatibility

| Element | Frozen experimental choice / tested boundary |
|---|---|
| Application marker | `QM-OPENPGP-PQ-1-EXPERIMENT-M5`, signed inner field; unknown profile rejects |
| Provider policy | Existing `M2-EXPERIMENT-RFC9980-AES256-GCM`; no negotiation/downgrade/fallback |
| Certificate | Unchanged M3 v6 alg-30 certification-only root, separate v6 alg-30 signing and alg-35 encryption subkeys |
| Signature / encryption | ML-DSA-65+Ed25519, v6/SHA-512; ML-KEM-768+X25519, v6 PKESKs; SEIPDv2/AES-256/GCM, 4096-byte chunks; no compression |
| Outer | RFC 3156 multipart/encrypted, protocol application/pgp-encrypted; Version: 1 control and 7bit application/octet-stream provider ASCII armor |
| Signed payload | RFC 9788 `hp="cipher"` on direct text/plain UTF-8/base64 or multipart/mixed root; no message/rfc822 intermediary |
| Protected fields | From, To/Cc, Subject, Date, stable operation-derived Message-ID, experimental marker, archive authorization, optional In-Reply-To/References, attachment name/type/bytes |
| Exposed fields / HCP | Bare routing From/To/Cc, Date, Message-ID; generic Subject `Encrypted message`; profile/archive/references removed outside; repeated signed HP-Outer snapshots for deliberately exposed fields. Explicit experimental HCP, not the exact registered hcp_baseline transformation |
| Archive and Bcc | Optional sender encryption recipient, not extra SMTP recipient; Bcc unavailable; no hidden-recipient privacy claim |
| Replay | Account scope + signer root + protected Message-ID; SHA-256 exact authenticated canonical MIME; first digest retained; duplicate/conflict explicit |
| Historical/legacy | No conversion; original bytes and unverified legacy classification; no modern-failure fallback. Candidate modern signer currently must pass M3 current-certificate inspection; time-aware expired/revoked historical signer policy unqualified |

Both independent directions use **the same M3-generated certificate/subkey model**.
Sequoia/OpenSSL produces packets decrypted and signature-verified by rPGP; rPGP
produces packets decrypted and signature-verified by Sequoia/OpenSSL. Each direction
opens at two distinct intended recipients and at the sender archival key. The
shared MIME constructor/parser and Sequoia armor wrapper prevent interpreting this
as independent MIME implementation or mail-client rendering qualification.
M2's component-specific composite failure/vector evidence is preserved; M5 does
not relabel it as a newly executed component-specific mutation suite.

## Primary standards and errata checked

Checked against current official sources during this work, most recently
2026-10-14. [RFC 3156 §§4/6.2](https://www.rfc-editor.org/rfc/rfc3156.html) specifies
armored PGP/MIME and combined sign/encrypt. [RFC 9788](https://www.rfc-editor.org/rfc/rfc9788.html)
and its [publication record](https://www.rfc-editor.org/info/rfc9788/) establish
the direct protected MIME payload, hp and HP-Outer semantics (Proposed Standard,
August 2025). The source does not treat protected headers as an arbitrary nested
message or claim every stricter local parser restriction is an RFC requirement.

[RFC 9580](https://www.rfc-editor.org/rfc/rfc9580.html) and
[RFC 9980](https://www.rfc-editor.org/info/rfc9980/) remain the packet/composite
references. [RFC 3156 errata](https://errata.rfc-editor.org/search/?rfc_number=3156)
includes rejected editorial 3443. [RFC 9788 query](https://errata.rfc-editor.org/search/?rfc_number=9788)
returned no matching errata (HTTP 200; retained query result).
[RFC 9980 errata](https://errata.rfc-editor.org/search/?rfc_number=9980) 9023 is
Reported, not a verified local algorithm change. No combiner was changed.
[RFC 9580 errata](https://errata.rfc-editor.org/search/?rfc_number=9580) includes
verified native-octet/MPI clarifications 8454/8465/8466 and editorial 8432/9094;
reported 8814 compression wording and 8847 v3 X25519 PKESK table do not authorize
compression or v3 packets in this profile. Held 8449 concerns bare-address UserIDs.
These are source assessments, not evidence of exhaustive provider conformance.

## Environment, exact commands and retained results

Windows 11 build 26200 x64; Python 3.12.14 MSC v1944, SQLite 3.53.1;
pytest 8.4.2, PyQt6 6.10.2, cryptography 50.0.2. Rust 1.99.0
(`b940084d7`, 2026-09-28), Cargo 1.99.0 (`5f94df478`, 2026-08-27),
`x86_64-pc-windows-msvc`. New helper debug build; dependency graph unchanged.

Sequoia 2.4.1 (`0b0c8c7f038b829de2da0d28a822941d8600f3ee`, crypto-openssl,
default features off); rPGP 0.21.0 (`c2b192e52b2e7f99777196539ea79b37f1f9ff30`,
pqc, defaults off); native OpenSSL 3.5.9 (`45e844fa2a14ec92d146bd8f5778ac130b6625fb`).
Exact source archives/checksums in unchanged [M2 inputs](../../experiments/m2/inputs.json).
OpenSSL flags: `VC-WIN64A no-shared no-tests no-module no-comp no-asm --libdir=lib`;
`OPENSSL_STATIC=1`, `OPENSSL_NO_VENDOR=1`. This run reuses the audited static library,
not a fresh native rebuild. SMTP Python TLS is separately OpenSSL 3.5.8.
Legacy tests use binding 0.16.0.1/native 0.16.0 research lane, not unavailable 0.14.1.

From repository root in PowerShell, final commands (logs redirect as shown):

```powershell
./experiments/m5/build-provider.ps1 *> tmp/m5-native-qualified.log
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.run_tests *> tmp/m5-normal-qualified.log
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.run_tests --reverse *> tmp/m5-reverse-qualified.log
./.venv-m1-clean/Scripts/python.exe -m experiments.m4.run_tests *> tmp/m5-m4-regression.log
./.venv-m1-clean/Scripts/python.exe -m experiments.m3.run_tests *> tmp/m5-m3-regression.log
$env:OQS_INSTALL_PATH = Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q *> tmp/m5-legacy.log
uv --cache-dir tmp/m5-uv-cache pip check --python .venv-m1-clean/Scripts/python.exe *> tmp/m5-dependencies.log
./.venv-m1-clean/Scripts/python.exe -m experiments.m5.audit_snapshot
```

Build script sets the repository-local Rust cache/native paths and invokes
`cargo build --manifest-path experiments/m5/provider/Cargo.toml --locked --offline`
and `cargo test --manifest-path experiments/m5/provider/Cargo.toml --locked --offline -- --test-threads=1`.
The Python fixtures configure offscreen Qt; the runner checks actual collected/executed
identities. It is not a static test-count estimate. M5 normal/reverse ran sequentially;
unchanged regression jobs ran independently, also sequential within their group.

| Retained output | Exact result |
|---|---|
| [native.txt](evidence/m5/native.txt) | Build 3.14 s; test build 2.92 s; 2 passed, 0 failed/ignored, 1.41 s; no compiler warnings |
| [normal.txt](evidence/m5/normal.txt) | 55 passed, 84.17 s; 55 distinct, zero skips/warnings |
| [reverse.txt](evidence/m5/reverse.txt) | Same 55 in exactly inverse order passed, 82.23 s; zero skips/warnings |
| [m4.txt](evidence/m5/m4.txt) | 85 passed, 87.20 s; zero skips/warnings |
| [m3.txt](evidence/m5/m3.txt) | 54 passed, 11.11 s; zero skips/warnings |
| [legacy.txt](evidence/m5/legacy.txt) | 37 passed, 3.10 s; five existing utcnow deprecations, zero skips |
| [dependencies.txt](evidence/m5/dependencies.txt) | 47 installed packages compatible, 182 ms |

Outputs are retained with workspace/user path prefixes replaced and line endings
normalized; no result or failure removed. Native tests ran once in harness order;
the 55-case Python suite ran in both orders. This is local Windows evidence, not
new hosted CI or Linux validation. No synthetic test is described as live OAuth.

## Failure history and assurance limits

Earlier executable interop failed while native unit tests passed. The isolated
[numeric exit diagnostic](evidence/m5/peer-diagnostic.txt) measured `0xc00000fd`
(Windows stack overflow) in both peer operations: 2 failed/24 deselected, 6.40 s.
The original 26-case run had 2 failures/24 passes. The native helper now runs on an
explicit 8 MiB worker stack; final executable tests above pass. It still fails
closed on a process failure. This does not establish constant-time behavior,
memory safety or complete heap containment.

An expanded intermediate suite had 44 passes/1 failure because the SQLite fault
fixture denied connection 1, which was the read rather than replay commit.
Targeting connection 2 now exercises actual SQLite COMMIT denial; the assertion
still requires no content result and no committed replay entry. These development
failures are retained separately from final qualified outputs; they are not
attributed to the final snapshot.

Real evidence: native crypto, generated disposable keys, Windows secure store,
authenticated SQLite vault, loopback sockets/CA/TLS, DATA digest identity and worker
generation handling. Synthetic evidence: enrolled provider identities/contact
verification and SMTP credentials/server scenarios. Mock evidence: incomplete
verification response and delayed worker signaling. Prior M2 diagnostic-provider
RNG/context-allocation and accessor audits remain distinct from this unmodified
provider build. No diagnostic patch is included in the M5 lock/helper.

The M1 42 MSVC optimization-barrier warnings and selected-provider diagnostic
categories retain their M2 dispositions. This helper build did not rebuild those
native libraries, so absence of new warnings resolves none of them. Context
allocation fallback, panic/failure boundaries and constant-time assurance questions
remain in the [M2 review package](m2-external-review.md). Functional success and
`no-asm` are not constant-time evidence or independent expert approval.

Actual budgets and reproduction/UI steps are in
[experiments/m5/README.md](../../experiments/m5/README.md). In particular 64 KiB
inner/256 KiB wire, 8 KiB body, 16 KiB aggregate attachments, six MIME parts/depth two,
three intended recipients plus archive are experimental caps. Shared 30-second
helper deadline includes public inspection; contended SQLite acquisition can add
five seconds before rechecking. Preparation crypto can hold the existing writer
transaction; network I/O does not. Native decoder first uses its inherited 1 MiB
cap, then rejects content over 64 KiB. This is bounded processing, not a hard OS
heap/CPU or 30-second whole-operation wall-time guarantee.

## Remaining gates and next bounded task

- Review the local M5 checkpoint/profile/parser corpus. Qualify a separately
  implemented RFC 9788/3156 peer against this exact experimental HCP without
  assuming shared-wrapper tests prove mail-client interoperability. Retain any
  incompatibility as evidence before changing profile semantics.
- Independent cryptographic/protocol and enrollment/recovery review remains
  deferred under ADR 004/006 until before production/security release; human
  review is not replaced by this implementation or test report.
- Live Google test-account authorization and external-provider SMTP acceptance
  remain unexecuted. They need explicit test-client/account provisioning and user
  browser completion; no existing credential caches were used.
- Linux/platform qualification, packaging/resource containment, project/provider/Qt
  distribution approval, original liboqs-python 0.14.1 artifact, authentic historical
  ciphertext and production approval retain their separate gates. No installer or
  native binary is distributed, and no project license is invented.

Legacy F07 remains open in unchanged legacy compose. The new opt-in path demonstrates
the intended durable ordering. Do not read this as permission to enable production,
start M6, migrate data or publish the branch. No push, merge, deployment or release.
