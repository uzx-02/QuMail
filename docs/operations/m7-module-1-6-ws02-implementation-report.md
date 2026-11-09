# QuMail M7 — Module 1.6 Implementation Report
## WS-02: Cryptographic Identity, Automated Key Discovery & Enterprise Trust

**Milestone:** M7 — Module 1.6  
**Workstream:** WS-02 (Gate 1: Pilot Readiness)  
**Implementation Branch:** `codex/m7-module-1-6-ws02`  
**Baseline Checkpoint:** WS-01 completion `d82ea90`  
**Accepted Module 1.5 Baseline:** `eff3736` | **Closeout Anchor:** `c9a3cf4`  
**Technical Lead & Security Architect:** ChatGPT  
**Implementation Engineer:** Antigravity  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  

---

## 1. Executive Summary

Workstream **WS-02 (Cryptographic Identity, Automated Key Discovery & Enterprise Trust)** establishes the core identity, discovery, and trust infrastructure for QuMail under the newly enacted corporate principle:

> **Zero Cryptographic Friction: Hide cryptographic complexity from employees without weakening identity verification, trust policy, or security enforcement.**

Prior to WS-02:
* Exchanging encrypted mail required employees to manually export armored keys, copy 64-character hexadecimal fingerprints, and execute out-of-band manual verification ceremonies before any encrypted session could commence.
* An unpinned contact triggered hard exceptions (`Failure(Code.SIGNER)`), preventing legitimate mail retrieval.
* The message profile was locked to an experimental research marker (`QM-OPENPGP-PQ-1-EXPERIMENT-M5`).
* Subkey expiration, revocation, and rotation lacked structured lifecycle and historical verification models.

Under WS-02, all four targeted pilot readiness gaps (`M16-KEY-001`, `M16-ONB-001`, `M16-KEY-002`, and `M16-KEY-004`) have been fully resolved. QuMail now automatically discovers public keys via OpenPGP Web Key Directory (WKD) and enterprise directory interfaces, standardizes on the `QM-OPENPGP-PQ-v1` profile with 100% backward compatibility for Module 1.5 envelopes, enforces strict policy-driven trust decisions via a centralized `TrustPolicyEngine`, and provides a stable plain-language `SecurityIndicator` contract for user interface consumption.

---

## 2. Architectural Deliverables & Implementation Details

### 2.1 Automated Key Discovery (`core/key_discovery.py`)
* **OpenPGP Web Key Directory (WKD):**
  - Implemented RFC 9580 / draft-koch-openpgp-webkey-service URL derivation:
    * Computed 20-byte SHA-1 digest of lowercase local part.
    * Encoded using canonical 32-character z-base-32 alphabet (`ybndrfg8ejkmcpqxot1uwisza345h769`).
    * Supported both Advanced (`https://openpgpkey.<domain>/.well-known/openpgpkey/<domain>/hu/<hash>?l=<local>`) and Direct (`https://<domain>/.well-known/openpgpkey/<domain>/hu/<hash>?l=<local>`) discovery methods.
  - Implemented address binding verification: Keys fetched via WKD are rejected with `ADDRESS_MISMATCH` if the certificate User IDs do not explicitly match the queried email address.
  - Payload limits (64 KiB) and timeouts (5.0s) strictly enforced.
* **Enterprise Key Directory Provider:**
  - Implemented `EnterpriseDirectoryProvider` for corporate address books and internal directories, maintaining precedence over public WKD.
* **Bounded-TTL Discovery Cache:**
  - Implemented `CachedKeyDiscoveryService` with configurable TTL (default 24 hours), monotonic timestamp tracking, FIFO capacity eviction, and explicit invalidation.
* **CRITICAL SECURITY ENFORCEMENT:**
  WKD is treated as a **key discovery mechanism, NOT an identity trust mechanism**. Successfully discovered WKD keys are never automatically upgraded to verified identity status. Silent Trust-on-First-Use (TOFU) is strictly prohibited.

