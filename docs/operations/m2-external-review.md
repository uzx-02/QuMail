# M2 external cryptographer/protocol review package

Prepared 2026-10-05 (Asia/Calcutta). **Not externally reviewed or approved.**
M2 engineering proof complete; M2 exit pending external expert review.
M2 remains PARTIAL. This package has not been transmitted or published.

## Decision requested and reviewer qualifications

Under canonical §54 M2 Review, assess whether the candidate composition,
provider behavior and secret boundaries support approving this bounded profile
proof, require corrections, or disqualify the candidate. Do not treat this
request as approval to deploy, package or send production mail.

The lead human reviewer should have demonstrable applied-cryptography review
experience with OpenPGP RFC9580/RFC9980, composite KEM/signature processing,
AEAD streaming/finalization, and Rust/native FFI. Include an email-protocol
reviewer familiar with RFC3156/RFC9788 and a native-crypto/compiler specialist
for MSVC/OpenSSL diagnostic and side-channel questions where the lead lacks that
expertise. Independence means a human reviewer other than this implementation
agent; another AI assessment or test result does not qualify.

Record reviewer identity/qualifications, date, exact experiment hashes, scope,
findings with severity, required corrections, accepted residual risks and an
explicit accept/request-changes/reject decision. No sign-off fields are prefilled.

## Review materials and immutable inputs

- [Current acceptance and exact execution](m2-validation.md).
- [Proposed ADR 003](../adrs/003-m2-provider-proof.md).
- [Provider/standards/license evaluation and warning assessment](m2-provider-evaluation.md).
- [Typed contract](../../experiments/m2/src/contract.rs),
  [provider/interop proof](../../experiments/m2/src/lib.rs),
  [native probes](../../experiments/m2/src/backend_probe.rs).
- [Exact upstream inputs](../../experiments/m2/inputs.json),
  [ordinary Cargo.lock](../../experiments/m2/Cargo.lock),
  [diagnostic Cargo.lock](../../experiments/m2/backend-probe/Cargo.lock),
  [reproduction guide](../../experiments/m2/README.md).
- [Diagnostic patch recipe](../../experiments/m2/prepare-probe.ps1),
  [source/lock audit program](../../experiments/m2/audit-inputs.py),
  [native build configuration](../../experiments/m2/build-native.ps1),
  [test runner](../../experiments/m2/run.ps1).
- [Source/build/test identity audit](evidence/m2/20261005-input-audit.json),
  [normal](evidence/m2/20261005-normal.txt),
  [reverse](evidence/m2/20261005-reverse.txt),
  [legacy regression](evidence/m2/20261005-legacy.txt).
- [Native warnings](evidence/m2/native-warnings.txt), prior nine-test evidence,
  original input hashes and dated decision snapshots in the same evidence folder.

At execution, branch `codex/m2-provider-proof` had HEAD
`5880dd4d6bc15a2e111c49d929432e6ed2419f33`. The tested working-tree hashes identify
the M2 proof, now preserved in a local checkpoint with unchanged experiment inputs.
The local `m2-reviewer-request.md`, prepared after committing, records the exact
checkpoint SHA and provides the unfilled human decision template. It is a
separate uncommitted handoff document, not additional executed-test evidence.
M1's validated 023c941 and review branch are preserved. The diagnostic accessor
audit establishes the narrow source difference, not broader crypto correctness.

Sequoia 2.4.1 source `0b0c8c7f038b829de2da0d28a822941d8600f3ee`;
rPGP 0.21.0 `c2b192e52b2e7f99777196539ea79b37f1f9ff30`;
OpenSSL 3.5.9 `45e844fa2a14ec92d146bd8f5778ac130b6625fb`.
Sequoia `crypto-openssl` only; rPGP `pqc` only; both default features disabled.
OpenSSL static VC-WIN64A, no-shared/no-tests/no-module/no-comp/no-asm, upstream
/O2 /MT /W3 /wd4090. Rust 1.99.0, MSVC cl 19.50.35728.0, Windows 10.0.26200 x64.
No Linux, hosted M2, optimized Rust release build or production IPC claim.

## Candidate profile and composition

The test-only name is `M2-EXPERIMENT-RFC9980-AES256-GCM`:

