# QuMail Module 1.2 — Live Google Acceptance Plan & Technical Assessment

**Project:** QuMail  
**Milestone:** M7 — Live Google Acceptance  
**Previous Milestone:** Module 1.1 (Desktop Launch Handoff & Filesystem Path Resolution — QM-BUG-001) [ACCEPTED & CLOSED]  
**Technical Authority:** ChatGPT — Senior Software Engineer, Software Architect & Security Lead  
**Project Owner:** Mohammed Uzair Shaikh  
**Branch:** `codex/m7-google-live-acceptance`  
**Baseline Commit:** `5c27585` (derived from accepted `42f447d`)  
**Status:** Acceptance Plan Prepared · Live Execution Deferred Awaiting Authority Approval  

---

## 1. Formal Milestone Transition & Provenance

### 1.1 Module 1.1 Formal Acceptance
Module 1.1 (`QM-BUG-001`) resolved the desktop launcher and filesystem visibility divergence on the Windows platform:
- Implemented robust directory and file preflight validation in `tools/start_google_acceptance.ps1`.
- Added `-DryRun` and `-SettingsOnly` isolation modes with strict mutual exclusion against `-EnableGmailSubmit`.
- Verified visible console host configuration in `tmp/m7/QuMail-Desktop-DryRun.lnk`.
- Verified zero socket connections and zero database creation in preflight dry-run.
- Formal owner verification succeeded on Windows 11 desktop.
- Accepted Checkpoints: `42f447d` and follow-up regression test commit `5c27585` on `codex/m7-desktop-handoff`.

### 1.2 Outstanding Technical Debt
- **`QM-ERR-001` (Deferred):** Coarse error classification in `IdentityService.unlock()`, which maps filesystem `sqlite3.OperationalError` to `BoundaryError(Code.STORE)`. Deliberately deferred to post-acceptance refactoring.

### 1.3 Module 1.2 Working Branch
In accordance with engineering discipline, branch `codex/m7-google-live-acceptance` was created from `5c27585` to isolate Module 1.2 acceptance planning and testing without mutating the accepted Module 1.1 branch.

---

## 2. Technical Architecture & Source Inventory

