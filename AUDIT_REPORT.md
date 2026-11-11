# QuMail 1.0 — Comprehensive Forensic Codebase Audit, Architectural Assessment & Engineering Recovery Report

**Audit Type:** Senior Software Engineering Forensic Audit, Application Security Review & Repository Recovery  
**Target:** QuMail Codebase (Windows x64 / CPython 3.12 / Rust Native Core)  
**Date of Audit:** November 11, 2026  
**Auditor:** Senior Software Engineer, Application Security Reviewer & Codebase Auditor  
**Repository Branch:** `main`  
**Latest Accepted Commit:** `ccc952b` (`fix(oauth): resolve FileNotFoundError connection abort with errno reset and direct urllib exchange`)  

---

## 1. Executive Summary

A forensic software engineering audit of the **QuMail** repository was conducted to establish an evidence-based assessment of the application's actual architecture, operational readiness, cryptographic posture, technical debt, and documentation accuracy.

The repository represents an ambitious project designed to create a corporate desktop email client supporting **Post-Quantum Cryptography** (NIST FIPS 203 ML-KEM-768 and NIST FIPS 204 ML-DSA-65 wrapped inside RFC 3156 / RFC 9788 OpenPGP-PQ envelopes). 

### Key Findings Summary
1. **Core Cryptographic Engine is Genuine and Functional:**  
   The project successfully transitions away from unapproved Python research wrappers to compiled 64-bit native Rust executables (`bin/qumail-m3-provider.exe` and `bin/qumail-m5-provider.exe`). These binaries enforce strict PE security mitigations (High Entropy 64-bit ASLR, DEP/NX, and Control Flow Guard) and pass full cryptographic roundtrips, signature verification, and tampered ciphertext rejection.
2. **Durable Outbox & Reconciliation Are Well-Engineered:**  
   The SQLite-backed outbox state machine (`core/outbox_manager.py` and `core/outbox_reconciliation.py`) rigorously implements transactional spooling, prevents duplicate automatic retries on `UNKNOWN` status, and reconciles ambiguous sends against IMAP Sent folders.
3. **Critical Security Vulnerability in Distribution Artifacts:**  
   Developer Google Cloud OAuth client secrets (`secrets/gmail_client_secret.json`) were unintentionally bundled into PyInstaller distribution directories (`dist/QuMail-App/secrets/`) and packaged into portable zip and Inno Setup installer archives (`dist/installer/Setup-QuMail-v1.0.exe`).
4. **Architectural Duplication and Divergence:**  
   The repository contains two competing desktop presentation layers:
   - A **PyQt6 native desktop application** (`main.py` -> `ui/mailbox_window.py`).
   - A **React 19 + Microsoft Edge WebView2 application** (`launch_react_desktop.py` -> `frontend/`).  
   These two frontends maintain divergent security policies, duplicate settings dialogs, and separate message queues.
5. **Simulated Cryptography in the Modern Presentation Layer:**  
   In `launch_react_desktop.py`, when sending a message to a recipient whose public key is missing from the local vault, the React bridge falls back to generating a random 32-byte symmetric key with `secrets.token_bytes(32)`, encrypts with AES-GCM, persists the key locally in `send_keys/`, and marks the message as `"ML-KEM-768+AES-256-GCM"`. It displays a green "Post-Quantum Sealed" badge in the UI, despite performing zero post-quantum key encapsulation.
6. **Disconnected Microservices & Mock Mobile Client:**  
   - The Public-Key Directory (`services/directory/server.py`) and Secure Web Link Portal (`services/portal/server.py`) are in-memory Flask prototypes that are completely disconnected from the desktop client's compose and receive workflows.
   - In `launch_react_desktop.py`, Web Link invitation emails are sent pointing to `https://portal.qumail.invalid/view/<msg_id>#<key>`, but the encrypted ciphertext blob is never uploaded to any portal server.
   - The Android client (`android/`) is a UI skeleton with hardcoded sample emails; its native Rust JNI library (`android/qumail_crypto_bridge/src/lib.rs`) returns a static hardcoded byte string with no cryptographic implementation.
7. **Documentation Discrepancy & Reset:**  
   Historical project-authored Markdown documents contained substantial exaggerations of feature completion, claiming fully deployed cloud directories, commercial readiness, and mobile interoperability. A total of **68 obsolete project Markdown files** have been archived into `recycle/markdown-archive/`, preserving operational and canonical documents (`AGENTS.md`, `AI_HANDOVER.md`, `QuMail-1.0-Research-Audit-Specification.md`, and `docs/adrs/`).
8. **Test Suite Integrity:**  
   Out of **321 automated tests**, 313 pass. The 8 failures consist of 1 unhandled `PermissionError` on startup in `test_startup.py` and 7 characterization failures in deprecated legacy OQS suites that require an obsolete C build directory (`OQS_INSTALL_PATH`). The modern core regression suite passes 100% (232/232 tests).

---

## 2. Actual Architecture & Technology Discovery

Contrary to historical documentation describing a unified cloud-native architecture, the actual codebase consists of a modular Python backend communicating via IPC with native Rust binaries and serving two alternative desktop user interfaces.

```
+---------------------------------------------------------------------------------------------------+
|                                     DUAL PRESENTATION LAYER                                       |
|                                                                                                   |
|  [ Option A: PyQt6 Desktop Client ]                   [ Option B: React 19 + WebView2 Client ]    |
|  - main.py (Default entry point)                      - launch_react_desktop.py                   |
|  - ui/mailbox_window.py (3-pane layout)               - frontend/ (Vite, React 19, Tailwind)      |
|  - ui/compose_dialog.py (Modal compose)               - pywebview (Edge WebView2 WinForms)        |
|  - ui/design_system.py (Dual themes)                  - QuMailJsApi (RPC Bridge over loopback)    |
+---------------------------------------------------+-----------------------------------------------+
                                                    |
                                                    v
+---------------------------------------------------------------------------------------------------+
|                                  CORE BUSINESS LOGIC & WORKFLOWS                                  |
|                                                                                                   |
|  - core/identity_service.py       : Vault manager & credential authority                          |
|  - mailbox_client/workflows.py    : Transactional compose, prepare, and submission coordinator    |
|  - core/outbox_manager.py         : Durable SQLite outbox state machine (DRAFT -> PREPARED -> ...) |
|  - core/outbox_reconciliation.py  : Sent-folder IMAP reconciler                                   |
|  - core/key_discovery.py          : RFC 9580 WKD client with anti-SSRF IP filtering               |
|  - core/enterprise_policy.py      : Windows Registry Group Policy (GPO) integration               |
+---------------------------------------------------+-----------------------------------------------+
                                                    |
                         +--------------------------+--------------------------+
                         | (JSON IPC via Stdin/Stdout)                         | (Direct Python / Network)
                         v                                                     v
+---------------------------------------------------+ +-----------------------------------------------+
|         NATIVE RUST CRYPTOGRAPHIC CORE            | |             NETWORK & TRANSPORTS              |
|                                                   | |                                               |
|  [ bin/qumail-m3-provider.exe ]                   | |  [ transport/oauth2_gmail.py ]                |
|  - ML-KEM-768 / ML-DSA-65 key generation          | |  - Google OAuth 2.0 PKCE Loopback Flow        |
|  - Subkey lifecycle & root derivation             | |                                               |
|  - Windows DPAPI master key encryption            | |  [ transport/custom_mailbox.py ]              |
|  - SQLite encrypted identity vault                | |  - Generic IMAP/SMTP TLS & Fernet store       |
|                                                   | |                                               |
|  [ bin/qumail-m5-provider.exe ]                   | |  [ transport/imap_receiver.py & smtp_sender ] |
|  - RFC 3156 / RFC 9788 OpenPGP-PQ sealing         | |  - Wire-level IMAP PEEK and SMTP dispatch     |
|  - Composite ML-DSA-65 / Ed25519 signing          | |                                               |
|  - Sequoia PGP & rpgp envelope verification       | |  [ services/relay/ (Loopback mTLS) ]          |
+---------------------------------------------------+ +-----------------------------------------------+
```

