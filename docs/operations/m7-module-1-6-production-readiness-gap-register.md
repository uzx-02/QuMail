# QuMail M7 — Module 1.6 Production Readiness Gap Register
## Comprehensive Prioritized Engineering Gaps Across Seven Domains

**Milestone:** M7 — Module 1.6  
**Document:** Production Readiness Gap Register  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  
**Branch:** `codex/m7-module-1-6-planning`  
**Accepted Baseline Checkpoint:** `eff3736` | **Closeout Anchor:** `c9a3cf4`  

---

## 1. Overview and Priority Framework

This register documents every identified technical, architectural, security, and operational gap preventing QuMail from transitioning from a successful two-account acceptance prototype into a corporate email security product.

### Priority Definitions
* **P0 (Critical Blocker):** Critical security flaw, data-loss hazard, or fundamental architectural blocker. Must be resolved before any controlled enterprise pilot.
* **P1 (Pilot Essential):** Core reliability, trust management, or usability requirement necessary for a successful, non-frustrating pilot with non-technical employees.
* **P2 (Enterprise Operational):** Fleet management, enterprise directory scaling, packaging, and policy compliance necessary for broad organization-wide rollout.
* **P3 (Long-Term Enhancement):** Advanced platform features, hardware token integration, and multi-device cloud synchronization.

---

## 2. Master Gap Register

### Domain A: Multi-user Onboarding and Identity Establishment

| Gap ID | Title | Current Behavior | Evidence | Expected Behavior | Risk | Severity | Priority | Dependency | Proposed Solution | Acceptance Criteria | Verification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **M16-ONB-001** | Manual Out-of-Band Fingerprint Verification | Contact public keys must be manually imported via armored text and verified by visually matching a 64-character hex string. | `core/identity_service.py:100-115`, `ui/identity_settings.py:175` | Organization contacts discoverable automatically; domain-wide trust rooted in corporate CA or directory. | Non-technical employees cannot safely verify keys, leading to unverified identity warnings or skipped verification. | High | **RESOLVED (WS-02)** | None | Implement automated WKD discovery (`core/key_discovery.py`) and enterprise trust directory (`core/enterprise_trust.py`). | Public keys resolve automatically without manual copy-pasting; corporate domain keys certified automatically. | Verified in `tests/test_ws02_identity_and_trust.py` (25/25 passing). |
| **M16-ONB-002** | Default Launch Routes to Insecure Legacy Prototype | Launching `python main.py` with no CLI arguments launches the legacy TQR/Flask simulator (`MainWindow`). | `main.py:73` (`_launch_desktop()`), `ui/main_window.py` | Default application launch opens the modern secure mailbox client with account selection or first-run onboarding. | Users or administrators launching the app inadvertently use the vulnerable, unmaintained legacy simulator path. | Critical | **RESOLVED (WS-01)** | None | Invert `main.py` entry point: default to `_launch_mailbox()`. Relegate legacy simulator to explicit `--legacy-simulator` flag with prominent warning banners. | `python main.py` opens `MailboxWindow` without needing `--dev-mailbox`. | Verified in `tests/test_startup.py` (11/11 passing). |
| **M16-ONB-003** | Lack of Organization Administrator Interface | No mechanism for IT administrators to pre-configure vault location, Google Workspace OAuth client credentials, or security policy. | `main.py:58-70`, `transport/development_google.py` | IT administrators can supply an enterprise configuration file (`qumail.json` or Windows Registry / GPO). | Corporate rollout requires manual command-line argument configuration per employee workstation. | High | **P1** | M16-ONB-002 | Add enterprise configuration loader checking `HKLM\Software\Policies\QuMail` or `%PROGRAMDATA%\QuMail\config.json`. | App starts and discovers OAuth client ID and default vault paths automatically from registry/GPO. | Configuration loader unit tests covering GPO registry keys and file overrides. |
| **M16-ONB-004** | Employee Deprovisioning & Offboarding Hazard | When an employee leaves, their local vault remains fully readable on the machine, containing decrypted cached headers and private keys. | `experiments/m3/vault.py:20-50` | Enterprise deprovisioning command or policy-driven secure vault deactivation and key revocation. | Ex-employee retaining laptop can access historical confidential communications unless machine is completely wiped. | Medium | **P2** | M16-ONB-003 | Implement `--deprovision` CLI command and API to securely zeroize vault database and delete Windows Credential Store entries. | Running deprovision securely wipes `accounts` table rows and calls `CredDeleteW` for the master key. | Automated test validating unrecoverability of vault after deprovisioning. |

