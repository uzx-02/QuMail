# QuMail M7 — Module 1.6 Architecture Assessment
## Reconstructed Architecture, Component Inventory, and Workflow Traces

**Milestone:** M7 — Module 1.6  
**Document:** System Architecture Assessment & Baseline Reconstruction  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  
**Branch:** `codex/m7-module-1-6-planning`  
**Accepted Baseline Checkpoint:** `eff3736` | **Closeout Anchor:** `c9a3cf4`  

---

## 1. Executive Summary & Repository Baseline

### 1.1 Baseline and Scope
Following the formal acceptance and closeout of Module 1.5 (`eff3736` implementation; `c9a3cf4` documentation), this assessment establishes the technical reality of QuMail as of November 2026. This is a read-only architecture and engineering reconstruction designed to provide an actionable blueprint for corporate production readiness (Module 1.6).

The repository state at this assessment is:
- **Baseline Commit:** `eff3736` (fix for MTA singleton headers in live Gmail roundtrip)
- **Documentation Anchor:** `c9a3cf4` (`docs/operations/m7-module-1-5-closeout-report.md`)
- **Working Branch:** `codex/m7-module-1-6-planning` (branched from `c9a3cf4`)
- **Working Tree:** Clean (untracked reference files preserved: `QuMail-1.0-Research-Audit-Specification.pdf`, `Start-QuMailDemo.ps1`, `docs/operations/m2-reviewer-request.md`)

### 1.2 Two Parallel Architectures
The primary architectural finding is that **two distinct applications coexist within the repository**:
1. **The Legacy Laboratory System:** Launched by default when running `python main.py` without arguments. It invokes `ui/main_window.py` and relies on `crypto/tqr.py`, `crypto/level1_otp.py`, `crypto/level2_aes.py`, `crypto/level3_mlkem.py`, `kme/virtual_node.py` (Flask CSPRNG simulator), `portal/portal_server.py` (server-decrypting web portal), and unauthenticated file-based token storage (`secrets/`). This path contains critical architectural vulnerabilities (F01–F19) identified in the research audit.
2. **The Modern Cryptographic Mailbox Client:** Launched strictly via opt-in CLI flags: `main.py --dev-mailbox --dev-vault <path> [--google-client <path>] [--dev-gmail-submit]`. It invokes `ui/mailbox_window.py`, backed by `core/identity_service.py`, `core/account_session.py`, `core/settings_operations.py`, `experiments/m3/vault.py` (Windows DPAPI-backed AES-256-GCM vault), `experiments/m5/services.py` (RFC 3156 / RFC 9788 OpenPGP-PQ MIME parser and builder), `experiments/m4/model.py` (durable outbox state machine), and native Rust providers (`qumail-m3-provider.exe`, `qumail-m5-provider.exe`) compiled against Sequoia PGP 2.4.1 and OpenSSL 3.5.9.

All production readiness evaluations in this document pertain exclusively to the **modern opt-in architecture**, which demonstrated the live cryptographic round trip across two Gmail accounts in Module 1.5.

---

## 2. Comprehensive Component Inventory

### 2.1 Entry Points & Launchers
* **Source Files:** `main.py` (lines 47–106), `tools/start_google_acceptance.ps1`
* **Responsibilities:** CLI parsing, execution-mode validation, QApplication initialization, dependency wiring, and desktop window dispatch.
* **Key Public API:** `main(argv=None) -> int`, `_launch_mailbox(vault, client, gmail_enabled) -> int`, `_launch_identity(vault, client) -> int`.
* **State Owned:** None (ephemeral bootstrap).
* **Dependencies:** `PyQt6.QtWidgets`, `argparse`, `pathlib.Path`.
* **Security Boundary:** Enforces strict exclusivity: `--dev-mailbox` requires `--dev-vault` and rejects `--dev-identity` or `--dev-simulator`. Blocks inadvertent activation of the KME simulator in modern mode.
* **Error Handling:** Exits via `parser.error()` on invalid argument combinations.
* **Limitations & Gaps:** Default startup (`python main.py`) drops directly into the legacy insecure simulator path. The native helper binary path is hardcoded to a developer `tmp/` build path (`tmp/m2/target/debug/qumail-m3-provider.exe` in `main.py:82, 97`).

### 2.2 Identity Service & Account Session
* **Source Files:** `core/identity_service.py` (lines 14–120), `core/account_session.py` (lines 8–65)
* **Responsibilities:** GUI-facing identity facade, session state coordinator, snapshot publisher, account selection leasing, and generation counter tracking.
* **Key Public API:** `IdentityService.configured(path, helper, client)`, `DevelopmentSession.install(active, accounts, locked, helper, google)`, `DevelopmentSession.snapshot -> Snapshot`, `DevelopmentSession.acquire_lease() -> Lease`.
* **State Owned:** In-memory `Snapshot(active, accounts, locked, generation, helper, google)` protected by a re-entrant mutex (`threading.RLock`).
* **Dependencies:** `experiments/m3/types.py`, `experiments/m3/vault.py`, `experiments/m3/secure_store.py`.
* **Security Boundary:** Disallows direct cross-thread mutation. Issues generation-bound `Lease` instances. When an account is locked or switched, the generation counter increments, instantly invalidating all outstanding background worker leases.
* **Error Handling:** Translates underlying storage exceptions into `BoundaryError` with typed `Code` enums.
* **Limitations & Gaps:** In-memory only; does not survive process termination. Multi-account switching causes instantaneous background job cancellation rather than graceful queue draining.