### 2.2 Centralized Trust Policy Engine (`core/trust_engine.py`)
* Implemented `TrustPolicyEngine` providing authoritative, centralized evaluation of all trust decisions:
  - `VERIFIED`: Known contact pinned via out-of-band verification or certified under an active enterprise trust anchor. Key is active and authorized.
  - `DISCOVERED_NOT_VERIFIED`: Usable public key was discovered via WKD or enterprise directory, address matches, but out-of-band identity trust has not been established. (Permits encryption, but displays unverified identity indicator).
  - `ENCRYPTED_NOT_VERIFIED`: Inbound message decrypted successfully, but sender identity is not independently verified.
  - `CHANGED_BLOCKED`: The key fingerprint does not match the historical pinned key for this address (defending against potential MITM or unauthorized key substitution).
  - `VERIFICATION_FAILED`: Signature check failed, outer/inner metadata mismatch, key revoked, or key expired.
  - `SECURITY_UNAVAILABLE`: Key could not be discovered or verification service is offline.
  - `LOCAL_ENROLLED`: Local user's own enrolled account identity.
* Prevents false trust upgrades: Mathematical signature validity or successful encryption never upgrades an unverified sender to `VERIFIED`.

### 2.3 Trust Indicator Contract (`core/security_indicators.py`)
* Authored the contract defining consumer-facing security states for WS-05 UI rendering:
  - `SECURED_BY_QUMAIL` (Green): Emitted strictly when signature is valid, identity is verified, replay is fresh, headers match, and key is active.
  - `ENCRYPTED_UNVERIFIED` (Amber/Yellow): Post-quantum encrypted and signature valid, but sender identity is unverified.
  - `EXTERNAL_CORRESPONDENT` (Neutral/Gray): External contact discovered via public directory.
  - `SIGNATURE_INVALID` (Red Alert): Signature verification failure or replay conflict.
  - `IDENTITY_MISMATCH` (Red Alert): Sender address does not match certificate or outer/inner headers mismatch.
  - `KEY_REVOKED_OR_EXPIRED` (Red Alert): Signer key is expired or revoked.
  - `CHANGED_BLOCKED` (Red Alert): Key changed unexpectedly.
  - `VERIFICATION_UNAVAILABLE` (Neutral/Gray): Missing certificate or network outage.
* All indicators provide plain-language headlines, non-technical descriptions, and actionable advice without exposing hexadecimal fingerprints or raw protocol exceptions.

### 2.4 Cryptographic Profile Standardization (`QM-OPENPGP-PQ-v1`)
* Defined `PROFILE_V1 = 'QM-OPENPGP-PQ-v1'` as the primary post-quantum wire profile.
* Preserved `PROFILE_LEGACY_M5 = 'QM-OPENPGP-PQ-1-EXPERIMENT-M5'`.
* Standardized `SUPPORTED_PROFILES = (PROFILE_V1, PROFILE_LEGACY_M5)`.
* Outbound messages emit `QM-OPENPGP-PQ-v1`.
* Inbound message parser (`experiments/m5/mime.py`) accepts both `QM-OPENPGP-PQ-v1` and `QM-OPENPGP-PQ-1-EXPERIMENT-M5`, ensuring 100% backward-compatible decryption of all Module 1.5 historical envelopes.
* Unsupported profiles are rejected with `Code.PROFILE`.

### 2.5 Subkey Lifecycle & Rotation (`core/key_lifecycle.py`)
* **Expiration Monitoring:** Inspects subkey validity period and generates proactive alerts when expiration is within 30 days (`EXPIRING_SOON`). Detects expired keys (`EXPIRED`).
* **Rotation vs. Replacement:**
  - Authorized Rotation: Root fingerprint remains identical, subkeys rotate, retired subkeys recorded, and historical signatures remain verifiable.
  - Unauthorized Replacement: Root fingerprint changes without cross-certification -> triggers `UNAUTHORIZED_ROOT_REPLACEMENT` and `CHANGED_BLOCKED`.
* **RFC 4880/9580 Historical Verification:**
  Signatures are evaluated with respect to message date: a message signed while a key was active remains historically valid even after the key subsequently expires or rotates.

