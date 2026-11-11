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

### 3.1 OpenPGP Web Key Directory (WKD) & Network Hardening
QuMail implements the standard WKD retrieval protocol specified in RFC 9580 and draft-koch-openpgp-webkey-service, with strict network-level security controls:

* **Hash Derivation:** The local part of the email address is lowercased and hashed with SHA-1 (160 bits). The resulting 20 bytes are encoded using the 32-character z-base-32 alphabet (`ybndrfg8ejkmcpqxot1uwisza345h769`):
  $$\text{hu} = \text{zbase32}(\text{SHA-1}(\text{lowercase}(\text{local\_part})))$$
* **Resolution Priority:**
  1. **Advanced Method:** `https://openpgpkey.<domain>/.well-known/openpgpkey/<domain>/hu/<hu>?l=<local_part>`
  2. **Direct Method:** `https://<domain>/.well-known/openpgpkey/<domain>/hu/<hu>?l=<local_part>`
* **Host & Domain Sanitization:** Domain syntax is strictly validated against RFC 1123 / RFC 952 hostname grammar. Control characters, path traversal (`..`), spaces, colons (ports), slashes, and null bytes are rejected.
* **Anti-SSRF Protection:** Before establishing any connection, the destination host is resolved and every returned IP address is checked against prohibited private, loopback, link-local, carrier-NAT, multicast, or reserved ranges (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `100.64.0.0/10`, `::1`, `fc00::/7`, `fe80::/10`). Destination IPs resolving to prohibited ranges abort immediately with `SecurityError`.
* **DNS Rebinding Defense:** The client connects directly to the pre-validated IP address while verifying the TLS certificate against the SNI hostname, eliminating time-of-check to time-of-use (TOCTOU) address switching.
* **Redirect Revalidation:** Redirects are capped at 2 hops and strictly revalidated. Redirects to insecure HTTP or to foreign hostnames outside the target domain are blocked.
* **Resource Bounding & Content-Type:** HTTP fetch enforces a 64 KiB payload ceiling (`MAX_KEY_BYTES`) with early stream termination. Responses with `Content-Type: text/html` are rejected.
* **Address Binding Validation:** When WKD returns an OpenPGP certificate, the client inspects its User ID packets. If the queried email address is not explicitly bound to the certificate, the key is rejected with `ADDRESS_MISMATCH`.
* **Non-Blocking Architecture:** Network discovery operations are executed off the main UI thread via thread-pool backed asynchronous methods (`lookup_async`, `discover_async`).

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

## 6. Enterprise Trust Provisioning & Policy Integration (`core/enterprise_trust.py`)

In enterprise deployments, IT administrators provision organization-wide trust anchors (`TrustAnchor`):

### 6.1 Cryptographic Certification vs. Administrative Provisioning
QuMail defines two explicit administrative trust models:
1. **`CRYPTOGRAPHICALLY_SIGNED` (Recommended):** The enterprise trust anchor contains an administrator Ed25519 public key. Every certified employee contact enrollment is cryptographically authenticated by an administrator signature over canonical bytes:
   $$\text{payload} = \text{"QuMail-Enterprise-Auth-v1:"} \parallel \text{anchor\_id} \parallel \text{email} \parallel \text{fingerprint} \parallel \text{expires\_at}$$
   If the signature is missing, expired, or invalid, certification is rejected.
2. **`LOCAL_ADMIN_PROVISIONED`:** In environments where policies are deployed via Windows Group Policy or endpoint management agents into the DPAPI-secured local vault directly, trust derives strictly from the local OS administrative security boundary. This limitation is explicitly stated rather than overclaiming cryptographic PKI certification.

### 6.2 Domain Scoping & Subdomain Protection
An anchor authorizes specific domain scopes (`domains=("acme.corp",)`). The client strictly verifies that contact email domains match the authorized scope or authorized subdomains (e.g. `eng.acme.corp`), and rejects foreign domains or spoofing attempts (e.g. `acme.corp.attacker.com`).

### 6.3 Revocation & Expiration Propagation
- When a trust anchor is revoked (`revoke_trust_anchor`), all contacts certified under that anchor immediately lose verified status.
- When an individual contact authorization expires or is revoked, verified status is revoked immediately.

### 6.4 Conflict Policy: Enterprise Precedence vs. Public WKD
When an email address belongs to an authorized enterprise domain:
- **Enterprise Precedence:** The authenticated enterprise directory is the authoritative source of truth. Conflicting keys returned by public WKD are rejected.
- **Anti-Bypass Protection:** If an enterprise contact's key is revoked or expired in the corporate directory, sending is **blocked**. QuMail strictly **prohibits silent fallback to public WKD**, preventing terminated employees or compromised keys from bypassing corporate revocation.
- **Unavailable Directory:** If the corporate directory is unavailable or disabled, public WKD keys are treated strictly as unverified `EXTERNAL_CORRESPONDENT` and cannot receive verified trust.
