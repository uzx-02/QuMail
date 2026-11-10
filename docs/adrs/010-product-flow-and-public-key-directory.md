# ADR 010 — Zero-Friction Product Flow, Public Key Directory & External Recipient Handling

**Status:** Proposed (Under Architecture Review; Implementation Not Authorized)  
**Date:** 2026-11-10  
**Authors:** Antigravity (Implementation Engineer) & Mohammed Uzair Shaikh (Project Owner)  
**Target Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Branch:** `codex/m7-module-1-6-ws06-ws07`  
**Accepted Baseline:** `d3b2078` (WS-06/07 Final Accepted Checkpoint)  

---

## 1. Context and Problem Statement

In early research milestones (M1–M3), cryptographic verification and message sealing were evaluated using a single-machine developer harness where Alice and Bob's accounts were alternately selected within the same local vault to export and import public certificates.

With the acceptance of **M7 Module 1.6 (WS-01 through WS-07)** at checkpoint `d3b2078` (verified by 223 passing modern regression tests), QuMail provides a complete three-pane desktop email client, background IMAP synchronization, a durable outbox, Windows MSI/Inno packaging, and Group Policy management.

However, as QuMail prepares for multi-workstation deployments across distinct users, two operational realities emerge:
1. **The Adoption Friction of Out-of-Band Key Sharing:** Non-technical employees communicating between personal or unmanaged mail domains (e.g., Alice on `@gmail.com` and Bob on `@outlook.com`) have no shared Active Directory or OpenPGP Web Key Directory (WKD) server. Requiring manual key file exchange before the first encrypted email impedes product adoption.
2. **The Non-User Recipient Problem:** If Alice emails Bob, and Bob does not use QuMail, requiring Bob to download and install a desktop Windows application simply to read one communication causes severe recipient abandonment.

---

## 2. Evaluation of Alternative Approaches

