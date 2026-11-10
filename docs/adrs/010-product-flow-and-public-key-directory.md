# ADR 010 — Zero-Friction Product Flow, Public Key Directory & External Recipient Handling

**Status:** Proposed (Under Architecture Review; Implementation Not Authorized)  
**Date:** 2026-11-10  
**Authors:** Antigravity (Implementation Engineer) & Mohammed Uzair Shaikh (Project Owner)  
**Target Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Branch:** `codex/m7-module-1-6-ws06-ws07`  
**Accepted Baseline:** `d3b2078` (WS-06/07 Final Accepted Checkpoint)  
**Documentation Checkpoint:** `3cd4845`  

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

### 2.2 Adopted Direction: The Two-Pillar Product Model
The project owner approved architectural investigation of the **Two-Pillar Product Model** (conceptually aligned with modern secure communication architectures such as ProtonMail, Virtru, and Microsoft Purview Message Encryption):
- **Pillar 1 (QuMail-to-QuMail):** Automated discovery and sealing using the composite post-quantum OpenPGP wire profile via a centralized, verifiable QuMail Public-Key Directory.
- **Pillar 2 (QuMail-to-External):** Ephemeral Secure Web Link with client-side symmetric encryption, URL-fragment key delivery, server-keyed OTP mailbox verification, and browser-side sandboxed decryption for non-QuMail recipients.

---

## 3. Cryptographic Invariants & Architectural Rules

1. **Strict Cryptographic Profile Preservation:**
   - Both pillars **MUST preserve 100% compatibility** with QuMail's accepted wire profile `QM-OPENPGP-PQ-v1` (RFC 9580 / draft-ietf-openpgp-pqc):
     - Encryption Subkey: Composite `ML-KEM-768` + `X25519`
     - Signing Key: Composite `ML-DSA-65` + `Ed25519` (or `Ed25519` standalone primary certification)
     - Symmetric Cipher: `AES-256-GCM`
   - No algorithmic downgrade, provider substitution, or classical-only fallback is permitted.
2. **Zero Server Plaintext Visibility:**
   - The directory server and the web portal server are treated as **untrusted transport infrastructure**.
   - Neither server possesses private decryption keys or access to unencrypted message bodies.
   - All message encryption occurs client-side in the native provider (`qumail-m5-provider.exe`); decryption occurs either in the desktop client or in client-side browser WebCrypto via URL fragment keys.
3. **Local Vault Protection Preserved:**
   - Existing M3 vault structures, DPAPI boundaries, M4 outbox semantics, and M5 MIME parsers remain untouched.
   - Endpoint private keys, master secrets, and OAuth credentials never reach any server.

---

## 4. Public Key Directory Architecture (Pillar 1)

Detailed specification: [`docs/operations/public-key-directory-protocol-specification.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/public-key-directory-protocol-specification.md)

1. **Transferable Public Key (TPK) Format:** Standard OpenPGP packet sequences strictly adhering to `QM-OPENPGP-PQ-v1`.
2. **Independent Account Ownership & Proof of Key Possession (PoP):**
   - **Account Ownership:** Verified independently via OAuth OIDC ID token validation (`email_verified=true`, unexpired, matching audience) or a single-use 256-bit activation challenge sent via email.
   - **Cryptographic PoP:** The client signs a single-use server challenge bound to normalized email, primary fingerprint, profile version (`QM-OPENPGP-PQ-v1`), protocol audience (`urn:qumail:directory:pop:v1`), and expiry.
   - **No Cryptographic Downgrade:** When enrolling a composite `ML-DSA-65` + `Ed25519` identity, the PoP signature MUST use the composite signing profile.
3. **Lookup Privacy & Directory Enumeration Protection:**
   - Evaluated OPRF-based lookup (RFC 9497 / VOPRF) and Private Information Retrieval (PIR) for future roadmap integration.
   - Selected for initial pilot: **Authenticated Query Model** over TLS 1.3 with strict per-account (60 queries/min) and per-IP subnet (120 queries/min) token-bucket rate limits.
   - **Explicit Limitation:** Shared HMAC keys do not prevent enumeration by authenticated clients; the directory operator observes which authenticated accounts query which email addresses. Plaintext query targets are not persisted in access logs.
4. **Merkle Tree Cryptographic Transparency:**
   - Directory replaces simple append-only tables with a binary Merkle tree (RFC 6962 / RFC 9162).
   - Issues Signed Tree Heads (STH) signed by `DirectoryAuthorityKey`.
   - Returns $O(\log N)$ inclusion proofs for registered keys; clients verify consistency proofs between cached checkpoints.
   - Independent monitors crawl the tree to detect split-view equivocation.
5. **Key Replacement & Trust Indicator Rules:**
   - **TOFU Limitation:** Trust-On-First-Use detects changes after first contact, but does NOT authenticate first contact or prevent first-contact equivocation.
   - Keys fetched from the directory without corporate CA certification display the amber **`CAUTION: Identity Unverified`** badge.
   - Only keys certified via corporate Group Policy (WS-07) or enterprise CA display the emerald green **`SECURE`** badge.
   - Unexplained primary key replacement triggers a hard, non-dismissible **`SECURITY ALERT: Key Substitution Detected`** dialog requiring out-of-band verification.

---

## 5. Secure Web Link Portal Architecture (Pillar 2)

Detailed specification: [`docs/operations/secure-web-link-threat-model-and-protocol.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/secure-web-link-threat-model-and-protocol.md)

