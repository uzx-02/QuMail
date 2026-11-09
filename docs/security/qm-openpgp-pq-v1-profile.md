# QuMail Cryptographic Profile Specification: QM-OPENPGP-PQ-v1
## Standardized Hybrid Post-Quantum OpenPGP Email Security Profile

**Milestone:** M7 — Module 1.6  
**Document:** Cryptographic Specification & Wire Profile  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  

---

## 1. Executive Summary

The `QM-OPENPGP-PQ-v1` profile formalizes QuMail's cryptographic architecture, transitioning from the experimental development marker (`QM-OPENPGP-PQ-1-EXPERIMENT-M5`) to an enterprise-standardized, versioned post-quantum profile.

This profile specifies:
* Hybrid post-quantum key encapsulation (ML-KEM-768 + X25519).
* Composite post-quantum digital signatures (ML-DSA-65 + Ed25519).
* Authenticated symmetric encryption with AEAD (AES-256-GCM / SEIPD v2).
* Protected header encapsulation (RFC 9788 / draft-autocrypt-protected-headers).
* Full backward compatibility with Module 1.5 historical envelopes.

---

## 2. Cryptographic Algorithm Suite

QuMail implements a dual-layer hybrid architecture ensuring classical 128-bit security guarantees against conventional attackers, combined with NIST FIPS 203/204 post-quantum protection against future cryptanalytically relevant quantum computers (CRQCs):

| Function | Primary Post-Quantum Algorithm | Classical Hardening Algorithm | Standard / Specification | Key / Parameter Size |
|---|---|---|---|---|
| **Root Certification** | ML-DSA-65 | Ed25519 | NIST FIPS 204 / RFC 9580 | 1952 bytes (public) |
| **Message Signing** | ML-DSA-65 | Ed25519 | NIST FIPS 204 / RFC 8410 | 1952 bytes (public) |
| **Key Encapsulation** | ML-KEM-768 | X25519 | NIST FIPS 203 / RFC 7748 | 1184 bytes (public) |
| **Symmetric Cipher** | AES-256 | — | FIPS 197 / RFC 9580 | 256-bit session key |
| **Authenticated Mode** | GCM (AEAD) | — | NIST SP 800-38D | 128-bit tag / 96-bit nonce |
| **Hash Function** | SHA-512 | — | FIPS 180-4 | 512-bit digest |

---

## 3. Key Hierarchy and Subkey Roles

Every QuMail identity adheres to a strictly validated version 6 (v6) OpenPGP certificate hierarchy:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Primary Root Certification Key                        │
│                   Algorithm: ML-DSA-65 + Ed25519 (v6)                       │
│                   Key Flags: Certification only (0x01)                       │
└──────────────────────┬──────────────────────────────┬───────────────────────┘
                       │ Certifies & Binds            │ Certifies & Binds
                       ▼                              ▼
┌──────────────────────────────────────────┐ ┌──────────────────────────────────────────┐
│              Signing Subkey              │ │            Encryption Subkey             │
│   Algorithm: ML-DSA-65 + Ed25519 (v6)    │ │   Algorithm: ML-KEM-768 + X25519 (v6)    │
│   Key Flags: Signing only (0x02)         │ │   Key Flags: Transport Encryption (0x04) │
│   Validity: 365 days (renewable)         │ │   Validity: 365 days (renewable)         │
└──────────────────────────────────────────┘ └──────────────────────────────────────────┘
```

### Certificate Invariants:
1. **Root Key Purpose:** The root key is restricted to certification only. It must NEVER be used directly for signing email bodies or encrypting message payloads.
2. **Subkey Separation:** Signing and encryption capabilities are assigned to distinct, isolated subkeys.
3. **Subkey Binding:** Every subkey must possess an unexpired, unrevoked primary key binding signature (`0x18`) and, for signing subkeys, a primary key cross-certification signature (`0x19`).
4. **Single Active Device:** Each enrolled account context maintains exactly one active signing subkey and one active encryption subkey at any time.

---

## 4. Message Wire Serialization

### 4.1 Outer Transport Envelope (`multipart/encrypted`)
The outer wire format complies with RFC 3156 MIME encapsulation:

```http
Content-Type: multipart/encrypted; protocol="application/pgp-encrypted"; boundary="===============outer_boundary=="
From: sender@domain.com
To: recipient@domain.com
Subject: Encrypted message
Date: Mon, 09 Nov 2026 08:00:00 +0000
Message-ID: <stable_unique_id@domain.com>
MIME-Version: 1.0

--===============outer_boundary==
Content-Type: application/pgp-encrypted
Content-Transfer-Encoding: 7bit

Version: 1

--===============outer_boundary==
Content-Type: application/octet-stream
Content-Transfer-Encoding: 7bit

-----BEGIN PGP MESSAGE-----
[ASCII-Armored Post-Quantum OpenPGP Payload]
-----END PGP MESSAGE-----
--===============outer_boundary==--
```

### 4.2 Inner Protected MIME Structure (`hp=cipher`)
Decryption reveals the inner MIME document containing the genuine, provider-authenticated headers and content:

```http
From: sender@domain.com
To: recipient@domain.com
Subject: Confidential Q7 Architecture Proposal
Date: Mon, 09 Nov 2026 08:00:00 +0000
Message-ID: <stable_unique_id@domain.com>
X-QuMail-Profile: QM-OPENPGP-PQ-v1
X-QuMail-Archive: sender@domain.com
HP-Outer: from: sender@domain.com
HP-Outer: to: recipient@domain.com
HP-Outer: subject: Encrypted message
HP-Outer: date: Mon, 09 Nov 2026 08:00:00 +0000
HP-Outer: message-id: <stable_unique_id@domain.com>
MIME-Version: 1.0
Content-Type: text/plain; charset="utf-8"; hp=cipher
Content-Transfer-Encoding: base64

[Base64-encoded UTF-8 Plaintext Body]
```

### 4.3 Protected Header Snapshot Verification
* The inner document includes `HP-Outer` headers recording exact copies of the outer RFC 5322 metadata.
* During message opening, `experiments/m5/mime.py:parse_inner` compares the outer headers with the inner `HP-Outer` records.
* Any unauthorized modification of the outer headers by an untrusted intermediary is detected and surfaced as a metadata mismatch (`IDENTITY_MISMATCH`).

---

## 5. Backward Compatibility & Migration Strategy

### 5.1 Profile Identification Rules
To preserve seamless interoperability with previously accepted Module 1.5 mailboxes:

1. **Emission Policy:** All newly composed messages emit:
   ```http
   X-QuMail-Profile: QM-OPENPGP-PQ-v1
   ```
2. **Reception Policy:** The inner header parser accepts any profile matching `SUPPORTED_PROFILES`:
   * `QM-OPENPGP-PQ-v1` (Current standard)
   * `QM-OPENPGP-PQ-1-EXPERIMENT-M5` (Module 1.5 legacy envelope)
3. **Rejection Policy:** Any profile identifier outside `SUPPORTED_PROFILES` is rejected with `Failure(Code.PROFILE)`.

### 5.2 Database Storage Migration
* Vault databases created under Module 1.5 store historical replay receipts in `m5_seen_v1` using SHA-256 digests of inner decrypted bytes.
* Because the underlying cryptographic primitives (Sequoia OpenPGP + rPGP ML-KEM/ML-DSA) remain identical, existing database records require **zero destructive migration**.
* Previously recorded replay digests remain valid and continue to prevent duplicate message replays across both `v1` and legacy `M5` profiles.
