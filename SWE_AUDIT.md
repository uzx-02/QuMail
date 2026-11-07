# QuMail | Comprehensive Software Engineering Audit & Technical Assessment

**Audit Date:** November 2026  
**Auditor:** Senior Software Engineer, System Architect & Security Auditor (Antigravity AI)  
**Target Repository:** QuMail (`c:\Users\uzx\Desktop\Aavishkar-26\QuMail`)  
**Current Branch:** `codex/m7-relay-google-acceptance`  
**Current HEAD:** `5658601` (Authoritative Source Parent: `4e429a4`, Checkpoint Anchor: `18174e1`)  
**Authoritative Specifications:** `QuMail-1.0-Research-Audit-Specification.md`, `AI_HANDOVER.md`, `docs/handover/STATUS_AND_ROADMAP.md`

---

## 1. Executive Summary

QuMail is a post-quantum cryptographic (PQC) secure email system engineered to provide end-to-end confidential and authenticated communication over conventional email transport infrastructure (specifically Gmail IMAP and SMTP). 

### 1.1 The Dual-Architecture Reality
A critical engineering discovery from this audit is that **the codebase currently contains two completely separate, co-existing architectural implementations**:

1. **The Legacy Prototype (`main.py` default / `--dev-simulator`):**
   - The original experimental codebase containing severe security and architectural vulnerabilities identified in the canonical audit specification (§15, F01–F19).
   - Incurable legacy defects include: sender-owned recipient ML-KEM private keys stored in local files (`secrets/send_keys/`), an unauthenticated in-memory CSPRNG "QKD simulator" (`kme/virtual_node.py`), a server-decrypting web portal (`portal/portal_server.py`) that exposes decrypted plaintext and private keys to server memory/Firestore, premature SMTP dispatch before key persistence (F07), and plaintext Fernet master keys on disk.
   - **Status:** Frozen as a legacy characterization baseline. Maintained exclusively for historical regression tests (`tests/`). **Must never receive production traffic, keys, or modern accounts.**

2. **The Modern Hardened Architecture (`main.py --dev-mailbox` / `--dev-identity`):**
   - The production-oriented re-engineering completed across milestones M1 through M7.
   - Implements true recipient-owned keys using a post-quantum hybrid OpenPGP profile: **ML-KEM-768 + X25519** for encryption and **ML-DSA-65 + Ed25519** for digital signatures, adhering to RFC 3156 (PGP/MIME) and RFC 9788 (Direct Protected Headers `hp=cipher`).
   - Uses an isolated, native Rust cryptographic helper (`qumail-m3-provider.exe` and `qumail-m5-provider.exe`) linking **Sequoia PGP 2.4.1** and a static build of **OpenSSL 3.5.9**.
   - Backed by an authenticated local SQLite vault (`AES-256-GCM` with Associated Authenticated Data binding account, vault ID, and monotonic revisions), protected by a 256-bit master key held exclusively in the **Windows Credential Manager** (`CredWriteW`).
   - Implements a crash-safe, durable outbox with process-level OS file locking (`ownership.py`), strictly enforcing envelope persistence before SMTP submission and handling transport uncertainty honestly.
   - Connects to real Gmail infrastructure via validating TLS connections: IMAP over port 993 (strictly using `EXAMINE` and `BODY.PEEK` to preserve unread state) and SMTP over port 587 (`STARTTLS` + `XOAUTH2`).
   - Features asynchronous, single-admission Settings with transactional commit guards, encrypted outcome receipts, and a strict recovery custody ceremony.
   - Includes an optional local loopback ciphertext relay (`services/relay`) providing client-cert authenticated mTLS storage with zero server-side decryption keys or plaintext bodies.

### 1.2 Milestone Disposition Summary (Per Canonical Spec §54)
- **M1 (Reproducible Baseline):** **COMPLETE at research baseline scope.** Pinned environments, deterministic test execution, truthful claims, and CI validation (Windows/Ubuntu).
- **M2 (Protocol Provider & Proof):** **PARTIAL (Engineering proof complete; independent external review pending).** Unmodified Sequoia 2.4.1 + OpenSSL 3.5.9 cross-tested with rPGP 0.21.0 in both directions. Bounded development authorized under ADR 003/004.
- **M3 (Identity & Vault):** **PARTIAL (Bounded Windows engineering complete; live verification & external review pending).** Real Windows Credential Manager integration, authenticated AES-GCM vault, PKCE Google ID token verification, certified recipient binding, fingerprint pinning, and explicit recovery ceremony.
- **M4 (Durable Outbox):** **PARTIAL (Bounded engineering complete; live submission acceptance pending).** Durable outbox state machine, freeze-before-send, identical retry bytes, crash/uncertainty handling, and loopback TLS adapter.
- **M5 (Protected MIME):** **PARTIAL (Bounded profile complete; peer interoperability & external parser review pending).** RFC 3156 + RFC 9788 direct protected headers, sender archive decryption, replay protection, and bounded size limits.
- **M6 (Workflows & Mailbox UI):** **PARTIAL (Bounded Windows engineering complete; live Google & human walkthrough pending).** Gmail IMAP PEEK retrieval, encrypted header caching, safe plain-text rendering, verified attachment export (`xb` no-clobber), reply/forward derivation, and asynchronous Settings operations.
- **M7 (Local Ciphertext Relay):** **Locally qualified (Relay-only).** Loopback mTLS SQLite store, atomic leases, quotas, tombstones. Cloud relay and real QKD explicitly excluded by owner decision (ADR 009).
- **M8 (Release Assurance):** **NOT STARTED.** Packaging, signed installers, SBOM, license reconciliation, and security release approvals remain future gates.

### 1.3 Exact Current Pause Point & Immediate Defect
The repository is paused on branch `codex/m7-relay-google-acceptance` at commit `5658601`.
- **Immediate Defect (P0 Blocker):** A filesystem visibility divergence was discovered between tool subprocesses and the interactive Windows desktop session. The acceptance launcher targeted `%LOCALAPPDATA%\QuMailAcceptance\2026-10-22-google-m7\acceptance.sqlite`, which tool shells could see but the user's desktop File Explorer could not find. An untested GUI shortcut (`tmp/m7/QuMail-Desktop-DryRun.lnk`) was prepared for a distinct path (`2026-11-01-desktop`), but was never launched.
- **Next Required Action:** Execute a clean, desktop-visible launch dry run through Settings, resolving the path divergence without overwriting old data, and stopping before vault creation or sending to allow manual owner testing.