### 2.3 Settings Operations & Commit Guard
* **Source Files:** `core/settings_operations.py` (lines 28–288)
* **Responsibilities:** Single-worker serialized execution of administrative, enrollment, key lifecycle, and recovery operations.
* **Key Public API:** `Operations.start(operation, *args)`, `Operations.take() -> Result | None`, `Operations.cancel()`, `Guard.reserve()`, `ScopedVault.commit(db)`.
* **State Owned:** Single active future (`self.future`), generation ticket, worker thread pool.
* **Dependencies:** `experiments/m3/vault.py`, `experiments/m3/secure_store.py`, `experiments/m3/provider.py`.
* **Security Boundary:** Admission control permits strictly ONE destructive settings operation at a time. `Guard.reserve()` performs an atomic check against the session lock immediately prior to calling `COMMIT`. The commit writes an encrypted owner receipt inside the SQLite transaction.
* **Error Handling:** Propagates typed `Failure` exceptions; ensures failed operations do not leave the session in a half-committed state.
* **Limitations & Gaps:** Background tasks are limited to a single worker queue; slow operations (e.g. keygen taking 1–2 seconds) block subsequent administrative actions.

### 2.4 Credential Storage & Local Encrypted Vault
* **Source Files:** `experiments/m3/secure_store.py` (lines 1–55), `experiments/m3/vault.py` (lines 20–290)
* **Responsibilities:** Hardware/OS-level secret storage and local AES-256-GCM encrypted persistence for account aggregates, keys, contacts, outbox, and inbox cache.
* **Key Public API:** `WindowsCredentialStore.put(target, secret)`, `WindowsCredentialStore.get(target) -> bytes`, `Vault.create(path, store, provider)`, `Vault.open(path, store, provider)`, `Vault.transaction(ctx)`.
* **State Owned:** 
  - Windows Credential Manager: 32-byte master key stored via Win32 `CredWriteW` / `CredReadW` with `CRED_PERSIST_LOCAL_MACHINE`.
  - SQLite Database: `vault(id TEXT PRIMARY KEY)` and `accounts(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, blob BLOB NOT NULL)`.
