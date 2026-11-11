# QuMail M7 — Module 1.6 Threat Model & Security Architecture Review
## Threat Scenarios, Boundary Controls, Residual Risks, and Release Gates

**Milestone:** M7 — Module 1.6  
**Document:** Threat Model & Security Architecture Assessment  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  
**Branch:** `codex/m7-module-1-6-planning`  
**Accepted Baseline Checkpoint:** `eff3736` | **Closeout Anchor:** `c9a3cf4`  

---

## 1. Security Architecture & Threat Modeling Framework

### 1.1 Methodology and Trust Boundaries
This threat model evaluates QuMail's security posture using STRIDE categorization across six primary trust boundaries:
1. **User Endpoint Boundary:** Local workstation OS, memory, processes, file system, Windows Credential Manager.
2. **IPC Subprocess Boundary:** Python GUI runtime ↔ Native Rust cryptographic engine (`qumail-m5-provider.exe`).
3. **Local Storage Boundary:** SQLite database (`.sqlite`) encrypted via AES-256-GCM.
4. **Network & Mail Server Boundary:** Local machine ↔ Google Workspace (IMAP:993, SMTP:587) over TLS 1.3.
5. **Public Transport & MTA Boundary:** Transit across intermediate MTAs, relay nodes, and mail hops.
6. **Recipient Endpoint Boundary:** Peer email client, public-key verification, and local decryption.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                   LOCAL ENDPOINT TRUST BOUNDARY                         │
│                                                                                        │
│  ┌───────────────────────┐   Anon Pipes    ┌────────────────────────────────────────┐  │
│  │   Python GUI Process  │◄───────────────►│  Native Cryptographic Engine (Rust)    │  │
│  │   (MailboxWindow/UI)  │   (No Secrets   │  (Sequoia PGP 2.4.1 / OpenSSL 3.5.9)   │  │
│  └───────────┬───────────┘    on argv)     └───────────────────┬────────────────────┘  │
│              │                                                 │                       │
│              ▼                                                 ▼                       │
│  ┌───────────────────────┐                 ┌────────────────────────────────────────┐  │
│  │ Win Credential Store  │                 │ Local Encrypted Vault (SQLite)         │  │
│  │ (32-byte Master Key)  │                 │ AES-256-GCM (QuMail-M3-record-v1)      │  │
│  └───────────────────────┘                 └────────────────────────────────────────┘  │
└──────────────────────────────────────┬─────────────────────────────────────────────────┘
                                       │ TLS 1.3 + SASL XOAUTH2
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              MAIL SERVER / TRANSPORT BOUNDARY                          │
│                                                                                        │
│         Google Workspace (imap.gmail.com:993 / smtp.gmail.com:587)                     │
│         Intermediate Mail Transfer Agents (MTAs)                                       │
│                                                                                        │
│         EXPOSED: Routing metadata (From, To, Date, Message-ID), Wire Size, Timing.     │
│         PROTECTED: Message Subject ("Encrypted message"), Inner Body, Attachments.    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Cryptographic Protection vs. Exposed Metadata
A foundational principle of this threat model is honest disclosure of what post-quantum OpenPGP protects versus what remains exposed to network adversaries:
* **Cryptographically Protected (Confidential & Authenticated):**
  - Message body (plain-text content).
  - All file attachments (filenames, media types, raw bytes).
  - True subject line (sealed inside inner MIME; outer subject is replaced with `Encrypted message`).
  - True inner sender address (`From:`) and recipient list (`To:`, `Cc:`).
  - Threading references (`In-Reply-To:`, `References:`).
  - Cryptographic signature (ML-DSA-65 + Ed25519 composite signature).
* **Deliberately Exposed on the Wire (Transport Necessity):**
  - Outer routing addresses (`From:`, `To:`, `Cc:`) required by MTAs for delivery.
  - Outer `Date:` and `Message-ID:` headers required for RFC 5322 compliance.
  - Overall message size (padded only to 4 KiB chunk boundaries).
  - Transmission timing and frequency (traffic analysis / communication graphs).
  - Intermediate MTA trace headers (`Received:`, `DKIM-Signature:`, `X-Google-Smtp-Source:`).

---

## 2. Threat Scenarios by Security Domain

---

### Domain 1: Local Endpoint & Process Compromise

