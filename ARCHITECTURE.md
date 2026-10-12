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