* **Dependencies:** `ctypes.wintypes`, `sqlite3`, `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
* **Security Boundary:** SQLite records are encrypted with AES-256-GCM. The Authenticated Associated Data (AAD) strictly binds `QuMail-M3-record-v1/{vault_id}/{account_id}/{revision}`. Transactions use `BEGIN IMMEDIATE` with `PRAGMA synchronous = FULL` and a 5-second busy timeout.
* **Error Handling:** Raises `BoundaryError(Code.STORE)` if Windows Credential Manager is inaccessible (e.g. in sandbox or non-interactive service). Raises `BoundaryError(Code.CORRUPT)` on AAD or GCM authentication tag mismatch.
* **Limitations & Gaps:** Platform locked to Windows (DPAPI). Does not support macOS Keychain, Linux Secret Service, or hardware TPM/YubiKey. No database migration framework; schema evolution is unversioned beyond record revision counters.

### 2.5 Contact Management & Fingerprint Verification
* **Source Files:** `core/identity_service.py` (lines 80–115), `experiments/m3/vault.py` (lines 180–235), `ui/identity_settings.py` (lines 140–190)
* **Responsibilities:** Importing armored public certificates, validating certified email address bindings, matching cryptographic fingerprints, and pinning trust.
* **Key Public API:** `Vault.import_contact(ctx, address, public_armored)`, `Vault.pin_contact(ctx, address, fingerprint, method)`.
* **State Owned:** `data['contacts'][address] = {'public': bytes, 'pinned': bool, 'fingerprint': str, 'method': str}` inside the encrypted account blob.
* **Dependencies:** `experiments/m3/provider.py` (Sequoia PGP certificate parsing).
* **Security Boundary:** Independent trust model. Importing a certificate does NOT grant trust. Trust is strictly established when an operator performs an out-of-band fingerprint comparison and marks it pinned (`method='fingerprint_out_of_band'`). Root key changes immediately revoke trust and block further sending.
* **Error Handling:** Rejects certificates with mismatched User IDs or multiple conflicting subkeys.
* **Limitations & Gaps:** 100% manual. No public key directory (PKD), HKP keyserver integration, Web Key Directory (WKD), or enterprise LDAP/SCIM integration. Verification requires the user to manually compare a 64-character hex string.

### 2.6 Cryptographic Provider & Native Engine
* **Source Files:** `experiments/m3/provider.py` (lines 1–55), `experiments/m5/provider.py` (lines 1–85), `tmp/m2/target/debug/qumail-m5-provider.exe`
* **Responsibilities:** Post-quantum hybrid OpenPGP cryptographic primitives: keypair generation, subkey certification, RFC 3156 PGP/MIME encryption and signing, decryption and composite signature verification.
* **Key Public API:** `Provider.call(op, budget, **values) -> dict` with operations: `generate`, `inspect`, `sign`, `verify`, `encrypt`, `decrypt`, `open`.
* **State Owned:** Stateless child process spawned per request or executed over anonymous pipes.
* **Dependencies:** Subprocess IPC to native Rust executable (`qumail-m5-provider.exe`) linking Sequoia PGP 2.4.1 and OpenSSL 3.5.9.
* **Security Boundary:** Anonymous standard I/O pipes (`stdin`/`stdout`). Secrets never appear on command-line arguments, environment variables, or disk files. Pipes enforce an 8 MiB limit and a 30-second hard execution budget. Child processes are terminated forcefully on timeout or cancellation.
* **Cryptographic Suite:**
  - Root Certificate: v6 ML-DSA-65 + Ed25519 (Algorithm 30, certification only, 3-year lifetime).
  - Signing Subkey: v6 ML-DSA-65 + Ed25519 (Algorithm 30, signing only, 1-year lifetime).
  - Encryption Subkey: v6 ML-KEM-768 + X25519 (Algorithm 35, encryption only, 1-year lifetime).
  - Symmetrics: AES-256-GCM (SEIPDv2, RFC 9580 / RFC 9980) with 4096-byte chunking.
* **Limitations & Gaps:** Binary currently points to a Debug build (`target/debug`), not an optimized, stripped Release build with ASLR, DEP, and stack guards.

### 2.7 Message Composition & Protection Pipeline
* **Source Files:** `ui/mail_actions.py` (lines 16–300), `mailbox_client/workflows.py` (lines 20–140), `experiments/m5/services.py` (lines 15–75)
* **Responsibilities:** UI draft editing, recipient certificate validation, payload construction, atomic draft-to-outbox freezing, and submission coordination.
* **Key Public API:** `Workflows.save(lease, draft, budget, editing)`, `Workflows.prepare(lease, op, key, budget)`, `Workflows.submit(lease, op, budget)`.
* **State Owned:** UI draft fields (`to`, `cc`, `subject`, `body`, `attachments`), outbox table view.
* **Dependencies:** `experiments/m5/model.py:Draft`, `experiments/m4/model.py:PreparedEnvelope`, `experiments/m5/mime.py`.
* **Security Boundary:** 
  - Every recipient in `To` and `Cc` must have an independently verified, pinned public key in the local vault.
  - Preparation freezes the exact serialized MIME bytes and SHA-256 digest before any network activity.
  - The sender's encryption subkey is automatically included as a recipient if "Include encrypted sender archive" is checked, ensuring the sender can read their own sent mail.
* **Error Handling:** Throws typed `Failure(Error.POLICY)` if any recipient key is unpinned or revoked.
* **Limitations & Gaps:** Hard limits enforced: Max 3 recipients, max 8 KiB plain-text body, max 4 attachments totaling 16 KiB. Bcc is completely disabled.

### 2.8 MIME Construction & Parsing
* **Source Files:** `experiments/m5/mime.py` (lines 15–185), `experiments/m5/model.py`
* **Responsibilities:** Constructing RFC 3156 `multipart/encrypted` envelopes with RFC 9788 Header Confidentiality (`hp="cipher"`), parsing outer headers, enforcing structural singletons, and unpacking inner protected MIME.
* **Key Public API:** `build(draft, armored_ciphertext) -> bytes`, `parse_outer(raw) -> tuple[OuterHeaders, bytes]`, `parse_inner(plaintext) -> InnerMessage`.
* **State Owned:** None (pure functional transformation).
* **Dependencies:** Python standard library `email.message`, `email.policy.SMTP`.
* **Security Boundary:** 
  - Structural singleton protection: Strictly enforces that RFC 5322 singleton headers (`From`, `To`, `Subject`, `Date`, `Message-ID`, `Content-Type`) appear at most once in outer headers, while permitting repeatable MTA trace headers (`Received:`, `DKIM-Signature:`, `X-Google-Smtp-Source:`).
  - Replaces outer `Subject` with literal `Encrypted message`. The true subject is sealed inside the inner encrypted MIME payload.
  - Rejects outer headers exceeding 8192 bytes or total wire size exceeding 256 KiB (`MAX_WIRE`).
* **Error Handling:** Raises `Failure(Code.INVALID)` or `Failure(Code.LIMIT)` on malformed MIME structure.
* **Limitations & Gaps:** Marked with experimental profile `QM-OPENPGP-PQ-1-EXPERIMENT-M5`. Fails closed if unexpected MIME structures or non-standard nesting depths (>2) are encountered.

### 2.9 Durable Outbox & State Machine
* **Source Files:** `experiments/m4/model.py` (lines 13–146), `experiments/m4/ownership.py` (lines 1–45), `experiments/m4/services.py`
* **Responsibilities:** Persistent queue management, state machine transitions, crash recovery, and duplicate submission prevention.
* **State Machine States:**
  - `Draft`: Editable local message draft.
  - `Prepared`: Cryptographically sealed, frozen MIME payload committed to vault with stable `Message-ID`.
  - `Submitting`: Transitioned immediately before opening network connection; lock acquired.
  - `Accepted`: Definitive SMTP 250 response received; permanent delivery success record.
  - `Unknown`: Unclassified socket drop, timeout after `DATA`, or crash during transmission. Requires manual inspection.
  - `Failed`: Definitive SMTP 5xx rejection or local validation rejection.
* **Key Public API:** `VaultOutbox.prepare()`, `VaultOutbox.claim_submitting()`, `VaultOutbox.record_result()`, `VaultOutbox.retry(acknowledge_duplicate_risk)`.
* **Security Boundary:** 
  - Persistent payload immutability: Retrying an operation sends the EXACT frozen bytes committed during preparation; it never re-encrypts.
  - Retry guard: Retrying an `Unknown` operation requires explicit user acknowledgment (`acknowledge_duplicate_risk=True`).
  - OS-level file locking (`ownership.py`) prevents two separate processes or threads from submitting the same operation simultaneously.
* **Error Handling:** Any process crash or power loss during `Submitting` leaves the record in `Submitting` state. On next boot, recovery reconciles `Submitting` to `Unknown`.
* **Limitations & Gaps:** Maximum 16 outbox operations per account (`MAX_OPERATIONS = 16`). Maximum 3 attempts per operation (`MAX_ATTEMPTS = 3`). No automatic background retry or exponential backoff scheduler.

### 2.10 SMTP Transport Subsystem
* **Source Files:** `mailbox_client/gmail.py` (lines 90–145), `transport/bounded_google.py`
* **Responsibilities:** Submitting outbound messages to Gmail SMTP server using TLS and SASL XOAUTH2.
* **Key Public API:** `GmailSMTP.send(credential, prepared_envelope, budget) -> Outcome`.
* **State Owned:** Ephemeral TCP connection.
* **Dependencies:** `smtplib`, `ssl`, `mailbox_client.model.Credential`.
* **Security Boundary:**
  - Hardcoded destination: `smtp.gmail.com:587`.
  - Mandatory STARTTLS with strict hostname and system CA certificate verification.
  - Scoped SASL XOAUTH2 authentication using access tokens bearing `https://mail.google.com/`. Identity-only tokens are rejected before socket connection.
  - Absolute deadlines and cancellation events checked at 50 ms intervals.