---

## 2. Project Purpose and Functional Overview

QuMail is designed to solve the critical vulnerability of email confidentiality in the advent of quantum computing (Store-Now-Decrypt-Later attacks) without requiring proprietary server infrastructure or untrusted intermediaries.

### 2.1 Core Functional Pillars
1. **Zero-Trust Infrastructure:** The mail transfer agents (Google, intermediate relays) and local network providers are treated as untrusted. They observe only encrypted transport sessions (TLS), encrypted MIME envelopes (PGP/MIME), and encrypted headers (RFC 9788).
2. **True Recipient Key Ownership:** Encryption is performed exclusively against the recipient's certified, locally owned public key. Private keys never leave the endpoint's secure store.
3. **Explicit Identity Ceremony:** Public certificates are authenticated via out-of-band fingerprint verification (pinning). Trust is never inferred from self-signatures, directory lookups, or outer transport headers.
4. **Local Cryptographic Isolation:** Private key operations execute in dedicated, short-lived native worker processes (`qumail-m3-provider.exe`, `qumail-m5-provider.exe`) over private OS pipes with strict timeouts, zero secret exposure via command-line arguments or environment variables, and memory-safe Rust execution.
5. **Durable Delivery Semantics:** Eliminates the classic email client bug where messages are submitted to SMTP before local encryption state and keys are persisted. Envelopes are frozen before submission; retries transmit identical bytes; network timeouts transition to an explicit `UNKNOWN` state rather than dangerous automatic resubmission.
6. **Air-Gapped Recovery Custody:** Account and key recovery packages require the user to explicitly acknowledge custody of an ephemeral 256-bit recovery passphrase *before* the encrypted archive is written to disk. The secret is never stored locally.

---

## 3. Repository Structure & Component Inventory

```
QuMail/
├── core/                        # Core coordination and session logic
│   ├── account_session.py       # Modern immutable account snapshot & ticket management
│   ├── identity_service.py      # Facade for modern vault, store, and identity operations
│   ├── settings_operations.py   # Asynchronous Settings worker, commit guards, and receipts
│   ├── config.py                # Legacy configuration constants
│   └── session.py               # [LEGACY] Mutable global session singleton
├── mailbox_client/              # Modern email client domain services
│   ├── connection.py            # Cancellable socket, DNS, and TLS setup
│   ├── gmail.py                 # Gmail IMAP adapter (EXAMINE, UID BODY.PEEK, XOAUTH2)
│   ├── model.py                 # Immutable mailbox display models and cache headers
│   ├── service.py               # Account-scoped mailbox service & encrypted header cache
│   ├── smtp.py                  # Validating Gmail SMTP & Loopback SMTP adapters
│   └── workflows.py             # Compose, draft, submit, archive, derive, export workflows
├── ui/                          # Presentation layer (PyQt6)
│   ├── mailbox_window.py        # Modern multi-account mailbox interface
│   ├── mail_actions.py          # UI workflow orchestration & confirmation dialogs
│   ├── identity_settings.py     # Modern Settings dialog (accounts, keys, recovery)
│   ├── mail_accessibility.py    # Accessibility tokens, focus traversal, actionable errors
│   ├── compose_window.py        # [LEGACY] Old compose window (insecure pipeline)
│   ├── inbox_view.py            # [LEGACY] Old inbox view (hangs on IMAP, insecure decrypt)
│   ├── main_window.py           # [LEGACY] Old main application window
│   └── settings_window.py       # [LEGACY] Old settings dialog
├── transport/                   # Network transport and authentication
│   ├── bounded_google.py        # Subprocess-isolated Google OAuth verifier & PKCE
│   ├── bounded_worker.py        # Generic deadline-bound subprocess worker
│   ├── development_google.py    # Ephemeral loopback OAuth server & claim verification
│   ├── network_worker.py        # Background thread socket runners
│   ├── imap_receiver.py         # [LEGACY] Unbounded IMAP receiver
│   ├── smtp_sender.py           # [LEGACY] Unbounded SMTP sender (F07 defect)
│   ├── oauth2_gmail.py          # [LEGACY] Old Gmail OAuth helper (disk Fernet token)
│   ├── oauth2_yahoo.py          # [LEGACY] Incomplete Yahoo OAuth helper
│   └── recipient_check.py       # [LEGACY] KME-based recipient check
├── crypto/                      # [LEGACY] Deprecated cryptographic modules
│   ├── legacy_provider.py       # Pinned liboqs-python loader
│   ├── level1_otp.py            # Unauthenticated XOR with CSPRNG simulator keys
│   ├── level2_aes.py            # Unauthenticated AES-GCM with simulator keys
│   ├── level3_mlkem.py          # Flawed ML-KEM-768 (sender generates private key)
│   └── tqr.py                   # Tiered Quantum Resilience dispatcher
├── kme/                         # [LEGACY] Deprecated key management entity
│   ├── virtual_node.py          # Unauthenticated Flask CSPRNG key server
│   ├── kme_client.py            # HTTP client for virtual node
│   └── key_models.py            # Legacy key request data models
├── portal/                      # [LEGACY] Insecure server-decrypting web portal
│   ├── portal_server.py         # Flask/HTTPS server storing ciphertexts & private keys
│   ├── portal_crypto.py         # Server-side decryption routines
│   └── cloud_entrypoint.py      # Cloud Run entry point
├── services/relay/              # Modern M7 local ciphertext relay
│   ├── store.py                 # SQLite WAL durable ciphertext store (zero plaintext)
│   ├── http.py                  # mTLS HTTP server, cert-to-peer authorization, leases
│   ├── client.py                # Client adapter for relay upload and download
│   └── __main__.py              # CLI entry point for local relay daemon
├── experiments/                 # Active modern application dependencies & proofs
│   ├── m2/                      # Sequoia 2.4.1 + OpenSSL 3.5.9 Rust proof & rPGP interop
│   ├── m3/                      # Modern vault, WindowsCredentialStore, M3 native provider
│   │   ├── types.py             # Strongly typed IDs (AccountContext, KeyHandle, etc.)
│   │   ├── vault.py             # AES-256-GCM authenticated SQLite aggregate store
│   │   ├── secure_store.py      # Windows Credential Manager ctypes wrapper
│   │   ├── provider.py          # Python IPC wrapper for qumail-m3-provider.exe
│   │   └── provider/            # Rust source for M3 native provider
│   ├── m4/                      # Durable outbox services, repository, and process locks
│   │   ├── model.py             # Outbox state machine (Prepared, Submitting, Accepted)
│   │   ├── ownership.py         # OS-level cross-process file lock for operations
│   │   ├── repository.py        # VaultOutbox adapter over SQLite
│   │   └── services.py          # PrepareMessage and SubmitOutbox services
│   ├── m5/                      # RFC 3156 / RFC 9788 protected MIME services & provider
│   │   ├── mime.py              # Strict PGP/MIME encapsulation and parsing
│   │   ├── model.py             # Bounded message models (256 KiB wire, 16 KiB attachment)
│   │   ├── services.py          # Compose and OpenMessage domain services
│   │   ├── provider.py          # Python IPC wrapper for qumail-m5-provider.exe
│   │   └── provider/            # Rust source for M5 native provider
│   ├── m6/                      # M6 integration test suites, fixtures, and audit scripts
│   └── m7/                      # M7 relay test suites and mTLS fixtures
├── tests/                       # Legacy test suite (37 tests, plain pytest entry)
├── packaging/                   # Dependency manifests, uv lockfiles, native manifests
│   ├── requirements.in          # Top-level dependencies
│   ├── requirements-runtime.lock# Pinned runtime dependencies with SHA-256 hashes
│   ├── requirements-dev.lock    # Pinned development dependencies
│   └── native-research.json     # liboqs native hash manifest
├── tools/                       # Operational scripts
│   └── start_google_acceptance.ps1 # Parameterized launcher with preflight checks
└── main.py                      # Application entry point (legacy by default, opt-in modern)
```

