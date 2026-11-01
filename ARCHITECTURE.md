# Current architecture index — handover 2026-11-01

For source checkpoint `4e429a43a6d9ae7fe6bb45c4ae5a8dcb6200e6b0`, the maintained
actual-path/interface map is [CODEBASE_MAP](docs/handover/CODEBASE_MAP.md), with
[security contracts](docs/handover/SECURITY_CONTRACTS.md). Read these before the
historical snapshots below. Modern application: `main.py --dev-mailbox` → mailbox/
Settings UI → coherent sessions and bounded workers → shared M3 vault/identity,
M5 MIME/crypto and M4 durable outbox → explicitly configured Gmail TLS. Optional
`services/relay` is separate local SQLite/mTLS ciphertext storage, not an ordinary
email dependency. Default startup remains legacy. Modern shared code still under
`experiments/` is not disposable fixture code; consolidation is proposed, not done.

Settings async engineering is complete at bounded Windows scope. Live Google,
normal-desktop launch handoff, independent review and release gates remain; historical
exclusions below describe earlier checkpoints only. Android is a new delivery goal
with no implementation, recorded in the [roadmap amendment](docs/handover/STATUS_AND_ROADMAP.md).
ADRs 004–009 retain development exceptions; no production approval is implied.
Canonical specification unchanged. No architecture/runtime rewrite in this handover.

## Preserved architecture snapshots (newest first)

# Asynchronous Settings boundary — 2026-10-21

`core.settings_operations` separates immutable account/vault/generation requests,
background preparation/persistence and GUI publication. One admission/worker bounds
work and private results. Workers open their own SQLite connections; neither Qt
widgets nor the mutable IdentityService run there. Account selection uses coherent
cached views; contact/lifecycle reads refresh asynchronously without invalidating
unrelated mail workers. Stale results cannot repopulate another account.

A narrow Vault.commit seam permits the Settings subclass to atomically encrypt
owner receipts and reserve authorization under the session mutex before COMMIT.
The mutex is released before disk I/O. Cancellation after reservation may leave a
durable original-account effect; Inspect outcomes after unlocking/selecting it.
No rollback claim is made for work already committed or authorized to commit.

Backup/transfer preparation is memory-only. The GUI requires saved-offline-secret
acknowledgment BEFORE a package can be written, then clears private staging. No
new durable secret retention is introduced. Export intent/file/final receipt are
separate bounded steps; transfer suspends only at the final successful commit.
See [ADR 008](docs/adrs/008-m6-mail-workflows.md),
[Settings validation](docs/operations/m6-settings-validation.md) and
[recovery custody](docs/operations/m3-recovery.md). Prior architecture follows as
historical context; its synchronous-Settings blocker is now superseded.

# Windows connection/UI continuation — 2026-10-21

Application DNS and Google OAuth run in bounded private child processes; fixed
Gmail TCP/TLS setup is nonblocking and deadline-aware. The child uses the unchanged
M3 verifier. Only owned results surviving session/cancel checks enter the vault.
Secrets use private pipes, not argv/caches. Existing crypto/outbox boundaries remain.
Settings hide/reopen differs from final disposal; mail controls have names/focus
and busy/state guards. This is development qualification, not approval.

Remaining engineering: Settings native/vault work, including post-OAuth commit,
is synchronous. Finite 30 s helper/5 s SQLite waits are not a subsecond UI contract.
Safely staged Settings preparation/commit is next; preserve account-generation,
transaction and recovery-secret guarantees. See
[current validation](docs/operations/m6-windows-validation.md) and ADR 008.

# Integrated M6 mail boundary — 2026-10-21

The opt-in `--dev-mailbox` path now connects real mailbox retrieval to
`mailbox_client.workflows.Workflows` and `ui.mail_actions`. M3 coherent contexts,
leases and owned vault handles remain the account boundary. M5 Compose/OpenMessage
owns protected MIME/crypto; M4 owns frozen outbox state and uncertain acceptance.
No presentation fixture or shared demo ciphertext is imported into the application.