| Subsystem | Primary Source Files | Component Responsibilities | Implementation State | Verification Status |
|---|---|---|---|---|
| **OAuth Flow & Callback** | `transport/bounded_google.py`<br>`transport/development_google.py`<br>`transport/bounded_worker.py`<br>`transport/network_worker.py` | Loopback HTTP listener (`127.0.0.1:<port>`), PKCE (S256), state/nonce verification, browser launch via `webbrowser.open()`, isolated subprocess IPC. | Complete (Modern) | Unit tests passed (14/14 in `test_google_diagnostics.py`). Live browser callback tested historically; full live acceptance pending. |
| **Token Verification & Clock Skew** | `experiments/m3/identity.py`<br>`transport/development_google.py` | Google ID token JWT verification against Google JWKS; audience, issuer, subject, nonce, email match; bounded <=20s wait for token-time skew. | Complete (Modern) | Unit tests passed. Live Google token-time verification resolved via retry loop. |
| **Identity Service & Session** | `core/identity_service.py`<br>`core/account_session.py`<br>`core/settings_operations.py` | Account lifecycle state machine, generation tickets, immutable snapshots, thread pool delegation, synchronized reservation. | Complete (Modern) | 54 M3 regression tests passing. Tested in headless desktop mode. |
| **Vault & Secure Store** | `experiments/m3/vault.py`<br>`experiments/m3/secure_store.py`<br>`experiments/m3/types.py` | AES-256-GCM encrypted SQLite vault (`accounts` table), per-account AAD revisions, Windows Credential Manager master key custody (`CredWriteW`/`CredReadW`). | Complete (Modern) | Passes with live user logon token. Blocked in headless sandbox. |
| **PGP/MIME Cryptography** | `experiments/m5/mime.py`<br>`experiments/m5/services.py`<br>`experiments/m5/provider.py` | RFC 3156 / RFC 9788 combined PGP/MIME encryption, Sequoia PGP native helper (`qumail-m5-provider.exe`), strict limits (3 recipients, 8 KiB body, 16 KiB attachments). | Complete (Modern) | PGP/MIME verification passing in M5 suite. |
| **Durable Outbox State Machine** | `experiments/m4/services.py`<br>`experiments/m4/model.py`<br>`experiments/m4/codec.py` | Durable state progression: `DRAFT` → `PREPARED` → `SUBMITTING` → `ACCEPTED`/`FAILED`/`UNKNOWN`. Strict crash recovery and duplicate send prevention. | Complete (Modern) | 12 M4 durability tests passing. |
| **SMTP Transport** | `mailbox_client/smtp.py`<br>`experiments/m4/smtp_transport.py`<br>`mailbox_client/connection.py` | `smtp.gmail.com:587`, STARTTLS (TLS 1.2+), XOAUTH2 SASL authentication, RFC 7628 empty challenge handling, line limits. | Complete (Modern) | Tested against loopback TLS fixtures; live Gmail submission pending. |
| **IMAP Client & PEEK** | `mailbox_client/gmail.py`<br>`mailbox_client/service.py`<br>`mailbox_client/connection.py` | `imap.gmail.com:993`, implicit TLS, XOAUTH2 SASL, readonly `EXAMINE`, `BODY.PEEK` header/message retrieval, explicit `UID STORE` for seen flags. | Complete (Modern) | Tested against mock IMAP fixtures; live Gmail retrieval pending. |
| **UI Boundaries** | `ui/mailbox_window.py`<br>`ui/identity_settings.py`<br>`ui/mail_actions.py` | Dark palette PyQt6 desktop UI, accessible names, strong focus policies, asynchronous worker polling, zero plaintext caching. | Complete (Modern) | Unit and UI tests passing (42/42 in `tests/`). |

---

## 3. Technical Investigation Findings

### 3.1 OAuth Architecture & RFC Compliance
1. **Flow Type:** Implements RFC 8252 (OAuth 2.0 for Native Apps) Authorization Code Grant using a local loopback interface (`http://127.0.0.1:<random-port>/`).
2. **PKCE (RFC 7636):** Mandatory S256 code challenge and verifier auto-generated by `google_auth_oauthlib.flow.InstalledAppFlow`.
3. **State & Nonce:** Generates 256-bit cryptographic tokens via `secrets.token_urlsafe(32)`. State verified on loopback HTTP callback via constant-time `secrets.compare_digest()`. Nonce embedded in Google ID token and verified during JWT decoding.
4. **Host & Path Validation:** Loopback HTTP server (`Loopback` in `transport/development_google.py`) validates that the incoming HTTP request `Host` header strictly matches `127.0.0.1:<port>` and path is `/`. Probes with mismatched Host or path are rejected with HTTP 400.
5. **Scopes:** Requested scopes are strictly bounded:
   - `openid` (ID token identity)
   - `https://www.googleapis.com/auth/userinfo.email` (user profile email)
   - `https://mail.google.com/` (full Gmail IMAP/SMTP access; required by Google for XOAUTH2)
6. **Publishing Status & Test Users:** Google OAuth application is configured in Google Cloud Console in **Testing** mode. Under Google policy, only pre-registered **Test Users** can complete authorization; all other accounts are rejected with `Error 403: access_denied`.

### 3.2 Credential and Token Lifecycle
1. **Initial Token Exchange:** Handled over direct TLS to `https://oauth2.googleapis.com/token` by `flow.fetch_token()`.
2. **Vault Encryption:** Tokens (`access_token`, `refresh_token`, `expiry`, `scopes`) are encrypted inside the account record using AES-256-GCM. The encryption key is protected by a 256-bit vault master key held in Windows Credential Manager (`QuMail M3 local vault`).
3. **Zero-Leakage Logging:** `Loopback.log_message` is overridden to a no-op; authorization codes, callback URLs, and bearer tokens are never printed to terminal or written to log files.
4. **Token Refresh:** Handled automatically in `Credentials.resolve()` when `expiry <= time.time() + 60`. Calls `GoogleAuthorization.refresh()` inside a bounded worker, validates the new token against `https://openidconnect.googleapis.com/v1/userinfo`, updates the vault under SQLite transaction, and increments the account revision.
5. **Revocation & Expiration:** If a refresh token is revoked or invalidated, `Credentials.resolve()` raises `Failure(Code.AUTH)`, and the UI presents an actionable error prompting reauthorization.

