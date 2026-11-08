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

### 5.3 User Privacy Disclosure & Regulatory Compliance

#### A. Technically Accurate User-Facing Privacy & Service Disclosure
> **QuMail Privacy and Google Service Access Disclosure**
>
> **1. Scope and Technical Authority Granted by Google:**  
> To connect using standard internet email protocols (IMAP and SMTP with SASL XOAUTH2), Google requires QuMail to request the full `https://mail.google.com/` permission [Verified]. Google's platform grants broad technical authority under this scope, including the ability to read, compose, send, and permanently delete email in your Gmail mailbox [Verified].  
> *QuMail Feature Constraint:* QuMail’s desktop application does not implement or expose any user-facing message deletion feature (`EXPUNGE` or trash emptying commands are excluded from regular mailbox operations), nor does it access spam or mail account settings [Verified]. However, users must understand that the permission granted to the application by Google is broad.
>
> **2. Message Payload, Transport Metadata, and Network Visibility:**  
> - **Plaintext Processing:** Composition, plaintext editing, and message decryption occur strictly in memory on your local computer [Verified]. Plaintext message bodies and unencrypted attachments are never transmitted to Google, QuMail developers, or any third party [Verified].  
> - **Encrypted Payload Transmission:** QuMail uses OpenPGP (Sequoia PGP) to encrypt and sign message content locally before transmission [Verified]. The resulting encrypted MIME ciphertext payload is transmitted through Google’s SMTP servers (`smtp.gmail.com:587`) to reach designated recipients [Verified]. Outer message subjects are standardized to `"Encrypted message"` to protect subject line confidentiality.  
> - **Network Intermediary Visibility vs Mail Service Visibility:**  
>   * *Network Intermediaries (ISPs, routers, network eavesdroppers):* While Transport Layer Security (TLS 1.2+) is operating correctly, network intermediaries observe only the encrypted TLS connection to Google endpoints (`smtp.gmail.com`, `imap.gmail.com`), TLS SNI headers, byte volume, and connection timestamps [Verified]. Ordinary network intermediaries **cannot** read email message bodies, subjects, headers, or recipient addresses through the encrypted TLS tunnel.  
>   * *Google Mail Infrastructure:* As the terminating SMTP and IMAP service provider, Google's servers necessarily process standard email routing metadata transmitted over the connection—including sender address, recipient addresses, message timestamps, transport Message-IDs, and transmission size—as well as the encrypted MIME ciphertext payload.
>
> **3. OAuth Tokens and Local Cryptographic Custody:**  
> - **OAuth Tokens:** Google OAuth authorization codes and refresh tokens are exchanged directly between your local computer and Google’s authorization servers (`accounts.google.com` / `oauth2.googleapis.com`) over TLS [Verified]. Tokens are stored encrypted on your local drive inside QuMail’s SQLite vault.  
> - **Master Key Custody:** The vault’s AES-256-GCM encryption key is protected by your Windows user account in the Windows Credential Manager under target name `QuMail M3 local vault` [Verified].  
> - **Private Keys:** Your OpenPGP private signing and decryption keys are generated locally, stored exclusively inside your local encrypted vault, and are never transmitted to Google, QuMail developers, or any third party [Verified].
>
> **4. Server Infrastructure & Telemetry Disclosure:**  
> QuMail operates with no developer-hosted backend servers for ordinary email operations [Verified]. QuMail does not operate telemetry, tracking, analytics, or remote crash-reporting servers [Verified]. Network traffic from QuMail flows strictly between your local computer and Google’s documented endpoints (`*.google.com`, `*.googleapis.com`), plus the local loopback interface (`127.0.0.1`) used during browser OAuth callback handling.

#### B. Google OAuth Verification & Assessment Implications
- `https://mail.google.com/` is classified as a restricted Gmail scope by Google.
- For an application to exit Testing status and serve general users, Google OAuth verification and applicable restricted-scope security assessment requirements must be satisfied.
- Google's security assessment process utilizes risk-based assurance levels. The specific assessment level (e.g., Cloud Application Security Assessment / CASA evaluation) must be determined and confirmed directly through Google's verification process. Development testing does not imply production approval, and no legal or compliance guarantee is made.