Compose stores encrypted drafts; preparation rechecks all recipients. Submission is
separate and disabled unless `--dev-gmail-submit` explicitly selects GmailSMTP.
The shared SMTP engine retains verified STARTTLS, bounded replies, post-TLS scoped
XOAUTH2 and exact DATA bytes. LoopbackSMTP retains numeric loopback-only policy;
GmailSMTP fixes smtp.gmail.com:587 and system CA/hostname validation. External opt-in
is explicit at the durable service boundary; offline inspection cannot submit.

Attachment export follows completed M5 verification and explicit no-clobber Save As;
there is no ordinary plaintext cache. Reply/forward produces new M5-protected mail,
revalidates current recipient keys, and separates forwarded content from original
endorsement. Only verified identity's inner references establish page-local thread
groups. Outer From can hint at an existing local certificate but cannot grant trust.
PEEK, UID identity, account generations and stale-worker clearing remain intact.

The native cryptographic profile, legacy readers and core storage/session code are
unchanged. No live provider acceptance, migration, M7/M8 or production approval.
[ADR 008](docs/adrs/008-m6-mail-workflows.md) and
[current validation](docs/operations/m6-validation.md) supersede the older feature
exclusions below while preserving their historical context.

## Preserved architecture at the inbox-only checkpoint

# Gmail-first development inbox boundary — 2026-10-20

`main.py --dev-mailbox --dev-vault <explicit-path> [--google-client <explicit-file>]`
launches the bounded inbox with existing M3 Settings/session/vault interfaces.
Default startup remains unchanged. No presentation accounts or sample mail are
imported; the b96abc4 presentation shell remains an isolated M5 fixture harness.
Production enablement and independent review are still pending.

`mailbox_client.gmail` connects to fixed Gmail TLS IMAP with XOAUTH2. Every read uses
EXAMINE and UID FETCH BODY.PEEK. Only explicit read/unread actions use UID STORE;
no CLOSE/EXPUNGE. Credentials are account-scoped vault records, with existing Google
identity-checked refresh and an explicit additional mail-scope authorization lane.
`mailbox_client.service` keeps a bounded encrypted header page per account, keyed by
mailbox/UIDVALIDITY/UID. Bodies are fetched on demand, not cached to plaintext files.

Protected mail uses unchanged M5 OpenMessage with an explicitly selected imported
public signer certificate. Signature/identity/replay/header discrepancy states remain
separate. Conventional mail is unverified plain text; HTML and remote resources are
not rendered. `ui.mailbox_window` clears content and rejects obsolete worker results
after account/message selection, cancellation or lock. Initial connection/OAuth waits
have documented limits; post-connect IMAP I/O polls cancellation at 50 ms.

No changes to M5 cryptography, persistence, transport or core session sources.
No inbox sample fallback, production SMTP, attachment workflow, reply/forward,
M7/M8 or migration. [ADR 007](docs/adrs/007-m6-gmail-mailbox-slice.md),
[validation](docs/operations/m6-validation.md), [setup](docs/operations/m6-gmail-inbox.md).

## Preserved architecture through M5

# M5 opt-in protected-message boundary — 2026-10-14

The new `experiments/m5` path composes RFC 3156 PGP/MIME with RFC 9788 direct
protected headers over the provisional M2/M3 standard OpenPGP profile. It is
disabled by default and uses disposable accounts and loopback-only TLS. The
historical architecture below and all earlier runtime paths remain unchanged.
[ADR 006](docs/adrs/006-m5-development-message-boundary.md) authorizes this bounded
development ordering, without independent or production approval.

`Compose` uses coherent M3 account leases and M3 current verified-recipient checks.
Its repository adapter reuses M4's encrypted draft/outbox transaction, binding and
submission services; only public recipient certificates enter encryption. M3-owned
key handles resolve private signing/decryption material inside the service and
private helper pipes. No directory/backend receives private keys. Sender archival
encryption is explicit; Bcc is unavailable. No TQR/simulator/portal routing exists.