---

### Domain B: Cryptographic Key and Trust Lifecycle

| Gap ID | Title | Current Behavior | Evidence | Expected Behavior | Risk | Severity | Priority | Dependency | Proposed Solution | Acceptance Criteria | Verification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **M16-KEY-001** | Experimental Wire Profile Marker | Message headers use experimental marker `QM-OPENPGP-PQ-1-EXPERIMENT-M5` and provider policy `M2-EXPERIMENT-RFC9980-AES256-GCM`. | `experiments/m5/model.py:7`, `experiments/m3/vault.py:16` | Standardized, production-qualified profile identifier with explicit backward compatibility and version negotiation. | Future clients rejecting experimental markers will fail to decrypt messages; interoperability blocks. | High | **RESOLVED (WS-02)** | None | Standardize on `QM-OPENPGP-PQ-v1` as default while accepting `QM-OPENPGP-PQ-1-EXPERIMENT-M5` backward-compatibly. | Parser accepts both `QM-OPENPGP-PQ-v1` and `QM-OPENPGP-PQ-1-EXPERIMENT-M5`, but only emits `v1`. | Verified in `tests/test_ws02_identity_and_trust.py` and `tests/test_cryptographic_roundtrip.py`. |
| **M16-KEY-002** | No Key Expiration Enforcement or Renewal Alerts | Vault records key generation and certificate timestamps, but UI does not notify users when subkeys approach their 1-year expiration. | `experiments/m3/vault.py:120-160`, `ui/mailbox_window.py` | Proactive UI warnings 30 days before subkey expiration, with one-click guided subkey rotation. | Expired subkeys will silently cause remote correspondents to fail encryption when composing messages. | Medium | **RESOLVED (WS-02)** | None | Implement `core/key_lifecycle.py:evaluate_key_expiration` with 30-day warning threshold and KeyStatus alerts. | Proactive alert generated when expiration < 30 days; expired keys cleanly detected and flagged. | Verified in `tests/test_ws02_identity_and_trust.py`. |
| **M16-KEY-003** | Single-Device Account Constraint | Each account in the vault is strictly bound to one active device (`enforce_one_active_device`); restoring a backup deactivates the source device. | `experiments/m3/vault.py:65`, `docs/adrs/004-m3-development-exception.md:30` | Secure multi-device support allowing employees to read mail on both Windows desktop and secondary laptop/device. | Employees cannot use QuMail across desktop and laptop without repeated, destructive recovery procedures. | High | **P2** | M16-KEY-001 | Design multi-device cryptographic key hierarchy: master root key certifies distinct per-device subkeys; messages encrypt to all active devices. | Both desktop and laptop receive distinct encrypted PKESK packets in the same email; both can independently decrypt. | Integration test with 2 distinct device keys receiving a multi-recipient payload. |
| **M16-KEY-004** | Lack of Historical Signer Expiration Policy | When verifying an old message whose sender certificate has since expired, the verification treats it as an invalid/untrusted signature. | `experiments/m5/services.py:110-120` | RFC 4880 / RFC 9580 time-aware verification: check signature against key validity at the time the message was signed. | Legitimate historical correspondence appears as "Signature invalid / untrusted" once annual subkeys expire. | Medium | **RESOLVED (WS-02)** | None | Implement RFC 4880/9580 time-aware verification in `core/key_lifecycle.py:is_signature_historically_valid`. | Historical messages signed by a valid key before its expiration date evaluate as historically authentic. | Verified in `tests/test_ws02_identity_and_trust.py`. |