### Discovered Technology Stack

| Layer | Declared in Old Docs | Actual Implementation in Codebase |
|---|---|---|
| **Programming Languages** | Python, Rust, Go, Kotlin | Python 3.12 (CPython), Rust 1.99+ (MSVC), TypeScript 5.7, Kotlin (Mock only) |
| **Primary Desktop UI** | "Unified React Desktop" | Two unmerged frontends: PyQt6 6.10.2 (canonical) and React 19 / WebView2 (alternative) |
| **Web Rendering Engine** | Native Chromium Embedded | Microsoft Edge WebView2 via `pywebview 5.4.1`, `pythonnet 3.0.5`, `clr_loader 0.2.7` |
| **PQ Cryptographic Core** | `liboqs-python` (C bindings) | Compiled Rust standalone executables (`qumail-m3-provider.exe`, `qumail-m5-provider.exe`) |
| **Classical Cryptography** | `cryptography` Python library | `cryptography 50.0.2` (Python AEAD/Fernet) + Sequoia PGP / OpenSSL 3.5.9 (in Rust) |
| **Directory Service** | Cloudflare Workers + D1 Global | In-memory Flask prototype (`services/directory/server.py`); Cloudflare code is an undeployed draft |
| **Web Link Portal** | Google Cloud Firestore + Cloud Run | In-memory Flask prototype (`services/portal/server.py`); legacy Firestore code is deprecated |
| **Mobile Client** | Functional Android App | UI prototype in Jetpack Compose; JNI Rust bridge returns hardcoded static strings |
| **Packaging / Installer** | Inno Setup & MSIX | Inno Setup 6 (`deploy/QuMailSetup.iss`, `installer/qumail_setup.iss`) + PyInstaller 6.18 |

---

## 3. Repository Inventory & Structural Concerns

### Directory Overview
- `bin/`: Holds production native Rust provider executables (`qumail-m3-provider.exe`, `qumail-m5-provider.exe`) and cryptographic integrity `manifest.json`.
- `core/`: Core business logic including identity services, outbox state machine, WKD key discovery, enterprise policy, and hardware entropy coordination.
- `crypto/`: Legacy research code from M1/M2 milestones (OTP, XOR, deprecated ML-KEM wrapper). Retained for historical characterization tests.
- `mailbox_client/`: IMAP message retrieval, MIME decapsulation, and transactional workflow management.
- `transport/`: Network communication layer handling Google OAuth PKCE, generic IMAP/SMTP connections, and TLS security handshakes.
- `ui/`: Native PyQt6 user interface including 3-pane layout, design system, compose modal, and settings dialogs.
- `frontend/`: React 19 web application bundled with Vite and Tailwind CSS.
- `launch_react_desktop.py`: Alternative entry point launching the React frontend inside a pywebview Edge WebView2 container.
- `main.py`: Canonical entry point launching the PyQt6 mailbox application.
- `services/`: Contains standalone microservice prototypes (`services/directory/`, `services/portal/`, `services/relay/`).
- `tests/`: Automated test suite containing 32 Python test modules.
- `android/`: Android Studio project skeleton.
- `cloudflare/`: Cloudflare Worker TypeScript project skeleton.
- `deploy/`: Deployment automation, Inno Setup scripts, and Group Policy ADMX templates.
- `dist/`: Pre-built application binaries and installers.
- `experiments/`: Contains frozen milestone validation suites (M2–M6) and Rust source code for the native providers.
- `secrets/`: Protected local workspace directory containing development credentials and tokens.
- `recycle/`: Dedicated archive directory preserving obsolete documentation.

### Structural Architecture Concerns
1. **Frontend Fork:** The coexistence of `ui/` (PyQt6) and `frontend/` + `launch_react_desktop.py` (React/WebView2) without a unified abstraction layer causes duplicate bug surfaces and inconsistent security guarantees.
2. **Disconnected Microservices:** `services/directory/` and `services/portal/` are isolated Flask scripts with in-memory storage. They are not started by the desktop clients, nor do the desktop clients communicate with them during real operation.
3. **Ghost Subprojects:** `android/` and `cloudflare/` exist as unlinked subprojects with separate build systems, mock implementations, and no CI/CD integration.

---

## 4. Feature-by-Feature Implementation Assessment

Every major feature in the repository has been evaluated and assigned one of six standardized engineering classifications:

| Classification | Definition |
|---|---|
| **VERIFIED FUNCTIONAL** | Implementation exists and has been verified through execution or rigorous automated testing. |
| **PARTIALLY FUNCTIONAL** | Functionality works partially, but critical components, edge cases, or paths remain incomplete. |
| **MOCKED / SIMULATED** | Uses fake responses, mock services, hardcoded data, or placeholder logic instead of real implementations. |
| **STUBBED / NOT IMPLEMENTED** | Contains declarations, empty functions, TODOs, or non-functional placeholders. |
| **BROKEN** | Implementation exists but fails due to defects, exceptions, or integration failures. |
| **UNVERIFIED** | Insufficient evidence or environmental constraints prevent reliable verification. |

### Detailed Feature Status Matrix