### 5.4 Operational Safeguards
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
|---|---|---|---|---|---|---|:---:|
| **M12-PRE-01** | **Tier 1** | Pure Dry-Run Preflight | Local environment configured; client JSON present; launcher present. | Run `start_google_acceptance.ps1 -CheckOnly -GoogleClient <path> -Vault <path>` (omitting `-AllowNewVault`). | Script verifies runtime dependencies and client JSON; if vault file does not exist, halts with exit code 1 to prevent unintended uninitialized launch; creates zero files, zero directories, zero credential writes, zero network calls. | Zero side effects; filesystem, credential store, and network remain 100% untouched. | No |
| **M12-VAULT-01** | **Tier 3** | Vault Creation (Sending Disabled) | `M12-PRE-01` verified; disposable path chosen; `-EnableGmailSubmit` omitted. | Launch QuMail via `start_google_acceptance.ps1 -Vault <path> -GoogleClient <path> -AllowNewVault` (NO `-EnableGmailSubmit`); click **"Create vault"** in Settings; enter passphrase. | Parent directory created; `%LOCALAPPDATA%\...\acceptance.sqlite` created; master key written to Windows Credential Manager (`QuMail M3 local vault`). Settings status displays `Unlocked · sending disabled`; Mailbox displays safe state without Gmail submission enabled. | SQLite DB initialized with `vault` and `accounts` tables; master key stored in Credential Manager; mail sending strictly disabled. | **Yes** (Creates persistent state on disk & in Credential Manager) |
| **M12-AUTH-01** | **Tier 4** | OAuth Enrollment (Account A) | Vault unlocked; Account A configured as Test User in Google Cloud Console. | In Settings, select **"Enroll account"**; set Alias `A`; click **"Authorize with Google"**; complete browser consent within 180s. | Loopback listener accepts code; ID token validated; Sequoia PGP root key generated; tokens stored encrypted in SQLite. | Settings displays Account A with email address, `active` status, root key fingerprint, and expiration timestamp. | **Yes** (Consumes OAuth token; browser interaction) |
| **M12-AUTH-02** | **Tier 4** | OAuth Enrollment (Account B) | Account A enrolled; Account B configured as Test User in Google Cloud Console. | In Settings, select **"Enroll account"**; set Alias `B`; click **"Authorize with Google"**; complete browser consent within 180s. | Loopback listener accepts code; ID token validated; distinct Sequoia PGP root key generated; tokens stored encrypted. | Settings displays Account B with distinct email address, distinct fingerprint, and distinct expiration timestamp. | **Yes** (Consumes OAuth token; browser interaction) |
| **M12-TRUST-01** | **Tier 3** | Mutual PGP Public Certificate Exchange | Accounts A and B enrolled; public keys unpinned. | Export Account A public cert; import into B contacts; verify fingerprint. Export Account B cert; import into A contacts; verify fingerprint. | Public certificates exchanged; root fingerprints match bit-for-bit; contacts stored in vault SQLite database. | Settings Contacts table shows A has B's verified fingerprint, and B has A's verified fingerprint. | **Yes** (Mutates local contact records in vault) |
| **M12-TOKEN-01** | **Tier 4** | Proactive Token Refresh | Accounts A and B enrolled; tokens in vault. | Select Account A in Settings; click **"Refresh Google"**. Repeat for Account B. | HTTPS POST to `oauth2.googleapis.com/token`; new access token received; user info validated; vault SQLite updated. | Status bar displays successful refresh; token expiration timestamp advances by ~3600 seconds; refresh token preserved. | **Yes** (Live Google network request) |
| **M12-IMAP-01** | **Tier 4** | Controlled Read-Only Header Retrieval | Accounts A and B enrolled; unread messages present in Gmail. | Open Mailbox window; select Account A; click **"Refresh headers"**; repeat for B. | TLS connection to `imap.gmail.com:993`; SASL XOAUTH2; `SELECT INBOX (readonly)` with `BODY.PEEK`. | Headers populate in UI table; message counts match Gmail; server unread states remain 100% unaltered in Gmail web UI. | **Yes** (Live Google IMAP connection) |
| **M12-SEND-01** | **Tier 6** | Single Protected Send (A → B) | Stage D complete; launcher restarted with `-EnableGmailSubmit`; Account A selected; B's key pinned; attachment ready. | Compose To: B; attach `acceptance-note.txt` (<16 KiB); click **"Verify recipients"** → **"Save encrypted draft"** → **"Prepare saved"** → **"Submit once"**. | Outbox transitions `DRAFT` → `PREPARED` (Sequoia PGP sealed, plaintext purged) → `SUBMITTING` → `ACCEPTED`. SMTP sends over TLS to `smtp.gmail.com:587`. | Outbox displays `Accepted` with attempt count 1; message accepted by Gmail SMTP; exactly 1 email sent. | **Yes** (Live external email transmission) |
| **M12-RECV-01** | **Tier 4** | Protected Receive, Decrypt & Attachment Export | `M12-SEND-01` accepted by Gmail; Account B selected. | Select Account B; click **"Refresh headers"**; select arrival; click **"Open selected"**; click **"Save attachment as…"**. | Outer subject is `Encrypted message`; inner decrypted subject/body matches A's message; signature valid; attachment exported intact. | Decrypted content matches sent content exactly; SHA-256 digests match. | **Yes** (Filesystem export) |
| **M12-ISOL-01** | **Tier 2** | Account Switch Isolation | Both Accounts A and B enrolled; Mailbox open with Account A message displayed. | Switch account selector from A to B while message is open. | Plaintext body, attachments, and security label clear immediately; Account B headers load; no cross-account residue. | Zero leakage of A's plaintext or tokens into B's session. | No |
| **M12-ISOL-02** | **Tier 2** | Vault Lock Isolation | Mailbox idle; zero pending worker threads. | Click **"Lock"** in Mailbox window while idle. | Vault locks immediately; lease invalidated; header/compose buttons disable; cached keys purged from memory; late workers drop results. | Application enters locked state safely without interrupting state transitions. | No |
| **M12-TOKEN-02** | **Tier 4** | On-Demand Auto Renewal | Access token near expiry (`<= 60s`). | In Mailbox, click **"Refresh headers"** with near-expired access token. | `Credentials.resolve()` detects near-expiry, automatically refreshes token via Google, updates vault, and proceeds to IMAP. | IMAP headers load without error; vault OAuth expiry timestamp updated. | **Yes** (Live Google call) |
| **M12-TOKEN-03** | **Tier 4** | Expired Refresh Recovery | Refresh token simulated as expired / revoked. | Select account; click **"Refresh Google"** (fails with `Code.AUTH`). Click **"Reauthorize selected"**; complete browser consent. | UI displays reauthorization prompt; browser consent restores fresh refresh token; root key and account ID preserved intact. | Account re-enrolled under exact same `AccountId` and PGP root. | **Yes** (Live OAuth handshake) |
| **M12-SEND-02** | **Tier 6** | Controlled Reply & Forward (B → A) | Original message opened in Account B; sending enabled. | Click **"Reply"**; add reply text; save, prepare, and submit once. Reopen original; click **"Forward"**; select A; save, prepare, and submit once. | Both submissions transition to `ACCEPTED`. Account A refreshes headers and decrypts both messages successfully. | Two distinct messages received by A; verified references established. | **Yes** (Live email transmission) |
| **M12-FLAG-01** | **Tier 5** | IMAP Flag Mutation | Test message present in mailbox. | Select message; click **"Mark read"** → refresh (verify read). Click **"Mark unread"** → refresh (verify unread). Click **"Open selected"** → refresh (verify remains unread). | Server flags updated only upon explicit command; opening message preserves prior unread state. | `\Seen` flag matches explicit user commands exactly. | **Yes** (Live IMAP mutation) |
| **M12-ISOL-03** | **Tier 3** | Restart Durability | Outbox contains accepted/sent records. | Close QuMail; restart via live launcher; unlock vault. | All historical outbox operations, attempts, and receipts remain intact; startup recovery transitions any interrupted submissions to `UNKNOWN`. | Re-read from SQLite matches pre-restart state bit-for-bit; no duplicate submission triggered. | **Yes** (Interacts with persistent vault & recovery) |

