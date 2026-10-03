# QuMail 1.0 architecture — actual development baseline

Status: prototype, not approved for confidential production use. Specification:
root-level research Markdown, §§3–18 and 38–54 (PDF is a reference copy).
See IMPLEMENTATION_STATUS.md and ADRs.
The original “100% complete” and “v2” narrative did not establish release evidence.

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
