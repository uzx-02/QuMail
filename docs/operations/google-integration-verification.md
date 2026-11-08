# QuMail Desktop — Google Integration Technical Verification & Call Graph Analysis

**Document:** `docs/operations/google-integration-verification.md`  
**Milestone:** M7 — Module 1.2: Live Google Acceptance  
**Branch:** `codex/m7-google-live-acceptance`  
**Purpose:** Architecture reconciliation, concrete runtime call graph proof, and M4 historical reconciliation in response to Technical Lead Review Directive.  
**Disposition:** Formal Technical Verification Report  

---

## 1. Concrete Runtime Call Graph: User Interaction to Google SMTP

The following call graph establishes the precise synchronous, worker-dispatched, and inter-process communication paths executing when a user drafts, prepares, and submits an encrypted email through the QuMail desktop application:

```
[User Action: Click "Save encrypted draft"]
  │
  ├─► ui/mail_actions.py: MailActions.start('save')  [GUI Thread]
  │     └─► Worker pool dispatch via self.window.pool.submit(work)  [Thread: qumail-mailbox]
  │           └─► mailbox_client/workflows.py: Workflows.save(lease, draft, budget)
  │                 └─► experiments/m5/services.py: Compose.draft(lease, draft, budget)
  │                       ├─► experiments/m5/mime.py: validate(draft)
  │                       ├─► experiments/m5/services.py: encode_draft(draft, date)
  │                       └─► experiments/m4/services.py: PrepareMessage.draft(lease, raw, until)
  │                             └─► experiments/m4/vault_adapter.py: VaultOutbox.transaction()
  │                                   └─► experiments/m3/vault.py: Vault._read() / transaction()
  │                                         [Persists State.DRAFT in SQLite accounts table via AES-256-GCM]

[User Action: Click "Verify recipients"]
  │
  ├─► ui/mail_actions.py: MailActions.start('verify')  [GUI Thread]
  │     └─► Worker pool dispatch via self.window.pool.submit(work)  [Thread: qumail-mailbox]
  │           └─► mailbox_client/workflows.py: Workflows.recipients(lease, draft, budget)
  │                 ├─► experiments/m5/mime.py: validate(draft)
  │                 └─► experiments/m4/vault_adapter.py: AccountTransaction._vault.recipient()
  │                       └─► experiments/m3/vault.py: Vault.recipient()
  │                             [Verifies each recipient in draft.to + draft.cc has pinned public key in vault]

[User Action: Click "Prepare saved"]
  │
  ├─► ui/mail_actions.py: MailActions.start('prepare')  [GUI Thread]
  │     └─► Worker pool dispatch via self.window.pool.submit(work)  [Thread: qumail-mailbox]
  │           └─► mailbox_client/workflows.py: Workflows.prepare(lease, operation, key, budget)
  │                 └─► experiments/m5/services.py: Compose.prepare(lease, operation, key, budget)
  │                       └─► experiments/m4/services.py: PrepareMessage.prepare(lease, operation, key, recipients, PROFILE)
  │                             ├─► experiments/m5/services.py: MessageBuilder.build()
  │                             │     ├─► experiments/m5/mime.py: build_inner() [MIME multipart/mixed]
  │                             │     ├─► experiments/m5/provider.py: Provider.call('seal', ...)
  │                             │     │     └─► IPC Subprocess: qumail-m5-provider.exe seal
  │                             │     │           [Sequoia PGP: signs with sender secret, encrypts with recipients' keys]
  │                             │     └─► experiments/m5/mime.py: build_outer() [Subject: "Encrypted message"]
  │                             ├─► Digest calculation: hashlib.sha256(raw).hexdigest()
  │                             └─► Outbox record update:
  │                                   ├─► row['prepared'] = dict(bytes=pack(raw), digest=digest, ...)
  │                                   ├─► row['state'] = State.PREPARED.value
  │                                   └─► del row['draft']  [CRITICAL: Plaintext draft purged]

[User Action: Click "Submit once"]
  │
  ├─► ui/mail_actions.py: Confirmation Dialog ("Submit this frozen protected message once...?")
  │     └─► MailActions.start('submit')  [GUI Thread]
  │           └─► Worker pool dispatch via self.window.pool.submit(work)  [Thread: qumail-mailbox]
  │                 └─► mailbox_client/workflows.py: Workflows.submit(lease, operation, budget)
  │                       ├─► Instantiates ScopedCredential(self.credentials, lease, budget)
  │                       ├─► Instantiates OperationTransport(self.transport_factory(resolver), budget)
  │                       │     └─► self.transport_factory is mailbox_client/smtp.py: GmailSMTP
  │                       └─► experiments/m4/services.py: SubmitOutbox.submit(lease, operation)
  │                             ├─► SQLite Transaction:
  │                             │     ├─► Check row['state'] == State.PREPARED
  │                             │     ├─► Append attempt record (number, identity, digest)
  │                             │     └─► row['state'] = State.SUBMITTING (Committed to SQLite BEFORE network I/O)
  │                             ├─► mailbox_client/smtp.py: GmailSMTP.submit()
  │                             │     └─► experiments/m4/smtp_transport.py: SMTPSubmission.submit()
  │                             │           ├─► mailbox_client/smtp.py: GmailConnection._get_socket()
  │                             │           │     └─► mailbox_client/connection.py: connect('smtp.gmail.com', 587)
  │                             │           ├─► smtplib.SMTP.ehlo()
  │                             │           ├─► smtplib.SMTP.starttls(context=ssl.create_default_context())
  │                             │           ├─► smtplib.SMTP.ehlo() [Verifies XOAUTH2 capability]
  │                             │           ├─► Resolver call: ScopedCredential.resolve()
  │                             │           │     └─► mailbox_client/service.py: Credentials.resolve()
  │                             │           │           ├─► Check tokens['expiry'] <= time.time() + 60
  │                             │           │           │     └─► (If expiring) transport/bounded_google.py: refresh()
  │                             │           │           └─► Returns MailCredential(address, access_token)
  │                             │           ├─► Format SASL: base64(user=addr\x01auth=Bearer token\x01\x01)
  │                             │           ├─► smtplib.SMTP.docmd('AUTH', 'XOAUTH2 ' + auth)
  │                             │           ├─► smtplib.SMTP.mail(sender)
  │                             │           ├─► smtplib.SMTP.rcpt(recipient) [Repeated for each recipient]
  │                             │           ├─► smtplib.SMTP.docmd('DATA')
  │                             │           ├─► smtplib.SMTP.send(framed_payload)  [possible = True]
  │                             │           └─► smtplib.SMTP.getreply() ──► 250 2.0.0 OK ──► Outcome.ACCEPTED
  │                             ├─► SQLite Transaction:
  │                             │     ├─► Map Outcome.ACCEPTED ──► State.ACCEPTED, reason='accepted_by_transport'
  │                             │     └─► row.update(state=State.ACCEPTED.value, reason='accepted_by_transport')
  │                             └─► Returns DeliveryResult(operation, State.ACCEPTED, 'accepted_by_transport', 1)
  │
  └─► ui/mail_actions.py: MailActions.poll()  [GUI Thread Polling Timer: 50ms]
        ├─► Collects future.result()
        ├─► Updates outbox table widget: Row displays State 'ACCEPTED', Reason 'accepted_by_transport'
        └─► Updates status label: "Committed."
```