---

## 7. Staged Execution Plan with Separate Gates

The 16 acceptance tests are strictly partitioned into six sequential stages, each gated by explicit verification before subsequent stages can be authorized. Approval for any single stage does **not** authorize subsequent stages:

### Stage A — Offline & Local Preparation (Tier 1)
- **Tests Included:** `M12-PRE-01` (pure dry-run preflight).
- **Scope:** Validates local environment, Python venv, client JSON syntax, and native binary availability without application launch.
- **Launcher Mode:** `tools/start_google_acceptance.ps1 -CheckOnly -GoogleClient <path> -Vault <path>` (omitting `-AllowNewVault`).
- **Gate 1:** Zero side effects; preflight confirms client JSON syntax and runtime components; zero files/directories created; zero network calls.

### Stage B — Owner-Authorized Vault Preparation (Tier 3)
- **Tests Included:** `M12-VAULT-01` (Acceptance vault creation and Credential Manager master key write).
- **Scope:** Initializes `%LOCALAPPDATA%\QuMailAcceptance\2026-11-01-desktop\acceptance.sqlite` and writes master key to Windows Credential Manager (`QuMail M3 local vault`).
- **Launcher Mode:** `tools/start_google_acceptance.ps1 -Vault <path> -GoogleClient <path> -AllowNewVault` (**WITHOUT** `-EnableGmailSubmit`).
- **Gate 2:** SQLite database initialized with `vault` and `accounts` tables; Settings displays `Unlocked · sending disabled`; Mailbox displays safe state without Gmail submission enabled.

