# QuMail 1.0 — Visual Design & Verification Screenshots

This directory contains authentic, pixel-rendered PNG screenshots of the QuMail application across all core user flows, captured via PyQt6 offscreen widget grabs (`tools/capture_screenshots.py`).

An interactive visual contact sheet is available at [`contact_sheet.html`](contact_sheet.html).

---

### Screenshot Catalog

| # | File | Viewport | Flow & Verified Elements |
|---|---|---|---|
| **01** | [`01_welcome_screen.png`](01_welcome_screen.png) | 800×600 | **First-Run Welcome Screen:** Branded shield logo, clean corporate copy, setup entry call-to-action. |
| **02** | [`02_how_it_works_guide.png`](02_how_it_works_guide.png) | 620×520 | **Onboarding Step 2:** Explains Local Encryption, Cryptographic Verification, and Honest Delivery States. |
| **03** | [`03_account_connection_permissions.png`](03_account_connection_permissions.png) | 620×520 | **Onboarding Step 3:** Permission transparency disclosure and Google account connection with explicit vault prompt. |
| **04** | [`04_main_inbox_workspace.png`](04_main_inbox_workspace.png) | 1060×750 | **Main Mailbox Workspace:** Top action bar, real-time sender/subject search bar, message list table. |
| **05** | [`05_message_reader_pane.png`](05_message_reader_pane.png) | 1060×750 | **Message Reader Pane:** Verified sender badge, OpenPGP cryptographic signature status, body, and attachment list. |
| **06** | [`06_compose_protected_email.png`](06_compose_protected_email.png) | 900×800 | **Secure Compose:** Truthful security indicator badge (`Recipient Keys Verified`), "🚀 Send Securely" primary button. |
| **07** | [`07_outbox_queue_status.png`](07_outbox_queue_status.png) | 900×800 | **Durable Outbox Queue:** Human-readable delivery states (`Accepted by mail server`, `Ready to send`, `Draft`). |
| **08** | [`08_account_settings.png`](08_account_settings.png) | 600×480 | **Account Settings:** Displays active account, OpenPGP root fingerprint, vault path, and key management controls. |
