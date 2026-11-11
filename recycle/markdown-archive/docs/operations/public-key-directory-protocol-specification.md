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

The QuMail Public-Key Directory provides an automated lookup service mapping user email addresses to their post-quantum public certificates. It eliminates the adoption friction of manual out-of-band certificate exchange while strictly preserving end-to-end cryptographic integrity.

### 1.1 Threat Model and Trust Assumptions
1. **Directory Operator as Honest-But-Curious / Potential Adversary:** The directory server is treated as untrusted infrastructure. It may attempt to harvest metadata, observe social graphs, or under coercion present unauthorized keys (equivocation).
2. **Zero Plaintext Visibility:** Private keys, database master secrets, OAuth tokens, and message contents **never** enter directory memory, network transit, or persistent storage.
3. **Trust-On-First-Use (TOFU) Reality:** TOFU detects key changes *after* first contact, but does **NOT** independently authenticate a first-contact key or prevent first-contact equivocation. Directory-discovered keys therefore remain marked with an amber **`CAUTION: Identity Unverified`** badge unless verified against an independent enterprise trust policy (Group Policy or corporate CA).

### 1.2 Core Security Objectives
1. **Preserve Wire Profile Compatibility:** Shipped certificates strictly adhere to QuMail's accepted `QM-OPENPGP-PQ-v1` composite post-quantum OpenPGP profile (RFC 9580 / draft-ietf-openpgp-pqc).
2. **Independent Verification of Identity and Key Possession:** Proving ownership of an email address and proving possession of the private key are decoupled into distinct cryptographic and authorization checks.
3. **Cryptographically Bound Proof of Possession (PoP):** Enrolling a public key requires solving a single-use server challenge signed using the complete composite signing profile (`ML-DSA-65` + `Ed25519`). Algorithmic downgrades to classical-only signatures during registration are strictly prohibited.
4. **Verifiable Merkle Tree Transparency:** Directory operations are committed to a binary Merkle tree issuing cryptographic Signed Tree Heads (STH), $O(\log N)$ inclusion proofs, and consistency proofs to detect equivocation and unauthorized key injection.
5. **Replacement Protection & Alerting:** Monotonic generation counters and transition signatures prevent arbitrary key replacement. Unexplained key replacement triggers a blocking security alert in the desktop client that cannot be bypassed via an ordinary dismiss dialog.

---

## 2. Public Key Certificate Format Specification

The directory accepts and distributes Transferable Public Key (TPK) packet sequences strictly conforming to the `QM-OPENPGP-PQ-v1` profile.

### 2.1 Canonical OpenPGP Packet Structure
```
+--------------------------------------------------------------------------------+
| Packet 6:  Primary Key Packet (Version 5 or Version 6)                         |
|            Algorithm: Ed25519 (0x16) or Composite ML-DSA-65 + Ed25519          |
|            Creation Timestamp (32-bit uint)                                    |
|            Public Key Material (32 bytes Ed25519 + 1952 bytes ML-DSA-65 pubkey)|
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

### 2.2 Profile Compatibility Constraints
- The directory rejects classical-only (RSA/ECDH) certificates and incomplete packet sequences lacking the composite post-quantum encryption subkey.
- The directory does not perform transcoding, re-armoring, or algorithm substitution; it validates and stores raw binary OpenPGP packets or standard ASCII-armored blocks (`-----BEGIN PGP PUBLIC KEY BLOCK-----`).

---

## 3. Directory Protocols & API Operations

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
     3. Registration (PoP)      │           │  4. Signed Receipt &
                                ▼           │     Inclusion Proof
                      +-----------------------------+
                      | Binary Merkle Tree Log      |
                      +-----------------------------+
```

---

### 3.1 Operation 1: Account Registration & Proof of Key Possession (PoP)

Account enrollment requires two distinct verifications:
1. **Account Ownership Verification:** Confirms that the client controls the requested email address.
2. **Proof of Key Possession (PoP):** Confirms that the client holds the private key matching the public certificate.