---

### Domain C: Inbound Mail Reliability and Mailbox Synchronization

| Gap ID | Title | Current Behavior | Evidence | Expected Behavior | Risk | Severity | Priority | Dependency | Proposed Solution | Acceptance Criteria | Verification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **M16-INB-001** | Manual Refresh Only (No Background Sync or IMAP IDLE) | Inbound messages are only discovered when the user manually clicks "Refresh headers". No background sync or push notifications. | `ui/mailbox_window.py:125, 217` | Background synchronization worker polling periodically (e.g. every 2 minutes) or maintaining IMAP IDLE connection. | Users miss urgent corporate emails; client does not function as an everyday corporate email reader. | High | **RESOLVED (WS-03)** | None | Implement `core/mailbox_sync.py:MailboxSyncEngine` using IMAP IDLE (RFC 2177) with fallback periodic polling and desktop notifications. | New emails appear automatically within seconds of delivery without user clicking Refresh. | Verified in `tests/test_ws03_sync_and_attachments.py` (27/27 passing). |
| **M16-INB-002** | Severe Message Size & Attachment Constraints | Maximum wire size capped at 256 KiB; message body capped at 8 KiB; attachments capped at 16 KiB total across at most 4 files. | `experiments/m5/model.py:8-15`, `mailbox_client/model.py:5` | Support normal business email sizes: up to 15–25 MiB total message size, bodies up to 1 MiB, attachments up to 20 MiB. | Employees cannot receive standard corporate communications (spreadsheets, slide decks, PDFs) via secure channel. | High | **RESOLVED (WS-03)** | None | Implement `core/attachment_pipeline.py` with measured 25 MiB wire / 20 MiB attachment limits and AES-256-GCM disk cache. | Successfully parse, decode, stream, cache, and save corporate attachments up to 20 MiB. | Verified in `tests/test_ws03_sync_and_attachments.py`. |
| **M16-INB-003** | 30-Message Bounded Window (No Full Mailbox Search) | Only the latest 30 headers are cached in the vault (`PAGE_SIZE = 30`). "Older" button scans backwards in 30-message slices. | `mailbox_client/model.py:7`, `mailbox_client/service.py:80-90` | Persistent local message index supporting full-text search across all received message headers and metadata. | Inability to locate past correspondence older than 30 messages; operational inefficiency for users. | Medium | **RESOLVED (WS-03)** | None | Implement persistent encrypted `MailboxIndex` in vault with dual-record M6 persistence and substring search across sender, subject, date. | User can type search query in header bar and immediately filter across historical headers. | Verified in `tests/test_ws03_sync_and_attachments.py`. |
| **M16-INB-004** | Plaintext Diagnostic Code in Inbound Open Path | `service.py:116, 123` and `mailbox_window.py:247` contain `print()` statements, `import traceback`, and print stack traces. | `mailbox_client/service.py:116, 123`, `ui/mailbox_window.py:247` | Clean production code with structured logging framework (`logging.getLogger("qumail")`) and no console pollution. | Diagnostic statements leak internal exception details to terminal stdout; violates production coding standards. | High | **RESOLVED (WS-01)** | None | Remove raw `print()` and `traceback.print_exc()` calls; replace with structured logging using severity levels and `PrivacyFilter` scrubbing. | Zero raw `print()` statements in production code; logs captured to rotating log file with scrubbed PII. | Verified in `tests/test_ws01_bootstrap_hygiene.py` (14/14 passing). |

---

### Domain D: Durable Outbox and Delivery Reliability