* **Error Handling:** 
  - SMTP 250 → `Outcome.ACCEPTED`.
  - SMTP 5xx → `Outcome.REJECTED`.
  - Socket timeout, connection reset, or network drop after `DATA` command sent → `Outcome.UNKNOWN`.
* **Limitations & Gaps:** Requires `--dev-gmail-submit` flag; otherwise submission is blocked at the UI boundary.

### 2.11 IMAP Mailbox Fetching & Synchronization
* **Source Files:** `mailbox_client/gmail.py` (lines 18–88), `mailbox_client/service.py` (lines 66–147)
* **Responsibilities:** Connecting to Gmail IMAP, authenticating via XOAUTH2, retrieving message headers via `BODY.PEEK`, caching header pages in the vault, and fetching message bodies on demand.
* **Key Public API:** `GmailMailbox.headers(credential, budget, before=None) -> Page`, `GmailMailbox.fetch(credential, key, budget) -> tuple[bytes, bool]`, `GmailMailbox.set_seen(credential, key, seen, budget) -> bool`.
* **State Owned:** Local vault table `m6_mailbox_v1` holding the latest 30 headers for the selected account.
* **Dependencies:** `imaplib`, `ssl`, `email.parser.BytesHeaderParser`.
* **Security Boundary:**
  - Hardcoded destination: `imap.gmail.com:993` over direct TLS.
  - Read-state preservation: All header and message body fetches use `EXAMINE` (read-only mode) and `BODY.PEEK[]`. Opening a message never marks it as read on the server.
  - Explicit flags: Marking read/unread requires deliberate user action via `SELECT` and `UID STORE`.
  - Message Keys are strictly quadruples: `(AccountContext, 'INBOX', UIDVALIDITY, UID)`. Sequence numbers are never used.
* **Error Handling:** Detects UIDVALIDITY rollover and purges stale local cache. Handles socket timeouts with graceful retry or status bar notifications.
* **Limitations & Gaps:** 
  - Strictly manual refresh: No background IMAP IDLE, no periodic polling timer. The user must manually click "Refresh headers".
  - Bounded window: Fetches at most 30 messages per page (`PAGE_SIZE = 30`). No full mailbox search or local indexing.

