# QuMail M7 — Module 1.6 Architecture Decisions
## Architectural Decision Records (ADRs) Proposed for Technical Lead Review

**Milestone:** M7 — Module 1.6  
**Document:** Proposed Architectural Decisions (ADR 010 – ADR 015)  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  
**Branch:** `codex/m7-module-1-6-planning`  
**Accepted Baseline Checkpoint:** `eff3736` | **Closeout Anchor:** `c9a3cf4`  

---

## 1. Executive Summary

As QuMail transitions from an experimental proof-of-concept into a dependable corporate email security product, six foundational architectural decisions must be formally evaluated and approved by the Technical Lead.

These proposals resolve ambiguities surrounding deployment models, multi-provider abstraction, contact discovery scaling, mailbox caching, multi-device key lifecycle, and wire profile standardization.

| Proposed ADR | Title | Decision Status | Primary Architectural Focus |
|---|---|---|---|
| **ADR 010** | Standalone Native Client vs. Local Decryption Proxy | **Proposed** | Retain standalone native client architecture; reject proxy model. |
| **ADR 011** | Unified Multi-Provider Transport Interface | **Proposed** | Abstract IMAP/SMTP transport beyond Gmail to support Microsoft 365 & standard IMAP. |
| **ADR 012** | Enterprise Contact Discovery & Scaling | **Approved & Implemented (WS-02)** | Hybrid Web Key Directory (WKD) + Enterprise Directory with strict separation of discovery and trust. |
| **ADR 013** | Mailbox Synchronization & Local Index Model | **Proposed** | SQLite FTS5 encrypted index cache for headers; bodies fetched on demand via `BODY.PEEK`. |
| **ADR 014** | Multi-Device Key Hierarchy & Enrollment | **Proposed** | Single master root key certifying distinct, non-exportable per-device subkeys. |
| **ADR 015** | Standardization of Wire Profile to `QM-OPENPGP-PQ-v1` | **Approved & Implemented (WS-02)** | Standardized production profile `QM-OPENPGP-PQ-v1` with dual-read backward compatibility. |

---

## 2. Proposed Architectural Decision Records

---

### ADR 010: Standalone Native Client vs. Local Decryption Proxy

#### Context & Problem Statement
QuMail currently runs as a standalone desktop application (`MailboxWindow` in PyQt6) directly managing UI, storage, cryptography, and network protocols. A recurring question in corporate email security is whether the product should remain a standalone mail client or transform into a local transparent decryption proxy (e.g. running on `127.0.0.1:1143`) that integrates with standard email clients like Microsoft Outlook, Mozilla Thunderbird, or Apple Mail.

#### Decision Drivers
* Attack surface and vulnerability to UI-based attacks (HTML rendering, tracking pixels, malicious scripts).
* Complexity of maintaining a full-featured desktop mail reader vs. delegating to commercial clients.
* Cryptographic security boundaries: "Verify then release" plaintext invariant.
* User familiarity and corporate adoption friction.

#### Considered Options
* **Option A (Proxy Model):** QuMail runs as a background service/daemon acting as a local loopback IMAP/SMTP proxy. Standard Outlook or Thunderbird connects to `localhost`. The proxy decrypts inbound mail on the fly and encrypts outbound mail.
  - *Pros:* Users keep Outlook/Thunderbird interface; QuMail team doesn't need to build rich text editors, calendar views, or complex UI.
  - *Cons:* Destroys the security model. Commercial email clients automatically parse HTML, load remote images/tracking pixels, execute complex MIME renderers, and write decrypted plain-text message bodies into unencrypted local OST/PST files. The proxy cannot enforce the "verify then release" UI invariant, nor can it prevent the outer client from leaking plaintext drafts or caching unverified identities.
* **Option B (Standalone Secure Mail Client — Recommended):** QuMail remains a dedicated, secure, standalone application.
  - *Pros:* Full end-to-end control over the security boundary. Strict enforcement of plain-text rendering, no remote tracking resources, explicit attachment export safeguards, and atomic zeroization of memory upon window lock. Plaintext never touches disk unencrypted.
  - *Cons:* Must maintain a dedicated desktop user interface.

#### Recommendation
**Adopt Option B (Standalone Native Client).**  
For a post-quantum, high-assurance security product, the UI is an integral part of the trust boundary. Delegating rendering and storage to Outlook or Thunderbird fundamentally breaks the security contracts established in ADR 007 and ADR 008.

---

### ADR 011: Unified Multi-Provider Transport Interface

#### Context & Problem Statement
Currently, QuMail's modern transport is hardcoded to Google Workspace (`GmailMailbox`, `GmailSMTP`, `imap.gmail.com`, `smtp.gmail.com`). However, the vast majority of enterprise corporate environments operate on Microsoft 365 (Exchange Online) or private corporate IMAP/SMTP servers.

#### Decision Drivers
* Corporate market applicability: Enterprises cannot adopt QuMail if restricted strictly to Gmail.
* Adherence to security contracts: Mandatory TLS, strict certificate validation, XOAUTH2 modern auth.
* Maintainability: Avoid duplicate outbox or mailbox logic per provider.

