# Manual acceptance launcher correction

The reported missing-vault failure is not currently reproducible: read-only
Windows PowerShell preflight finds the existing acceptance database and validates
the explicitly supplied Desktop client. No vault contents or Windows credentials
were read; no new database or account was created. Earlier live acceptance
remains pending; the owner is performing manual tests.

Added a versioned parameterized launcher with `-CheckOnly`, explicit path errors,
Desktop-client validation and opt-in `-AllowNewVault` for intentional fresh tests.
The ignored machine-specific wrapper now delegates to it. Removed the runnable
placeholder command from the manual guide. Existing vaults require Unlock.
Validation: actual existing-path preflight passed; missing vault and missing
client rejected; explicit new-vault preflight passed without creating a file.
These are launcher-only checks; previous 163/27 regression evidence is unchanged.
No application/provider/dependency changes, authorization, sending or migration.

# Combined Google / optional relay continuation — 2026-11-01

**M7 locally qualified; live Google acceptance remains incomplete and is now
handed to the owner for manual execution.** Cloud relay deployment is explicitly
outside this workstream per the owner's 2026-10-23 direction, not an engineering
blocker. No cloud-operation/production claim or independent approval is made.

Started from actual checkpoint `8eebb5eb7834caa230795c7ca9b446c631df6247` on
`codex/m7-relay-google-acceptance`. This section describes the separately
hash-identified tested working tree; it does not attribute new results to that
unchanged parent. The local checkpoint commit containing these files identifies
the final continuation; its parent is the SHA above.

| Requirement / finding | Actual result |
|---|---|
| M7 ciphertext-only, own-audience authentication, I01 | Isolated loopback mTLS API, dedicated certificate allowlist bound to real disposable M3 account/device contexts; frozen M5 encrypted MIME only; no endpoint private keys, Gmail tokens or plaintext body/attachment in backend snapshots |
| M7 I10 / T10 lease, retry, expiry, concurrency | One initial device/request-bound lease under 128 requests in eight Windows processes; <=300-second same-lease retry; expiry after lock and before publication; ACK/restart/concurrency tested |
| M7 I12 quotas/outage/retention | Durable single-host SQLite; bounded body/headers/handlers; global/principal object/byte/tombstone caps; explicit creation, no memory fallback; consumed/expired payload removal and transparent WAL/backup limits |
| Existing endpoint boundaries | Actual provider decrypt/signature/trust/attachment/archive; tamper rejected locally without ACK; stale response suppressed; current vault trust and exact persisted bytes rechecked before upload |
| Google live findings | Real A browser/callback/token exchange reached verification; token-time rejection confirmed with fixed secret-free codes. Added bounded wait only for not-yet-valid tokens, then full verification again. No signature/expiry/nonce/audience weakening |
| Final local regressions | **163 passed in 122.39 s** (13 M7 + 96 M6 + 54 M3); exact reversed 27 relay/OAuth cases **27 passed in 29.42 s**. Same distinct IDs, zero skips/warnings; source hashes verified unchanged |
| Live acceptance | Owner reported possible A enrollment after the correction, not subsequently verified by the agent. B/refresh/IMAP/flags/three SMTP sends/decrypt/archive/attachment/reply/forward and human checks require the supplied manual sequence. No agent-executed external sends |

[Manual Google instructions](docs/operations/google-manual-acceptance.md),
[actual live attempts](docs/operations/m6-google-acceptance.md),
[M7 validation](docs/operations/m7-validation.md),
[ADR 009](docs/adrs/009-m7-local-ciphertext-relay.md),
[final hashes](docs/operations/evidence/m7/checkpoint-input-hashes.json).
The machine-specific launcher is in ignored `tmp/m7/Start-GoogleAcceptance.ps1`;
client JSON, vault, credentials and user keys remain outside the checkpoint.

M1 hosted baseline and M2 committed proof remain preserved. M6 local engineering
and existing review deferrals remain; full live/human acceptance is not complete.
M7 independent backend/identity review remains a pre-production/security-release
gate. QKD is excluded; no custom combiner or hardware results. Historical
compatibility, provider assurance, licensing and distribution gates are unchanged.
No M8, migration, paid provisioning, public deployment, push, merge or release.

## Preserved M6 checkpoint assessment

# Windows M6 Settings engineering completion — 2026-10-21

**Local Windows M6 engineering complete at the documented development scope;
full M6 remains PARTIAL pending live Google and human acceptance.** Continued from
actual clean tracked `f39bc5429658ec3009b9ce10c3f1cd39c21db3ef` on
`codex/m6-gmail-inbox`. The synchronous Settings blocker is resolved.

| Requirement | Final evidence / disposition |
|---|---|
| Settings responsiveness, QM-PERF-002 / M6 T12/T15 | Immutable owner/vault/generation requests; one worker/admission; per-worker SQLite; all widgets/publication on GUI; tested delayed native/read/SQLite phases with responsive Cancel/Lock/selection/close |
| Commit/isolation, T04/T12 | Short synchronized commit reservation, encrypted owner receipt, stale publication rejection; after-reservation cancellation reports inspectable durable effects, not rollback |
| Recovery custody, T08/T12 | In-memory preparation; explicit offline-secret acknowledgment BEFORE writing; real restore after cancellation/lock/SQLite COMMIT denial; failed transfer leaves source active; format/history/root rules preserved |
| Integration regressions | **82 M6 passed in 64.27 s; 54 M3 passed in 12.49 s; 17 focused Settings tests passed in reverse order in 7.97 s** (same 17 included in normal M6). Zero skips/warnings |
| Remaining acceptance | Live Google browser/refresh/IMAP/SMTP, human usable-security/accessibility walkthrough; independent review deferred under ADR 004/006. No production approval |

[Acceptance, exact commands and bounds](docs/operations/m6-settings-validation.md),
[final snapshot hashes and logs](docs/operations/evidence/m6-settings/input-hashes.json),
[recovery custody instructions](docs/operations/m3-recovery.md).
No known remaining local Windows engineering blocker for this bounded M6 scope.
Native calls/OS I/O may drain after immediate GUI cancellation; no universal
subsecond OS/process-exit promise. Qualified size/storage limits remain unchanged
apart from explicit bounded encrypted Settings receipts/export intents.