### 2.12 Inbound Decryption & Cryptographic Verification
* **Source Files:** `experiments/m5/services.py` (lines 80–145), `mailbox_client/service.py` (lines 93–136)
* **Responsibilities:** Decrypting armored OpenPGP messages, verifying composite post-quantum signatures, enforcing recipient authorization, and checking metadata integrity.
* **Key Public API:** `OpenMessage.open(lease, key_handle, wire, signer_public, budget) -> OpenedMessage`.
* **State Owned:** None (ephemeral cryptographic pipeline).
* **Dependencies:** `experiments/m5/provider.py`, `experiments/m5/mime.py`.
* **Security Boundary:**
  - Decryption and signature verification occur inside the isolated native provider before any plaintext is returned to Python.
  - Identity verification: The outer `From:` header is treated strictly as an unauthenticated transport claim. The application maps `From:` to an imported local contact certificate, extracts the pinned public key, and passes it to the provider.
  - Signatures by unpinned or unknown senders are labeled `unverified_identity` and NEVER grant `verified_confidential` status.
  - Outer/Inner header consistency: Compares protected inner `HP-Outer` headers against outer transport headers; reports mismatches.
* **Error Handling:** Any cryptographic tampering, invalid signature, or decryption failure raises `Failure(Code.CRYPTO)` or `Failure(Code.SIGNER)` and releases zero plaintext.
* **Limitations & Gaps:** Does not handle legacy S/MIME, PGP 4.x/5.x RSA/DSA keys, or cleartext PGP signatures.

### 2.13 Persistent Replay Protection Subsystem
* **Source Files:** `experiments/m5/services.py` (lines 125–140), `experiments/m3/vault.py`
* **Responsibilities:** Preventing duplicate presentation or replay attacks of previously observed cryptographic emails.
* **Key Public API:** `Vault.record_replay(ctx, signer_root, message_id, digest) -> ReplayStatus`.
* **State Owned:** Vault table `replay_v1` storing `(account_id, signer_root, message_id, sha256_digest, timestamp)`.
* **Security Boundary:** 
  - Atomic ordering: The SHA-256 digest of the canonical authenticated inner MIME bytes is committed to the local vault BEFORE decrypted plaintext is released to the UI.
  - If a message with the same `(signer_root, message_id)` arrives with an identical digest, it is marked `ReplayStatus.DUPLICATE`.
  - If the same identifier arrives with a different digest, it is classified as `ReplayStatus.CONFLICT` and immediately denied confidential status.
* **Error Handling:** Replay database commit failure blocks message opening, preventing unverified plaintext release.
* **Limitations & Gaps:** Replay table is local to the device vault. Restoring an old database backup rolls back the replay table, creating an epoch window for replay attacks.

### 2.14 Secure Message Viewer & Accessibility
* **Source Files:** `ui/mailbox_window.py` (lines 80–160), `ui/mail_accessibility.py` (lines 10–75)
* **Responsibilities:** Presenting decrypted message subject, body, sender identity badges, security indicators, and accessible UI navigation.
* **Key Public API:** `MailboxWindow.show_display(display)`, `MailboxWindow.clear_display()`.
* **State Owned:** UI widget state (`QPlainTextEdit`, `QLabel`, `QTableWidget`).
* **Security Boundary:**
  - Plain-text only: Uses `QPlainTextEdit` with plain text mode. HTML parsing, CSS execution, external images, web views, and active JavaScript are completely absent.
  - Stale clearing: Switching accounts, locking the vault, or cancelling an in-flight fetch immediately clears visible plaintext from memory and screen.
* **Error Handling:** Catches all worker exceptions and renders standardized, non-technical error messages via `error_message()`.
* **Limitations & Gaps:** No rich text, tables, inline images, or markdown rendering.

