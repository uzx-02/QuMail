# QuMail 1.0 Stable Prototype: Development Tracking

This register records verified limitations, security observations, pending validations, and improvement opportunities for future development. QuMail 1.0 is a functional concept demonstration. It is not claimed to be production-grade, enterprise-ready, or independently audited.

The entries below come from source inspection of the Desktop application, the Android application, the native Rust providers, the Cloudflare directory, and the ESP32 firmware documentation. Cross-platform Desktop-to-Android and Android-to-Desktop encrypted mail has been demonstrated. That interoperability is treated as confirmed project functionality.

<!-- TOC -->
- [Status model](#status-model)
- [1. Verified baseline](#1-verified-baseline)
- [2. Architecture and deployment](#2-architecture-and-deployment)
- [3. Desktop security](#3-desktop-security)
- [4. Android application](#4-android-application)
- [5. Directory and WebLink service](#5-directory-and-weblink-service)
- [6. Hardware and QKD demonstration](#6-hardware-and-qkd-demonstration)
- [7. Cryptographic implementation](#7-cryptographic-implementation)
- [8. Testing, documentation, and process](#8-testing-documentation-and-process)
- [9. Product scope](#9-product-scope)
- [10. Suggested next iteration](#10-suggested-next-iteration)

---

### Status model

| Status | Meaning |
|---|---|
| Confirmed | Verified in the current source or authoritative firmware documentation. |
| Needs validation | Source suggests a gap or risk, but runtime behavior or deployment context was not verified. |
| Demonstration | Intentionally limited educational or concept capability. Not represented as production infrastructure. |
| Future | Accepted improvement for a later iteration. |

Practical impact is an engineering priority for future work, not a formal audit severity.

---

### 1. Verified baseline

| Capability | State | Evidence |
|---|---|---|
| Desktop PQ mail | Implemented | Rust providers build OpenPGP v6 certificates with ML-DSA-65 plus Ed25519 signing and ML-KEM-768 plus X25519 encryption. |
| Desktop WebLink | Implemented | AES-256-GCM payload encryption, key in the URL fragment, optional passcode and recipient email OTP. |
| Desktop mail transport | Implemented | Gmail OAuth 2.0 with PKCE, IMAP over TLS, and SMTP with STARTTLS. |
| Cloud key directory | Implemented | Cloudflare Worker with D1, Google OIDC, single-use challenge, ML-DSA proof of possession, device records, and tombstones. |
| Android companion | Implemented subset | Expo and React Native UI, JNI bridge to the Rust crypto library, Gmail REST transport, directory enrollment, PQ send and receive. |
| Cross-platform PQ mail | Demonstrated | Desktop to Android and Android to Desktop encrypted messages were exchanged successfully. |
| Hardware entropy | Demonstration | ESP32 Zener-noise circuit streams debiased bytes. It is not a validated TRNG and does not perform QKD. |
| Quantum key distribution | Not implemented | No quantum channel, key distillation, or QKD key ingestion exists in the message path. |

---

### 2. Architecture and deployment

| ID | Item | Status | Practical impact | Recommendation |
|---|---|---|---|---|
| A1 | The default directory endpoint is the development Worker (`qumail-directory-dev`). | Confirmed | Medium | Deploy a production Worker with separate secrets, D1 backups, monitoring, and documented availability expectations before any wider pilot. |
| A2 | The Flask directory in `services/directory/` is a development harness. Rotation does not verify the transition signature, revocation is unauthenticated, and lookup has no authentication. | Confirmed | High if deployed | Keep it out of deployment documentation and label the package as test-only. Do not expose it beyond loopback. |
| A3 | PQ sends are capped at four recipient or device certificates. Larger device sets are truncated by the client. | Confirmed | Medium | Define device-selection behavior, or support multiple envelopes per message. Surface truncation in the UI. |
| A4 | The production crypto provider accepts a bounded inner payload (64 KiB). Large-body behavior was not exercised. | Needs validation | Unrated | Verify how Desktop handles bodies above the provider limit. Add a clear error or a documented split strategy. |
| A5 | The Cloud Directory is centralized and cannot be self-hosted without a separate Worker deployment. | Confirmed | Medium | Publish a deployment guide and consider a portable directory contract for future operators. |
| A6 | Desktop is Windows-only by design. Android is the only mobile client. iOS is untested. | Confirmed | Low | State platform support explicitly in release material. |

---

### 3. Desktop security

| ID | Item | Status | Practical impact | Recommendation |
|---|---|---|---|---|
| B1 | A change in a contact's device set is accepted and re-pinned with a warning. The send path does not block on the warning. | Confirmed | Medium | Fail closed on a pin mismatch and require an explicit re-trust action before sending. |
| B2 | Test-only peer key fabrication activates when `PYTEST_CURRENT_TEST` is set or a test-domain address is used. | Confirmed | Medium if leaked into production | Gate it behind an explicit test build flag and reject it under enterprise policy. |
| B3 | `sampleEntropy` calls a pool method that does not exist and always falls back to OS randomness while reporting hardware status. | Confirmed | Low | Correct the call and make the UI show the actual provenance of returned bytes. |
| B4 | ETSI QKD mode only polls status. No QKD key is fetched or consumed, yet the status surface can imply QKD is active. | Confirmed | Medium for user expectation | Label the mode as a demonstration. Do not present QKD as protecting message traffic. |
| B5 | Hardware entropy never reaches PQ key generation. Key generation uses the operating system CSPRNG. | Confirmed | Low | Keep the demonstration isolated, or define a reviewed conditioning and provenance path before integration. |
| B6 | WebLink passcode mode derives the payload key with `HMAC(raw_key, passcode)` and stores a fast `SHA-256(passcode + salt)` tag server-side. | Confirmed | Medium | Use a memory-hard KDF or a per-link high-entropy secret, and verify the passcode inside the encrypted payload. |
| B7 | Desktop OAuth tokens use DPAPI-wrapped Fernet keys. The vault master key uses Windows Credential Manager and per-record AES-GCM. | Documented | None | Keep the README and policy wording split by storage mechanism so the distinction stays accurate. |

---

### 4. Android application

| ID | Item | Status | Practical impact | Recommendation |
|---|---|---|---|---|
| C1 | WebLink payload keys are generated with `Math.random()` in the current Android build. | Confirmed | High | Replace with `expo-crypto.getRandomBytes` or a native bridge call. |
| C2 | Incoming PQ mail accepts sender certificates returned by the directory. There is no local sender-fingerprint pinning. | Confirmed | Medium | Add a persistent TOFU pin store and refuse a changed sender fingerprint. |
| C3 | The application PIN is stored as `btoa(pin)` and compared in plaintext-equivalent form. It has no KDF, salt, or lockout. | Confirmed | Medium | Treat the PIN as a UI gate and document that role. Move to a salted KDF and Keystore-bound authentication in a later iteration. |
| C4 | `CryptoBridge` fallbacks return zero-filled proof arrays and a successful vault unlock when the native module is absent. | Confirmed | Medium | Fail closed and surface a clear native-module error instead of a synthetic success. |
| C5 | Custom IMAP and SMTP settings UI exists, but no IMAP or SMTP transport implementation was found. Gmail REST is the implemented mail path. | Needs validation | Medium | Implement mailbox transport or hide the custom-mailbox path until it works. |
| C6 | The default Google OAuth client ID is compiled into the app source. | Confirmed | Low | Move client configuration to build-time environment values for distributable builds. |
| C7 | The Android project has no automated test suite or CI typecheck script. | Confirmed | Medium | Add `tsc --noEmit`, lint, and a small bridge contract test suite. |
| C8 | The full secret certificate is stored through SecureStore and passed through the JavaScript bridge. | Confirmed | Medium | Keep long-lived secret material inside the native vault and expose only operations. |
| C9 | Android WebLink sends default to five views without a passcode, while Desktop enables recipient email OTP by default. | Confirmed | Low | Align defaults or make the difference visible during compose. |

---

### 5. Directory and WebLink service

| ID | Item | Status | Practical impact | Recommendation |
|---|---|---|---|---|
| D1 | WebLink payload keys are sent only in the URL fragment, and the Worker stores ciphertext. This matches the intended zero-knowledge design. | Confirmed | None | Preserve this property in any future portal changes and add a regression test. |
| D2 | WebLink attachments are limited to 30 MB total and 512 KiB per chunk. | Confirmed | Low | Document the limit in the compose UI and in release notes. |
| D3 | Recipient email gating stores a salted hash of the normalized address, not the raw address. | Confirmed | None | Keep the Worker and client normalization functions in sync with a shared test vector. |
| D4 | Device revocation writes tombstones and cascades session invalidation. | Confirmed | None | Add operator tooling and audit export for tombstone events. |
| D5 | The active WebLink path has no sender signature. An unused Ed25519 WebLink module exists but is not called. | Confirmed | Low | Remove the dead module or wire a defined sender-binding scheme, then update documentation. |

---

### 6. Hardware and QKD demonstration

| ID | Item | Status | Practical impact | Recommendation |
|---|---|---|---|---|
| E1 | The ESP32 Zener-noise circuit is an educational hardware-integration demonstration. The firmware report states that it does not perform QKD and is not a validated TRNG. | Demonstration | None, when described accurately | Keep the report as the authoritative reference. Describe the board as a noise-source demonstration, not as quantum hardware. |
| E2 | The schematic leaves the Zener starved, Q1 unbiased, and the ADC input unbiased. The observed signal is plausibly pickup noise. | Demonstration | None, when described accurately | Present this as an engineering limitation and a future hardware revision item. |
| E3 | The firmware continues streaming when no meaningful signal is present, and the variance window affects display only. | Demonstration | Low | Add a documented signal-presence gate and on-device health indication in a future board revision. |
| E4 | The firmware source header says "Production ESP32 Firmware" while the authoritative report disclaims production TRNG status. | Confirmed inconsistency | Low | Correct the header comment in a future revision. Do not edit the demonstration report. |
| E5 | The ETSI GS QKD 014 client implements status and key request methods, but only status is called. The local simulator uses `secrets.token_bytes`. | Demonstration | None in the current message path | Define a future integration contract and test harness for a commercial KEM or QKD device before claiming QKD support. |
| E6 | Conditioned hardware entropy is mixed with OS entropy in the pool, but no PQ operation consumes it. | Demonstration | None | Keep the demo endpoint separate. Document that OS CSPRNG remains the security source for key generation. |

Future hardware direction: integrate a commercially available TRNG or QKD key-delivery interface behind the existing HSM manager seam. Require device authentication, key provenance, health tests, and an auditable fallback policy before any cryptographic use.

---

### 7. Cryptographic implementation

| ID | Item | Status | Practical impact | Recommendation |
|---|---|---|---|---|
| F1 | The native profile string is experimental (`M2-EXPERIMENT-RFC9980-AES256-GCM`). Third-party OpenPGP PQ interoperability is not verified. | Confirmed | Medium for claims | Describe the format as an experimental OpenPGP v6 profile. Do not claim RFC compliance or general interoperability. |
| F2 | Certificate generation requests the ML-DSA cipher suite for the transport-encryption subkey, while policy requires an ML-KEM suite. Tests assert ML-KEM output. | Needs validation | Unrated | Generate a certificate, dump subkey algorithms, and confirm the effective suite. |
| F3 | Key rotation and revocation exist in the vault provider. End-to-end rotation across two live clients was not exercised in this review. | Needs validation | Unrated | Add an integration test for rotate, revoke, and historical decryption. |
| F4 | The production crypto provider rejects peer-verification operations unless the feature is compiled in. | Confirmed | Low | Keep the disabled stubs and document the build feature. |
| F5 | An RSA compatibility module exists for legacy interoperability but is not used by the mail path. | Confirmed | Low | Mark it as experimental utility code or remove it if unused. |
| F6 | PQ messages include the sender's own certificate as an archive recipient. | Confirmed | None | Preserve this behavior and document it in the security model. |

---

### 8. Testing, documentation, and process

| ID | Item | Status | Practical impact | Recommendation |
|---|---|---|---|---|
| G1 | The Desktop suite contains 135 test functions across 16 test files. Prior documentation claimed 143 passing tests. | Confirmed | Low | Record the actual collected and passing counts for each release. |
| G2 | Cross-platform interoperability is demonstrated manually, not covered by an automated end-to-end test. | Needs validation | Medium | Add a two-client harness with fixture accounts and fixed test vectors. |
| G3 | The prior audit described the codebase as production-staged and missed the QKD, storage, and WebLink discrepancies. | Confirmed | Low | Keep the corrected audit and this register as the current record. |
| G4 | The firmware demonstration report must remain unchanged as the authoritative hardware reference. | Process rule | None | Do not edit the report. Update surrounding documentation instead. |
| G5 | The terms already describe the software as a private prototype. The README and audit did not use the same status language. | Confirmed | Low | Use "QuMail 1.0 Stable Prototype" consistently until a production release is declared. |

---

### 9. Product scope

| Item | Position |
|---|---|
| Production readiness | Not claimed. No SLA, independent audit, or enterprise support commitment. |
| Enterprise deployment | Registry policy exists, but deployment hardening, support, and compliance evidence are future work. |
| External interoperability | QuMail clients interoperate with each other. Interoperability with unrelated PQ OpenPGP implementations is not verified. |
| Mail transport | Standard mode is ordinary email over TLS. Only PQ mail and WebLink provide QuMail payload protection. |
| WebLink trust | The directory stores ciphertext and enforces access controls, but it remains a centralized availability and policy dependency. |
| Hardware narrative | The ESP32 board demonstrates a hardware integration path. It is not QKD and not a certified entropy source. |

---

### 10. Suggested next iteration

1. Replace Android WebLink key generation with a CSPRNG, add sender pinning on receive, and make native bridge failures fail closed.
2. Make Desktop contact-pin mismatches block sends until the user explicitly re-trusts the contact.
3. Correct the QKD and entropy status surfaces so demonstrations are never presented as active protection.
4. Strengthen WebLink passcode derivation and align Android and Desktop access-control defaults.
5. Add an automated two-client interoperability test and a CI typecheck for Android.
6. Validate the certificate generation suite, rotation flow, and large-message behavior with reproducible tests.
7. Deploy a hardened production directory with backups, monitoring, and an operator runbook.
8. Define the commercial TRNG or QKD integration contract, including provenance and fallback policy.

---

*This register describes QuMail 1.0 Stable Prototype. It is a development planning document, not a certification or a substitute for an independent security audit.*
