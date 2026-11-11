# QuMail — Post-Quantum Secure Corporate Email Client

> [!WARNING]
> **Engineering Status: Pre-Production Research Prototype**  
> QuMail is currently an active development prototype undergoing architectural consolidation. It is **not** approved for commercial deployment, production security use, or handling unencrypted classified/sensitive communications without independent third-party cryptographic review.

---

## 1. Project Overview

**QuMail** is a desktop email application designed to explore and implement post-quantum secure messaging protocols for corporate communication on 64-bit Windows environments.

The project is built around the **RFC 3156 / RFC 9788 OpenPGP-PQ** hybrid profile (`QM-OPENPGP-PQ-v1`). Its core engineering goal is to protect email content and attachments against future "Harvest Now, Decrypt Later" (HNDL) attacks by combining classical cryptographic primitives with NIST post-quantum standards:
- **Key Encapsulation:** NIST FIPS 203 **ML-KEM-768** hybrid-wrapped with classical **X25519**.
- **Digital Signatures:** NIST FIPS 204 **ML-DSA-65** composite-signed with classical **Ed25519**.
- **Symmetric Encryption:** **AES-256-GCM** authenticated encryption with Associated Authenticated Data (AAD).
- **Local Vault Storage:** Encrypted SQLite local databases protected by the Windows Data Protection API (**DPAPI**).

---

## 2. Current Implementation Status

An evidence-based forensic audit of the repository establishes that while the core Rust-based cryptographic engine and durable outbox state machine are functional, the application exhibits significant architectural fragmentation, duplicate presentation layers, disconnected microservices, and simulated fallback paths.

| Subsystem / Layer | Current Reality |
|---|---|
| **Core Post-Quantum Engine** | **Verified Functional:** Native 64-bit Rust binaries (`bin/qumail-m3-provider.exe`, `bin/qumail-m5-provider.exe`) successfully generate keypairs, sign, seal, open, and verify OpenPGP-PQ envelopes. |
| **Durable Outbox & Reconciliation** | **Verified Functional:** SQLite-backed outbox enforces strict delivery state transitions, prevents duplicate automatic retries on `UNKNOWN`, and reconciles against IMAP Sent folders. |
| **Desktop Client (React 19 / WebView2)** | **Functional:** Unified desktop interface renders via Microsoft Edge WebView2 (`pywebview`), backed by native Rust cryptographic providers, Google OAuth 2.0 PKCE, and IMAP/SMTP sync. PyQt6 has been completely purged from the codebase. |
| **Directory & Merkle Transparency** | **Partially Functional (Isolated):** Merkle tree and challenge-response server exist in Python, but are disconnected from desktop client compose and receive workflows. |
| **Secure Web Link Portal** | **Partially Functional (Isolated):** Local Flask server exists, but client does not actually upload encrypted payloads to the portal server over HTTP. |
| **Android Mobile Companion** | **Mocked / Simulated:** Android Kotlin/Compose UI exists with hardcoded mock emails; native Rust JNI returns static hardcoded bytes with no cryptographic operations. |
| **Hardware TRNG & QKD** | **Simulated / Stubbed:** COM port registry scanning works, but physical serial ingestion lacks dependencies (`pyserial`); ETSI QKD client uses a local in-memory mock key generator. |

---

## 3. Technology Stack

### Core Runtime & Languages
- **Python:** CPython 3.12 (Windows x64 baseline)
- **Rust:** Rust 1.99+ (MSVC toolchain, `nightly-x86_64-pc-windows-msvc`) with PE security mitigations (ASLR, DEP/NX, Control Flow Guard)
- **TypeScript & React:** React 19, TypeScript 5.7, Vite 6, Tailwind CSS 3.4 (for modern WebView2 presentation)
- **C# / .NET:** Edge WebView2 WinForms interop via `pythonnet` and `clr_loader`

### Core Libraries & Frameworks
- **GUI:** Microsoft Edge WebView2 (`pywebview 5.4+`) with React 19, TypeScript 5.7, Tailwind CSS (PyQt6 completely purged)
- **Cryptography:** `cryptography 50.0.2` (Python), `sequoia-openpgp 2.4.1`, `rpgp 0.21.0`, and OpenSSL 3.5.9 (in Rust providers)
- **Protocols & Transport:** `google-auth 2.49.1`, `google-auth-oauthlib 1.3.0`, standard library `imaplib`, `smtplib`, `email`
- **Testing:** `pytest 8.4.2`
- **Packaging:** PyInstaller, Inno Setup 6