---

## 4. Verified System Architecture

```
                                  +-------------------------------------------------------+
                                  |                 main.py (Entry Point)                 |
                                  |  --dev-mailbox --dev-vault <path> [--google-client]   |
                                  +---------------------------+---------------------------+
                                                              |
                                           +------------------+------------------+
                                           |                                     |
                                           v                                     v
                        +------------------------------------+ +-----------------------------------+
                        |         MailboxWindow (UI)         | |       IdentitySettings (UI)       |
                        |   - Thread-safe worker lifecycle   | |   - Account enrollment / refresh  |
                        |   - Generation-checked selection   | |   - Fingerprint pinning ceremony  |
                        |   - Stale plaintext auto-clearing  | |   - Custody-guarded recovery      |
                        +------------------+-----------------+ +-----------------+-----------------+
                                           |                                     |
                                           v                                     v
                        +------------------------------------+ +-----------------------------------+
                        |       Workflows (Domain Layer)     | |   Settings Operations (Worker)    |
                        |   - Draft, prepare, submit, retry  | |   - Single-worker admission queue |
                        |   - Derive reply / forward         | |   - Owned SQLite connections      |
                        |   - Atomic attachment export (xb)  | |   - Encrypted outcome receipts    |
                        +--------+------------------+--------+ +-----------------+-----------------+
                                 |                  |                            |
            +--------------------+                  +-------------+              |
            |                                                     |              |
            v                                                     v              v
+-----------------------+                             +-----------------------------------+
|  M5 Protected MIME    |                             |        M3 Authenticated Vault     |
|  - RFC 3156 (PGP/MIME)|                             |  - AES-256-GCM record encryption  |
|  - RFC 9788 (hp=cipher|                             |  - AAD bound to vault/acct/rev    |
|  - Outer/inner parsing|                             |  - FULL synchronous SQLite commit |
+-----------+-----------+                             +-----------------+-----------------+
            |                                                           |
            v                                                           v
+-----------------------+                                     +-------------------+
| Native Crypto Helper  |                                     | Win32 Credential  |
| - qumail-m5-provider  |                                     | Manager (Master)  |
| - Sequoia PGP 2.4.1   |                                     +-------------------+
| - Static OpenSSL 3.5.9|
| - ML-KEM-768/X25519   |
| - ML-DSA-65/Ed25519   |
+-----------------------+
            |
            | Prepared Envelope
            v
+-----------------------+
|   M4 Durable Outbox   |
| - State machine       |
| - ownership.py lock   |
| - Exact retry bytes   |
+-----------+-----------+
            |
            +---------------------------------+
            |                                 |
            v                                 v
+-----------------------+         +-----------------------+
|  Gmail SMTP (TLS 587) |         |  Local Relay (mTLS)   |
|  - Validating TLS     |         |  - Loopback SQLite    |
|  - Scoped XOAUTH2     |         |  - Zero plaintext     |
|  - Honest UNKNOWN     |         |  - Cert auth lease    |
+-----------------------+         +-----------------------+
```

### 4.1 Architectural Patterns & Separation of Concerns
1. **Immutable State Snapshots:** The modern session (`core/account_session.py`) distributes state via frozen `Snapshot` and `AccountView` dataclasses. The GUI cannot mutate session state directly; background workers receive a generation `Ticket` that is invalidated upon account switching, lock, or cancellation.
2. **Short Synchronized Reservation vs. Long I/O:** In `core/settings_operations.py`, workers acquire the session mutex only for an instantaneous reservation check (`Guard.reserve()`), releasing it immediately before performing disk I/O, native cryptography, or network communication.
3. **Owned Worker Connections:** SQLite connections are never shared across threads or processes. Every background worker in `Settings`, `MailboxService`, and `SubmitOutbox` creates, uses, and closes its own dedicated connection.
4. **Isolated Subprocess Cryptography:** Python never links native C++ or Rust crypto shared libraries directly in the modern path. Crypto operations run inside separate native executables with strictly budgeted standard I/O pipes. A native crash or memory fault cannot corrupt Python runtime memory.

---

## 5. Detailed Feature-by-Feature Implementation Assessment

