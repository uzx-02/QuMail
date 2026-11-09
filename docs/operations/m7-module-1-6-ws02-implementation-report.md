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

All **72 automated tests** passed cleanly in **23.18 seconds**:

| Test Suite File | Focus Area | Tests Executed | Passed | Failed |
|---|---|:---:|:---:|:---:|
| `tests/test_startup.py` | Modern default launch, CLI flags, dry-run network isolation | 11 | 11 | 0 |
| `tests/test_ws01_bootstrap_hygiene.py` | Provider resolution, PE CFG `0xc160`, PrivacyFilter, code hygiene | 14 | 14 | 0 |
| `tests/test_ws02_identity_and_trust.py` | WKD discovery, z-base-32, TrustEngine, SecurityIndicators, Profile v1, lifecycle | 25 | 25 | 0 |
| `tests/test_cryptographic_roundtrip.py` | End-to-end M5 crypto roundtrip, Ed25519, replay detection, MIME parser | 15 | 15 | 0 |
| `tests/test_cancellation_submission_semantics.py` | Outbox cancellation, uncertain submission recovery, crash semantics | 7 | 7 | 0 |
| **Total** | **Complete Modern Regression Suite** | **72** | **72** | **0** |

---

## 4. Production Readiness Gap Resolution Status

| Gap ID | Description | Severity | Prior Status | WS-02 Status | Evidence |
|---|---|:---:|:---:|:---:|---|
| **M16-KEY-001** | Experimental wire profile marker | High (P1) | OPEN | **RESOLVED** | `QM-OPENPGP-PQ-v1`, `SUPPORTED_PROFILES`, `test_mime_parse_inner_accepts_v1_and_legacy_m5` |
| **M16-ONB-001** | Manual out-of-band fingerprint verification | High (P1) | OPEN | **RESOLVED** | `core/key_discovery.py`, `core/enterprise_trust.py`, `IdentityService.discover_and_import_contact` |
| **M16-KEY-002** | No key expiration enforcement or renewal alerts | Medium (P1) | OPEN | **RESOLVED** | `core/key_lifecycle.py:evaluate_key_expiration` (< 30-day warning) |
| **M16-KEY-004** | Lack of historical signer expiration policy | Medium (P2) | OPEN | **RESOLVED** | `core/key_lifecycle.py:is_signature_historically_valid` (RFC 4880/9580 time-aware) |

---

## 5. Scope Boundary Compliance

In accordance with WS-02 constraints:
* No IMAP IDLE or background mailbox synchronization was introduced (deferred to WS-03).
* No message or attachment size limits were altered (deferred to WS-03).
* No automated outbox reconciliation worker was introduced (deferred to WS-04).
* The 3-pane UI overhaul remains deferred to WS-05 (WS-02 provides the backend engine and indicator contract).
* No Windows installer or GPO packaging was introduced (deferred to WS-06).
* No live Google OAuth, SMTP, or IMAP operations were conducted; all tests use deterministic mocks and fixtures.
* Baselines `eff3736`, `c9a3cf4`, `6b16f36`, and `d82ea90` remain fully preserved.
