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

## 1. Problem Statement & Operational Context

QuMail's primary wire format (`QM-OPENPGP-PQ-v1`) provides end-to-end post-quantum encryption between QuMail desktop endpoints. However, in enterprise and commercial workflows, employees must frequently communicate confidential materials to external recipients (clients, outside counsel, auditors) who do not run QuMail.

Forcing an external correspondent to install desktop software simply to read a single communication causes severe friction and workflow abandonment.

The **Secure Web Link Portal** provides a zero-install recipient experience while enforcing client-side symmetrical sealing, zero-server-plaintext visibility, and composite post-quantum sender authentication.

---

## 2. Threat Model & Security Boundaries

```
+-------------------+           +-------------------------+           +-------------------+
| Alice (Sender)    |           | QuMail Web Portal       |           | Bob (Recipient)   |
| QuMail Desktop    |           | (Untrusted Storage Host)|           | Any Web Browser   |
+-------------------+           +-------------------------+           +-------------------+
        │                                    │                                    │
        │ 1. Upload Encrypted Blob           │                                    │
        ├───────────────────────────────────►│                                    │
        │    (POST /api/v1/portal/stage)     │                                    │
        │                                    │                                    │
        │ 2. Email Link with #KeyFragment    │                                    │
        ├────────────────────────────────────┼───────────────────────────────────►│
        │    (via standard Gmail / SMTP)     │                                    │
        │                                    │ 3. HTTP GET /view/UUID (NO #key!)  │
        │                                    │◄───────────────────────────────────┤
        │                                    │                                    │
        │                                    │ 4. Issue & Keyed-HMAC Verify OTP   │
        │                                    │◄──────────────────────────────────►│
        │                                    │                                    │
        │                                    │ 5. Release Encrypted Blob          │
        │                                    ├───────────────────────────────────►│
        │                                    │                                    │
        │                                    │                                    │ [Browser decrypts
        │                                    │                                    │  using #key locally]
```

### 2.1 Threat Model Entities
1. **Alice (Sender):** Uses the trusted QuMail desktop client on Windows. Executes local key generation, encryption, and composite post-quantum signing.
2. **Bob (Recipient):** Uses an ordinary web browser on desktop or mobile. Does not possess a local QuMail installation or native post-quantum key vault.
3. **QuMail Web Portal Server:** Untrusted cloud infrastructure hosting the storage backend. **Treated as an adversary / untrusted host.**
4. **Mail Transport Agents (MTAs):** Intermediary mail servers (Google, Microsoft, recipient mail server) transmitting the link and OTP.

---

### 2.2 Trusted Decryptor Delivery Analysis

#### 2.2.1 The Untrusted Origin Conundrum
A critical security challenge in browser-delivered cryptography is that the server serving the client application code is itself treated as untrusted:
- **SRI and CSP Limitations:** Subresource Integrity (SRI) and Content Security Policy (CSP) headers are delivered *by the server itself*. If the portal origin is compromised, the attacker can modify `index.html`, strip the CSP header, remove SRI tags, and inject JavaScript that reads `window.location.hash` and exfiltrates $K_{\text{msg}}$.
- **Architectural Safeguards:**
  1. **Origin Separation (Static vs. Dynamic):** The decryptor Single-Page Application (SPA) is hosted on an immutable, static, signed origin (e.g., Cloudflare Pages / AWS S3 static hosting / GitHub Pages with commit pinning) completely separated from the dynamic API and blob storage origin (`portal-api.qumail.invalid`).
  2. **Independent Pinned Verification / Web Extension (Enterprise Mode):** Enterprise recipients can install a lightweight browser extension or verify the decryptor SHA-256 hash before execution.
  3. **Explicit Residual Risk Acknowledgment:** For standard consumer browser sessions without pre-installed extensions, web-delivered cryptography fundamentally depends on the integrity of the web delivery origin at runtime. This is an unavoidable property of zero-install web portals.