`MessageBuilder` fixes protected metadata in bounded inner MIME, asks the provider
for complete signed/encrypted standard packets, wraps provider ASCII armor, and
commits the exact serialized envelope before SMTP. M4 preserves those bytes on
retry, honest acceptance uncertainty and independent receipt export. The native
helper includes unchanged M3 crypto source with a separate root package/lock;
an explicit worker stack fixes the measured Windows peer stack overflow.

`OpenMessage` bounds outer MIME, requires complete provider integrity/signature
verification, validates signed profile/author/intended recipient/metadata, then
commits account-scoped replay state before returning a frozen result. Identity
trust and outer-header discrepancies are separate from signature validity. Conflicts
cannot be labeled verified-confidential. Legacy classification preserves original
bytes and never serves as fallback for failed modern verification.

`ComposePanel` uses a worker and generation/lease checks for prepare/open/network
work. The explicit demo offers encrypted draft, prepare, inspect, submit, controlled
failure/recovery/retry, recipient copy and sender archive open. It has a plain-text
test display, no IMAP inbox or active-content renderer. Cancellation/switch/lock
prevents late publication; process pipes have deadline/output bounds. SQLite waits
and preparation writer-lock duration remain documented development limits.

[M5 validation](docs/operations/m5-validation.md) distinguishes real native/storage/
TLS evidence from synthetic identities and shared MIME wrappers. Independent crypto
exchange is demonstrated both ways; independent mail-client interoperability is not.
Actual smaller limits and launch instructions are in [M5 README](experiments/m5/README.md).
Legacy F07 remains open in unchanged compose. Full M5 and production/review/licensing/
live-provider gates remain pending. M6 is not begun.

## Preserved architecture through the M4 checkpoint

# QuMail 1.0 architecture — actual development baseline

Status: prototype, not approved for confidential production use. Specification:
root-level research Markdown, §§3–18 and 38–54 (PDF is a reference copy).
See IMPLEMENTATION_STATUS.md and ADRs.
The original “100% complete” and “v2” narrative did not establish release evidence.

## M4 controlled loopback outbox (2026-10-12)

[ADR 005](docs/adrs/005-m4-development-ordering-and-outbox.md) now includes
controlled SMTP/TLS qualification. Qt-independent PrepareMessage/SubmitOutbox
services persist exact provider fixture bytes, frozen sender/recipients/profile/
keys and durable attempt identity. Short claim/result SQLite transactions surround
network work; per-operation OS ownership prevents competing submission or recovery
from stealing a live worker. Account/vault writes proceed during network waits.

`LoopbackSMTP` accepts only numeric IPv4 loopback and an explicit port. Required
STARTTLS, certificate/hostname verification and fresh EHLO precede scoped credential
resolution and AUTH. The default trust context validates normally; disposable roots
are passed only by fixtures. Absolute deadlines, bounded replies and cancellation
apply across protocol stages. Any required recipient rejection prevents DATA.
Final DATA success means server acceptance, not delivery; possible acceptance stays
Unknown. Retry reuses exact bytes. Cleanup/receipt failure cannot undo Accepted.

`python -m experiments.m4.loopback_demo --loopback` opens the small development
outbox with generated fixture accounts/server; `--smoke` exercises it headlessly.
The panel consumes coherent M3 snapshots, uses workers for network waits and rejects
stale display results after selection/lock. It offers inspection, submission,
restart recovery, explicit duplicate-risk retry and separate receipt export.
Default startup, real provider configuration and legacy paths below are unchanged.