### 3.3 Gmail Transport & Message Workflow
1. **Composition & Validation:** `experiments/m5/mime.py` enforces qualified limits: max 3 recipients, max 8 KiB body, max 4 attachments / 16 KiB total, Bcc disallowed.
2. **PGP/MIME Packaging:** Encapsulates the message using Sequoia PGP native provider (`qumail-m5-provider.exe`). Generates inner encrypted MIME part and outer unencrypted transport envelope with fixed subject `Encrypted message`.
3. **Durable Persistence:** The prepared MIME payload is serialized and durably committed to the SQLite vault (`State.PREPARED`) before any network socket is opened. The unencrypted draft is deleted upon preparation.
4. **SMTP XOAUTH2 Submission:** `SMTPSubmission.submit()` connects to `smtp.gmail.com:587`, establishes TLS 1.2+ via STARTTLS, formats SASL XOAUTH2 payload (`user=<addr>\x01auth=Bearer <token>\x01\x01`), sends `AUTH XOAUTH2`, and submits `MAIL FROM`, `RCPT TO`, and `DATA`.
5. **Ambiguous Delivery Handling:** If network drops after `DATA` is transmitted, the submission state transitions to `Outcome.UNKNOWN`. Duplicate sending is prevented by blocking retries unless the owner explicitly acknowledges duplicate risk.

### 3.4 Two-Account Isolation
1. **Vault Record Separation:** Account A and Account B are stored in separate rows in the SQLite `accounts` table, keyed by independent `AccountId` UUIDs. Each row is encrypted under AES-GCM with separate authenticated data (AAD) incorporating its specific `account_id` and `revision`.
2. **Session Lease Protection:** `AccountAccess.select(context)` issues an ephemeral, epoch-bound `Lease`. Any background worker checking an outdated lease is rejected with `Failure(Error.ACCOUNT)`.
3. **UI Switching Isolation:** Selecting a different account in `MailboxWindow` immediately calls `self.cancel()`, clears opened plaintext, drops attachments, resets displayed signers, and terminates active thread futures. Cross-account data leakage is architecturally prohibited.

---

## 4. Security Assessment & Risk Classification

| Issue ID | Severity | Category | Description & Source Evidence | Practical Impact | Remediation & Mitigation | Blocks Live Acceptance? |
|---|---|---|---|---|---|---|
| **QM-SEC-002** | **High** | Operational / OAuth | Google Cloud OAuth App in "Testing" Mode. Google blocks any Google account not explicitly registered in Google Cloud Console under "Test Users" with `Error 403: access_denied`. | If Account A or B is omitted from Test Users, browser authorization fails closed immediately. | Owner must verify both A and B are added in Google Cloud Console before running Phase 2. | **Yes** (Operational Precondition) |
| **QM-SEC-003** | **Medium** | Clock / Identity | Windows Desktop Clock Skew. `google.oauth2.id_token.verify_oauth2_token()` enforces zero clock skew on token issuance time. If Windows clock is skewed behind Google by >20s, verification permanently fails with `Code.GOOGLE_CLOCK`. | Authorization code consumed but token rejected; account enrollment fails. | `verify_google_token()` already provides a bounded 20s retry. Owner must synchronize Windows date/time before test. | No (Mitigated in code) |
| **QM-SEC-004** | **Low** | UI / Deception | IMAP Transport Claims vs Authenticated Inner Content. Mailbox table displays transport `From` and `Subject` headers before decryption. Malicious actor could spoof outer headers. | Untrusted outer headers could deceive user if trusted blindly. | UI explicitly appends `(transport claim)` to table column headers and displays cryptographic status only after verified PGP decrypt. | No |
| **QM-SEC-005** | **Low** | Usability / Process | Single-Operator Fingerprint Verification Limitation. Testing both A and B on one machine compares fingerprints across Settings views rather than an out-of-band communication channel. | Proves software pinning logic but does not simulate real-world out-of-band trust establishment. | Documented explicitly as a controlled single-operator test constraint; not claimed as third-party review. | No |
| **QM-ERR-001** | **Medium** | Diagnostics | Broad Exception Handling in `IdentityService.unlock()`. Collapses `sqlite3.OperationalError` into generic `BoundaryError(Code.STORE)` ("Vault/storage unavailable"). | Diagnostic ambiguity if database file is corrupted or locked. | Mitigated by Module 1.1 launcher preflight checks. Full exception typing logged for future refactoring. | No (Deferred) |

