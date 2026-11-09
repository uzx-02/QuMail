# QuMail M7 — User Interface and Security Indicator Contract

**Milestone:** M7 — Module 1.6  
**Workstream:** WS-05 — Complete User Experience & Interface Integration  
**Document:** User Interface and Security Indicator Contract  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  
**Status:** Approved & Implemented

---

## 1. Purpose and Scope

This document specifies the user experience, layout architecture, and security presentation contracts for QuMail M7 Module 1.6.

It defines the interaction patterns, component responsibilities, plain-language indicator vocabulary, and strict security invariants enforced across the desktop email client. The contract guarantees **Zero Cryptographic Friction** for non-technical corporate employees while maintaining absolute mathematical rigor and fail-safe security invariants.

---

## 2. Desktop Layout Architecture: Three-Pane Experience

QuMail implements a responsive three-pane desktop layout within `ui/mailbox_window.py` hosted inside a horizontal `QSplitter`, enforcing sensible minimum desktop dimensions ($940 \times 600\text{ px}$).

```
+-------------------+-----------------------------------+--------------------------------------------+
| Navigation Pane   | Message List Pane                 | Reading Pane                               |
| (~220 px)         | (~380 px)                         | (Remaining / Responsive)                   |
+-------------------+-----------------------------------+--------------------------------------------+
| QuMail Brand      | Search Bar [🔍 Filter messages]   | Message Subject Header                     |
| [✏️ New Mail]     | Tabs: [All] [Unread]              | Sender & Recipient Badges, Date/Time       |
| 📥 Inbox (Badge)  |-----------------------------------| [SecurityBanner: Status, Headline, Advice] |
| ⭐ Starred        | [Message Card]                    |--------------------------------------------|
| 📤 Sent Mail      | - Sender | Time                   | Safe Plain-Text Message Viewer             |
| 📝 Drafts         | - Subject Preview                 | (Preserved whitespace, no script/trackers) |
| 📦 Outbox         | - [Pill: Secure] 📎               |--------------------------------------------|
| 🗄️ Archive        |-----------------------------------| Attached Files:                            |
| 🗑️ Trash          | [Message Card]                    | [📎 financial_q3.pdf (1.2 MB) [Save] [Open] ] |
|-------------------| ...                               |                                            |
| [Account Card]    |-----------------------------------|                                            |
| [Sync Dot: Idle]  | [ Older UID Window ]              |                                            |
| [⚙️ Settings] [🔒] |                                   |                                            |
+-------------------+-----------------------------------+--------------------------------------------+
```

### 2.1 Navigation Pane (`ui/navigation_pane.py`)
- **Branding & Action:** QuMail corporate lock logo and primary `✏️ New Mail` compose button.
- **Folder Tree:** Inbox, Starred, Sent Mail, Drafts, Outbox, Archive, and Trash.
- **Dynamic Badge Counts:** Inbox badge dynamically updates in real-time based on unread counts emitted by the background sync worker or local index.
- **Account Identity Card:** Shows the currently selected account email address with tooltip.
- **Unobtrusive Synchronization Indicator:** Color-coded status dot and plain-language label:
  - `Idle` (Green dot): Client is connected and up to date.
  - `Synchronizing…` (Cyan dot): Background sync or cursor catch-up in progress.
  - `Reconnecting…` (Amber dot): Transient connection drop, reconnection attempt in progress.
  - `Offline` (Gray dot): Network unavailable or background sync stopped.
- **System Actions:** One-click access to Settings (`⚙️`) and Vault Lock (`🔒`).

### 2.2 Message List Pane (`ui/message_list_pane.py`)
- **Instant Local Search:** Real-time filter filtering sender and subject fields across locally cached headers with zero latency.
- **Filter Tabs:** Segmented toggle between `All` and `Unread` messages.
- **Message Cards:** Compact card layout rendering:
  - Sender display name or email.
  - Date/time formatted according to corporate conventions (Today $\rightarrow$ time, Current year $\rightarrow$ `MMM d`, Older $\rightarrow$ `M/d/yy`).
  - Subject line and preview snippet.
  - Unread indicator dot (cyan).
  - Attachment paperclip indicator (`📎`).
  - Compact `SecurityPill` showing message security status at a glance.
- **Non-blocking Pagination:** "Older" button at bottom requesting the next 30-message window asynchronously.

### 2.3 Reading Pane (`ui/reading_pane.py`)
- **Inline Message Viewing:** Messages render directly inside the reading pane upon list selection; no separate pop-up windows are spawned.
- **Structured Header:** Displays full Subject, authenticated Sender, Recipients (`To` / `Cc`), and Date timestamp.
- **SecurityBanner:** Prominent banner positioned above message content presenting verified cryptographic status and non-technical advice.
- **Sandboxed Plain-Text Body:** Decrypted body displayed in a comfortable, readable plain-text area. Scripts, external HTTP requests, tracking pixels, and CSS stylesheets are completely prohibited.
- **Attachment Cards:** Verified attachments displayed as structured cards with filename, formatted size, and explicit user action buttons (`Save As` and `Open`).

---

## 3. Security Indicators Contract (WS-02 Integration)

All security presentation consumes the canonical `SecurityIndicator` contract from `core/security_indicators.py`. Security presentation is partitioned into two UI components:
1. **`SecurityPill` (`ui/security_badge_widget.py`):** Compact badge embedded within message list cards and compose dialog.
2. **`SecurityBanner` (`ui/security_badge_widget.py`):** Full banner rendered above the message body in the reading pane.

### 3.1 Five Canonical Indicator Vocabulary States