#### Scenario 1.1: Same-User Malware Memory Scraping
* **Threat:** Malware executing under the same Windows user account inspects QuMail's process memory to dump decrypted email text or private keys.
* **Required Attacker Capability:** Unprivileged execution in the user's desktop session.
* **Existing Mitigation:** 
  - Subprocess isolation: Native provider executes in a separate child process communicating over private anonymous pipes. Secrets are never passed via command-line arguments or environment variables.
  - Stale clearing: Locking the vault, switching accounts, or closing the viewer clears visible text from Qt widgets.
* **Evidence:** `experiments/m5/provider.py:25-50`, `ui/mailbox_window.py:150-160`.
* **Residual Risk:** Python strings and byte objects in the CPython heap are not pinned or actively zeroized by default; garbage collection delays leave transient copies in RAM.
* **Proposed Mitigation (WS-07):** Implement `secure_zero()` for bytearray buffers containing plaintext; lock memory pages via `VirtualLock` for high-assurance deployments.
* **Mandatory Gate:** Enterprise Deployment.

#### Scenario 1.2: Hostile File System Races on Attachment Export
* **Threat:** Malicious process running on the host monitors the export destination folder and races to substitute an exported document with a malicious executable.
* **Required Attacker Capability:** Write access to the destination directory selected by the user.
* **Existing Mitigation:**
  - Export uses exclusive creation (`os.O_CREAT | os.O_EXCL`); fails immediately if destination file already exists.
  - Filename traversal defense: Rejects `..`, `:`, NTFS Alternate Data Streams, and reserved device names (`CON`, `PRN`).
  - No auto-execution: Exported files are never automatically launched or opened.
* **Evidence:** `mailbox_client/workflows.py:120-140`, `tests/test_cryptographic_roundtrip.py:test_attachment_filename_traversal_defense`.
* **Residual Risk:** Low. Attacker cannot overwrite existing files or force code execution.
* **Proposed Mitigation:** None needed beyond current controls; current defense is verified.
* **Mandatory Gate:** Passed.

---

### Domain 2: Cryptographic Key & Vault Theft

#### Scenario 2.1: Theft of SQLite Vault Database File
* **Threat:** Adversary copies `qumail_vault.sqlite` from an unattended laptop or via compromised backup media.
* **Required Attacker Capability:** Read access to the local disk file.
* **Existing Mitigation:**
  - AES-256-GCM authenticated encryption on all account records.
  - Authenticated Associated Data (AAD) binds vault ID, account ID, and revision: `QuMail-M3-record-v1/{vault}/{account}/{revision}`.
  - 32-byte master encryption key is NOT stored in the database; it is stored in Windows Credential Manager via Win32 `CredWriteW` protected by DPAPI.
* **Evidence:** `experiments/m3/vault.py:20-55`, `experiments/m3/secure_store.py:20-50`.
* **Residual Risk:** If attacker has the logged-in user's credentials and can execute code as that user, DPAPI decrypts the master key automatically. DPAPI is not a hardware TPM enclave.
* **Proposed Mitigation (Future):** Windows Hello biometric prompt or TPM 2.0 platform binding before unlocking master key.
* **Mandatory Gate:** Enterprise Deployment.

#### Scenario 2.2: Vault Rollback to Re-play Revoked Credentials
* **Threat:** Attacker restores a 3-month-old vault backup to resurrect an expired or revoked subkey or roll back replay protection receipts.
* **Required Attacker Capability:** Ability to overwrite the local `.sqlite` database file.
* **Existing Mitigation:**
  - Revision counter checked during transaction commit.
  - Account aggregates fail GCM verification if manipulated.
* **Evidence:** `experiments/m3/vault.py:80-110`.
* **Residual Risk:** Entire-database rollback: GCM verifies integrity within the restored database snapshot, but cannot detect that the entire file was replaced with an authentic older version.
* **Proposed Mitigation (WS-07):** Store a monotonic rollback-detection counter in Windows Credential Manager or an append-only registry key.
* **Mandatory Gate:** Enterprise Deployment.

---

### Domain 3: Network, IMAP/SMTP & Transport Exposure

#### Scenario 3.1: Active Network Man-in-the-Middle (MitM) Attack
* **Threat:** Network adversary (rogue Wi-Fi, malicious ISP, compromised router) intercepts IMAP or SMTP traffic to eavesdrop on emails or inject commands.
* **Required Attacker Capability:** Position on the local network / packet interception.
* **Existing Mitigation:**
  - Mandatory TLS 1.3 / 1.2 on both IMAP (port 993) and SMTP (port 587 STARTTLS).
  - Strict hostname validation (`imap.gmail.com`, `smtp.gmail.com`) and system CA validation.
  - Cleartext connections, unencrypted fallback, or `verify=False` are hard-blocked.
  - Even if TLS were terminated (e.g. corporate SSL inspection proxy), the inner email is post-quantum encrypted (ML-KEM-768 + AES-256-GCM) and signed (ML-DSA-65 + Ed25519).
