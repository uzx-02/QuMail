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

This test verifies that QuMail can retrieve an authentic RFC 3156 `multipart/encrypted` OpenPGP message from Gmail IMAP over TLS using read-only PEEK, verify the sender's Ed25519 signature against the local vault, decrypt the payload locally, and render the verified content safely.

1. **Exact Prerequisites:**  
   - Acceptance Vault: `C:\Users\uzx\Desktop\Aavishkar-26\qumail_acceptance_vault.sqlite` exists and is unlocked.
   - Client Secrets: `C:\Users\uzx\Desktop\Aavishkar-26\client_secret_953431543574-t137vvqsic9jbrddt9dr1t3g5hjkj5p3.apps.googleusercontent.com.json` is configured.
   - Recipient Account: `uzair.valiacollege@gmail.com` (Account B) is enrolled with active private key in vault.
   - Sender Trust Pinning: The public certificate of `uzair.shaikh.sec@gmail.com` (Account A) is pinned in Account B's contact store.
   - Authorized Message Fixture: Exactly one authentic protected test message exists in the Inbox of `uzair.valiacollege@gmail.com`.

2. **Precise Mailbox & Account Boundaries:**  
   - **Active Reading Account:** `uzair.valiacollege@gmail.com` (Account B) ONLY.
   - **Expected Authenticated Sender:** `uzair.shaikh.sec@gmail.com` (Account A).
   - **Target IMAP Folder:** `INBOX`.
   - **Strict Mailbox Isolation:** Under no circumstances may any message other than the designated test fixture be opened, fetched, or inspected.

3. **Message Provenance Documentation:**  
   The test fixture must have a verifiable, documented origin:
   - **Author / Sender Identity:** Generated and signed exclusively by Account A (`uzair.shaikh.sec@gmail.com`) using its active Ed25519 signing key.
   - **Ingestion Pathway:**
     - *Primary Pathway (TM-08 $\rightarrow$ TM-07 Sequence):* The message was composed in QuMail by Account A, prepared via M5 OpenPGP provider, encrypted to Account B's public key, and transmitted to `smtp.gmail.com` via live TM-08 submission.
     - *Alternative Pathway (Controlled Pre-Staged Injection):* The message was constructed using the QuMail native pipeline (`experiments/m5/services.py:Compose`) with authentic Account A keys and delivered to Account B's mailbox through a verified MTA channel.
   - **Payload Invariants:** The body contains known, benign acceptance text and an optional known test attachment; zero sensitive personal data.

4. **Mandatory Exact-Fixture Identification Step (Singleton Enforcement):**  
   The sender-plus-subject-prefix rule is strictly an initial filter. Before fetching any message body, the operator must verify all six identification criteria against the header list:

   | Fixture Identification Parameter | Expected Exact Value | Source / Verification Method |
   |---|---|---|
   | **Target Account** | `uzair.valiacollege@gmail.com` | Active account selector in UI |
   | **Target IMAP Folder** | `INBOX` | Active folder context |
   | **Expected Sender** | `uzair.shaikh.sec@gmail.com` | Message table `From` column |
   | **Exact Subject** | `[QuMail-TM07-Acceptance] Confidential Q7 Architecture Proposal` | Operator-specified exact subject string |
   | **RFC 5322 Message-ID** | `[OPERATOR-SUPPLIED PREREQUISITE AT LIVE RUN]` | Recorded from outbound TM-08 receipt or web header |
   | **IMAP Message UID** | `[OPERATOR-SUPPLIED PREREQUISITE UPON REFRESH]` | Recorded from IMAP header fetch table row |

   > [!CRITICAL]
   > **The Singleton Rule (Mandatory Stop Condition):**
   > Filtering the inbox headers by the exact subject and sender **must yield EXACTLY ONE matching candidate row**.
   > - **If Zero candidates match:** **STOP.** The expected fixture has not yet arrived or has not synced. Do not guess or select another email.
   > - **If Multiple candidates match:** **STOP.** Multiple test runs or duplicate subjects create ambiguity. The operator must inspect the candidate Message-IDs and supply the exact IMAP UID to disambiguate before opening.
   > - **Only when exactly one candidate matches:** The operator is authorized to proceed with opening the message.

5. **`BODY.PEEK[]` Wire Semantics & Privacy Protection:**  
   - **Read-Only Server State:** IMAP `UID FETCH <uid> (BODY.PEEK[])` guarantees that Gmail's remote `\Seen` flag remains unmodified. The message remains unread on the Gmail server.
   - **Full Wire Transmission Reality:** Although read-only on the server, `BODY.PEEK[]` **transmits the entire raw RFC 5322 message body and all attachment bytes over the TLS socket** into QuMail's memory. It is **not** a metadata-only query.
   - **Privacy Imperative:** Because `BODY.PEEK[]` retrieves full message contents, opening an unintended row would stream unauthorized private correspondence over the network. The singleton candidate check (Step 4) is a mandatory safety barrier preventing inspection of unrelated messages.