### 2.6 Enterprise Trust Architecture (`core/enterprise_trust.py`)
* Implemented `EnterpriseTrustDirectory` and `TrustAnchor`.
* Supports administrator-provisioned organization trust roots (e.g. `@company.com`).
* Certified enterprise contacts within authorized domains are automatically recognized as `VERIFIED` without manual employee fingerprint ceremonies.
* Extended `experiments/m3/vault.py:pin_contact` to support `'enterprise-directory'` as an approved pinning method.

---

## 3. Automated Test Verification Results

All **131 automated tests** passed cleanly:

| Test Suite File | Focus Area | Tests Executed | Passed | Failed |
|---|---|:---:|:---:|:---:|
| `tests/test_startup.py` | Modern default launch, CLI flags, dry-run network isolation | 11 | 11 | 0 |
| `tests/test_ws01_bootstrap_hygiene.py` | Provider resolution, PE CFG `0xc160`, PrivacyFilter, code hygiene | 14 | 14 | 0 |
| `tests/test_ws02_identity_and_trust.py` | WKD discovery, z-base-32, TrustEngine, SecurityIndicators, Profile v1, lifecycle | 25 | 25 | 0 |
| `tests/test_ws02_security_assurance.py` | Historical time evidence, mandatory RFC 3161 signedAttrs, certificate path validation, anti-SSRF WKD, Ed25519 admin trust, Module 1.5 compat | 59 | 59 | 0 |
| `tests/test_cryptographic_roundtrip.py` | End-to-end M5 crypto roundtrip, Ed25519, replay detection, MIME parser | 15 | 15 | 0 |
| `tests/test_cancellation_submission_semantics.py` | Outbox cancellation, uncertain submission recovery, crash semantics | 7 | 7 | 0 |
| **Total** | **Complete Modern Regression Suite** | **131** | **131** | **0** |

---

## 4. Production Readiness Gap Resolution Status

| Gap ID | Description | Severity | Prior Status | WS-02 Status | Evidence |
|---|---|:---:|:---:|:---:|---|
| **M16-KEY-001** | Experimental wire profile marker | High (P1) | OPEN | **RESOLVED** | `QM-OPENPGP-PQ-v1`, `SUPPORTED_PROFILES`, `test_mime_parse_inner_accepts_v1_and_legacy_m5`, `test_module_1_5_legacy_message_complete_inbound_parsing_and_verification` |
| **M16-ONB-001** | Manual out-of-band fingerprint verification | High (P1) | OPEN | **RESOLVED** | `core/key_discovery.py`, `core/enterprise_trust.py`, `IdentityService.discover_and_import_contact`, `test_wkd_provider_success`, `test_enterprise_trust_valid_administrator_authorization` |
| **M16-KEY-002** | No key expiration enforcement or renewal alerts | Medium (P1) | OPEN | **RESOLVED** | `core/key_lifecycle.py:evaluate_key_expiration` (< 30-day warning), `test_evaluate_key_expiration_alert_under_30_days` |
| **M16-KEY-004** | Lack of historical signer expiration policy | Medium (P2) | OPEN | **RESOLVED** | `core/key_lifecycle.py:verify_historical_signature` (time-aware verification with trusted timestamp evidence), `test_historical_signature_valid_with_trusted_tsa_evidence` |

---

## 5. Scope Boundary Compliance

In accordance with WS-02 constraints:
* No IMAP IDLE or background mailbox synchronization was introduced (deferred to WS-03).
* No message or attachment size limits were altered (deferred to WS-03).
* No automated outbox reconciliation worker was introduced (deferred to WS-04).
* The 3-pane UI overhaul remains deferred to WS-05 (WS-02 provides the backend engine and indicator contract).
* No Windows installer or GPO packaging was introduced (deferred to WS-06).
* No live Google OAuth, SMTP, or IMAP operations were conducted; all tests use deterministic mocks and fixtures.
* Baselines `eff3736`, `c9a3cf4`, `6b16f36`, `d82ea90`, and `cd2b43e` remain fully preserved.

---

## 6. WS-02 Security Assurance Closeout