---

## 4. Architecture & Repository Structure

The codebase is structured into the following operational modules:

```
QuMail/
├── bin/                        # Verified native 64-bit Rust provider binaries & manifest
│   ├── qumail-m3-provider.exe  # Identity, DPAPI vault, and subkey management
│   ├── qumail-m5-provider.exe  # RFC 3156 / RFC 9788 OpenPGP-PQ message sealing/opening
│   └── manifest.json           # SHA-256 hashes and PE mitigation security metadata
├── core/                       # Shared application business logic
│   ├── enterprise_policy.py    # Windows Registry GPO policy parsing
│   ├── identity_service.py     # Python bridge to M3 SQLite DPAPI vault
│   ├── key_discovery.py        # RFC 9580 WKD discovery with anti-SSRF IP filtering
│   ├── outbox_manager.py       # Durable SQLite outbox state machine
│   ├── outbox_reconciliation.py# Background Sent-folder IMAP reconciliation
│   ├── provider_resolver.py    # Binary path resolver and integrity verifier
│   └── web_link_crypto.py      # Client-side AES-256-GCM sealing for web link delivery
├── crypto/                     # Legacy M1/M2 prototype crypto & deprecation characterizations
├── mailbox_client/             # Message retrieval and workflow coordination
│   ├── gmail.py                # Gmail IMAP connection with XOAUTH2 and PEEK flags
│   ├── smtp.py                 # RFC 5321 SMTP submission transport
│   └── workflows.py            # M5 transactional compose, prepare, and submit workflows
├── transport/                  # Transport adapters and authentication handlers
│   ├── oauth2_gmail.py         # Google OAuth 2.0 PKCE loopback consent flow
│   ├── custom_mailbox.py       # Generic IMAP/SMTP host discovery & Fernet credential store
│   ├── imap_receiver.py        # Generic IMAP inbox fetching and decapsulation
│   └── smtp_sender.py          # Generic SMTP outgoing message dispatch
├── frontend/                   # Modern React 19 + Tailwind CSS web application
│   ├── src/                    # React UI components, icons, and theme managers
│   └── dist/                   # Production Vite bundle served to Edge WebView2
├── launch_react_desktop.py     # React desktop launcher helper (Edge WebView2 bridge)
├── main.py                     # Primary desktop entry point (React 19 + Edge WebView2 launcher)
├── services/                   # Standalone microservices (isolated prototypes)
│   ├── directory/              # RFC 6962 / RFC 9162 Merkle tree transparency directory
│   ├── portal/                 # Ephemeral zero-knowledge web link staging & OTP verification
│   └── relay/                  # M7 loopback mTLS ciphertext relay
├── tests/                      # Automated regression, unit, and integration test suites
├── packaging/                  # Dependency requirement manifests and lockfiles
├── deploy/                     # Inno Setup scripts and enterprise GPO ADMX/ADML templates
└── recycle/                    # Preserved historical documentation archive
    └── markdown-archive/       # Archived obsolete specifications, reports, and logs
```

---

## 5. Feature Implementation Matrix

