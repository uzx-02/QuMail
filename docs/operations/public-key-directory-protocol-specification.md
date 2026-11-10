# QuMail Public-Key Directory Protocol Specification

**Milestone:** M8 Architecture Proposal  
**Document:** Public-Key Directory Protocol Specification  
**Status:** Architecture Proposal (Under Review; Implementation Deferred)  
**Author:** Antigravity (Implementation Engineer) & Mohammed Uzair Shaikh (Project Owner)  
**Target Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Date:** 2026-11-10  
**Accepted Baseline:** `d3b2078` (WS-06/07 Final Accepted Checkpoint)  
**Reference ADR:** [`docs/adrs/010-product-flow-and-public-key-directory.md`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/docs/adrs/010-product-flow-and-public-key-directory.md)  

---

## 1. Overview and Security Objectives

The QuMail Public-Key Directory provides an automated, centralized lookup service mapping user email addresses to their post-quantum public certificates. It eliminates the adoption friction of manual out-of-band certificate exchange while strictly preserving end-to-end cryptographic integrity.

### Core Security Objectives
1. **Preserve Wire Profile Compatibility:** Shipped certificates strictly adhere to QuMail's accepted `QM-OPENPGP-PQ-v1` composite post-quantum OpenPGP profile (RFC 9580 / draft-ietf-openpgp-pqc).
2. **Proof of Possession (PoP):** A client registering a public key must cryptographically prove possession of the corresponding private signing key. Rogue key injection is blocked.
3. **Replacement & Impersonation Protection:** Once registered, an account's public key record cannot be replaced or overwritten by an adversary. Updating a key requires cryptographic authorization from the existing primary key or an authenticated enterprise recovery authority.
4. **Authenticity & Non-Repudiation of Responses:** Lookup responses carry cryptographic claims signed by a dedicated Directory Authority key, allowing clients to detect tampering by malicious proxies.
5. **Zero Secret Exposure:** The directory is strictly public infrastructure. Private keys, database master secrets, OAuth tokens, and message contents **never** enter directory memory or storage.

---

## 2. Public Key Certificate Format Specification

The directory accepts and distributes Transferable Public Key (TPK) packet sequences strictly conforming to the `QM-OPENPGP-PQ-v1` profile.

### 2.1 Packet Sequence Structure
An enrolled public key certificate consists of the following canonical OpenPGP packet sequence:

```
+--------------------------------------------------------------------------------+
| Packet 6:  Primary Key Packet (Version 5 or Version 6)                         |
|            Algorithm: Ed25519 (0x16) or Composite ML-DSA-65 + Ed25519          |
|            Creation Timestamp (32-bit uint)                                    |
|            Public Key Material (32 bytes Ed25519 + optional ML-DSA-65 pubkey)  |
+--------------------------------------------------------------------------------+
| Packet 13: User ID Packet                                                      |
|            Text: "Alice Smith <alice@example.invalid>"                         |
+--------------------------------------------------------------------------------+
| Packet 2:  Self-Signature Packet (Signature Type 0x13: Positive Certification) |
|            Issuer Key ID / Fingerprint                                         |
|            Key Flags: Certification (0x01) + Signing (0x02)                    |
|            Preferred Symmetric Algorithms: AES-256 (0x09)                      |
|            Preferred Hash Algorithms: SHA-512 (0x0A), SHA-256 (0x08)            |
|            Preferred AEAD: AES-256-GCM (0x02)                                  |
|            Key Expiration: 31,536,000 seconds (1 year)                         |
+--------------------------------------------------------------------------------+
| Packet 14: Public Subkey Packet                                                |
|            Algorithm: Composite ML-KEM-768 + X25519 (0x65 / Private Profile)   |
|            Creation Timestamp                                                  |
|            Public Material: 1184 bytes ML-KEM-768 + 32 bytes X25519            |
+--------------------------------------------------------------------------------+
| Packet 2:  Subkey Binding Signature Packet (Signature Type 0x18)               |
|            Issuer Key ID (Primary Key)                                         |
|            Key Flags: Encrypt Storage (0x04) + Encrypt Transport (0x08)        |
|            Signature over (Primary Key || Subkey) using Primary Signing Key    |
+--------------------------------------------------------------------------------+
```