Next user action: supply provisioned Desktop-client JSON path, new test-vault path,
two controlled addresses and browser availability using the existing
[Google checklist](docs/operations/m6-google-acceptance.md). Sending requires separate
explicit permission; retrieval consent alone is insufficient. Earlier M1/M2/M6
checkpoints/evidence, user files, providers/dependencies and legacy data preserved.
No migration, external mail, push, merge, release, M7/M8 or production enablement.

## Preserved assessment at f39bc54

# Current Windows M6 decision — 2026-10-21

**M6 PARTIAL: connection/usability corrections validated; one local engineering
blocker remains.** Started from actual clean tracked checkpoint
`6f4d5fcb62ae0fbae7be68739e0242a4468d750d`, branch `codex/m6-gmail-inbox`.

- Bounded private DNS/OAuth workers, cancellable TCP/TLS/IMAP setup, cleanup on
  shutdown, Settings reopening/disposal, accessible names/focus, actionable errors
  and busy/outbox state controls implemented. Verification, account, frozen outbox,
  transport uncertainty and UID/PEEK guarantees retained.
- Final M6 **65 passed in 54.93 s**; focused **13 passed in 16.78 s** (subset of 65);
  affected M3 **54 passed in 11.19 s**. Zero skips/warnings. Real disposable Windows
  vault/crypto and local TLS, with synthetic OAuth clearly distinguished.
- **Engineering blocker:** synchronous Settings native/vault work, including
  enrollment/restore acceptance. Finite 30 s helper/5 s SQLite waits are not a
  responsive/subsecond UI contract. Stage work off UI with account-generation,
  transactional commit and recovery-secret guarantees; test delayed/cancelled/late
  results. This work needs neither live credentials nor independent review.
- Live Google browser/refresh/IMAP/SMTP and human usable-security/accessibility
  walkthrough remain separate gates. ADR 004/006 review deferrals, interoperability,
  historical compatibility, native assurance and licensing/release gates unchanged.

[Acceptance and evidence](docs/operations/m6-windows-validation.md),
[manifest](docs/operations/evidence/m6-windows/input-hashes.json),
[live checklist and exact user inputs](docs/operations/m6-google-acceptance.md).
M1 hosted baseline `023c941…`, M2 proof `1fc4e55…`, previous evidence, native inputs,
legacy data/readers and untracked user files preserved. No M7/M8, ports, external
mail, migration, push, merge, deployment or release. Results describe recorded
working-tree hashes; the local Git receipt identifies their checkpoint.

## Preserved prior assessment at 6f4d5fc

# Current M6 mail workflow decision — 2026-10-21

**Requested bounded workflows implemented and locally validated; full M6 PARTIAL.**
Continued from actual clean tracked HEAD `2c0eed635bb66740f8365ee89b81e04470a7f515`
on `codex/m6-gmail-inbox`. Untracked user launcher, reference PDF and reviewer draft
remain excluded. M1 COMPLETE baseline and M2 engineering checkpoint `1fc4e55…`
remain preserved; no milestone restart or independent approval claim.

| Requirement / scope | Implemented and tested |
|---|---|
| M3/M5/M4 integration, §54 M6 | Real account context/vault, encrypted draft save/edit, current-recipient validation, frozen preparation, durable outbox, explicit cancel/retry, sender archive |
| Explicit Gmail development transport | Disabled-by-default `--dev-gmail-submit`; fixed verified STARTTLS endpoint; owned mail-scoped OAuth after TLS; no passwords/identity-scope fallback; loopback fixtures remain restricted |
| Attachments, QM-MAIL-006/PERF-001 | Existing qualified limits; verified Save As; unsafe/overwrite/unverified export rejected; partial export cleaned up; never auto-open/execute |
| Reply/forward/threading, §43 | Inner author/references for verified protected reply; explicit forward recipients, attachments re-encrypted without endorsement claim; conventional identity unverified, recipients confirmed; authenticated page-local thread grouping |
| Inbox/session invariants, T07/T12 | PEEK/unread/UID isolation retained; local signer hint still requires full verification; account switch/lock/cancel rejects late results and clears plaintext |
| Evidence / disposition | 52 M6 tests normal and exact reverse; M4 85, M5 55, M3 54, legacy 37 pass; zero skips; five existing legacy warnings only |

[Validation and acceptance table](docs/operations/m6-validation.md),
[controls and live acceptance](docs/operations/m6-gmail-inbox.md),
[ADR 008](docs/adrs/008-m6-mail-workflows.md),
[hash-identified snapshot](docs/operations/evidence/m6-workflows/input-hashes.json).
The final runtime source is identified by those hashes and its local Git receipt;
results are not attributed to unchanged parent HEAD. Existing dependencies/helpers,
M3/M5 code and prior evidence are preserved. Narrow M4 adapter/fixture changes are
recorded separately; no crypto or storage redesign.

Remaining M6: live Google OAuth/IMAP/SMTP acceptance, usable-security/accessibility
walkthrough and supported-platform/connection-phase cancellation qualification.
Small experimental limits, INBOX manual paging, page-local threads and 16-operation
outbox retention remain explicit limits. Independent MIME-peer/expert review,
historical compatibility, native assurance and licensing/distribution/release gates
remain pending under ADR 004/006 exceptions. No M7/M8 or production acceptance.
Next bounded task is M6 walkthrough/platform qualification; live test-account work
only when provisioned and externally sending is separately authorized. No mail was
sent externally, no credentials searched, no migration, push, merge or release.

## Preserved prior assessment at 2c0eed6

# Current M6 Gmail-first development decision — 2026-10-20

**Bounded Gmail-first inbox engineering implemented and locally tested; full M6
PARTIAL. Live Google acceptance remains unexecuted.** Production approval and
independent review remain pending under ADR 004/006/007. No M7/M8 work.

Actual parent: `b96abc45d975c208d37c03bed80e87f6b68c04c2`; local branch
`codex/m6-gmail-inbox`. The M5 branch, known-good `219dc97…` checkpoint, user
launcher, reviewer draft, reference PDF, earlier source and evidence are preserved.
M1 remains COMPLETE at baseline scope: retained Windows/Ubuntu success at
`023c941ec2ef284f6be28b5a9605f1dca9c28787` was verified, not reopened. M2's committed
engineering proof is `1fc4e55f09e173cec7634d0b2dc776097b552063`; `5880dd4…` is its parent.