| Feature / Subsystem | Implementation Status | Technical Mechanism & Evidence | Test Coverage & Verification | Remaining Gaps / Limitations |
|---|---|---|---|---|
| **Account Enrollment & Identity** | Fully Implemented (Modern) | `transport/bounded_google.py`, `core/settings_operations.py`. S256 PKCE, ephemeral loopback, strict ID token verification (issuer, audience, time, nonce, subject, email). | 14 unit tests in `test_google_diagnostics.py` passing offline. | Live Google browser callback tested with test accounts; final live token refresh unverified by agent. |
| **Key Management & Lifecycle** | Fully Implemented (Modern) | `experiments/m3/vault.py`, `identity.py`. Recipient root certifies separate signing and encryption subkeys; additive rotation, root revocation, replacement root trust ceremony. | 54 tests in `experiments/m3/tests` passing in normal and reverse order. | One active enrolled device limit enforced; multi-device synchronization deferred. |
| **Secure Key Storage** | Fully Implemented (Modern) | `experiments/m3/secure_store.py`. Windows Credential Manager stores 256-bit random master key via `CredWriteW`. No plaintext disk fallback. | Tested in Windows logon session; unit tests fail in sandboxed shells (expected). | Local malware in same user logon session can still query Credential Manager (no HSM/enclave). |
| **Encrypted Account Database** | Fully Implemented (Modern) | `experiments/m3/vault.py`. AES-256-GCM wraps whole account aggregates; AAD binds vault ID, account ID, and revision; SQLite `PRAGMA synchronous=FULL`. | 54 tests in `experiments/m3/tests`. Atomicity and rollback resistance verified. | SQLite cannot participate in an atomic distributed transaction with Windows Credential Manager. |
| **Backup & Disaster Recovery** | Fully Implemented (Modern) | `core/settings_operations.py:172-200`. In-memory package generation; explicit UI custody acknowledgment *before* writing; atomic `xb` file persistence. | 17 focused Settings tests in `test_settings.py`. Real SQLite commit denial verified. | Cannot prevent user from losing their offline secret passphrase. |
| **Post-Quantum Crypto Engine** | Fully Implemented (Modern) | `experiments/m5/provider/src/main.rs`, Sequoia PGP 2.4.1 + OpenSSL 3.5.9. ML-KEM-768/X25519 hybrid encryption, ML-DSA-65/Ed25519 composite signatures. | 17 tests in `experiments/m2` (Sequoia ↔ rPGP interoperability). 2 native provider tests. | External cryptographer / security review pending. Development exception ADR 003/004. |
| **Protected MIME Packaging** | Fully Implemented (Modern) | `experiments/m5/mime.py`. RFC 3156 PGP/MIME outer body, RFC 9788 direct protected headers (`hp=cipher`). Inner headers encrypted. | 55 tests in `experiments/m5/tests`. Negative tamper, truncation, and mismatch tests pass. | Interoperability with independent third-party mail clients (Thunderbird, etc.) unverified. |
| **Message Decryption & Verification** | Fully Implemented (Modern) | `experiments/m5/services.py:OpenMessage`. Full verification before release; separate tracking of signature, identity trust, outer mismatch, and replay conflict. | 55 tests in `experiments/m5/tests`. Replay cache in SQLite tested. | Verified confidential label strictly denied if replay conflict or identity unverified. |
| **Durable Outbox & Delivery** | Fully Implemented (Modern) | `experiments/m4/services.py:SubmitOutbox`. Operation state machine: Draft → Prepared → Submitting → Accepted / Unknown / Failed. OS file lock (`ownership.py`). | 85 tests in `experiments/m4/tests`. 10 crash-boundary and timeout tests pass. | SMTP acceptance guarantees submission to MTA, not delivery to or decryption by recipient. |
| **Gmail SMTP Transport** | Fully Implemented (Modern) | `mailbox_client/smtp.py:GmailSMTP`. smtp.gmail.com:587, validating STARTTLS, system CA root validation, scoped XOAUTH2 after TLS established. | Controlled loopback TLS tests pass (85 tests). | Live Gmail submission tested locally; pending final owner acceptance on live test accounts. |
| **Gmail IMAP Retrieval** | Fully Implemented (Modern) | `mailbox_client/gmail.py:GmailMailbox`. imap.gmail.com:993, validating TLS, XOAUTH2, strictly `EXAMINE` (read-only) and `UID FETCH BODY.PEEK`. | 96 tests in `experiments/m6`. | Paging capped at 30 messages per page; only INBOX folder supported. |
| **Mailbox UI & Navigation** | Fully Implemented (Modern) | `ui/mailbox_window.py`. Account selection, generation-guarded workers, safe plain-text display, stale result discarding, busy state indicators. | Automated Qt test cases in `experiments/m6`. | Human accessibility and usability review pending. |
| **Attachment Export** | Fully Implemented (Modern) | `mailbox_client/workflows.py:export`. Strict path sanitization (no UNC, reserved names, traversal); atomic `open(..., 'xb')` no-clobber write. | Verified in `test_workflows.py`. Partial write unlinked on failure. | Attachments limited to 16 KiB in current development profile. |
| **Local Ciphertext Relay** | Fully Implemented (Modern) | `services/relay/store.py`, `http.py`. Loopback mTLS SQLite store, client cert digest mapping, atomic leases, quotas, tombstones. Zero plaintext bodies. | 13 tests in `experiments/m7`. Concurrency race (128 requests / 8 processes) verified. | Local single-host only. Cloud relay explicitly excluded by owner decision. |
| **Legacy TQR Dispatcher** | Deprecated / Vulnerable | `crypto/tqr.py`. Routes to Level 1, 2, 3. Relies on virtual KME and sender-persisted keys. | 37 tests in `tests/` pass with characterization markers. | Incurable architectural flaws (F01-F06). Frozen for regression only. |
| **Legacy Virtual KME** | Deprecated / Simulated | `kme/virtual_node.py`. Flask app generating CSPRNG bytes via `os.urandom`. Unauthenticated. | Tested in `tests/test_kme.py`. | Fake QKD. Unauthenticated loopback HTTP only. |
| **Legacy Web Portal** | Deprecated / Insecure | `portal/portal_server.py`. Decrypts messages on server; stores private keys and ciphertexts in Firestore. | Characterized in `tests/test_legacy_characterization.py`. | Critical security vulnerability (F02, F10-F12). Excluded from modern path. |
| **Android Application** | **Not Implemented** | Proposed delivery target: Kotlin/Jetpack Compose UI + Rust JNI cryptographic boundary. | None. Zero code exists. | Platform roadmap amendment approved by owner (2026-11-01). Feasibility spike required. |
| **Hardware QKD / ESP32** | **Not Implemented** | Deferred research track. | None. Zero code exists. | Excluded from approved project scope. |

---

## 6. Data Flow and Execution Lifecycle