---

## 5. Test Environment Prerequisites & Safeguards

### 5.1 Account Setup Requirements
- **Account A (Sender):** Dedicated test Google account (e.g. `test-a@gmail.com`). Must be added to Google Cloud Console Test Users.
- **Account B (Recipient):** Dedicated test Google account (e.g. `test-b@gmail.com`). Must be added to Google Cloud Console Test Users.
- **Strict Prohibition:** Never use personal, production, or high-value Google accounts for this testing.

### 5.2 Local Application Configuration
- **Google Client JSON:** Pinned Desktop application credentials file located at:
  `C:\Users\uzx\Downloads\client_secret_953431543574-6oapvj8m0nbu3e71mdd3kb2r45atgjfh.apps.googleusercontent.com.json`
- **Target Vault Path:** Pinned acceptance vault:
  `%LOCALAPPDATA%\QuMailAcceptance\2026-11-01-desktop\acceptance.sqlite`
- **Working Tree:** Pinned to branch `codex/m7-google-live-acceptance`.

### 5.3 Secrets & Privacy Rules
- **Zero Secrets in Chat/Logs:** Never paste client secrets, access tokens, refresh tokens, passwords, private keys, or raw callback URLs.
- **Redacted Reporting:** Test reports must contain only sanitized UI state strings, account aliases (A/B), and cryptographic fingerprints.

---

## 6. Module 1.2 Comprehensive Acceptance Matrix