* **Evidence:** `mailbox_client/gmail.py:25-45, 95-115`, `tests/test_cancellation_submission_semantics.py`.
* **Residual Risk:** Corporate SSL inspection proxies will observe outer headers (`From`, `To`, `Subject: Encrypted message`, timing), but cannot inspect inner message bodies or attachments.
* **Proposed Mitigation:** None; current transport TLS and end-to-end PQ crypto are robust.
* **Mandatory Gate:** Passed.

#### Scenario 3.2: Malicious Mail Server Content Modification
* **Threat:** Compromised Google Workspace or rogue MTA alters ciphertext bytes or tampers with message headers in transit.
* **Required Attacker Capability:** Control over the mailbox provider or intermediate MTA.
* **Existing Mitigation:**
  - OpenPGP SEIPDv2 integrity authentication: Any byte alteration causes OpenSSL / Sequoia PGP to fail authentication. Zero plaintext is released.
  - Composite digital signature: ML-DSA-65 and Ed25519 verify that the inner MIME content was created by the sender.
  - Header consistency check: Inner `HP-Outer` protected headers are verified against outer headers; mismatches are flagged.
* **Evidence:** `tests/test_cryptographic_roundtrip.py:test_tampered_ciphertext_rejection`.
* **Residual Risk:** Server can drop messages (Denial of Service), but cannot alter contents undetected.
* **Proposed Mitigation:** None; cryptographic integrity is complete.
* **Mandatory Gate:** Passed.

---

### Domain 4: MIME Parser, Header Injection & Content Attacks

#### Scenario 4.1: Adversarial MIME Nesting & Resource Exhaustion (Zip/MIME Bomb)
* **Threat:** Attacker sends an email with deeply nested `multipart` structures or millions of MIME parts to trigger stack overflow or OOM in the parser.
* **Required Attacker Capability:** Ability to send an email to the recipient's address.
* **Existing Mitigation:**
  - Strict recursion limits: `MAX_DEPTH = 2`, `MAX_PARTS = 6`, `MAX_HEADERS = 8192`.
  - Wire limit: `MAX_WIRE = 256 KiB` (expanding to 15 MiB in WS-03 with streaming).
  - Native helper runs with an explicit 8 MiB worker stack to prevent Windows `0xc00000fd` stack overflows.
* **Evidence:** `experiments/m5/mime.py:25-50`, `experiments/m5/model.py:8-15`, `ADR 006:45-50`.
* **Residual Risk:** Bounded memory growth; parser exits cleanly with `Failure(Code.LIMIT)`.
* **Proposed Mitigation (WS-03):** Maintain strict part counts and depth limits even when expanding wire size to 15 MiB.
* **Mandatory Gate:** Controlled Pilot.

#### Scenario 4.2: Header Injection (CRLF Line Splitting)
* **Threat:** Attacker injects carriage return and line feed (`\r\n`) characters into compose fields (e.g. Subject or recipient names) to inject rogue SMTP commands or duplicate headers.
* **Required Attacker Capability:** Compromise of client UI input or crafted incoming message.
* **Existing Mitigation:**
  - `experiments/m5/mime.py:16` uses Python's `email.policy.SMTP.clone(raise_on_defect=True)`.
  - RFC 5322 singleton header checks strictly enforce exactly one occurrence of structural headers.
* **Evidence:** `experiments/m5/mime.py:20, 131`, `eff3736`.
* **Residual Risk:** Need explicit regex rejection of raw `\r` and `\n` in compose field setters.
* **Proposed Mitigation (WS-07):** Add input sanitization in `Draft` construction rejecting raw control characters in `subject`, `to`, and `cc`.
* **Mandatory Gate:** Controlled Pilot.

---

### Domain 5: Contact Trust, Impersonation & Identity Attacks

#### Scenario 5.1: Sender Spoofing via Outer `From:` Header
* **Threat:** Adversary sends an email with `From: ceo@company.com` containing phishing text, signed by an attacker's key or completely unsigned.
* **Required Attacker Capability:** Standard SMTP sender spoofing (SPF/DKIM bypass or unauthenticated relay).
* **Existing Mitigation:**
  - QuMail treats outer `From:` strictly as an untrusted transport routing hint.
  - Inner cryptographic identity verification: QuMail matches the sender against imported local vault contacts.
  - If unsigned: Displays `Conventional mail: author and content are not cryptographically verified`.
  - If signed by an unknown key: Displays `unverified_identity` warning banner; NEVER grants `verified_confidential` badge.
  - If signed by pinned contact: Displays green badge `Signature valid; identity: independently_verified`.
