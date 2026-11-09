# QuMail Cryptographic Key Lifecycle & Rotation Operations
## Subkey Expiration, Authorized Rotation, Historical Verification & Memory Hygiene

**Milestone:** M7 — Module 1.6  
**Document:** Operations & Key Management Guide  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  

---

## 1. Overview and Operational Philosophy

Cryptographic security in QuMail depends on maintaining active, authorized subkeys while managing lifecycle transitions cleanly. 

WS-02 introduces automated lifecycle management that:
1. Monitors subkey validity periods and provides proactive renewal warnings before keys expire.
2. Supports authorized key rotation without breaking historical message readability.
3. Defends against unauthorized root key substitution.
4. Preserves historical signature verification under RFC 4880 and RFC 9580 time-aware rules.

---

## 2. Key Validity Periods & Proactive Expiration Alerts

### 2.1 Subkey Validity Rules
* Subkeys are generated with an initial validity period of **365 days (1 year)** from creation.
* Primary certification root keys do not expire by default, but can be explicitly retired or revoked.

### 2.2 Expiration Monitoring (`core/key_lifecycle.py`)
`evaluate_key_expiration` monitors subkeys and categorizes validity:

| State | Condition | UI Behavior | Action Required |
|---|---|---|---|
| `ACTIVE` | More than 30 days until expiration | Normal operation | None |
| `EXPIRING_SOON` | 30 days or fewer until expiration | Amber notification banner | Prompt one-click subkey rotation |
| `EXPIRED` | Expiration timestamp has passed | Red security warning | Subkey rotation required; sending blocked |
| `REVOKED` | Explicit revocation signature issued | Red security alert | Immediate retirement of key material |

---

## 3. Subkey Rotation vs. Key Replacement

A critical security distinction enforced by QuMail is distinguishing **authorized subkey rotation** from **unauthorized key replacement**:

```
AUTHORIZED SUBKEY ROTATION                      UNAUTHORIZED ROOT REPLACEMENT
Root Key: AAAA (Unchanged)                      Root Key: AAAA -> BBBB (Changed!)
Old Signing: S1                                 Old Signing: S1
New Signing: S2 (Signed by Root AAAA)           New Signing: S2
Old Encryption: E1                              Old Encryption: E1
New Encryption: E2 (Signed by Root AAAA)        New Encryption: E2
RESULT: APPROVED (Historical records kept)      RESULT: BLOCKED (CHANGED_BLOCKED alert)
```

### 3.1 Authorized Rotation
When an employee initiates subkey rotation:
1. The local primary root key issues a subkey revocation signature (`0x28`) for the outgoing subkeys with reason `KeyRetired`.
2. The primary root key generates and certifies fresh post-quantum signing and encryption subkeys.
3. The outgoing subkey fingerprints are appended to the contact's `retired_subkeys` list in the vault.
4. **Anti-Rollback Invariant:** If a remote correspondent or server attempts to present a subkey that was previously retired, `experiments/m3/vault.py:import_contact` rejects the transaction with `BoundaryError(Code.TRUST)`.

### 3.2 Unauthorized Replacement
If an incoming message or directory lookup presents a **different primary root fingerprint** for an already established contact:
* QuMail classifies the transition as `UNAUTHORIZED_ROOT_REPLACEMENT`.
* The contact's state is set to `CHANGED_BLOCKED`.
* Outbound encryption to that recipient is blocked, and inbound messages display a prominent red `Security Alert — Key Changed Unexpectedly` warning.
* Communication remains blocked until the change is verified through an approved out-of-band channel or enterprise administrator intervention.

---

## 4. RFC 4880 / RFC 9580 Time-Aware Historical Verification & Backdating Defense

In standard OpenPGP implementations, when an annual subkey expires, previously received emails signed by that subkey are often erroneously flagged as having "invalid" or "untrusted" signatures.

Conversely, a naive implementation that evaluates validity against an unauthenticated `signature_time` packet field creates a severe security vulnerability: **backdating attacks**. An adversary who compromises or acquires an expired private key could craft a signature today with a falsified creation date from 2 years ago, tricking the client into validating it as authentic historical correspondence.