Following targeted technical lead review of checkpoint `cd2b43e`, four critical security assurance areas were remediated, verified, and documented prior to WS-03.

### 6.1 Findings
1. **Historical Signature Verification:** An OpenPGP signature creation-time field is untrusted metadata controlled by the signer. If a key subsequently expires or is revoked/compromised, an adversary holding that private key could backdate a forged signature to claim pre-expiry creation. Evaluating historical validity solely against claimed signature time violated cryptographic trust boundaries.
2. **WKD Network Security:** The initial HTTP fetcher did not validate redirect destinations against destination host boundaries, did not defend against Server-Side Request Forgery (SSRF) targeting loopback or private cloud metadata services (e.g. `169.254.169.254`), lacked DNS rebinding defense between validation and TCP connection, and did not reject non-binary Content-Types (e.g. `text/html`).
3. **Enterprise Trust Boundaries:** Storing a provenance string (`enterprise-directory`) in local storage is not cryptographic proof of administrator authorization. A cryptographically sound enterprise directory must authenticate administrator authorization manifests with digital signatures, strictly enforce domain scoping, immediately propagate revocations, and prevent silent fallback to unverified public WKD when an enterprise key is revoked.
4. **Module 1.5 Wire Compatibility:** Merely checking that `SUPPORTED_PROFILES` contained the legacy string did not prove end-to-end compatibility of accepted Module 1.5 wire messages against the native post-quantum provider (`qumail-m5-provider.exe`), nor did it verify replay detection, header integrity, or absence of cryptographic downgrade.

### 6.2 Fixes Applied
1. **Time-Aware Historical Signature Verification (`core/key_lifecycle.py`):**
   - Implemented `verify_historical_signature` and `TimestampEvidence` supporting RFC 3161 TSA tokens, authenticated vault replay receipts, and trusted notaries.
   - Enforced **Backdating Defense**: When a key is expired or revoked and no independent trusted timestamp evidence is provided, QuMail returns `INDETERMINATE_NO_TRUSTED_TIME` (`is_valid=False`).
   - Differentiated Revocation Reasons: Keys revoked due to `KEY_COMPROMISED` invalidate all signatures postdating compromise; only signatures with authenticated receipts strictly predating the compromise timestamp remain valid.
2. **Hardened HTTPS WKD Fetcher (`core/key_discovery.py`):**
   - Implemented `secure_wkd_fetch`, `validate_domain`, and `is_ip_prohibited`.
   - **Anti-SSRF Protection:** Resolves hostnames and validates all resolved IPs against loopback (`127.0.0.0/8`, `::1`), RFC 1918 private (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `fc00::/7`), link-local (`169.254.0.0/16`, `fe80::/10`), carrier-grade NAT (`100.64.0.0/10`), and multicast ranges.
   - **DNS Rebinding Defense:** Pins the TCP connection directly to the pre-validated IP address while verifying the TLS certificate against the SNI hostname.
   - **Redirect Hardening:** Revalidates every redirect destination (max 2 hops); strictly rejects HTTP downgrades and redirects to foreign domains.
   - **Payload & Content-Type Defense:** Enforces strict 64 KiB ceiling with early stream abortion; rejects HTML or non-binary responses.
   - **Non-Blocking Architecture:** Added `lookup_async` and `discover_async` backed by thread pools for non-blocking UI execution.
3. **Cryptographically Authenticated Enterprise Directory (`core/enterprise_trust.py`):**
   - Introduced `TrustAnchor.admin_public_key` (Ed25519) and `EnterpriseContactRecord.admin_signature`.
   - Differentiated `CRYPTOGRAPHICALLY_SIGNED` from `LOCAL_ADMIN_PROVISIONED` policy boundaries.
   - Canonical authorization payload: `QuMail-Enterprise-Auth-v1:{anchor_id}:{email}:{fingerprint}:{expires_at}` verified via Ed25519.
   - Domain Scoping: Enforced exact domain and subdomain matching (rejecting unauthorized domains and subdomain spoofing).
   - Conflict & Fallback Policy: Authenticated enterprise directory records take absolute precedence over public WKD. If an enterprise key is revoked or expired, sending is blocked and silent fallback to public WKD is strictly prohibited.