* **Evidence:** `mailbox_client/service.py:105-128`, `tests/test_cryptographic_roundtrip.py:test_sender_trust_model_enforcement`.
* **Residual Risk:** Non-technical employees might ignore the "unverified" label on conventional emails.
* **Proposed Mitigation (WS-05):** Enhance visual contrast between conventional (gray/unverified) and cryptographically verified (indigo/green) messages.
* **Mandatory Gate:** Controlled Pilot.

#### Scenario 5.2: Public-Key Substitution (Man-in-the-Middle on Key Discovery)
* **Threat:** Adversary injects a rogue public key during contact exchange, enticing the sender to encrypt to the attacker's key.
* **Required Attacker Capability:** Interception of key discovery channel or compromise of web server hosting WKD.
* **Existing Mitigation:**
  - Independent trust model: Importing a key does NOT grant trust. An explicit pinning action (`pin_contact`) requiring fingerprint confirmation or enterprise directory certification is mandatory.
  - If a contact's root key changes, sending is immediately blocked with an explicit root-replacement security warning (`CHANGED_BLOCKED`).
  - Separation of Discovery from Trust (WS-02): Discovered WKD keys are marked `EXTERNAL_CORRESPONDENT` or `ENCRYPTED_UNVERIFIED` and never granted `SECURED_BY_QUMAIL` or automatic pinning (no silent TOFU).
  - Corporate Domain Anchors (WS-02): Admin-provisioned `EnterpriseTrustDirectory` provides corporate trust roots for company domains (`@company.com`) without manual fingerprint verification.
  - Subkey Rotation vs Replacement (WS-02): `evaluate_key_transition` permits authentic subkey rotation signed by the same root key, but halts immediately on unauthorized primary key changes.
* **Evidence:** `experiments/m3/vault.py:200-230`, `core/key_discovery.py`, `core/trust_engine.py`, `core/key_lifecycle.py`, `tests/test_ws02_identity_and_trust.py`.
* **Residual Risk:** DNS/HTTPS hijacking of an unpinned external correspondent's WKD could present an unverified public key. Risk is mitigated by plain-language badge warnings (`ENCRYPTED_UNVERIFIED`) and blocking corporate-grade trust unless explicitly pinned or anchor-certified.
* **Mitigation Status:** Implemented & Verified in WS-02 (`tests/test_ws02_identity_and_trust.py`).
* **Mandatory Gate:** Passed for WS-02.

#### Scenario 5.3: Historical Signature Backdating & Key Compromise Forgery
* **Threat:** Attacker acquires an expired or compromised private key, crafts a fraudulent message today, and backdates the OpenPGP signature creation timestamp to appear signed years earlier when the key was active.
* **Required Attacker Capability:** Possession of an expired or compromised private key.
* **Existing Mitigation:**
  - Backdating Defense: An OpenPGP signature creation-time field is untrusted metadata. QuMail strictly rejects claimed signature time as proof of historical validity.
  - Granular Historical Verification: When a key is expired or revoked, `core/key_lifecycle.py:verify_historical_signature` requires independent, authenticated time evidence (`TimestampEvidence`: RFC 3161 TSA token or durable vault replay receipt committed at live reception). Without evidence, it returns `INDETERMINATE_NO_TRUSTED_TIME`.
  - Compromise Handling: Keys revoked due to `KEY_COMPROMISED` invalidate all signatures postdating compromise; only signatures with authenticated receipts strictly predating the compromise point are accepted.
* **Evidence:** `core/key_lifecycle.py`, `tests/test_ws02_security_assurance.py`.
* **Residual Risk:** If an attacker compromises a key AND compromises the local vault replay database, they could forge local receipts. Protected by SQLite AES-256-GCM encryption and OS DPAPI master key.
* **Mitigation Status:** Implemented & Verified in WS-02 Security Assurance.
* **Mandatory Gate:** Passed for WS-02.

