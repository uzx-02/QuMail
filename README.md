# QuMail 1.0 — Post-Quantum Secure Corporate Email Client

QuMail 1.0 is an enterprise-grade desktop email client for Windows x64 integrating composite post-quantum cryptography directly into everyday email workflows with **Zero Cryptographic Friction**.

Ordinary employees can connect their Google Workspace or IMAP accounts, read, search, organize, and compose emails with automatic end-to-end post-quantum sealing, without dealing with raw keys, manual certificate exports, or algorithm choices.

---

## 🛡️ Core Product Architecture: Two-Pillar Delivery Model

```
                               ┌─────────────────────────────────────────────────────┐
                               │             QuMail Desktop Outbox Engine            │
                               └──────────────────────────┬──────────────────────────┘
                                                          │
                                         Is recipient a registered QuMail user?
                                         (Authenticated Public Directory Query)
                                                          │
                                ┌─────────────────────────┴─────────────────────────┐
                                │ YES                                               │ NO
                                ▼                                                   ▼
                ┌───────────────────────────────┐                   ┌───────────────────────────────┐
                │   Pillar 1: Direct PQ-Mail    │                   │   Pillar 2: Secure Web Link   │
                │   (QuMail-to-QuMail)          │                   │   (External Recipient)        │
                ├───────────────────────────────┤                   ├───────────────────────────────┤
                │ • Wire: QM-OPENPGP-PQ-v1      │                   │ • Client generates K_msg      │
                │ • ML-KEM-768 + X25519         │                   │ • Encrypts with AES-256-GCM   │
                │ • ML-DSA-65 + Ed25519         │                   │ • Uploads ciphertext to portal│
                │ • Merkle Transparency Log     │                   │ • Sends link with #K_msg in   │
                │ • TOFU local vault key pinning│                   │   URL fragment (blind server) │
                │ • Amber indicator for un-     │                   │ • Recipient verifies via OTP  │
                │   certified directory keys    │                   │ • Browser decrypts in sandbox │
                │ • Green indicator for GPO/CA  │                   │ • WebKEM reply key-wrapping   │
                │   certified enterprise keys   │                   │ • Ephemeral retention/purge   │
                └───────────────────────────────┘                   └───────────────────────────────┘
```

---

## 🎨 Complete UI/UX Pro Max Desktop Redesign

The user interface is built on **UI/UX Pro Max** standards for desktop productivity:
- **Dual-Theme Reactive Engine:** Seamless runtime switching between **Dark Enterprise Slate** (`#0A0E17`) and **Light Executive Workspace** (`#F8FAFC`). Toggle with one click via the `[☀️ / 🌙]` button.
- **Left Navigation Pane:** Shield branding, primary New Message CTA (`Ctrl+N`), folder list with dynamic unread badges, monogram avatar card, sync status, and quick settings.
- **Middle Message List Pane:** Real-time multi-attribute search, 4-mode filter pills (**All**, **Unread**, **🔒 Secure**, **📎 Files**), and rich message cards with relative timestamps ("10:45 AM", "Yesterday", "Nov 09").
- **Right Inline Reading Pane:** Direct reading view without popups, plain-language `SecurityBanner`, expandable cryptographic verification drawer, attachment shelf with execution-safe export, and sandboxed body viewer.
- **Modern Compose Dialog:** Security mode selector (Post-Quantum Encrypted, Secure Web Link, Standard Email), auto-completing recipient chips, attachment budget counter, and integrated durable Outbox inspection tab.
- **Comprehensive Settings:** 7-tab enterprise preferences dialog for Account, Sync, Post-Quantum Keys, Merkle Transparency, Enterprise Policy (GPO), Appearance, and Privacy-Safe Diagnostics.

---

## 🚀 Running QuMail

### 1. Launch Modern Desktop Client
```powershell
# Default entry point launches the modern three-pane secure desktop client:
.venv-m1-clean\Scripts\python.exe main.py

# Optional: specify explicit vault path or enable live Gmail SMTP submission:
.venv-m1-clean\Scripts\python.exe main.py --dev-mailbox --dev-vault qumail_vault.sqlite --submit
```

### 2. Verify Native Cryptographic Providers
```powershell
.venv-m1-clean\Scripts\python.exe main.py --check-provider
```

### 3. Run Comprehensive Test Suite (241 Tests)
```powershell
.venv-m1-clean\Scripts\pytest.exe `
  tests/test_ws01_bootstrap_hygiene.py `
  tests/test_ws02_identity_and_trust.py `
  tests/test_ws02_security_assurance.py `
  tests/test_ws03_sync_and_attachments.py `
  tests/test_ws04_outbox_and_reconciliation.py `
  tests/test_ws05_ui_and_experience.py `
  tests/test_ws06_ws07_packaging_and_deployment.py `
  tests/test_cancellation_submission_semantics.py `
  tests/test_cryptographic_roundtrip.py `
  tests/test_startup.py `
  tests/test_directory_service.py `
  tests/test_web_link_portal.py `
  tests/test_ui_redesign.py `
  tests/test_e2e_enterprise_workflow.py `
  -q
```

---

## 📦 Commercial Distribution & Release Gates

QuMail is development complete, functionally complete, and internally validated for enterprise pilots. Public commercial distribution requires:
1. **Commercial Authenticode EV Code-Signing Certificate:** Eliminates Windows SmartScreen warnings on installer executables.
2. **Google Cloud OAuth CASA Tier 2 Assessment:** Required before removing the 100-user cap for production Gmail OAuth scopes.
3. **Independent Third-Party Cryptographic Audit:** Required before enterprise marketing of certified security claims.
