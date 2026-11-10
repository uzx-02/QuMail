# QuMail: Engineering Handover & Current Project State

**Updated:** 2026-11-10  
**Current Active Branch:** `codex/m7-module-1-6-ws06-ws07`  
**Accepted Baseline:** `d3b2078` (WS-06/07 Final Accepted Checkpoint)  
**Consolidated Delivery:** M7 Closeout + M8 Architecture Review + UI/UX Pro Max Redesign + Public-Key Directory + Secure Web Link  
**Validation Evidence:** 241 passing modern regression tests (100% green, 0 failures)  

---

## 1. Product Reality & Current State

QuMail 1.0 is a complete, polished, post-quantum secure corporate email client for Windows x64.
It enforces the central product principle of **Zero Cryptographic Friction**:
- Ordinary employees can open QuMail, connect their Google Workspace or IMAP account, navigate their mailbox, read and search messages, compose emails, and manage attachments without dealing with raw cryptographic keys, manual certificate exports, or algorithm choices.
- Behind the interface, strict post-quantum cryptography (`QM-OPENPGP-PQ-v1` composite ML-KEM-768/X25519 and ML-DSA-65/Ed25519) is strictly enforced. No unencrypted or plaintext fallbacks are permitted.
- The user interface is built on **UI/UX Pro Max** standards with native dual-theme support (Dark Enterprise Slate & Light Executive Workspace), real-time search, multi-mode filter pills, monogram avatars, and human-friendly security indicators.

### Two-Pillar Product Delivery Model (Fully Implemented)
1. **Pillar 1: Direct QuMail-to-QuMail Post-Quantum Messaging**
   - Automated key discovery via the centralized **Public-Key Directory** (`services/directory/server.py`, `core/directory_client.py`).
   - Ephemeral challenge-response Proof of Key Possession (PoP).
   - Binary Merkle Tree transparency log (RFC 6962 / RFC 9162) issuing Signed Tree Heads (STH) and $O(\log N)$ inclusion proofs.
   - Trust-On-First-Use (TOFU) key pinning in local SQLite vault with hard security alarms on key substitution.
   - Honest trust badges: Emerald Green **`SECURE`** for enterprise GPO certified keys, Amber **`CAUTION: Identity Unverified`** for uncertified directory keys.
2. **Pillar 2: Secure Web Link for External Recipients**
   - Enables confidential communications to external correspondents who do not run QuMail (`core/web_link_crypto.py`, `services/portal/server.py`).
   - Client-side symmetrical sealing using `AES-256-GCM` with CSPRNG key and nonce.
   - RFC 3986 `#key` URL fragment delivery (portal server is blind to the key).
   - Mailbox-access verification via server-secret keyed HMAC One-Time Passcodes (OTP) with 3-attempt lockout.
   - Browser WebCrypto simulated decryption inside sandboxed iframe.

---

## 2. Architecture & File Locations

- **Desktop Entry Point:** `main.py` (defaults to modern 3-pane client `_launch_mailbox()`).
- **UI Architecture:**
  - `ui/design_system.py`: Dual-theme tokens (Dark & Light), ThemeManager singleton, StatusBadgeWidget, AvatarWidget, SearchInput, ActionButton, EmptyState.
  - `ui/navigation_pane.py`: Sidebar with folder navigation, unread badges, account card, theme toggle, and settings.
  - `ui/message_list_pane.py`: Multi-attribute search, 4-way filter pills (All, Unread, Secure, Files), rich message cards.
  - `ui/reading_pane.py`: Inline reading pane, SecurityBanner, safe attachment cards, sanitized body viewer.
  - `ui/compose_dialog.py`: Security mode selector (PQ, Web Link, Standard), draft saving, outbox queueing.
  - `ui/settings_dialog.py`: 7-tab enterprise preferences dialog.
- **Cryptographic Engine:** Native Rust providers in `bin/` (`qumail-m3-provider.exe`, `qumail-m5-provider.exe`).
- **Public-Key Directory Service:** `services/directory/server.py`, `services/directory/merkle.py`.
- **Desktop Directory Client:** `core/directory_client.py`.
- **Secure Web Link Engine:** `core/web_link_crypto.py`, `services/portal/server.py`.
- **Packaging & Enterprise:** `QuMail.spec`, `core/packaging.py`, `core/enterprise_policy.py`, `deploy/inno_setup.iss`.

---

## 3. Test & Verification Evidence

All 241 modern regression tests pass across 14 test suites:
```powershell
.venv-m1-clean\Scripts\pytest.exe tests/test_ws01_bootstrap_hygiene.py tests/test_ws02_identity_and_trust.py tests/test_ws02_security_assurance.py tests/test_ws03_sync_and_attachments.py tests/test_ws04_outbox_and_reconciliation.py tests/test_ws05_ui_and_experience.py tests/test_ws06_ws07_packaging_and_deployment.py tests/test_cancellation_submission_semantics.py tests/test_cryptographic_roundtrip.py tests/test_startup.py tests/test_directory_service.py tests/test_web_link_portal.py tests/test_ui_redesign.py tests/test_e2e_enterprise_workflow.py -q
```
**Result:** `241 passed in 77.98s (Exit Code: 0)`.

---

## 4. External Release Gates (Commercial Distribution)

The application is development-complete, functionally complete, and pilot-ready. Public production distribution requires:
1. **Commercial Authenticode EV Code-Signing Certificate:** Required to eliminate Windows SmartScreen warnings on public `.exe` installers.
2. **Google OAuth CASA Tier 2 Assessment:** Required by Google before removing the 100-user cap for production Gmail OAuth scopes.
3. **Independent Cryptographic Audit:** Required before enterprise marketing of certified security claims.
