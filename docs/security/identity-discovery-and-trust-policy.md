# QuMail Identity Discovery & Trust Policy Architecture
## Automated Discovery, Enterprise Trust Anchors & Security Indicator Specification

**Milestone:** M7 — Module 1.6  
**Document:** Security Architecture & Policy Specification  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  

---

## 1. Architectural Philosophy: Zero Cryptographic Friction

In traditional OpenPGP workflows, cryptographic security imposed significant manual labor on users:
* Employees had to manually export public keys in ASCII-armored format.
* Communicating parties had to exchange 64-character hexadecimal fingerprints out-of-band (via phone or in-person).
* Users had to manually sign certificates, manage subkey bindings, and inspect technical certificate details.

In an enterprise environment, this friction leads to total failure of adoption. Non-technical corporate employees (finance, human resources, sales, executives) will bypass security controls if routine communication requires cryptographic ceremonies.

**QuMail WS-02 establishes the foundational architectural rule:**
> **The employee experience must be as seamless as Gmail or Outlook. The post-quantum cryptography, digital signatures, and key discovery must operate invisibly under the hood, while the client presents plain-language, accurate security indicators.**

Crucially, **removing friction does not mean weakening trust**. QuMail achieves simplicity by automating discovery and policy decisions, while strictly enforcing cryptographic and identity boundaries.

---

## 2. Discovery vs. Identity Trust: The Non-Negotiable Boundary

A foundational security vulnerability in many modern messaging systems is **silent Trust-on-First-Use (TOFU)**, where retrieving a public key from a directory or server automatically causes the client to trust that the key owner is authentic.

QuMail strictly separates **Key Discovery** from **Identity Trust**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           KEY DISCOVERY LAYER                               │
│  Queries: OpenPGP WKD (Public) or Enterprise Directory (Corporate)          │
│  Validates: Payload limit, Email address binding in User ID                 │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Public Key Material Discovered
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CENTRALIZED TRUST POLICY ENGINE                       │
│  Evaluates:                                                                 │
│  * Is this contact certified by an Enterprise Trust Anchor?                 │
│  * Is this contact pinned in the local vault via approved verification?     │
│  * Has the key changed unexpectedly compared to historical records?         │
│  * Is the digital signature valid and replay fresh?                         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Authoritative Trust Decision
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SECURITY INDICATOR CONTRACT                        │
│  🟢 SECURED_BY_QUMAIL: Verified corporate identity & post-quantum encrypted │
│  🟡 ENCRYPTED_UNVERIFIED: Post-quantum encrypted, unverified sender         │
│  🔴 SECURITY ALERT: Signature invalid, identity mismatch, or changed key    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Security Invariants:
1. **WKD is strictly a discovery mechanism.** Successfully fetching a key from WKD establishes that a domain-hosted key exists for an address; it does NOT verify that the key belongs to an authentic individual.
2. **Never upgrade trust based on cryptographic success alone.** A mathematically valid signature or successful decryption proves possession of the corresponding private key, not the real-world identity of the sender.
3. **Contradictory or changed keys are blocked.** If a correspondent whose key was previously verified presents a different root key, the client flags `CHANGED_BLOCKED` to protect against unauthorized substitution or Man-in-the-Middle (MITM) attacks.

---

## 3. Automated Key Discovery Engine (`core/key_discovery.py`)

### 3.1 OpenPGP Web Key Directory (WKD)
QuMail implements the standard WKD retrieval protocol specified in RFC 9580 and draft-koch-openpgp-webkey-service:

* **Hash Derivation:** The local part of the email address is lowercased and hashed with SHA-1 (160 bits). The resulting 20 bytes are encoded using the 32-character z-base-32 alphabet (`ybndrfg8ejkmcpqxot1uwisza345h769`):
  $$\text{hu} = \text{zbase32}(\text{SHA-1}(\text{lowercase}(\text{local\_part})))$$
* **Resolution Priority:**
  1. **Advanced Method:** `https://openpgpkey.<domain>/.well-known/openpgpkey/<domain>/hu/<hu>?l=<local_part>`
  2. **Direct Method:** `https://<domain>/.well-known/openpgpkey/<domain>/hu/<hu>?l=<local_part>`
* **Address Binding Validation:** When WKD returns an OpenPGP certificate, the client inspects its User ID packets. If the queried email address is not explicitly bound to the certificate, the key is rejected with `ADDRESS_MISMATCH`.
* **Resource Bounding:** HTTP fetch enforces a 64 KiB payload ceiling (`MAX_KEY_BYTES`) and a 5.0-second timeout to prevent resource exhaustion or denial-of-service.

### 3.2 Enterprise Key Directory Provider
For corporate deployments, QuMail provides `EnterpriseDirectoryProvider`. Corporate identity directories take precedence over public WKD, allowing organizations to maintain authoritative internal key directories for all employees.

### 3.3 Bounded-TTL Caching
`CachedKeyDiscoveryService` maintains an in-memory cache with configurable TTL (default 24 hours) and FIFO eviction (maximum 512 entries). Cached entries are checked against monotonic timestamps, ensuring that stale keys do not persist indefinitely.