### 6.1 Modern Message Composition & Transmission Lifecycle
```
User Enters Draft (To, Subject, Body, Attachments)
       |
       v
Workflows.save() ---------------------------------> Write Draft to SQLite Outbox (Encrypted)
       |
       v
Workflows.recipients() ---------------------------> Validate verified certificate & pin for each recipient
       |
       v
Workflows.prepare() ------------------------------> Compose.prepare()
       |                                                   |
       |                                                   v
       |                                            MIME Builder: Construct RFC 9788 Inner MIME
       |                                                   |
       |                                                   v
       |                                            Spawn Native Helper (qumail-m5-provider.exe)
       |                                            - Pass inner MIME + recipient public subkeys
       |                                            - Sign with ML-DSA-65 / Encrypt with ML-KEM-768
       |                                            - Receive armored RFC 3156 PGP/MIME payload
       |                                                   |
       |                                                   v
       |                                            Envelope Bound & Frozen in SQLite Outbox
       |                                            - Status: PREPARED
       |
       v
Workflows.submit() -------------------------------> SubmitOutbox.submit()
       |                                                   |
       |                                                   v
       |                                            Acquire OS Process Lock (ownership.py)
       |                                            - Transition to SUBMITTING in SQLite
       |                                                   |
       |                                                   v
       |                                            Resolve XOAUTH2 Token from Vault
       |                                                   |
       |                                                   v
       |                                            Connect smtp.gmail.com:587
       |                                            - TLS Handshake & Hostname Validation
       |                                            - Send XOAUTH2 Authentication
       |                                            - Transmit Frozen RFC 3156 Bytes
       |                                                   |
       |                         +-------------------------+-------------------------+
       |                         |                                                   |
       |                         v (Success 250 OK)                                  v (Socket Drop / Timeout)
       |                  Transition to ACCEPTED                              Transition to UNKNOWN
       |                  - Delivery complete                                 - Requires operator inspection
       |                  - Archive decrypted copy saved                      - No blind auto-retry
```

### 6.2 Modern Message Retrieval & Decryption Lifecycle
```
User Clicks Refresh Headers
       |
       v
GmailMailbox.fetch_headers() ---------------------> Connect imap.gmail.com:993 (TLS + XOAUTH2)
       |                                            - Send EXAMINE INBOX (Read-Only)
       |                                            - UID SEARCH ALL (Bounded to 30 most recent)
       |                                            - UID FETCH ... (BODY.PEEK[HEADER.FIELDS (...)])
       |                                            - Update Encrypted Header Cache in Vault
       |                                            - Note: Seen flag is NEVER modified
       |
       v
User Selects Message in MailboxWindow
       |
       v
MailboxWindow spawns FetchBodyWorker -------------> Checks Account Generation Ticket
       |                                            - Connects IMAP (EXAMINE)
       |                                            - UID FETCH ... BODY.PEEK[]
       |                                            - Receives raw RFC 822 wire bytes
       |
       v
OpenMessage.open() -------------------------------> Inspect Outer MIME Headers
       |                                            - Extract multipart/encrypted wrapper
       |                                                   |
       |                                                   v
       |                                            Spawn Native Helper (qumail-m5-provider.exe)
       |                                            - Pass ciphertext + recipient secret subkey
       |                                            - Decapsulate ML-KEM-768 / Decrypt AES-GCM
       |                                            - Verify ML-DSA-65 Composite Signature
       |                                                   |
       |                                                   v
       |                                            Parse RFC 9788 Protected Inner Headers
       |                                            - Compare Outer vs Inner From/Subject
       |                                            - Check Monotonic Replay Cache in Vault
       |                                            - Match Signer Fingerprint Against Vault Pins
       |
       v
Display Model Emitted ----------------------------> MailboxWindow Renders Plain Text
                                                    - Verified Badge if Signature & Pin Match
                                                    - Warning if Outer/Inner Header Mismatch
                                                    - Conflict Alert if Replay Detected
                                                    - Plain text ONLY (HTML strictly denied)
```

---

## 7. Internal and External Integration Assessment

### 7.1 External Provider Integrations
- **Google OAuth 2.0 Identity Platform:**
  - **Implementation:** `transport/bounded_google.py` and `transport/development_google.py`.
  - **Verification:** Implements RFC 7636 S256 PKCE with ephemeral IPv4 loopback callback servers (`127.0.0.1:<random-port>`). Verifies ID token JWT signatures against Google's live JWKS endpoints (`https://www.googleapis.com/oauth2/v3/certs`), enforcing zero clock skew, exact client audience match, issuer validity (`https://accounts.google.com`), and subject-to-email binding.
  - **Environment Requirements:** Explicit Google Cloud Console "Desktop App" OAuth client credentials JSON. Test users must be provisioned.
  - **Status:** Offline tests pass (14/14). Live browser interaction verified up to token exchange; token-time rejection resolved by bounded wait; live end-to-end send pending owner execution.
- **Gmail IMAP Service (`imap.gmail.com:993`):**
  - **Implementation:** `mailbox_client/gmail.py`.
  - **Verification:** TLS 1.3 socket with system certificate authority validation. Authenticates via SASL `XOAUTH2`. Strictly avoids state-altering IMAP commands during reads (`SELECT`, `CLOSE`, `EXPUNGE` avoided; `EXAMINE` and `BODY.PEEK` enforced).
  - **Status:** Fully functional in unit and loopback harness tests.
- **Gmail SMTP Service (`smtp.gmail.com:587`):**
  - **Implementation:** `mailbox_client/smtp.py`.
  - **Verification:** Connects in cleartext, issues `EHLO`, mandates `STARTTLS`, verifies hostname and TLS certificates, re-issues `EHLO`, authenticates via `XOAUTH2`, and submits raw MIME DATA.
  - **Status:** Qualified over TLS loopback and integration harnesses. Requires `--dev-gmail-submit` flag to enable live network submission.

### 7.2 Operating System & Local Integrations
- **Windows Credential Manager (Win32 API):**
  - **Implementation:** `experiments/m3/secure_store.py` via `ctypes.windll.advapi32`.
  - **Functions:** `CredWriteW`, `CredReadW`, `CredDeleteW`.
  - **Target Identifier:** `QuMail/M3/Vault/<vault_id_hex>`.
  - **Security Profile:** Stores the 32-byte master key with `CRED_PERSIST_LOCAL_MACHINE` (persist level 2). Keys survive reboots and are isolated per Windows user account.
  - **Environmental Note:** Denied inside sandboxed shells lacking interactive user tokens (`secure_store_unavailable`); functions flawlessly in normal Windows user logon desktop sessions.
- **SQLite Database Engine:**
  - **Implementation:** `experiments/m3/vault.py`, `experiments/m4/repository.py`, `services/relay/store.py`.
  - **Configuration:** `PRAGMA journal_mode = WAL`, `PRAGMA synchronous = FULL`. Immediate transactions (`BEGIN IMMEDIATE`) prevent concurrent write deadlocks. Writer timeout set to 5.0 seconds.