4. **End-to-End Module 1.5 Compatibility Suite (`tests/test_ws02_security_assurance.py`):**
   - Authored complete native provider tests for `QM-OPENPGP-PQ-1-EXPERIMENT-M5` messages: verifies decryption, composite ML-DSA-65/Ed25519 signature verification, replay receipt persistence, and duplicate detection.
   - Verified that `QM-OPENPGP-PQ-v1` roundtrip functions identically.
   - Verified strict rejection of unknown profiles (`QM-OPENPGP-PQ-UNSUPPORTED-v99`) and tampered wire payloads (no cryptographic downgrade).

### 6.3 Remaining Limitations
- **External TSA Network Client:** The timestamp verification engine parses and validates `TimestampEvidence` data structures; live automated network querying of RFC 3161 TSA servers over HTTP/TSP remains mock-tested in WS-02 and will be connected to an enterprise time service in enterprise deployment phases.
- **Hardware Token / Smartcard Anchors:** Enterprise trust anchors currently support Ed25519 software keys and Windows Credential Manager DPAPI master keys; hardware PKCS#11 / FIPS YubiKey support is deferred to post-Module 1.6 milestones.
- **WKD Directory Publishing:** QuMail implements client-side WKD discovery; generating and uploading static WKD directories to corporate web servers is an administrative out-of-band operational task.

### 6.4 Test Evidence Summary
- **Total Tests:** 131 passed.
- **Security Tests:** 59 dedicated security assurance tests in `tests/test_ws02_security_assurance.py`.
- **Failures / Skips:** 0 failed, 0 skipped.

### 6.5 Trust Assumptions
1. **Local Endpoint Boundary:** The Windows user session and process memory are assumed uncompromised by root-level malware during cryptographic operations.
2. **Administrator Key Authenticity:** The administrator Ed25519 public key configured in a `TrustAnchor` is provisioned through authenticated administrative channels (e.g. signed configuration file or Windows Group Policy).
3. **No Silent TOFU:** Network key availability (WKD) is explicitly assumed to be an unauthenticated transport channel until verified out-of-band or certified by an enterprise trust anchor.

### 6.6 Historical Timestamp Evidence Clarification & Final Corrections

Following targeted technical lead guidance for final WS-02 acceptance, historical timestamp evidence sources, verification procedures, and local receipt security boundaries have been formalized and verified:

#### A. RFC 3161 Time-Stamp Token Offline Verification
The implementation in `core/key_lifecycle.py:verify_rfc3161_token_offline` provides strict, offline verification of existing RFC 3161 TimeStampToken DER bytes:
1. **ASN.1 CMS Structure Validation:** Parses ASN.1 CMS `ContentInfo` with `contentType = id-signedData` (RFC 5652) and `SignedData` containing `encapContentInfo` with `eContentType = id-ct-TSTInfo` (RFC 3161). Decodes `TSTInfo` and validates GeneralizedTime `genTime`.
2. **Message-Imprint Matching:** Compares `TSTInfo.messageImprint.hashedMessage` byte-for-byte against the expected message digest (`expected_message_digest`). Rejects any token whose message imprint does not match the exact target message digest.
3. **SignerInfo Identification & Certificate Matching:** Matches `SignerInfo.sid` (`issuerAndSerialNumber` or `subjectKeyIdentifier`) to candidate certificates in `SignedData.certificates`. Rejects tokens with absent signer certificates, no matches, or ambiguous multiple matches.
4. **Mandatory CMS Signed Attributes (`signedAttrs`):** Per RFC 3161 Section 2.4.2, CMS `signedAttrs` in `SignerInfo` are mandatory. Direct signature over encapsulated `eContent` without signed attributes is strictly rejected (no direct-signature fallback).
   - Enforces exactly one `id-contentType` attribute whose value is `id-ct-TSTInfo`. Duplicates, missing attributes, or contradictory content types are rejected.
   - Enforces exactly one `id-messageDigest` attribute. Duplicates, missing attributes, or malformed values are rejected.
   - Recomputes the digest over encapsulated `TSTInfo` bytes using the declared digest algorithm (SHA-256, SHA-384, or SHA-512) and verifies exact match against `id-messageDigest`.
   - Verifies the TSA signature over the canonical DER-encoded `signedAttrs` re-tagged as `SET OF` (`0x31`).