### 2.15 Attachment Security Pipeline
* **Source Files:** `experiments/m5/mime.py` (lines 60–110), `mailbox_client/workflows.py` (lines 115–140), `ui/mailbox_window.py` (lines 280–315)
* **Responsibilities:** Validating attachment filenames, enforcing size limits during composition, and safe disk export during retrieval.
* **Key Public API:** `import_attachment(path) -> Attachment`, `Workflows.export(lease, opened, index, destination, budget)`.
* **Security Boundary:**
  - Traversal protection: Incoming attachment filenames are sanitized; absolute paths, `..`, path separators, NTFS Alternate Data Streams (`:`), Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`, `LPT1`), and reparse points are rejected.
  - No auto-execution: Export requires explicit user selection of a destination path via `QFileDialog.getSaveFileName()`. Files are written with `O_CREAT | O_EXCL` to prevent silent overwriting.
  - Zero auto-preview: Attachments are never executed or launched via OS shell handlers.
* **Error Handling:** Export failure removes partially written bytes from disk.
* **Limitations & Gaps:** Maximum 4 attachments totaling at most 16 KiB. Large documents (PDFs, spreadsheets) exceed current limits.

### 2.16 Concurrency, Threading & Background Worker Model
* **Source Files:** `ui/mailbox_window.py` (lines 200–260), `ui/mail_actions.py` (lines 255–305)
* **Responsibilities:** Off-thread execution of network, cryptographic, and storage operations to maintain UI responsiveness.
* **State Owned:** `QThreadPool.globalInstance()`, `self.pending = []`, `QTimer` polling at 50 ms.
* **Security Boundary:**
  - GUI widgets are manipulated exclusively on the main Qt GUI thread.
  - Background workers receive an immutable `Lease(context, generation, cancel_event)` and a worker-owned SQLite connection.
  - When workers complete, `poll()` checks:
    ```python
    if (epoch != self.epoch or cancel.is_set() or lease is not self.lease or
        generation != self.identity.session.snapshot.generation):
        continue # Discard stale completion
    ```
  - Late results from a previously selected or locked account are dropped immediately; stale tokens or plaintext can never leak into another account.
* **Error Handling:** Unhandled worker exceptions are captured by `Future.result()`, caught in `poll()`, and displayed on the status bar.
* **Limitations & Gaps:** Uses a 50 ms timer polling loop (`self.timer = QTimer(self); self.timer.timeout.connect(self.poll)`) rather than native Qt signals and slots (`pyqtSignal`), consuming unnecessary idle CPU cycles.

---

## 3. End-to-End Workflow Traces

### Workflow A: First-Time Employee Onboarding
```
[User] Launch QuMail Desktop
  │
  ▼
main.py:main() ──> _launch_mailbox(vault_path, client_json)
  │
  ▼
IdentityService.configured()
  ├── Vault.open() / Vault.create()
  │     ├── WindowsCredentialStore.get(vault_id)
  │     └── SQLite accounts table verified
  └── DevelopmentSession.install()
  │
  ▼
MailboxWindow.__init__() ──> show_onboarding() (OnboardingWizard)
  │
  ▼
Step 1: Account Creation
  ├── User enters corporate email (e.g. alice@company.com)
  └── SettingsOperations.execute('enroll')
        ├── Provider.call('generate') ──> ML-DSA-65 root + signing & ML-KEM-768 encryption keys
        ├── Vault.store_account() ──> AES-256-GCM encrypted aggregate committed to SQLite
        └── WindowsCredentialStore.put() confirms master key protection
  │
  ▼
Step 2: Google Authorization
  ├── BoundedGoogleAuthorization.authorize()
  │     ├── Spawns loopback HTTP server on 127.0.0.1
  │     ├── Opens default system browser to Google OAuth consent
  │     ├── User logs in and approves scopes (openid, userinfo.email, https://mail.google.com/)
  │     └── Receives authorization code, exchanges for tokens, validates ID token (aud, iss, sub)
  └── Vault.store_oauth() ──> Tokens encrypted into account vault
  │
  ▼
Step 3: Contact Key Exchange
  ├── Export Alice's public certificate armored text
  ├── Import Bob's public certificate armored text (bob@company.com)
  ├── Out-of-band fingerprint verification (phone / secure chat)
  └── SettingsOperations.execute('pin_contact') ──> Bob's fingerprint pinned in vault
  │
  ▼
Mailbox Ready (Inbox displayed, lease established, generation = 1)
```

### Workflow B: Outbound Secure Email Transmission
```
[User] Compose Secure Email in MailActions
  ├── To: bob@company.com, Subject: "Q3 Financials", Body: "Confidential..."
  └── Click "🚀 Send Securely"
  │
  ▼
MailActions.send_securely() ──> start('send_securely')
  │
  ▼
Worker Thread (Workflows):
  │
  ├── 1. Save Encrypted Draft
  │     └── Workflows.save() ──> Vault.save_draft() (State: DRAFT)
  │
  ├── 2. Cryptographic Preparation
  │     ├── Workflows.prepare()
  │     ├── Check Bob's contact: PINNED? Yes. Subkey valid? Yes.
  │     ├── Check Sender Archive: Alice's encryption subkey included as second recipient.
  │     ├── M5 Provider.call('encrypt'):
  │     │     ├── Generates v6 PKESK for Bob (ML-KEM-768 + X25519)
  │     │     ├── Generates v6 PKESK for Alice (ML-KEM-768 + X25519)
  │     │     ├── Encrypts inner MIME with AES-256-GCM (4 KiB chunks)
  │     │     └── Signs payload with Alice's signing subkey (ML-DSA-65 + Ed25519)
  │     ├── M5 MIME.build():
  │     │     ├── Inner MIME sealed with true Subject, From, To, Body
  │     │     └── Outer MIME created: Subject: "Encrypted message", multipart/encrypted
  │     └── VaultOutbox.prepare():
  │           └── Atomically commits serialized MIME bytes, digest, stable Message-ID (State: PREPARED)
  │
  ├── 3. SMTP Submission
  │     ├── VaultOutbox.claim_submitting() ──> State: SUBMITTING (Acquires file lock)
  │     ├── Credentials.resolve() ──> Checks token expiry; refreshes via Google if needed
  │     ├── GmailSMTP.send():
  │     │     ├── Connects to smtp.gmail.com:587
  │     │     ├── Issues EHLO, STARTTLS, verifies TLS certificate
  │     │     ├── Issues AUTH XOAUTH2 with bearer token
  │     │     └── Transmits MAIL FROM, RCPT TO, DATA (frozen MIME payload)
  │     └── Receives: "250 2.0.0 OK id=... - gsmtp"
  │
  └── 4. Final State Commit
        └── VaultOutbox.record_result() ──> State: ACCEPTED (Receipt committed, lock released)
  │
  ▼
GUI Thread (poll):
  └── Status bar updated: "Protected email sent! State: Accepted by mail server."
```

### Workflow C: Inbound Secure Email Retrieval & Verification
```
[User] Click "Refresh headers" in MailboxWindow
  │
  ▼
Worker Thread (MailboxService.headers):
  ├── Credentials.resolve() ──> Validates OAuth mail token
  ├── GmailMailbox.headers():
  │     ├── Connects to imap.gmail.com:993 over TLS
  │     ├── Authenticates via AUTHENTICATE XOAUTH2
  │     ├── Opens mailbox via EXAMINE INBOX (Read-Only mode)
  │     └── Fetches UID FETCH 1:* (UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (...)])
  └── Vault.transaction() ──> Caches 30 latest headers in m6_mailbox_v1
  │
  ▼