| Layer | Frozen experimental setting |
|---|---|
| Certificate | v6 primary/signing key ID30 ML-DSA-65+Ed25519; one v6 encryption subkey ID35 ML-KEM-768+X25519; SEIPDv2 capability |
| Recipient encryption | v6 PKESK; provider performs the standardized composite KEM processing; no local combiner |
| Encrypted data | SEIPDv2, AES-256/GCM, 4096-byte chunks; no compression; provider owns fresh session key/salt/nonce rules |
| Signature | One required v6 composite signature; SHA-512 for generated profile messages; each component must validate |
| Email fixture | RFC3156 two-part ASCII-armored combined sign/encrypt; RFC9788 hp=cipher and HP-Outer snapshots inside signed/encrypted bytes |
| Protected metadata fixture | From, To, Date, Message-ID, Subject and experimental X-QuMail-Profile; generic outer Subject |
| Limits | 1 MiB input/output/key blob and 32 recipients; conservative proof bounds, not qualification of §42's product budgets |

Published RFC vectors retain their specified algorithms and hashes; they are
known-answer integration evidence, not silently relabeled candidate-profile
messages. Full MIME semantics, Bcc, replay, attachment/header/parser limits and
render/reply behavior belong to M5/M6. No independent MUA rendered this fixture.

## Trust and secret boundaries

| Boundary | Implemented proof behavior | Remaining assurance question |
|---|---|---|
| Request → CryptoPolicy | One typed profile/route/extension/resource gate for generate/seal/open | Future UI/API must have no bypass; currently no production entry point is wired |
| Sender → recipient | Public-only certificate bytes; secret blobs, untrusted/changed/unsupported recipient rejected | Synthetic trust input is not identity enrollment or directory authentication |
| Policy → provider | Single selected provider; no retry, substitution, portal or KME route | Provider is trusted; policy cannot detect a malicious provider fabricating verification |
| Provider → caller | Private staging; EOF/integrity/required signature/limits before VerifiedPlaintext | No secure-zeroization, side-channel or process-crash containment claim |
| Native failure → result | Structured error; whole operation catches unwind, including parsing/fingerprinting | Abort/OOM/segfault require future helper-process containment; stderr policy needs qualification |

The full matrix and named tests are in validation. Negative evidence includes
wrong signer/recipient, bit flip/truncation, malformed/weak profiles and keys,
unsupported provider-generated AEAD/hash/critical notation, each composite
signature component, health failures and staged-output failure. Mock status/error
tests prove boundary propagation only; the following native tests are separate.

## Native path trace and fault evidence

At exact Sequoia source, `src/crypto/backend/openssl.rs:52` implements random by
creating `ossl::rand::EvpRandCtx::new_hmac_drbg` in its private OnceLock context,
SHA2-512, then calling generate. `src/crypto/mod.rs` uses this for session keys.
`ossl` 1.5.3 `src/rand.rs:62` calls EVP_RAND_fetch(HMAC-DRBG),
EVP_RAND_CTX_new with no parent, EVP_RAND_instantiate (prediction resistance 1),
then EVP_RAND_generate. Errors become Sequoia errors; some mandatory-algorithm
assumptions elsewhere panic instead.

OpenSSL provider `providers/implementations/rands/drbg.c` obtains entropy/nonce
through `providers/common/provider_seeding.c`. Core dispatch in
`crypto/provider_core.c` reaches `crypto/rand/prov_seed.c`:
`ossl_rand_get_user_entropy`/`ossl_rand_get_user_nonce` use a configured seed
context when present, otherwise the OS-pool paths. Windows seeding source is
`providers/implementations/rands/seeding/rand_win.c`, including BCryptGenRandom
and conditional CryptoAPI branches. OS-failure branches were **source inspected,
not directly faulted**.

Because the context is private, a process-default RAND configuration would miss
the real selected path. The separate diagnostic crate exposes only the private
context pointer, gated by `qumail-m2-fault-probe`. Verified source audit: 651 files,
only Cargo.toml feature declaration and appended accessor differ. No native
library or implementation logic changes. Faults run in fresh children with a
30-second parent timeout; the unmodified-provider lane never installs them.