#### 2.2.2 Threat Analysis of URL Fragment (`#`) Exposure
While RFC 3986 §3.5 guarantees that fragment identifiers are not transmitted in HTTP request lines, fragments can still be exposed via side channels:
1. **Malicious Browser Extensions:** Extensions with `<all_urls>` or `tabs` permissions can read the full URL including the fragment via `chrome.tabs.get()`.
2. **Browser History Persistence:** Browsers can persist URLs in local history files unless sanitized. Mitigation: The decryptor application calls `window.history.replaceState(null, "", window.location.pathname)` immediately upon extracting the key.
3. **Enterprise Email Security Scanners (SafeLinks / Mimecast / Proofpoint):** Security appliances rewrite URLs. While the fragment is preserved client-side, dynamic sandbox scanners clicking through the link could execute the decryptor in a remote crawler environment.
4. **User Clipboard & Chat Sharing:** Users copying the link from the email and pasting it into corporate Slack, Microsoft Teams, or ticketing systems leak the decryption key to those third-party platforms.

---

## 3. Cryptographic Protocol Specification

### 3.1 Step 1: Client-Side Symmetrical Sealing & Composite PQ Signing (Alice)

When Alice composes an email to an external non-QuMail recipient:
1. **Ephemeral Symmetric Key Generation:**
   $$K_{\text{msg}} \leftarrow \text{CSPRNG}(256\text{ bits})$$
   $$\text{IV} \leftarrow \text{CSPRNG}(96\text{ bits})$$
   $$M_{\text{id}} \leftarrow \text{UUIDv4}()$$
2. **Payload Encryption (AES-256-GCM):**
   $$(C_{\text{body}}, T_{\text{tag}}) = \text{AES-256-GCM-Encrypt}(K_{\text{msg}}, \text{IV}, \text{PlaintextMessage}, \text{AAD})$$
   Where $\text{AAD} = \text{UTF8}(M_{\text{id}} \parallel \text{AliceEmail} \parallel \text{BobEmail} \parallel T_{\text{timestamp}} \parallel T_{\text{expiry}})$.
3. **Composite Post-Quantum Sender Authentication:**
   To maintain cryptographic consistency with `QM-OPENPGP-PQ-v1`, Alice authenticates the message using her composite `ML-DSA-65` + `Ed25519` signing keys:
   $$\text{MetadataTuple} = \text{"QM-WEBLINK-v1"} \parallel M_{\text{id}} \parallel \text{AliceEmail} \parallel \text{BobEmail} \parallel T_{\text{timestamp}} \parallel T_{\text{expiry}} \parallel \text{SHA256}(C_{\text{body}} \parallel T_{\text{tag}})$$
   $$\sigma_{\text{composite}} = (\text{ML-DSA-65-Sign}(SK_{\text{mldsa}}, \text{MetadataTuple}), \text{Ed25519-Sign}(SK_{\text{ed25519}}, \text{MetadataTuple}))$$
4. **Ciphertext Blob Assembly:**
   $$\text{Blob} = \{M_{\text{id}}, \text{IV}, C_{\text{body}}, T_{\text{tag}}, \text{AAD}, \sigma_{\text{composite}}, \text{AliceCertificateArmor}, T_{\text{expiry}}\}$$

---

### 3.2 Step 2: Blob Staging & Fragment URL Construction