#### Step 1: Challenge Request
The client requests an enrollment challenge:
```http
POST /api/v1/auth/challenge
Content-Type: application/json

{
  "email": "alice@example.invalid",
  "client_version": "1.0.0"
}
```
**Server Response:**
Returns an ephemeral 256-bit CSPRNG challenge nonce $N_{\text{chal}}$ bound to a 300-second TTL:
```json
{
  "challenge_id": "c71a39f0-21a4-4f51-b842-8d77c1e54911",
  "nonce": "a7f92b4c10e3952d...",
  "audience": "urn:qumail:directory:pop:v1",
  "issued_utc": "2026-11-10T12:00:00Z",
  "expires_utc": "2026-11-10T12:05:00Z"
}
```

#### Step 2: Proof-of-Possession Construction
The client constructs the canonical PoP binding payload:
$$\text{NormEmail} = \text{NormalizeEmail}(\text{email})$$
$$\text{PoP-Binding} = \text{SHA256}(\text{"QUMAIL-POP-v1"} \parallel \text{NormEmail} \parallel N_{\text{chal}} \parallel \text{Fingerprint} \parallel \text{ProfileVersion} \parallel \text{Audience} \parallel T_{\text{issued}} \parallel T_{\text{expires}})$$

Where:
- $\text{NormalizeEmail}$: RFC 5321 / RFC 6531 lowercase, Unicode NFC normalized string.
- $\text{Fingerprint}$: Complete SHA-256 fingerprint over the canonical primary key packet.
- $\text{ProfileVersion}$: Literal ASCII string `"QM-OPENPGP-PQ-v1"`.
- $\text{Audience}$: Literal string `"urn:qumail:directory:pop:v1"`.
- $T_{\text{issued}}, T_{\text{expires}}$: ISO 8601 UTC timestamps matching the server challenge.

**Cryptographic Signature Rule (No Downgrade):**
- If the enrolled identity uses the composite `ML-DSA-65` + `Ed25519` primary signing key, the client MUST compute a composite signature containing **both** the `ML-DSA-65` signature and the `Ed25519` signature over $\text{PoP-Binding}$.
- If the primary key is standalone `Ed25519`, an `Ed25519` signature is computed.
- Submissions attempting to enroll a composite key using only an `Ed25519` signature are **rejected with HTTP 400 Bad Request**.

#### Step 3: Registration Submission
```http
POST /api/v1/keys/register
Content-Type: application/json

{
  "challenge_id": "c71a39f0-21a4-4f51-b842-8d77c1e54911",
  "email": "alice@example.invalid",
  "certificate_armor": "-----BEGIN PGP PUBLIC KEY BLOCK-----\n...",
  "pop_signature_composite": {
    "mldsa65_signature_b64": "...",
    "ed25519_signature_b64": "..."
  },
  "auth_credential": {
    "auth_type": "oidc_token",
    "token": "eyJhbGciOiJSUzI1NiIs..."
  }
}
```

#### Step 4: Server Verification Rules
1. **Challenge Validity:** `challenge_id` exists, is unused, matches $N_{\text{chal}}$, and current server time $< T_{\text{expires}}$. The challenge is marked used immediately (replay defense).
2. **Identity Verification (Independent Check):**
   - **OIDC Flow (Google Workspace / Microsoft 365):** The directory validates the OIDC ID token against the identity provider's published JWKS. It verifies `iss`, `aud`, expiration, and confirms that `email_verified == true` and that the token `email` claim matches $\text{NormEmail}$.
   - **Email Activation Flow (Consumer / Standalone):** The directory transmits a 256-bit CSPRNG activation token via SMTP to $\text{NormEmail}$ with a 15-minute expiry. Registration remains in provisional pending state until the recipient submits the activation token.
3. **Cryptographic PoP Verification:** Directory verifies `pop_signature_composite` against the primary public key in the submitted certificate over the constructed $\text{PoP-Binding}$.
4. **Collision & Replacement Check:** If a record for $\text{NormEmail}$ already exists, direct overwrite is strictly prohibited (see Section 3.4).

---

### 3.2 Operation 2: Lookup Privacy & Authenticated Query Model

#### 3.2.1 Privacy Model Evaluation
A privacy mechanism must protect against directory scraping while remaining operationally viable for multi-workstation pilots:
1. **Shared HMAC Key Model (Rejected as Insufficient):**
   - *Flaw:* Distributing a shared HMAC secret ($K_{\text{directory\_blind}}$) to clients does not prevent directory enumeration. Any authenticated client in possession of the key can run dictionary attacks against prospective email lists offline, compute the blinded hashes, and query the directory to harvest the entire user database.