GUI Thread renders headers table. User selects message and clicks "Open selected".
  │
  ▼
Worker Thread (MailboxService.open):
  ├── GmailMailbox.fetch() ──> UID FETCH <uid> (BODY.PEEK[]) (Read flag untouched!)
  ├── Wire CRLF canonicalization and outer header parsing
  ├── Classification: Content-Type: multipart/encrypted ──> Kind.MODERN
  ├── Signer resolution: Outer From: alice@company.com
  │     └── Lookup contact in vault ──> Contact found, pinned public certificate retrieved
  │
  ├── M5 Provider.call('open'):
  │     ├── Parses v6 PKESK matching Bob's encryption subkey
  │     ├── Decrypts session key via ML-KEM-768 + X25519
  │     ├── Decrypts SEIPDv2 AES-256-GCM ciphertext chunks
  │     ├── Verifies ML-DSA-65 + Ed25519 composite signature against Alice's pinned key
  │     └── Emits verified inner plaintext MIME
  │
  ├── M5 Services / Replay Protection:
  │     ├── Computes SHA-256 digest of canonical authenticated MIME
  │     ├── Queries vault replay_v1: Seen before? No.
  │     └── Vault.record_replay() ──> Commits digest to vault (ReplayStatus.FRESH)
  │
  └── Returns OpenedMessage(subject, body, identity_trust='independently_verified', replay='fresh')
  │
  ▼
GUI Thread renders decrypted text in QPlainTextEdit; Security Badge: "Signature valid; identity: independently_verified; replay: fresh".
```

### Workflow D: Interrupted Submission and Recovery
```
[Outbound Transmission Initiated]
  ├── Operation 0x4A... committed as PREPARED
  ├── Worker claims state SUBMITTING, commits to SQLite, acquires OS file lock
  ├── SMTP connection established to smtp.gmail.com:587
  ├── Client sends DATA block
  │
  ▼ 💥 [EVENT: Network drops / Laptop lid closes / Process terminated]
  │
Client loses TCP connection before receiving SMTP 250 response.
  │
  ▼ [Next Application Launch]
MailboxWindow initializes, loads outbox for active account.
  │
  ▼
Recovery Worker (Workflows.outbox):
  ├── Detects Operation 0x4A... in state SUBMITTING with NO active worker process lock
  ├── Invokes VaultOutbox.recover()
  │     └── Transitions state from SUBMITTING ──> UNKNOWN (Recorded in vault)
  └── Outbox Table displays: "Type: Send | Status: Unknown | Attempts: 1"
  │
  ▼
Operator Action:
  ├── Status warning: "⚠️ Delivery Uncertain · Check Sent Folder Before Retry"
  ├── Operator logs into Gmail Web interface or checks recipient's inbox out-of-band:
  │     ├── Scenario 1: Email arrived at server.
  │     │     └── Operator selects operation, clicks "Discard" ──> Outbox cleared.
  │     │
  │     └── Scenario 2: Email never arrived.
  │           └── Operator clicks "Retry send".
  │                 ├── Modal Prompt: "Send the same frozen message again? Duplicate risk..."
  │                 ├── Operator confirms (acknowledge_duplicate_risk = True).
  │                 └── Workflows.retry() sends EXACT frozen bytes with attempt counter = 2.
```

### Workflow E: Application Shutdown and Worker Draining
```
[User] Closes Main Mailbox Window (Click 'X' or Alt+F4)
  │
  ▼
