# QuMail M8 — Milestone Boundaries, Workstreams & Acceptance Criteria

**Milestone:** M8 — Enterprise Pilot, Public Key Directory & Zero-Friction Web Delivery  
**Document:** M8 Milestone Boundaries, Workstreams & Acceptance Criteria  
**Status:** Architecture Proposal (Under Review; Implementation Deferred)  
**Author:** Antigravity (Implementation Engineer) & Mohammed Uzair Shaikh (Project Owner)  
**Target Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Date:** 2026-11-10  
**Accepted Baseline:** `d3b2078` (WS-06/07 Final Accepted Checkpoint)  
**Reference ADR:** [`docs/adrs/010-product-flow-and-public-key-directory.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/adrs/010-product-flow-and-public-key-directory.md)  

---

## 1. Milestone Mission & Scope Definition

Milestone **M8** expands QuMail from a verified standalone Windows desktop client into an enterprise-ready ecosystem supporting real-world pilot deployments across both QuMail users and external correspondents.

### 1.1 Invariants and Constraints
- **Preserve M7 Baseline:** All existing M1–M7 cryptographic providers (`qumail-m3-provider`, `qumail-m5-provider`), local SQLite vaults, DPAPI credential boundaries, M4 outbox state machines, and M5 OpenPGP-PQ wire specifications remain strictly intact.
- **Zero Server Decryption:** Neither the directory server nor the web portal server may possess decryption capabilities or observe plaintext message bodies.
- **Implementation Gate:** No M8 code implementation or server deployment will begin until this architecture package is formally approved by the Technical Lead.

---

## 2. Consolidated Workstream Roadmap

The M8 milestone is executed across five sequential workstreams. Secure Web Link implementation (WS05) is gated behind a formal security-design review of WS04.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ M8-WS01: Public-Key Directory Protocol & Backend                            │
│ (FastAPI, SQLite, Merkle Tree Transparency Log, Composite PoP, Rate Limits)  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ M8-WS02: Desktop Client Directory Integration & Trust Behavior              │
│ (Key Pinning, TOFU Handling, Amber/Green Trust Badges, Substitution Alarms) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ M8-WS03: Multi-Device QuMail-to-QuMail Acceptance & Pilot Verification       │
│ (Independent Multi-Device Sealing/Decryption, Key Rotation, Revocation Sync)│
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ M8-WS04: Secure Web Link Protocol Redesign & Security Review                │
│ [SECURITY-DESIGN APPROVAL GATE — NO PORTAL CODE WRITTEN BEFORE SIGN-OFF]     │
│ (Composite PQ Sender Authentication, WebKEM Reply Wrapping, Keyed OTP Spec) │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (Gate Passed)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ M8-WS05: Secure Web Link Portal Implementation & Controlled Pilot           │
│ (Static Decryptor Origin, Keyed-HMAC OTP Backend, Controlled Pilot Staging) │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### M8-WS01: Public-Key Directory Protocol & Backend
* **Objective:** Implement the server-side public-key directory service with Merkle tree transparency.
* **Deliverables:**
  - `services/directory/server.py`: FastAPI / SQLite service with TLS 1.3.
  - Independent identity verification (Google/Microsoft OAuth OIDC token validation or SMTP challenge token).
  - Cryptographically bound Proof of Key Possession (PoP) verifying composite `ML-DSA-65` + `Ed25519` signatures.
  - Binary Merkle Tree implementation (RFC 6962 / RFC 9162) issuing Signed Tree Heads (STH), inclusion proofs, and consistency proofs.
  - Authenticated query model with token-bucket rate limiting (60 queries/min per account, 120 queries/min per IP subnet) and zero-query-log policy.
* **Measurable Acceptance Criteria:**
  1. Submitting valid `QM-OPENPGP-PQ-v1` certificate with matching composite PoP signature passes verification and appends a leaf to the Merkle tree.
  2. Submitting an expired challenge nonce, altered email binding, or classical-only Ed25519 signature for a composite identity fails with HTTP 400 Bad Request.
  3. Attempting to overwrite an existing user's record without a signature from the previous primary key or enterprise recovery authority fails with HTTP 409 Conflict.
  4. Lookup returns valid $O(\log N)$ Merkle inclusion proof verifying against current STH root hash.
  5. Consistency proof between tree size $N$ and $M$ ($N < M$) verifies mathematically; injected inconsistent leaf causes consistency verification failure.

---

### M8-WS02: Desktop Client Directory Integration & Trust Behavior
* **Objective:** Integrate directory discovery and Merkle verification into the desktop application.
* **Deliverables:**
  - `core/directory_client.py`: Client library for registration, lookup, and Merkle checkpoint verification.
  - Local SQLite checkpoint store (`directory_checkpoints` table).
  - Trust-On-First-Use (TOFU) key pinning in `contacts` table.
  - Visual trust indicator alignment:
    - Amber **`CAUTION: Identity Unverified`** badge for directory-discovered keys without corporate CA.
    - Emerald Green **`SECURE`** badge for enterprise GPO / CA certified keys.
  - Blocking UI modal for unexpected key changes (`SECURITY ALERT: Key Substitution Detected`).
* **Measurable Acceptance Criteria:**
  1. Composing to an un-cached recipient performs authenticated directory query, verifies Merkle inclusion proof and STH, and seals message using discovered post-quantum subkey.
  2. Discovered key without enterprise CA displays amber `CAUTION` badge in message inspector.
  3. Modifying a pinned contact's primary key in the directory triggers a hard blocking alert; outbox dispatch is prohibited until explicit out-of-band verification is recorded.
  4. Simulating a directory history rewrite (invalid consistency proof) causes the client to halt directory queries and raise a critical integrity alarm.
  5. Offline directory behavior: cached contacts function seamlessly; uncached recipients hold in Outbox with descriptive status.

---

### M8-WS03: Multi-Device QuMail-to-QuMail Acceptance & Pilot Verification
* **Objective:** Validate end-to-end post-quantum messaging across physically distinct workstations and accounts.
* **Deliverables:**
  - Automated multi-client test harness executing across isolated SQLite vaults and network boundaries.
  - Key rotation and revocation propagation test suite.
  - Multi-workstation pilot deployment guide.
* **Measurable Acceptance Criteria:**
  1. Client A and Client B on distinct virtual workstations enroll with directory, discover each other's keys, and exchange encrypted `QM-OPENPGP-PQ-v1` messages via live IMAP/SMTP without manual key exchange.
  2. Client A rotates subkey; Client B automatically discovers incremented generation, verifies primary transition signature, and seals future messages with new subkey.
  3. Client A revokes subkey; Client B discovers revocation certificate and transitions contact state to `Trust.REVOKED`, refusing further encryption.
  4. Zero cryptographic failures across 100 consecutive message exchanges under varying network latency conditions.

---

### M8-WS04: Secure Web Link Protocol Redesign & Security Review
* **Objective:** Complete cryptographic protocol specification and security threat modeling for external non-QuMail delivery prior to implementation.
* **Deliverables:**
  - Formal protocol specification document covering:
    - Composite `ML-DSA-65` + `Ed25519` sender signature format and identity binding.
    - WebAssembly `ML-KEM-768` + `X25519` key-wrapping reply protocol.
    - Server-secret keyed-HMAC OTP verification design.
    - Threat analysis of URL fragment exposure (extensions, history, proxy scanners).
    - Origin separation architecture isolating static decryptor hosting from dynamic API storage.
  - Security review submission package for Technical Lead review.
* **Measurable Acceptance Criteria:**
  1. Protocol specification eliminates all ambiguous symmetric reply fallbacks.
  2. Sender signature verification format strictly enforces composite post-quantum algorithms.
  3. Cryptographic review completed and formally signed off by the Technical Lead before any web portal code is written.

---

### M8-WS05: Secure Web Link Portal Implementation & Controlled Pilot
* **Objective:** Implement the ephemeral web portal service and browser decryptor in conformance with the approved WS04 design.
* **Deliverables:**
  - `services/portal/server.py`: Ephemeral storage service with server-keyed HMAC OTP verification and automated TTL sweeper.
  - `services/portal/static/`: Static decryptor SPA hosted on an independent static origin, enforcing sandboxed `<iframe>` plain-text rendering and strict CSP.
  - Controlled 10-client pilot verification report.
* **Measurable Acceptance Criteria:**
  1. Sender client seals message with AES-256-GCM and composite signature; generates fragment URL without transmitting key to portal.
  2. Accessing URL triggers 6-digit OTP to recipient email; OTP verified using server-secret keyed HMAC; 3 incorrect attempts permanently locks access.
  3. Web decryptor parses URL fragment, decrypts ciphertext in browser memory via WebCrypto, validates composite sender signatures, and renders inside sandboxed `<iframe>`.
  4. Web decryptor encapsulates reply key using sender's composite `ML-KEM-768` + `X25519` subkey; sender desktop client receives and decrypts reply.
  5. If sender's public key is unavailable, reply creation is strictly blocked.
  6. Expired blobs are permanently deleted from database and disk upon TTL expiration or explicit sender revocation.

---

## 3. Commercial Release Gates (External Prerequisites)

| Gate | Purpose | Owner / Dependency | Status |
|---|---|---|:---:|
| **1. Commercial Code-Signing** | EV Authenticode Certificate for `QuMail.exe` / `QuMailSetup.exe` to eliminate Windows SmartScreen warnings. | CA Purchase / HSM Provisioning | **Prerequisite for Public Windows Distribution** |
| **2. Google OAuth CASA Verification** | Cloud Application Security Assessment (Tier 2) required by Google for public distribution using restricted Gmail scopes. | External Google Auditor (e.g. Bishop Fox / Leviathan) | **Prerequisite for Unlimited Gmail Users** (Private pilot capped at 100 test users) |
| **3. Independent Cryptographic Audit** | Formal external review of native Rust providers, composite PQC wire format, and directory protocols. | Independent Security Firm (e.g. Trail of Bits, Cure53) | **Prerequisite for Enterprise Production Release** |

---

## 4. Explicit Unresolved Security Assumptions & Residual Risks

The following explicit security assumptions and residual risks are documented for Technical Lead review:

1. **Browser Delivery Origin Trust (Untrusted Host Limitation):**
   - Web-delivered cryptography inherently depends on the integrity of the origin serving the JavaScript decryptor. If the static origin hosting the web application is compromised, malicious code could exfiltrate the URL fragment key.
   - *Mitigation:* Static origin separation, optional enterprise browser extension with code-hash pinning.
2. **Mailbox Compromise Exposure (Web Link):**
   - The Secure Web Link model delivers the fragment URL and the OTP to the same destination email address. If an adversary compromises the recipient's email account, they obtain both secrets.
   - *Classification:* Known limitation inherent to all zero-install email encryption portals (Virtru, Cisco CRES, Microsoft Purview). Full security requires native QuMail desktop endpoints (Pillar 1).
3. **Directory Operator Traffic Analysis:**
   - In the initial pilot authenticated-query model, the directory operator can observe which authenticated accounts query specific email addresses, exposing social graph metadata.
   - *Mitigation:* Zero-query-log server policy; OPRF / PIR scheduled for future scale-out roadmap.
4. **Backup Retention & Cryptographic Erasure:**
   - Ciphertext blobs in database point-in-time recovery backups persist until backup cycle rotation (14–30 days). An adversary who intercepted the URL link during transit could theoretically decrypt a restored backup blob until the backup expires.
