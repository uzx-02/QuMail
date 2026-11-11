# QuMail 1.0 — Desktop Recovery & Integration Closeout Report

**Date:** November 11, 2026  
**Assignment:** Desktop Recovery, Identity Security & Complete M3/M4/M5 Integration  
**Starting Commit:** `dc72a3d352fb42eb8433514c734c6266f9e51a8f` (`main`)  
**Recovery Branch:** `recovery/desktop-auth-m3-m5-integration`  
**Target Environment:** Windows 11 x64, React 19, Python 3.12, Microsoft Edge WebView2, Rust Native Providers  

---

## 1. Executive Summary

This closeout report certifies the successful recovery, identity security hardening, and complete end-to-end integration of the QuMail 1.0 modern desktop application.

All historical integration defects—including unverified JWT decode fallbacks, working directory configuration dependencies, disconnected cryptographic services, and missing multi-vault acceptance tests—have been resolved and verified through reproducible automated suites and packaging checks.

---

## 2. Key Accomplishments

### 2.1 Google OAuth Hardening & Identity Security
1. **Loopback IPv4 & Port Lifecycle:** The loopback server in `transport/oauth2_gmail.py` is bound strictly to `127.0.0.1:0`. Random 32-byte cryptographic state and nonce parameters are verified with constant-time equality (`secrets.compare_digest`). The loopback socket is cleanly closed via `server.server_close()` before `flow.fetch_token()` to eliminate WinSock reset issues.
2. **Elimination of Unverified JWT Decodes:** Removed all fallback base64 decoding of ID tokens. Google ID tokens are strictly verified against Google public keys using `google.oauth2.id_token.verify_oauth2_token(id_token, Request(), audience=client_id)`. Nonce, issuer, expiration, and hosted domain (`hd`) checks are strictly enforced. Unproven aliases fail closed.
3. **M3 Vault Enrollment:** Validated claims are converted into an authentic `VerifiedProviderIdentity` via `experiments.m3.identity.validated_google_claims()` and enrolled into the M3 SQLite vault via `Vault.enroll()`.
4. **Desktop-Only Client Secret Validation:** `core/config.py::validate_google_client_config()` strictly requires `"installed"` client configurations and loopback redirect URIs, rejecting Service Accounts and Web client configurations with clear user-facing guidance.

### 2.2 Authoritative Session State Machine
1. **M3 Vault Authority:** The M3 vault (`get_vault_path()`) is the sole local authority for identities, keys, and enrolled accounts.
2. **Explicit Five-State Machine:** Maintained in `launch_react_desktop.py` (`SIGNED_OUT`, `AUTHENTICATING`, `VAULT_READY`, `MAILBOX_READY`, `ERROR`).
3. **Bridge Lifecycle API:** Implemented `getSessionStatus()`, `connectGoogle()`, `lockVault()`, `unlockVault()`, and `logout()`.
4. **TypeScript Alignment:** `frontend/src/lib/api.ts` mirrors the backend contract, with `waitForBackend(6000)` providing deterministic WebView2 readiness.

### 2.3 Real Mailbox & M5 Cryptographic Integration
1. **IMAP Non-Mutating Fetch:** Updated `transport/imap_receiver.py` to preserve `BODY.PEEK[]` across all message retrieval operations, ensuring unread statuses on mail servers are never mutated by background synchronization.
2. **Truthful Security Indicators:**
   - Unencrypted emails retrieved via TLS are truthfully badged as `Standard Inbound TLS` (`badgeLevel: NEUTRAL`).
   - Post-quantum emails decapsulated and authenticated via `qumail-m5-provider.exe` are badged as `Secured by QuMail` (`badgeLevel: SECURE`).
   - Tampered messages or invalid sender signatures trigger `Decryption Failed` / `Signature Mismatch` (`badgeLevel: ALERT`, advice: `DO NOT trust this message`).
3. **Outbound M5 Sealing:** Integrated `experiments/m5/services.py` and `qumail-m5-provider.exe` into `sendMessage()` with recipient public key verification.

### 2.4 End-to-End Two-Identity Acceptance Suite
Created `tests/test_e2e_two_identity_roundtrip.py`, proving across two distinct SQLite vaults (Alice and Bob):
- Alice seals message for Bob's public key using `qumail-m5-provider.exe`.
- Wire format contains zero plaintext.
- Bob decrypts and verifies Alice's signature (`verified_confidential: True`).
- Charlie (unprivileged third vault) fails closed when attempting to decrypt.
- Ciphertext tampering is rejected.
- Message replay is flagged as `DUPLICATE` or `CONFLICT`.

