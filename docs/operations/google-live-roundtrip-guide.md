# QuMail — Live Gmail SMTP & End-to-End Round-Trip Operational Guide
## Acceptance Procedures for TM-08 & TM-09

**Milestone:** M7 — Module 1.4: Corporate UX Completion & E2E Acceptance Readiness  
**Target Accounts:**  
- **Primary / Sender Account (Account A):** `uzair.shaikh.sec@gmail.com`  
- **Secondary / Recipient Account (Account B):** `uzair.valiacollege@gmail.com`  
**Execution Authority:** Mohammed Uzair Shaikh (Project Owner)  
**Safety Status:** Offline Prepared. Live submission requires explicit owner execution.

---

### 1. Architectural Safety & Cryptographic Pre-Submission Validation (D1)

Before any message can be dispatched via the Gmail SMTP endpoint (`smtp.gmail.com:465` or `:587`), the QuMail client enforces a deterministic sequence of client-side validation rules in accordance with ADR-005, ADR-007, and the QuMail 1.0 Specification:

1. **Mandatory Recipient Key Verification:**  
   Every recipient address listed in `To` or `Cc` is resolved against the active local vault certificate store. If any recipient does not possess a currently trusted certificate, preparation fails immediately (`Failure(Error.POLICY)`).
2. **Strict Quota & Payload Enveloping:**  
   - Recipients: Maximum 3 verified email addresses.
   - Bcc: Explicitly prohibited (Bcc violates end-to-end signed recipient transparency).
   - Plaintext Body: Maximum 8 KiB (8,192 bytes).
   - Attachments: Maximum 4 files, aggregate size strictly capped at 16 KiB (16,384 bytes).
   - Path Traversal Defense: All attachment file names are stripped of path separators and checked against OS-reserved names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`).
3. **Frozen Preparation Before Socket Opening:**  
   The client creates the complete RFC 5322/3156 `multipart/encrypted` OpenPGP payload and persists the exact serialized byte sequence into the SQLite database in state `PREPARED`. Once prepared, the message bytes are **immutable**. Even if network transmission fails or is retried, the byte sequence remains bit-for-bit identical.
4. **Encrypted Sender Archive:**  
   Unless explicitly deselected, every outgoing message includes a sender-encrypted archive copy encrypted to the sender's own root key, enabling future verifiable reference without storing unencrypted drafts.

---

### 2. Operational Semantics & Delivery State Machine (D2)

The application adheres to honest corporate delivery semantics. It never presents misleading "Sent" claims when true delivery is uncertain:

| Backend State | Employee Display Label | Semantic Meaning & Operator Guidance |
|---|---|---|
| `DRAFT` | **Draft** | Plaintext saved in local encrypted database. Not yet encrypted to recipient keys. |
| `PREPARED` | **Ready to send** | Encrypted, signed, and frozen in local database. Ready for SMTP submission. |
| `SUBMITTING` | **Sending securely…** | TLS connection open to `smtp.gmail.com`; XOAUTH2 handshake or payload streaming active. |
| `ACCEPTED` | **Accepted by mail server** | Server returned SMTP `250 OK`. The mail server has queued the message. *(Note: Does not confirm recipient mailbox delivery or client decryption).* |
| `FAILED` | **Not sent** | Transmission failed with terminal error (e.g., authentication rejected, policy block). Safe to retry. |
| `UNKNOWN` | **Delivery uncertain — check Sent folder** | Socket closed, timed out, or connection dropped during/after SMTP `DATA` transmission. **Never automatically retried.** User must manually check Gmail web interface / Sent folder before acknowledging a retry. |

> [!WARNING]
> **No Automatic Retry on UNKNOWN:** Automatic retry of an `UNKNOWN` outbox record could result in duplicate transmissions. The application requires explicit human acknowledgment (`acknowledge_duplicate_risk=True`) before a retry can be initiated.

---

### 3. TM-08: Live Gmail SMTP Submission Acceptance Procedure

This procedure verifies that QuMail can authenticate via Google XOAUTH2, open a secure TLS connection to `smtp.gmail.com`, and submit a prepared encrypted message.

#### Prerequisites
1. Acceptance vault located at `C:\Users\uzx\Desktop\Aavishkar-26\qumail_acceptance_vault.sqlite`.
2. Active Google Client configuration at `C:\Users\uzx\Desktop\Aavishkar-26\client_secret_953431543574-t137vvqsic9jbrddt9dr1t3g5hjkj5p3.apps.googleusercontent.com.json`.
3. Account `uzair.shaikh.sec@gmail.com` successfully enrolled (OAuth tokens present in Credential Manager).

#### Execution Steps (Interactive Desktop Session)

1. Launch QuMail with the explicit `--dev-gmail-submit` flag:
   ```powershell
   & ".\.venv-m1-clean\Scripts\python.exe" main.py `
       --dev-mailbox `
       --dev-vault "C:\Users\uzx\Desktop\Aavishkar-26\qumail_acceptance_vault.sqlite" `
       --google-client "C:\Users\uzx\Desktop\Aavishkar-26\client_secret_953431543574-t137vvqsic9jbrddt9dr1t3g5hjkj5p3.apps.googleusercontent.com.json" `
       --dev-gmail-submit
   ```
2. Verify banner indicates:  
   `🔒️ Gmail submission enabled`
3. Click **"✍️ Compose / outbox"** to open the Secure Compose window.
4. Verify top badge displays: `🔒 End-to-End Encrypted (OpenPGP)`.
5. Enter compose fields:
   - **To:** `uzair.valiacollege@gmail.com`
   - **Subject:** `QuMail Live Acceptance TM-08: Protected Test Submission`
   - **Body:** `This is an automated live acceptance verification email generated by QuMail 1.0 (Module 1.4). Cryptographic payload: OpenPGP / Ed25519.`
6. Click **"🚀 Send Securely"**.
7. Confirm the security prompt:  
   `"Encrypt with verified recipient keys and send to: uzair.valiacollege@gmail.com. Proceed with transmission?"` -> Click **Yes**.
8. Observe Status Bar:
   - Transitions to: `Working…`
   - Then: `Protected email sent! State: Accepted by mail server (smtp_accepted_by_gmail).`
9. In Outbox table, verify:
   - State column displays: `Accepted by mail server`
   - Attempts: `1`
   - Details: `smtp_accepted_by_gmail`

---

### 4. TM-09: Complete Encrypted Email Round-Trip Acceptance Procedure

This procedure verifies the complete bidirectional cycle:
1. Message prepared and sent from Account A (`uzair.shaikh.sec@gmail.com`).
2. Message retrieved from Gmail IMAP on Account B (`uzair.valiacollege@gmail.com`) using read-only PEEK.
3. Message parsed, classified as `multipart/encrypted`, verified against sender root key, and decrypted.

#### Execution Steps

1. **Step 1: Outbound Submission (Account A)**  
   Execute TM-08 as described above addressed to `uzair.valiacollege@gmail.com`.
2. **Step 2: Account B Enrollment / Session Switch**  
   - In QuMail Settings (`⚙️ Settings`), enroll `uzair.valiacollege@gmail.com` using the Google OAuth flow.
   - Switch active account dropdown to `uzair.valiacollege@gmail.com`.
3. **Step 3: IMAP Header Retrieval**  
   - Click **"🔄 Refresh headers"**.
   - Verify header appears in message list:  
     `From: uzair.shaikh.sec@gmail.com | Subject: QuMail Live Acceptance TM-08... | Date: <Current>`
4. **Step 4: Message Opening & Inbound Verification**  
   - Double-click the message or select row and click **"📖 Open selected"**.
   - Client executes IMAP `BODY.PEEK[]` over TLS (preserving unread flag on server).
   - Inbound parser classifies payload as RFC 3156 `multipart/encrypted`.
   - Security verification panel renders:
     - `🔒 End-to-End Encrypted (OpenPGP)`
     - `Verified Sender: uzair.shaikh.sec@gmail.com`
     - `Cryptographic signature valid`
   - Message content pane displays decrypted body text.
5. **Step 5: Acceptance Record**  
   Record timestamps, message IDs, and outbox operation IDs for acceptance sign-off.