| Subsystem / Feature | Implementation Status | Actual Functional Behavior | Known Limitations |
|---|---|---|---|
| **M3 DPAPI Vault** | VERIFIED FUNCTIONAL | Generates post-quantum identities, encrypts database with Windows DPAPI, manages subkeys. | Windows-only DPAPI binding; non-portable across machines. |
| **M5 OpenPGP-PQ Sealing** | VERIFIED FUNCTIONAL | Seals and opens MIME envelopes with ML-KEM-768 and ML-DSA-65 signatures. | Requires recipient public key pre-enrolled in local vault or WKD. |
| **Durable Outbox** | VERIFIED FUNCTIONAL | Persists message records in SQLite; reconciles with IMAP Sent folder; halts on UNKNOWN. | Requires active IMAP connection to confirm ambiguous delivery. |
| **Google OAuth 2.0 PKCE** | VERIFIED FUNCTIONAL | Completes browser consent flow; retrieves access/refresh tokens; auto-refreshes tokens. | Requires user-provided `client_secret.json`; CASA Tier 2 audit pending. |
| **Custom IMAP/SMTP** | VERIFIED FUNCTIONAL | Connects to external email servers via TLS/STARTTLS; encrypts credentials with Fernet. | Relies on standard username/password or provider App Passwords. |
| **WKD Key Discovery** | VERIFIED FUNCTIONAL | Derives z-base-32 WKD URLs; queries HTTPS endpoints; enforces anti-SSRF subnet blocks. | Does not upgrade keys to "Verified" without explicit enterprise certification. |
| **Desktop Client (React 19 / WebView2)** | PARTIALLY FUNCTIONAL | Modern interface rendering; Google OAuth login; live IMAP syncing; Edge WebView2 bridge. | Falls back to simulated AES-GCM without KEM for un-enrolled recipients. |
| **Public Directory Service** | PARTIALLY FUNCTIONAL | In-memory Merkle tree, Signed Tree Heads, and PoP challenge validation. | Ephemeral in-memory state; completely disconnected from client compose flow. |
| **Web Link Portal** | PARTIALLY FUNCTIONAL | Staging server with HMAC OTP verification. | Client does not upload encrypted blobs over HTTP; in-memory server state. |
| **Android Companion** | MOCKED / SIMULATED | Jetpack Compose UI with static mock email items. | Rust JNI returns static string; no cryptographic implementation. |
| **Hardware TRNG & QKD** | PARTIALLY SIMULATED | COM port discovery via Windows registry; NIST SP 800-90B health checking. | No serial transmission (`pyserial` missing); QKD client uses mock generator. |
| **Legacy M1/M2 TQR** | BROKEN / DEPRECATED | Insecure research prototype with XOR OTP and server-side private key storage. | Requires unapproved `liboqs-python` native build; disabled by default. |

---

## 6. Mock Data and Simulated Components

The audit identified several areas where simulated behavior or test fixtures exist:

1. **Simulated Post-Quantum Fallback (`launch_react_desktop.py`):**  
   When sending a message to a recipient whose public key is missing from the local vault, the React bridge falls back to generating a 32-byte symmetric key with `secrets.token_bytes(32)`, encrypts the payload with AES-GCM, stores the key in the sender's local `send_keys/` folder, and flags the message metadata as `"ML-KEM-768+AES-256-GCM"`. The remote recipient receives an encrypted payload with no KEM mechanism to decrypt it, while the sender's UI falsely reports "Post-Quantum Sealed".
2. **Disconnected Web Link Delivery (`launch_react_desktop.py` & `core/web_link_crypto.py`):**  
   The client creates a secure web link package pointing to `https://portal.qumail.invalid/view/<msg_id>#<key>`, but never performs an HTTP POST to upload the encrypted payload to `services/portal/server.py`.
3. **Android Crypto JNI Stub (`android/qumail_crypto_bridge/src/lib.rs`):**  
   The function `open_envelope_internal()` ignores all parameters and returns a hardcoded byte string `b"Verified Post-Quantum Message (ML-KEM-768 / ML-DSA-65)"`.
4. **ETSI QKD Local Simulator (`core/hsm/etsi_qkd.py`):**  
   `ETSI014LocalSimulator` simulates an optical quantum key distribution node using Python CSPRNG tokens with hardcoded node identifiers (`KME_AAVISHKAR_QUANTUM_1`).
5. **In-Memory Service Storage (`services/directory/server.py`, `services/portal/server.py`):**  
   Both modern services store state entirely in volatile Python dictionaries (`self.records = {}`, `self.blobs = {}`), losing all registrations and messages upon server restart.

---

## 7. Known Issues and Engineering Limitations

1. **Secret Leakage in Build Output (CRITICAL):**  
   PyInstaller and Inno Setup build configurations package private developer client secrets into `dist/QuMail-App/secrets/gmail_client_secret.json` and resulting installer packages.
2. **Simulated Fallback for Unenrolled Recipients (HIGH):**  
   React desktop bridge falls back to local AES-GCM without KEM exchange when sending to an un-enrolled contact.
3. **Missing Dependency for USB TRNG (LOW):**  
   `core/hsm/detector.py` attempts to import `serial`, but `pyserial` is omitted from `packaging/requirements.in`.

---

## 8. Build and Execution Instructions