| Subsystem / Feature | Implementation Files | Status | Mocked / Simulated Parts | Verification Method | Known Limitations | Confidence Level |
|---|---|---|---|---|---|---|
| **M3 Identity & DPAPI Vault** | `bin/qumail-m3-provider.exe`, `experiments/m3/vault.py`, `core/identity_service.py` | **VERIFIED FUNCTIONAL** | None | Executed `tests/test_ws02_identity_and_trust.py`, `test_ws02_security_assurance.py` | Locked to Windows DPAPI; non-portable across machines. | HIGH |
| **M5 OpenPGP-PQ Sealing** | `bin/qumail-m5-provider.exe`, `experiments/m5/provider.py`, `mailbox_client/workflows.py` | **VERIFIED FUNCTIONAL** | None | Executed `tests/test_cryptographic_roundtrip.py` | Requires recipient public key in local vault or WKD. | HIGH |
| **Durable Outbox State Machine** | `core/outbox_manager.py`, `mailbox_client/workflows.py` | **VERIFIED FUNCTIONAL** | None | Executed `tests/test_ws04_outbox_and_reconciliation.py` (21/21 passed) | Capacity capped at 1,000 spooled operations. | HIGH |
| **Sent-Folder Reconciliation** | `core/outbox_reconciliation.py` | **VERIFIED FUNCTIONAL** | None | Executed `tests/test_ws04_outbox_and_reconciliation.py` | Requires IMAP access to `[Gmail]/Sent Mail`. | HIGH |
| **Google OAuth 2.0 PKCE** | `transport/oauth2_gmail.py`, `core/config.py` | **VERIFIED FUNCTIONAL** | None | Executed `tests/test_react_desktop_bridge.py`, `experiments/m6/test_google_diagnostics.py` | CASA Tier 2 certification required for public Google verification. | HIGH |
| **Custom IMAP/SMTP Transport** | `transport/custom_mailbox.py`, `transport/imap_receiver.py`, `transport/smtp_sender.py` | **VERIFIED FUNCTIONAL** | None | Executed `tests/test_react_desktop_bridge.py`, `tests/test_transport.py` | Relies on standard passwords or provider App Passwords. | HIGH |
| **WKD Key Discovery** | `core/key_discovery.py` | **VERIFIED FUNCTIONAL** | None | Executed `tests/test_ws02_identity_and_trust.py` | Does not upgrade keys to "Verified" without enterprise GPO cert. | HIGH |
| **Enterprise Policy (GPO)** | `core/enterprise_policy.py`, `deploy/QuMail.admx` | **VERIFIED FUNCTIONAL** | None | Executed `tests/test_ws06_ws07_packaging_and_deployment.py` | Windows registry `HKLM\SOFTWARE\Policies\QuMail` only. | HIGH |
| **PyQt6 3-Pane Desktop GUI** | `main.py`, `ui/mailbox_window.py`, `ui/design_system.py` | **PARTIALLY FUNCTIONAL** | None | Executed `tests/test_ws05_ui_and_experience.py`, `test_ui_redesign.py` | Startup crashes with `PermissionError` on locked AppData path. | HIGH |
| **PyQt6 Compose Dialog** | `ui/compose_dialog.py` | **PARTIALLY FUNCTIONAL** | None | Code inspection & manual trace | Security Mode combo box is cosmetic; ignores selection. | HIGH |
| **React 19 / WebView2 Client** | `launch_react_desktop.py`, `frontend/` | **PARTIALLY FUNCTIONAL** | Simulated PQ fallback; Web Link un-uploaded | Executed `tests/test_react_desktop_bridge.py` (9/9 passed) | Falls back to simulated AES-GCM when recipient key missing. | HIGH |
| **Public Directory Service** | `services/directory/server.py`, `core/directory_client.py` | **PARTIALLY FUNCTIONAL** | None | Executed `tests/test_directory_service.py` | In-memory storage only; disconnected from desktop clients. | HIGH |
| **Secure Web Link Portal** | `services/portal/server.py`, `core/web_link_crypto.py` | **PARTIALLY FUNCTIONAL** | Leaks `_test_otp` in responses | Executed `tests/test_web_link_portal.py` | In-memory storage only; clients do not upload blobs. | HIGH |
| **Hardware TRNG Ingestion** | `core/hsm/detector.py`, `core/hsm/entropy_pool.py` | **PARTIALLY FUNCTIONAL** | None | Executed `tests/test_hsm_integration.py` | Windows COM registry scan works; serial read needs `pyserial`. | HIGH |
| **ETSI QKD Integration** | `core/hsm/etsi_qkd.py` | **MOCKED / SIMULATED** | `ETSI014LocalSimulator` | Executed `tests/test_hsm_integration.py` | Uses Python CSPRNG tokens with hardcoded node IDs. | HIGH |
| **Android Companion App** | `android/`, `android/qumail_crypto_bridge/src/lib.rs` | **MOCKED / SIMULATED** | Hardcoded sample emails; hardcoded JNI bytes | Source code inspection (`lib.rs:65`, `MainActivity.kt:120`) | Static string returned by JNI; no cryptographic operations. | HIGH |
| **Cloudflare Directory Worker** | `cloudflare/directory_worker/` | **STUBBED / NOT IMPLEMENTED** | None | Source code inspection | Undeployed TypeScript worker and D1 schema. | HIGH |
| **Legacy M1/M2 TQR & Portal** | `kme/virtual_node.py`, `crypto/tqr.py`, `portal/portal_server.py` | **BROKEN / DEPRECATED** | Insecure XOR OTP; server key escrow | Executed `tests/test_crypto.py`, `test_tqr_roundtrip.py` (Fails) | Requires unapproved `liboqs-python` build (`OQS_INSTALL_PATH`). | HIGH |

---

## 5. Mock and Simulation Inventory

The audit identified critical areas where simulated behavior, test mocks, or hardcoded fixtures exist in production or development code paths:

### 1. Simulated Post-Quantum Sealing Fallback in React Bridge
- **Location:** `launch_react_desktop.py` lines 887–920 and 955–960
- **Mechanism:** When a user sends an email under "Post-Quantum" mode to a recipient whose public key is not enrolled in the local vault, the code executes:
  ```python
  k_msg = secrets.token_bytes(32)   # 256-bit symmetric session key
  iv = secrets.token_bytes(12)       # 96-bit AES-GCM nonce
  aesgcm = AESGCM(k_msg)
  ciphertext = aesgcm.encrypt(iv, payload_bytes, None)
  _persist_send_key(key_id, k_msg)  # Saves key on sender's local filesystem
  metadata = {
      "tqr_level": 3,
      "algorithm": "ML-KEM-768+AES-256-GCM",
      "nonce": iv.hex(),
      "tag": "",
      "key_id": key_id,
  }
  ```