The only changed M3 source is deterministic SQLite connection closure in vault.py;
the old GC workaround is removed. Previous proof remains historical and the affected
M3 suite is rerun. No native/provider inputs change. Test MIME is not M5 protected
mail. [Current acceptance/evidence](docs/operations/m4-smtp-tls-validation.md)
separates real loopback observations from synthetic identities and release gates.
F07 remains in the unchanged legacy entry point; no production enablement follows.

## M3 development integration (2026-10-10)

[ADR 004](docs/adrs/004-m3-development-exception.md) permits bounded development
while independent cryptographic/enrollment review remains deferred until before
production enablement/security release. It is not independent approval.

`main --dev-identity --dev-vault PATH` lazily opens only `IdentitySettings` through
`IdentityService`. Default startup is unchanged. The development option rejects
simulator startup and does not construct legacy MainWindow, global Session,
inbox, compose, TQR, portal or SMTP. Sending remains disabled.

`DevelopmentSession` holds one immutable account snapshot: complete account/device
context, opaque key handle and public display metadata. It installs all fields
before emitting changes. Selection, lock, cancellation and replacement authorization
invalidate worker tickets. Workers produce transient OAuth results; only a current
ticket can commit account/credentials and update the display. Tokens/private keys
are never placed in the view or legacy session. The vault owns encrypted records.

Google external-browser authorization uses maintained libraries, random state/
nonce, S256 PKCE and an ephemeral IPv4 loopback callback with strict path/Host/
port checks. Token signature, issuer, audience, nonce, subject, expiry and authorized
address are checked before a single enrollment transaction. Refresh authenticates
the fresh access token at Google's fixed TLS userinfo endpoint and validates an
ID token if supplied. Only an explicit test-client file is read; no legacy cache
is consulted. Real provider acceptance remains unexecuted; Yahoo is unavailable.

Windows Credential Manager protects the random master key. Authenticated SQLite
records bind account/device ownership, keys, lifecycle, trust and credentials.
Explicit public certificate import and independent fingerprint pinning control
trust; changed roots, observed old subkeys, expiry and revocation block use.
Separate root/signing/encryption certificate keys and additive rotation retain
the independent rPGP tests. Native provider/version/flags remain provisional.

Ordinary encrypted backup leaves source lifecycle unchanged. Confirmed transfer
persists a new encrypted file before committing local suspension. Restore is
transactional and archive-only by default. Unchanged-root activation requires
explicit prior-device retirement acknowledgment; replacement creates a new
fingerprint requiring renewed contact verification. Offline clones cannot be
detected/erased; whole-database rollback and same-user compromise remain limitations.

[Settings/setup](docs/operations/m3-development-settings.md),
[validation](docs/operations/m3-validation.md) and
[recovery](docs/operations/m3-recovery.md) separate tested development behavior,
live acceptance and deferred review. No existing data or legacy flow below is
migrated. No M4 service is wired into this Settings path.

## Actual execution flows

Each row follows input → processing/cryptography → storage → network → output.

