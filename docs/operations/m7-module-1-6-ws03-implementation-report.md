# QuMail M7 — Module 1.6 Workstream 03 Implementation Report

**Milestone:** M7 — Module 1.6  
**Workstream:** WS-03 — Event-Driven Mailbox Synchronization, Background Inbox & Attachment Pipeline  
**Implementation Branch:** [`codex/m7-module-1-6-ws03`](https://github.com/uzx-02/QuMail/tree/codex/m7-module-1-6-ws03)  
**Accepted Baseline:** `33733d6` (WS-02 Final Acceptance Checkpoint)  
**Technical Lead & Security Architect:** ChatGPT  
**Implementation Engineer:** Antigravity  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  

---

## 1. Executive Summary

Workstream **WS-03 (Event-Driven Mailbox Synchronization, Background Inbox & Attachment Pipeline)** is complete.

QuMail has successfully transitioned from a static, manual-refresh email reader with a 30-message window and 16 KiB attachment limit into an event-driven background mailbox client supporting RFC 2177 IMAP IDLE, safe fallback polling, persistent race-safe cursor management, a metadata-first encrypted message index, and a practical attachment pipeline supporting corporate document exchange up to 25 MiB.

All implementation work is isolated to branch `codex/m7-module-1-6-ws03` starting from accepted baseline `33733d6`. 27 new comprehensive automated tests were authored and verified, bringing the modern regression suite to **166 passing tests** with zero failures, zero skips, and zero network leakage.

---

## 2. Production Readiness Gap Resolution Status

| Gap ID | Description | Severity | Prior Status | WS-03 Status | Verification Evidence |
|---|---|:---:|:---:|:---:|---|
| **M16-INB-001** | Manual Refresh Only (No Background Sync or IMAP IDLE) | High (P1) | OPEN | **RESOLVED** | `core/mailbox_sync.py:MailboxSyncEngine` implementing RFC 2177 IDLE, fallback polling, and push notifications; verified in `test_sync_engine_initial_synchronization`, `test_sync_engine_idle_notification_event_driven`. |
| **M16-INB-002** | Severe Message Size & Attachment Constraints | High (P1) | OPEN | **RESOLVED** | `core/attachment_pipeline.py` supporting 25 MiB envelope, 20 MiB attachments, safe streaming decoding, and AES-256-GCM encrypted disk cache; verified in `test_attachment_pipeline_pdf_and_office_documents`, `test_attachment_pipeline_oversized_limits_rejected`. |
| **M16-INB-003** | 30-Message Bounded Window (No Local Metadata Index) | Medium (P2) | OPEN | **RESOLVED** | `core/mailbox_index.py:MailboxIndex` providing metadata-first encrypted index in the vault with dual-record M6 persistence; verified in `test_index_query_filtering_and_pagination`, `test_index_vault_schema_migration_and_dual_save`. |
| **M16-UX-002** | Polling Timer Overhead (50 ms QTimer Loop) | Medium (P2) | OPEN | **RESOLVED** | Event-driven architecture with clean application callbacks and background worker lifecycle off the GUI thread; verified in `test_sync_engine_idle_notification_event_driven`. |

---

## 3. Comprehensive Test Suite Evidence

The test suite was executed against the installed Python 3.12 environment (`.venv-m1-clean`) using zero-network deterministic fixtures.

### 3.1 Suite Summary

| Test Suite File | Component / Focus Area | Tests Executed | Passed | Failed | Skips |
|---|---|:---:|:---:|:---:|:---:|
| `tests/test_startup.py` | Modern default launch, CLI flags, dry-run network isolation | 11 | 11 | 0 | 0 |
| `tests/test_ws01_bootstrap_hygiene.py` | Provider resolution, PE CFG `0xc160`, PrivacyFilter, code hygiene | 14 | 14 | 0 | 0 |
| `tests/test_ws02_identity_and_trust.py` | WKD discovery, z-base-32, TrustEngine, SecurityIndicators, Profile v1 | 25 | 25 | 0 | 0 |
| `tests/test_ws02_security_assurance.py` | Historical time evidence, mandatory RFC 3161 signedAttrs, EKU, ESS cert ID | 67 | 67 | 0 | 0 |
| `tests/test_ws03_sync_and_attachments.py` | **Background sync engine, IMAP IDLE, cursor model, index, practical attachments** | **27** | **27** | **0** | **0** |
| `tests/test_cryptographic_roundtrip.py` | End-to-end M5 crypto roundtrip, Ed25519, replay detection, MIME parser | 15 | 15 | 0 | 0 |
| `tests/test_cancellation_submission_semantics.py` | Outbox cancellation, uncertain submission recovery, crash semantics | 7 | 7 | 0 | 0 |
| **Total** | **Complete Modern Regression Suite** | **166** | **166** | **0** | **0** |

Execution time: **35.02s** for all 166 tests.

---

## 4. Workstream Technical Breakdown

### 4.1 WS-03A — Background Synchronization Engine (`core/mailbox_sync.py`)
- **Lifecycle State Machine:** Implemented 8 distinct states (`STOPPED`, `CONNECTING`, `SYNCHRONIZING`, `IDLE`, `RECONNECTING`, `DEGRADED_POLLING`, `STOPPING`, `FAILED`).
- **IMAP IDLE Implementation:** Handled RFC 2177 IDLE command entry (`TAG IDLE`), continuation wait (`+ idling`), unsolicited untagged server event processing, clean `DONE` termination, and periodic re-issuing before server timeouts (default 10 minutes).
- **Fallback Polling:** Configurable fallback polling (`DEGRADED_POLLING`) when IDLE is unsupported by the server or repeatedly drops.
- **Reconnection & Backoff:** Implemented exponential backoff with random jitter ($\text{initial}=1.0\text{s}$, $\text{multiplier}=2.0$, $\text{max}=60.0\text{s}$, $\text{jitter}=\pm 20\%$).
- **Authentication Expiration:** Fails closed on authentication errors, transitions to `FAILED`, and notifies application observers via `on_auth_required`.
- **Cancellation & Concurrency:** Cancellation cleanly interrupts socket operations and joins worker threads without hanging. Account-level locking prevents duplicate worker spawning.

### 4.2 WS-03B — IMAP State and Cursor Management (`core/mailbox_cursor.py`)
- **Persistent Synchronization Cursor:** Tracks `account_id`, `mailbox`, `uidvalidity`, `uidnext`, `highest_modseq`, `synced_uids`, and `last_sync_time`.
- **UIDVALIDITY Rollover Safety:** Enforces immediate invalidation and index reset if server `UIDVALIDITY` changes. Stale UIDs are never reused across generations.
- **Expunge Reconciliation:** Compares local `synced_uids` against server UID search results; purges expunged/vanished messages from local index and reconciles unread counters.
- **Transactional Durability:** Cursor state commits atomically inside the encrypted account vault transaction (`m7_sync_cursor_v1`).

### 4.3 WS-03C — Metadata-First Encrypted Mailbox Index (`core/mailbox_index.py`)
- **Metadata-First Invariant:** Inbound sync retrieves only headers and metadata via non-mutating `BODY.PEEK[HEADER.FIELDS ...]`.
- **Indexed Fields:** `uid`, `uidvalidity`, `mailbox`, `account_id`, `sender_display`, `sender_address`, `recipients`, `subject`, `date`, `date_ts`, `message_id`, `size`, `flags`, `seen`, `has_attachments`, `attachments_meta`, `snippet`, `in_reply_to`, `references`.
- **Encrypted Vault Storage:** Stored in `m7_mailbox_index_v1` inside the AES-256-GCM protected vault.
- **M6 Dual-Record Persistence:** Maintains backward compatibility with legacy `m6_mailbox_v1` by synchronizing the 30-message window on every index write.
- **Read-State Invariant:** Background synchronization and on-demand body fetches use `BODY.PEEK[]`, strictly preserving server `\Seen` flags.

### 4.4 WS-03D — Authoritative Unread Counts & Event Dispatching
- **Unread Accounting:** Directly derived from authoritative flags (`\Seen` absent).
- **Expunge & Reconnect Reconciliation:** Unread counts are dynamically recomputed after expunges and reconnects, avoiding drift.
- **Privacy in Notifications:** Events expose sanitized sender and subject snippets; message bodies, attachments, and private tokens are excluded from OS notifications.

### 4.5 WS-03E — Practical Attachment Pipeline (`core/attachment_pipeline.py`)
- **Separation of Concerns:** Separates transport-level conventional/business attachments from the frozen M5 64 KiB experimental cryptographic envelope.
- **Measured Limits:** Enforced 25 MiB maximum wire size, 1 MiB body size, 20 MiB individual attachment size, 20 MiB aggregate attachment size, 20 maximum attachments, 8 MIME nesting levels, 64 parts, 64 KiB header block, and 10x decompression expansion cap.
- **Defensive Hardening:**
  - Filename sanitization strips traversal (`..`, `/`, `\`), ADS (`:`), bidi overrides, control characters, and reserved Windows device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`).
  - Encrypted attachment cache (`<cache_dir>/<content_hash>.enc`) using AES-256-GCM.
  - Atomic export via `open(target, "xb")` with path validation and zero auto-execution.

### 4.6 WS-03F — Security Invariants Preservation
- Verification strictly precedes plaintext release.
- Recipient trust and identity pinning from WS-02 preserved.
- Zero sensitive data logged.
- No plaintext caches or SMTP outbox changes introduced.

---

## 5. Empirical Windows Profiling Evidence

Measured on Windows (`Python 3.12.14`, `Win32 x86_64`):

```text
AES-GCM  1 MiB:   0.9 ms, RSS:  21.8 MiB
AES-GCM  5 MiB:   3.7 ms, RSS:  33.8 MiB
AES-GCM 10 MiB:   8.2 ms, RSS:  48.8 MiB
AES-GCM 20 MiB:  16.1 ms, RSS:  78.8 MiB
AES-GCM 25 MiB:  19.8 ms, RSS:  93.8 MiB

MIME  1 MiB (1.4MB wire):  parse =  27.0 ms, RSS =  25.5 MiB
MIME  5 MiB (6.8MB wire):  parse = 130.6 ms, RSS =  49.2 MiB
MIME 10 MiB (13.5MB wire): parse = 283.0 ms, RSS =  80.3 MiB
MIME 20 MiB (27.0MB wire): parse = 533.7 ms, RSS = 140.6 MiB

JSON list(bytes) 4 MiB: output = 16.0 MiB (4.0x expansion) -> proves why M5 pipe cannot handle 25 MiB
```

---

## 6. Documentation Deliverables

1. [`docs/operations/m7-module-1-6-ws03-implementation-report.md`](docs/operations/m7-module-1-6-ws03-implementation-report.md) (this document)
2. [`docs/operations/mailbox-synchronization-and-cursor-model.md`](docs/operations/mailbox-synchronization-and-cursor-model.md)
3. [`docs/operations/mime-and-attachment-security.md`](docs/operations/mime-and-attachment-security.md)

---

## 7. Scope Boundaries & Explicit Exclusions

In accordance with WS-03 instructions:
- The full 3-pane UI redesign remains deferred to WS-05.
- Automated outbox reconciliation and retry scheduler remain deferred to WS-04.
- Windows installer and GPO packaging remain deferred to WS-06.
- No live external mail operations occurred; all tests used zero-network deterministic in-memory fixtures.
- Baselines `eff3736`, `c9a3cf4`, `6b16f36`, `d82ea90`, `cd2b43e`, and `33733d6` remain strictly preserved.