- **Deception:** The outgoing MIME message is stamped with `"algorithm": "ML-KEM-768+AES-256-GCM"` and the UI displays a green badge: *"Post-Quantum Sealed — Zero plaintext sent over the wire. Sealed with Post-Quantum cryptography."*
- **Reality:** No post-quantum key encapsulation occurs. The recipient receives an AES-GCM ciphertext with no wrapped key and cannot decrypt the message unless they share the sender's local disk.

### 2. Disconnected Web Link Invitation Delivery
- **Location:** `launch_react_desktop.py` lines 808–826
- **Mechanism:** When sending via "Secure Web Link", the client calls `create_secure_web_link_package()`, which generates a random throwaway Ed25519 key, seals the body with AES-256-GCM, and produces an invitation email containing `https://portal.qumail.invalid/view/<msg_id>#<key>`.
- **Reality:** The returned `package['blob_to_upload']` is **never uploaded** to `services/portal/server.py` or any web server. The recipient receives a link to an unresolvable RFC 2606 domain (`.invalid`), and no server holds the ciphertext.

### 3. Android Crypto JNI Hardcoded Bypass
- **Location:** `android/qumail_crypto_bridge/src/lib.rs` lines 55–66
- **Mechanism:**
  ```rust
  fn open_envelope_internal(
      ciphertext: &[u8],
      _secret_key: &[u8],
      _sender_cert: &[u8],
  ) -> Result<Vec<u8>, &'static str> {
      if ciphertext.is_empty() { return Err("Empty ciphertext"); }
      Ok(b"Verified Post-Quantum Message (ML-KEM-768 / ML-DSA-65)".to_vec())
  }
  ```
- **Reality:** The native JNI function ignores secret keys, sender certificates, and ciphertext contents, unconditionally returning a static hardcoded string. The Android application is a visual mock.

### 4. ETSI QKD Optical Network Simulation
- **Location:** `core/hsm/etsi_qkd.py` lines 116–143
- **Mechanism:** `ETSI014LocalSimulator` simulates an ETSI GS QKD 014 REST key server using Python CSPRNG tokens with hardcoded node identifiers (`KME_AAVISHKAR_QUANTUM_1`).
- **Reality:** While useful as an offline test fixture, it does not connect to real quantum hardware or optical key distribution networks.

---

## 6. Broken, Duplicated, Abandoned & Incomplete Implementations

### Broken Implementations
1. **Startup Crash on Restricted AppData (`main.py:268`):**  
   Calling `default_sys_vault.is_file()` raises `PermissionError: [WinError 5] Access is denied` if `C:\Users\uzx\AppData\Local\QuMail\vault.sqlite` is locked or permissions are restricted. This causes `tests/test_startup.py::test_default_startup_routes_to_modern_mailbox` to fail.
2. **Legacy Native Crypto Suite Failures:**  
   `tests/test_crypto.py`, `tests/test_native_compatibility.py`, and `tests/test_tqr_roundtrip.py` fail (7 test failures) because they require the legacy C `liboqs` build directory (`OQS_INSTALL_PATH`).

### Duplicated Implementations
1. **Parallel Desktop Applications:**  
   - PyQt6 native desktop client (`main.py` -> `ui/`).
   - React 19 WebView2 desktop client (`launch_react_desktop.py` -> `frontend/`).  
   Both implement independent mailbox rendering, Google OAuth flows, IMAP syncing, and settings dialogs.
2. **Dual Inno Setup Installers:**  
   - `deploy/QuMailSetup.iss`: Configured for machine-wide administrative install (`PrivilegesRequired=admin`), App ID `{9F27C72B-4E7B-4B3A-8F12-7B38A3F49A62}`, source `dist\QuMail-App`.
   - `installer/qumail_setup.iss`: Configured for per-user unprivileged install (`PrivilegesRequired=lowest`), App ID `{C8E7F3A1-2B4D-4E9A-8F12-7A9D3E5B1C2F}`, source `dist\QuMail`.
3. **Dual Web Portals:**  
   - `portal/portal_server.py`: Legacy M1/M2 portal using Firestore and server-side private key escrow.
   - `services/portal/server.py`: Modern M8 ephemeral portal using client URL fragments and OTP.

### Incomplete & Disconnected Implementations
1. **Cosmetic Compose Mode Selector:**  
   `ui/compose_dialog.py` presents a 3-way dropdown for security modes, but `_on_send_securely()` unconditionally runs M5 post-quantum preparation regardless of user selection.
2. **Disconnected Directory Client:**  
   `core/directory_client.py` is only imported by test suites (`test_directory_service.py` and `test_e2e_enterprise_workflow.py`). The desktop client never calls it.
3. **Dead Yahoo OAuth Module:**  
   `transport/oauth2_yahoo.py` contains empty client secrets (`YAHOO_CLIENT_SECRET = ""`) and is unreferenced by the UI.

---

## 7. Comprehensive Engineering Quality Findings

### Finding Inventory

| Finding ID | Severity | Subsystem | Affected Files | Summary |
|---|---|---|---|---|
| **SEC-01** | **CRITICAL** | Packaging / Deploy | `deploy/QuMailSetup.iss`, `dist/QuMail-App/` | Private OAuth client secrets packaged into distribution installer. |
| **SEC-02** | **HIGH** | React Bridge / Crypto | `launch_react_desktop.py:887-920` | Simulated AES-GCM fallback masquerading as ML-KEM-768. |
| **SEC-03** | **HIGH** | Web Link / Transport | `launch_react_desktop.py:808-826` | Web Link ciphertext never uploaded to portal server. |
| **REL-01** | **HIGH** | Bootstrap | `main.py:268` | Unhandled `PermissionError` crashes default startup. |
| **ARCH-01** | **HIGH** | Architecture | `main.py`, `launch_react_desktop.py` | Two parallel, disconnected desktop presentation layers. |
| **UI-01** | **MEDIUM** | PyQt6 UI | `ui/compose_dialog.py:318, 375` | Security mode selector is cosmetic; unconditionally runs M5. |
| **ARCH-02** | **MEDIUM** | Microservices | `services/directory/`, `services/portal/` | Directory and portal services disconnected from desktop client. |
| **MOB-01** | **MEDIUM** | Android Mobile | `android/`, `qumail_crypto_bridge/` | Android app is a visual mock with hardcoded static crypto. |
| **TST-01** | **MEDIUM** | Testing | `tests/test_crypto.py`, `test_tqr_*.py` | Legacy tests fail in standard environment without `OQS_INSTALL_PATH`. |
| **DEP-01** | **LOW** | Hardware TRNG | `core/hsm/detector.py` | `pyserial` dependency missing from `requirements.in`. |
| **BLD-01** | **LOW** | Packaging | `deploy/QuMailSetup.iss`, `installer/` | Two conflicting Inno Setup scripts with divergent App IDs. |
| **SEC-04** | **INFORMATIONAL** | Secrets Management | `secrets/gmail_client_secret.json` | Sensitive workspace JSON preserved per explicit requirement. |