| Test ID | Requirement | Preconditions | Procedure | Expected Result | Evidence to Collect | Pass/Fail Criteria | Requires Owner Approval? |
|---|---|---|---|---|---|---|---|
| **M12-PRE-01** | Launcher Live Submit Validation | Client JSON exists; parent directory exists; Python venv valid. | Execute `tools/start_google_acceptance.ps1` with `-AllowNewVault -EnableGmailSubmit -CheckOnly`. | Preflight passes; console reports client valid, new-vault mode, live submission mode enabled; no DB created. | Console log output. | Exit code 0; exactly matches preflight signature. | No |
| **M12-VAULT-01** | Clean Acceptance Vault Creation | Vault file does not exist; launcher started in live submit mode. | Launch QuMail; open Settings; click **"Create vault"**. | Vault initializes in `%LOCALAPPDATA%\...\acceptance.sqlite`; status transitions from `Locked` to `Unlocked · sending disabled`. | File Explorer confirmation of SQLite file; UI status label. | SQLite DB created with tables `vault` and `accounts`; master key in Credential Manager. | **Yes** (Creates persistent state) |
| **M12-AUTH-01** | Account A Google OAuth Enrollment | Vault unlocked; Account A configured in Google Cloud Test Users. | Enter Account A address in Settings; click **"Connect Google"**; complete browser consent within 180s. | Browser displays "Return to QuMail"; QuMail Settings displays Account A address, `active` lifecycle, and root fingerprint. | Sanitized UI status; account list contains A. | Account A row created in `accounts` table with encrypted OAuth tokens. | **Yes** (Live OAuth handshake) |
| **M12-AUTH-02** | Account B Google OAuth Enrollment | Account A enrolled; Account B configured in Google Cloud Test Users. | Enter Account B address in Settings; click **"Connect Google"**; complete browser consent within 180s. | Browser displays "Return to QuMail"; Settings account selector now lists both A and B independently. | Sanitized UI status; account selector contains A and B. | Separate Account B row created in `accounts` table; A and B root fingerprints differ. | **Yes** (Live OAuth handshake) |
| **M12-TOKEN-01** | Token Refresh Verification | Accounts A and B enrolled; tokens stored in vault. | Select Account A; click **"Refresh Google"**. Repeat for Account B. | Bounded worker queries Google userinfo endpoint; token refreshed; status displays `Committed.` | UI status label; token expiry timestamp updated in DB. | Refresh succeeds without re-opening browser consent. | **Yes** (Live Google network call) |
| **M12-TRUST-01** | Public Certificate Export & Mutual Trust Pinning | Accounts A and B enrolled in vault. | Select A → **"Export my public certificate"** to `A-public.asc`. Select B → export to `B-public.asc`. Select A → import `B-public.asc` and verify fingerprint. Select B → import `A-public.asc` and verify fingerprint. | Certificates exported without private keys; contacts table displays verified root fingerprints. | Exported `.asc` files; Contacts table rows showing `pinned` trust. | Mutual fingerprints match source account displays exactly. | **Yes** (Local filesystem file creation) |
| **M12-IMAP-01** | Header Retrieval via IMAP PEEK | Account A selected; Settings kept open (vault unlocked). | In Mailbox window, click **"Refresh headers"**. Repeat for Account B. | IMAP connects to `imap.gmail.com:993`; retrieves headers via `BODY.PEEK`; displays headers in table; read flags unchanged. | Mailbox header list row count; status text. | Zero message state mutation; unread messages remain unread on server. | **Yes** (Live IMAP query) |
| **M12-SEND-01** | Protected A → B Email Submission | Account A selected; B's certificate verified; attachment prepared. | Compose message To: B; attach `acceptance-note.txt` (<16 KiB); click **"Verify recipients"** → **"Save encrypted draft"** → **"Prepare saved"** → **"Submit once"**. | Outbox transitions `DRAFT` → `PREPARED` → `SUBMITTING` → `ACCEPTED`. SMTP sends over TLS to `smtp.gmail.com:587`. | Outbox table showing `Accepted` with attempt count 1. | Message accepted by Google SMTP; digest logged; draft purged. | **Yes** (Live external email send) |
| **M12-RECV-01** | Recipient Verification & Attachment Export | Message sent in M12-SEND-01; Account B selected. | In Mailbox, select Account B; click **"Refresh headers"**; select arrival; click **"Open selected"**; click **"Save attachment as…"**. | Outer subject is `Encrypted message`; inner decrypted subject/body matches A's message; signature valid; attachment exported intact. | Decrypted UI view; binary diff between sent and exported attachment. | Decrypted content matches sent content exactly; SHA-256 digests match. | **Yes** (Filesystem export) |
| **M12-SEND-02** | Protected B → A Reply & Forward | Original message opened in Account B. | Click **"Reply"**; add reply text; save, prepare, and submit once. Reopen original; click **"Forward"**; select A; save, prepare, and submit once. | Both submissions transition to `ACCEPTED`. Account A refreshes headers and decrypts both messages successfully. | Outbox status for reply and forward; Account A inbox view. | Two distinct messages received by A; verified references established. | **Yes** (Live external email sends) |
| **M12-FLAG-01** | Explicit Read/Unread State Mutation | Test message present in mailbox. | Select message; click **"Mark read"**; click **"Refresh headers"** (verify read). Click **"Mark unread"**; click **"Refresh headers"** (verify unread). Click **"Open selected"** (verify remains unread). | Server flags updated only upon explicit command; opening message preserves prior unread state. | Mailbox table `Read state` column. | `\Seen` flag matches explicit user commands exactly. | **Yes** (Live IMAP mutation) |
| **M12-ISOL-01** | Active Account Switching Isolation | Mailbox open with Account A message displayed. | Switch account selector from A to B while message is open. | Plaintext body, attachments, and security label clear immediately; Account B headers load; no cross-account residue. | Visual inspection of mailbox UI fields. | Zero leakage of A's plaintext or tokens into B's session. | No |
| **M12-ISOL-02** | Vault Lock & Cancellation Isolation | Operations running or completed. | Click **"Lock"** in Mailbox window. | Vault locks immediately; lease invalidated; header/compose buttons disable; cached keys purged from memory. | UI control enable states; `status` displays locked. | Application cannot perform mail operations until re-unlocked. | No |
| **M12-ISOL-03** | Restart Durability & Outbox Reconciliation | Outbox contains accepted/sent records. | Close QuMail; restart via dry-run or live launcher; unlock vault. | All historical outbox operations, attempts, and receipts remain intact; no duplicate submission triggered. | Outbox table inspection upon restart. | Re-read from SQLite matches pre-restart state bit-for-bit. | No |