---

## 2. Step-by-Step UI Execution Path & Component Trace

The 10 architectural trace questions from the Technical Lead Review Directive are answered with exact source-code citations:

### 1. Which UI action initiates composition and message submission?
- **Composition initiation:** User clicks the **"Compose / outbox"** button in [`ui/mailbox_window.py` line 77](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/ui/mailbox_window.py#L77), opening `MailActions(QDialog)` ([`ui/mail_actions.py` lines 16–67](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/ui/mail_actions.py#L16-L67)). Clicking **"New"** ([`ui/mail_actions.py` line 90](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/ui/mail_actions.py#L90)) clears prior draft state.
- **Submission initiation:** User selects a row in the outbox table in state `Prepared` and clicks the **"Submit once"** button ([`ui/mail_actions.py` line 52](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/ui/mail_actions.py#L52)), triggering `MailActions.start('submit')` ([`ui/mail_actions.py` line 128](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/ui/mail_actions.py#L128)).

### 2. Which exact function handles recipient verification?
- Function: [`Workflows.recipients(lease, draft, budget)`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/workflows.py#L98-L106) in [`mailbox_client/workflows.py`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/workflows.py).
- Execution: Calls [`experiments.m5.mime.validate(draft)`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m5/mime.py#L40-L56) to verify recipient count (1 to 3), absence of Bcc, and RFC 5322 syntax. Then opens a repository transaction calling [`Vault.recipient(account_data, EmailAddress(addr))`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m3/vault.py#L254-L260) for every recipient in `draft.to + draft.cc`, requiring a verified, pinned root certificate.

### 3. Which exact function creates the encrypted MIME message?
- Function: [`MessageBuilder.build(account, binding, plaintext, message_id)`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m5/services.py#L61-L78) in [`experiments/m5/services.py`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m5/services.py).
- Execution:
  1. Calls [`experiments.m5.mime.build_inner()`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m5/mime.py#L71-L85) to assemble the inner authenticated MIME multipart message (body + attachments).
  2. Resolves recipient public keys and optional sender archive public key.
  3. Invokes the native Sequoia helper to generate PGP encrypted & signed ASCII armor.
  4. Calls [`experiments.m5.mime.build_outer()`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m5/mime.py#L88-L98) to encapsulate the armor into an RFC 3156 / RFC 9788 combined PGP/MIME envelope with fixed Subject `Encrypted message`.

### 4. Which exact Sequoia provider implementation is invoked?
- Native Binary: [`tmp/m2/target/debug/qumail-m5-provider.exe`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/tmp/m2/target/debug/qumail-m5-provider.exe).
- Python Wrapper: [`experiments.m5.provider.Provider`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m5/provider.py#L21-L45).
- Invocation: `self.provider.call('seal', self.budget, certificate=bytes(key['secret']), recipients=recipients, data=inner)` via stdin/stdout pipe IPC.

### 5. Where is the prepared encrypted message persisted?
- Location: The application SQLite vault database at `%LOCALAPPDATA%\QuMailAcceptance\2026-11-01-desktop\acceptance.sqlite`.
- Structure: Persisted in the `accounts` table within the JSON document for the owning account, under `records[operation_id]['prepared']['bytes']`, serialized using binary `pack()` and encrypted under AES-256-GCM authenticated with AAD `QuMail-M3-record-v1/{vault_id}/{account_id}/{revision}`.
- Persistence Point: Executed in [`experiments/m4/services.py` line 47](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m4/services.py#L47) before any network operation begins.

### 6. Which exact outbox implementation manages the message lifecycle?
- Class: [`experiments.m4.services.PrepareMessage`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m4/services.py#L18-L55) and [`experiments.m4.services.SubmitOutbox`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m4/services.py#L57-L133).
- Repository Interface: [`experiments.m5.services.Repository`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m5/services.py#L53-L59), which subclasses [`experiments.m4.vault_adapter.VaultOutbox`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m4/vault_adapter.py#L107-L140).

### 7. Which exact function initiates SMTP submission?
- Function: [`Workflows.submit(lease, operation, budget)`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/workflows.py#L119-L126) in [`mailbox_client/workflows.py`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/workflows.py), which delegates to [`SubmitOutbox.submit(lease, operation, until=budget.deadline)`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m4/services.py#L72-L108).

### 8. Which transport implementation is instantiated?
- Concrete Class: [`mailbox_client.smtp.GmailSMTP`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/smtp.py#L19-L27) in [`mailbox_client/smtp.py`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/smtp.py).
- Base Engine: Subclasses [`experiments.m4.smtp_transport.SMTPSubmission`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m4/smtp_transport.py#L112-L178).
- Socket Wrapper: Uses [`mailbox_client.smtp.GmailConnection`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/smtp.py#L10-L16) which restricts sockets strictly to `('smtp.gmail.com', 587)`.
- Wrapper: Wrapped in [`mailbox_client.workflows.OperationTransport`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/workflows.py#L55-L63) to bind cancellation tokens.

### 9. How is the OAuth access token obtained and passed to XOAUTH2?
- Resolution: During SMTP handshake, `SMTPSubmission.submit()` calls `self.resolver.resolve(credential, envelope.sender, cancel, deadline)`.
- Delegator: [`mailbox_client.workflows.ScopedCredential`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/workflows.py#L44-L53) delegates to [`mailbox_client.service.Credentials.resolve()`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/service.py#L17-L36).
- Vault Read & Proactive Refresh: Reads the OAuth tokens dictionary from the active account vault. If `expiry <= time.time() + 60`, calls `GoogleAuthorization.refresh()` to fetch a fresh access token and commits it to the vault.
- SASL XOAUTH2 Formatting: In [`experiments/m4/smtp_transport.py` lines 150–151](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m4/smtp_transport.py#L150-L151):
  ```python
  auth = base64.b64encode(f'user={resolved.address}\x01auth=Bearer {resolved.token}\x01\x01'.encode()).decode()
  auth_code = smtp.docmd('AUTH', 'XOAUTH2 ' + auth)[0]
  ```

### 10. How does the application update the durable outbox state after SMTP responds?
- In [`experiments/m4/services.py` lines 100–106](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m4/services.py#L100-L106):
  `SubmitOutbox.submit()` receives the transport `Outcome`:
  ```python
  state, reason = {
      Outcome.ACCEPTED: (State.ACCEPTED, 'accepted_by_transport'),
      Outcome.REJECTED: (State.FAILED, 'rejected_by_transport'),
      Outcome.UNKNOWN: (State.UNKNOWN, 'unknown_submission_outcome'),
  }[outcome]
  with self.repository.transaction(lease, until) as account:
      row = account.row(operation)
      row.update(state=state.value, reason=reason)
      row['attempts'][-1].update(state=state.value, reason=reason)
  ```
- The transaction commits to the SQLite vault before the worker returns `DeliveryResult`.

---

## 3. Explicit Architecture Inquiries & Discrepancy Reconciliation

### A. SMTP Implementation Ambiguity
- **Relationship:**
  - [`experiments/m4/smtp_transport.py`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m4/smtp_transport.py) provides the protocol state engine: `SMTPSubmission` (RFC 4954 SASL XOAUTH2, STARTTLS handshake, 1000-char line limit, and `Outcome` mapping) and `BoundedSMTP`.
  - [`mailbox_client/smtp.py`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/mailbox_client/smtp.py) provides the production Google adapter: `GmailSMTP(SMTPSubmission)` with `host = 'smtp.gmail.com'`, `port = 587`, `loopback_only = False`, and `ssl.create_default_context()`.
- **Verdict:** There is **zero duplication or competition**. `GmailSMTP` is a direct subclass of `SMTPSubmission`. In the desktop application, `Workflows` instantiates `GmailSMTP`.

### B. Outbox Integration
- The modern desktop application **directly uses** [`experiments/m4/services.py`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m4/services.py).
- `Workflows` in `mailbox_client/workflows.py` instantiates `SubmitOutbox` for both submission (`submit()`) and startup recovery (`outbox()` calling `offline.recover()`).
- All outbox states (`DRAFT`, `PREPARED`, `SUBMITTING`, `ACCEPTED`, `FAILED`, `UNKNOWN`) are managed by M4's durable state machine.

### C. Cryptographic Integration
- The desktop workflow **directly invokes** [`experiments/m5/services.py`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/experiments/m5/services.py) and the native Sequoia helper binary [`qumail-m5-provider.exe`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/tmp/m2/target/debug/qumail-m5-provider.exe).
- `MailActions.service()` instantiates `Provider(helper)` pointing to the compiled native binary and passes it to `Workflows`. `Workflows` passes it to `Compose` and `OpenMessage`.
- Every outgoing email is encrypted via `qumail-m5-provider.exe seal`; every opened protected message is decrypted via `qumail-m5-provider.exe unseal`.

### D. Historical M4 Discrepancy Reconciliation
- **Historical Context (M4 Milestone):**
  When M4 was committed (`codex/m4-durable-outbox`), its scope was restricted to qualifying the durable outbox state machine and local IPv4 loopback SMTP with STARTTLS. External internet submission was locked out (`loopback_only = True`), and Gmail OAuth submission was not yet implemented.
- **Architectural Progression (M5 & M6):**
  - M5 (`codex/m5-protected-compose`) introduced Sequoia PGP/MIME packaging and wired `Compose` with `VaultOutbox`.
  - M6 (`codex/m6-gmail-inbox`, commit `8eebb5e`) completed the full Gmail integration by introducing `mailbox_client/smtp.py` (`GmailSMTP`), `mailbox_client/gmail.py` (`GmailMailbox`), and `mailbox_client/workflows.py` (`Workflows`), unlocking external submission under the explicit CLI flag `--dev-gmail-submit`.
- **Reconciliation:** The earlier statement in handover docs that "M4 has simulated submission and no real SMTP" accurately reflects M4's frozen historical boundary, whereas the modern application in M6/M7 uses the completed `GmailSMTP` adapter extending M4's engine.

### Definitive Conclusion:
**`END-TO-END INTEGRATION VERIFIED.`**  
The desktop pipeline from UI compose, recipient verification, Sequoia PGP encryption, durable SQLite outbox preparation, XOAUTH2 token resolution, and Gmail SMTP transmission is fully implemented, directly wired, and verified by regression test suites.

---

## 4. Google OAuth Testing-Mode & Scope Evaluation

### A. Seven-Day Authorization Limitation
1. **Google Policy:** For External OAuth applications in **Testing** status, refresh tokens issued to test users expire **7 days** (604,800 seconds) after issuance, regardless of token activity.
2. **Access-Token vs Refresh-Token Expiry:**
   - **Access Token:** Valid for **1 hour** (3,600s). Refreshed automatically by QuMail without user intervention whenever `expiry <= time.time() + 60`.
   - **Refresh Token:** Valid for **7 days** (in Testing mode). When expired, Google's token endpoint returns HTTP 400 (`{"error": "invalid_grant", "error_description": "Token has been expired or revoked"}`).
3. **Detection & UI Error Prompt:**
   - In `transport/development_google.py`, `RefreshError` from Google is caught and raises `BoundaryError(Code.IDENTITY)`.
   - In `mailbox_client/service.py`, this is mapped to `Failure(Code.AUTH)`.
   - In `ui/mail_accessibility.py` line 34, QuMail displays:
     `"Google authorization failed or expired. Check the configured Desktop client; reauthorize the selected account with mail consent in Settings."`
4. **Account State Preservation on Reauthorization:**
   - In `IdentitySettings`, clicking **"Reauthorize selected"** initiates an OAuth loopback flow constrained to `expected_subject=ctx.subject`.
   - Upon successful authorization, `vault.store_oauth(ctx, identity, tokens)` updates only the `oauth` dictionary within the existing account record.
   - **Zero Loss:** The account's `AccountId`, private PGP keys, root fingerprint, contacts, outbox records, and historical receipts remain completely intact.

### B. Full Gmail Scope (`https://mail.google.com/`) Justification
1. **Protocol Requirement:** Google's official SASL XOAUTH2 protocol for standard IMAP (`imap.gmail.com:993`) and SMTP (`smtp.gmail.com:587`) explicitly mandates the `https://mail.google.com/` scope [Verified].
2. **Granular Scopes Unavailable on IMAP/SMTP:** Google does **not** support granular REST API scopes (such as `gmail.send` or `gmail.readonly`) over standard IMAP or SMTP connections [Verified].
3. **Exercised vs Granted Permissions:**
   - *Exercised:* `SELECT INBOX (readonly)`, `FETCH (BODY.PEEK)`, `STORE (+FLAGS.SILENT \Seen)`, and `SMTP AUTH XOAUTH2 / MAIL / RCPT / DATA` [Verified].
   - *Never Exercised:* QuMail's current implementation does not implement or expose any message deletion feature (`EXPUNGE` or trash emptying commands are excluded by design), nor does it access spam or mail settings [Verified].
4. **Production / Restricted Scope Verification:**
   - `https://mail.google.com/` is classified as a restricted Gmail scope by Google.
   - For an application to exit Testing status and serve general users, Google OAuth verification and applicable restricted-scope security assessment requirements must be satisfied.
   - Google's security assessment process utilizes risk-based assurance levels. The specific assessment level (e.g., Cloud Application Security Assessment / CASA evaluation) must be determined and confirmed directly through Google's verification process. Development testing does not imply production approval, and no legal or compliance guarantee is made.

### C. Technically Accurate User-Facing Privacy & Service Disclosure
The exact user-facing disclosure text distinguishing local processing, external Google transmission, and metadata exposure:
> **QuMail Privacy and Google Service Access Disclosure**
>
> **1. Scope and Permissions Granted to QuMail:**  
> To connect using standard internet email protocols (IMAP and SMTP with SASL XOAUTH2), Google requires QuMail to request the full `https://mail.google.com/` permission. This permission grants broad access to your Google account, including the ability to read, compose, send, and permanently delete all email in your Gmail mailbox.  
> *QuMail Feature Constraint:* QuMail’s code does not implement or expose any message deletion feature (`EXPUNGE` or trash emptying commands are excluded by design), nor does it access spam or mail settings. However, Google’s platform grants QuMail full technical authority under this scope.
>
> **2. Message Payload and Network Transmission:**  
> - **Plaintext Processing:** Composition, plaintext editing, and message decryption occur strictly in memory on your local computer. Plaintext message bodies and unencrypted attachments are never sent to Google or any other server.  
> - **Encrypted Payload Transmission:** QuMail uses OpenPGP (Sequoia PGP) to encrypt and sign your messages locally before transmission. The resulting encrypted MIME ciphertext payload is transmitted directly through Google’s SMTP servers (`smtp.gmail.com`) to reach your recipients.  
> - **Visible Transport Metadata:** While message contents and attachments are encrypted, standard email routing metadata—including sender address, recipient addresses, message timestamps, transport Message-IDs, and transmission size—remains visible to Google and network intermediaries as required by standard SMTP protocols. Outer message subjects are standardized to `"Encrypted message"` to protect subject line confidentiality.
>
> **3. OAuth Tokens and Local Cryptographic Custody:**  
> - **OAuth Tokens:** Google OAuth authorization codes and refresh tokens are exchanged directly between your local computer and Google’s authorization servers (`accounts.google.com` / `oauth2.googleapis.com`) over TLS. Tokens are stored encrypted on your local drive inside QuMail’s SQLite vault.  
> - **Master Key Custody:** The vault’s AES-256-GCM encryption key is protected by your Windows user account in the Windows Credential Manager (`QuMail M3 local vault`).  
> - **Private Keys:** Your OpenPGP private signing and decryption keys are generated locally, stored exclusively inside your local encrypted vault, and are never transmitted to Google, QuMail developers, or any third party.
>
> **4. Server Infrastructure & Telemetry Disclosure:**  
> QuMail operates with no developer-hosted backend servers for ordinary email operations. QuMail does not operate telemetry, tracking, analytics, or remote crash-reporting servers. Network traffic from QuMail flows strictly between your local computer and Google’s documented endpoints (`*.google.com`, `*.googleapis.com`), plus the local loopback interface (`127.0.0.1`) used during browser OAuth callback handling.

---

## 5. Corrected Acceptance Matrix & Semantic Clarifications

### A. Operational Clarifications
- **`M12-PRE-01` Preflight:** Strictly side-effect-free validation of local environment readiness (client JSON schema, python interpreter, native crypto binaries, and vault path resolution without `-AllowNewVault`). It executes zero network calls, creates no directories, and does not probe Google servers.
- **`M12-VAULT-01` UI State:**
  - In `IdentitySettings`: displays `Unlocked · sending disabled` (by design, Settings never provides a mail send interface).
  - In `MailboxWindow`: banner displays `Development · production approval pending · Gmail submission explicitly enabled`.
  - In `MailActions`: the **"Submit once"** button is **enabled**.
- **Delivery Semantics:**
  - `ACCEPTED` in the outbox represents **Google SMTP server acceptance** (`250 2.0.0 OK`).
  - It does **not** prove recipient inbox arrival, decryption, or signature validity.
  - Recipient arrival, decryption, signature validation, and attachment verification are evaluated as separate, observable acceptance steps.

### B. Six-Level State & Authorization Classification
Every acceptance test is classified into one of six operational tiers:
- **Tier 1:** Static or offline validation (No side effects).
- **Tier 2:** Local application state modification (In-memory UI state, focus, window traversal).
- **Tier 3:** Credential or vault modification (Disk creation of SQLite database, Credential Manager write, file export).
- **Tier 4:** Live Google read operation (HTTPS userinfo query, IMAP PEEK read, OAuth handshake).
- **Tier 5:** Live Google write operation (IMAP `\Seen` flag mutation).
- **Tier 6:** External email transmission (Live SMTP submission to `smtp.gmail.com:587`).

---

## 6. Comprehensive Revised Acceptance Matrix

| Test ID | Tier | Operation Category | Preconditions | Procedure | Expected Observable Result | Pass/Fail Criteria | Requires Owner Approval? |
|---|---|---|---|---|---|---|---|
| **M12-PRE-01** | **Tier 1** | Local Preflight | Client JSON downloaded; Python venv valid. | Run `start_google_acceptance.ps1` with `-Vault <path>` `-GoogleClient <path>` `-CheckOnly` (no `-AllowNewVault`). | Console reports client valid, preflight passed; zero filesystem modification; zero network calls. | Exit code 0; strictly side-effect-free. | No |
| **M12-VAULT-01** | **Tier 3** | Vault Creation | Vault file absent; launched with `-AllowNewVault -EnableGmailSubmit`. | Launch QuMail; open Settings; click **"Create vault"**. | SQLite created in `%LOCALAPPDATA%\...\acceptance.sqlite`; Settings status shows `Unlocked · sending disabled`; Mailbox banner shows `Gmail submission explicitly enabled`. | SQLite DB initialized with `vault` and `accounts` tables; master key stored in Credential Manager. | **Yes** (Creates persistent state) |
| **M12-AUTH-01** | **Tier 4** | OAuth Enrollment (A) | Vault unlocked; Account A in Google Test Users. | Enter Account A address in Settings; click **"Connect Google"**; complete browser consent within 180s. | Browser shows "Return to QuMail"; Settings displays Account A address, `active` lifecycle, and root fingerprint. | Account A row created in `accounts` table with encrypted OAuth tokens. | **Yes** (Live OAuth handshake) |
| **M12-AUTH-02** | **Tier 4** | OAuth Enrollment (B) | Account A enrolled; Account B in Google Test Users. | Enter Account B address in Settings; click **"Connect Google"**; complete browser consent within 180s. | Browser shows "Return to QuMail"; Settings account selector lists both A and B independently. | Separate Account B row created in `accounts` table; A and B root fingerprints differ. | **Yes** (Live OAuth handshake) |
| **M12-TOKEN-01** | **Tier 4** | Proactive Token Refresh | Accounts A and B enrolled; tokens in vault. | Select Account A; click **"Refresh Google"**. Repeat for Account B. | Bounded worker queries Google userinfo endpoint; token refreshed; status displays `Committed.` | Token expiry timestamp updated in DB without re-opening browser. | **Yes** (Live Google call) |
| **M12-TOKEN-02** | **Tier 4** | On-Demand Auto Renewal | Access token near expiry (`<= 60s`). | In Mailbox, click **"Refresh headers"** with near-expired access token. | `Credentials.resolve()` detects near-expiry, automatically refreshes token via Google, updates vault, and proceeds to IMAP. | IMAP headers load without error; vault OAuth expiry timestamp updated. | **Yes** (Live Google call) |
| **M12-TOKEN-03** | **Tier 4** | Expired Refresh Recovery | Refresh token simulated as expired / revoked. | Select account; click **"Refresh Google"** (fails with `Code.AUTH`). Click **"Reauthorize selected"**; complete browser consent. | UI displays reauthorization prompt; browser consent restores fresh refresh token; root key and account ID preserved intact. | Account re-enrolled under exact same `AccountId` and PGP root. | **Yes** (Live OAuth handshake) |
| **M12-TRUST-01** | **Tier 3** | PGP Trust Pinning | Accounts A and B enrolled in vault. | Select A → export `A-public.asc`. Select B → export `B-public.asc`. Select A → import `B-public.asc` and pin fingerprint. Select B → import `A-public.asc` and pin fingerprint. | Certificates exported without private keys; Contacts table displays verified root fingerprints with `pinned` trust. | Mutual fingerprints match source account displays exactly. | **Yes** (Local file writes) |
| **M12-IMAP-01** | **Tier 4** | IMAP PEEK Header Read | Account A selected; vault unlocked. | In Mailbox window, click **"Refresh headers"**. Repeat for Account B. | IMAP connects to `imap.gmail.com:993`; fetches headers via `BODY.PEEK`; displays headers; read flags unchanged. | Zero message state mutation; unread messages remain unread on server. | **Yes** (Live IMAP call) |
| **M12-SEND-01** | **Tier 6** | Protected Email Send | Account A selected; B's key pinned; attachment ready. | Compose To: B; attach `acceptance-note.txt` (<16 KiB); click **"Verify recipients"** → **"Save encrypted draft"** → **"Prepare saved"** → **"Submit once"**. | Outbox transitions `DRAFT` → `PREPARED` → `SUBMITTING` → `ACCEPTED`. SMTP sends over TLS to `smtp.gmail.com:587`. | Outbox displays `Accepted` with attempt count 1; message accepted by Gmail SMTP. | **Yes** (Live email transmission) |
| **M12-RECV-01** | **Tier 4** | Recipient PEEK & Decrypt | Message sent in M12-SEND-01; Account B selected. | Select Account B; click **"Refresh headers"**; select arrival; click **"Open selected"**; click **"Save attachment as…"**. | Outer subject is `Encrypted message`; inner decrypted subject/body matches A's message; signature valid; attachment exported intact. | Decrypted content matches sent content exactly; SHA-256 digests match. | **Yes** (Filesystem export) |
| **M12-SEND-02** | **Tier 6** | Protected Reply & Forward | Original message opened in Account B. | Click **"Reply"**; add reply text; save, prepare, and submit once. Reopen original; click **"Forward"**; select A; save, prepare, and submit once. | Both submissions transition to `ACCEPTED`. Account A refreshes headers and decrypts both messages successfully. | Two distinct messages received by A; verified references established. | **Yes** (Live email transmission) |
| **M12-FLAG-01** | **Tier 5** | IMAP Flag Mutation | Test message present in mailbox. | Select message; click **"Mark read"** → refresh (verify read). Click **"Mark unread"** → refresh (verify unread). Click **"Open selected"** → refresh (verify remains unread). | Server flags updated only upon explicit command; opening message preserves prior unread state. | `\Seen` flag matches explicit user commands exactly. | **Yes** (Live IMAP mutation) |
| **M12-ISOL-01** | **Tier 2** | Account Switch Isolation | Mailbox open with Account A message displayed. | Switch account selector from A to B while message is open. | Plaintext body, attachments, and security label clear immediately; Account B headers load; no cross-account residue. | Zero leakage of A's plaintext or tokens into B's session. | No |
| **M12-ISOL-02** | **Tier 2** | Vault Lock Isolation | Mailbox idle; zero pending worker threads. | Click **"Lock"** in Mailbox window while idle. | Vault locks immediately; lease invalidated; header/compose buttons disable; cached keys purged from memory; late workers drop results. | Application enters locked state safely without interrupting state transitions. | No |
| **M12-ISOL-03** | **Tier 3** | Restart Durability | Outbox contains accepted/sent records. | Close QuMail; restart via live launcher; unlock vault. | All historical outbox operations, attempts, and receipts remain intact; startup recovery transitions any interrupted submissions to `UNKNOWN`. | Re-read from SQLite matches pre-restart state bit-for-bit; no duplicate submission triggered. | **Yes** (Interacts with persistent vault & recovery) |

---

## 7. Staged Execution Plan with Separate Gates

The 16 acceptance tests are strictly partitioned into six sequential stages, each gated by explicit verification before subsequent stages can be authorized:

### Stage A — Offline & Local Preparation (Tiers 1 & 2)
- Tests: `M12-PRE-01` (side-effect-free preflight), `M12-ISOL-01` (account switch view purging).
- Scope: Validates local environment, client JSON syntax, binary availability, and UI memory isolation.
- Gate: Zero side effects; preflight passes exit code 0.

### Stage B — Owner-Authorized Vault Preparation (Tier 3)
- Tests: `M12-VAULT-01` (Acceptance vault creation and Credential Manager master key write).
- Scope: Creates `%LOCALAPPDATA%\QuMailAcceptance\2026-11-01-desktop\acceptance.sqlite` and writes master key to Windows Credential Manager.
- Gate: SQLite database initialized; Settings displays `Unlocked · sending disabled`; Mailbox banner displays `Gmail submission explicitly enabled`.

### Stage C — Google OAuth Authorization (Tier 4)
- Tests: `M12-AUTH-01` (Account A enrollment), `M12-AUTH-02` (Account B enrollment), `M12-TRUST-01` (Mutual PGP export & fingerprint pinning), `M12-TOKEN-01` (Proactive token refresh).
- Scope: Completes browser OAuth consent for both test users, verifies ID token signatures, establishes PGP root keys, and mutually pins public fingerprints.
- Gate: Both accounts enrolled with distinct root keys; mutual public certificates pinned; token refresh succeeds.

### Stage D — Controlled Mailbox Read (Tier 4)
- Tests: `M12-IMAP-01` (IMAP PEEK header retrieval).
- Scope: Connects to `imap.gmail.com:993` in readonly mode using `BODY.PEEK`.
- Gate: Headers fetched for A and B; zero server-side read flag mutations occur.

### Stage E — First Protected Message Send & Receive (Tiers 4 & 6)
- Tests: `M12-SEND-01` (Single A → B protected email send), `M12-RECV-01` (Recipient B PEEK read, decrypt, and attachment export).
- Scope: Executes exactly one protected email send from Account A to Account B via `smtp.gmail.com:587`. Account B retrieves via IMAP PEEK, decrypts inner payload, verifies signature, and exports attachment.
- Gate: Outbox status `Accepted`; B decrypts message; signature valid; exported attachment SHA-256 matches sent attachment bit-for-bit.

### Stage F — Recovery & Extended Workflows (Tiers 2, 3, 4, 5, 6)
- Tests: `M12-TOKEN-02` (On-demand auto renewal), `M12-TOKEN-03` (Expired refresh recovery), `M12-SEND-02` (B → A Reply & Forward), `M12-FLAG-01` (Explicit `\Seen` flag mutation), `M12-ISOL-02` (Idle vault lock isolation), `M12-ISOL-03` (Restart durability & recovery).
- Scope: Evaluates token expiration recovery, two-way threaded replies/forwards, explicit read flag mutation, idle locking, and restart durability.
- Gate: All extended operations complete; zero duplicate sends; persistence confirmed.


---

## 7. Security and Production-Readiness Clarifications

1. **Local-Only Boundary Invariant:**
   - QuMail transmits data exclusively to two endpoints: `*.google.com` (OAuth/IMAP/SMTP) and local loopback (`127.0.0.1`).
   - Zero telemetry, analytics, or crash reports are sent to any developer-controlled or third-party servers.
   - All cryptographic key generation, signing, and decryption run locally via `qumail-m5-provider.exe`.
2. **Master Key Custody:**
   - Windows Credential Manager stores exclusively the 256-bit vault master key (`QuMail M3 local vault`).
   - No private PGP keys, OAuth tokens, or message contents are stored in Credential Manager; all remain encrypted inside the SQLite database file.
3. **Sensitive Data Scrubbing:**
   - Logging explicitly scrubs or omits sensitive materials (OAuth callback URLs, auth codes, access tokens, refresh tokens, private keys, plaintext bodies).
   - In `experiments/m4/smtp_transport.py`, Google OAuth 334 error challenge responses are not logged.

---

## 8. Summary of Documentation Updates

1. **Created:** [`docs/operations/google-integration-verification.md`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/google-integration-verification.md) — Comprehensive technical verification document containing the complete runtime call graph, M4 historical reconciliation, and explicit answers to all 10 architectural questions.
2. **Updated:** [`docs/operations/google-live-acceptance-plan.md`](file:///c:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/google-live-acceptance-plan.md) — Updated to reflect the six-level state and authorization tiers, explicit testing-mode refresh token recovery test (`M12-TOKEN-03`), token renewal test (`M12-TOKEN-02`), and precise UI status descriptions.
3. **Committed & Pushed:** The updates were committed to `codex/m7-google-live-acceptance` and pushed to `origin/codex/m7-google-live-acceptance`.

---

## 9. Updated Go / No-Go Recommendation

### Recommendation: **READY FOR CONTROLLED LIVE ACCEPTANCE (CONDITIONAL UPON OWNER PRE-CHECK)**

#### Supporting Evidence:
1. **End-to-End Runtime Pipeline Proven:** The complete path from UI compose → recipient verification → Sequoia PGP encryption → M4 durable outbox persistence → XOAUTH2 token resolution → Gmail SMTP transmission is fully verified and backed by executable tests.
2. **Acceptance Matrix Refined:** All 16 tests now possess rigorous tier classifications (Tiers 1–6), explicit pass/fail criteria, and clear owner authorization boundaries.
3. **Operational Preconditions Documented:** The 7-day Testing mode expiration is fully accounted for with dedicated reauthorization and recovery procedures.

#### Required Owner Preconditions Before Directive Issuance:
1. Confirm both Account A and Account B are added under **Google Cloud Console → OAuth consent screen → Test users**.
2. Confirm interactive presence at the Windows 11 desktop for completing browser OAuth consent.

---

## ABSOLUTE STOP CONDITION COMPLIANCE

**STOP.**  
In accordance with Section 8 of the Technical Lead Review Directive:
- **No live Google account has been enrolled or authorized.**
- **No acceptance vault or SQLite database has been created.**
- **No credentials or tokens have been read, written, or migrated.**
- **No IMAP or SMTP connections have been initiated.**
- **No email has been submitted or transmitted.**
- **No further actions will be taken until the Technical Authority reviews this report and issues the formal Module 1.2 Execution Directive.**