| Bounded requirement | Current evidence / disposition |
|---|---|
| Provider-backed account-scoped INBOX | Fixed Gmail TLS/XOAUTH2 adapter, owned vault token resolution/refresh, explicit mail scope; no sample inbox or cloud configuration |
| Header-first/on-demand | EXAMINE + UID header fetch; explicit BODY.PEEK open; bounded paging; encrypted per-account header cache |
| Identity/read state | Account + mailbox + UIDVALIDITY + UID; rollover/deletion/cross-account rejection; refresh/open do not set Seen; explicit confirmed read/unread controls |
| Safe protected opening | Unchanged M5 verifier, explicit imported signer certificate, no modern-failure fallback; conventional plain text is unverified; HTML/resources not rendered |
| Worker boundaries | Account/message generations, late-result rejection, cancellation, immediate display clearing; initial DNS/connect/OAuth timing limits documented |
| Presentation reconciliation | b96abc4 shell retained only in M5 fixture harness/history; actual inbox imports no presentation/server fixture, shared-copy shortcut or fabricated enrollment |
| Acceptance gates | Live Google, independent review, other platforms, full M6 workflows/accessibility and existing licensing/release conditions remain pending |

Final results: **21 M6 passed normal (9.76 s) and the same 21 reverse (8.61 s)**;
**55 M5 passed (87.09 s)**; **85 M4 passed (92.33 s)**; **54 M3 passed (11.72 s)**;
**37 legacy passed (2.30 s), five existing datetime warnings**. Zero skips; other
suites have no warnings. A measured Windows blocked-TLS cancellation defect was
fixed using nonblocking polling; initial failure evidence is retained separately.

Runtime results are tied to `docs/operations/evidence/m6/input-hashes.json`, not
unchanged parent HEAD. The local Git receipt identifies the checkpoint containing
those bytes. Existing M3/M5 helpers and native library hashes are unchanged.

[Setup and exact live acceptance steps](docs/operations/m6-gmail-inbox.md),
[acceptance table and retained results](docs/operations/m6-validation.md),
[ADR 007](docs/adrs/007-m6-gmail-mailbox-slice.md).
Next bounded task: perform authorized Google test-account/client live acceptance
when provisioned; no synthetic substitute. No push, merge, release or migration.

## Preserved earlier milestone assessments

Statements below about M6 not having begun are historical checkpoint descriptions.

# Current M5 development decision — 2026-10-14

**Bounded M5 protected-message and compose engineering complete; full M5 PARTIAL.**
M1 remains COMPLETE at baseline scope; M2/M3/M4 retain their scoped earlier
assessments. ADR 006 preserves the owner's development exception while live-provider
acceptance and independent review remain required before production/security release.
No independent approval or production readiness is claimed. M6 has not begun.

Verified local parent: `b00693cbaba92037b3dec8c9e35d866650a5018f` (preserved M4
branch). New local branch: `codex/m5-protected-compose`. Runtime results belong to
the M5 source identified by `docs/operations/evidence/m5/input-hashes.json`, not
unchanged parent HEAD; the local Git receipt identifies the commit containing it.
Earlier source/evidence/locks, canonical specification, reviewer draft and reference
PDF are preserved. Only new M5 files and these current architecture/status additions
are included. No keys, credentials, generated binaries or private evidence.

| Requirement / criterion | Evidence and decision |
|---|---|
| §§41–43/54 M5; QM-MAIL-002/003 | Genuine armored RFC 3156 combined sign/encrypt with direct RFC 9788 hp=cipher protected MIME; experimental marker only; protected author/recipients/subject/date/ID/references/attachments |
| T01/T02/QM-INT-001 | Sequoia 2.4.1/OpenSSL 3.5.9 ↔ rPGP 0.21.0; two recipient keys plus real sender archive decryption using unchanged M3 subkey model; shared MIME wrapper is not independent mail-client evidence |
| T04/I05/I06 | All recipients require existing M3 verified state/current certificate; unknown/changed/expired/revoked blocks all; Bcc unavailable |
| T02/T05/I07/I18 | Immutable results separate crypto/identity/mismatch/replay; malformed/forbidden/tampered/truncated/wrong-key rejection; persisted duplicates/conflicts; read-only legacy classification without fallback |
| QM-MAIL-004/I09/T07/T09 | Off-GUI compose prepares complete persisted MIME before loopback TLS; identical retry bytes; Accepted/Failed/Unknown; receipt isolation; cancel/switch/lock discard stale work |
| Limits | Smaller explicit experimental caps qualified; no 25 MiB product claim, hard OS heap cap or hard 30-second whole-operation guarantee |
| Full milestone/release | Independent protocol/parser review, independent-client evidence and production transition remain pending; live Google, licensing, platform and historical compatibility gates retained separately |

Final results: **55 M5 passed normal (84.17 s); same 55 passed reverse (82.23 s)**;
**2 native passed (1.41 s)**; **85 M4 passed (87.20 s)**; **54 M3 passed (11.11 s)**;
**37 legacy passed (3.10 s), five existing datetime warnings**. Zero skips;
no M5/M4/M3 warnings. All 47 Python packages compatible. Local Windows evidence,
not new hosted/Linux validation. The executable peer stack-overflow failure and
corrected SQLite fault-fixture targeting are retained as development history.

[Acceptance table, exact commands, profile and evidence](docs/operations/m5-validation.md),
[opt-in workflows and actual limits](experiments/m5/README.md),
[ADR 006](docs/adrs/006-m5-development-message-boundary.md).

Legacy F07 remains open at unchanged entry points; durable ordering is demonstrated
in the new opt-in compose path. Exact next bounded task: review this local checkpoint
and qualify the exact RFC 9788/3156 experimental profile against a separately
implemented peer, without expanding into M6 or enabling production. Live-provider
acceptance can proceed separately with explicit provisioned test configuration.
No external mail, data migration, push, merge, deployment or release occurred.

## Preserved earlier milestone status

The earlier dated assessments below are historical snapshots. Their statements
that M5 has not begun describe those checkpoints; the current assessment is above.

# QuMail 1.0 implementation status

Updated: 2026-10-12 (Asia/Calcutta). Target: first proper QuMail 1.0.

## Current M4 SMTP/TLS decision — 2026-10-12