2. **Oblivious Pseudorandom Function (OPRF / RFC 9497) (Future Roadmap):**
   - *Concept:* Client blinds an email address, server evaluates a PRF using a secret key without learning the email, and client unblinds to receive a query token.
   - *Status:* Cryptographically sound, but introduces significant client-side latency, requires complex protocol state machines, and is reserved for enterprise scale-out milestones.
3. **Selected Practical Pilot Model: Authenticated Query Model with Strict Rate Limits:**
   - Queries require client authentication (valid OAuth token or device session token).
   - Strict rate limiting: Maximum 60 queries/minute per account; maximum 120 queries/minute per IP subnet.
   - Directory logging policy: The directory server operates under a **zero-query-log policy**—access logs record timestamp, client ID, and HTTP status code, but query parameters (target email addresses) are never written to persistent disk logs.
   - **Explicit Trust Assumption:** The directory operator is in a position to observe which authenticated accounts perform lookups for specific target email addresses. True query privacy requires local vault caching.

#### 3.2.2 Lookup Protocol
```http
GET /api/v1/keys/lookup?email=bob@example.invalid
Authorization: Bearer <client_auth_token>
Accept: application/json
```

**Directory Response:**
```json
{
  "email": "bob@example.invalid",
  "fingerprint": "5ceb47b86bec9b3b8d6e666e718947391c59f8763be1347b0e3c2a692e022241",
  "certificate_armor": "-----BEGIN PGP PUBLIC KEY BLOCK-----\n...",
  "generation": 1,
  "registered_utc": "2026-11-10T12:00:00Z",
  "valid_until_utc": "2027-11-10T12:00:00Z",
  "revoked": false,
  "leaf_index": 1042,
  "tree_size": 2048,
  "inclusion_proof": [
    "a8f12...",
    "7b09c..."
  ],
  "sth": {
    "tree_size": 2048,
    "timestamp_utc": "2026-11-10T12:01:00Z",
    "root_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "signature": "<ML-DSA-65_plus_Ed25519_DirectoryAuthoritySignature>"
  }
}
```

---

### 3.3 Operation 3: Cryptographic Merkle Tree Transparency

To ensure that the directory cannot equivocate (presenting one public key for Bob to Alice and another to Charlie) without public detection, the directory maintains an append-only binary Merkle tree conforming to RFC 6962 / RFC 9162 principles.

```
                              Signed Tree Head (Root Hash)
                                           │
                        ┌──────────────────┴──────────────────┐
                        │                                     │
                     Node 0-1                              Node 2-3
                        │                                     │
                  ┌─────┴─────┐                         ┌─────┴─────┐
                  │           │                         │           │
                Leaf 0      Leaf 1                    Leaf 2      Leaf 3
              (Alice v1)  (Bob v1)                  (Charlie)   (Alice v2)
```

#### 3.3.1 Tree Construction Rules
1. **Leaf Hashing:** Every enrollment, rotation, revocation, or recovery event generates a log leaf:
   $$\text{LeafData} = \text{Type} \parallel \text{Timestamp} \parallel \text{NormEmail} \parallel \text{Fingerprint} \parallel \text{Generation} \parallel \text{CertBytes}$$
   $$H(\text{leaf}) = \text{SHA256}(0x00 \parallel \text{LeafData})$$
   (Byte `0x00` provides domain separation for leaves).
2. **Internal Node Hashing:**
   $$H(\text{parent}) = \text{SHA256}(0x01 \parallel H(\text{left\_child}) \parallel H(\text{right\_child}))$$
   (Byte `0x01` provides domain separation for interior nodes).
3. **Signed Tree Head (STH):**
   Periodically (every 60 seconds or on each commit), the directory computes the root hash of the tree and signs the tuple:
   $$\text{STH-Payload} = \text{tree\_size} \parallel \text{timestamp} \parallel \text{root\_hash}$$
   $$\text{STH-Signature} = \text{Sign}(SK_{\text{DirectoryAuthority}}, \text{STH-Payload})$$