---

## 4. Centralized Trust Policy Engine (`core/trust_engine.py`)

All trust decisions in QuMail are centralized in `TrustPolicyEngine`. Neither UI components nor background workers independently infer trust from raw booleans.

### 4.1 Authoritative Trust States

| Trust State | Meaning | Encryption Permitted? | Identity Verified? | UI Indicator |
|---|---|:---:|:---:|---|
| `VERIFIED` | Correspondent pinned via out-of-band verification or certified under active enterprise anchor. | **Yes** | **Yes** | 🟢 `SECURED_BY_QUMAIL` |
| `DISCOVERED_NOT_VERIFIED` | Usable public key discovered via WKD/directory; identity unverified. | **Yes** | **No** | ⚪ `EXTERNAL_CORRESPONDENT` |
| `ENCRYPTED_NOT_VERIFIED` | Message successfully decrypted, but sender identity is unverified. | **Yes** | **No** | 🟡 `ENCRYPTED_UNVERIFIED` |
| `CHANGED_BLOCKED` | Correspondent's key changed unexpectedly compared to historical record. | **No** | **No** | 🔴 `CHANGED_BLOCKED` |
| `VERIFICATION_FAILED` | Signature invalid, metadata mismatch, key revoked, or key expired. | **No** | **No** | 🔴 `SECURITY_ALERT` |
| `SECURITY_UNAVAILABLE` | Public key not found or discovery service offline. | **No** | **No** | ⚪ `VERIFICATION_UNAVAILABLE` |
| `LOCAL_ENROLLED` | User's own enrolled identity in local vault. | **Yes** | **Yes** | 🟢 `SECURED_BY_QUMAIL` |

---

## 5. Security Indicator Contract (`core/security_indicators.py`)

The security indicator contract defines the plain-language representations rendered by the UI (WS-05):

### 5.1 Indicator Details

1. **`SECURED_BY_QUMAIL` (Badge: Green `SECURE`)**
   * *Headline:* `Secured by QuMail`
   * *Description:* `Verified corporate identity from {sender}. Encrypted with post-quantum security.`
   * *Advice:* `Identity and digital signature are authenticated. Safe to communicate.`
   * *Requirement:* Emitted strictly when signature is valid, identity is verified, replay is fresh, headers match, and key is active.
2. **`ENCRYPTED_UNVERIFIED` (Badge: Amber/Yellow `CAUTION`)**
   * *Headline:* `Encrypted — Sender Identity Unverified`
   * *Description:* `Message is encrypted with post-quantum security, but identity from {sender} has not been verified.`
   * *Advice:* `If this message contains sensitive business instructions or financial details, verify via an independent channel.`
3. **`EXTERNAL_CORRESPONDENT` (Badge: Neutral/Gray `NEUTRAL`)**
   * *Headline:* `External Correspondent`
   * *Description:* `Public key for {email} was discovered via public directory, but no corporate trust relationship exists.`
   * *Advice:* `Standard external communication. Messages can be encrypted.`
4. **`SIGNATURE_INVALID` (Badge: Red `ALERT`)**
   * *Headline:* `Security Alert — Digital Signature Invalid`
   * *Description:* `The digital signature on this message could not be verified. The message may have been altered or corrupted in transit.`
   * *Advice:* `DO NOT trust this message or click any attachments. Report to IT Security.`
5. **`IDENTITY_MISMATCH` (Badge: Red `ALERT`)**
   * *Headline:* `Security Alert — Sender Address Mismatch`
   * *Description:* `The sender address '{claimed}' does not match the certified certificate identity '{actual}'.`
   * *Advice:* `DO NOT release sensitive information. The sender may be spoofed.`
6. **`CHANGED_BLOCKED` (Badge: Red `ALERT`)**
   * *Headline:* `Security Alert — Key Changed Unexpectedly`
   * *Description:* `The cryptographic key for '{address}' has changed since it was previously verified.`
   * *Advice:* `Communication is blocked until the new key is authenticated to prevent potential interception.`
7. **`KEY_REVOKED_OR_EXPIRED` (Badge: Red `ALERT`)**
   * *Headline:* `Security Alert — Signer Key Inactive`
   * *Description:* `The cryptographic key used to sign this message is {reason} and is no longer authorized for use.`
   * *Advice:* `Contact the sender through an alternate channel to request an updated key.`

---

## 6. Enterprise Trust Provisioning (`core/enterprise_trust.py`)

In enterprise deployments, IT administrators provision organization-wide trust anchors (`TrustAnchor`):
* Administrators register approved domain roots (e.g., `@acme.com`).
* Certified employee keys are registered under active anchors (`EnterpriseContactRecord`).
* When an employee addresses an email to a colleague in the same organization, the client recognizes the enterprise certification automatically.
* When an anchor is revoked (e.g., during corporate restructuring or certificate authority compromise), all contacts certified under that anchor immediately lose verified status.