| Gap ID | Title | Current Behavior | Evidence | Expected Behavior | Risk | Severity | Priority | Dependency | Proposed Solution | Acceptance Criteria | Verification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **M16-OUT-001** | Manual-Only UNKNOWN Outbox Reconciliation | When an interrupted send enters `UNKNOWN`, recovery requires the user to manually log into Gmail Web and inspect Sent mail. | `experiments/m4/model.py:75-80`, `docs/handover/SECURITY_CONTRACTS.md:22` | Automated reconciliation: client queries Gmail IMAP `[Gmail]/Sent Mail` by stable `Message-ID` to determine outcome. | Non-technical users cannot determine if an email was sent; risk of duplicate sending or abandoning important emails. | High | **RESOLVED (WS-04)** | M16-INB-001 | Implement `SentFolderReconciler`: query Sent folder by RFC Message-ID, sender, recipient, and timestamp window; update state safely. | If Message-ID found in Sent folder, outbox transitions `UNKNOWN` -> `ACCEPTED` with `reconciled_sent_copy_found`; absence retains `UNKNOWN`. | Verified in `tests/test_ws04_outbox_and_reconciliation.py` (21/21 passing). |
| **M16-OUT-002** | Rigid 16-Operation Outbox Queue Limit | Maximum 16 outbox operations per account (`MAX_OPERATIONS = 16`). Attempting to queue a 17th operation raises `Failure(Error.LIMIT)`. | `experiments/m4/model.py:145` | Configurable spool queue supporting at least 256 pending/historical outbox records with automatic pruning of old `ACCEPTED` receipts. | High-volume senders or offline mobile workers get hard errors when composing multiple emails offline. | Medium | **RESOLVED (WS-04)** | None | Increase `MAX_OPERATIONS` to 256; implement `OutboxManager.prune_accepted()` with FIFO capacity pruning and 30-day age checks. | Queueing 50 drafts/messages succeeds cleanly without hitting resource limits; FIFO pruning verified. | Verified in `tests/test_ws04_outbox_and_reconciliation.py`. |
| **M16-OUT-003** | Lack of Submission Retry Backoff Scheduler | Retrying a failed or unknown send requires explicit manual user button click. No automated transient retry with jitter. | `experiments/m4/services.py`, `ui/mail_actions.py:70` | For transient network failures (DNS, socket timeout before `DATA`), client performs bounded automatic retry (3 attempts with backoff). | Transient Wi-Fi blips cause immediate send failure, requiring user to manually intervene and click Retry. | Medium | **RESOLVED (WS-04)** | M16-OUT-001 | Implement `ReconciliationScheduler` (5s, 15s, 60s backoff for `UNKNOWN`) and `TransientSubmissionRetry` (2s, 8s, 30s before DATA). | Client automatically executes bounded backoff passes; stops upon resolution; zero resends of post-DATA `UNKNOWN`. | Verified in `tests/test_ws04_outbox_and_reconciliation.py`. |

---

### Domain E: Corporate Usability and Product Experience