### 7.3 Inter-Process Communication (IPC)
- **Rust Native Cryptographic Helpers:**
  - **Binaries:** `tmp/m2/target/debug/qumail-m3-provider.exe`, `tmp/m2/target/debug/qumail-m5-provider.exe`.
  - **Transport:** Anonymous standard input/output OS pipes.
  - **Protocol:** Version-1 JSON request/response payloads with byte buffers serialized as integer lists.
  - **Safeguards:** 8 MiB maximum pipe transfer limit, 30-second hard execution timeout, native stderr suppressed from leaking to console, 50 ms cancellation polling.

---

## 8. Security and Reliability Assessment

### 8.1 Cryptographic Architecture & Invariants
- **Composite Public Key Algorithms:**
  - **KEM:** NIST FIPS 203 **ML-KEM-768** combined with **X25519** (NIST Category 3 / 128-bit quantum security level). Both shared secrets are derived and combined into the final symmetric encryption key.
  - **Digital Signatures:** NIST FIPS 204 **ML-DSA-65** combined with **Ed25519**. Signatures are generated over the SHA-512 digest of the message. Both signatures must verify; failure of either rejects the entire message.
- **Symmetric Encryption & Integrity:**
  - Uses OpenPGP v6 packets with **SEIPDv2 (Symmetrically Encrypted Integrity Protected Data Packet version 2)** utilizing **AES-256-GCM** in 4 KiB chunks.
  - Eliminates vulnerable MDC (Modification Detection Code) and legacy cipher modes (CFB).
- **No Insecure Fallback:**
  - The modern pipeline contains zero fallback to plaintext, unauthenticated XOR, legacy TQR, or web portal decryption. If a provider fails or a signature is invalid, the operation fails closed with a typed `BoundaryError`.

### 8.2 Key Custody & Identity Lifecycle
- **Master Key Protection:** The vault encryption key is never written to disk or configuration files. It exists solely in process memory and the Windows Credential Manager.
- **Subkey Separation:** An enrolled identity possesses a primary v6 certification root key, which certifies two dedicated subkeys: an authentication/signing subkey and an encryption/decryption subkey. Subkey compromise does not compromise root identity.
- **Explicit Trust Ceremony:** A contact's public certificate must be imported and pinned by fingerprint. Outer SMTP `From:` headers are treated as untrusted transport claims; verified identity is established exclusively from the inner signed RFC 9788 header matching a pinned root key.

### 8.3 Concurrency, Race Conditions & UI Safety
- **GUI Thread Isolation:** PyQt6 UI widgets are manipulated exclusively on the main GUI thread. Long-running native cryptography, SQLite operations, and network transactions execute in background threads/subprocesses.
- **Cross-Process Outbox Locks (`experiments/m4/ownership.py`):** An operating-system level file lock (`msvcrt.locking` on Windows / `fcntl.flock` on Unix) guarantees that two competing QuMail processes or worker threads cannot submit or recover the same outbox operation simultaneously.
- **Commit Guard Pattern:** Workers stage database modifications in local memory, check session validity, execute `Guard.reserve()`, perform disk commits, and record encrypted owner outcome receipts.

---

## 9. Code Quality & Engineering Practices

### 9.1 Strengths
- **Exemplary Modern Engineering:** The modern modules (`core/account_session.py`, `core/settings_operations.py`, `mailbox_client/workflows.py`, `experiments/m4/services.py`, `experiments/m5/mime.py`) demonstrate exceptionally high engineering standards. Code is modular, type-annotated, uses immutable dataclasses, enforces strict input validation, and implements defense-in-depth against state desynchronization.
- **Zero Information Leakage:** Debug logging explicitly scrubs or omits sensitive materials (tokens, private keys, plaintext bodies, callback URLs).
- **Hermetic Test Fixtures:** Modern test suites clean up disposable Windows Credential Manager entries, temporary SQLite files, and loopback TLS sockets deterministically.

### 9.2 Technical Debt & Architectural Weaknesses
- **Application Dependencies in `experiments/`:** Core application logic and data models reside in `experiments/m3`, `experiments/m4`, and `experiments/m5`. While fully functional and tested, maintaining primary dependencies in an `experiments` directory creates architectural ambiguity and onboarding friction.
- **Hardcoded Native Helper Paths:** `main.py`, `ui/mailbox_window.py`, and `ui/mail_actions.py` locate native helpers via relative path arithmetic (`../../tmp/m2/target/debug/qumail-*.exe`). This breaks if the working directory changes or when packaging for production.
- **Low Operational Wire/Attachment Limits:** The modern profile enforces `MAX_WIRE = 256 KiB` and `MAX_ATTACHMENT_BYTES = 16 KiB`. While appropriate for proof-of-concept testing, these limits are too small for real-world email usage (the canonical spec targets 25 MiB wire / 15 MiB attachment).
- **Dead Legacy Code Coupling:** The repository retains substantial legacy code (`ui/main_window.py`, `crypto/tqr.py`, `kme/`, `portal/`). Although bypassed by `--dev-mailbox`, its presence complicates static analysis and risks accidental invocation if flags are omitted.

---

## 10. Testing Infrastructure & Validation Status

### 10.1 Test Suites and Execution Commands
The repository contains four distinct testing tiers:

1. **Legacy Characterization Suite (`tests/`):**
   - **Command:** `$env:OQS_INSTALL_PATH = (Resolve-Path tmp/oqs-install).Path; python -m pytest tests -q`
   - **Result:** **37 passed, 5 deprecation warnings in 4.20s.**
   - **Coverage:** Characterizes legacy behavior, virtual KME, legacy cert generation, and ensures backward compatibility of legacy data readers.

2. **Modern M3 Identity & Vault Suite (`experiments/m3/tests/`):**
   - **Command:** `python -m pytest experiments/m3/tests -q`
   - **Result:** **54 passed in 11.23s (normal order), 54 passed in 11.42s (reverse order).**
   - **Coverage:** Windows Credential Manager, AES-GCM vault, PKCE Google ID token verifier, subkey rotation, recovery backup/restore.

3. **Modern M4 Durable Outbox Suite (`experiments/m4/tests/`):**
   - **Command:** `python -m pytest experiments/m4/tests -q`
   - **Result:** **85 passed in 91.35s (normal order), 85 passed in 90.53s (reverse order).**
   - **Coverage:** Crash boundaries, process kill injection, SQLite commit failure, loopback STARTTLS, exact retry bytes.

