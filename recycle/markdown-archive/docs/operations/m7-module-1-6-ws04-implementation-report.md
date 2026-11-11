# QuMail M7 — Module 1.6 Workstream 04 Implementation Report

**Milestone:** M7 — Module 1.6  
**Workstream:** WS-04 — Durable Outbox, Sent-Folder Reconciliation & Delivery Resilience  
**Implementation Branch:** [`codex/m7-module-1-6-ws04`](https://github.com/uzx-02/QuMail/tree/codex/m7-module-1-6-ws04)  
**Accepted Baseline:** `1414722` (WS-03 Final Acceptance Checkpoint)  
**Technical Lead & Security Architect:** ChatGPT  
**Implementation Engineer:** Antigravity  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  

---

## 1. Executive Summary

Workstream **WS-04 (Durable Outbox, Sent-Folder Reconciliation & Delivery Resilience)** is complete.

QuMail's outbox subsystem has been upgraded from a rigid, manual prototype into a crash-resilient, durable delivery pipeline. It provides a formal 6-state lifecycle (`DRAFT`, `PREPARED`, `SUBMITTING`, `ACCEPTED`, `UNKNOWN`, `FAILED`), boundary-safe crash recovery, automated Sent-folder reconciliation via read-only IMAP, bounded exponential backoff scheduling, explicit duplicate-risk retry authorization, single-flight per-operation concurrency locking, expanded 256-operation spool capacity with safe FIFO pruning, and a plain-language user status contract for WS-05.

All implementation work is isolated to branch `codex/m7-module-1-6-ws04` starting from accepted baseline `1414722`. 21 new automated tests were authored and verified, bringing the modern regression suite to **187 passing tests** with zero failures, zero skips, and zero network leakage.

---

## 2. Production Readiness Gap Resolution Status

| Gap ID | Description | Severity | Prior Status | WS-04 Status | Verification Evidence |
|---|---|:---:|:---:|:---:|---|
| **M16-OUT-001** | Manual-Only UNKNOWN Outbox Reconciliation | High (P1) | OPEN | **RESOLVED** | `core/outbox_reconciliation.py:SentFolderReconciler` querying Sent folders by Message-ID, sender, recipients, and timestamp; verified in `test_reconciliation_conclusive_match_in_sent_folder`, `test_reconciliation_absence_from_sent_retains_unknown_and_never_auto_retries`. |
| **M16-OUT-002** | Rigid 16-Operation Outbox Queue Limit | Medium (P2) | OPEN | **RESOLVED** | Spool capacity expanded to 256 (`MAX_OPERATIONS = 256`); `OutboxManager.prune_accepted()` implements FIFO pruning of old `ACCEPTED` receipts; verified in `test_outbox_capacity_supports_50_plus_operations`, `test_fifo_pruning_of_accepted_records_never_touches_pending`. |
| **M16-OUT-003** | Lack of Submission Retry Backoff Scheduler | Medium (P2) | OPEN | **RESOLVED** | `ReconciliationScheduler` (5s, 15s, 60s backoff for `UNKNOWN`) and `TransientSubmissionRetry` (2s, 8s, 30s before DATA); verified in `test_reconciliation_scheduler_background_resolution`, `test_transient_submission_retry_for_pre_submission_errors`. |

---

## 3. Comprehensive Test Suite Evidence

The test suite was executed against the installed Python 3.12 environment (`.venv-m1-clean`) using zero-network deterministic fixtures.

### 3.1 Modern Regression Suite Summary

| Test Suite File | Component / Focus Area | Tests Executed | Passed | Failed | Skips |
|---|---|:---:|:---:|:---:|:---:|
| `tests/test_startup.py` | Modern default launch, CLI flags, dry-run network isolation | 11 | 11 | 0 | 0 |
| `tests/test_ws01_bootstrap_hygiene.py` | Provider resolution, PE CFG `0xc160`, PrivacyFilter, code hygiene | 14 | 14 | 0 | 0 |
| `tests/test_ws02_identity_and_trust.py` | WKD discovery, z-base-32, TrustEngine, SecurityIndicators, Profile v1 | 25 | 25 | 0 | 0 |
| `tests/test_ws02_security_assurance.py` | Historical time evidence, mandatory RFC 3161 signedAttrs, EKU, ESS cert ID | 67 | 67 | 0 | 0 |
| `tests/test_ws03_sync_and_attachments.py` | Background sync engine, IMAP IDLE, cursor model, index, practical attachments | 27 | 27 | 0 | 0 |
| `tests/test_ws04_outbox_and_reconciliation.py` | **Durable outbox, crash recovery, Sent-folder reconciliation, backoff, capacity** | **21** | **21** | **0** | **0** |
| `tests/test_cryptographic_roundtrip.py` | End-to-end M5 crypto roundtrip, Ed25519, replay detection, MIME parser | 15 | 15 | 0 | 0 |
| `tests/test_cancellation_submission_semantics.py` | Outbox cancellation, uncertain submission recovery, crash semantics | 7 | 7 | 0 | 0 |
| **Total** | **Complete Modern Regression Suite** | **187** | **187** | **0** | **0** |

Execution time: **62.87s** for all 187 tests.

---

## 4. Workstream Technical Breakdown

### 4.1 WS-04A — Durable Outbox State Machine (`core/outbox_manager.py`)
- **Explicit 6-State Lifecycle:** Formalized `OutboxState` (`DRAFT`, `PREPARED`, `SUBMITTING`, `ACCEPTED`, `UNKNOWN`, `FAILED`).
- **WS-05 Integration Contract:** Mapped all internal states to plain-language, non-technical labels:
  - `DRAFT` $\rightarrow$ "Draft saved locally"
  - `PREPARED` $\rightarrow$ "Queued for secure sending"
  - `SUBMITTING` $\rightarrow$ "Sending to mail server..."
  - `ACCEPTED` $\rightarrow$ "Accepted by your mail server"
  - `UNKNOWN` $\rightarrow$ "Could not confirm whether this message was sent"
  - `FAILED` $\rightarrow$ "Submission failed"
  - Sent-copy found annotation: "A sent copy was found"
  - Duplicate-risk annotation: "Retrying may send a duplicate"
- **Delivery Invariant:** Status labels strictly avoid claiming "delivered to recipient", as server acceptance (`250 OK`) confirms only transfer agent receipt.

### 4.2 WS-04B — Boundary Safety & Crash Recovery
- **Boundary Safety Enforcement:** Errors occurring before the message terminator (`.\r\n`) are definitively marked `FAILED`. Errors occurring after the terminator or while awaiting `250 OK` are strictly evaluated as `UNKNOWN`.
- **Startup Crash Recovery:** `OutboxManager.recover()` scans for orphaned `SUBMITTING` states and transitions them to `UNKNOWN` with reason `interrupted_acceptance_unknown`.
- **Mandatory Invariant — Zero Automatic Retry:** Recovered `UNKNOWN` records are never resubmitted across restarts, background workers, or sync passes.

### 4.3 WS-04C — Sent-Folder Reconciliation Engine (`core/outbox_reconciliation.py`)
- **Folder Discovery:** Queries user Sent mailboxes (`[Gmail]/Sent Mail`, `Sent`, `Sent Messages`, `INBOX.Sent`) via read-only IMAP (`EXAMINE`).
- **4-Point Matching Criteria:**
  1. RFC 5322 `Message-ID` normalized match.
  2. `From` address matching sender identity.
  3. `To` / `Cc` addresses containing all binding recipients.
  4. Parsed `Date` timestamp falling within $[-24\text{h}, +24\text{h}]$ of submission.
- **Delivery Semantics:**
  - Positive match: transitions `UNKNOWN` $\rightarrow$ `ACCEPTED` with reason `reconciled_sent_copy_found` and persists sent-copy audit data.
  - Absence from Sent: retains `UNKNOWN` with `reconciled_no_sent_copy_found`. **Absence does not prove rejection and never triggers automatic resends.**
  - Conflicting matches: retains `UNKNOWN` with `reconciliation_conflicting_candidates`.

### 4.4 WS-04D — Explicit Retry Authorization & Duplicate Protection
- Resending `UNKNOWN` requires explicit user decision (`acknowledge_duplicate_risk=True`). Retrying without acknowledgment raises `Failure(Error.DUPLICATE)`.
- Original frozen ciphertext, message identifier, and SHA-256 digest are strictly preserved across retries.
- Maximum retry attempts capped at 3 (`DEFAULT_MAX_ATTEMPTS`); further attempts raise `Failure(Error.LIMIT)`.

### 4.5 WS-04E — Bounded Backoff Scheduler & Transient Retry (`M16-OUT-003`)
- `ReconciliationScheduler` executes non-polling background reconciliation at 5s, 15s, and 60s intervals. Stops immediately upon match confirmation or clean cancellation.
- `TransientSubmissionRetry` provides bounded automated retry (2s, 8s, 30s) strictly for pre-submission network errors (DNS, connect drops before DATA). Post-DATA errors are never retried.

### 4.6 WS-04F — Capacity Expansion & FIFO Pruning (`M16-OUT-002`)
- Increased outbox queue limit from 16 to 256 operations.
- `OutboxManager.prune_accepted()` safely prunes oldest `ACCEPTED` records when exceeding capacity or older than 30 days.
- Never prunes `DRAFT`, `PREPARED`, `SUBMITTING`, `UNKNOWN`, or `FAILED` operations.

---

## 5. Security & Invariant Integrity Audit

1. **Zero Real Network Operations in Tests:** All tests executed using in-memory mock clients and mock transports.
2. **Zero Plaintext Secrets Leaked:** Outbox presentation models and audit records scrub all private keys, passwords, and OAuth tokens.
3. **Preservation of Baseline History:** Starting baseline `1414722` preserved; no historical commits amended.
4. **Untracked Reference Files Preserved:**
   - `QuMail-1.0-Research-Audit-Specification.pdf`
   - `Start-QuMailDemo.ps1`
   - `docs/operations/m2-reviewer-request.md`