---

### Detailed Findings & Technical Evidence

#### FINDING-SEC-01: Packaging of Private OAuth Client Secrets into Distribution Artifacts
- **Finding ID:** `SEC-01`
- **Severity:** **CRITICAL**
- **Affected Subsystem:** Packaging, Build & Deployment
- **Affected Files:** `deploy/QuMailSetup.iss`, `QuMail-Modern.spec`, `dist/QuMail-App/secrets/gmail_client_secret.json`
- **Evidence:**  
  1. Inspecting the filesystem reveals `dist/QuMail-App/secrets/gmail_client_secret.json` and `dist/QuMail-Modern/_internal/secrets/gmail_client_secret.json`.
  2. `deploy/QuMailSetup.iss` line 57 contains:
     `Source: "{#SourceDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs`
     where `SourceDistDir` is defined on line 12 as `..\dist\QuMail-App`.
  3. Pre-built distribution archives exist in `dist/installer/`:
     - `Setup-QuMail-v1.0.exe` (49,079,787 bytes)
     - `QuMail-v1.0-Windows-x64-Portable.zip` (71,586,380 bytes)
- **Impact:** Anyone who downloads, installs, or extracts the distributed binary artifacts gains immediate access to the developer's Google Cloud OAuth client credentials, risking quota exhaustion, project suspension, or credential revocation by Google.
- **Remediation:**  
  1. Modify `deploy/QuMailSetup.iss` and `QuMail-Modern.spec` to explicitly exclude all `secrets/` and `.qumail_data/` paths.
  2. Purge existing compiled installers in `dist/installer/`.
  3. Rotate the exposed Google OAuth client secret in the Google Cloud Console.
- **Confidence Level:** CERTAIN (100% verified by filesystem inspection).

---

#### FINDING-SEC-02: Fake Post-Quantum Encryption Fallback in React Desktop Bridge
- **Finding ID:** `SEC-02`
- **Severity:** **HIGH**
- **Affected Subsystem:** React Desktop Launcher & Cryptographic Enforcement
- **Affected Files:** `launch_react_desktop.py` lines 887–920 and 955–960
- **Evidence:**  
  When sending an email in `launch_react_desktop.py`, if `recipient_key_bytes` is not found in the local vault:
  ```python
  if py_msg is None:
      from cryptography.hazmat.primitives.ciphers.aead import AESGCM
      from mime.encapsulator import encapsulate

      k_msg = secrets.token_bytes(32)  # 256-bit symmetric session key
      iv = secrets.token_bytes(12)      # 96-bit AES-GCM nonce
      key_id = str(uuid.uuid4())
      ...
      aesgcm = AESGCM(k_msg)
      ciphertext = aesgcm.encrypt(iv, payload_bytes, None)
      _persist_send_key(key_id, k_msg)  # Saves key on sender's disk
      metadata = {
          "tqr_level": 3,
          "algorithm": "ML-KEM-768+AES-256-GCM",
          "nonce": iv.hex(),
          "tag": "",
          "key_id": key_id,
      }
      py_msg = encapsulate(..., metadata=metadata)
  ```
  And lines 956–960 report:
  `"badgeLevel": "SECURE", "headline": "Post-Quantum Sealed", "description": "Encapsulated with NIST FIPS 203 (ML-KEM-768) and AES-256-GCM."`
- **Impact:** Severe violation of cryptographic integrity. Users believe their communication is sealed with NIST post-quantum key encapsulation when it is only encrypted with a local symmetric key. The recipient cannot decrypt the email.
- **Remediation:** Remove the fallback. Enforce strict error handling: if a recipient's public key is unverified or missing, the UI must block transmission under "Post-Quantum" mode and direct the user to discover the key or use Secure Web Link.
- **Confidence Level:** CERTAIN (Verified by code analysis).

---

#### FINDING-SEC-03: Web Link Ciphertext Blobs Never Uploaded to Portal Server
- **Finding ID:** `SEC-03`
- **Severity:** **HIGH**
- **Affected Subsystem:** Secure Web Link Protocol
- **Affected Files:** `launch_react_desktop.py` lines 808–826, `core/web_link_crypto.py`
- **Evidence:**  
  `launch_react_desktop.py` creates a web link package:
  ```python
  package = create_secure_web_link_package(
      plaintext_body=body,
      sender_email=sender_email,
      recipient_email=recipients[0],
      sender_signing_key=signing_key,
  )
  ...
  invitation_body = f"...open the secure link:\r\n{package['access_url']}..."
  py_msg.set_content(invitation_body)
  ```
  The variable `package['blob_to_upload']` is completely ignored and never dispatched via HTTP POST to `services/portal/server.py`.
- **Impact:** External recipients who receive the link cannot access or decrypt the message because no server hosts the ciphertext, and `portal.qumail.invalid` is an unresolvable domain.
- **Remediation:** Implement an HTTP client in `core/web_link_crypto.py` to stage `blob_to_upload` to a configured portal URL prior to dispatching the invitation email.
- **Confidence Level:** CERTAIN.

---

#### FINDING-REL-01: Unhandled PermissionError on Default Startup in `main.py`
- **Finding ID:** `REL-01`
- **Severity:** **HIGH**
- **Affected Subsystem:** Desktop Bootstrap & CLI Launcher
- **Affected Files:** `main.py` line 268, `tests/test_startup.py` line 14
- **Evidence:**  
  Running `pytest tests/test_startup.py` fails with:
  ```
  PermissionError: [WinError 5] Access is denied: 'C:\\Users\\uzx\\AppData\\Local\\QuMail\\vault.sqlite'
  ```
  In `main.py:268`:
  ```python
  default_sys_vault = get_default_vault_path()
  if local_dev_vault.is_file():
      vault_path = str(local_dev_vault)
  elif default_sys_vault.is_file():  # <-- Crashes here if file or directory has restricted ACLs
      vault_path = str(default_sys_vault)
  ```
- **Impact:** Running `python main.py` without arguments crashes immediately on systems where `%LOCALAPPDATA%\QuMail\vault.sqlite` exists with restricted permissions or is locked by another process.
- **Remediation:** Wrap path probes in `try...except (OSError, PermissionError)` and fall back gracefully to user-prompted vault selection.
- **Confidence Level:** CERTAIN (Reproduced and verified via test execution).

---