5. **TSA Leaf Certificate KeyUsage & Critical Extension Handling:**
   - Critical extensions: Fails closed on unrecognized critical extensions.
   - KeyUsage: If present, MUST assert `digitalSignature` or `contentCommitment` (`nonRepudiation`), and MUST NOT assert `keyCertSign` or `crlSign`.
   - ExtendedKeyUsage: Enforces that the TSA certificate possesses `ExtendedKeyUsage` with `timeStamping` (OID `1.3.6.1.5.5.7.3.8`).
   - Validity period: Enforces certificate validity at timestamp generation time (`not_before <= genTime <= not_after`).
6. **Genuine Cryptographic Certificate Path Validation (`_verify_certificate_path`):**
   - Validates that the TSA certificate chains through genuine cryptographic signatures to a configured trust anchor in `trusted_tsa_certificates`.
   - Traverses candidate CA certificates; verifies `BasicConstraints` with `ca=True` on all issuing authorities.
   - Enforces `path_length` constraint (`pathLenConstraint`) on all issuing CAs.
   - Enforces `KeyUsage.keyCertSign` on all issuing CAs when KeyUsage is present.
   - Checks critical extensions on all certificates along the path; fails closed on unrecognized critical extensions.
   - Prohibits weak or insecure certificate signature hash algorithms (MD5, SHA-1).
   - Verifies validity period dates (`not_before <= genTime <= not_after`) on all certificates in the chain.
   - Cryptographically validates each certificate's digital signature using the issuing authority's public key (`issuer_pub_key.verify()`). Does **not** treat issuer name matching or cert presence alone as successful chain validation.
   - Enforces self-signature verification on root trust anchors.
7. **TSA Policy Enforcement:** Where a required policy is configured (`required_policy_oid`), verifies that `TSTInfo.policy` matches the requirement; fails closed on mismatch.
8. **Offline vs. Live TSA Distinction:** WS-02 strictly implements and tests **offline verification** of pre-existing tokens. Live network acquisition of new tokens from a remote TSA service is an operational network task and is not required for local offline evidence verification.

#### B. Authenticated Receipts in Local Vault (Corrected Rollback & Clock Limitations)
The local vault replay receipt mechanism (`experiments/m5/services.py:120-135`) serves as authenticated local observation evidence under corrected security claims:
1. **Receipt Storage & Key:** Stored in the encrypted SQLite table `accounts` under key `m5_seen_v1` as a JSON map of replay keys: `replay_key = signer['fingerprint'] + '/' + ident` (binding the sender root fingerprint and message-ID, with inner `From` verified against the certificate).
2. **Recorded Digest:** SHA-256 hexadecimal digest of the decrypted, authentic inner MIME `raw` stream (covering all inner headers, body parts, and attachments).
3. **Wall-Clock Observation Timestamp:** `first_seen = int(time.time())` is a **wall-clock observation timestamp**, not a monotonic clock. It reflects the local endpoint OS clock when QuMail received and verified the message, and is subject to local NTP step adjustments, clock drift, or local clock modifications.
4. **Tamper Protection & Rollback Limitations (Honest Assessment):**
   - The account record is encrypted with AES-256-GCM using a 32-byte DPAPI-protected master key stored in the Windows Credential Manager. Authenticated Associated Data (AAD) binds vault ID, account ID, and revision counter.
   - **No Independent Rollback Detection:** A SQLite revision counter protected only within the same database is **not** independent rollback detection.
   - AES-GCM authentication protects receipt integrity against in-place modification, but does **not** independently prevent deletion of the database or restoration of an older valid database backup file.
   - Independent rollback detection is **not implemented** in Module 1.6 (planned for WS-07 using out-of-vault monotonic storage).