1. **Blob Upload:** Alice's client uploads $\text{Blob}$ to the portal storage over TLS 1.3:
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
2. **Key Omission Invariant:** $K_{\text{msg}}$ is **NOT** included in the upload payload. The portal receives **only** ciphertext and public metadata.
3. **Access URL Generation:**
   $$\text{AccessURL} = \texttt{https://portal-app.qumail.invalid/view/}M_{\text{id}}\texttt{\#}K_{\text{msg\_hex}}$$
4. **Email Invitation:** Alice's client sends the invitation email via her normal mail transport containing $\text{AccessURL}$.

---

### 3.3 Step 3: Mailbox Verification via Keyed-HMAC OTP

Before releasing the encrypted blob, the portal verifies mailbox access (proving inbox control, not legal identity):
1. **Challenge Generation:** Portal generates a 6-digit numeric OTP:
   $$\text{OTP} \leftarrow \text{CSPRNG}(6\text{ digits})$$
2. **Keyed Verification Storage:**
   To prevent offline dictionary brute-forcing ($10^6$ combinations) if the portal database is dumped, the OTP is stored using a server-secret keyed HMAC:
   $$\text{OTP\_Verifier} = \text{HMAC-SHA256}(K_{\text{server\_otp\_secret}}, \text{OTP} \parallel M_{\text{id}} \parallel \text{Salt})$$
3. **Delivery & Rate Limiting:**
   - OTP transmitted via SMTP to `bob@externalcorp.invalid`.
   - Validity: Strict 10-minute expiry.
   - Attempt Limit: Maximum 3 failed attempts. Upon the 3rd failure, the message enters permanent lockout.
4. **Mailbox Compromise Inherent Limitation:** If an attacker compromises Bob's email account, they obtain both the link (with `#key`) and the OTP email, allowing complete message decryption.

---

### 3.4 Step 4: Browser Decryption & Sandboxed Rendering

1. **Key Extraction & Sanitization:**
   - Browser script reads $K_{\text{msg}}$ from `window.location.hash`.
   - Immediately invokes `window.history.replaceState(null, "", window.location.pathname)` to erase the fragment from URL history.
2. **WebCrypto Decryption:**
   - Browser calls `crypto.subtle.decrypt({ name: "AES-GCM", iv, additionalData: AAD }, key, ciphertext)`.
   - If authentication tag verification fails, execution halts closed.
3. **Composite Sender Signature Validation:**
   - Browser parses `AliceCertificateArmor`, validates Alice's composite `ML-DSA-65` and `Ed25519` public keys against the user ID.
   - Verifies $\sigma_{\text{composite}}$ over $\text{MetadataTuple}$.
   - Displays sender verification badge: Green **`VERIFIED POST-QUANTUM SENDER`** or Amber **`SIGNATURE UNVERIFIED`**.
4. **Sandboxed Plain-Text Rendering:**
   - Decrypted message is rendered inside an isolated `<iframe>`:
     ```html
     <iframe sandbox="allow-same-origin" srcdoc="..."></iframe>
     ```
   - Enforces strict Content Security Policy:
     `default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src data:; connect-src 'self';`

---

### 3.5 Step 5: Cryptographic Reply Protocol (No Insecure Fallback)

To ensure confidential bidirectional replies without requiring software installation:
1. **Public Key Retrieval:**
   The decryptor extracts Alice's composite `ML-KEM-768` + `X25519` public subkey from `AliceCertificateArmor` (or queries the Directory).
2. **Key Encapsulation & Sealing:**
   - Browser generates a fresh symmetric key $K_{\text{reply}} \leftarrow \text{CSPRNG}(256)$.
   - Browser encrypts the reply body and attachments with `AES-256-GCM` using $K_{\text{reply}}$.
   - Browser encapsulates $K_{\text{reply}}$ to Alice's composite public subkey using WebAssembly:
     $$(C_{\text{kem}}, SS_{\text{kem}}) = \text{ML-KEM-768-Encaps}(PK_{\text{Alice\_kem}})$$
     $$(C_{\text{x25519}}, SS_{\text{x25519}}) = \text{X25519-Encaps}(PK_{\text{Alice\_x25519}})$$
     $$K_{\text{wrap}} = \text{HKDF-SHA256}(SS_{\text{kem}} \parallel SS_{\text{x25519}}, \text{info}=\text{"QM-REPLY-WRAP-v1"})$$
     $$C_{\text{key}} = \text{AES-KeyWrap}(K_{\text{wrap}}, K_{\text{reply}})$$
3. **Replay & Thread Binding:**
   - The reply payload binds original $M_{\text{id}}$, thread ID, monotonic reply sequence number, and timestamp in its authenticated data.
4. **Mandatory Failure Behavior:**
   - If Alice's public key certificate is missing, malformed, or fails signature validation, reply creation is **BLOCKED**.
   - **No Unencrypted Fallback:** The web portal refuses to accept an unencrypted or improperly encapsulated reply.

---

## 4. Retention, Deletion & Cryptographic Erasure Contract

| Layer | Deletion Contract | Retention Window |
|---|---|---|
| **Primary Storage (DB/Blobs)** | Hard record deletion upon expiry (`ExpiresUTC`) or sender revocation. | Max 30 days (default 7 days). |
| **Object Storage Replicas** | Automated bucket lifecycle expiration rules purge all blob fragments. | Purged within 24 hours of primary deletion. |
| **Database Backups** | Point-in-time recovery backups overwrite expired records cyclically. | Retained 14 to 30 days. |
| **Server Access Logs** | RFC-compliant servers log request paths (`/api/v1/portal/stage`) without `#fragments`. | Retained 30 days for abuse detection, then purged. |
| **Cryptographic Erasure Limitations** | If ciphertext survives in a database backup, an adversary who captured the URL link from email transit could decrypt the backup blob until the backup expires. | Permanent confidentiality relies on backup lifecycle purging. |