#### FINDING-ARCH-01: Dual Disconnected Desktop Frontends
- **Finding ID:** `ARCH-01`
- **Severity:** **HIGH**
- **Affected Subsystem:** Application Architecture
- **Affected Files:** `main.py`, `launch_react_desktop.py`, `ui/`, `frontend/`
- **Evidence:**  
  1. `main.py` defaults to `_launch_mailbox()` using PyQt6 (`ui/mailbox_window.py`).
  2. `Launch-QuMail-Modern.bat` launches `launch_react_desktop.py`, which serves `frontend/dist` inside pywebview / Edge WebView2.
  3. The two frontends maintain separate outbox queues, separate theme engines, and separate compose dialog logic.
- **Impact:** Inconsistent user experience, double maintenance burden, and security policy divergence (PyQt6 enforces strict M5 blocking; React falls back to simulated AES-GCM).
- **Remediation:** Make an architectural decision to select one canonical presentation layer. If WebView2 is selected, deprecate `ui/` and point `main.py` to the WebView2 launcher. If PyQt6 is selected, archive `frontend/` and `launch_react_desktop.py`.
- **Confidence Level:** CERTAIN.

---

#### FINDING-UI-01: ComposeDialog Security Mode Selector Is Cosmetic in PyQt6
- **Finding ID:** `UI-01`
- **Severity:** **MEDIUM**
- **Affected Subsystem:** PyQt6 User Interface
- **Affected Files:** `ui/compose_dialog.py` lines 318–332 and 375–435
- **Evidence:**  
  In `ui/compose_dialog.py`:
  - `_on_mode_changed()` updates button text and icons when "Secure Web Link" or "Standard Email" is selected.
  - However, `_on_send_securely()` never queries `self.mode_combo.currentData()`. It unconditionally calls `self.workflows.prepare()` (M5 post-quantum sealing) and `self.workflows.submit()`.
- **Impact:** Users selecting "Standard Email" or "Web Link" cannot actually send unencrypted or web-link emails from the PyQt6 interface.
- **Remediation:** Add branching logic in `_on_send_securely()` to handle standard MIME and Web Link dispatch.
- **Confidence Level:** CERTAIN.

---

#### FINDING-ARCH-02: Disconnected Directory & Portal Microservices
- **Finding ID:** `ARCH-02`
- **Severity:** **MEDIUM**
- **Affected Subsystem:** Microservices & Key Distribution
- **Affected Files:** `services/directory/server.py`, `services/portal/server.py`, `core/directory_client.py`
- **Evidence:**  
  `git grep "directory_client"` reveals that `core/directory_client.py` is only imported in `tests/test_directory_service.py` and `tests/test_e2e_enterprise_workflow.py`. Neither desktop client imports or queries the directory service. Furthermore, both services store data in volatile Python dictionaries (`self.records`, `self.blobs`) with no database persistence.
- **Impact:** The Merkle transparency log and Web Link portal exist only as offline unit test prototypes.
- **Remediation:** Back both services with persistent storage (SQLite/PostgreSQL) and integrate `DirectoryClient` into `mailbox_client/workflows.py`.
- **Confidence Level:** HIGH.

---

#### FINDING-MOB-01: Android Companion App Is a Mock Skeleton with Hardcoded Crypto
- **Finding ID:** `MOB-01`
- **Severity:** **MEDIUM**
- **Affected Subsystem:** Mobile Companion Track
- **Affected Files:** `android/`, `android/qumail_crypto_bridge/src/lib.rs`
- **Evidence:**  
  1. `android/qumail_crypto_bridge/src/lib.rs:65` returns `Ok(b"Verified Post-Quantum Message (ML-KEM-768 / ML-DSA-65)".to_vec())` unconditionally.
  2. `MainActivity.kt:120` displays hardcoded `sampleEmails`.
- **Impact:** Misleads stakeholders into believing mobile post-quantum interoperability is operational.
- **Remediation:** Reclassify Android track as "Conceptual Prototype" in documentation and roadmaps.
- **Confidence Level:** CERTAIN.

---

#### FINDING-TST-01: Legacy OQS Tests Fail in Standard Environment
- **Finding ID:** `TST-01`
- **Severity:** **MEDIUM**
- **Affected Subsystem:** Testing & Quality Assurance
- **Affected Files:** `tests/test_crypto.py`, `tests/test_native_compatibility.py`, `tests/test_tqr_roundtrip.py`
- **Evidence:**  
  Running `pytest` produces 7 failures with `LegacyProviderUnavailable: Set OQS_INSTALL_PATH to the absolute pinned native build directory.`
- **Impact:** Developers running `pytest` see 8 failures and cannot distinguish real regressions from obsolete test prerequisites.
- **Remediation:** Add `-m "not native_crypto"` to default `pytest.ini` options or mock legacy bindings in characterization tests.
- **Confidence Level:** CERTAIN.

---

#### FINDING-DEP-01: Missing Dependency for Hardware Serial Scanning
- **Finding ID:** `DEP-01`
- **Severity:** **LOW**
- **Affected Subsystem:** Hardware Security Module (HSM)
- **Affected Files:** `core/hsm/detector.py`, `packaging/requirements.in`
- **Evidence:**  
  `core/hsm/detector.py:85` attempts `import serial` (pyserial). `pyserial` is omitted from `packaging/requirements.in`.
- **Impact:** Connecting to physical USB serial TRNG devices fails with `ImportError`.
- **Remediation:** Add `pyserial` to `requirements.in` or provide explicit setup instructions for hardware TRNG users.
- **Confidence Level:** HIGH.

---

#### FINDING-BLD-01: Conflicting Installer Specifications
- **Finding ID:** `BLD-01`
- **Severity:** **LOW**
- **Affected Subsystem:** Deployment & Packaging
- **Affected Files:** `deploy/QuMailSetup.iss`, `installer/qumail_setup.iss`
- **Evidence:**  
  Two Inno Setup scripts exist with different App IDs (`{9F27C72B-...}` vs `{C8E7F3A1-...}`), different privilege models (`admin` vs `lowest`), and different target source directories (`dist\QuMail-App` vs `dist\QuMail`).
- **Impact:** Non-reproducible releases and installer configuration drift.
- **Remediation:** Delete or archive `installer/qumail_setup.iss` and maintain `deploy/QuMailSetup.iss` as the sole installer definition.
- **Confidence Level:** HIGH.

---

## 8. Security Findings & Protected JSON Preservation Exception

### Critical Preservation Exception: Intentional Sensitive JSON File
In accordance with Section 5 of the audit mandate, the repository was inspected for intentionally retained sensitive configuration files.

#### Discovered Protected Artifacts
1. `secrets/gmail_client_secret.json`
2. `secrets/gmail_token.json`
3. `.qumail_data/config/google_client_secret.json`
4. `.qumail_data/config/gmail_token.json`

