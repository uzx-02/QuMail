# QuMail M8 — Milestone Boundaries, Acceptance Criteria & Security Assumptions

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

Milestone **M8** expands QuMail from a verified standalone Windows desktop client into an enterprise-ready product ecosystem capable of supporting real-world pilot deployments across both QuMail users and external correspondents.

### Boundaries and Invariants
- **Preserve M7 Baseline:** All existing M1–M7 cryptographic providers (`qumail-m3-provider`, `qumail-m5-provider`), local SQLite vaults, DPAPI credential boundaries, M4 outbox state machines, and M5 OpenPGP-PQ wire specifications remain strictly intact.
- **Zero Decryption on Servers:** Neither the directory server nor the web portal server may possess decryption capabilities or observe plaintext message bodies.
- **Implementation Gate:** No M8 code implementation or server deployment will begin until this architecture package is formally approved by the Technical Lead.

---

## 2. Workstream Breakdown & Acceptance Criteria

### M8-WS01: Public-Key Directory Backend & Transparency Engine
* **Objective:** Deliver the server-side directory service implementing the protocol specified in [`docs/operations/public-key-directory-protocol-specification.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/public-key-directory-protocol-specification.md).
* **Deliverables:**
  - `services/directory/server.py`: FastAPI / SQLite service with TLS 1.3 enforcement.
  - Challenge-response Proof of Key Possession (PoP) verification.
  - Hashed/blinded lookup endpoint to prevent directory harvesting.
  - Cryptographic response signing via `DirectoryAuthorityKey`.
  - Rate limiting (token bucket per IP/subnet) and registration sequence counters (`generation`).
* **Acceptance Criteria:**
  1. Valid OpenPGP-PQ certificate with correct PoP signature registers cleanly.
  2. Submitting an invalid PoP signature or tampered subkey binding fails with HTTP 400/403.
  3. Attempting to overwrite an existing user's key without previous primary key authorization is strictly rejected.
  4. Blinded lookups return valid signed Directory Claims; malformed queries fail.
  5. 100% test coverage with deterministic local mock server; zero live cloud dependencies.

---

### M8-WS02: Desktop Client Directory & Trust Integration
* **Objective:** Integrate directory discovery and registration into the desktop application.
* **Deliverables:**
  - `core/directory_client.py`: Client library for registration, rotation, and lookup.
  - Integration with `core/key_discovery.py` and `mailbox_client/workflows.py:recipients`.
  - Automatic public key publication upon first-run account enrollment.
  - Trust-On-First-Use (TOFU) key pinning in local SQLite vault; critical UI alarm on unexpected key change.
  - Visual indicator alignment: Directory keys without corporate CA display amber **`CAUTION: Identity Unverified`**; corporate GPO keys display emerald green **`SECURE`**.
* **Acceptance Criteria:**
  1. Composing to an unknown recipient queries directory automatically; if found, seals message without manual cert import.
  2. If directory key changes unexpectedly, UI prompts with security warning and blocks sending until confirmed.
  3. Offline directory fallback gracefully falls back to local vault without crashing or unencrypted leakage.
  4. Unit and UI tests passing in headless test suite.

---

### M8-WS03: Secure Web Link Cryptographic Engine & Browser Decryptor
* **Objective:** Implement client-side symmetric payload packaging and sandboxed browser decryptor specified in [`docs/operations/secure-web-link-threat-model-and-protocol.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/operations/secure-web-link-threat-model-and-protocol.md).
* **Deliverables:**
  - `core/web_link_crypto.py`: Desktop client library for AES-256-GCM encryption with URL fragment key packing and Ed25519 signature binding.
  - `services/portal/static/`: Static browser decryptor application using Web Cryptography API (`crypto.subtle`) and sandboxed `<iframe>`.
  - Content Security Policy (CSP) headers prohibiting script injection, external network fetch, and tracking pixels.
* **Acceptance Criteria:**
  1. End-to-end cryptographic roundtrip: Python client encrypts $\rightarrow$ browser WebCrypto decrypts and verifies signature.
  2. Decryption key ($K_{\text{msg}}$) is strictly verified to reside in URL fragment (`#...`) and is never sent to the portal in HTTP request headers.
  3. Tampered ciphertext or altered AAD fails closed with authentication error.
  4. Attachments export safely from browser memory via object URLs; executable extensions (`.exe`, `.bat`) blocked.

---

### M8-WS04: Secure Portal Service & OTP Verification
* **Objective:** Implement the ephemeral web portal service hosting encrypted blobs and issuing OTP challenges.
* **Deliverables:**
  - `services/portal/server.py`: Ephemeral storage service with automated TTL sweeper.
  - OTP generator and validator (6-digit CSPRNG, 10-minute expiry, max 3 attempts).
  - Authenticated sender revocation API.
* **Acceptance Criteria:**
  1. Accessing message URL triggers OTP challenge to recipient's email; incorrect OTP fails.
  2. Exceeding 3 failed OTP attempts locks message access.
  3. Expired blobs are permanently zeroized and purged by background sweeper.
  4. Sender revocation command immediately deletes blob and renders link inaccessible.

---