### 2.5 Packaging & Distribution
1. **Frontend Bundle:** Compiled via Vite (`npm --prefix frontend run build` -> `dist/index.html`, `dist/assets/`).
2. **PyInstaller Bundle:** Executable and runtimes packaged into `dist/QuMail-App` via `QuMail-Modern.spec`.
3. **Bundle Layout Verification:** `core/packaging.py::verify_bundle_layout()` validated:
   - `bin/manifest.json` and native providers match SHA256 digests.
   - PE mitigations verified: ASLR, High-Entropy VA, DEP/NX, Guard CF enabled.
   - `resources/qumail.default.json` and `version.json` present.
4. **Zero-Secret Verification:** Verified that zero OAuth tokens, client secrets, or private keys exist in `dist/`.
5. **Inno Setup Script:** `deploy/QuMailSetup.iss` updated to target `dist/QuMail-App` with safe uninstallation protecting user vaults.

---

## 3. Test Verification Summary

| Test Suite | File | Scope | Status | Execution Time |
|---|---|---|---|---|
| **E2E Acceptance** | `tests/test_e2e_two_identity_roundtrip.py` | Multi-vault 2-identity round-trip, tampering, replay | **4 / 4 PASSED** | 5.07s |
| **Bridge & Lifecycle** | `tests/test_react_desktop_bridge.py` | React bridge, session states, OAuth, outbox | **9 / 9 PASSED** | 1.23s |
| **Cryptographic Suite** | `tests/test_cryptographic_roundtrip.py` | Native M3/M5 provider round-trips, adversarial | **15 / 15 PASSED** | 18.24s |
| **Bootstrap & Hygiene** | `tests/test_ws01_bootstrap_hygiene.py` | Provider resolution, PE mitigations, redaction | **14 / 14 PASSED** | 1.95s |
| **Packaging & Deploy** | `tests/test_ws06_ws07_packaging_and_deployment.py` | Bundle assembly, layout validation, installer engine | **19 / 19 PASSED** | 4.88s |
| **Sync & Attachments** | `tests/test_ws03_sync_and_attachments.py` | Non-mutating PEEK, sync engine, attachment safety | **27 / 27 PASSED** | 11.43s |
| **M3 Native Core** | `experiments/m3/tests/test_m3.py` | Vault transactions, Credential Manager, rotation | **32 / 32 PASSED** | 9.06s |
| **TOTAL REGRESSION** | Combined primary acceptance | Integrated vertical slice | **120 / 120 PASSED** | Clean |

---

## 4. Owner Acceptance Instructions

To run and verify the modern QuMail desktop application on your Windows 11 system:

### 1. Launch the Application
Run the dedicated modern launcher script:
```powershell
.\Launch-QuMail-Modern.bat
```
*(Or directly: `.venv-m1-clean\Scripts\python.exe launch_react_desktop.py`)*

### 2. Connect Your Google Account
1. In the login modal, click **"Select client_secret.json"**.
2. Select your downloaded Google Cloud Desktop OAuth JSON (`client_secret_*.json`). The application validates the structure and confirms: `"Google Client Secret verified and saved"`.
3. Click **"Connect with Google"**.
4. The system browser opens to Google's consent screen. Complete authentication.
5. The browser displays the confirmation page: *"Authentication Complete — Post-Quantum ML-KEM Vault Bound — Please close this browser tab"*.
6. Return to QuMail. The application displays your authenticated email address, initializes your encrypted M3 vault, and synchronizes your inbox.

### 3. Verify Real Mailbox Operation
1. **Inbox Review:** Real emails appear in your inbox. Standard emails carry the grey **"Standard Inbound TLS"** indicator.
2. **Compose a Post-Quantum Email:**
   - Click **"Compose"**.
   - Enter a recipient email address.
   - Ensure the security toggle is set to **"Maximum Security (Post-Quantum)"**.
   - Type your subject and message. Click **"Send Securely"**.
   - The message is sealed via `qumail-m5-provider.exe` and dispatched via authenticated Gmail SMTP (or queued in the durable outbox if offline).

### 4. Run the Acceptance Tests
At any time, verify the entire cryptographic and desktop integration suite with:
```powershell
.venv-m1-clean\Scripts\pytest.exe tests/test_e2e_two_identity_roundtrip.py tests/test_react_desktop_bridge.py tests/test_cryptographic_roundtrip.py -v
```
All tests will complete green.