#### 3.3.2 Verification Mechanisms
1. **Inclusion Proofs ($O(\log N)$):**
   - On every lookup, the directory provides an audit path of sibling hashes from `LeafData` up to `root_hash`.
   - The desktop client recomputes the root hash and validates equality with `sth.root_hash`.
2. **Consistency Proofs ($O(\log M)$):**
   - When the client observes a new STH at tree size $M > N$, it requests a consistency proof verifying that the tree at size $M$ is an exact append-only continuation of the tree at cached size $N$.
   - If consistency verification fails, the client halts directory operations and alerts the user:
     > *"SECURITY ALERT: Directory split-view or history rewrite detected. Communication halted."*
3. **Client Cached Checkpoints:**
   - The desktop client stores the latest verified STH (`tree_size`, `root_hash`, `timestamp`) in its local SQLite database (`directory_checkpoints` table).
4. **Independent Monitors:**
   - Third-party monitors (enterprise auditors, automated monitoring daemons) continuously query the log via `GET /api/v1/transparency/entries`, recompute the Merkle tree independently, and cross-compare observed STHs (STH gossiping) to detect conflicting views.

---

### 3.4 Operation 4: Key Rotation, Replacement Protection & Trust Indicators

#### 3.4.1 Monotonic Generations & Authorized Rotation
- Every user's record has a monotonic integer `generation` (starts at 1).
- **Authorized Rotation (Subkey Renewal):**
  - The client submits the updated certificate with an incremented subkey.
  - The rotation payload **must be signed by the existing active primary signing key**.
  - The directory verifies the primary signature, increments `generation` ($1 \rightarrow 2$), appends the event as a new leaf in the Merkle tree, and updates the active pointer.

#### 3.4.2 Account Recovery & Key Replacement
If a user loses access to their primary private key (hardware failure without backup):
- **Enterprise Mode:** Replacement requires a cryptographically signed recovery instruction from the designated Enterprise Recovery Authority key (configured via WS-07 Group Policy).
- **Consumer Mode:** The directory initiates a mandatory 7-day cooling-off challenge period. Email notifications and revocation abort links are dispatched to the target address. If not cancelled within 7 days, the new key is committed to the tree with an explicit `RECOVERY` event flag.

#### 3.4.3 Desktop Client Trust Behavior on Key Change
- The desktop client pins all discovered public keys in its local SQLite vault upon first use.
- **Unexplained Key Replacement:** If a directory lookup returns a new primary key for an existing contact without a valid primary-to-primary cross-certification signature:
  1. The client **BLOCKS** email composition and outbox dispatch to that recipient.
  2. The UI raises a modal alert:
     > *"SECURITY ALERT: The public encryption key for <recipient> has changed unexpectedly. This may indicate an account compromise or directory manipulation."*
  3. **No Ordinary Dismissal:** The prompt cannot be bypassed by clicking "Continue" or "OK". The user must explicitly perform an out-of-band fingerprint verification or have corporate IT update the key policy.
- **Trust Indicators (WS-02 Contract):**
  - First-time directory lookups without enterprise CA certification display the amber **`CAUTION: Identity Unverified`** badge.
  - Corporate GPO-provisioned or enterprise-signed keys display the emerald green **`SECURE`** badge.

---

### 3.5 Operation 5: Certificate Revocation

When a private key is suspected of compromise:
1. The client generates an OpenPGP Revocation Certificate (Packet 2, signature type `0x20` for key revocation or `0x28` for subkey revocation).
2. The client submits the revocation certificate to `/api/v1/keys/revoke`.
3. The directory records the revocation in the Merkle tree, marks the active record tombstone, and includes the revocation certificate in all future lookup responses.
4. Clients observing the revocation update the contact record to `Trust.REVOKED` and refuse further encryption.

---

## 4. Abuse Prevention & Operational Resilience

1. **Rate Limiting:** Enforced via token bucket per authenticated user (60 req/min) and IP subnet (120 req/min).
2. **Payload Size Capping:** All submissions are capped at 64 KiB, preventing buffer bloat while accommodating composite post-quantum keys.
3. **Offline Resilience:** If the directory is unreachable, existing contacts cached in the local vault operate unimpeded. Uncached recipients remain queued in the Outbox without sending in plain text.