#### Considered Options
* **Option A (Provider-Specific Slices):** Create independent silos like `m6_gmail`, `m8_microsoft365`, `m9_generic_imap`.
  - *Cons:* Code duplication, divergent state machines, fragmented testing.
* **Option B (Unified Transport Interface with Pluggable OAuth / Authenticator Adapters — Recommended):**
  - Define canonical `MailboxTransport` and `SubmissionTransport` protocols in `core/transport/`:
    ```python
    class MailboxTransport(Protocol):
        def headers(self, cred: Credential, budget: Budget, before: int | None) -> Page: ...
        def fetch(self, cred: Credential, key: MessageKey, budget: Budget) -> tuple[bytes, bool]: ...
        def set_seen(self, cred: Credential, key: MessageKey, seen: bool, budget: Budget) -> bool: ...
    ```
  - Implement concrete adapters: `GoogleWorkspaceAdapter`, `Microsoft365Adapter` (OAuth2 device/authorization code flow with Microsoft Graph or modern IMAP/SMTP), and `GenericIMAPAdapter` (App Passwords + STARTTLS).

#### Recommendation
**Adopt Option B (Unified Transport Interface).**  
Abstract the transport layer into a clean interface. Maintain Gmail as the qualified reference implementation, while implementing the Microsoft 365 adapter as the primary enterprise target in Gate 2.

---

### ADR 012: Enterprise Contact Discovery & Scaling

#### Context & Problem Statement
Currently, contact public keys must be manually imported by pasting armored ASCII blocks and verified through visual comparison of a 64-character hexadecimal fingerprint (`experiments/m3/vault.py:pin_contact`). This manual ceremony was acceptable for two-account acceptance verification, but cannot scale to a 500-person enterprise workforce.

#### Decision Drivers
* Zero-friction coworker discovery for non-technical employees.
* Resistance to Man-in-the-Middle (MitM) key substitution attacks.
* Scalability without requiring a proprietary, centralized QuMail key server.
* Open standards compliance (IETF OpenPGP).

#### Considered Options
* **Option A (Proprietary Centralized Key Server):** QuMail hosts a proprietary key escrow/directory service.
  - *Cons:* Introduces a centralized point of compromise; requires ongoing cloud operations; contradicts the "no server trust" security philosophy.
* **Option B (Web Key Directory - WKD + DNS DANE OPENPGPKEY — Recommended):**
  - Use standard RFC-compliant Web Key Directory (WKD). When an employee types `bob@company.com`, QuMail queries `https://openpgpkey.company.com/.well-known/openpgpkey/hu/...`.
  - Keys signed by the organization's published root identity or served over HTTPS from the target domain are automatically marked `domain_verified`.
  - Manual fingerprint verification remains available for external, unauthenticated domains.
* **Option C (LDAP / SCIM Corporate Directory Sync):** Client polls internal corporate LDAP/Active Directory for user certificates.
  - *Cons:* Requires direct enterprise network/VPN access; complex enterprise schema variations.

#### Recommendation
**Adopt Option B (Standard Web Key Directory).**  
WKD is supported natively by major secure mail ecosystems (GnuPG, ProtonMail) and allows any enterprise to publish their employees' post-quantum public keys using static files on their existing corporate web server, requiring zero QuMail backend infrastructure.

#### Implementation Status (WS-02)
Implemented in `core/key_discovery.py`, `core/enterprise_trust.py`, `core/trust_engine.py`, and `core/security_indicators.py`. RFC 9580 z-base-32 WKD lookup, in-memory bounded caching with TTL, and enterprise root anchor directory support are verified by `tests/test_ws02_identity_and_trust.py`. Strict separation of discovery and trust ensures WKD never grants silent TOFU.

---

### ADR 013: Mailbox Synchronization & Local Index Model

#### Context & Problem Statement
QuMail currently does not store messages locally; it only caches the latest 30 headers in an in-memory page within the vault (`PAGE_SIZE = 30`). Message bodies are fetched from IMAP on demand via `BODY.PEEK[]`. While this provides outstanding data-at-rest protection (zero unencrypted or encrypted bodies stored on disk), it prevents searching older messages, offline reading, and responsive mailbox navigation.

#### Decision Drivers
* Offline availability: Should an employee be able to read previously decrypted messages while on an airplane?
* Search capability: Employees need to search through months of communications.
* Endpoint security: Storing decrypted bodies on disk introduces data leakage risks.
* Storage scalability: Bounding local database size.

#### Considered Options
* **Option A (Pure On-Demand / Zero Body Cache — Current):** Retain current design. Bodies exist strictly in volatile RAM while viewing; never written to disk.
  - *Pros:* Ultimate forensic security. Stolen laptop yields zero message plaintext even if the vault database is compromised.
  - *Cons:* No offline access; searching bodies is impossible; opening messages always incurs network latency.
* **Option B (Encrypted Local Header Index + On-Demand Body Fetch — Recommended):**
  - Cache all message *headers* and metadata in an encrypted SQLite FTS5 table in the local vault.
  - Message *bodies* remain on the remote IMAP server, fetched on demand via `BODY.PEEK[]` and retained in memory only.
  - Users can explicitly select "Save to Offline Archive" for specific critical messages, encrypting the body with the local vault's AES-256-GCM key.