### M8-WS05: First-Run Onboarding & Security Tutorial Wizard
* **Objective:** Provide a polished, non-technical first-launch wizard in the desktop client.
* **Deliverables:**
  - `ui/onboarding_wizard.py`: Multi-step welcome dialog for first-time application launch:
    1. Welcome to QuMail branding and post-quantum value proposition.
    2. Account sign-in (Google OAuth / IMAP credentials) with automated key generation progress.
    3. Interactive security indicator guide (explaining Green `SECURE`, Amber `CAUTION`, Red `ALERT`).
    4. Mandatory account backup secret generation and acknowledgment dialog.
* **Acceptance Criteria:**
  1. Wizard launches automatically when no vault exists; does not reappear on subsequent launches.
  2. Key generation completes in background thread without freezing GUI.
  3. Backup secret acknowledgment must be checked before proceeding into the mailbox.
  4. Full UI unit test coverage.

---

### M8-WS06: Pilot Hardening, Security Review & Staging
* **Objective:** Package and validate the complete ecosystem for a controlled 10-client pilot.
* **Deliverables:**
  - Staging deployment script for zero-cost hosting (Render / Cloudflare).
  - End-to-end multi-client simulation test suite.
  - Comprehensive pilot deployment documentation.
* **Acceptance Criteria:**
  1. 10 simulated distinct clients can register, discover keys, send post-quantum emails, and send secure web links to non-users.
  2. Complete modern regression suite (all M1–M7 tests + M8 tests) passing 100%.
  3. Zero network calls during dry-run / unit tests.

---

## 3. Commercial Release Gates (External Prerequisites)

The following gates are strictly required before commercial public release:

| Gate | Purpose | Owner / Dependency | Status |
|---|---|---|:---:|
| **1. Commercial Code-Signing** | EV Authenticode Certificate for `QuMail.exe` / `QuMailSetup.exe` to eliminate Windows SmartScreen warnings. | CA Purchase / HSM Provisioning | **Prerequisite for Public Windows Installers** |
| **2. Google OAuth CASA Verification** | Cloud Application Security Assessment (Tier 2) required by Google for public distribution using restricted Gmail scopes. | External Google Auditor (e.g. Bishop Fox / Leviathan) | **Prerequisite for Unlimited Gmail Users** (Private pilot capped at 100 test users) |
| **3. Independent Cryptographic Audit** | Formal external review of native Rust providers, composite PQC wire format, and directory protocols. | Independent Security Firm (e.g. Trail of Bits, Cure53) | **Prerequisite for Enterprise Claims** |

---

## 4. Explicit Unresolved Security Assumptions

The following explicit security assumptions and residual risks are documented for technical lead evaluation:

### Assumption 1: Web Browser Execution Environment Trust (Non-QuMail Recipients)
* **Risk:** The Secure Web Link portal relies on the recipient's web browser environment to decrypt the message client-side.
* **Assumption:** The recipient's workstation and browser are assumed free of malicious browser extensions, memory scrapers, or compromised certificate authorities. If an adversary has installed a malicious extension that scrapes DOM text or captures keystrokes, the decrypted plaintext can be compromised after client-side decryption.
* **Mitigation:** Strict Content Security Policy (`script-src 'self' 'wasm-unsafe-eval'`), sandboxed `<iframe>` isolation, and disabling browser caching of decrypted blobs.

### Assumption 2: Threat of Directory Equivocation (Malicious Directory Operator)
* **Risk:** A compromised or coerced directory server could attempt an equivocation attack (serving Bob's genuine public key to Charlie, but serving a rogue adversary key to Alice).
* **Assumption:** First-time directory lookups without corporate CA certification are assumed to be *opportunistic* rather than authoritative.
* **Mitigation:**
  1. The UI explicitly flags directory-only keys with the amber **`CAUTION: Identity Unverified`** indicator.
  2. The desktop client pins keys on first use (TOFU) and alarms if a key changes.
  3. The directory logs all registrations to an append-only transparency log so that rogue key injection can be detected by Bob.

### Assumption 3: Security of the Initial OTP Transit Channel
* **Risk:** For non-QuMail recipients, the OTP is transmitted over conventional email via standard SMTP/TLS.
* **Assumption:** The recipient's email account is not actively intercepted in real time by an adversary who also captured the URL link.
* **Reality:** If an adversary compromises the recipient's email inbox directly, they obtain both the link and the OTP. This is an inherent property of all zero-install email recovery/portal architectures (including Cisco IronPort, Microsoft Purview, and Virtru).
* **Mitigation:** Short OTP validity window (10 minutes), maximum 3 attempts, sender revocation capability, and optional out-of-band shared passphrase for ultra-confidential communications.

### Assumption 4: Post-Quantum vs. Classical Transit Discrepancy
* **Risk:** QuMail-to-QuMail communications use pure post-quantum `ML-KEM-768` + `Ed25519` encryption immune to quantum computers. However, for external non-users receiving a Secure Web Link, the OTP and invitation email travel over classical TLS/SMTP.
* **Assumption:** The payload itself is encrypted with symmetric AES-256-GCM (which is quantum-safe against Grover's algorithm with $2^{128}$ effective strength). However, the classical email channel carrying the URL link could be archived by a nation-state adversary for future quantum analysis if the fragment key were ever exposed.
* **Mitigation:** The fragment key ($K_{\text{msg}}$) is never sent to the portal server; the link expires quickly; and users are encouraged to onboard frequent correspondents onto native QuMail for complete post-quantum assurance.
