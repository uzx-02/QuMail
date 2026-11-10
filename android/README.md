# QuMail 1.0 — Companion Android Architecture & Demonstration Guide

This directory contains the mobile companion client architecture for QuMail, engineered for the **Aavishkar Research Convention** to demonstrate live cross-platform post-quantum cryptographic interoperability.

---

## 1. System Architecture Overview

```
+-------------------------------------------------------------------------+
|                  QUMAIL ANDROID MOBILE ARCHITECTURE                     |
+-------------------------------------------------------------------------+
|                                                                         |
|  [ Presentation Layer ]                                                 |
|  - Jetpack Compose UI (Material 3 Dark Slate & Executive Light)        |
|  - BiometricPrompt (Fingerprint / Face Unlock)                          |
|  - Live Quantum Security Status Badges                                  |
|                              |                                          |
|                              v                                          |
|  [ Platform Security & Storage ]                                        |
|  - Android Keystore System + StrongBox Keymaster (Hardware TEE)        |
|  - SQLCipher Local Encrypted SQLite Database                            |
|                              |                                          |
|                              v                                          |
|  [ Native JNI Cryptographic Core (qumail_crypto_mobile) ]                |
|  - Cross-compiled Rust Shared Library (.so via cargo-ndk)               |
|  - ML-KEM-768 (NIST FIPS 203) Key Encapsulation Mechanism               |
|  - ML-DSA-65 (NIST FIPS 204) Digital Signature Verification            |
|  - RFC 9580 / RFC 9788 OpenPGP-PQ Envelope Parsing                     |
|  - Strict Zeroization of Secret Key Buffers in Memory                   |
|                              |                                          |
|                              v                                          |
|  [ Networking & Synchronization ]                                       |
|  - Standard IMAP IDLE Push Worker (imap.gmail.com:993 via TLS 1.3)     |
|  - QuMail Public-Key Directory HTTPS Client                             |
|                                                                         |
+-------------------------------------------------------------------------+
```

---

## 2. Compiling Native Rust Cryptographic Libraries for Android

The native post-quantum cryptographic core in `qumail_crypto_bridge/` is compiled across all major Android ABIs using `cargo-ndk`:

```bash
# 1. Install Android target architectures
rustup target add aarch64-linux-android armv7-linux-androideabi x86_64-linux-android

# 2. Install cargo-ndk
cargo install cargo-ndk

# 3. Compile release shared libraries (.so)
cd android/qumail_crypto_bridge
cargo ndk -t arm64-v8a -t armeabi-v7a -t x86_64 -o ../app/src/main/jniLibs build --release
```

---

## 3. The 45-Second Aavishkar Live Demonstration Protocol

This script proves the core USP and technical viability to the evaluation panel within the 3-minute presentation limit:

```
[ Step 1: Desktop Compose ] (Time: 0:00 - 0:15)
- Open Desktop QuMail on presentation laptop.
- Compose email to: "researcher@gmail.com".
- Subject: "Aavishkar 2026 — Classified National Quantum Research Brief".
- Body: "Confidential patent specifications and experimental validation data."
- Click "Send Securely" (Sealed with ML-KEM-768 & signed with ML-DSA-65).

[ Step 2: The Google Plaintext Contrast ] (Time: 0:15 - 0:25)
- Hand Android phone to judges or mirror phone screen on projector.
- Open the standard official GMAIL app.
- Open the received email in standard Gmail.
- SHOW JUDGES: The email body is pure ASCII-armored post-quantum ciphertext:
  "-----BEGIN PGP MESSAGE-----
   ... ML-KEM-768 Ciphertext Blob ...
   -----END PGP MESSAGE-----"
- EXPLAIN TO JUDGES: "Google's servers only see this unreadable ciphertext.
  Even if Google or an eavesdropping adversary intercepts and stores this data,
  they can never decrypt it (HNDL threat eliminated)."

[ Step 3: QuMail Android Instant Decryption ] (Time: 0:25 - 0:45)
- Open the QuMail Android App.
- Touch fingerprint sensor (BiometricPrompt unlocks hardware key in Android Keystore).
- QuMail Android automatically decapsulates ML-KEM-768 using the local private key
  and verifies the ML-DSA-65 desktop signature.
- Cleartext instantly appears with a glowing green badge:
  "🛡️ Post-Quantum Secured — ML-KEM-768 & ML-DSA-65 Verified".
```

Total demonstration time: **45 seconds**. Clear, undeniable, and scientifically hardened.