MailboxWindow.closeEvent(event):
  │
  ├── 1. Check Active Submissions
  │     └── If worker in 'submit': Display Warning Dialog:
  │           "Message transmission in progress. Disconnecting cannot recall sent mail."
  │           User selects "Yes, close".
  │
  ├── 2. Worker Cancellation
  │     ├── MailboxWindow.cancel():
  │     │     ├── Increments self.epoch (invalidates future UI completions)
  │     │     └── Sets self.cancel_event (signals cooperative worker threads)
  │     └── MailActions.stop(): Signals compose workers
  │
  ├── 3. Lock Session
  │     └── IdentityService.session.lock() ──> Clears active account context from memory
  │
  ├── 4. Thread Pool Draining
  │     └── QThreadPool.globalInstance().waitForDone(2000) ──> Allows short DB writes to finish
  │
  ├── 5. SQLite Connection Teardown
  │     └── Vault connections closed deterministically
  │
  └── 6. Event accepted ──> Process terminates cleanly (Exit code 0)
```

---

## 4. Implementation vs. Documentation Discrepancies

| Architectural Dimension | Specification / Handover Claim | Actual Codebase Implementation | Discrepancy Assessment |
|---|---|---|---|
| **Default Startup Path** | Modern secure mail client is the primary application. | `main.py:73` defaults to `_launch_desktop()`, opening the legacy insecure TQR simulator. | **Critical:** Production users launching without flags get the legacy prototype. |
| **Native Provider Binary** | Packaged, hardened native cryptographic engine. | `main.py:82, 97` and `ui/mailbox_window.py:129` hardcode paths to `tmp/m2/target/debug/qumail-*.exe`. | **High:** Dependent on disposable `tmp/` build artifacts; debug binary lacks security flags. |
| **Mailbox Synchronization** | Standard background client synchronization. | `ui/mailbox_window.py:125` only runs a 50 ms worker polling timer; IMAP headers only refresh on manual button click. | **High:** No automatic synchronization, no IMAP IDLE, no background notification. |
| **Message Size Limits** | Research Audit Spec §§42/54 proposes 25 MiB wire / 15 MiB attachments. | `experiments/m5/model.py:8-15` caps wire at 256 KiB, body at 8 KiB, and attachments at 16 KiB total. | **Medium:** Sufficient for testing; completely inadequate for corporate enterprise email. |
| **Logging & Diagnostics** | Structured audit logging with sensitive data redaction. | Code contains raw `print()` statements in `service.py:116, 123` and `mailbox_window.py:247`, with traceback printing. | **Medium:** Diagnostic pollution in console; no structured disk logging or syslog/EventLog. |
| **Key Distribution** | Certified public key binding with directory discovery. | Entirely manual: user must paste armored PGP blocks and manually compare 64-char hex fingerprints. | **Resolved in WS-02:** Automated Web Key Directory (WKD) and enterprise directory discovery implemented (`core/key_discovery.py`, `core/trust_engine.py`). Zero-friction lookups without manual hex comparison; trust separated from discovery. |
| **Multi-Device Support** | Multi-device key management roadmap. | `experiments/m3/vault.py` enforces strictly ONE active device per account. Restoring a backup requires device retirement. | **Low:** Explicitly documented as bounded scope; requires future architectural expansion. |
| **MIME Profile Status** | Production post-quantum OpenPGP profile. | `experiments/m5/model.py:7` declares `QM-OPENPGP-PQ-1-EXPERIMENT-M5`. | **Resolved in WS-02:** Standardized wire profile `QM-OPENPGP-PQ-v1` with dual-read backward compatibility for `QM-OPENPGP-PQ-1-EXPERIMENT-M5`. |
| **Platform Portability** | Windows and Android product goals. | `experiments/m3/secure_store.py` directly calls Win32 `CredWriteW`/`CredReadW`. | **Medium:** Hard Windows dependency; zero Linux or Android implementation exists. |
| **Outbox Queue Capacity** | Enterprise durable outbound spool. | `experiments/m4/model.py:145` caps outbox at 16 operations per account. | **Medium:** Operational bottleneck if an offline worker queues numerous emails. |

---

## 5. Architectural Strengths to Preserve

The architecture has several robust design patterns that must not be degraded during future refactoring:
1. **Synchronized Commit Guard (`Guard.reserve()`):** Prevents holding GUI mutexes during network/disk I/O, while strictly re-checking session validity before committing transactions.
2. **Atomic Replay Receipt Commitment:** Persisting the SHA-256 digest of decrypted canonical MIME before releasing plaintext to the UI completely eliminates race-condition replay attacks.
3. **Immutable Frozen Wire Envelopes:** Exact serialized bytes and cryptographic digests are frozen in the outbox; retries NEVER re-encrypt, eliminating ephemeral nonce leakage and ciphertext substitution.
4. **Cooperative Cancellation & Lease Invalidation:** Immediate clearing of plaintext and generation-based disposal of late worker results guarantees that account switches never cross-contaminate data.
5. **Read-State Preservation (`BODY.PEEK`):** Strict adherence to read-only IMAP operations prevents accidental server-side state modification during secure inspection.