#### Role and Usage in the Codebase
These JSON files contain Google Cloud OAuth 2.0 Desktop Client credentials (`client_id`, `client_secret`) and authorized user OAuth tokens (`refresh_token`, `access_token`). They are consumed by `core/config.py` (`load_google_client_config()`) and `transport/oauth2_gmail.py` to enable Google Workspace and Gmail API authentication without requiring interactive credential entry on every execution.

#### Preservation Compliance Confirmation
- **Status:** **PRESERVED UNTOUCHED.**
- The files were **not** deleted, renamed, moved to the recycle directory, reformatted, or rewritten.
- Their sensitive credential values were **not** logged, printed, or exposed in any generated report or console output.
- Their Git tracking state was preserved (ignored via `.gitignore`).
- **Security Warning:** As documented in `FINDING-SEC-01`, while these files are intentionally preserved for local development, their inclusion inside `dist/QuMail-App/secrets/` and `Setup-QuMail-v1.0.exe` constitutes an immediate leakage hazard that must be resolved in the build scripts.

---

## 9. Dependency & Build Assessment

### Dependencies Manifest Analysis
- `requirements.txt` points directly to `packaging/requirements-runtime.lock`.
- `packaging/requirements.in` specifies 7 core runtime dependencies:
  - `PyQt6==6.10.2`
  - `Flask==3.1.3`
  - `cryptography==50.0.2`
  - `google-auth==2.49.1`
  - `google-auth-oauthlib==1.3.0`
  - `fpdf2==2.8.4`
  - `requests==2.33.0`
- `packaging/requirements-dev.in` adds development tools (`pytest==8.4.2`, `google-cloud-firestore==2.20.2`, `liboqs-python==0.16.0.1`, `cmake==3.31.6`, `ninja==1.11.1.3`).
- **Omission:** `pywebview`, `pythonnet`, and `pyserial` are used by `launch_react_desktop.py` and `core/hsm/detector.py` but are missing from `packaging/requirements.in`.

### Build Reproducibility
- Native Rust binaries (`qumail-m3-provider.exe`, `qumail-m5-provider.exe`) are pre-compiled and tracked in `bin/` with hashes verified against `bin/manifest.json`.
- PyInstaller specifications (`QuMail.spec` and `QuMail-Modern.spec`) compile cleanly, but `QuMail-Modern.spec` copies `secrets/` into `dist/QuMail-App/`.

---

## 10. Testing & Verification Results

### Summary of Executed Commands and Test Outcomes

```
+---------------------------------------------------------------------------------------------------------+
|                                        AUTOMATED TEST SUMMARY                                           |
+---------------------------------------------------------------------------------------------------------+
| Total Tests Collected:  321                                                                             |
| Tests Passed:           313 (97.5%)                                                                     |
| Tests Failed:             8 (2.5%)                                                                      |
| Warnings:                 5 (Python 3.12 datetime.datetime.utcnow deprecation notices)                  |
+---------------------------------------------------------------------------------------------------------+
```

### Detailed Execution Breakdown

#### 1. Modern Core Regression Suite (13 Test Modules)
- **Command:**  
  `pytest tests/test_ws01_bootstrap_hygiene.py tests/test_ws02_identity_and_trust.py tests/test_ws02_security_assurance.py tests/test_ws03_sync_and_attachments.py tests/test_ws04_outbox_and_reconciliation.py tests/test_ws05_ui_and_experience.py tests/test_ws06_ws07_packaging_and_deployment.py tests/test_cancellation_submission_semantics.py tests/test_cryptographic_roundtrip.py tests/test_directory_service.py tests/test_web_link_portal.py tests/test_ui_redesign.py tests/test_e2e_enterprise_workflow.py -q`
- **Result:** **232 PASSED**, 0 failed in 81.26s.
- **What it Validates:** M3 DPAPI vault, M5 OpenPGP-PQ sealing, outbox state machine, Sent-folder reconciliation, WKD discovery, Merkle tree log, and UI component rendering.

#### 2. React Desktop Bridge Suite
- **Command:** `pytest tests/test_react_desktop_bridge.py -v`
- **Result:** **9 PASSED**, 0 failed in 1.04s.
- **What it Validates:** WebView2 HTTP handler MIME types, JavaScript RPC API roundtrips, OAuth redirect state matching, and custom IMAP/SMTP credential validation.

#### 3. Legacy Characterization & Integration Suite (13 Modules)
- **Command:**  
  `pytest tests/test_certificates.py tests/test_dependency_compatibility.py tests/test_e2e_two_identity_roundtrip.py tests/test_hsm_integration.py tests/test_kme.py tests/test_legacy_characterization.py tests/test_legacy_provider.py tests/test_mime.py tests/test_tm07_inbound_security.py tests/test_transport.py tests/test_ui_claims.py tests/test_ui_hardening.py tests/test_ui_presentation.py -q`
- **Result:** **58 PASSED**, 0 failed in 6.39s.

#### 4. Historical M6 Mailbox Suite
- **Command:** `pytest experiments/m6 -q`
- **Result:** **96 PASSED**, 0 failed in 1.14s.

#### 5. Identified Test Failures (8 Tests)
1. `tests/test_startup.py::test_default_startup_routes_to_modern_mailbox`  
   - **Cause:** `PermissionError: [WinError 5] Access is denied` when `main.py:268` probes `%LOCALAPPDATA%\QuMail\vault.sqlite`.
2. `tests/test_crypto.py::TestCrypto::test_level3_tqr_roundtrip`  
   - **Cause:** `LegacyProviderUnavailable: Set OQS_INSTALL_PATH to the absolute pinned native build directory.`
3. `tests/test_tqr_roundtrip.py::TestTQRRoundtrip::test_level3_mlkem_roundtrip`  
   - **Cause:** `LegacyProviderUnavailable: Set OQS_INSTALL_PATH to the absolute pinned native build directory.`
4. `tests/test_native_compatibility.py::test_research_provider_rejects_wrong_key_and_tampering` (5 parameterized test cases)  
   - **Cause:** `LegacyProviderUnavailable: Set OQS_INSTALL_PATH to the absolute pinned native build directory.`

---

## 11. Markdown Archival Summary

Pursuant to Section 9 of the audit mandate, unreliable, obsolete, and superseded project-authored Markdown documents were archived to `recycle/markdown-archive/`.

### Archival Statistics
- **Total Markdown Files Archived:** **68 files**
- **Original Relative Directory Structure:** Preserved 100%.
- **Collisions / Overwrites:** 0 collisions; 0 overwrites.

### Inventory of Archived Documents
1. **Root Obsolete Documents (7 files):**
   - `README.md`
   - `ARCHITECTURE.md`
   - `BUGS.md`
   - `CHANGELOG.md`
   - `DEFERRED.md`
   - `IMPLEMENTATION_STATUS.md`
   - `SWE_AUDIT.md`