1. **Client-Side Key Generation & Symmetrical Sealing:**
   - Sender generates ephemeral symmetric key $K_{\text{msg}} \leftarrow \text{CSPRNG}(256)$ and nonce $IV \leftarrow \text{CSPRNG}(96)$.
   - Encrypts payload with `AES-256-GCM`.
2. **Composite Post-Quantum Sender Authentication:**
   - Sender signs message envelope metadata using composite `ML-DSA-65` + `Ed25519` signing keys.
   - Recipient decryptor validates composite signatures against sender's certificate before presenting the message.
3. **Zero-Knowledge Key Delivery via URL Hash Fragment:**
   - Ciphertext blob uploaded to ephemeral portal storage; $K_{\text{msg}}$ is omitted from the server payload.
   - Access URL: `https://portal-app.qumail.invalid/view/<MessageID>#<KeyFragment>`
   - RFC 3986 mandates user agents never send `#fragment` in HTTP requests.
   - **Threat Analysis of Fragment Exposure:** Documented exposure vectors including browser extensions, browser history persistence, clipboard copying, and corporate URL scanners (Proofpoint/Mimecast).
4. **Untrusted Portal & Decryptor Delivery Integrity:**
   - Explains why SRI and CSP alone cannot protect against a compromised origin (an attacker modifying the HTML root strips SRI and CSP).
   - Solution: Decryptor SPA served from an immutable, separately authenticated static origin (e.g., Cloudflare Pages / signed static origin) isolated from dynamic API/storage servers.
5. **Server-Keyed OTP Mailbox Verification:**
   - OTP proves mailbox access, NOT legal identity.
   - Verified via server-secret keyed HMAC: $\text{HMAC-SHA256}(K_{\text{server\_otp\_secret}}, \text{OTP} \parallel M_{\text{id}} \parallel \text{Salt})$ to defeat offline brute-force attacks on leaked databases.
   - 10-minute validity, maximum 3 attempts before permanent lockout.
   - **Inherent Limitation:** Mailbox compromise exposes both the invitation link and OTP.
6. **Complete Cryptographic Reply Protocol:**
   - Recipient browser encapsulates a fresh symmetric key $K_{\text{reply}}$ to Alice's composite `ML-KEM-768` + `X25519` public subkey.
   - If Alice's public key certificate is unavailable, reply creation is **blocked** (no unauthenticated fallback permitted).
7. **Realistic Retention & Deletion Contract:**
   - Specifies primary database hard deletion, replica lifecycle policies, backup retention windows, access log rotation (30 days), and cryptographic erasure limitations.

---

## 6. Implementation Boundaries & Pilot Strategy

1. **No Implementation Without Review:**
   - Implementation of M8 services remains strictly stopped pending formal Technical Lead sign-off.
2. **Implementation Sequence & Approval Gate:**
   - Sequential execution: Directory backend $\rightarrow$ Desktop directory integration $\rightarrow$ Multi-device QuMail-to-QuMail acceptance $\rightarrow$ Secure Web Link protocol redesign $\rightarrow$ Portal implementation & pilot.
   - Secure Web Link implementation is gated behind a separate security-design approval gate.
3. **External Release Gates:**
   - Commercial Authenticode EV Code-Signing certificate for Windows installers.
   - Google CASA Tier 2 verification for production Gmail OAuth scopes.
   - Independent third-party cryptographic review before enterprise production release.

---

## 7. Status and Governance

- **Decision Status:** **PROPOSED** — Awaiting formal Technical Lead review.
- **Implementation Status:** Gated. No code modifications permitted until architecture review sign-off.
- **Preserved History:** Baseline `d3b2078` and all M1–M7 invariants preserved intact.