| Native probe | Actual observation | Limit |
|---|---|---|
| Empty TEST-RAND seed via RAND_set_seed_source_type, forced source initialization | Sequoia random/keygen/encryption return failure; native errors include retrieving nonce/instantiating DRBG | Random-source deprivation; failure occurs at nonce acquisition before entropy completion. Not direct BCryptGenRandom failure or a replacement production RNG |
| Nonexistent provider via EVP_set_default_properties on that context | Random/keygen errors; raw encryption hits mandatory-SHA256 panic with native unsupported reason | Broad provider unavailability; not corruption of one primitive |
| Provider fault injected after real successful random-health probe | Typed seal AND open contain actual native panic as Backend(Panic), no output | Tests unwinding, not process abort or OS resource exhaustion |
| Default-provider self_test call | Returns 1; source dispatch has no self_test callback | No FIPS self-test occurred; return value is not a health assurance |

Supported-control references: OpenSSL
[seed-source configuration](https://docs.openssl.org/3.5/man3/RAND_set_DRBG_type/),
[test random source](https://docs.openssl.org/3.5/man7/EVP_RAND-TEST-RAND/),
[default properties](https://docs.openssl.org/3.5/man3/EVP_set_default_properties/).
Exact local source determines the traced behavior, not assumptions about a
different OpenSSL release or FIPS module. Mock failed-health status is separately
tested. There is no default-provider self-test failure callback to corrupt here.

## Warning and assurance questions for reviewers

1. **Composition/profile:** confirm final RFC9980 processing, algorithm/version/
   hash constraints, both signature components, certified recipient capability,
   critical extension rejection and GCM settings. Is the bounded header fixture
   adequate for M2, with the stated M5/M6 gates?
2. **Verification/release:** review stream EOF/final AEAD/signature sequencing,
   the single-signature rule and error paths. Does the typed boundary ever admit
   success after partial verification? Review rPGP peer semantics separately;
   the common outer precheck is not independent parser assurance.
3. **Native behavior:** assess the real mandatory-SHA256 panic at Sequoia
   `packet/key/v6.rs:282`, absence of a default-provider self-test callback, and
   readiness probe's limited meaning. Are these acceptable for the candidate
   pending a production helper, or do they require upstream correction first?
4. **Context allocation:** Sequoia calls deprecated `OsslContext::new_lib_ctx`;
   ossl documents fallback to NULL/default context on allocation failure.
   No allocation-failure injection was executed. This is a disclosed upstream
   isolation/assurance concern, not a protocol downgrade silently accepted here.
5. **Native diagnostics:** M1's 42 liboqs common-header emissions relate to its
   barrier fallback; Frodo call excluded from minimal ML-KEM build; selected
   candidate does not link liboqs. Separately review 871 OpenSSL MSVC emissions:
   C4267 688/C4244 79 (conversions, including ML-DSA/key codecs), C4133 66
   (pointer types including conditional interlocked calls), C4334 36 (shift
   width), C4319 2 (widening). Counts establish neither exploitability nor safety.
   231 Perl locale lines are build diagnostics, not cryptographic findings.
   Diagnostic path compilation exposes 22 upstream Rust deprecation warnings,
   including the context constructor; no suppression was introduced.
6. **Compiler/side channels:** no-asm and /O2 do not prove constant time. Identify
   required assembly/range/timing review for ML-KEM/ML-DSA/X25519/Ed25519/AES-GCM
   and shared code on target builds before production-provider approval.
7. **Future boundary:** confirm error coarsening, panic/abort handling, stdout/
   stderr restrictions and resource limits for the proposed Rust helper/Python
   interface. Synthetic verified-recipient state is not M3 enrollment assurance.

## Approval boundary

Demonstrated: Windows functional interoperability, policy matrix, real native
failure/containment and retained known vectors/negative/header tests.
Source inspected: native entropy route, absent default-provider self-test,
allocation fallback, warning categories and upstream configuration.
Unverified: independent human review, constant-time behavior, OS entropy-source
outage handling specifically, allocation/abort stress, Linux/IPC/package support,
full mail-client interoperability and production identity verification.

Project/Qt/provider redistribution, historical OQS artifacts/ciphertext and
release approval remain separate gates. No license decision is invented. The
specific next step is human review of this hash-identified package, with bounded
M2 corrections if requested; do not begin M3, publish or enable production sending.