#### Scenario 5.4: WKD Network SSRF, DNS Rebinding & Hostile Redirection
* **Threat:** Malicious email domain induces QuMail to query a WKD server that resolves to local private IP addresses (e.g. AWS/Azure metadata `169.254.169.254`, localhost `127.0.0.1`, internal routers) or redirects to an external malicious server.
* **Required Attacker Capability:** Control over the recipient or sender email domain name.
* **Existing Mitigation:**
  - Strict HTTPS Enforcement: Insecure HTTP connections and HTTPS-to-HTTP downgrades are rejected.
  - Domain Sanitization: `validate_domain` strictly rejects malformed syntax, control characters, colons (ports), slashes, and spaces.
  - Anti-SSRF Defense: `is_ip_prohibited` resolves hostnames and rejects any address in loopback, RFC 1918 private, link-local, carrier-grade NAT, multicast, or reserved ranges.
  - DNS Rebinding Defense: TCP socket connects directly to the pre-validated IP while validating TLS against the target SNI hostname.
  - Redirect Hardening: Redirects are capped at 2 hops, revalidated against the target domain, and blocked if pointing to external hosts or prohibited IPs.
  - Payload Ceiling: Bounded 64 KiB ceiling with stream abort; HTML responses rejected.
* **Evidence:** `core/key_discovery.py:secure_wkd_fetch`, `tests/test_ws02_security_assurance.py`.
* **Residual Risk:** Low. Network querying is sandboxed, memory-bounded, and strictly validates destinations.
* **Mitigation Status:** Implemented & Verified in WS-02 Security Assurance.
* **Mandatory Gate:** Passed for WS-02.

#### Scenario 5.5: Enterprise Key Revocation Bypass via Public Directory Fallback
* **Threat:** Terminated employee or compromised account has their key revoked in the corporate enterprise directory; attacker publishes an unverified public key in public WKD hoping the client will fall back to it.
* **Required Attacker Capability:** Control over public DNS/web hosting for an enterprise domain, or third-party WKD publication.
* **Existing Mitigation:**
  - Enterprise Absolute Precedence: Authenticated enterprise directory is the authoritative source of truth for corporate domains (`@company.com`).
  - Anti-Bypass Fallback Blocking: When an enterprise key is revoked or expired in the corporate directory, sending is blocked. Silent fallback to public WKD is strictly prohibited (`VERIFICATION_FAILED`).
* **Evidence:** `core/trust_engine.py`, `core/enterprise_trust.py`, `tests/test_ws02_security_assurance.py`.
* **Residual Risk:** None; corporate domain keys cannot be overridden by public directory records.
* **Mitigation Status:** Implemented & Verified in WS-02 Security Assurance.
* **Mandatory Gate:** Passed for WS-02.

---

### Domain 6: Replay, Duplicate & State Manipulation Attacks

#### Scenario 6.1: Replay of Previously Captured Encrypted Email
* **Threat:** Eavesdropper captures an authentic encrypted email (e.g. "Approve wire transfer") and resends it to the recipient 2 weeks later.
* **Required Attacker Capability:** Ability to re-inject raw wire bytes into the recipient's mail spool.
* **Existing Mitigation:**
  - Replay Subsystem: Every opened modern message records its canonical SHA-256 MIME digest in the vault table `replay_v1` keyed by `(account, signer_root, message_id)`.
  - The replay digest is committed to the database BEFORE decrypted plaintext is released to the UI.
  - When replayed, QuMail detects the duplicate digest, sets `opened.replay = ReplayStatus.DUPLICATE`, and displays an explicit replay warning banner.
* **Evidence:** `experiments/m5/services.py:125-140`, `tests/test_cryptographic_roundtrip.py:test_duplicate_message_replay_detection`.
* **Residual Risk:** If the same message arrives with a different digest (e.g. modified outer headers), it is marked `ReplayStatus.CONFLICT` and denied confidential status.
* **Proposed Mitigation:** None; replay protection is robustly implemented.
* **Mandatory Gate:** Passed.

#### Scenario 6.2: Duplicate Send via Outbox Retry Confusion
* **Threat:** Network times out during SMTP submission; user repeatedly clicks "Retry send", causing multiple duplicate financial or contractual emails to be dispatched.
* **Required Attacker Capability:** None (user error caused by ambiguous UI).
* **Existing Mitigation:**
  - Ambiguous outcomes are classified as `UNKNOWN` (never falsely marked Failed).
  - Retrying an `UNKNOWN` operation requires explicit duplicate-risk acknowledgment in a modal confirmation dialog.
  - Retrying sends the EXACT frozen bytes and `Message-ID`; it never re-encrypts with a new ID.