### Prerequisites
- **OS:** Windows 10 / 11 (64-bit x64)
- **Python:** Python 3.12 (64-bit)
- **Node.js:** Node.js 20+ (for building the React frontend)
- **Rust:** MSVC Nightly toolchain (only if recompiling native providers in `bin/`)

### Environment Setup
```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install locked runtime dependencies
pip install -r requirements.txt
```

### Launching the Application

```powershell
# 1. Launch unified desktop application (React 19 + Microsoft Edge WebView2)
python main.py

# Launch connected to live Vite development server (hot reloading)
python main.py --dev

# Verify native cryptographic engine integrity
python main.py --check-provider

# Export operational diagnostics bundle
python main.py --export-diagnostics "qumail_diagnostics.json"
```

---

## 9. Testing and Verification

The repository contains 26 test suites in `tests/` comprising **266 automated test cases** (PyQt6-specific UI tests removed following full UI consolidation onto React 19).

### Executing Regression Suites

#### Modern Core Regression Suite (Verified Passing: 232/232 tests)
Runs the modern identity, outbox, reconciliation, cryptography, directory, and UI suites:
```powershell
pytest tests/test_ws01_bootstrap_hygiene.py `
       tests/test_ws02_identity_and_trust.py `
       tests/test_ws02_security_assurance.py `
       tests/test_ws03_sync_and_attachments.py `
       tests/test_ws04_outbox_and_reconciliation.py `
       tests/test_ws05_ui_and_experience.py `
       tests/test_ws06_ws07_packaging_and_deployment.py `
       tests/test_cancellation_submission_semantics.py `
       tests/test_cryptographic_roundtrip.py `
       tests/test_directory_service.py `
       tests/test_web_link_portal.py `
       tests/test_ui_redesign.py `
       tests/test_e2e_enterprise_workflow.py -q
```
**Result:** `232 passed in ~81s`

#### React Desktop Bridge Suite (Verified Passing: 9/9 tests)
```powershell
pytest tests/test_react_desktop_bridge.py -v
```
**Result:** `9 passed in ~1.0s`

#### Legacy Characterization Note
Running `pytest` without arguments executes all 321 tests, producing **313 passes and 8 failures**. The 8 failures stem from:
- 1 failure in `test_startup.py` due to the unhandled `PermissionError` on `AppData/Local/QuMail/vault.sqlite`.
- 7 failures in legacy characterization suites (`test_crypto.py`, `test_native_compatibility.py`, `test_tqr_roundtrip.py`) which require the deprecated C `liboqs` build path (`OQS_INSTALL_PATH`).

---

## 10. Security Considerations & Protected Artifacts

1. **Protected Client Secrets:**  
   The workspace retains intentional OAuth client configuration files (`secrets/gmail_client_secret.json`, `secrets/gmail_token.json`, and `.qumail_data/config/google_client_secret.json`). These files are protected repository artifacts used for local development and are excluded from Git tracking via `.gitignore`. Their contents must never be modified, deleted, committed, or exposed.
2. **Cryptographic Boundaries:**  
   Cryptographic operations are isolated inside compiled Rust binaries. Private keys and decrypted plaintext are zeroized in RAM immediately after use.
3. **No Unencrypted Fallbacks:**  
   In the PyQt6 client, sending to an unverified recipient strictly blocks preparation; unencrypted plaintext release is forbidden.
4. **External Distribution Gate:**  
   Public distribution requires a commercial Authenticode EV Code-Signing Certificate and a formal Google OAuth CASA Tier 2 assessment.

---

## 11. Development Roadmap & Priorities

Before QuMail can be considered reliable, production-ready software, the following remediation tasks must be addressed:

1. **Build & Release Sanitization:** Remove client secret files from PyInstaller bundles and Inno Setup source trees.
2. **Startup Crash Remediation:** Add exception handling around vault path probing in `main.py`.
3. **Presentation Layer Consolidation:** Retire one of the duplicate frontends (or complete the React/WebView2 backend wiring).
4. **Eliminate Crypto Mocks:** Remove the fake AES-GCM fallback in `launch_react_desktop.py` and enforce strict key discovery.
5. **Microservice Wiring:** Connect `services/directory` and `services/portal` to real persistent databases and wire them into client compose workflows.
6. **Mobile Track Realignment:** Formally reclassify the Android application as an early conceptual prototype until real JNI crypto is implemented.
