# M2 provider evaluation

Provider survey date: 2026-10-04; proof update: 2026-10-05, Asia/Calcutta. Canonical requirements: specification
§§35, 37 (I01/I02/I04/I07/I15/I18), 41–42 and 54 M2. This is a local protocol
experiment, not a production send implementation, identity enrollment or release.
See [validation](m2-validation.md) for measured results and
[ADR 003](../adrs/003-m2-provider-proof.md) for the proposed decision.

## Standards checked

| Primary source | Verified status / relevance |
|---|---|
| [RFC 9580](https://www.rfc-editor.org/info/rfc9580/) | July 2024, IETF Standards Track / Proposed Standard; modern OpenPGP foundation. |
| [RFC 9980](https://datatracker.ietf.org/doc/rfc9980/) | June 2026, Proposed Standard; not merely an Internet-Draft. Preferred algorithm IDs are 35 (ML-KEM-768+X25519) and 30 (ML-DSA-65+Ed25519). Composite signature verification requires both components. |
| [9580 errata](https://errata.rfc-editor.org/search/?rfc_number=9580) | Five verified: 8454, 8465, 8466 (native signature/key octet representations), 8432 (reference), 9094 (editorial); two reported: 8814 (compression wording), 8847 (v3 PKESK registry description); 8449 held for update (User ID syntax). Reported changes are not treated as approved replacements. |
| [9980 errata](https://errata.rfc-editor.org/search/?rfc_number=9980) | 9023 is reported, not verified: decryption procedure omits explicitly obtaining the ECDH public key used by the combiner. Do not invent a different combiner. Provider code owns this operation; successful exchange is behavioral evidence, not disposition of the erratum. |

No local algorithm IDs, combiners, KDFs, packet serializers or nonce schedules are
implemented. Raw packets alone do not meet §54's M2 header-fixture requirement.
The continuation therefore executes a bounded RFC 3156/RFC 9788 fixture using
the same provider pair: required ASCII armor, combined signing/encryption,
`hp="cipher"`, protected fields and `HP-Outer`. Both directions preserve verified
inner fields even when the outer Subject changes. This establishes a candidate
header approach, not independent mail-client rendering or full conformance.
Production MIME preparation/decoding remains M5; rendering/replies remain M6.
See the exact [scope and results](m2-validation.md#headerprofile-boundary).

## Exact candidates

Versions were checked against live official release/registry metadata, then
source archives and immutable refs. A blog's old preview version is not substituted
for a current stable release. Crate archive hashes, source refs and backend flags
are in [inputs.json](../../experiments/m2/inputs.json); transitive Rust inputs are
in the experiment's separate Cargo.lock. None changes M1's Python/OQS locks.

| Candidate | Exact immutable source | Disposition |
|---|---|---|
| Sequoia OpenPGP 2.4.1 | `0b0c8c7f038b829de2da0d28a822941d8600f3ee`, `openpgp/` | Primary integration candidate; explicitly `crypto-openssl`, defaults off. 2.4.0 added final RFC 9980 support; 2.4.1 fixes OpenSSL cleanup lifetime. |
| rPGP / crate pgp 0.21.0 | `c2b192e52b2e7f99777196539ea79b37f1f9ff30` | Independent OpenPGP peer; explicitly `pqc`, defaults off. Separate RustCrypto PQ implementation from the selected Sequoia/OpenSSL backend. |
| OpenPGP.js 6.3.2 | `5f33328a3b601fb9c9dce310d1ecc137db0dbc75` | RFC 9580 candidate, but this release's public-key enum has no IDs 30/35. Not a complete preferred-profile peer. |
| GnuPG 2.5.24 | `66dfde9fddd4f928ab25e132221a9a517f06cc7d` | `--allow-9980` opt-in added in 2.5.23; release notes emphasize encryption and experimental FIPS/GCM mode. Source contains ML-DSA IDs/key-generation names; that alone does not prove working composite signing. Not experimentally qualified here. |
| RNP 0.18.1 | `aad1892e4d8423398a0b973bd0a7e4544c359afc` | Optional crypto-refresh/PQC code exists, but source uses private IDs 105/107 for the preferred-looking composites and KMAC-based composition. This is not RFC 9980 IDs 35/30 and its specified construction. Do not relabel or patch it into compliance. |

Primary capability references: [Sequoia source](https://gitlab.com/sequoia-pgp/sequoia/-/tree/0b0c8c7f038b829de2da0d28a822941d8600f3ee/openpgp),
[rPGP release](https://github.com/rpgp/rpgp/releases/tag/v0.21.0),
[OpenPGP.js release](https://github.com/openpgpjs/openpgpjs/releases/tag/v6.3.2),
[GnuPG NEWS](https://github.com/gpg/gnupg/blob/66dfde9fddd4f928ab25e132221a9a517f06cc7d/NEWS),
[RNP IDs](https://github.com/rnpgp/rnp/blob/aad1892e4d8423398a0b973bd0a7e4544c359afc/include/repgp/repgp_def.h),
[RNP build flags](https://github.com/rnpgp/rnp/blob/aad1892e4d8423398a0b973bd0a7e4544c359afc/src/lib/CMakeLists.txt).

## Capability, platform and integration comparison

The following describes inspected APIs/source unless the validation record
explicitly marks behavior as executed. No row implies a complete standards audit.

| Area | Sequoia 2.4.1 | rPGP 0.21.0 | OpenPGP.js 6.3.2 | GnuPG 2.5.24 | RNP 0.18.1 |
|---|---|---|---|---|---|
| RFC 9580 / 9980 | Both in selected backend; other Sequoia backends do not all support PQ | Both with `pqc` | 9580; preferred 9980 composites absent | Partial opt-in capability, full profile unverified | Refresh/PQC optional; inspected PQ format differs from final standard |
| Encryption / signatures | Both preferred composites | Both preferred composites | Classical X25519/Ed25519 etc.; no preferred composites | Encryption documented; signature names present but untested | Draft composite encryption/signatures; not final profile |
| Authenticated content modes | EAX/OCB/GCM APIs; explicit GCM tested | EAX/OCB/GCM APIs; explicit GCM tested | EAX/OCB/GCM; `aeadProtect`, v6 configuration necessary | OCB/other historical modes; experimental GCM flag is not proof of full profile | OCB/EAX APIs; no qualified final-profile GCM evidence |
| Certificates / secret keys | Certificate validation/policy, TSK serialization, encrypted secret material, subkeys | Import/export/binding checks; caller supplies expiration/revocation/key-selection semantics | Public/private key import/export, protection, subkeys | Keyring/agent, import/export, protected secret keys | FFI keystores, import/export/protection |
| Multiple recipients | Encryptor accepts key iterator; tested two | Builder accepts recipient keys; tested two | API arrays; untested here | Multiple recipient options; untested here | Multiple recipients in FFI; untested here |
| Windows / Linux prerequisites | Rust >=1.85; selected OpenSSL backend needs OpenSSL >=3.5 for PQ, C toolchain, Perl, libclang for ossl bindings; Linux needs corresponding compiler/build headers | Rust >=1.88; RustCrypto dependencies; optional native compression disabled here | Node/WebCrypto on both; exact runtime compatibility must be tested | Linux autoconf/make + libgcrypt/libgpg-error and other GnuPG dependencies; Windows Gpg4win/cross-build | CMake/C++ + Botan 3 for PQ/refresh, JSON-C and other declared libraries; Windows/Linux builds |
| Python option | Narrow Rust helper process or reviewed FFI; no Python binding built here | Rust helper/FFI; application must supply more semantic policy | Separate Node process over bounded IPC; no direct Python API | GPGME bindings or status-fd subprocess API; avoid human output parsing | CFFI/ctypes over librnp, with ownership/error review |
| Parser/failure behavior | Typed errors and verification helper; streaming can release data before final verification if misused; buffer and discard on any error | Errors plus explicit verify after consuming stream; low-level API does not enforce application trust; cap decompression separately | Promise rejection; must await signature verification; decompression default can be unlimited unless configured | Exit/status-fd must both be interpreted; plaintext staging and size/time limits are caller obligations | Return codes and operation validity must be checked; FFI caller controls lifetime/limits |

All candidate parser limits require application-level input, output, recursion,
certificate-count, CPU-time and memory policies. The experiment enforces 1 MiB
input/output and 32 recipients, no generated compression, and no plaintext return
before EOF plus verification. This is not a fuzzing campaign or proof of bounded
allocation inside every provider. Production §42's 25 MiB/15 MiB budgets, MIME
depth/parts and 30-second parser budget are not claimed implemented.

Sequoia's RustCrypto backend was inspected and initially attempted. Its explicit
experimental/variable-time approvals are **not** in the final manifest. CNG,
Nettle and Botan support must not be inferred from OpenSSL's PQ capabilities.
For the final proof, OpenSSL is source-built with `no-asm`; neither that choice
nor functional success establishes constant-time behavior.

## License and distribution implications

| Component | Declared license / decision boundary |
|---|---|
| Sequoia | LGPL-2.0-or-later. Linking/FFI/helper packaging and relink/source obligations need owner/legal review; subprocess separation is not an automatic exemption. |
| rPGP | MIT OR Apache-2.0. Retain selected license/notices and review all transitives. |
| OpenPGP.js | LGPL-3.0; bundling Node/JS does not remove license obligations. |
| GnuPG | GPL-3.0-or-later; GPGME and companion components have their own terms. Gpg4win availability is not QuMail redistribution approval. |
| RNP | BSD-2-Clause plus backend/transitive licenses (Botan or OpenSSL). |
| OpenSSL 3.5.9 | Apache-2.0; exact native source, flags, notices and build provenance remain part of eventual packaging review. |

No project license is invented. Existing project/Qt redistribution uncertainty
remains. No installer, compiled native binary, private key or test plaintext is
added to the review files or published.

## Advisory and assurance review

Review is dated, not a claim of absence of vulnerabilities. Retained advisory
metadata is scoped to the inspected releases and does not replace a complete
transitive audit/SBOM or independent cryptographer review.

- OpenPGP.js advisory [CVE-2025-47934](https://github.com/openpgpjs/openpgpjs/security/advisories/GHSA-8qff-qr5q-5pr8)
  concerns signature spoofing and was fixed in 6.1.1/5.11.3; 6.3.2 is outside the
  published affected range. Its release also fixes packet/decompression issues.
- rPGP's [advisories](https://github.com/rpgp/rpgp/security/advisories) include
  malformed-key and deeply nested-message crashes and missing integrity checks
  fixed in 0.19.0. GHSA-9rq6-pw5r-326p lists decompression amplification through
  <=0.20.0 with no patched-version field; 0.21.0 is outside that listed range,
  but this is not proof of safe resource use. Compression remains excluded here.
- RNP 0.18.1 fixes all-zero public-key-encryption session keys (CVE-2025-13470 /
  CVE-2025-13402); old versions must not serve as the comparison baseline.
- GnuPG 2.5.23/24 NEWS includes parser/debug-path fixes; a full libgcrypt/GPGME/
  Gpg4win advisory inventory was not performed because no such build is selected.
- Sequoia's 2.4.1 OpenSSL lifetime fix is included. Its
  [verification UX discussion](https://sequoia-pgp.org/blog/2026/01/12/202601-to-sign-or-not-to-sign/)
  illustrates why key validity and trusted identity cannot be inferred from a
  generic signature-success status. No independent audit of this adapter is claimed.
- [OpenSSL 3.5 advisories](https://openssl-library.org/news/vulnerabilities-3.5/)
  showed the Cargo-packaged 3.5.5 source lagging fixes through 3.5.9. Final native
  input is explicitly 3.5.9, not ambient Conda OpenSSL 3.0.16 and not the initial
  3.5.5 build. No broad cryptographic assurance is inferred from version currency.

Published provider vectors and ecosystem interop reports are useful references,
but neither replaces this task's independently generated exchange. The exact
tested provider pair, message directions, negative cases, platform limitations
and unexecuted gates are recorded separately in the validation document.

## Disposition of the 42 M1 MSVC warnings

Counted 42 occurrences in the retained hosted Windows log for 023c941. They are
repeated emissions of one pragma in liboqs 0.16.0
[`src/common/common.h`](https://github.com/open-quantum-safe/liboqs/blob/5a1a854b0dc9f2141bdc771c555ee60c37950183/src/common/common.h),
not evidence of 42 different vulnerable functions. In the non-GNU/non-Clang
branch, `OQS_MEM_BLACK_BOX(v)` becomes `(void)v`, with no optimization-barrier
guarantee. No warning has been suppressed or reclassified as proof of safety.

Source search at the exact M1 source ref finds the macro's call in
`src/kem/frodokem/external/util.c:129`, in `ct_select`. Upstream
[PR 2431](https://github.com/open-quantum-safe/liboqs/pull/2431) and the release
notes explain the compiler-barrier change for FrodoKEM. M1's recorded build is
MSVC, shared distribution library, OpenSSL OFF, minimal `KEM_ml_kem_768`; FrodoKEM
is excluded. The warning is emitted when common headers are included anyway.
ML-KEM-native has its own barrier handling in
`src/kem/ml_kem/mlkem-native_ml-kem-768_ref/mlkem/src/verify.h`: inline assembly
for GCC/Clang and a volatile global fallback otherwise. These are **source
observations**, not inspection of generated machine code or side-channel tests.

The selected M2 dependency graph uses Sequoia/OpenSSL and rPGP/RustCrypto, not
liboqs. The particular liboqs macro therefore is not in the new candidate's
execution path. This removes its direct applicability, **not the need for
constant-time assurance**. OpenSSL's `no-asm`, Rust functional success and
passing known vectors prove none of that. Native OpenSSL uses optimized `/O2`
C code; exact compiler, algorithm paths, assembly, optimizations and timing
behavior still need expert review on target platforms. The M1 warning remains
a recorded research-provider limitation. No production provider is approved.

The selected OpenSSL build is not warning-free either. Final native-log inspection
found **871 MSVC diagnostics**: C4267 688, C4244 79, C4133 66, C4334 36, C4319 2;
plus 231 Perl locale warning lines. Full redacted diagnostics are retained in
`evidence/m2/native-warnings.txt`. Counts are emissions, not distinct defects.
These are separate from the 42 liboqs messages and from the warning-free final
Rust test compilation. No new warning suppression was added.

Conversion diagnostics include `crypto/ml_dsa/ml_dsa_sign.c`,
`crypto/ml_dsa/ml_dsa_key.c`, AES wrappers, and ML-KEM/ML-DSA key-management and
codec paths. They require range/type review; passing short messages cannot
establish safety for every input length. C4133 appears in libcrypto
`crypto/property/property.c:856` and `crypto/objects/obj_dat.c:238`, as well as
SSL. Inspection traces these to `include/internal/tsan_assist.h:117`, whose
`sizeof(*ptr)` conditional includes both 32-bit and 64-bit interlocked calls.
MSVC diagnoses the incompatible pointer in the unselected expression too;
that source explanation is not generated-code verification. Selected-algorithm
and shared-library warning triage belongs in the outstanding provider review;
the build remains experimental. No claim that this analysis resolves all 871
diagnostics or qualifies the exact compiler/build for production.

## Integration and decision

Recommend the pinned Sequoia/OpenSSL candidate behind the bounded Rust helper
contract in [ADR 003](../adrs/003-m2-provider-proof.md#python-integration-recommendation).
The typed policy/provider contract is now implemented inside the M2 experiment.
The production helper is a recommendation, not a built Python extension/IPC bridge.
Local Windows OpenPGP behavior is executed; Linux builds, clean Windows helper
installation, IPC failure/cancellation, platform resource limits and packaging
are still untested. Configured Windows/Linux availability is not executed support.

**M2 engineering proof complete; M2 exit pending external expert review.**
M2 stays PARTIAL. All 17 tests pass in both orders, including the typed matrix
and real native failure probes. The diagnostic Sequoia copy exposes only the
private context for supported OpenSSL fault controls; normal interoperability
uses the unmodified crate. No native algorithm or production RNG is replaced.

Additional measured limitations: missing-provider selection triggers Sequoia's
mandatory-SHA256 panic; typed whole-operation containment rejects it, including
post-health send/open failure. The default OpenSSL provider has no self_test
callback, so its return of 1 is not a self-test assurance. The local diagnostic
path build displays 22 upstream Rust deprecation warnings (registry Cargo lint
treatment normally hides these), including use of ossl's deprecated context
constructor, which documents default-context fallback on allocation failure.
No allocation-failure experiment or constant-time assurance is claimed.
These findings and reviewer questions are in the
[external review package](m2-external-review.md); no AI approval substitutes for it.
Project/Qt/provider distribution rights and legacy compatibility retain separate
gates. No weaker profile, production fallback or new production path is enabled.