4. **Modern M5 Protected MIME Suite (`experiments/m5/tests/`):**
   - **Command:** `python -m pytest experiments/m5/tests -q`
   - **Result:** **55 passed in 84.17s (normal order), 55 passed in 82.23s (reverse order), 2 native provider tests passed.**
   - **Coverage:** RFC 3156 PGP/MIME, RFC 9788 direct protected headers, sender archive decryption, replay detection, resource limits.

5. **Modern M6 Mailbox Workflows & Settings Suite (`experiments/m6/`):**
   - **Command:** `python -m pytest experiments/m6 -q`
   - **Result:** **96 passed.**
   - **Coverage:** Gmail IMAP PEEK, asynchronous Settings, commit reservation guards, attachment export no-clobber, threading derivation.

6. **Modern M7 Local Ciphertext Relay Suite (`experiments/m7/`):**
   - **Command:** `python -m pytest experiments/m7 -q`
   - **Result:** **13 passed in 10.45s.**
   - **Coverage:** mTLS loopback server, client cert allowlists, atomic leases, 128-request / 8-process lease race, quotas, tombstones.

7. **Latest Checkpoint Combined Regression Suite:**
   - **Command:** `python -m pytest experiments/m7 experiments/m6 experiments/m3/tests -q -rA`
   - **Result:** **163 passed in 122.39s** (normal order); exact 27-test reverse subset passed in 29.42s. Zero skips, zero warnings.

---

## 11. Identified Bugs, Missing Components, and Gaps

### 11.1 Critical & High Priority Issues
1. **QM-BUG-001 (Critical): Launcher / Desktop Filesystem Visibility Mismatch**
   - **Evidence:** `AI_HANDOVER.md:42`, `docs/handover/STATUS_AND_ROADMAP.md:35-48`.
   - **Description:** The acceptance launcher targets `%LOCALAPPDATA%\QuMailAcceptance\2026-10-22-google-m7\acceptance.sqlite`. Tool subprocesses see this path, but the user's interactive Windows desktop File Explorer cannot find the parent folder.
   - **Impact:** Prevents the owner from conducting live desktop UI verification.
   - **Resolution:** Provide a tested, explicit desktop launcher pointing to a verified desktop path (`2026-11-01-desktop`), allowing the owner to create and enroll a disposable vault without silent data overwrites.

2. **QM-GAP-001 (High): Unexecuted Live Google End-to-End Verification**
   - **Evidence:** `docs/operations/m6-google-acceptance.md`.
   - **Description:** While Google OAuth token exchange and verifier clock-wait were implemented and tested, the complete live sequence (two accounts A & B, token refresh, unread PEEK retrieval, public key exchange, A→B attachment send, B→A reply/forward) remains unverified with live accounts.
   - **Impact:** Prevents claim of full live operational capability.
   - **Resolution:** Execute the manual checklist (`docs/operations/google-manual-acceptance.md`) with owner participation.

3. **QM-GAP-002 (High): Missing Android Implementation**
   - **Evidence:** `docs/handover/STATUS_AND_ROADMAP.md:101-106`.
   - **Description:** The owner approved Windows and Android as delivery goals (2026-11-01). Currently, zero lines of Android code exist.
   - **Impact:** Fails product roadmap requirement for mobile secure email.
   - **Resolution:** Execute the prioritized Android delivery track (A1–A8): Rust ABI compilation, JNI boundary, Android Keystore integration, Jetpack Compose UI.

4. **QM-DEBT-001 (Medium): Core Dependencies Located in `experiments/`**
   - **Evidence:** `core/identity_service.py`, `mailbox_client/workflows.py` importing from `experiments/m3`, `m4`, `m5`.
   - **Description:** The production application directly imports data models and providers from temporary milestone experiment folders.
   - **Impact:** Violates clean architecture, impedes packaging, and creates developer confusion.
   - **Resolution:** Mechanically consolidate `experiments/m3`, `m4`, `m5` into permanent packages (`qumail/core`, `qumail/storage`, `qumail/protocol`, `qumail/crypto`) preserving backward compatibility shims.

5. **QM-LIMIT-001 (Medium): Severely Constrained Wire and Attachment Limits**
   - **Evidence:** `experiments/m5/model.py:8-15` (`MAX_WIRE = 256 KiB`, `MAX_ATTACHMENT_BYTES = 16 KiB`).
   - **Description:** Limits are artificially small development caps, preventing exchange of standard documents or images.
   - **Impact:** Inadequate for real-world user communication.
   - **Resolution:** Incrementally expand limits with streaming or bounded chunked parsing, accompanied by hostile-input and memory-exhaustion regression tests.

---

## 12. Prioritized Issue Register

| ID | Title | Priority | Complexity | Affected Components | Recommended Resolution |
|---|---|---|---|---|---|
| **QM-BUG-001** | Launcher/Desktop Path Divergence | **Critical** | Low | `tools/start_google_acceptance.ps1`, `main.py` | Verify desktop path visibility, update dry-run launcher, confirm Settings reachability without creation. |
| **QM-GAP-001** | Live Google End-to-End Acceptance | **High** | Medium | `mailbox_client`, `transport`, Google OAuth | Execute manual checklist with owner-supplied test accounts A/B; verify retrieval, send, reply, forward. |
| **QM-GATE-001**| Usable-Security & Accessibility Walkthrough | **High** | Low | `ui/mailbox_window.py`, `ui/mail_accessibility.py` | Conduct human operator walkthrough of keyboard navigation, screen reader labels, and error dialogues. |
| **QM-DEBT-001**| Consolidate `experiments/` into Core Tree | **Medium** | Medium | `experiments/m3..m5`, `core/`, `mailbox_client/` | Move shared modules to `qumail/{storage,protocol,outbox}`; retain backward-compatible import shims. |
| **QM-LIMIT-001**| Expand Wire & Attachment Caps | **Medium** | Medium | `experiments/m5/model.py`, `mime.py` | Benchmark and expand wire cap to 2 MiB / attachments to 1 MiB with memory guards. |
| **QM-GATE-002**| Independent Cryptographic & Parser Review | **Medium** | High | Native providers, PGP/MIME parser | Prepare review packages for external cryptographer review prior to production security release. |
| **QM-GAP-002** | Android Feasibility & JNI Engine | **Medium** | High | Android NDK, Rust ABI, JNI bindings | Compile Sequoia + OpenSSL static for arm64-v8a; validate JNI boundary with vector tests. |
| **QM-GAP-003** | Android Jetpack Compose Application Shell | **Future** | High | Android app, Android Keystore, WorkManager | Build native Android email client consuming JNI crypto engine and Android Keystore master keys. |