5. **Absence & Observation Invariants:**
   - A local vault receipt can establish prior QuMail observation under its documented Windows endpoint, vault-integrity, and clock assumptions.
   - **Crucial Invariant 1 (Prior Observation vs Creation Time):** A local receipt establishes *prior QuMail observation*. It **DOES NOT** prove the sender's original signature creation time.
   - **Crucial Invariant 2 (Absence is Not Proof of Non-Observation):** Receipt absence, database deletion, or suspected database rollback must **never** be interpreted as proof that a message was not previously observed. It merely leaves historical validity indeterminate under Backdating Defense rules.

#### C. Trusted Notary Evidence Status
The `TimestampEvidenceSource.TRUSTED_NOTARY` source is **unsupported in Module 1.6**. Any verification attempt providing this source is rejected with `HistoricalValidity.INVALID_EVIDENCE` ("Trusted notary evidence source is currently unsupported in Module 1.6."). Notary counter-signature schemas and verification procedures remain deferred to future enterprise archival milestones.

---

## 7. WS-02 Final Compliance Corrections Summary

### 7.1 Mandatory Signed Attributes & Path Qualification Corrections

| Requirement | Behavior Before Correction | Behavior After Correction | Evidence |
|---|---|---|---|
| **Mandatory CMS `signedAttrs`** | Allowed direct-signature fallback over `eContent` when `signedAttrs` was absent. | Strictly rejected if `signedAttrs` is absent (RFC 3161 Section 2.4.2). | `test_rfc3161_offline_verification_absent_signed_attrs_rejected` |
| **`id-contentType` Attribute** | Accepted missing or duplicated content-type attributes without rejection. | Strictly requires exactly one `id-contentType` equal to `id-ct-TSTInfo`. | `test_rfc3161_offline_verification_missing_content_type_rejected`, `test_rfc3161_offline_verification_duplicate_content_type_rejected`, `test_rfc3161_offline_verification_incorrect_content_type_rejected` |
| **`id-messageDigest` Attribute** | Accepted missing or duplicated message-digest attributes. | Strictly requires exactly one `id-messageDigest` matching recomputed digest of `eContent`. | `test_rfc3161_offline_verification_missing_message_digest_rejected`, `test_rfc3161_offline_verification_duplicate_message_digest_rejected`, `test_rfc3161_offline_verification_signed_attrs_and_digest_mismatch_rejected` |
| **TSA Leaf KeyUsage** | Did not inspect KeyUsage on TSA leaf certificate. | Enforces `digitalSignature` or `contentCommitment`; strictly rejects `keyCertSign` and `crlSign`. | `test_rfc3161_offline_verification_tsa_leaf_invalid_key_usage_rejected` |
| **CA BasicConstraints & KeyUsage** | Checked `ca=True` only, without `pathLenConstraint` or CA `keyCertSign`. | Enforces `BasicConstraints` `ca=True`, `path_length` constraint, and `KeyUsage.keyCertSign`. | `test_rfc3161_offline_verification_ca_key_usage_and_basic_constraints`, `test_rfc3161_offline_verification_ca_path_len_constraint_exceeded` |
| **Critical Extensions** | Did not check critical extension OIDs. | Fails closed on any unrecognized critical extension. | `test_rfc3161_offline_verification_unrecognized_critical_extension` |
| **Prohibited Signature Hashes** | Permitted weak certificate signature hash algorithms. | Strictly rejects weak certificate signature hash algorithms (MD5, SHA-1). | `test_rfc3161_offline_verification_prohibited_weak_hash_algorithm` |

### 7.2 Explicit PKIX Qualification Limitations

The QuMail Module 1.6 certificate path validator evaluates genuine cryptographic signatures, validity periods, basic constraints, path lengths, KeyUsage, EKU, and critical extensions. However, in accordance with zero-compromise engineering integrity:
* Full RFC 5280 PKIX features—including `NameConstraints` permitted/excluded subtrees, `PolicyConstraints`, `PolicyMappings`, and online CRL/OCSP revocation checking—are **not implemented** in Module 1.6 and are **not claimed**.
* Timestamp token path validation operates strictly offline against locally supplied trust anchors and bundled intermediate certificates.