**M1 COMPLETE at baseline scope; M2 PARTIAL; M3 PARTIAL; M4 PARTIAL for the full
application milestone. Bounded M4 SMTP/TLS and development integration engineering
complete.** The full milestone still needs deliberate integration at the eventual
compose boundary: legacy F07 remains open. Production MIME belongs to M5, which
has not begun. Live Google/provider acceptance and independent review remain
separate gates under the preserved ADR 004/005 development exceptions, not a
recurring engineering stop. No independent or production approval is claimed.

Verified/resumed local parent: `b833e8b38892ba84bc0be3e0ab5cf29607c6d479`, branch
`codex/m4-durable-outbox`. Baseline input/output hashes matched. Current results
belong to the new tested working-tree snapshot recorded in
`docs/operations/evidence/m4/tls/input-hashes.json`; the final local Git receipt
identifies the checkpoint containing those bytes. Prior checkpoints and retained
evidence are preserved. One M3 file explicitly changes: `experiments/m3/vault.py`,
to close SQLite creation/setup connections deterministically. Its regressions
were rerun. No native input, canonical specification, legacy path or user data changed.

| Criterion | Evidence / disposition |
|---|---|
| QM-MAIL-001 / T07 | Real loopback STARTTLS, verified certificate/hostname, fresh EHLO; zero resolver/AUTH on TLS failures; identity scopes rejected for mail |
| QM-MAIL-004 / I09 | Frozen sender/recipients/profile/bytes; all required recipients accepted before DATA; actual server byte-digest equality across retry |
| QM-REL-001 / T09 | OS-released operation ownership, short claim/result commits, durable attempt UUID; competing process blocked; account/vault writes work during I/O |
| §50 uncertainty | Real final-response loss, child kill, result-commit denial recover Unknown; no auto-resend; final acceptance survives cleanup/export errors |
| Development interface | Opt-in fixture panel/harness; network off GUI thread; coherent M3 context and stale selection/lock rejection; deterministic shutdown |
| Existing proof / legacy | M1–M3 evidence preserved; 54 M3 regressions and 37 legacy regressions pass; legacy F07 not globally fixed |
| Remaining full integration | Future compose routing to durable service; real provider account acceptance remains unexecuted; M5 protected MIME deferred |

Final runs: **85 M4 passed normal (91.35 s); the same 85 passed reverse (90.53 s)**,
zero skips/warnings. **54 M3 passed (12.56 s)**; **37 legacy passed (1.94 s)**
with five existing datetime warnings. A reverse-run TLS cancellation failure was
fixed using nonblocking handshake polling; the failed run is retained and both
final orders passed on the corrected source.
Dependency consistency: 47 packages compatible. Real socket/TLS/process/SQLite
observations are retained separately from synthetic identities/credentials.

[Current acceptance and exact evidence](docs/operations/m4-smtp-tls-validation.md),
[development workflows](experiments/m4/README.md),
[ADR 005 amendment](docs/adrs/005-m4-development-ordering-and-outbox.md).
Next bounded step: review the local checkpoint and scope opt-in compose routing
to the durable service. M3 Google test-account acceptance can proceed separately
when explicitly provisioned; it is not an engineering stop. Full MIME integration
needs its own M5 scope; M5 was not started. No external mail, migration,
push, merge, deployment or release occurred.

## Preserved initial M4 assessment (b833e8b, 2026-10-11)

The simulation-only and coarse-lock statements below describe that historical
checkpoint; current behavior is documented above.

## Current M4 development decision — 2026-10-11

**M1 COMPLETE at baseline scope; M2 PARTIAL; M3 PARTIAL; M4 PARTIAL.**
**Bounded M4 durable-outbox engineering proof complete.** Full M4 acceptance
still needs actual transport/TLS and application integration qualification.
[ADR 005](docs/adrs/005-m4-development-ordering-and-outbox.md) records the owner's
explicit permission to use controlled identities and injected transports before
M3 live Google acceptance. ADR 004's independent-review exception is preserved;
review remains required before production cryptographic enablement/security
release, not a recurring development stop. No independent approval is claimed.
M5–M8 have not begun; production and real sending remain disabled in this path.

Verified starting branch/HEAD: `codex/m3-identity-vault` /
`1af13a1ee8a58016bdca2dfa25055eb689ec7fd8`. No tracked changes existed; only the
reference PDF and reviewer draft were untracked. M3 source/evidence hashes matched.
New local branch: `codex/m4-durable-outbox`, directly from that M3 checkpoint.
The final local checkpoint contains the tested source identified by
`docs/operations/evidence/m4/input-hashes.json`; its SHA is in the Git receipt.
No test result is attributed to unchanged M3 HEAD. M1/M2/M3 branches, sources,
locks, retained evidence, canonical specification, legacy data and reviewer draft
are preserved. No user-data migration, push, merge, deployment or release.

| M4 criterion | Evidence / disposition |
|---|---|
| §§47/54 typed services | Immutable prepared envelope/binding; explicit account/key/credential handles and repository/builder/transport Protocols; no Qt/concrete network in application logic |
| §46 protected persistence | Existing OS-protected AES-GCM account aggregate; encrypted drafts, exact envelope, immutable recipients/profile/root/subkeys/archive refs and attempts committed atomically |
| QM-MAIL-004 / I09 ordering | Prepared before submit; Submitting before transport; retries load identical bytes; changed capabilities block without regeneration |
| §50 / QM-REL-001 uncertainty | Accepted/Unknown/Failed honest results; ten actual child-kill boundaries; SQLite FULL/COMMIT failure; restart never resends automatically |
| T07/T09 concurrency/cancel | One worker claims operation; active recovery serializes; stale/cross-account/cancel/deadline/three-attempt limits tested |
| Receipt isolation | Optional export error and process death preserve Accepted |
| QM-MAIL-001 real TLS/SMTP | Not executed: simulation only; requires later bounded M4 transport qualification |
| §54 M5 boundary | Raw existing-provider fixture only; comprehensive MIME/header/archive integration deferred to M5 by explicit scope |
| Review/live gates | Google acceptance remains pending; M2 crypto and M3 recovery/enrollment independent review deferred before production/security release |

Final runs: **40 M4 passed normal (35.98 s); the same 40 passed reverse (34.87 s)**,
zero skips/warnings. **54 M3 passed (12.26 s)**, zero skips/warnings.
**37 legacy passed (2.40 s), five existing datetime warnings**, zero skips.
The opt-in disposable harness passed; actual SQLite/process failures are separated
from synthetic identity/transport observations in the validation record.