| Flow | Actual responsible code and order |
|---|---|
| Startup | `main.main` parses explicit `--dev-simulator`; optional daemon `_start_kme_server` runs Flask loopback; `_launch_desktop` creates Qt/MainWindow. Default creates no KME server. |
| Gmail auth | Settings `_AuthWorker` → `oauth2_gmail.get_access_token` → cached Fernet file/refresh or InstalledAppFlow browser → Google → token; `_on_auth_success` installs separately typed address into global session. No verified subject binding. |
| Yahoo auth | `_AuthWorker` → PKCE/browser local callback → requests token exchange → Fernet token file → token/session; explicit state validation is absent. |
| Account | `Session.active_account` emits before related provider/token assignments finish; session is mutable process-global. Account-isolation redesign pending. |
| Recipient | Compose → `recipient_check.check_recipient` → KME email registry lookup → bool/SAE string; lookup failure enters confirmation for legacy portal. Registry is not cryptographic identity. |
| Keys 1/2 | `tqr._request_key` → `KMEClient.request_key` → Flask `request_key` → OS CSPRNG → `_issued_keys` RAM → raw key/ID; retrieval by ID has no caller authorization. Registry JSON persists, keys do not. |
| Legacy XOR | `tqr.encrypt` pads short plaintext → simulator key → `level1_otp.encrypt` XOR → ciphertext + unauthenticated metadata. No integrity or one-use enforcement. |
| Legacy AES | `tqr.encrypt` → simulator key → `level2_aes.encrypt` AES-GCM, random nonce, AAD=None → ciphertext/tag + unbound metadata. |
| Legacy ML-KEM | `level3_mlkem` → pinned `legacy_provider.load_oqs` → sender-generated pair → KEM/DEM → ciphertext + metadata, private key returned separately. No signatures or recipient public-key discovery. |
| Compose/send | `_SendWorker._execute`: body → TQR → `encapsulator.encapsulate` custom MIME → `smtp_sender.send_email` → unsigned JSON/PDF → optional portal store/start → `_persist_send_key` → result. F07 remains: SMTP is too early. |
| SMTP | provider domain heuristic → OAuth → port 587 STARTTLS with default validating context → XOAUTH2 → sendmail. Acceptance is not delivery/decryption. |
| Inbox headers | `imap_receiver.fetch_inbox`: account → OAuth → validating IMAPS/993 → readonly INBOX → UID search + header PEEK → parsed rows. No real mail/network in tests. |
| Open message | `_FetchMessageWorker`: fetch RFC822 by UID → permissive `decapsulator` → `_load_send_key` file lookup and TQR → decoded text. No signatures/replay/UIDVALIDITY cache; stale-worker hazards remain. |
| Portal create | `store_session`: ciphertext + metadata + private key → Firestore or silent memory fallback → URL. SMTP does not contain that final URL. |
| Portal retrieve | browser POST → `_PortalHandler.do_POST` → `portal_crypto.decrypt_for_portal` on server → `_mark_consumed` transaction/lock → plaintext JSON → browser textContent. Consumption retains secrets. |
| Local secrets | Gmail/Yahoo caches and sender private files use nearby raw Fernet wrapping key; permissions/save failures can be swallowed. No OS-backed vault or recovery. |
| Records | `cert_generator.generate` → unsigned JSON with sender/hash/key ID → `pdf_export.export`; labels say unsigned local record, no authenticity/delivery proof. |
| Errors/logs | named exceptions → Qt signals/dialogs; some persistence errors swallowed. Portal logs capability IDs; no unified redaction. Current IMAP source has no debug print calls despite the audit narrative. |

## Boundaries and disposition

KEEP transport TLS verification, header-first retrieval, Qt UI foundations, OS
randomness and useful exception boundaries/tests. REFACTOR UI orchestration,
session, OAuth/storage, safe rendering and accurate delivery states. REPLACE
production TQR/MIME, unauthenticated directory trust and sender-owned recipient
keys. REMOVE server-decrypting portal from eventual production. INVESTIGATE exact
OpenPGP profile/provider, licenses, OS vault and independent interoperability.

`UI → transport/crypto/KME/portal/records` describes the current implementation.
It is not yet the intended `UI/infrastructure → application → domain/policy` design.
Qt, globals and dicts still couple operations. M1 introduces no wholesale tree move,
new packet format, recipient-identity scheme or storage migration.

## M1 changes and limits

Tests start in temporary state before collection, reset state per test, disallow
real sockets and reject skips. Native loading is explicit and version/source checked;
see ADR 002. Simulator HTTP status includes simulated provenance. Main/UI labels
state development-only status. Legacy MIME types and crypto fields remain compatible;
the human-readable preamble/labels are corrected. Historical native 0.14.1 binary
compatibility remains unverified because that artifact is unavailable.

No independent recipient E2E, real mail provider, Firestore transaction, real QKD,
platform keystore, fuzz campaign, signed package or release has been validated by
these local characterization tests. Those are separate milestone gates.