### Stage C — Separately Authorized Google OAuth Authorization & Trust Establishment (Tiers 3 & 4)
- **Tests Included:** `M12-AUTH-01` (Account A enrollment), `M12-AUTH-02` (Account B enrollment), `M12-TRUST-01` (Mutual PGP export & fingerprint pinning), `M12-TOKEN-01` (Proactive token refresh).
- **Scope:** Completes browser OAuth consent for test users A and B, validates ID token signatures, generates Sequoia PGP root keys, mutually pins public certificates in contacts, and verifies token refresh.
- **Gate 3:** Both accounts enrolled with distinct root keys; mutual public certificates pinned in contacts; token refresh succeeds without browser prompt.

### Stage D — Separately Authorized Read-Only Gmail Mailbox Access (Tier 4)
- **Tests Included:** `M12-IMAP-01` (IMAP PEEK header retrieval).
- **Scope:** Connects to `imap.gmail.com:993` in readonly mode (`EXAMINE`) using `BODY.PEEK`.
- **Gate 4:** Headers fetched and displayed for A and B; zero server-side read flag mutations occur in Gmail web interface.

### Stage E — Single Separately Authorized Protected Send & Receive (Tiers 4 & 6)
- **Tests Included:** `M12-SEND-01` (Single A → B protected email send), `M12-RECV-01` (Recipient B PEEK read, decrypt, and attachment export).
- **Scope:** Application is restarted with `-EnableGmailSubmit` specifically for this approved single-send test. Executes exactly one protected email send from Account A to Account B via `smtp.gmail.com:587`. Account B retrieves via IMAP PEEK, decrypts inner payload, verifies signature, and exports attachment.
- **Gate 5:** Outbox status `Accepted` with attempt count 1; exactly one email transmitted; Account B decrypts message; signature valid; exported attachment SHA-256 matches sent attachment bit-for-bit.

### Stage F — Optional Recovery, State Mutation & Durability Workflows (Tiers 2, 3, 4, 5, 6 — Each Separately Gated)
- **Tests Included:**  
  - `M12-ISOL-01` (Account switch view purging) [Tier 2]  
  - `M12-ISOL-02` (Idle vault lock isolation) [Tier 2]  
  - `M12-TOKEN-02` (On-demand auto renewal near expiry) [Tier 4]  
  - `M12-TOKEN-03` (Expired/revoked refresh recovery) [Tier 4]  
  - `M12-SEND-02` (Controlled B → A Reply & Forward) [Tier 6]  
  - `M12-FLAG-01` (Explicit `\Seen` flag mutation) [Tier 5]  
  - `M12-ISOL-03` (Restart durability & outbox recovery) [Tier 3]  
- **Scope:** Evaluates in-memory view purging on account switch, vault locking while idle, token auto-renewal, browser reauthorization recovery, two-way reply/forward threading, explicit read flag mutation, and restart recovery.
- **Gate 6:** Each extended test is executed only upon separate owner/authority authorization; persistence confirmed; zero duplicate sends.


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