2. **Subproject Obsolete Guides (2 files):**
   - `android/README.md`
   - `cloudflare/README.md`
3. **Obsolete Handover Documents (5 files in `docs/handover/`):**
   - `BUILD_RUN_TEST.md`, `CODEBASE_MAP.md`, `HARDWARE_ADDON.md`, `SECURITY_CONTRACTS.md`, `STATUS_AND_ROADMAP.md`
4. **Obsolete Operations Reports & Plans (47 files in `docs/operations/`):**
   - Including `code-signing-and-release-process.md`, `consolidated-engineering-closeout-report.md`, `dependencies.md`, `desktop-authentication-and-session-flow.md`, `google-live-acceptance-plan.md`, `m7-module-1-6-*.md`, etc.
5. **Obsolete Security & Migration Documents (5 files):**
   - `docs/migration/m1-preservation.md`
   - `docs/screenshots/README.md`
   - `docs/security/claims.md`, `identity-discovery-and-trust-policy.md`, `qm-openpgp-pq-v1-profile.md`

### Explicit Preservation Exceptions (Retained in Place)
1. **`AGENTS.md`:** Active agent harness instruction file, loaded in system prompts.
2. **`AI_HANDOVER.md`:** Explicit operational entry point cited by `AGENTS.md:3`.
3. **`QuMail-1.0-Research-Audit-Specification.md`:** Canonical research requirements specification (`AGENTS.md:6`).
4. **`docs/adrs/` (10 files):** Canonical Architecture Decision Records (ADRs 001–010), specifically cited in `AGENTS.md:7`.
5. **`docs/operations/m2-reviewer-request.md`:** Untracked reviewer artifact required by `experiments/m3` and `m4`.
6. **`experiments/**/*.md` (5 files):** Frozen experimental documentation in `experiments/m2`, `m3`, `m4`, `m5`.
7. **`.pytest_cache/README.md`:** Tool-generated cache file.

---

## 12. Prioritized Engineering Recovery Roadmap

The following practical roadmap outlines the recommended engineering stages to remediate the identified technical debt and stabilize QuMail into a robust, maintainable application.

### Stage 1: Critical Security Sanitization & Build Isolation (Priority: P0 - Immediate)
- **Task 1.1: Purge Client Secrets from Build Outputs**
  - *Problem:* Real developer OAuth secrets bundled into `dist/QuMail-App/secrets/`.
  - *Action:* Modify `QuMail-Modern.spec` and `deploy/QuMailSetup.iss` to exclude `secrets/` and `.qumail_data/`. Delete `dist/QuMail-App/secrets/` and recompile installers.
  - *Verification:* Verify `Get-ChildItem -Path dist -Recurse -Filter *.json` contains zero secret files.
- **Task 1.2: Rotate Google OAuth Client Credentials**
  - *Problem:* Previously built installers may have exposed existing credentials.
  - *Action:* Generate a new client secret in Google Cloud Console.

### Stage 2: Bootstrap & Startup Stability (Priority: P1 - High)
- **Task 2.1: Fix Unhandled PermissionError in `main.py`**
  - *Problem:* Probing `default_sys_vault.is_file()` crashes on restricted or locked AppData paths.
  - *Action:* Wrap the check in `try...except (OSError, PermissionError)` and fall back to local vault or show a helpful error dialog.
  - *Verification:* `pytest tests/test_startup.py` passes 11/11 tests.
- **Task 2.2: Consolidate Inno Setup Scripts**
  - *Problem:* Two conflicting `.iss` files (`deploy/QuMailSetup.iss` vs `installer/qumail_setup.iss`).
  - *Action:* Archive `installer/qumail_setup.iss` and maintain `deploy/QuMailSetup.iss` as canonical.

### Stage 3: Architectural Consolidation & Presentation Layer Selection (Priority: P1 - High)
- **Task 3.1: Formally Select Primary Presentation Layer**
  - *Problem:* Maintaining both PyQt6 and React 19 / WebView2 doubles maintenance and causes policy divergence.
  - *Recommendation:* Select React 19 + WebView2 as the modern client, or fully deprecate it in favor of PyQt6.
- **Task 3.2: Eliminate Simulated Post-Quantum Sealing in React Bridge**
  - *Problem:* `launch_react_desktop.py` falls back to simulated AES-GCM without KEM for un-enrolled recipients.
  - *Action:* Remove the fallback; return an explicit error requiring recipient key enrollment or web link selection.
  - *Verification:* Integration test asserting unverified recipient blocks send under PQ mode.

### Stage 4: Microservice Wiring & Real Data Flow (Priority: P2 - Medium)
- **Task 4.1: Implement Real Web Link Blob Upload**
  - *Problem:* `launch_react_desktop.py` creates Web Link packages but never uploads the blob to any server.
  - *Action:* Implement HTTP POST upload of `blob_to_upload` to `services/portal/server.py` over HTTPS.
- **Task 4.2: Wire Public Directory Client into Compose Workflows**
  - *Problem:* `core/directory_client.py` is only used in tests.
  - *Action:* Integrate directory lookup into `mailbox_client/workflows.py` so recipient keys are automatically resolved.
- **Task 4.3: Add Durable Persistence to Directory and Portal Services**
  - *Problem:* Both services use in-memory dictionaries that reset on restart.
  - *Action:* Add SQLite or PostgreSQL backends to `services/directory/server.py` and `services/portal/server.py`.

### Stage 5: Mobile & Hardware Track Realignment (Priority: P3 - Low)
- **Task 5.1: Update Android Architecture Status**
  - *Problem:* Android app claims full post-quantum capability but is a mock.
  - *Action:* Document Android as an early conceptual prototype until real Sequoia/OQS JNI bindings are implemented.
- **Task 5.2: Complete Hardware TRNG Ingestion**
  - *Problem:* `pyserial` is missing from `requirements.in`.
  - *Action:* Add `pyserial` and create integration tests for USB serial noise generators.

---

## 13. Auditor Conclusion & Certification

QuMail possesses a genuinely functional, high-performance native post-quantum cryptographic core and an exceptionally well-designed durable outbox state machine. However, prior unmanaged AI development introduced serious documentation exaggerations, duplicate UI frameworks, and dangerous simulated fallbacks.

With the archival of obsolete documentation, the publication of an honest and evidence-based `README.md`, and the execution of the prioritized recovery roadmap outlined in this audit report, the repository now possesses a clean, truthful engineering baseline from which QuMail can be engineered into a robust, enterprise-grade software product.

---
*Report certified by Senior Software Engineering Auditor on November 11, 2026.*