* **Option C (Full Local Mailbox Mirroring):** Mirror the entire mailbox (all bodies and attachments) locally in the encrypted vault.
  - *Cons:* High disk footprint (tens of gigabytes); long initial synchronization times; large blast radius if local vault is compromised.

#### Recommendation
**Adopt Option B (Encrypted Local Header Index + On-Demand Body Fetch).**  
This provides fast search across senders, dates, and subjects, enables instantaneous inbox loading, supports selective offline caching, and maintains the core security posture of keeping bulk message bodies off the local disk.

---

### ADR 014: Multi-Device Key Hierarchy & Enrollment

#### Context & Problem Statement
ADR 004 established a strict product constraint: "one active enrolled device per account". Restoring a backup on a new computer requires explicit acknowledgment of prior-device retirement. In modern corporate reality, employees routinely operate across a primary desktop, a portable laptop, and (in future phases) a mobile device.

#### Decision Drivers
* Employees must be able to read incoming secure mail on both their desktop and laptop.
* Compromise of a laptop should not compromise the desktop's private keys.
* Independent cryptographic revocation of lost or stolen devices.
* Compliance with OpenPGP multi-recipient encryption standards.

#### Considered Options
* **Option A (Shared Master Private Key Cloning):** Exporting the private root and subkeys from the desktop and importing them onto the laptop.
  - *Cons:* Dangerous security practice. Leaking keys across devices via USB or network exposes master identity; cannot selectively revoke a stolen laptop without revoking the desktop.
* **Option B (Root-Certified Independent Device Subkeys — Recommended):**
  - An employee's identity possesses one long-term **Corporate Root Key** (stored securely on the primary workstation or corporate smartcard).
  - Each physical device (Desktop, Laptop) generates its own independent **Device Encryption Subkey** (ML-KEM-768) and **Device Signing Subkey** (ML-DSA-65).
  - The Root Key issues certified binding signatures for both device subkeys and publishes a composite public certificate.
  - Senders encrypt messages to *both* device subkeys (creating two v6 PKESK packets in the OpenPGP envelope).
  - Either device can independently decrypt incoming messages.
  - If a laptop is lost, the employee revokes the laptop's subkey from their desktop; the root key remains secure.

#### Recommendation
**Adopt Option B (Root-Certified Independent Device Subkeys).**  
This leverages standard OpenPGP multi-subkey mechanics, prevents private key cloning, supports granular device revocation, and aligns with the long-term Android roadmap.

---

### ADR 015: Standardization of Wire Profile to `QM-OPENPGP-PQ-v1`

#### Context & Problem Statement
The Module 1.5 roundtrip implementation marks outer MIME headers with `X-QuMail-Profile: QM-OPENPGP-PQ-1-EXPERIMENT-M5` and passes `M2-EXPERIMENT-RFC9980-AES256-GCM` to the native provider. As we approach pilot deployment, experimental markers must be replaced with a stable, versioned specification that guarantees backward compatibility for existing messages.

#### Decision Drivers
* Wire protocol stability and long-term archival readability.
* Interoperability with future client versions and third-party security auditors.
* Clean deprecation and migration paths.

#### Considered Options
* **Option A (Retain Experimental Markers):** Keep `EXPERIMENT-M5` marker until final commercial release.
  - *Cons:* Unprofessional for corporate pilot; signals unfinished laboratory software to enterprise security reviewers.
* **Option B (Versioned Production Profile with Dual-Read Compatibility — Recommended):**
  - Standardize wire profile identifier as **`QM-OPENPGP-PQ-v1`**.
  - Update `experiments/m5/model.py` and `experiments/m5/mime.py` to emit `QM-OPENPGP-PQ-v1` for all new compositions.
  - Maintain dual-read compatibility in `parse_outer()` and `OpenMessage`:
    ```python
    SUPPORTED_PROFILES = {
        'QM-OPENPGP-PQ-v1',                     # Standard Production Profile
        'QM-OPENPGP-PQ-1-EXPERIMENT-M5'         # Module 1.5 Historical Acceptance Profile
    }
    ```
  - Incoming messages bearing either profile are accepted and verified; outbound messages always use `v1`.

#### Recommendation
**Adopt Option B (Versioned Production Profile `QM-OPENPGP-PQ-v1`).**  
Guarantees permanent readability for historical Module 1.5 test correspondence while establishing a formal, production-grade protocol version for all future communications.

#### Implementation Status (WS-02)
Implemented in `experiments/m5/model.py`, `experiments/m5/mime.py`, and `experiments/m5/services.py`. Outbound compositions emit `QM-OPENPGP-PQ-v1`. Inbound message parser accepts both `QM-OPENPGP-PQ-v1` and historical `QM-OPENPGP-PQ-1-EXPERIMENT-M5` while strictly rejecting unregistered profile markers. Verified in `tests/test_ws02_identity_and_trust.py`.