### 2.1 Rejected Option: In-Band Asynchronous Email Handshake (Automated SMTP Ping-Pong)
An automated 3-way handshake over email (Alice auto-sends public key $\rightarrow$ Bob's QuMail auto-replies with his key $\rightarrow$ Alice encrypts and sends the original message) was evaluated and **rejected**:
- **Offline Recipient Latency:** If Bob's laptop is asleep, Alice's confidential message sits frozen in her outbox for hours or days.
- **Gmail Bot & Abuse Filters:** Rapid automated back-and-forth emails between newly contacted addresses trigger Google Workspace / M365 bot detection, risking account suspension.
- **Inbox Clutter on Secondary Devices:** Mobile apps (iOS Mail, Gmail mobile) display machine-generated handshake emails in plain text.
- **Mail Loops & Quota Risk:** Auto-responders ("Out of Office") trigger infinite loops, exhausting daily SMTP quotas.

### 2.2 Investigated Architecture: The Two-Pillar Product Model
The project owner approved investigation of the **Two-Pillar Product Model** (similar to ProtonMail, Virtru, and Microsoft 365 Purview):
- **Pillar 1 (QuMail-to-QuMail):** Automatic public key lookup via a dedicated QuMail Public Key Directory.
- **Pillar 2 (QuMail-to-External):** Ephemeral Secure Web Link with browser-side decryption and OTP verification for non-QuMail recipients.

---

## 3. Cryptographic Invariants & Compatibility Decisions

1. **Strict Cryptographic Profile Preservation:**
   - The directory and web link workflows **MUST preserve 100% compatibility** with QuMail's accepted wire profile `QM-OPENPGP-PQ-v1` (RFC 9580 / draft-ietf-openpgp-pqc):
     - Encryption: Composite `ML-KEM-768` + `X25519`
     - Signatures: Composite `ML-DSA-65` + `Ed25519` (or `Ed25519` standalone primary certification)
     - Symmetric Cipher: `AES-256-GCM`
   - No algorithmic downgrade, provider substitution, or classical-only fallback is permitted.
2. **Zero Server Plaintext Visibility:**
   - The directory server and the web link portal server are treated as **untrusted transport infrastructure**.
   - Neither server possesses decryption keys or access to unencrypted message bodies.
   - All message encryption occurs client-side in the native provider (`qumail-m5-provider.exe`); decryption occurs either in the desktop client or in client-side browser WebAssembly via URL fragment keys.
3. **Local Vault Protection Preserved:**
   - Existing M3 vault structures, DPAPI boundaries, M4 outbox semantics, and M5 MIME parsers remain untouched.
   - Endpoint private keys, master secrets, and OAuth credentials never reach any server.

---

## 4. Public Key Directory Architecture (Pillar 1)

Detailed specification: [`docs/operations/public-key-directory-protocol-specification.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/public-key-directory-protocol-specification.md)

1. **Transferable Public Key (TPK) Format:** Standard OpenPGP packet sequence containing primary key, user ID, self-signatures, and post-quantum subkeys.
2. **Authenticated Registration & Proof of Possession (PoP):**
   - Registration requires cryptographic Proof of Key Possession (PoP) by signing a server-generated nonce using the primary private key.
   - Email identity ownership is established via Google OAuth OIDC ID token or an email-based confirmation challenge.
3. **Replacement & Key Rotation Protection:**
   - Directory maintains an append-only, versioned record log (`generation`).
   - Updating a public key requires a signature from the *previous* active primary key OR an administrative enterprise recovery ceremony. Rogue key substitution is blocked.
4. **Directory Authenticity:** Lookups return a signed Directory Claim verified against a pinned `QuMailDirectoryAuthorityKey`.
5. **Privacy & Abuse Safeguards:** Lookups use blinded/hashed identifiers (HMAC-SHA256) to prevent bulk directory scraping. Strict token-bucket rate limiting is enforced per IP and per account.
6. **Trust Indicators (WS-02 Contract):** Directory-retrieved keys without corporate CA certification display the amber **`CAUTION: Identity Unverified`** badge. Keys provisioned via corporate Group Policy (WS-07) display the emerald green **`SECURE`** badge.

---

## 5. Secure Web Link Portal Architecture (Pillar 2)

Detailed specification: [`docs/operations/secure-web-link-threat-model-and-protocol.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/secure-web-link-threat-model-and-protocol.md)

1. **Client-Side Key Generation at Sender:**
   - Sender generates ephemeral symmetric key $K_{\text{msg}} \leftarrow \text{CSPRNG}(256)$.
   - Encrypts body and attachments with AES-256-GCM. Signs ciphertext digest with sender's Ed25519 key.
2. **Zero-Knowledge Key Delivery (URL Hash Fragment):**
   - Ciphertext blob is uploaded to ephemeral portal storage.
   - $K_{\text{msg}}$ is embedded **exclusively in the URL fragment identifier (`#key`)**:
     `https://portal.qumail.invalid/view/<MessageID>#<KeyFragment>`
   - RFC 3986 mandates that URL fragments are never sent to the web server in HTTP requests. The server remains blind to the decryption key.
3. **OTP Identity Verification:**
   - Recipient proves inbox ownership by submitting a time-limited 6-digit OTP sent to their email before receiving the encrypted ciphertext.
4. **Browser-Side Sandboxed Decryption:**
   - Client-side WebAssembly / Web Cryptography API (`crypto.subtle`) extracts $K_{\text{msg}}$ from `window.location.hash`, decrypts the ciphertext, and renders plain text inside a sandboxed `<iframe>` with scripts and remote asset loading disabled.
5. **Secure Replies:** Recipient replies are encrypted client-side in the browser before transmission back to the sender.
6. **Strict Lifecycle:** Ephemeral retention (default 7 days), sender revocation support, and immediate tombstoning after expiration.

---

## 6. Implementation Boundaries & Pilot Strategy

1. **No Production Deployment Without Separate Authorization:**
   - The directory and web portal will **NOT** be deployed to public production environments or registered with live user keys until this architecture review is formally accepted.
2. **Zero-Cost Pilot Architecture:**
   - For initial controlled evaluation (10–50 clients), the directory and portal backends can be hosted on zero-cost tiers (Render.com, Cloudflare Workers) using SQLite storage and automated HTTPS certificates.
3. **Release Gates:**
   - Commercial Authenticode Code-Signing certificate required for Windows installer distribution.
   - Google OAuth CASA Tier 2 verification required before public production Gmail release.
   - Third-party cryptographic audit required before enterprise security claims.

---

## 7. Status and Governance

- **Decision Status:** **PROPOSED** — Awaiting formal Technical Lead review.
- **Implementation Status:** No code modifications permitted until architecture review sign-off.
- **Preserved History:** Baseline `d3b2078` and all M1–M7 invariants preserved intact.
