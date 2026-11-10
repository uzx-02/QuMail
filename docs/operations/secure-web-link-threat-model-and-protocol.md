# QuMail Secure Web Link Threat Model & Protocol Proposal

**Milestone:** M8 Architecture Proposal  
**Document:** Secure Web Link Threat Model and Protocol Proposal  
**Status:** Architecture Proposal (Under Review; Implementation Deferred)  
**Author:** Antigravity (Implementation Engineer) & Mohammed Uzair Shaikh (Project Owner)  
**Target Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Date:** 2026-11-10  
**Accepted Baseline:** `d3b2078` (WS-06/07 Final Accepted Checkpoint)  
**Reference ADR:** [`docs/adrs/010-product-flow-and-public-key-directory.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/adrs/010-product-flow-and-public-key-directory.md)  

---

## 1. Problem Statement & Motivation

QuMail's primary wire format (`QM-OPENPGP-PQ-v1`) delivers end-to-end post-quantum security between QuMail endpoints. However, in enterprise and commercial workflows, employees frequently need to communicate confidential materials (contracts, payroll, audit reports) to external recipients (clients, partners, accountants) who do not have QuMail installed.

Forcing an external partner to install a desktop Windows client simply to read a single email causes extreme friction and workflow abandonment.

The **Secure Web Link Portal** solves this problem by enabling a **Zero-Install Recipient Experience** while strictly preserving client-side encryption and zero-server-plaintext visibility.

---

## 2. Threat Model & Security Boundaries

### 2.1 Threat Model Entities
```
+-------------------+           +-------------------------+           +-------------------+
| Alice (Sender)    |           | QuMail Web Portal       |           | Bob (Recipient)   |
| QuMail Desktop    |           | (Untrusted Storage Host)|           | Any Web Browser   |
+-------------------+           +-------------------------+           +-------------------+
        │                                    │                                    │
        │ 1. Upload Encrypted Blob           │                                    │
        ├───────────────────────────────────►│                                    │
        │                                    │                                    │
        │ 2. Email Link with #KeyFragment    │                                    │
        ├────────────────────────────────────┼───────────────────────────────────►│
        │    (via standard Gmail / SMTP)     │                                    │
        │                                    │ 3. HTTP GET /view/UUID (NO #key!)  │
        │                                    │◄───────────────────────────────────┤
        │                                    │                                    │
        │                                    │ 4. Issue & Verify OTP              │
        │                                    │◄──────────────────────────────────►│
        │                                    │                                    │
        │                                    │ 5. Release Encrypted Blob          │
        │                                    ├───────────────────────────────────►│
        │                                    │                                    │
        │                                    │                                    │ [Browser decrypts
        │                                    │                                    │  using #key locally]
```

1. **Alice (Sender):** Uses the trusted QuMail desktop client on Windows. Generates encryption keys locally.
2. **Bob (Recipient):** Uses an ordinary web browser on desktop or mobile (Chrome, Safari, Edge, Firefox). Does not possess a local vault.
3. **QuMail Web Portal Server:** Untrusted cloud or on-premise infrastructure. Hosts the web application and stores ephemeral encrypted blobs. **Treated as an untrusted adversary.**
4. **Mail Transport Agents (MTAs):** Intermediary mail servers (Google, Microsoft, recipient MTA) transmitting the invitation link and OTP.
5. **Adversaries:**
   - *Passive Eavesdropper on Network / SMTP:* Captures emails traversing transit.
   - *Compromised Web Portal Server:* Attacker with root/database access to the portal storage.
   - *Malicious Third Party:* Attempts to guess OTPs, intercept links, or access expired messages.

### 2.2 Security Assets & Required Invariants

| Asset | Protection Required | Mechanism |
|---|---|---|
| **Message Body & Attachments** | Confidentiality & Integrity | Encrypted client-side with AES-256-GCM. Portal server **never** sees plaintext. |
| **Decryption Key ($K_{\text{msg}}$)** | Confidentiality from Server | Delivered via URL Fragment (`#key`). Fragments are **never** transmitted to the server. |
| **Sender Identity & Authenticity** | Integrity & Non-Repudiation | Digital signature by Alice's Ed25519 signing key over ciphertext digest. |
| **Recipient Identity Verification** | Authorization | Time-limited One-Time Passcode (OTP) sent to Bob's registered email address. |
| **Forward Secrecy & Expiration** | Freshness & Replay Prevention | Unique key per message, strict Time-to-Live (TTL), immediate deletion upon expiry. |

---

## 3. Cryptographic Protocol Specification

### 3.1 Step 1: Client-Side Key Generation & Encryption (Alice's QuMail Desktop)

When Alice drafts an email to an external recipient:
1. **Key Generation:**
   - Generates ephemeral 256-bit symmetric message key:
     $$K_{\text{msg}} \leftarrow \text{CSPRNG}(32\text{ bytes})$$
   - Generates 96-bit random nonce:
     $$\text{IV} \leftarrow \text{CSPRNG}(12\text{ bytes})$$
   - Generates UUIDv4 Message Identifier:
     $$M_{\text{id}} \leftarrow \text{UUIDv4}()$$
2. **Associated Authenticated Data (AAD):**
   $$\text{AAD} = \text{UTF8}(M_{\text{id}} \parallel \text{AliceEmail} \parallel \text{BobEmail} \parallel \text{TimestampISO})$$
3. **Payload Encryption (AES-256-GCM):**
   $$(C_{\text{body}}, T_{\text{tag}}) = \text{AES-256-GCM-Encrypt}(K_{\text{msg}}, \text{IV}, \text{PlaintextMessage}, \text{AAD})$$
4. **Sender Signature:**
   Alice signs the binding tuple using her local Ed25519 signing key:
   $$\sigma_{\text{sender}} = \text{Ed25519-Sign}(SK_{\text{Alice}}, \text{SHA256}(M_{\text{id}} \parallel C_{\text{body}} \parallel T_{\text{tag}} \parallel \text{AAD}))$$
5. **Ciphertext Blob Assembly:**
   $$\text{Blob} = \{\text{version}: 1, M_{\text{id}}, \text{IV}, C_{\text{body}}, T_{\text{tag}}, \text{AAD}, \sigma_{\text{sender}}, \text{AliceFingerprint}, \text{ExpiresUTC}\}$$

---

### 3.2 Step 2: Storage Staging & URL Fragment Assembly

1. **Blob Upload:** Alice's client uploads $\text{Blob}$ to the portal storage over TLS:
   ```http
   POST /api/v1/portal/stage
   Content-Type: application/json

   {
     "message_id": "9f27c72b-4e7b-4b3a-8f12-7b38a3f49a62",
     "recipient_email": "bob@externalcorp.invalid",
     "expires_utc": "2026-11-17T12:00:00Z",
     "payload_blob": "<Base64_Blob>"
   }
   ```
2. **Critical Security Invariant — Key Omission:**
   $K_{\text{msg}}$ is **NOT** included in the upload payload. The portal receives **only** ciphertext.
3. **URL Generation (RFC 3986 Fragment Delivery):**
   Alice's client constructs the access link:
   $$\text{AccessURL} = \texttt{https://portal.qumail.invalid/view/}M_{\text{id}}\texttt{\#}K_{\text{msg\_hex}}$$
   - **Why URL Fragment (`#`)?** RFC 3986 Section 3.5 mandates that the fragment identifier is processed purely client-side by user agents. Web browsers **NEVER transmit fragment identifiers in HTTP request headers (`GET /view/UUID HTTP/1.1`)**.
   - Therefore, the portal web server, intermediate proxies, and access logs **CANNOT observe $K_{\text{msg}}$**.

---

### 3.3 Step 3: Invitation Delivery & Recipient Access

1. **Invitation Email:** Alice's client transmits a standard email to Bob via her normal SMTP/Gmail transport:
   > **Subject:** Encrypted message from Alice Smith  
   > **Body:**  
   > Alice Smith has sent you a secure encrypted communication via QuMail.  
   > 🔒 **[View Secure Message](AccessURL)**  
   > *This message will expire on November 17, 2026.*
2. **Recipient Clicks Link:** Bob's browser navigates to `https://portal.qumail.invalid/view/<UUID>#<KeyFragment>`.
   - Browser sends: `GET /view/<UUID>` (no key).
   - Server responds with the lightweight static WebAssembly/JS decryptor application.

---

### 3.4 Step 4: OTP Authentication Challenge

Before releasing the encrypted blob, the portal verifies that the user accessing the link controls `bob@externalcorp.invalid`:
1. Server generates cryptographically random 6-digit numeric OTP:
   $$\text{OTP} \leftarrow \text{CSPRNG}(6\text{ digits})$$
2. Server hashes OTP with SHA-256 and stores with a strict **10-minute expiry**:
   $$\text{OTP\_Hash} = \text{SHA256}(\text{OTP} \parallel M_{\text{id}} \parallel \text{Salt})$$
3. Server transmits an email to Bob:
   > **Subject:** Your QuMail verification code  
   > **Body:** Your one-time access code is: **482 915**. It expires in 10 minutes.
4. Bob enters the code on the web page.
5. **Brute Force Defense:** Maximum **3 attempts allowed**. Exceeding 3 failed attempts permanently invalidates the current OTP and initiates a 15-minute cooldown.
6. Upon successful verification, the portal issues an ephemeral session token and releases the encrypted $\text{Blob}$.

---

### 3.5 Step 5: Browser-Side Sandboxed Decryption

Once the browser receives $\text{Blob}$:
1. **Key Extraction:** Client-side JavaScript extracts $K_{\text{msg}}$ from `window.location.hash`.
2. **Decryption via Web Cryptography API:**
   - Browser calls `crypto.subtle.decrypt({ name: "AES-GCM", iv, additionalData }, key, ciphertext)`.
   - The browser verifies the GCM authentication tag $T_{\text{tag}}$ and AAD bindings. If altered, decryption fails closed.
3. **Signature Verification:**
   - Browser verifies $\sigma_{\text{sender}}$ against Alice's public key (fetched from directory).
4. **Sandboxed Plain-Text Rendering:**
   - Message contents and attachments render inside an isolated, sandboxed `<iframe>`:
     ```html
     <iframe sandbox="allow-same-origin" srcdoc="<pre>Safe plain text</pre>"></iframe>
     ```
   - **Content Security Policy (CSP):**
     `default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src data:; connect-src 'self';`
   - External network connections, tracking pixels, scripts, and remote stylesheets are strictly prohibited.
5. **Attachments:** Attachments can be downloaded directly from browser memory via `Blob` object URLs (`URL.createObjectURL()`). Direct execution of `.exe`, `.bat`, etc. is blocked.

---

### 3.6 Step 6: Secure Browser Reply Flow

Bob can reply securely without software installation:
1. Bob drafts his response in the browser interface.
2. The browser generates a fresh symmetric key $K_{\text{reply}} \leftarrow \text{CSPRNG}(32)$.
3. If Alice's public key is known, the browser optionally encrypts to Alice's post-quantum public key using compiled WebAssembly ML-KEM-768; otherwise, encrypts with $K_{\text{reply}}$ under AES-256-GCM.
4. The encrypted reply is submitted to the portal.
5. Alice's QuMail desktop client receives notification and downloads/decrypts the reply.

---

## 4. Lifecycle, Replay & Revocation Safeguards

1. **Strict Time-to-Live (TTL):**
   - Default expiration: 7 days. Configurable by sender: 1 to 30 days.
   - Upon reaching `ExpiresUTC`, the portal server's background sweeper permanently zeroizes and deletes $\text{Blob}$ from disk and database.
2. **Sender Revocation Action:**
   - Alice's QuMail client maintains a reference to $M_{\text{id}}$ in her local Outbox/Sent records.
   - If Alice sent an email by mistake, she clicks **Revoke Access** in QuMail.
   - QuMail sends an authenticated revocation instruction signed with Alice's private key.
   - The portal immediately marks $M_{\text{id}}$ as revoked and purges the blob. Future access attempts fail with *"This message was revoked by the sender."*
3. **Replay & Forwarding Protection:**
   - Forwarding the email to a third party does not grant access unless the third party also has access to Bob's inbox to receive the OTP.
   - The link cannot be reused once revoked or expired.

---

## 5. Security Evaluation & Residual Risks

| Threat Scenario | Impact | Mitigation / Residual Risk |
|---|---|---|
| **Portal Database Breach / Compromise** | Attacker dumps all database records. | **ZERO Plaintext Leak:** The database contains only AES-256-GCM ciphertext. The keys ($K_{\text{msg}}$) are never stored on the server. |
| **Mail Server Eavesdropper (Passive MITM)** | Attacker reads emails between Alice and Bob. | The email contains the link with `#key`, but **does NOT contain the OTP**. To decrypt, the attacker must simultaneously compromise the mail transit to intercept the OTP during its 10-minute window. |
| **Compromised Recipient Mailbox** | Attacker has full access to Bob's Gmail. | If Bob's mailbox is compromised, attacker receives both the link and the OTP. *(This is an unavoidable property of any email-based recovery or zero-install system).* |
| **Malicious Portal Code Injection (Active MITM)** | Compromised server modifies JS to exfiltrate `window.location.hash`. | **Residual Risk:** An attacker modifying the portal's served JavaScript could exfiltrate the fragment key. **Mitigation:** Subresource Integrity (SRI), static code signing of web assets, Content Security Policy, and optional passphrase protection supplied by Alice out-of-band. |
| **Post-Quantum Security Status** | Classical AES-256 is quantum-resistant against Grover's algorithm ($2^{128}$ complexity). | The symmetric link encryption is quantum-safe. The transit channel (OTP over standard email/TLS) is classical. |
