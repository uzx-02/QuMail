# QuMail M8 — Architecture Review Resolution Report

**Milestone:** M8 Architecture Proposal  
**Document:** Technical Review Findings & Design Resolution Matrix  
**Status:** Architecture Proposal (Under Review; Implementation Deferred)  
**Author:** Antigravity (Implementation Engineer) & Mohammed Uzair Shaikh (Project Owner)  
**Target Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Date:** 2026-11-10  
**Accepted Baseline:** `d3b2078` (WS-06/07 Final Accepted Checkpoint)  
**Documentation Checkpoint:** `3cd4845`  
**Reference ADR:** [`docs/adrs/010-product-flow-and-public-key-directory.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/adrs/010-product-flow-and-public-key-directory.md)  

---

## 1. Overview and Executive Summary

This document provides a line-by-line resolution matrix addressing each security critique and architectural finding raised by the Technical Lead during the M8 Architecture Review of checkpoint `3cd4845`.

All corresponding design specifications have been updated across the architectural suite:
- [`docs/adrs/010-product-flow-and-public-key-directory.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/adrs/010-product-flow-and-public-key-directory.md)
- [`docs/operations/public-key-directory-protocol-specification.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/public-key-directory-protocol-specification.md)
- [`docs/operations/secure-web-link-threat-model-and-protocol.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/secure-web-link-threat-model-and-protocol.md)
- [`docs/operations/m8-milestone-boundaries-and-acceptance-criteria.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/m8-milestone-boundaries-and-acceptance-criteria.md)

No implementation code was written, no servers were deployed, and the accepted M7 baseline ([`d3b2078`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail)) remains strictly untouched.

---

## 2. Review Findings & Resolution Matrix

| # | Review Finding | Architectural Flaw / Critique | Design Change & Resolution | Updated Document Section |
|---|---|---|---|---|
| **2.1** | **Lookup Privacy & Directory Enumeration** | The shared `K_directory_blind` HMAC model is ineffective; any client holding the key can brute-force dictionary lists offline and enumerate all users. | Evaluated OPRF (RFC 9497 / VOPRF) and PIR. Selected for pilot: **Authenticated Query Model** over TLS 1.3 with strict token-bucket rate limits (60/min account, 120/min IP) and a zero-query-log server policy. Explicitly documented operator visibility (social graph metadata). | [`public-key-directory-protocol-specification.md §3.2`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/public-key-directory-protocol-specification.md#32-operation-2-lookup-privacy--authenticated-query-model) |
| **2.2** | **Proof of Key Possession (PoP) Strengthening** | PoP lacked binding to normalized email, audience, profile version, and expiry; downgraded composite identities to Ed25519-only signatures. | Bound PoP payload to: single-use CSPRNG $N_{\text{chal}}$, normalized email (RFC 5321/6531 lowercase/NFC), primary fingerprint, profile version `"QM-OPENPGP-PQ-v1"`, audience `"urn:qumail:directory:pop:v1"`, and expiry. Enforced **composite `ML-DSA-65` + `Ed25519`** signature verification for composite identities (no downgrade permitted). | [`public-key-directory-protocol-specification.md §3.1`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/public-key-directory-protocol-specification.md#31-operation-1-account-registration--proof-of-key-possession-pop) |
| **2.3** | **Cryptographic Merkle Tree Transparency** | Simple append-only database is not cryptographic transparency; TOFU does not authenticate first contact or prevent equivocation. | Implemented RFC 6962 / RFC 9162 binary Merkle tree with domain-separated leaf (`0x00`) and node (`0x01`) hashing, Signed Tree Heads (STH), $O(\log N)$ inclusion proofs, and consistency proofs. Desktop clients cache STH checkpoints and alarm on history rewrite. Explicitly documented that TOFU only detects post-first-contact changes. Directory keys remain amber `CAUTION` without enterprise CA. | [`public-key-directory-protocol-specification.md §3.3`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/public-key-directory-protocol-specification.md#33-operation-3-cryptographic-merkle-tree-transparency) |
| **2.4** | **Independent Registration & Key Replacement** | Account ownership and key possession were conflated; end-user confirmation could silently accept rogue key replacements. | Decoupled into independent checks: Account Ownership via OIDC ID token validation (`email_verified=true`) or SMTP challenge token; Key Possession via composite PoP. Key replacements require active primary key signature or Enterprise Recovery Authority. Unexplained replacements trigger a hard, non-dismissible `SECURITY ALERT: Key Substitution Detected` modal blocking email dispatch. | [`public-key-directory-protocol-specification.md §3.1, §3.4`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/public-key-directory-protocol-specification.md#34-operation-4-key-rotation-replacement-protection--trust-indicators) |
| **3.1** | **Trusted Decryptor Delivery & Fragment Exposure** | Portal is treated as untrusted, but serves the decryptor HTML/JS. A compromised origin can modify HTML and strip SRI/CSP to exfiltrate `#key`. | Documented SRI/CSP origin limitations. Adopted **Origin Separation** (immutable static origin for decryptor SPA isolated from dynamic API/storage). Documented fragment exposure risks: browser extensions, browser history (`replaceState` mitigation), corporate email security scanners (SafeLinks), and chat clipboard pasting. | [`secure-web-link-threat-model-and-protocol.md §2.2`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/secure-web-link-threat-model-and-protocol.md#22-trusted-decryptor-delivery-analysis) |
| **3.2** | **Cryptographic Profile Consistency in Web Link** | Web Link sender authentication used Ed25519-only signatures, conflicting with the composite post-quantum profile. | Updated sender authentication to use composite **`ML-DSA-65` + `Ed25519`** signatures over an enveloped metadata tuple binding message ID, sender, recipient, timestamps, and ciphertext SHA-256 hash. Recipient decryptor validates composite signatures against sender's certificate. | [`secure-web-link-threat-model-and-protocol.md §3.1, §3.4`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/secure-web-link-threat-model-and-protocol.md#31-step-1-client-side-symmetrical-sealing--composite-pq-signing-alice) |
| **3.3** | **Complete Reply Protocol** | Incomplete symmetric reply fallback lacked secure key distribution and allowed ambiguous fallback. | Removed symmetric fallback. Specified full WebKEM reply wrapping: recipient browser generates $K_{\text{reply}}$ (AES-256-GCM) and encapsulates it to Alice's composite `ML-KEM-768` + `X25519` subkey via WebAssembly. If Alice's public key is unavailable, reply creation is **blocked**; unencrypted or improperly wrapped replies are refused. | [`secure-web-link-threat-model-and-protocol.md §3.5`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/secure-web-link-threat-model-and-protocol.md#35-step-5-cryptographic-reply-protocol-no-insecure-fallback) |
| **3.4** | **OTP Semantics & Storage Hardening** | OTP was described as identity verification; plain SHA-256 hash was vulnerable to offline brute-force if database dumped. | Redefined OTP as **mailbox-access verification** (proving inbox control, not legal identity). Replaced plain SHA-256 with server-secret keyed HMAC: $\text{HMAC-SHA256}(K_{\text{server\_otp\_secret}}, \text{OTP} \parallel M_{\text{id}} \parallel \text{Salt})$. Documented inherent limitation that recipient mailbox compromise exposes both link and OTP. | [`secure-web-link-threat-model-and-protocol.md §3.3`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/secure-web-link-threat-model-and-protocol.md#33-step-3-mailbox-verification-via-keyed-hmac-otp) |
| **3.5** | **Retention, Deletion & Cryptographic Erasure** | Claims of absolute "permanent zeroization" ignored replicas, backups, logs, and cryptographic erasure limits. | Authored realistic retention and deletion contract defining primary database hard deletion, object replica lifecycle rules, 14–30 day backup rotation cycles, 30-day access log purging, and explicit cryptographic erasure limits for backed-up ciphertexts. | [`secure-web-link-threat-model-and-protocol.md §4`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/secure-web-link-threat-model-and-protocol.md#4-retention-deletion--cryptographic-erasure-contract) |
| **4.1** | **Workstream Consolidation & Implementation Sequence** | Discrepancy between executive summary and milestone document; premature portal implementation before security sign-off. | Consolidated all architectural documents to the preferred 5-workstream roadmap: **WS01** (Directory backend), **WS02** (Desktop directory integration), **WS03** (Multi-device QuMail-to-QuMail acceptance), **WS04** (Secure Web Link protocol redesign), **WS05** (Portal implementation & pilot). Secure Web Link implementation is gated behind formal approval of WS04. Measurable acceptance criteria established. | [`m8-milestone-boundaries-and-acceptance-criteria.md §2`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/m8-milestone-boundaries-and-acceptance-criteria.md#2-consolidated-workstream-roadmap) |

---

## 3. Detailed Technical Resolutions

### 3.1 Proof of Key Possession (PoP) Binding Structure
The canonical PoP string constructed by the client and validated by the directory server is:
$$\text{NormEmail} = \text{LowerCase}(\text{NFC}(\text{email}))$$
$$\text{PoP-Binding} = \text{SHA256}(\text{"QUMAIL-POP-v1"} \parallel \text{NormEmail} \parallel N_{\text{chal}} \parallel \text{Fingerprint} \parallel \text{"QM-OPENPGP-PQ-v1"} \parallel \text{"urn:qumail:directory:pop:v1"} \parallel T_{\text{issued}} \parallel T_{\text{expires}})$$

If the enrolled identity contains a composite primary key (`ML-DSA-65` + `Ed25519`), the PoP payload MUST include valid signatures under both algorithms:
$$\sigma_{\text{composite}} = (\sigma_{\text{mldsa65}}, \sigma_{\text{ed25519}})$$
Single-algorithm submissions for composite keys fail with HTTP 400.

### 3.2 Binary Merkle Tree Transparency Rules
The transparency log is structured as an append-only binary Merkle tree (RFC 6962 / RFC 9162):
- **Leaf Hash:** $H(\text{leaf}) = \text{SHA256}(0x00 \parallel \text{LeafData})$
- **Interior Node Hash:** $H(\text{node}) = \text{SHA256}(0x01 \parallel \text{LeftChild} \parallel \text{RightChild})$
- **Signed Tree Head (STH):** Root hash and tree size signed by the offline/HSM-backed `DirectoryAuthorityKey`.
- **Client Consistency Check:** Desktop clients cache the latest observed STH in SQLite. On each subsequent query, the client verifies that the tree is an append-only extension ($N \le M$). An inconsistent history halts client directory operations immediately.

### 3.3 Server-Keyed OTP Verification
To defeat offline brute-force attacks against the 6-digit numeric OTP space ($10^6$ combinations) in the event of database exfiltration:
$$\text{OTP\_Verifier} = \text{HMAC-SHA256}(K_{\text{server\_otp\_secret}}, \text{OTP} \parallel M_{\text{id}} \parallel \text{Salt})$$
Verification evaluates this HMAC in constant time. The maximum attempt count is strictly enforced at 3 attempts, after which the message enters permanent lockout.

### 3.4 WebKEM Reply Key Wrapping
The recipient web decryptor encrypts replies client-side without plaintext server exposure:
1. Recipient generates $K_{\text{reply}} \leftarrow \text{CSPRNG}(256)$ and encrypts payload with `AES-256-GCM`.
2. Browser WebAssembly encapsulates $K_{\text{reply}}$ using Alice's composite `ML-KEM-768` + `X25519` public subkey:
   $$SS = \text{HKDF-SHA256}(\text{ML-KEM-SharedSecret} \parallel \text{X25519-SharedSecret})$$
   $$C_{\text{key}} = \text{AES-KeyWrap}(SS, K_{\text{reply}})$$
3. If Alice's public key certificate is missing or invalid, reply creation is prohibited.

---

## 4. Remaining Unresolved Security Assumptions & Residual Risks

The following explicit security assumptions remain inherent to the architecture and must be acknowledged prior to pilot deployment:

1. **Web Decryptor Delivery Origin Trust:**
   - *Residual Risk:* While static origin separation protects against portal database breaches, web-delivered cryptography fundamentally relies on the integrity of the web origin serving the JavaScript code. A compromised web delivery origin could exfiltrate the URL fragment key.
   - *Classification:* Inherent architectural limitation of browser-based zero-install delivery. Enterprise users requiring absolute origin independence must use native QuMail desktop endpoints (Pillar 1).
2. **Mailbox Compromise Exposure (Web Link):**
   - *Residual Risk:* Both the invitation link (containing `#key`) and the OTP verification email are delivered to the recipient's email address. If an adversary compromises the recipient's mail account or IMAP server, they obtain both secrets.
   - *Classification:* Inherent to email-based recovery and verification workflows. Pillar 2 provides transport and storage confidentiality against eavesdroppers and portal hosts, but cannot defend against destination mailbox takeover.
3. **Directory Operator Social Graph Metadata:**
   - *Residual Risk:* In the initial pilot Authenticated Query Model, the directory operator can observe which authenticated user accounts query specific target email addresses.
   - *Mitigation:* Zero-query-log policy on directory servers; OPRF / Private Information Retrieval (PIR) scheduled as a future scale-out roadmap item.
4. **Cryptographic Erasure & Backup Persistence:**
   - *Residual Risk:* Ciphertext blobs in database point-in-time recovery backups persist until cyclical backup rotation (14–30 days). An attacker who obtained the URL link during transit could theoretically decrypt a restored backup blob until the backup expires.

---

## 5. Governance and Implementation Gate

- **M7 Baseline Preservation:** Checkpoint [`d3b2078`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail) remains the authoritative accepted implementation.
- **Implementation Status:** Gated. No M8 service implementation, server deployment, or code modification is authorized until the Technical Lead reviews and signs off on this resolution package.