### 4.1 Security Invariant: Signature Creation Time is Not Trusted Evidence
- The OpenPGP signature creation timestamp packet (`0x02` subpacket) is untrusted metadata controlled by whoever holds the private key.
- Claimed signature time alone **CANNOT** prove that a signature was created before key expiration, revocation, or compromise.

### 4.2 Defensible Trusted Time Evidence (`TimestampEvidence`)
To establish true historical validity, QuMail requires independent, authenticated time evidence:

1. **RFC 3161 Time-Stamp Protocol (TSA) — Offline Verification:**
   - Cryptographically verified TimeStampToken DER proofs (`core/key_lifecycle.py:verify_rfc3161_token_offline`).
   - Parses ASN.1 CMS `ContentInfo` (`id-signedData`, RFC 5652) and `SignedData` containing encapsulated `TSTInfo` (`id-ct-TSTInfo`, RFC 3161).
   - **Single-Signer Enforcement:** Enforces that the TimeStampToken contains exclusively the TSA's signature (exactly one `SignerInfo` in `SignedData.signerInfos`; multiple signers are strictly rejected per RFC 3161 §2.4.2).
   - **Message-Imprint Matching:** Enforces that `TSTInfo.messageImprint.hashedMessage` strictly matches the expected message digest (`expected_message_digest`). Any mismatch causes immediate rejection.
   - **SignerInfo Identification & Certificate Matching:** Matches `SignerInfo.sid` (`issuerAndSerialNumber` or `subjectKeyIdentifier`) to candidate certificates in `SignedData.certificates`. Rejects missing, unmatched, or ambiguous certificates.
   - **Mandatory CMS Signed Attributes (`signedAttrs`):** Per RFC 3161 Section 2.4.2, CMS `signedAttrs` in `SignerInfo` are mandatory. Direct signature over encapsulated `eContent` without signed attributes is strictly rejected (no direct-signature fallback).
     * Enforces exactly one `id-contentType` attribute whose value is `id-ct-TSTInfo`. Duplicates, missing attributes, or non-matching content types are rejected.
     * Enforces exactly one `id-messageDigest` attribute. Duplicates, missing attributes, or malformed values are rejected.
     * Recomputes the digest over encapsulated `TSTInfo` bytes using the declared digest algorithm (SHA-256, SHA-384, or SHA-512) and verifies exact match against `id-messageDigest`.
     * **Signer-Certificate Identification (RFC 3161 §2.4.2 & RFC 5816):** Mandates exactly one signer-certificate identifier attribute in `signedAttrs`:
       - `SigningCertificate` with `ESSCertID` (RFC 2634, SHA-1 certHash).
       - `SigningCertificateV2` with `ESSCertIDv2` (RFC 5035 / RFC 5816, default SHA-256, or declared SHA-384/SHA-512/SHA-1 certHash).
       - Validates `certHash` directly against the DER encoding of the exact TSA certificate chosen for verification.
       - Rejects missing, duplicate, conflicting, or mismatched signer-certificate identifiers. SignerInfo identifier matching alone is not a substitute.
     * Verifies the TSA signature over the canonical DER-encoded `signedAttrs` re-tagged as `SET OF` (`0x31`).
   - **TSA Certificate Profile (RFC 3161 §2.3):**
     * Critical extension whitelisting: fails closed on unrecognized critical extensions.
     * KeyUsage enforcement: If KeyUsage extension is present, MUST assert `digitalSignature` or `contentCommitment` (`nonRepudiation`), and MUST NOT assert `keyCertSign` or `crlSign`.
     * **ExtendedKeyUsage Profile:** The certificate MUST contain **exactly one** ExtendedKeyUsage extension, MUST be marked **critical**, and MUST **exclusively** contain `id-kp-timeStamping` (`1.3.6.1.5.5.7.3.8`). Rejects non-critical EKU, duplicate EKU, and additional purposes (e.g. `serverAuth`, `clientAuth`).
     * Validity period: Enforces certificate validity at timestamp generation time (`not_before <= genTime <= not_after`).
   - **Genuine Cryptographic Certificate Path Validation:** When `trusted_tsa_certificates` trust anchors are configured, validates the TSA certificate via genuine cryptographic signature verification up to a configured anchor:
     * Traverses intermediate CA certificates in `SignedData.certificates`.
     * Enforces `BasicConstraints` with `ca=True` on all issuing CAs (rejects `ca=False` or missing extension).
     * Enforces `path_length` constraint (`pathLenConstraint`) on all issuing CAs (fails if intermediate count exceeds limit).
     * Enforces `KeyUsage.keyCertSign` on all issuing CAs when KeyUsage is present.
     * Checks critical extensions on all certificates along the path; fails closed on unrecognized critical extensions.
     * Prohibits weak or insecure certificate signature hash algorithms (MD5, SHA-1).
     * Enforces validity period of all path certificates at timestamp generation time (`not_before <= genTime <= not_after`).
     * Cryptographically verifies the digital signature of every certificate using the issuing authority's public key (`issuer_pub_key.verify()`). Does **not** treat issuer name matching or cert presence alone as chain validation.
     * Validates self-signature on root trust anchors.
   - **Explicit PKIX Qualification Limitations & Revocation Scope (Honest Assessment):**
     * While QuMail performs genuine cryptographic chain signature validation, CA basic constraints, path length enforcement, KeyUsage validation, critical EKU profile validation, and critical extension whitelisting, it is **not** a full RFC 5280 PKIX implementation.
     * NameConstraints permitted/excluded subtrees, PolicyConstraints, and PolicyMappings are **not implemented** in Module 1.6 and are explicitly not claimed.
     * Online revocation checking (OCSP / CRL distribution points) is **not implemented** in offline verification mode; verification relies on configured local trust anchors and cryptographic certificate validity windows.
   - **TSA Policy Enforcement:** Where a required policy is configured (`required_policy_oid`), verifies that `TSTInfo.policy` matches the requirement; fails closed on mismatch.
   - **Operational Distinction:** Distinguishes offline verification of an existing token from obtaining a new token from a live TSA. Offline verification operates deterministically in zero-network environments.

