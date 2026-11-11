# QuMail M7 — Sent-Folder Reconciliation Engine & Delivery Semantics

**Milestone:** M7 — Module 1.6  
**Workstream:** WS-04 — Durable Outbox, Sent-Folder Reconciliation & Delivery Resilience  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  
**Status:** Approved & Implemented (`codex/m7-module-1-6-ws04`)  

---

## 1. Executive Summary

When network disconnects, timeouts, or process terminations leave an outgoing message in the ambiguous `UNKNOWN` state, QuMail employs an automated **Sent-Folder Reconciliation Engine** (`core/outbox_reconciliation.py`).

By inspecting the authenticated user's remote Sent mailbox (`[Gmail]/Sent Mail`, `Sent`, `Sent Messages`, `INBOX.Sent`), QuMail can cryptographically and structurally determine whether the mail server processed and accepted the submission without risking duplicate delivery.

---

## 2. Sent-Folder Reconciliation Protocol

### 2.1 Candidate Matching Invariants

To avoid false-positive matches (such as matching an older email with a similar subject or an unrelated message), candidate messages discovered in the Sent folder must satisfy four strict verification criteria:

1. **RFC 5322 `Message-ID` Equality:**
   - The candidate's `Message-ID` header must match the prepared envelope's `message_id` exactly (case-normalized, whitespace and angle brackets stripped).
   - In QuMail, the Message-ID is deterministic and bound to the operation: `<operation-id@qumail.invalid>` or corporate domain equivalent.
2. **Sender (`From`) Binding:**
   - The sender email address parsed from the candidate's `From` header must match `envelope.sender.value`.
   - Prevents an adversary or shared mailbox from spoofing the origin.
3. **Recipient (`To` / `Cc`) Conformance:**
   - All recipient addresses in `envelope.binding.recipients` must be present in the candidate's parsed `To` or `Cc` headers.
4. **Timestamp Window Bounds:**
   - The candidate's parsed `Date` header must fall within a strict operational window around the submission timestamp:
     $$\text{submission\_ts} - 86400.0 \le \text{candidate\_ts} \le \text{submission\_ts} + 86400.0$$
   - Prevents replay of historical messages matching synthetic or reused identifiers.

```
       Candidate Message in Sent Mail
      +------------------------------------------+
      | Message-ID: <op123@qumail.invalid>      | ---> Must match envelope.message_id
      | From:       alice@example.invalid        | ---> Must match envelope.sender
      | To:         bob@example.invalid          | ---> Must contain envelope.recipients
      | Date:       Mon, 09 Nov 2026 17:34:00    | ---> Must fall within [-24h, +24h]
      +------------------------------------------+
```

---

## 3. Reconciliation Outcomes & Delivery Semantics

| Outcome Status | Trigger Condition | State Transition | Audit Reason | Plain-Language Label |
|---|---|:---:|---|---|
| `CONFIRMED` | Exactly 1 candidate matches all 4 criteria. | `UNKNOWN` $\rightarrow$ `ACCEPTED` | `reconciled_sent_copy_found` | "A sent copy was found" |
| `NOT_FOUND` | 0 candidates match in the Sent folder. | `UNKNOWN` $\rightarrow$ `UNKNOWN` | `reconciled_no_sent_copy_found` | "Could not confirm whether this message was sent" |
| `CONFLICT` | Multiple candidates match (ambiguous). | `UNKNOWN` $\rightarrow$ `UNKNOWN` | `reconciliation_conflicting_candidates` | "Could not confirm whether this message was sent" |
| `UNAVAILABLE` | Sent folder missing or connection drops. | `UNKNOWN` $\rightarrow$ `UNKNOWN` | `sent_folder_not_found_or_inaccessible` | "Could not confirm whether this message was sent" |

### 3.1 The "Absence Does Not Prove Rejection" Invariant
A critical security rule enforced in QuMail:
> **Absence from the Sent folder does NOT prove that a message was rejected by the server.**

**Why?**
- In modern mail systems (including Google Workspace and standard IMAP), server-side spooling to Sent may lag behind SMTP ingestion by seconds or minutes.
- Certain custom SMTP relays accept outbound messages without automatically copying them into the user's IMAP Sent folder.
- If QuMail assumed that absence from Sent meant rejection and automatically retried the message, it would cause catastrophic duplicate email storms.

**Enforced Behavior:**
- Negative reconciliation retains `UNKNOWN`.
- The audit log records `reconciled_no_sent_copy_found`.
- Zero automatic resends occur.
- Resending strictly requires user authorization with duplicate risk acknowledgment.

---

## 4. Reconciliation Scheduling & Backoff (M16-OUT-003)

QuMail implements `ReconciliationScheduler` to automate Sent-folder inspection without aggressive polling or CPU wakeups:

1. **Bounded Backoff Intervals:**
   When an operation enters `UNKNOWN`, the scheduler executes up to 3 non-polling passes:
   - **Pass 1:** After 5.0 seconds (catches typical immediate server spooling).
   - **Pass 2:** After 15.0 seconds (catches slight network/indexing delays).
   - **Pass 3:** After 60.0 seconds (final background verification attempt).
2. **Immediate Termination on Resolution:**
   If Pass 1 or Pass 2 finds the message (`CONFIRMED`), the scheduler updates the repository to `ACCEPTED`, triggers the application callback, and immediately terminates further scheduled attempts.
3. **Clean Cancellation:**
   Background workers monitor `cancel_event` and `lease.cancelled`. Application shutdown, logout, or account switching halts all running reconciliation threads in $< 100$ ms.

---

## 5. Transient Pre-Submission Retry (M16-OUT-003)

For network interruptions that occur **strictly before the message DATA terminator** (e.g. transient Wi-Fi drops, DNS failures, connection timeouts during TCP/TLS connect):
- QuMail provides `TransientSubmissionRetry`.
- Performs up to 3 automated retries with exponential backoff (2.0s, 8.0s, 30.0s).
- **Strict Invariant:** If the final `.\r\n` terminator has already been transmitted, `TransientSubmissionRetry` is **strictly forbidden**. Any post-terminator error is immediately routed to `UNKNOWN` and the `SentFolderReconciler`.

---

## 6. Capacity Management & FIFO Pruning (M16-OUT-002)

To eliminate the historical 16-operation outbox bottleneck:
- Maximum operations increased to $\text{MAX\_OPERATIONS} = 256$.
- `OutboxManager.prune_accepted()` implements safe FIFO pruning:
  - Scans exclusively for records in `State.ACCEPTED`.
  - Prunes oldest records if total records exceed 256, or if records are older than 30 days.
  - **Never** prunes `DRAFT`, `PREPARED`, `SUBMITTING`, `UNKNOWN`, or `FAILED` operations.
  - Automatically called during `save()` when approaching capacity limits to ensure seamless drafting.
