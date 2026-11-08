# QuMail — Live Gmail SMTP & End-to-End Round-Trip Operational Guide
## Standard Operating Procedures for TM-07, TM-08 & TM-09

**Milestone:** M7 — Module 1.5 Live Acceptance Readiness  
**Working Branch:** `codex/m7-security-roundtrip`  
**Target Accounts:**  
- **Primary / Sender Account (Account A):** `uzair.shaikh.sec@gmail.com`  
- **Secondary / Recipient Account (Account B):** `uzair.valiacollege@gmail.com`  
**Live Execution Authority:** Mohammed Uzair Shaikh (Project Owner)  
**Safety Status:** Offline Prepared. Live submission requires explicit owner execution.

---

### 1. Cryptographic Pre-Submission Validation Rules (D1)

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

### 3. TM-07: Retrieve and Decrypt Protected Message Procedure

This test verifies that QuMail can retrieve an authentic RFC 3156 `multipart/encrypted` OpenPGP message from Gmail IMAP over TLS using read-only PEEK, verify the sender's Ed25519 signature against the local vault, and decrypt the payload locally.

1. **Preconditions:**  
   - Vault unlocked with active recipient identity (`uzair.valiacollege@gmail.com`).
   - Sender public key (`uzair.shaikh.sec@gmail.com`) pinned in recipient's contact store.
   - At least one valid protected message exists in the Gmail Inbox.
2. **Exact User Action:**  
   - In Mailbox window, click **"🔄 Refresh headers"**.
   - Select the target protected message row in the table.
   - Double-click or click **"📖 Open selected"**.
3. **Expected Result:**  
   - IMAP `BODY.PEEK[]` fetches message wire bytes over TLS without clearing the `\Seen` flag on Gmail.
   - Reader renders message subject and plaintext body.
   - Security panel displays: `🔒 End-to-End Encrypted (OpenPGP) · Verified Sender: uzair.shaikh.sec@gmail.com · Valid signature`.
   - Any attachments are listed in the attachment selector with valid byte sizes.
4. **Failure Conditions:**  
   - Network timeout or TLS handshake failure.
   - Unknown sender certificate (`Failure(Error.POLICY)`): Displays clear guidance to import certificate in Settings.
   - Corrupted ciphertext or tampered payload: Fails closed without releasing unverified plaintext.
5. **Evidence to Capture:**  
   - Screen capture of opened message with security verification panel.
   - Message UID and Date header.
   - Console/log verification showing PEEK query.
6. **Rollback or Safe-Stop Procedure:**  
   - Click **"⏹️ Cancel"** to stop pending socket worker.
   - PEEK ensures Gmail mailbox state is unaltered; no server rollback needed.
7. **Authorization Required:**  
   - Explicit Project Owner approval to fetch message bodies from `uzair.valiacollege@gmail.com`.

---

### 4. TM-08: Live Gmail SMTP Submission Acceptance Procedure

This test verifies that QuMail can authenticate via Google XOAUTH2, open a secure TLS connection to `smtp.gmail.com`, and submit a prepared encrypted message.

1. **Preconditions:**  
   - Acceptance vault located at `C:\Users\uzx\Desktop\Aavishkar-26\qumail_acceptance_vault.sqlite`.
   - Active Google Client configuration at `C:\Users\uzx\Desktop\Aavishkar-26\client_secret_953431543574-t137vvqsic9jbrddt9dr1t3g5hjkj5p3.apps.googleusercontent.com.json`.
   - Sender account `uzair.shaikh.sec@gmail.com` successfully enrolled.
   - Recipient `uzair.valiacollege@gmail.com` certificate pinned.
2. **Exact User Action:**  
   - Launch QuMail with `--dev-gmail-submit`:
     ```powershell
     & ".\.venv-m1-clean\Scripts\python.exe" main.py `
         --dev-mailbox `
         --dev-vault "C:\Users\uzx\Desktop\Aavishkar-26\qumail_acceptance_vault.sqlite" `
         --google-client "C:\Users\uzx\Desktop\Aavishkar-26\client_secret_953431543574-t137vvqsic9jbrddt9dr1t3g5hjkj5p3.apps.googleusercontent.com.json" `
         --dev-gmail-submit
     ```
   - Click **"✍️ Compose / outbox"**.
   - Enter: To: `uzair.valiacollege@gmail.com`, Subject: `QuMail Live Acceptance TM-08: Protected Test Submission`, Body: `Automated live acceptance verification email generated by QuMail 1.0. Cryptographic payload: OpenPGP / Ed25519.`
   - Click **"🚀 Send Securely"** and confirm dialog.
3. **Expected Result:**  
   - Status bar transitions: `Working…` -> `Protected email sent! State: Accepted by mail server (smtp_accepted_by_gmail).`
   - Security badge displays: `✅ Accepted by Mail Server (Transit En Route)`.
   - Outbox table displays: `Accepted by mail server` with `attempt: 1`.
   - Draft editor is safely cleared.
4. **Failure Conditions:**  
   - Auth rejection: Status indicates `Google authorization failed or expired`.
   - Socket drop during DATA: Transitions to `UNKNOWN` (`Delivery uncertain — check Sent folder`). No automatic retry occurs.
   - Server rejection (SMTP 5xx): Transitions to `FAILED` (`Not sent`). User's text is preserved in editor.
5. **Evidence to Capture:**  
   - Screenshot of Outbox row showing `Accepted by mail server` with operation digest.
   - Gmail Web interface confirmation showing received message in Sent folder with `multipart/encrypted` content type.
6. **Rollback or Safe-Stop Procedure:**  
   - If submission fails, message is frozen in SQLite. Discarding can be executed via "Discard / cancel saved".
   - Cancellation cannot recall mail once SMTP returns `250 OK`.
7. **Authorization Required:**  
   - Explicit Project Owner approval to transmit external SMTP email over the public network.

---

### 5. TM-09: Complete Encrypted Email Round-Trip Acceptance Procedure

This test verifies the complete end-to-end bidirectional cycle between two authentic accounts.

1. **Preconditions:**  
   - Both Account A (`uzair.shaikh.sec@gmail.com`) and Account B (`uzair.valiacollege@gmail.com`) are enrolled in QuMail.
   - Public certificates are mutually pinned.
2. **Exact User Action:**  
   - **Phase 1 (Account A):** Execute TM-08 outbound submission addressed to Account B.
   - **Phase 2 (Account B):** Switch active account dropdown to `uzair.valiacollege@gmail.com`.
   - Click **"🔄 Refresh headers"**.
   - Double-click the incoming message header.
3. **Expected Result:**  
   - Outbound message arrives in Account B Inbox.
   - IMAP read successfully retrieves and classifies message as OpenPGP `multipart/encrypted`.
   - Message is decrypted locally with Account B private key.
   - Sender signature verified against Account A pinned root.
   - Body and attachments match the exact outbound submission.
4. **Failure Conditions:**  
   - Delay in Google MTA delivery (wait 30–60 seconds and refresh).
   - Key mismatch: Decryption fails with provider error.
5. **Evidence to Capture:**  
   - Outbox Accepted receipt from Account A.
   - Inbound decrypted view from Account B showing verified security badge.
   - Message-ID and RFC 5322 header alignment.
6. **Rollback or Safe-Stop Procedure:**  
   - Safe stop by locking session (`🔒 Lock`). No state corruption possible.
7. **Authorization Required:**  
   - Explicit Project Owner approval for full end-to-end multi-account transmission.