---

## 7. Staged Implementation & Testing Roadmap

```
  Phase 1: Environment & Preflight Validation
     │   • Verify Google Cloud Console Test Users (Accounts A & B)
     │   • Run automated test suite & launcher preflight checks
     ▼
  Phase 2: Vault Initialization & Account Enrollment (Authorized by Owner)
     │   • Create disposable acceptance vault
     │   • Enroll Account A via Google OAuth loopback
     │   • Enroll Account B via Google OAuth loopback
     ▼
  Phase 3: Cryptographic Trust Establishment
     │   • Export A and B public certificates
     │   • Mutually import and verify root fingerprints
     ▼
  Phase 4: Live Mailbox Verification & Controlled Sends
     │   • IMAP PEEK header retrieval (A & B)
     │   • One A → B protected email send (SMTP XOAUTH2)
     │   • Recipient B verification, PEEK read, attachment export
     │   • Two B → A sends (Reply and Forward)
     ▼
  Phase 5: State & Isolation Stress Verification
     │   • Explicit flag toggling (Read/Unread)
     │   • Account switching & lock clearing verification
     │   • Restart durability inspection
```

---

## 8. Go / No-Go Recommendation

### Recommendation: **READY FOR CONTROLLED LIVE ACCEPTANCE (SUBJECT TO PRECONDITIONS)**

#### Rationale & Evidence:
1. **Architectural Readiness:** The modern QuMail codebase (`experiments/m3` through `m6`, `mailbox_client/`, `transport/`) contains complete, audited, and tested implementations of Google OAuth (PKCE S256), token lifecycle management, PGP/MIME encryption, durable outbox sequencing, and Gmail SMTP/IMAP transports.
2. **Regression Integrity:** All 42 unit and compatibility tests in `tests/` pass with zero failures. All 14 Google diagnostic tests in `experiments/m6/test_google_diagnostics.py` pass. Launcher preflight tests pass 11/11.
3. **Sandbox & Desktop Decoupling:** Module 1.1 successfully decoupled the launcher from tool environment path confusion. The desktop shortcut and launcher script have been verified on the owner's Windows desktop.
4. **Safety Boundaries:** Gmail submission is disabled by default and requires explicit CLI opt-in (`-EnableGmailSubmit`). Outbox durability guarantees that duplicate sending is prevented even under network interruptions.

#### Preconditions for Live Execution:
1. **Owner Confirmation of Test Users:** Owner must confirm in Google Cloud Console that both designated test accounts (A and B) are added under **OAuth Consent Screen → Test Users**.
2. **Owner Presence for Browser Consent:** Owner must be present at the Windows desktop to complete the Google OAuth consent prompts in their default browser for Account A and Account B.
3. **Technical Lead Authorization Directive:** Execution must not commence until the Technical Lead issues the formal implementation and execution directive for Module 1.2.