### 2.2 Wire Compatibility Constraints
- The directory rejects classical-only (RSA/ECDH) certificates and incomplete packet sequences lacking the post-quantum encryption subkey.
- The directory does not perform transcoding, re-armoring, or algorithm substitution; it validates and stores raw binary OpenPGP packets or standard ASCII-armored blocks (`-----BEGIN PGP PUBLIC KEY BLOCK-----`).

---

## 3. Directory Protocols & API Operations

The directory exposes an authenticated REST API over TLS 1.3:

```
                      +-----------------------------+
                      | QuMail Desktop Client       |
                      +-----------------------------+
                                │           ▲
           1. Request Nonce     │           │  2. Challenge Nonce
                                ▼           │
                      +-----------------------------+
                      | QuMail Directory API        |
                      +-----------------------------+
                                │           ▲
     3. Registration (PoP)      │           │  4. Signed Receipt
                                ▼           │
                      +-----------------------------+
                      | Directory Transparency Log  |
                      +-----------------------------+
```

### 3.1 Operation 1: Account Registration & Proof of Possession (PoP)
Registration binds an email address to a public certificate.

#### Step 1: Challenge Request
The client requests a registration challenge from the directory:
```http
POST /api/v1/auth/challenge
Content-Type: application/json

{
  "email": "alice@example.invalid",
  "client_version": "1.0.0"
}
```
**Server Response:** Returns an ephemeral, cryptographically secure 256-bit challenge nonce $N_{\text{chal}}$ (valid for 300 seconds).

#### Step 2: Proof-of-Possession Submission
The client submits its registration payload:
```http
POST /api/v1/keys/register
Content-Type: application/json

{
  "email": "alice@example.invalid",
  "certificate_armor": "-----BEGIN PGP PUBLIC KEY BLOCK-----\n...",
  "pop_signature": "<Ed25519_Signature(N_chal || email || timestamp)>",
  "auth_token": "<OIDC_Identity_Token_OR_Email_Verification_Token>",
  "timestamp_utc": "2026-11-10T12:00:00Z"
}
```

#### Step 3: Server Verification Rules
Before accepting the record, the directory validates:
1. **Certificate Syntax:** The certificate parses cleanly into the canonical packet sequence; the primary key matches the advertised fingerprint; subkey binding signature verifies.
2. **Proof of Possession (PoP):** `pop_signature` is verified against the primary public key in the submitted certificate over $N_{\text{chal}} \parallel \text{email} \parallel \text{timestamp}$.
3. **Identity Verification:**
   - **Enterprise Mode:** Verified via corporate OIDC ID token signed by the organization's Google Workspace / Microsoft Entra IdP matching `email`.
   - **Consumer / Standalone Mode:** An out-of-band email containing an activation challenge token is sent to `email`; registration is provisional until the activation link is clicked.
4. **Collision Check:** If a record for `email` already exists, direct overwrite is **prohibited** (see Section 3.3).

---

### 3.2 Operation 2: Public Key Lookup

```http
GET /api/v1/keys/lookup?email_hash=<HMAC_SHA256(email, blind_key)>
Accept: application/json
```

**Directory Response (Directory Claim):**
```json
{
  "email_hash": "a1b2c3d4...",
  "fingerprint": "5ceb47b86bec9b3b8d6e666e718947391c59f8763be1347b0e3c2a692e022241",
  "certificate_armor": "-----BEGIN PGP PUBLIC KEY BLOCK-----\n...",
  "generation": 1,
  "registered_utc": "2026-11-10T12:00:00Z",
  "valid_until_utc": "2027-11-10T12:00:00Z",
  "revoked": false,
  "log_index": 1042,
  "directory_signature": "<Ed25519_Signature_by_DirectoryAuthorityKey>"
}
```

#### Client Verification:
1. Client verifies `directory_signature` against the pre-configured `QuMailDirectoryAuthorityKey`.
2. Computes SHA-256 fingerprint of the returned certificate and verifies equality with `fingerprint`.
3. Verifies that the internal User ID matches the target email.
4. Applies trust indicator logic (amber `CAUTION` badge displayed unless certified by corporate CA).

---

### 3.3 Operation 3: Key Rotation & Replacement Protection

To prevent an attacker from overwriting an existing user's key with an adversary key:

1. **Active Key Authorization (Normal Subkey Rotation):**
   - The user's client rotates their annual post-quantum subkey.
   - The rotation update payload **must be signed by the existing primary signing key**.
   - The directory increments `generation` (e.g., $1 \rightarrow 2$) and logs the update in the append-only history.