[Acceptance table and exact evidence](docs/operations/m4-validation.md),
[interfaces and reproduction](experiments/m4/README.md),
[ordering/storage ADR](docs/adrs/005-m4-development-ordering-and-outbox.md).
F07 is not fixed across unchanged legacy entry points. No production security,
original-provider reproduction, historical compatibility or license approval follows.

Next bounded task: opt-in M4 SMTP/TLS adapter qualification against controlled
loopback fixtures, with no real credentials/mail and no M5 integration. Separately,
complete M3 user-driven Google test-account acceptance once explicitly provisioned.

## Preserved M3 handoff assessment (2026-10-10)

The following M3/M2/M1 record is preserved as historical evidence. Statements that
M4 has not begun describe that checkpoint and are superseded by the section above.

## Current milestone and exit decision

**M1: COMPLETE at baseline scope. M2: PARTIAL. M3: PARTIAL.**
**M2 engineering proof complete; M2 exit pending external expert review.**
M3 development proceeds under the owner's explicit ordering exception in
[ADR 004](docs/adrs/004-m3-development-exception.md). Independent review remains
required before production cryptographic enablement or a security release; it
may require corrections to M2 and dependent M3 work. No AI assessment substitutes
for independent review. M4–M8 have not begun. No production release is approved.

Current branch: `codex/m3-identity-vault`. Actual handoff HEAD was M2 checkpoint
`1fc4e55f09e173cec7634d0b2dc776097b552063`; previous M3 changes were uncommitted.
After verifying their tested hashes, they were preserved in local M3 checkpoint
**`ef4b3086d8eac16fd65a3a34f107e75ad4966ec4`**. The current integration checkpoint
is its descendant; exact tested source/output hashes are recorded in
`docs/operations/evidence/m3/integration/input-hashes.json`. Results belong to that
working-tree snapshot, not to unchanged parent HEAD. The local Git receipt records
the final checkpoint SHA. M1/M2 branches/evidence, canonical specification, user
changes, reference PDF and uncommitted reviewer draft are preserved.

## Current M3 development integration — 2026-10-10

**Bounded M3 integration engineering complete; M3 milestone acceptance PARTIAL.**
Independent cryptographic/enrollment/recovery review is deferred until before
production enablement/security release under ADR 004. It is not an engineering
stop and no independent approval is claimed. Real provider acceptance remains
unavailable, not inferred from fixtures. M4 has not begun; sending remains disabled.

| Criterion | Current evidence / status |
|---|---|
| Development path / §54 M3 | `--dev-identity --dev-vault PATH` opens separate Settings/services; default unchanged; no legacy Session/TQR/simulator/portal/mail path is constructed |
| Account/session / QM-ID-001/002 | Complete immutable contexts precede notifications; two same-provider accounts; stale/cancelled/switch/lock worker results cannot install credentials or display state |
| Settings identity/vault / QM-ID-003/005, QM-KEY-001/002 | Creation/selection, OS-backed lock/unlock, public import/export, independent fingerprint pinning, accurate lifecycle display, rotation/revocation and recovery controls tested |
| Google implementation / T06 | Maintained state/S256-PKCE/loopback, signature/issuer/audience/nonce/subject/expiry/address checks; refresh userinfo binding; atomic vault-only credentials; reauthorization supported. Live acceptance pending; Yahoo unavailable |
| Recovery / QM-KEY-004/005, T08 | Ordinary backup does not suspend. Confirmed transfer persists before local suspension; write/commit failures do not deactivate. Restore archive-only; unchanged-root activation explicit, replacement root requires re-verification |
| Interoperability / §§39–41 | Prior actual separate signing-subkey and rotated-certificate exchange retained; actual provider active/revoked/expired statuses added |
| Owner exception / review gate | ADR 004 preserved and amended for integration/backup semantics; independent review deferred before production/security release; M2 still PARTIAL |

Final execution: **3 native passed** (1.16 s); **54 Python passed** normal (11.23 s)
and the **same 54 distinct tests passed** reverse (11.42 s), zero warnings/skips.
Legacy: **37 passed, 5 existing warnings** (1.14 s), zero skips. Actual Windows
Credential Manager entries were disposable and cleaned up; OAuth provider responses
were controlled fixtures, with actual local loopback and offscreen Qt tests.
No Google client/test-account configuration was provided or searched for, so no
live authorization was attempted. No provider/dependency substitution occurred.

[Current acceptance/evidence](docs/operations/m3-validation.md),
[usable development workflows and Google acceptance setup](docs/operations/m3-development-settings.md),
[recovery policy](docs/operations/m3-recovery.md) and
[ADR 004](docs/adrs/004-m3-development-exception.md) are current.

Next bounded step: provision a Google Desktop test client and two owner-controlled
test accounts, then complete the documented live browser/refresh/cancellation
acceptance. Deferred independent review is still required before production or
security release, without repeatedly stopping authorized development for its absence.
No M4, migration, mail send, push, merge, deployment or release occurred.

## Preserved isolated M3 baseline (historical, ef4b308)

The following assessment and 32-test counts describe the prior isolated snapshot,
not the current integrated tree. Settings/browser and transfer-only backup statements
are superseded by the current section, recovery instructions and ADR 004 amendment.

Current local branch: `codex/m3-identity-vault`, created from preserved M2 checkpoint
`1fc4e55f09e173cec7634d0b2dc776097b552063`. The local M3 checkpoint records only the
isolated source/locks/tests/scripts, redacted evidence and documentation. Exact
input correspondence is in `docs/operations/evidence/m3/input-hashes.json`; results
belong to the tested working-tree bytes, not the unchanged M2 parent. M1/M2
branches, canonical specification and M2 reviewer draft are preserved. Nothing
was pushed, merged, deployed or released; no real mail or user-data migration.

## M3 bounded implementation and acceptance (2026-10-05–06)

[Full acceptance table and exact outputs](docs/operations/m3-validation.md),
[owner exception and design](docs/adrs/004-m3-development-exception.md),
[recovery instructions](docs/operations/m3-recovery.md) and
[source/reproduction](experiments/m3/README.md) describe this isolated boundary.