| Level | Badge Text | Color Scheme | Headline | Description & Non-Technical Advice |
|---|:---:|:---:|---|---|
| **SECURE** | `SECURE` | Emerald Green (`#10B981`) | Secured by QuMail | "Verified corporate identity. End-to-end encrypted and sealed with post-quantum algorithms." |
| **CAUTION** | `CAUTION` | Amber / Warning (`#F59E0B`) | Identity Unverified | "Encrypted message, but the sender's signing certificate has not been certified by corporate directory." |
| **NEUTRAL** | `NEUTRAL` | Slate / Neutral (`#64748B`) | External Correspondent | "Standard transport from an external correspondent outside your organization." |
| **ALERT** | `ALERT` | Ruby Red (`#EF4444`) | Signature Invalid / Tampered | "DO NOT trust this message. Cryptographic verification failed or content was altered in transit." |
| **NEUTRAL** | `NEUTRAL` | Slate Gray (`#475569`) | Security Info Unavailable | "Cryptographic verification information is unavailable or could not be determined." |

### 3.2 Strict Security Invariants
1. **Verification Precedes Plaintext Release:** The reading pane is never populated with decrypted plaintext before cryptographic verification has completed.
2. **Zero Concealment of Security Failures:** If a signature fails, digest mismatches, or certificate validation fails, the UI strictly displays the `ALERT` indicator with red warning styling. The application never falls back silently to unverified display or suppresses errors.
3. **Explicit Recipient Trust:** During message composition, recipient trust is evaluated live. If a recipient key is uncertified or requires discovery, an amber `CAUTION` pill is displayed.

---

## 4. Zero-Cryptographic-Friction Compose & Send

QuMail eliminates all cryptographic friction during email drafting and sending (`ui/compose_dialog.py`).

### 4.1 Employee Workflow
1. Employee clicks `✏️ New Mail`.
2. Fills standard fields: `To`, `Cc`, `Subject`, and message body.
3. Optionally attaches files via `📎 Add Attachment`.
4. Clicks `🚀 Send Securely`.

### 4.2 Behind-the-Scenes Automation
- **Zero Cryptographic Jargon:** The user is never prompted to select algorithms (Kyber, Dilithium, Ed25519, AES-GCM), select key IDs, export armored blocks, or inspect fingerprints.
- **Automated Sealing:** The client transparently calls:
  1. `Workflows.save()` $\rightarrow$ saves draft in encrypted local SQLite vault.
  2. `Workflows.prepare()` $\rightarrow$ resolves sender's active post-quantum signing key and seals the message.
  3. `Workflows.submit()` $\rightarrow$ queues payload into the durable outbox and initiates transmission.
- **Outbox Tab Integration:** The compose dialog hosts an `Outbox & Status` tab displaying current queue items with WS-04 delivery statuses.

### 4.3 Outbox Delivery Status Contract (WS-04 Integration)

| Internal `OutboxState` | User-Facing Plain-Language Label | Tooltip / Description |
|---|---|---|
| `DRAFT` | Draft saved locally | Draft stored safely in encrypted vault. |
| `PREPARED` | Queued for secure sending | Message encrypted and sealed; waiting for submission. |
| `SUBMITTING` | Sending to mail server... | Contacting email provider transmission endpoint. |
| `ACCEPTED` | Accepted by your mail server | Server received the message for onward delivery. |
| `UNKNOWN` | Could not confirm whether this message was sent | Network interrupted during transmission; sent-folder check advised. |
| `FAILED` | Submission failed | Submission rejected by mail server or recipient invalid. |

#### Duplicate Delivery Risk Protection
- Retrying an `UNKNOWN` outbox entry requires explicit employee confirmation via a modal dialog explaining duplicate risk:
  > *"The mail server may have already received this message during the network interruption. Retrying may send a duplicate copy to the recipient. Do you wish to authorize retrying?"*
- Canceling the prompt aborts retry without mutation. Confirming authorizes a single retrial pass while preserving identical frozen ciphertext and message ID.

---

## 5. Attachment Pipeline Safety Contract

Attachment interaction in `ui/reading_pane.py` and `ui/mailbox_window.py` enforces strict file handling policies:

1. **Structured Attachment Cards:** Each attachment displays:
   - File icon and filename.
   - Human-readable file size (`KB` / `MB`).
   - `Save As` action button.
   - `Open` action button.
2. **Safe Atomic Export:** Clicking `Save As` prompts the user for a new file destination via `QFileDialog.getSaveFileName` and writes data atomically without clobbering existing files.
3. **Executable File Execution Block:**
   - Extensions `.exe`, `.bat`, `.cmd`, `.ps1`, `.vbs`, `.js`, `.scr`, `.com`, `.pif`, `.msi` are strictly blocked from direct execution.
   - Attempting to click `Open` on an executable attachment immediately displays a `Security Policy Block` critical alert explaining that direct execution of executable attachments is prohibited to protect the employee's workstation.

---

## 6. Theme and Accessibility System (`ui/design_system.py`)

QuMail provides a cohesive design token system supporting Dark and Light appearance themes:

- **Dark Theme (Default):** Deep slate palette (`#0F172A`, `#1E293B`, `#334155`) engineered for low eye strain in enterprise environments.
- **Light Theme:** High-contrast clean paper palette (`#F8FAFC`, `#FFFFFF`, `#E2E8F0`).
- **Dynamic Switching:** Settings dialog provides a live theme dropdown emitting `theme_changed` and updating all active windows without restart.
- **Accessibility:** Text contrast ratios adhere to WCAG 2.1 AA standards ($>4.5:1$ for body text, $>3:1$ for large headings and badges).