* **Evidence:** `ui/mail_actions.py:265-270`, `experiments/m4/model.py:75-80`, `tests/test_cancellation_submission_semantics.py`.
* **Residual Risk:** User might click "Yes" on the duplicate warning dialog without verifying Sent mail.
* **Proposed Mitigation (WS-04):** Automated IMAP Sent-folder reconciliation: client checks Sent mail automatically before offering the retry button.
* **Mandatory Gate:** Controlled Pilot.

---

### Domain 7: Supply Chain, Packaging & Update Attacks

#### Scenario 7.1: Malicious Native Binary Substitution
* **Threat:** Attacker substitutes `qumail-m5-provider.exe` with a trojanized binary on disk to intercept plaintext and private keys.
* **Required Attacker Capability:** Write permissions to the application installation directory (`C:\Program Files\QuMail\bin`).
* **Existing Mitigation:** Standard Windows NTFS permissions: `Program Files` is writable only by `NT AUTHORITY\SYSTEM` and local Administrators; standard non-admin users cannot modify files.
* **Residual Risk:** Unprivileged portable execution running from user directories (`AppData` or `Downloads`) allows binary tampering.
* **Proposed Mitigation (WS-06):** MSI installer installing strictly to `Program Files`; digital signature verification on provider startup.
* **Mandatory Gate:** Enterprise Deployment.

#### Scenario 7.2: Unsigned Application Updates
* **Threat:** Attacker on local network spoofing update server to push malicious executable updates.
* **Required Attacker Capability:** Network MitM on update channel.
* **Existing Mitigation:** QuMail currently possesses zero auto-update mechanism; cannot be exploited via rogue update feeds.
* **Residual Risk:** Manual updates require IT distribution.
* **Proposed Mitigation (Future):** When auto-update is added, enforce HTTPS, Ed25519 update manifest signature verification, and Authenticode binary checks.
* **Mandatory Gate:** Public Release.

---

## 3. Threat Mitigation Matrix and Release Gates

| Threat ID | Threat Description | Severity | Target Mitigation | Mandatory Release Gate | Gate Status |
|---|---|---|---|---|---|
| **T-01** | Same-User Malware Memory Scraping | Medium | `secure_zero()` buffer clearing; sub-second plaintext window (WS-07) | Enterprise Deployment | Planned (WS-07) |
| **T-02** | Hostile Attachment Path Traversal | Critical | `O_CREAT \| O_EXCL`, filename sanitization, no auto-execution | Controlled Pilot | **VERIFIED PASS** |
| **T-03** | Theft of Offline Vault Database | High | DPAPI master key + AES-256-GCM authenticated encryption | Controlled Pilot | **VERIFIED PASS** |
| **T-04** | Whole-Database Rollback Replay | Medium | Monotonic out-of-vault replay counter (WS-07) | Enterprise Deployment | Planned (WS-07) |
| **T-05** | Network Transport MitM Eavesdropping | Critical | Strict TLS 1.3 + ML-KEM-768/AES-GCM end-to-end payload encryption | Controlled Pilot | **VERIFIED PASS** |
| **T-06** | Mail Server Ciphertext Tampering | Critical | OpenPGP SEIPDv2 integrity auth + ML-DSA-65 composite signature | Controlled Pilot | **VERIFIED PASS** |
| **T-07** | Adversarial MIME Bomb / Resource Exhaustion | High | Part limits, 8 MiB worker stack, depth limits (WS-03) | Controlled Pilot | Planned (WS-03) |
| **T-08** | Header Injection via CRLF Splitting | Medium | Strict RFC 5322 regex validation in draft construction (WS-07) | Controlled Pilot | Planned (WS-07) |
| **T-09** | Outer `From:` Sender Address Spoofing | High | Inner cryptographic signature verification; unverified badges | Controlled Pilot | **VERIFIED PASS** |
| **T-10** | Public-Key Substitution on Discovery | High | Mandatory pinning; domain-signed WKD keys (WS-02) | Controlled Pilot | Planned (WS-02) |
| **T-11** | Replay of Stale Encrypted Messages | High | Atomic pre-release SHA-256 digest commitment in vault | Controlled Pilot | **VERIFIED PASS** |
| **T-12** | Duplicate Outbound Transmission on Disconnect | Medium | Automated IMAP Sent-folder reconciliation (WS-04) | Controlled Pilot | Planned (WS-04) |
| **T-13** | Native Cryptographic Binary Tampering | High | NTFS `Program Files` protection + Authenticode code signing (WS-06) | Enterprise Deployment | Planned (WS-06) |