| Requirement / criterion | Implemented and executed evidence | Remaining gate |
|---|---|---|
| §54 M2 prerequisite | M2 engineering preserved; explicit owner-authorized ordering exception | M2 remains PARTIAL; independent crypto/protocol review before production enablement/security release |
| QM-ID-001/002, T06 | Distinct account/device/root/handle types; two same-provider accounts; maintained Google signature verifier with synthetic issuer; state/nonce/issuer/audience/subject/expiry/hosted-domain rejection | Live Gmail/Yahoo authorization, browser/PKCE, session/Settings integration pending; Yahoo fails closed |
| QM-ID-003/004/005, QM-PQC-002, T04 | Recipient-owned root plus separate signing/encryption keys; public-only import/export; explicit fingerprint pin; changed/retired-key blocking; root-signed rotation/revocation; expiry/unbound foreign subkey rejection | Human ceremony and enrollment/root-reset threat-model review; simultaneous devices explicitly deferred |
| QM-KEY-001/002/006, QM-SEC-004, T08 | Real Windows Credential Manager write/read/delete and cleanup; no file fallback; authenticated owned SQLite records; cross-account/tamper/hostile-ID rejection | Same-user malware/OS-store rollback/path races/installation ACLs not claimed addressed |
| QM-KEY-003/004/005, T08 | Additive rotation/history retention; explicit encrypted transfer backup; clean archive-only restore decrypts actual historical envelope; new-root re-verification; destruction acknowledgment | Offline copies/backups are not remotely erased; independent recovery review pending |
| §39 changed certificate interoperability | Sequoia/OpenSSL ↔ rPGP with separate signing subkey; rotated certificate sign/verify/decrypt checks | Common active-fingerprint selection is not independent policy selection; no multi-device/MUA/Linux claim |
| T08 atomicity | Parallel real writes, abrupt child exit, SQLite FULL and commit-denied restore leave consistent records | Whole-database rollback resistance and OS-store/database joint transaction not provided |
| QM-DOC-001/002, §54 | ADR 004, architecture, recovery, support limits and evidence updated | M3 stays PARTIAL pending provider-specific/live/integration and independent-review gates |

Final tests: **2 native passed** (1.14 s); **32 Python passed** normal (14.80 s)
and the **same 32 distinct tests passed** reverse (14.74 s), zero skips/warnings.
Legacy regression: **37 passed, 5 existing warnings**, 2.68 s, zero skips.
Real OS-store tests required the normal Windows logon session because the sandbox
denied access; mocked storage denial and synthetic OAuth are labeled separately.
All 15 M2 input hashes remain unchanged; M3 third-party Cargo inputs match M2.
OpenPGP still uses native OpenSSL 3.5.9; storage uses cryptography 50.0.2's separate
OpenSSL 4.0.3 backend. Neither is substituted silently for the other.

Next bounded work remains M3: complete and validate external-browser authorization
and session/Settings integration using explicitly provisioned test accounts;
obtain independent enrollment/recovery and M2 cryptographer/protocol review.
No production cryptographic enablement, M4, push, merge or release is approved.

## Preserved M2 handoff provenance

Preserved M2 branch: `codex/m2-provider-proof`. At test execution, HEAD was
`5880dd4d6bc15a2e111c49d929432e6ed2419f33` and M2 was working-tree content,
identified by the experiment source/input hashes in
`docs/operations/evidence/m2/20261005-input-audit.json`. The local review checkpoint
preserves those exact 15 input files; its SHA is recorded in the local reviewer
request prepared after committing (`docs/operations/m2-reviewer-request.md`).
Results belong to the hash-identified snapshot, not its earlier parent commit.
The M1 review branch below is preserved. No M2 publication,
merge, production integration, user-data migration or release occurred.

Review branch: `codex/m1-hosted-validation`, published to `uzx-02/QuMail`.
Audited source baseline: `7079cf16cb2623172a329fd045045227f7eb65b4` on `main`.
First fully successful hosted implementation/workflow commit:
`023c941ec2ef284f6be28b5a9605f1dca9c28787`. Results below belong to that exact SHA;
subsequent documentation commits must not inherit an unexecuted test claim.
The canonical engineering source is `QuMail-1.0-Research-Audit-Specification.md`.
The 143-page PDF is a presentation/reference copy. Comparison found formatting,
link/reference extraction differences (including merged/omitted citation labels),
not differing engineering requirements. Both supplied files remain untouched.

## M2 engineering continuation and acceptance (2026-10-05)

[Current acceptance table and exact validation](docs/operations/m2-validation.md),
[external review package](docs/operations/m2-external-review.md),
[provider evaluation](docs/operations/m2-provider-evaluation.md) and
[proposed ADR 003](docs/adrs/003-m2-provider-proof.md) are consistent with this
decision. The original nine-test evidence, hashes and dated 2026-10-04 decision
snapshots are retained; the broad provider survey was not repeated.

- Handoff unchanged: 023c941 → 5880dd4 is documentation/evidence only (15 files);
  application/dependency/CI paths unchanged. M1 review branch/evidence preserved.
- Candidate unchanged: Sequoia 2.4.1/OpenSSL 3.5.9; independent rPGP 0.21.0.
  The unmodified-provider lane retains all nine positive/negative/vector/header
  tests plus three typed contract tests. No provider version substitution.
- `CryptoPolicy`/`OpenPgpProvider` and explicit profile/failure/result types are
  implemented only inside the experiment. Unknown/weak/malformed/unsupported
  profiles, untrusted/changed recipients, forbidden portal/simulator routes,
  critical extensions and resource violations fail closed. Private staging
  cannot become VerifiedPlaintext on provider error or incomplete verification.
- Actual provider-generated OCB, SHA-256 signatures and unknown critical
  notations are rejected, with a valid-profile positive control. Mock provider
  status/staging/panic tests are labeled separately from native evidence.
- Sequoia's private OpenSSL context uses HMAC-DRBG/SHA-512. A diagnostic-only
  source copy exposes its context pointer without changing algorithms. Supported
  OpenSSL controls in fresh child processes demonstrate actual random-source
  initialization and provider failures, plus real post-health send/open panic
  containment. No ciphertext/plaintext success escapes. The native library is
  unchanged; the 651-file audit finds only a feature and accessor addition;
  transitive lock versions/checksums match the ordinary lane.
- Exact configuration has no default-provider self-test callback. Its return
  value 1 is not a FIPS/KAT guarantee. Direct OS entropy-outage and allocation
  failure are not claimed as executed; review questions state the limitations.