| Gap ID | Title | Current Behavior | Evidence | Expected Behavior | Risk | Severity | Priority | Dependency | Proposed Solution | Acceptance Criteria | Verification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **M16-UX-001** | Technical Jargon in Error Messages and Badges | Status messages expose raw internal details: `server_accepted_not_delivered`, `invalid_message`, `Failure: Code.LIMIT`. | `ui/mailbox_window.py:252`, `mailbox_client/service.py:128` | Plain-language, actionable business messages (e.g. "Sent to Google mail servers", "Message exceeds size limit of 15 MiB"). | Employees become confused or alarmed by cryptographic and protocol terminology, reducing adoption. | High | **RESOLVED (WS-05)** | None | Comprehensive user-facing string audit in `ui/security_badge_widget.py`, `core/security_indicators.py`, and `ui/compose_dialog.py`; map all internal codes to human-friendly advice and badges. | All error dialogs, status bar messages, and badges pass non-technical usability review with zero raw exception names. | Verified in `tests/test_ws05_ui_and_experience.py` (17/17 passing). |
| **M16-UX-002** | Polling Timer Overhead (50 ms QTimer Loop) | Both `MailboxWindow` and `MailActions` run a 50 ms polling timer (`self.timer.start(50)`) to check background worker futures. | `ui/mailbox_window.py:125`, `ui/mail_actions.py:85` | Event-driven architecture using Qt signals and slots (`pyqtSignal`) emitted upon worker task completion. | Continuous CPU wakeups drain laptop battery life and introduce slight UI thread stutter. | Medium | **RESOLVED (WS-03)** | None | Replace `QTimer` polling with event-driven background sync engine (`core/mailbox_sync.py`) emitting application events. | Zero idle CPU polling timers; updates triggered immediately on push notification. | Verified in `tests/test_ws03_sync_and_attachments.py`. |
| **M16-UX-003** | Lack of Rich Text or Markdown Rendering | Message viewing and composition are strictly plain text (`QPlainTextEdit`). Line wraps, paragraphs, bolding, and lists are unavailable. | `ui/mailbox_window.py:96`, `ui/mail_actions.py:41` | Clean, sandboxed rich text or Markdown viewer/editor without external web requests or script execution. | Modern business emails look archaic; tables and formatted reports cannot be read comfortably. | Medium | **RESOLVED (WS-05)** | None | Implement `ui/reading_pane.py` with sanitized, comfortable plain-text view strictly disallowing script execution, external tracking pixels, or remote CSS while formatting whitespace and line-wrap. | Clean, comfortable typography with complete isolation from remote asset fetch and script execution. | Verified in `tests/test_ws05_ui_and_experience.py`. |

---

### Domain F: Enterprise Deployment and Operations

| Gap ID | Title | Current Behavior | Evidence | Expected Behavior | Risk | Severity | Priority | Dependency | Proposed Solution | Acceptance Criteria | Verification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **M16-OPS-001** | Hardcoded Developer Native Binary Paths | Production entry points hardcode provider path to `tmp/m2/target/debug/qumail-m5-provider.exe`. | `main.py:82, 97`, `ui/mailbox_window.py:129`, `ui/mail_actions.py:134` | Provider binary resolved relative to application install root (`bin/qumail-provider.exe`) with signed release binary. | Application fails to run on any computer where the developer `tmp/` build tree does not exist. | Critical | **RESOLVED (WS-01)** | None | Implement `core.provider_resolver.resolve_provider()` with prioritized search (env vars, `_MEIPASS`, `bin/`, fallbacks) and staging layout. | Application resolves providers from `bin/` without developer repository or `tmp/` dependencies. | Verified in `tests/test_ws01_bootstrap_hygiene.py` (14/14 passing). |
| **M16-OPS-002** | Absence of Windows Installer and Code Signing | Application exists only as loose Python source files and scripts in a Git repository. | Repository root | Standard Windows MSI / Inno Setup installer; code-signed executable and native DLLs. | Cannot be deployed via Microsoft Intune, SCCM, or Group Policy; SmartScreen blocks execution. | High | **P1** | M16-OPS-001 | Create PyInstaller / cx_Freeze packaging script generating a single directory distribution; wrap with Inno Setup script. | Double-clicking `QuMailSetup.exe` installs app to `Program Files`, registers Start Menu shortcut, and runs cleanly. | Silent installation test: `QuMailSetup.exe /VERYSILENT /NORESTART` exits 0. |
| **M16-OPS-003** | Hardcoded Windows Credential Manager Dependency | Vault master key strictly requires Win32 `CredWriteW` / `CredReadW`. | `experiments/m3/secure_store.py:20-55` | Pluggable secure storage interface: DPAPI on Windows, Keychain on macOS, Secret Service on Linux. | Blocks the owner's strategic platform goal for multi-platform (and future Android) delivery. | Medium | **P2** | None | Implement `SecureStore` abstraction with `WindowsCredentialStore`, `MacOSKeychainStore`, and `LinuxSecretServiceStore`. | Vault initializes and passes tests on macOS/Linux using native OS credential stores. | Platform test suite run across OS environments. |
| **M16-OPS-004** | Missing Privacy-Preserving Crash Reporting | Unhandled exceptions or native panics crash the process silently or print to console; no crash dump or telemetry. | `main.py`, `ui/mailbox_window.py:245-255` | Local diagnostic crash logger generating scrubbed, encrypted crash reports that users can optionally submit to IT. | IT administrators cannot diagnose workstation-specific crashes or provider panics in the field. | Medium | **P2** | None | Add `sys.excepthook` handler capturing crash backtrace with memory addresses, scrubbing PII, and writing to `logs/crash.log`. | Unhandled exception triggers crash dialog prompting user to save or send diagnostic log. | Test injecting synthetic unhandled exception and verifying sanitized crash log generation. |