2. **Authenticated Local Vault Replay Receipts (Corrected Claims):**
   - **Receipt Structure:** Recorded in the local encrypted SQLite table `accounts` under key `m5_seen_v1` as a JSON dictionary mapping sender replay keys to receipt records (`dict(digest=digest, first_seen=int(time.time()))`).
   - **Digest Recorded:** Hex-encoded SHA-256 digest of the complete decrypted and verified inner MIME payload (`raw`, covering all inner headers, body parts, and attachments).
   - **Identity & Key Binding:** Replay key strictly binds the sender's verified root fingerprint and the message-ID (`replay_key = signer['fingerprint'] + '/' + ident`), while verifying that the inner `From` header matches the certified sender address.
   - **Wall-Clock Observation Timestamp:** `first_seen = int(time.time())` is a **wall-clock observation timestamp**, not a monotonic clock. It reflects the local endpoint OS clock when QuMail received and verified the message, and is subject to local NTP step adjustments, clock drift, or local clock modifications.
   - **Tamper Protection & Rollback Limitations (Honest Assessment):**
     * The account record is encrypted with AES-256-GCM using a 32-byte DPAPI-protected master key stored in Windows Credential Manager. Authenticated Associated Data (AAD) binds the vault ID, account ID, and revision counter.
     * **No Independent Rollback Detection:** A SQLite revision counter protected only within the same database is **not** independent rollback detection.
     * AES-GCM authentication protects receipt integrity against in-place modification, but does **not** independently prevent deletion of the database or restoration of an older valid database backup file.
     * Independent rollback detection is **not implemented** in Module 1.6 (planned for WS-07 using out-of-vault monotonic storage).
   - **Absence & Observation Invariants:**
     * A local vault receipt can establish prior QuMail observation under its documented Windows endpoint, vault-integrity, and clock assumptions.
     * **Crucial Invariant 1 (Prior Observation vs Creation Time):** A local receipt establishes *prior QuMail observation*. It **DOES NOT** prove the sender's original signature creation time.
     * **Crucial Invariant 2 (Absence is Not Proof of Non-Observation):** Receipt absence, database deletion, or suspected database rollback must **never** be interpreted as proof that a message was not previously observed. It merely leaves historical validity indeterminate under Backdating Defense rules.