- Final normal: **12 passed** (3.03s) ordinary, **5 passed** (0.13s) diagnostic,
  zero failures/ignored. Reverse executes the **same 17 distinct tests**.
  New legacy regression: **37 passed, 5 existing warnings**, 2.40s, zero skips.
  No hosted/Linux M2 result or production IPC execution is claimed.
- Warnings remain visible: M1's 42 liboqs barrier emissions; the candidate native
  build's 871 MSVC diagnostics/231 Perl locale lines; diagnostic path dependency's
  22 upstream Rust deprecation warnings. Native mandatory-SHA256 panic and
  deprecated context constructor's allocation-failure fallback are reviewer
  questions. Successful tests/no-asm do not establish constant-time safety.

| M2 traceability | Current disposition |
|---|---|
| QM-CRYPTO-001/002; QM-INT-001 M2 portion; QM-PQC-001; §§41/54 exact provider/AEAD/header fixture | Engineering proof satisfied on measured Windows build; candidate frozen for review, not production-approved |
| QM-CRYPTO-006 / T01 | Published integration vectors and negative cases retained/passing; broad primitive/fuzz/platform qualification remains M8 |
| QM-CRYPTO-004 / T01/T09 | Real selected-backend RNG/provider failures prevent key generation/encryption; late native errors/panics contained. No nonexistent FIPS self-test guarantee claimed |
| QM-SEC-001/002/006, QM-QKD-004, QM-PORTAL-003 / T03, §54 typed interfaces | Isolated contract/matrix satisfied; no downgrade/substitution. Production UI/TQR/portal are unchanged and not declared fixed |
| §54 M2 Review | **Pending external human cryptographer/protocol review** of composition, secret boundaries and disclosed assurance limits |
| §54 Docs/Migration | Review package, proposed ADR, hash-identified validation ready; no production write migration |

**M2 engineering proof complete; M2 exit pending external expert review.**
Keep M2 PARTIAL until the specification's reviewer accepts it or requests bounded
corrections. Passing tests and this agent's inspection are not independent approval.
No new milestone requirement for enrollment, production UI, SMTP, installer or
Linux CI is invented. Linux/helper/package qualification, full independent MUA
interoperability, original-artifact/historical compatibility, owner licensing and
production release retain their existing gates. F01–F19 are not fully remediated.

## M1 evidence authority (preserved record)

[Checkpoint, exact commands and retained output](docs/operations/m1-validation.md)
records the pre-edit inventory, current tests, failed order runs and final results.
The prior status narrative was stale; source and executable evidence supersede it.

- Original available-dependency baseline in this session: 8 passed, 3 failed,
  2 skipped on Windows. Failures were KME limiter state and two POSIX-only
  permission assertions; ML-KEM skipped without its unavailable provider.
- Continuation checkpoint: 30 passed, 5 warnings, zero skips in existing research
  environment. Not evidence of order independence.
- Clean environment: CPython 3.12.14 x64, 47 packages installed from the development
  hash lock. Dependency consistency check passed.
- Focused M1 tests: 29 passed, 4 warnings. Added research-provider negative tests.
- First reversed/shuffled full runs exposed QApplication lifetime pollution:
  2 passed/35 errors and 25 passed/12 errors. Corrected the test fixture to session
  scope; production Session code was not changed.
- Final complete suite: **37 passed, 5 warnings, zero skips**, in each of normal,
  reverse and seeded order (20261003). Times: 1.50s / 1.55s / 1.41s.