---

## 13. Dependency-Aware Modular Development Roadmap

```
+---------------------------------------------------------------------------------+
| Phase 1: Immediate Stabilization & Acceptance (P0 / P1)                         |
|   +-------------------------------------------------------------------------+   |
|   | Module 1.1: Desktop Launch Handoff & Path Resolution (QM-BUG-001)        |   |
|   | - Verify desktop filesystem visibility for acceptance vault             |   |
|   | - Validate launcher dry run stopping before creation                    |   |
|   +------------------------------------+------------------------------------+   |
|                                        |                                        |
|                                        v                                        |
|   +-------------------------------------------------------------------------+   |
|   | Module 1.2: Live Google Acceptance Execution (QM-GAP-001)               |   |
|   | - Execute manual checklist with owner test accounts A and B             |   |
|   | - Verify unread PEEK retrieval, public key pinning, 3 test sends        |   |
|   +------------------------------------+------------------------------------+   |
|                                        |                                        |
|                                        v                                        |
|   +-------------------------------------------------------------------------+   |
|   | Module 1.3: Usable-Security & Accessibility Walkthrough (QM-GATE-001)   |   |
|   | - Human verification of keyboard focus, contrast, and cancellation      |   |
|   +------------------------------------+------------------------------------+   |
+----------------------------------------|----------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
| Phase 2: Architecture Consolidation & Production Hardening (P2)                 |
|   +-------------------------------------------------------------------------+   |
|   | Module 2.1: Package Restructuring & Path Decoupling (QM-DEBT-001)       |   |
|   | - Move experiments/m3..m5 to permanent qumail/ packages                 |   |
|   | - Decouple native helper paths via environment/package lookup           |   |
|   +------------------------------------+------------------------------------+   |
|                                        |                                        |
|                                        v                                        |
|   +-------------------------------------------------------------------------+   |
|   | Module 2.2: Safe Resource Limit Expansion (QM-LIMIT-001)                |   |
|   | - Expand message and attachment size limits with memory-budget tests    |   |
|   +------------------------------------+------------------------------------+   |
|                                        |                                        |
|                                        v                                        |
|   +-------------------------------------------------------------------------+   |
|   | Module 2.3: Independent Interoperability Qualification                   |   |
|   | - Test RFC 3156 / RFC 9788 envelopes against independent PGP/MIME peer   |   |
|   +-------------------------------------------------------------------------+   |
+----------------------------------------+----------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
| Phase 3: Android Platform Delivery Track (P2 / P3)                              |
|   +-------------------------------------------------------------------------+   |
|   | Module 3.1: Android Native Cryptographic Core (Track A1-A2)             |   |
|   | - Compile Sequoia + OpenSSL static library for Android NDK (arm64-v8a)  |   |
|   | - Implement narrow, memory-safe JNI boundary with structured errors     |   |
|   +------------------------------------+------------------------------------+   |
|                                        |                                        |
|                                        v                                        |
|   +-------------------------------------------------------------------------+   |
|   | Module 3.2: Android Keystore & Identity Custody (Track A3-A4)           |   |
|   | - Implement Android Keystore hardware-wrapped key encryption            |   |
|   | - Android OAuth2 AppAuth integration with Gmail                         |   |
|   +------------------------------------+------------------------------------+   |
|                                        |                                        |
|                                        v                                        |
|   +-------------------------------------------------------------------------+   |
|   | Module 3.3: Jetpack Compose Mailbox Client (Track A5-A8)                |   |
|   | - Native Compose UI for inbox, compose, and contact verification        |   |
|   | - WorkManager durable background sending engine                         |   |
|   +-------------------------------------------------------------------------+   |
+---------------------------------------------------------------------------------+
```

---

## 14. GitHub Branch & Version Control Strategy

### 14.1 Current Repository State
- **Active Branch:** `codex/m7-relay-google-acceptance`
- **Current HEAD:** `5658601` ("Preserve engineering handover and Windows Android delivery roadmap")
- **Remote Origin:** `https://github.com/uzx-02/QuMail.git`
- **Tracked Changes:** Clean working tree.
- **Excluded Untracked Files:**
  - `QuMail-1.0-Research-Audit-Specification.pdf` (Reference copy)
  - `Start-QuMailDemo.ps1` (Presentation script)
  - `docs/operations/m2-reviewer-request.md` (Local reviewer draft)
  - `tmp/` (Private build caches, local test databases, test artifacts)

### 14.2 Branching Model for Next Modules
1. **Branch Isolation:**
   - Retain `codex/m7-relay-google-acceptance` as the stable M7 baseline.
   - For immediate stabilization (Phase 1), work directly on a focused branch: `codex/m7-desktop-handoff`.
   - For Phase 2 consolidation: `codex/m8-consolidation`.
   - For Phase 3 Android delivery: `codex/android-engine`.
2. **Commit Discipline:**
   - Follow strict Conventional Commits syntax:
     - `fix(launcher): resolve desktop filesystem path divergence`
     - `test(acceptance): record live google acceptance outcomes`
     - `refactor(core): migrate m3 vault to core package`
     - `feat(android): add jni cryptographic provider bindings`
   - Every commit must represent an independently reviewable, tested engineering checkpoint.
   - **Never commit:** Secrets, tokens, client JSON credentials, test databases, or compiled binaries.
   - **Verification before commit:** All affected unit and regression tests must pass with zero skips or hidden errors.

---

## 15. Final Recommendations and Immediate Next Steps

1. **Do Not Rewrite Working Components:** The modern core (`account_session`, `settings_operations`, `workflows`, `vault`, `ownership`, `mime`) is robust, elegant, and mathematically sound. Avoid broad rewrites.
2. **Execute Desktop Launch Dry-Run First (P0):** Before any new feature development, resolve the tool vs. desktop path mismatch so the owner can launch QuMail in their normal desktop logon session and reach the Settings window cleanly.
3. **Support Owner in Live Google Acceptance (P1):** Provide clean instructions and wait for the owner to conduct the manual A/B testing checklist.
4. **Begin Android Feasibility Spike in Parallel:** Once Phase 1 is validated, initiate the Android native build environment (NDK + Rust cross-compilation) to establish proof of cryptographic compatibility on mobile devices.

---
*End of Software Engineering Audit Report.*