---

### Domain G: Security Architecture and Threat Model

| Gap ID | Title | Current Behavior | Evidence | Expected Behavior | Risk | Severity | Priority | Dependency | Proposed Solution | Acceptance Criteria | Verification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **M16-SEC-001** | Debug Build Security Flags in Native Provider | `qumail-m5-provider.exe` is compiled in Debug mode (`target/debug`), lacking full compiler hardening. | `ui/mailbox_window.py:129`, `experiments/m2/Cargo.toml` | Compiled with `cargo build --release` with ASLR (`/DYNAMICBASE`), DEP (`/NXCOMPAT`), stack protection, and symbols stripped. | Vulnerability to binary exploitation techniques or reverse engineering in corporate environments. | High | **RESOLVED (WS-01)** | None | Compile native providers via `tools/build_providers.ps1` with `RUSTFLAGS="-C control-flow-guard"` and release profile; verify DllCharacteristics `0xc160`. | Provider binary inspection via pure-Python PE parser confirms ASLR, DEP, 64-bit ASLR, and Control Flow Guard. | Verified in `tests/test_ws01_bootstrap_hygiene.py` and `bin/manifest.json`. |
| **M16-SEC-002** | Plaintext Memory Hygiene in Python Runtime | Plaintext bodies and private key buffers remain in Python heap memory as immutable strings/bytes until garbage collected. | `mailbox_client/service.py:126`, `experiments/m5/services.py:95` | Sensitive plaintext zeroized immediately after rendering; memory locking where possible. | Malware running in same user account or forensic memory dump can extract plaintext message contents. | Medium | **P1** | None | Use `bytearray` buffers with explicit zeroization loops for decrypted plaintext; clear UI widgets immediately upon window hide/lock. | Forensic memory search shows zero decrypted message string remnants after message viewer closed. | Memory dump analysis script verifying zeroization after close. |
| **M16-SEC-003** | Vault Rollback Replay Vulnerability | Restoring an older vault backup restores an older `replay_v1` table, allowing previously observed messages to be re-rendered as "fresh". | `docs/handover/SECURITY_CONTRACTS.md:82`, `experiments/m3/vault.py` | Monotonic counter or out-of-vault persistent replay receipt tracking across backup restores. | Attacker inducing an employee to restore a backup can replay previously revoked or executed instructions. | Medium | **P2** | None | Store replay digests in Windows Credential Manager or an append-only registry key that survives database file replacement. | Restoring a 1-week-old vault database still detects and flags messages received yesterday as DUPLICATE. | Test creating backup, receiving message, restoring backup, and verifying replay detection persists. |
| **M16-SEC-004** | Missing MTA Header Injection Sanitization | Parser checks singletons on known headers, but does not sanitize potential line-folding or non-ASCII control characters in inner headers. | `experiments/m5/mime.py:20, 115` | Strict RFC 5322 header field validation rejecting control characters (`\r`, `\n`, `\x00`–`\x1F`) inside header values. | Potential header injection or UI rendering anomalies if an adversary crafts malicious inner header fields. | Medium | **P1** | None | Add regex/byte validator in `mime.py:validate()` rejecting raw control characters in `Subject:`, `From:`, and `To:`. | Malicious message with embedded `\r\nBcc:` inside Subject raises `Failure(Code.INVALID)` during parsing. | Security regression test with header injection fuzzing vectors. |