- Hosted run [37128055379](https://github.com/uzx-02/QuMail/actions/runs/37128055379)
  passed both Windows 2022 and Ubuntu 24.04 at `023c941`: **37 passed, 5 warnings,
  zero failures/errors/skips/xfails**, each in normal/reverse/seeded order.
  Dependency consistency: Windows 47 packages, Ubuntu 46; both passed.
- Intentional missing-native run: 2 failed, 4 passed, zero skips; explicit native
  configuration failure. Intentional skip/xfail probe exited 1 as required.
- Original exact OQS pin resolver: exit 1, unsatisfiable. No silent substitution.
- `transport/imap_receiver.py` has no diagnostic print calls despite the historical
  audit narrative; this current-source difference is documented in architecture.

## M1 requirement checkpoint after work

| M1 requirement or task | Status | Evidence | Files involved | Tests proving it | Remaining action |
|---|---|---|---|---|---|
| Baseline and prior changes | complete | main/7079cf16 baseline, inventory retained; review branch published | validation report; Git | branch/status/rev-parse/staged scan | Review branch remains unmerged |
| Clean development installation | complete | Local and hosted Windows: 47 packages; hosted Ubuntu: 46; all consistent | requirements.txt; packaging inputs/locks | clean installs and complete suites | Other platforms remain unvalidated |
| Research native reproducibility/report | complete | binding 0.16.0.1, native 0.16.0, immutable source/flags/binary hash recorded | legacy_provider.py; native manifest; ADR 002 | research report, round trips, five tamper/wrong-key cases, no-install guard | Research only; not original artifact reproduction |
| Original provider and historical compatibility | blocked | exact 0.14.1 resolver fails; historical fixtures unavailable | original-provider requirements; availability report | resolver exit 1; explicit offline blocker exit 1 | Obtain authentic original artifacts/fixtures; do not silently replace |
| Deterministic isolated tests | complete | fresh limiter/registry/stores/clock/temp cwd; session-scoped test QApplication | tests/conftest.py; test_ui_claims.py | three complete orders pass | None at local baseline scope |
| Platform-aware permissions | complete | POSIX mode checked only on POSIX; Windows chmod intent/access checked | test_transport.py | Windows and Ubuntu hosted tests pass | No Windows ACL claim |
| Mandatory native tests/no false skips | complete | missing provider fails; skips/xfails fail | pytest.ini; conftest; native tests | missing-native and skip probes; full suite zero skips | Release vectors remain M2/M8 |
| Simulator opt-in/boundary | complete | default creates no server; custom simulator provenance/UI labels | main.py; kme/virtual_node.py; UI | startup/status/UI tests | Real QKD excluded |
| Baseline characterizations | complete | F03/F04/F05/F07/F10/F11/F15 retained as known defects | test_legacy_characterization.py | seven tests | Fix only in their future milestones |
| CI definition and execution | complete | pinned workflow; independent native builds; run 37128055379 at 023c941 | .github/workflows/m1.yml; hosted evidence | Both platforms pass three complete orders and consistency checks | Preserve exact-SHA attribution for later changes |
| Truthful architecture/claims/support | complete | canonical source corrected; actual flows, provider and historical-doc limits | README; ARCHITECTURE; historical docs; docs/security; docs/operations | source/diff inspection; UI tests | Update support only as new evidence arrives |
| Preservation/status/ADRs | complete | no data migration; backups/rollback and decisions recorded | docs/migration; status; ADR 001/002 | legacy round trips/MIME characterization; diff review | Retain user data and original reader evidence |

## Requirements and security disposition

QM-QKD-001, QM-TEST-001, QM-DOC-001 and QM-DOC-002 are addressed at M1 scope.
QM-DEPLOY-001 receives hash locks and CI groundwork, not signed release/SBOM
completion. QM-CRYPTO-006 independent-provider vectors/interoperability remain
M2/M8 work; same-provider ML-KEM tests do not fulfill them.

F03: simulator exposure/provenance labeling and opt-in addressed; no authorization
redesign. F16: unsigned records/privacy claims corrected. F17: lock/research
availability/reporting and cryptography input update addressed, original pin still
blocked. F19: limiter/Qt isolation, explicit skips and local order evidence
addressed, including hosted CI evidence. **F01–F19 remain tracked as open
findings; this milestone does not claim complete security remediation.**

No changes to TQR dispatch, XOR/AES algorithms, custom MIME schema/reader, identity
ownership, portal decryption/storage trust, OAuth storage or full storage design.
Legacy metadata, key IDs, readers and user data were preserved. Tests used temporary
fixture state; no real mail, credentials, cloud service or hardware QKD was used.

## Blockers and limits

1. No outstanding M1 baseline validation blocker. Hosted run 37128055379 validates
   exact commit 023c941 on both declared platforms; later commits need their own
   evidence. Branch remains unmerged; there is no release approval.
2. Original `liboqs-python==0.14.1` unavailable. ADR 002 explicitly permits a
   different research-only lane; it is not evidence of historical compatibility.
3. Project license/Qt distribution choice unresolved; no redistribution approval.
4. Legacy Docker recipe is obsolete and excluded, not advertised as runnable.
5. Five legacy datetime deprecation warnings remain. No release/interoperability,
   real provider OAuth/SMTP/IMAP, real Firestore or Windows ACL validation claimed.
6. Hosted MSVC emitted 42 optimization-barrier/possible non-constant-time warnings.
   Functional research success does not qualify constant-time safety; production
   compiler/provider review remains gated. Both jobs also reported the checkout
   action's Node 20-to-24 runtime deprecation notice.

## Publishing continuation (2026-10-03)

Historical record before authentication became available; superseded by the
completed hosted continuation below. Preserved for audit continuity.

Remote confirmed as `https://github.com/uzx-02/QuMail`; branch/HEAD unchanged.
`gh auth status` exits 1: no GitHub host is authenticated. Per the user's explicit
stop condition, no review branch was created, no files were staged, and no commit,
push or hosted run was attempted. Git's `manager` helper does not establish CLI
authentication or workflow-write permission. No credentials were sought elsewhere.

Publication scan found local account paths in ten validation files. Byte-identical
originals are retained under ignored `tmp/m1-private-evidence/2026-10-03-publish-review`;
publication copies replace the account component with `<LOCAL_USER>`. Redaction
hashes are recorded in `docs/operations/evidence/publication-redactions.json`.
No common credential-pattern hits, key/cache directories or generated native
binaries were found among pending candidate files; final staged review is still
required before publishing. The PDF remains an unstaged user reference.

The validation report now assesses each M1 acceptance criterion as satisfied,
blocked or deferred. **Original 0.14.1 reproduction and historical compatibility
are separately blocked compatibility/release gates, not additional M1 exit
requirements:** §54 permits a reproducible research-only pair or explicitly
unavailable Level 3; ADR 002 records that choice and its limits. Project/Qt rights
remain owner/distribution gates; triage is complete, approval is not supplied.
The actual remaining M1 exit gate is successful hosted Windows/Ubuntu evidence.

Required user action: complete `gh auth login --hostname github.com --git-protocol
https --web --scopes workflow`, then `gh auth setup-git --hostname github.com` and
`gh auth status` in a local terminal. Do not paste tokens into chat. The review
branch publication remains authorized once normal authentication is available.

## Historical M2 handoff next step (superseded only for development ordering)

Obtain the §54 external human cryptographer/protocol review of the local M2
package and exact input hashes. Address any requested corrections within M2.
That handoff did not authorize M3, production sending, push, merge or release. ADR
004 now authorizes bounded M3 development while retaining the review gate. The package
has not been sent or published; this task does not claim independent approval.

## Hosted continuation completed (2026-10-03)

Authentication verified outside the network sandbox as account `uzx-02`, with
repository access and workflow scope; no unrelated credential search occurred.
Created/pushed the review branch only. The explicit 67-file initial staging list
excluded the reference PDF, private originals, environments, keys and binaries;
staged credential-pattern and personal-path checks passed. Canonical Markdown
and archived output retain presentation/trailing whitespace; code diff checks
pass with those preserved records excluded. No main push, merge or deployment.

Actual failures fixed only in CI setup: actions/setup-python lacked Windows
3.12.14; Ubuntu lacked libEGL; uv 0.11.15 lacked the requested Python download in
its embedded catalog. Pinned uv 0.12.22 now creates fresh managed Python 3.12.14
environments; Linux Qt libraries are explicitly installed. Application locks,
OQS binding 0.16.0.1/native 0.16.0 and all tests/assertions are unchanged. Local
focused checks after the setup edit: 12 passed. No algorithm/provider substitution.

First all-green run: [Windows job](https://github.com/uzx-02/QuMail/actions/runs/37128055379/job/111217345728),
[Ubuntu job](https://github.com/uzx-02/QuMail/actions/runs/37128055379/job/111217345547).
The final acceptance assessment, commands, toolchain versions, native hashes,
warnings and preserved failed runs are in `docs/operations/m1-validation.md`.
All M1 criteria are satisfied; historical compatibility, project/Qt distribution
rights, independent interoperability and production approval retain their
existing separate gates. F01–F19 are not declared fully fixed. At the end of that
M1 continuation M2 had not started; the subsequent M2 state is recorded above.