2. **Lost Device / Account Recovery (Primary Key Replacement):**
   - If the primary private key was lost (device destroyed, no backup):
   - Replacement requires an **Identity Re-Verification Ceremony**:
     - Enterprise Mode: Signed administrative revocation statement from the IT administrator.
     - Consumer Mode: Mandatory 7-day notice period sent to the verified email address alerting the user of key replacement with an abort link, preventing silent account hijacking.
3. **Client-Side Key Pinning (Trust-On-First-Use / TOFU):**
   - The QuMail desktop client pins the primary key fingerprint in its local SQLite vault (`contacts` table).
   - If a directory lookup returns a different primary key for an existing contact without a valid cross-certification or revocation certificate, the client raises a critical security alarm:
     > *"SECURITY ALERT: The public key for bob@example.invalid has changed. This could indicate a key rotation or a network interception attempt. Verification required before sending."*

---

### 3.4 Operation 4: Certificate Revocation

When a subkey or primary key is compromised:
1. The client submits a standard OpenPGP Revocation Certificate (Packet 2, signature type `0x20` / `0x28`) signed by the primary key or a designated revocation key.
2. The directory sets `"revoked": true`, marks the tombstone, and includes the revocation certificate in future lookup responses.
3. Querying clients immediately transition cached contact state to `Trust.REVOKED` and prohibit further encryption to the revoked key.

---

## 4. Privacy, Abuse & Infrastructure Resilience Analysis

### 4.1 Directory Enumeration & Harvesting Prevention
* **Threat:** Spammers or adversaries query the directory sequentially to harvest all corporate email addresses.
* **Mitigations:**
  1. **Hashed / Blinded Lookups:** Queries do not submit plaintext email strings. The query uses an HMAC-SHA256 blind hash:
     $$\text{query\_id} = \text{HMAC-SHA256}(K_{\text{directory\_blind}}, \text{normalized\_email})$$
     Clients obtain the rotating $K_{\text{directory\_blind}}$ over authenticated TLS.
  2. **No Wildcard or List Queries:** The directory API strictly rejects prefix queries, listing, or pagination. Only exact 1:1 lookups are permitted.

### 4.2 Query Privacy
* **Threat:** The directory operator tracks which users Alice is communicating with based on her lookup queries.
* **Mitigations:**
  - **Local Vault Cache First:** QuMail checks its local SQLite vault and contacts index before making any directory network request. Repeat communications generate zero directory queries.
  - **Future Track (PIR):** Evaluation of Private Information Retrieval (PIR) or batched k-anonymity query models for large deployments.

### 4.3 Abuse Prevention & Rate Limiting
* **Per-IP Rate Limits:** Maximum 60 lookups/minute per IPv4/IPv6 subnet.
* **Per-Account Registration Limits:** Maximum 3 key registrations/rotations per 24 hours per account.
* **Payload Size Limits:** Registration payloads capped at 64 KiB (sufficient for composite ML-KEM-768/ML-DSA-65 certificates while rejecting malformed bloat).

### 4.4 Availability & Offline Resilience
* **Directory Unavailability Fallback:** If the directory is offline or unreachable:
  - Existing cached contacts in the local vault continue functioning without interruption.
  - New un-cached recipients cannot be fetched; QuMail safely falls back to local composition with a clear message: *"Directory unavailable; cannot verify new recipient. Message held in Outbox."*
  - **Zero Unencrypted Fallback:** Outages never trigger unencrypted transmission.

### 4.5 Server Compromise Risk Analysis
* **Worst-Case Compromise Scenario:** What happens if an adversary fully compromises the directory server?
  1. **Cannot Decrypt Past Communications:** The directory holds zero private keys and zero emails. Past and future emails remain encrypted with endpoint post-quantum keys.
  2. **Cannot Inject Plaintext Exploits:** The directory holds only public keys.
  3. **Equivocation / MITM Threat:** An adversary on the compromised server could attempt to serve a rogue public key for Bob.
  4. **Compromise Defenses:**
     - **WS-02 Trust Indicators:** Directory-retrieved keys display amber `CAUTION: Identity Unverified`. Employees are warned that the identity is not certified by corporate CA.
     - **Key Pinning (TOFU):** Existing contacts reject changed keys.
     - **Transparency Log Audit:** Directory records are published to an append-only verifiable log; unauthorized key injection is publicly detectable.