3. **Trusted Cryptographic Notaries (Unsupported in Module 1.6):**
   - The `TRUSTED_NOTARY` evidence source is explicitly marked **UNSUPPORTED** in Module 1.6.
   - Any historical verification attempt supplying `TimestampEvidenceSource.TRUSTED_NOTARY` is rejected with `HistoricalValidity.INVALID_EVIDENCE` ("Trusted notary evidence source is currently unsupported in Module 1.6.").

### 4.3 Granular Historical Verdicts (`verify_historical_signature`)

| Historical Verdict | Condition | Meaning |
|---|---|---|
| `VALID_HISTORICAL` | Trusted time evidence exists, and $t_{\text{evidence}} \le t_{\text{expires}} \land t_{\text{evidence}} < t_{\text{revoked}}$ | Cryptographically and historically authentic. |
| `INDETERMINATE_NO_TRUSTED_TIME` | Key is currently expired or revoked, and **no trusted timestamp evidence** was provided. | Cannot verify historical validity; unauthenticated claimed signature time rejected (Backdating Defense). |
| `EXPIRED_AT_CREATION` | Verified timestamp proves signature was created after key expired ($t_{\text{evidence}} > t_{\text{expires}}$). | Invalid; key was expired at signing. |
| `REVOKED_AT_CREATION` | Verified timestamp proves signature was created after key was revoked ($t_{\text{evidence}} > t_{\text{revoked}}$). | Invalid; key was revoked at signing. |
| `KEY_COMPROMISED` | Key was revoked due to `KEY_COMPROMISED` and timestamp postdates compromise point, or no prior receipt exists. | Untrusted; key was compromised. |
| `INVALID_EVIDENCE` | Timestamp evidence is malformed, unverified, or contradictory ($t_{\text{claimed}} > t_{\text{evidence}}$). | Invalid evidence rejected. |
| `PREDATES_KEY` | Claimed or evidence timestamp predates key creation. | Invalid signature date. |

### 4.4 Revocation Reason Differentiation
Not all revocations are equivalent:
* **Key Superseded / Key Retired (`KEY_SUPERSEDED`, `KEY_RETIRED`):** Normal lifecycle retirement. Signatures with trusted timestamp evidence pre-dating the retirement date remain valid.
* **Key Compromised (`KEY_COMPROMISED`):** Private key was stolen or exposed. All signatures postdating the compromise timestamp are invalidated. Only signatures with authenticated prior receipts recorded strictly *before* the compromise point can be historically trusted.

---

## 5. Runtime Memory Hygiene & Limitations

### 5.1 Native Provider Memory (Rust)
Inside `qumail-m3-provider.exe` and `qumail-m5-provider.exe`:
* Secret keys and intermediate cryptographic buffers are managed using Rust's memory-safe semantics.
* Sensitive key pairs in Sequoia and OpenSSL are cleared from heap memory upon process drop.
* Subprocess IPC operates over anonymous unidirectional pipes, terminating immediately after each operation.

### 5.2 Python Runtime Memory Limitations (Honest Assessment)
In accordance with Module 1.6 integrity requirements, we explicitly document the limitations of Python runtime memory management:
* In CPython 3.12, strings (`str`) and byte objects (`bytes`) are immutable heap objects.
* While Python variables can be deleted (`del data`) and garbage collection invoked (`gc.collect()`), CPython’s small object allocator does not guarantee immediate zeroization of physical RAM pages.
* Complete in-memory zeroization of sensitive plaintext buffers requires mutable `bytearray` structures and native memory wiping (`memset_s` / `SecureZeroMemory`), which is scheduled for formal hardening under **WS-07 (Forensic Hardening & Replay Armor)**.
