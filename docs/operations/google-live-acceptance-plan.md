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

For complete runtime call graphs and source-code integration proofs, see [`docs/operations/google-integration-verification.md`](google-integration-verification.md).

### 6.1 State and Authorization Tiers
Every acceptance test is classified into one of six operational tiers:
- **Tier 1:** Static or offline validation (No application launch or side effects).
- **Tier 2:** Local application state modification (In-memory UI state, window traversal, draft editing).
- **Tier 3:** Credential or vault modification (Disk creation of SQLite database, Credential Manager write, file export).
- **Tier 4:** Live Google read operation (HTTPS userinfo query, IMAP PEEK read, OAuth handshake).
- **Tier 5:** Live Google write operation (IMAP `\Seen` flag mutation).
- **Tier 6:** External email transmission (Live SMTP submission to `smtp.gmail.com:587`).

### 6.2 Acceptance Matrix

| Test ID | Tier | Operation Category | Preconditions | Procedure | Expected Observable Result | Pass/Fail Criteria | Requires Owner Approval? |
|---|---|---|---|---|---|---|---|
| **M12-PRE-01** | **Tier 1** | Local Preflight | Client JSON downloaded; Python venv valid. | Run `start_google_acceptance.ps1` with `-AllowNewVault -EnableGmailSubmit -CheckOnly`. | Console reports client valid, new-vault mode, live submission mode enabled; zero DB created; no network calls. | Exit code 0; exactly matches preflight signature. | No |
| **M12-VAULT-01** | **Tier 3** | Vault Creation | Vault file absent; launched with `-EnableGmailSubmit`. | Launch QuMail; open Settings; click **"Create vault"**. | SQLite created in `%LOCALAPPDATA%\...\acceptance.sqlite`; Settings status shows `Unlocked · sending disabled`; Mailbox banner shows `Gmail submission explicitly enabled`. | SQLite DB initialized with `vault` and `accounts` tables; master key stored in Credential Manager. | **Yes** (Creates persistent state) |
| **M12-AUTH-01** | **Tier 4** | OAuth Enrollment (A) | Vault unlocked; Account A in Google Test Users. | Enter Account A address in Settings; click **"Connect Google"**; complete browser consent within 180s. | Browser shows "Return to QuMail"; Settings displays Account A address, `active` lifecycle, and root fingerprint. | Account A row created in `accounts` table with encrypted OAuth tokens. | **Yes** (Live OAuth handshake) |
| **M12-AUTH-02** | **Tier 4** | OAuth Enrollment (B) | Account A enrolled; Account B in Google Test Users. | Enter Account B address in Settings; click **"Connect Google"**; complete browser consent within 180s. | Browser shows "Return to QuMail"; Settings account selector lists both A and B independently. | Separate Account B row created in `accounts` table; A and B root fingerprints differ. | **Yes** (Live OAuth handshake) |
| **M12-TOKEN-01** | **Tier 4** | Proactive Token Refresh | Accounts A and B enrolled; tokens in vault. | Select Account A; click **"Refresh Google"**. Repeat for Account B. | Bounded worker queries Google userinfo endpoint; token refreshed; status displays `Committed.` | Token expiry timestamp updated in DB without re-opening browser. | **Yes** (Live Google call) |
| **M12-TOKEN-02** | **Tier 4** | On-Demand Auto Renewal | Access token near expiry (`<= 60s`). | In Mailbox, click **"Refresh headers"** with near-expired access token. | `Credentials.resolve()` detects near-expiry, automatically refreshes token via Google, updates vault, and proceeds to IMAP. | IMAP headers load without error; vault OAuth expiry timestamp updated. | **Yes** (Live Google call) |
| **M12-TOKEN-03** | **Tier 4** | Expired Refresh Recovery | Refresh token simulated as expired / revoked. | Select account; click **"Refresh Google"** (fails with `Code.AUTH`). Click **"Reauthorize selected"**; complete browser consent. | UI displays reauthorization prompt; browser consent restores fresh refresh token; root key and account ID preserved intact. | Account re-enrolled under exact same `AccountId` and PGP root. | **Yes** (Live OAuth handshake) |
| **M12-TRUST-01** | **Tier 3** | PGP Trust Pinning | Accounts A and B enrolled in vault. | Select A → export `A-public.asc`. Select B → export `B-public.asc`. Select A → import `B-public.asc` and pin fingerprint. Select B → import `A-public.asc` and pin fingerprint. | Certificates exported without private keys; Contacts table displays verified root fingerprints with `pinned` trust. | Mutual fingerprints match source account displays exactly. | **Yes** (Local file writes) |
| **M12-IMAP-01** | **Tier 4** | IMAP PEEK Header Read | Account A selected; vault unlocked. | In Mailbox window, click **"Refresh headers"**. Repeat for Account B. | IMAP connects to `imap.gmail.com:993`; fetches headers via `BODY.PEEK`; displays headers; read flags unchanged. | Zero message state mutation; unread messages remain unread on server. | **Yes** (Live IMAP call) |
| **M12-SEND-01** | **Tier 6** | Protected Email Send | Account A selected; B's key pinned; attachment ready. | Compose To: B; attach `acceptance-note.txt` (<16 KiB); click **"Verify recipients"** → **"Save encrypted draft"** → **"Prepare saved"** → **"Submit once"**. | Outbox transitions `DRAFT` → `PREPARED` → `SUBMITTING` → `ACCEPTED`. SMTP sends over TLS to `smtp.gmail.com:587`. | Outbox displays `Accepted` with attempt count 1; message accepted by Gmail SMTP. | **Yes** (Live email transmission) |
| **M12-RECV-01** | **Tier 4** | Recipient PEEK & Decrypt | Message sent in M12-SEND-01; Account B selected. | Select Account B; click **"Refresh headers"**; select arrival; click **"Open selected"**; click **"Save attachment as…"**. | Outer subject is `Encrypted message`; inner decrypted subject/body matches A's message; signature valid; attachment exported intact. | Decrypted content matches sent content exactly; SHA-256 digests match. | **Yes** (Filesystem export) |
| **M12-SEND-02** | **Tier 6** | Protected Reply & Forward | Original message opened in Account B. | Click **"Reply"**; add reply text; save, prepare, and submit once. Reopen original; click **"Forward"**; select A; save, prepare, and submit once. | Both submissions transition to `ACCEPTED`. Account A refreshes headers and decrypts both messages successfully. | Two distinct messages received by A; verified references established. | **Yes** (Live email transmission) |
| **M12-FLAG-01** | **Tier 5** | IMAP Flag Mutation | Test message present in mailbox. | Select message; click **"Mark read"** → refresh (verify read). Click **"Mark unread"** → refresh (verify unread). Click **"Open selected"** → refresh (verify remains unread). | Server flags updated only upon explicit command; opening message preserves prior unread state. | `\Seen` flag matches explicit user commands exactly. | **Yes** (Live IMAP mutation) |
| **M12-ISOL-01** | **Tier 2** | Account Switch Isolation | Mailbox open with Account A message displayed. | Switch account selector from A to B while message is open. | Plaintext body, attachments, and security label clear immediately; Account B headers load; no cross-account residue. | Zero leakage of A's plaintext or tokens into B's session. | No |
| **M12-ISOL-02** | **Tier 2** | Vault Lock Isolation | Operations running or completed. | Click **"Lock"** in Mailbox window. | Vault locks immediately; lease invalidated; header/compose buttons disable; cached keys purged from memory. | Application cannot perform mail operations until re-unlocked. | No |
| **M12-ISOL-03** | **Tier 3** | Restart Durability | Outbox contains accepted/sent records. | Close QuMail; restart via live launcher; unlock vault. | All historical outbox operations, attempts, and receipts remain intact; no duplicate submission triggered. | Re-read from SQLite matches pre-restart state bit-for-bit. | No |


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