6. **Sequential Execution Pipeline & Architectural Distinctions:**  
   QuMail enforces four distinct, decoupled stages. Each stage must pass independently before the next begins:
   - **Stage 1 — IMAP Retrieval:** Executes `UID FETCH <uid> (BODY.PEEK[])` over TLS to `imap.gmail.com:993`. Confirms successful socket transmission of wire bytes.
   - **Stage 2 — MIME Parsing & Armor Extraction:** The raw bytes are parsed by `experiments/m5/mime.py`. It confirms `Kind.MODERN` classification, parses outer headers, extracts the OpenPGP ASCII armor block, and verifies that outer MIME boundaries are intact.
   - **Stage 3 — Cryptographic Decryption & Signature Verification:**  
     - Invokes native Rust provider `qumail-m5-provider.exe` (`decrypt_and_verify`).
     - Decrypts ciphertext using Account B's private key (`key_handle`).
     - Verifies sender Ed25519 signature against Account A's pinned certificate (`data['contacts']['uzair.shaikh.sec@gmail.com']['public']`).
     - Verifies inner MIME headers: authenticated inner sender address matches the certificate identity (`sender in signer['addresses']`).
     - Verifies recipient address: Account B address appears in inner `draft.to` or `draft.cc`.
     - Replay check: Computes SHA-256 digest of decrypted inner payload and checks SQLite `m5_seen_v1` store (`Replay.FRESH`).
   - **Stage 4 — User-Visible GUI Rendering:**  
     - Renders decrypted subject and body in the reading pane.
     - Displays truthful verified security badge with sender identity and signature status.
     - Populates attachment selector with verified filenames and byte lengths.

7. **Expected UI Result:**  
   - **Status Bar:** `Signature valid; identity: Trusted Contact; replay: Fresh; outer mismatches: none; archive: False`.
   - **Reading Pane:** Decrypted plain text displayed clearly without cryptographic escape characters.
   - **Security Badge:** Green shield indicator: `🔒 End-to-End Encrypted (OpenPGP) · Verified Sender: uzair.shaikh.sec@gmail.com · Valid signature`.
   - **Attachment Area:** Attachment listed with matching byte size (if attached).

8. **Failure & Stop Conditions:**  
   - **Network Timeout / IMAP Connection Loss:** Worker terminates cleanly; UI displays network retry status; mailbox state is unaltered.
   - **Untrusted Sender Certificate (`Failure(Code.SIGNER)`):** If sender key is missing or unpinned, QuMail **stops immediately and fails closed**. No ciphertext is decrypted, and no unverified plaintext is released.
   - **Corrupted Armor / Tampered Ciphertext (`SecurityFailure`):** If ciphertext bits are flipped, decryption aborts with cryptographic error. Zero plaintext released.
   - **Signature Verification Failure (`Failure(Code.PROVIDER)`):** If signature does not match sender certificate, verification fails closed.
   - **Replay Conflict (`Replay.CONFLICT`):** Message ID matches previously seen message with different payload digest; flags potential replay attack.

9. **Privacy-Preserving Evidence Collection:**  
   - **Masking Mandatory:** When capturing screenshots of the mailbox view, the operator MUST crop or mask all unrelated inbox message rows (personal, institutional, or third-party emails).
   - **No Credential Exposure:** Screenshots, screen recordings, and log outputs must NEVER display OAuth access tokens, refresh tokens, client secrets, or private key material.
   - **Required Artifacts:**
     1. Cropped screenshot of the reading pane showing the decrypted `[QuMail-TM07-Acceptance]` body and green verified security badge.
     2. Verification of message UID and Date header from log output.
     3. Console log snippet confirming IMAP read-only `BODY.PEEK[]` command.

10. **Rollback & Safe-Stop Procedure:**  
    - In-flight retrieval can be stopped cleanly by clicking **"⏹️ Cancel"**.
    - Because `BODY.PEEK[]` is strictly read-only, Gmail server state is unchanged. No remote rollback or flag reset is required.

11. **Authorization Required:**  
    - **STOP:** Execution of TM-07 is NOT authorized by this milestone audit.
    - Requires explicit, separate authorization from the Project Owner (Mohammed Uzair Shaikh) before any live IMAP fetch of message bodies is initiated.

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