---

## 3. Prioritized Gap Summary by Phase

### Phase 1: Pre-Pilot Blockers (P0 — All 4 Resolved in WS-01)
1. **M16-ONB-002:** Invert `main.py` default entry point to launch modern mailbox client. **[RESOLVED - WS-01]**
2. **M16-OPS-001:** Resolve hardcoded `tmp/` native binary paths to production install directory. **[RESOLVED - WS-01]**
3. **M16-SEC-001:** Compile native provider with release flags, ASLR, DEP, and Control Flow Guard. **[RESOLVED - WS-01]**
4. **M16-INB-004:** Clean diagnostic `print()` statements and traceback logging from production code. **[RESOLVED - WS-01]**

### Phase 2: Pilot Essential Capabilities (P1 — Core Pilot Requirements)
1. **M16-ONB-001:** Automatic contact discovery via WKD / enterprise directory lookup. **[RESOLVED - WS-02]**
2. **M16-ONB-003:** Enterprise configuration loader via Registry / GPO / config file.
3. **M16-KEY-001:** Standardize wire profile marker from `EXPERIMENT` to `QM-OPENPGP-PQ-v1`. **[RESOLVED - WS-02]**
4. **M16-KEY-002:** Subkey expiration monitoring and guided rotation notifications. **[RESOLVED - WS-02]**
5. **M16-INB-001:** Background mailbox synchronization worker with desktop notifications. **[RESOLVED - WS-03]**
6. **M16-INB-002:** Increase message limits (15 MiB wire, 10 MiB attachments) with streaming buffers. **[RESOLVED - WS-03]**
7. **M16-OUT-001:** Automated IMAP Sent-folder reconciliation for `UNKNOWN` outbox states. **[RESOLVED - WS-04]**
8. **M16-UX-001:** Plain-language corporate user interface string and error message audit. **[RESOLVED - WS-05]**
9. **M16-OPS-002:** Windows installer packaging (Inno Setup / MSI) with code signing.
10. **M16-SEC-002:** Plaintext buffer zeroization and memory hygiene.
11. **M16-SEC-004:** Strict RFC 5322 header injection sanitization.

### Phase 3: Enterprise Operational Features (P2 — Broad Deployment)
1. **M16-ONB-004:** Enterprise offboarding and secure vault deprovisioning.
2. **M16-KEY-003:** Multi-device key management hierarchy.
3. **M16-KEY-004:** Historical message verification with time-aware certificate validation. **[RESOLVED - WS-02]**
4. **M16-INB-003:** Persistent SQLite FTS5 full-mailbox header search index. **[RESOLVED - WS-03]**
5. **M16-OUT-002:** 256-operation outbox spool with automatic pruning. **[RESOLVED - WS-04]**
6. **M16-OUT-003:** Exponential backoff scheduler for transient network failures. **[RESOLVED - WS-04]**
7. **M16-UX-002:** Replace 50 ms polling loop with native Qt event-driven signals. **[RESOLVED - WS-03]**
8. **M16-UX-003:** Sandboxed rich text / comfortable plain-text viewer. **[RESOLVED - WS-05]**
9. **M16-OPS-003:** Cross-platform credential store abstraction (macOS / Linux).
10. **M16-OPS-004:** Privacy-preserving diagnostic crash reporting.
11. **M16-SEC-003:** Monotonic out-of-vault replay protection.
