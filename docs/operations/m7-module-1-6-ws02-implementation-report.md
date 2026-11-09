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

All **114 automated tests** passed cleanly:

| Test Suite File | Focus Area | Tests Executed | Passed | Failed |
|---|---|:---:|:---:|:---:|
| `tests/test_startup.py` | Modern default launch, CLI flags, dry-run network isolation | 11 | 11 | 0 |
| `tests/test_ws01_bootstrap_hygiene.py` | Provider resolution, PE CFG `0xc160`, PrivacyFilter, code hygiene | 14 | 14 | 0 |
| `tests/test_ws02_identity_and_trust.py` | WKD discovery, z-base-32, TrustEngine, SecurityIndicators, Profile v1, lifecycle | 25 | 25 | 0 |
| `tests/test_ws02_security_assurance.py` | Historical time evidence, RFC 3161 offline validation, anti-SSRF WKD, Ed25519 admin trust, Module 1.5 compat | 42 | 42 | 0 |
| `tests/test_cryptographic_roundtrip.py` | End-to-end M5 crypto roundtrip, Ed25519, replay detection, MIME parser | 15 | 15 | 0 |
| `tests/test_cancellation_submission_semantics.py` | Outbox cancellation, uncertain submission recovery, crash semantics | 7 | 7 | 0 |
| **Total** | **Complete Modern Regression Suite** | **114** | **114** | **0** |

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
- **Total Tests:** 114 passed.
- **Security Tests:** 42 dedicated security assurance tests in `tests/test_ws02_security_assurance.py`.
- **Failures / Skips:** 0 failed, 0 skipped.

### 6.5 Trust Assumptions
1. **Local Endpoint Boundary:** The Windows user session and process memory are assumed uncompromised by root-level malware during cryptographic operations.
2. **Administrator Key Authenticity:** The administrator Ed25519 public key configured in a `TrustAnchor` is provisioned through authenticated administrative channels (e.g. signed configuration file or Windows Group Policy).
3. **No Silent TOFU:** Network key availability (WKD) is explicitly assumed to be an unauthenticated transport channel until verified out-of-band or certified by an enterprise trust anchor.

### 6.6 Historical Timestamp Evidence Clarification

Following targeted technical lead guidance for final WS-02 acceptance, historical timestamp evidence sources and verification procedures have been formalized and demonstrated:

#### A. RFC 3161 Time-Stamp Token Offline Verification
The implementation in `core/key_lifecycle.py:verify_rfc3161_token_offline` provides strict, offline verification of existing RFC 3161 TimeStampToken DER bytes:
1. **ASN.1 CMS Structure Validation:** Parses ASN.1 CMS `ContentInfo` with `contentType = id-signedData` (RFC 5652) and `SignedData` containing `encapContentInfo` with `eContentType = id-ct-TSTInfo` (RFC 3161). Decodes `TSTInfo` and validates the `genTime` GeneralizedTime format.
2. **Message-Imprint Matching:** Compares `TSTInfo.messageImprint.hashedMessage` byte-for-byte against the expected message digest (`expected_message_digest`). Rejects any token whose message imprint does not match the exact target message.
3. **TSA Certificate-Chain Validation:**
   - Extracts TSA certificates from `SignedData.certificates`.
   - Validates that the signing certificate possesses `ExtendedKeyUsage` with `timeStamping` (OID `1.3.6.1.5.5.7.3.8`).
   - Validates certificate validity dates (`not_valid_before` and `not_valid_after`) against token generation time (`genTime`).
   - Validates against configured `trusted_tsa_certificates` trust anchors when specified.
4. **TSA Digital Signature Verification:** Cryptographically validates the TSA RSA/ECDSA signature over `eContent` (or signed attributes) using the public key extracted from the validated TSA certificate.
5. **Rejection of Malformed / Tampered Tokens:** Explicitly rejects oversized tokens (>64 KiB), malformed ASN.1 structures, tampered signature bytes, mismatched digests, missing EKUs, expired TSA certs, and untrusted roots.
6. **Offline vs. Live TSA Distinction:** WS-02 strictly implements and tests **offline verification** of pre-existing tokens. Live network acquisition of new tokens from a remote TSA service is an operational network task and is not required for local offline evidence verification.

#### B. Authenticated Receipts in Local Vault
The local vault replay receipt mechanism (`experiments/m5/services.py:120-135`) serves as authenticated local observation evidence:
1. **Receipt Storage & Key:** Stored in the encrypted SQLite table `accounts` under key `m5_seen_v1` as a JSON map of replay keys: `replay_key = signer['fingerprint'] + '/' + ident` (binding the sender root fingerprint and message-ID, with inner `From` verified against the certificate).
2. **Recorded Digest:** SHA-256 hexadecimal digest of the decrypted, authentic inner MIME `raw` stream (covering all inner headers, body parts, and attachments).
3. **Observation Timestamp:** Monotonic Unix epoch integer `first_seen = int(time.time())` committed immediately upon successful cryptographic verification during live inbound IMAP retrieval.
4. **Tamper Resistance:** Encrypted with AES-256-GCM using a 32-byte DPAPI master key stored in the Windows Credential Manager. Authenticated Associated Data (AAD) binds vault ID, account ID, and revision counter.
5. **Rollback & Deletion Boundaries:** Bounded by local SQLite revision monotonicity. Deletions or rollbacks of the local database cannot forge earlier timestamps, but local state loss destroys receipt history (no distributed transparency log is claimed).
6. **Clock & Endpoint Assumptions:** Relies on local endpoint OS clock integrity and an uncompromised local execution environment.
7. **Observation vs. Creation Time Invariant:** A local vault receipt proves **prior QuMail observation** under its documented trust assumptions. It **DOES NOT** prove the sender's original signature creation time.

#### C. Trusted Notary Evidence Status
The `TimestampEvidenceSource.TRUSTED_NOTARY` source is **unsupported in Module 1.6**. Any verification attempt providing this source is rejected with `HistoricalValidity.INVALID_EVIDENCE` ("Trusted notary evidence source is currently unsupported in Module 1.6."). Notary counter-signature schemas and verification procedures remain deferred to future enterprise archival milestones.
