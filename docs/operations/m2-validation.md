# M2 validation and acceptance

Updated 2026-10-05 (Asia/Calcutta). **M2 engineering proof complete; M2 exit pending external expert review.**
M2 remains **PARTIAL**. No independent cryptographer/protocol approval has occurred.
This is the bounded isolated proof authorized by the user, not production policy integration.

## Checkout, preservation and evidence attribution

At execution: branch `codex/m2-provider-proof`, HEAD
`5880dd4d6bc15a2e111c49d929432e6ed2419f33`; M2 was local working-tree content.
The M1 branch `codex/m1-hosted-validation` is preserved. Between validated M1
`023c941ec2ef284f6be28b5a9605f1dca9c28787` and that parent, the 15 changed files are
documentation/evidence only. No M1 application, dependency, CI, ADR or evidence
file changed in this continuation. Reference PDF and user data remain untouched.
No push, merge, release, production send integration or M3 work.

The [2026-10-04 validation snapshot](evidence/m2/m2-validation-20261004.txt),
[earlier ADR](evidence/m2/adr003-20261004.txt), original nine-test outputs and
`input-hashes.json` are retained unchanged. The following results belong to the
**2026-10-05 tested working-tree inputs**, recorded in
[evidence/m2/20261005-input-audit.json](evidence/m2/20261005-input-audit.json),
not to unchanged HEAD or the older hash record.

### Local review checkpoint (2026-10-05)

Before checkpointing, all 15 experiment input SHA-256 values matched the above
tested snapshot. A fresh read-only `audit-inputs.py` execution also reproduced
the retained JSON exactly, including diagnostic source changes, native-library
hash, transitive locks and the same 17 normal/reverse test identities. Engineering
tests were not repeated: no experiment input changed. Only handoff documentation
was amended. This accessor-difference audit does not establish cryptographic
correctness. The exact local checkpoint SHA and retained-output hashes are in
`m2-reviewer-request.md`, prepared locally after the checkpoint so it can name
the commit without a self-reference. That request is a separate, uncommitted
handoff document; the proof and evidence are frozen in the checkpoint.

## Acceptance against actual M2 criteria

| M2 criterion | Canonical reference | Evidence and its kind | Current status / remaining action |
|---|---|---|---|
| M1 prerequisite and preservation | §54 Dependencies; ADR 001/002 | Existing exact-SHA hosted evidence; new legacy regression 37 passed/5 warnings; Git inspection | Satisfied at baseline scope |
| Exact standard/provider/version/flags/license evaluation | §§28, 41, 54 | Dated evaluation; runtime OpenSSL version assertion; locked dependencies/source/native hashes. Standards/license/advisory review is inspection | Satisfied for candidate evaluation; distribution approval remains separate |
| Preferred standardized composites | QM-CRYPTO-001/002; §41; §54 | Both providers encrypt/decrypt/sign/verify; each signature component mutation rejected | Engineering proof satisfied; expert approval pending |
| Two independent implementations exchange frozen candidate | QM-INT-001 M2 portion; §54 Acceptance | Sequoia/OpenSSL ↔ rPGP, both key generators, separate keys/public-only recipient inputs, multiple recipients | Satisfied on measured Windows build; no independent MUA/Linux claim |
| AEAD/header-profile fixture | §§41–42; §54 Tests/Docs | AES-256/GCM/SEIPDv2; armored RFC3156/RFC9788 fixture, protected fields survive outer Subject changes | Satisfied for M2 fixture; production MIME M5, rendering/replies M6 |
| Known-answer/negative evidence | QM-CRYPTO-006; §51 T01; §54 | Retained published signature and KEM-message vectors, component/wrong-key/tamper/truncation/malformed tests; new critical-notation/hash/AEAD rejection | Satisfied at M2 proof scope; broad primitive/fuzz/platform qualification M8 |
| Typed policy/provider contract, no downgrade/substitution | QM-SEC-001/002/006; QM-PQC-001; QM-QKD-004; QM-PORTAL-003; §51 T03; §54 Interfaces | `contract.rs`: typed matrix across generate/seal/open; real-provider positive/negative tests; mock unavailable/unhealthy/error/staging/panic cases separately labeled | Engineering proof satisfied inside experiment. Existing UI/TQR/portal paths are unchanged, not declared fixed |
| RNG/provider failure prevents new operations | QM-CRYPTO-004; §51 T01/T09 | Real selected-backend random/keygen/encryption failures under empty TEST-RAND source and unavailable provider query; late native panic containment in seal/open | Satisfied for exposed failure behavior. No FIPS self-test callback exists in this configuration; no fictitious self-test guarantee |
| Composition and secret-boundary review | §54 Review; Appendix C3 | Review package prepared, source inspection/test evidence only | **Outstanding external expert review; M2 exit remains PARTIAL** |
| Profile/compatibility documentation and no write migration | §54 Docs/Migration | Proposed ADR/profile, source/lock audit, no production imports/data changes | Satisfied; production enablement requires later gates |

The M2 typed service is tested in isolation as explicitly authorized. Its future
UI/API callers must use this shared boundary at production integration; no
claim is made that all existing production entry points already do so. This is
not an amendment granting production sending. No new M2 requirement for a vault,
mail UI, installer, actual SMTP or full Linux CI has been invented.

## Exact inputs and executed commands

Same provider versions/flags as the retained proof: Sequoia 2.4.1, defaults off,
`crypto-openssl`; OpenSSL 3.5.9, static, `VC-WIN64A no-shared no-tests no-module
no-comp no-asm --libdir=lib`; rPGP 0.21.0, defaults off, `pqc`.
OpenSSL runtime string: `OpenSSL 3.5.9 29 Sep 2026`.
Source/archive refs remain in `experiments/m2/inputs.json`.
Rust 1.99.0 (b940084d7 2026-09-28), Windows x86_64-pc-windows-msvc,
OS 10.0.26200, VS Developer Shell 18.4.3, cl 19.50.35728.0/toolset 14.50.35717.
Rust test profile: unoptimized + debuginfo; native C: upstream /O2 /MT /W3 /wd4090.
Native upstream tests remain unexecuted; no native rebuild or warning suppression.

Two deliberately separate lanes:
1. Main manifest uses the **unmodified registry Sequoia**, testing the contract
   and all nine retained interoperability/vector/header tests.
2. Backend diagnostic manifest uses a source copy from the hash-verified same
   crate archive. The only changes are an empty feature and gated public context
   accessor; no crypto, RNG, parsing or verification implementation is changed.
   `audit-inputs.py` compares 651 files and asserts exactly those changes.
   The two locks have identical transitive versions/sources/checksums except for
   the intentionally local diagnostic Sequoia entry. Native libcrypto is unchanged.

Exact final commands, PowerShell from repository root:

```powershell
./experiments/m2/prepare-probe.ps1
./experiments/m2/run.ps1
./experiments/m2/run.ps1 -Order reverse
./.venv-m1-clean/Scripts/python.exe experiments/m2/audit-inputs.py
$env:OQS_INSTALL_PATH = Join-Path $PWD 'tmp/oqs-install'
./.venv-m1-clean/Scripts/python.exe -m pytest -q
```

The diagnostic lock was initially created by:
`cargo generate-lockfile --manifest-path experiments/m2/backend-probe/Cargo.toml --offline`.
All test invocations subsequently use `--locked --offline --lib`.
`run.ps1` sets the same local Cargo/Rustup/native/libclang paths and verifies
four RFC fixture hashes and native version. It discovers the corpus with
`cargo test --manifest-path <manifest> --locked --offline --lib <filter> -- --list`.
Main filter is empty; diagnostic filter is `backend_probe`.
Normal execution uses `-- --test-threads=1`; reverse executes each discovered
name descending with `--exact --test-threads=1`. Diagnostic execution adds
`--nocapture` for explicit native reasons, not secret data.
The script checks actual successful test names, counts, exit status and zero
ignored tests. The audit independently compares normal/reverse identities.

| Final execution | Exact outcome |
|---|---|
| Main normal, unmodified provider | **12 passed**, 0 failed/ignored/filtered, 3.03s |
| Diagnostic normal | **5 passed**, 0 failed/ignored, 12 deliberately filtered inherited main tests, 0.13s |
| Reverse | Same **17 distinct tests** pass; main invocations filter 11 others, diagnostic invocations filter 16 others |
| Legacy regression | **37 passed, 5 existing warnings**, 2.40s, zero skips |
| Input audit | 651 source files compared; only Cargo.toml and src/lib.rs changed; transitive locks match; native hash unchanged; same 17 identities |

Retained [normal output](evidence/m2/20261005-normal.txt),
[reverse output](evidence/m2/20261005-reverse.txt),
[legacy output](evidence/m2/20261005-legacy.txt).
No seeded-order, Linux, hosted M2 or Python IPC execution is claimed.
The diagnostic path dependency exposes **22 upstream Rust deprecation warnings**;
the registry dependency's normal Cargo lint treatment does not display them.
They are retained, not suppressed. These are separate from 871 MSVC and 231 Perl
native-build diagnostics and M1's 42 liboqs warnings.

## Typed policy matrix and executable evidence

`Profile::CompositeGcm` is the sole accepted profile.
`Failure` distinguishes RejectedProfile(Malformed/Unknown/Weak/Unsupported),
ProviderUnavailable, Backend(Entropy/Operation/Panic/Health), Verification,
ResourceLimit, InvalidRecipient, UntrustedRecipient, ForbiddenRoute and
UnsupportedExtension. No provider error text/secret enters the public error value.

| Input/condition | Required result | Executed evidence |
|---|---|---|
| Exact profile, good keys, verified experimental recipient | Successful encrypted envelope and verified plaintext | `policy_matrix_and_real_provider` |
| Empty/NUL name, unknown name, Level1/2/3, plaintext/classical, unsupported OCB-named profile | Explicit rejected-profile variant in generate/seal/open | Same matrix |
| Unknown/changed recipient; malformed/classical/secret recipient material | UntrustedRecipient / InvalidRecipient; no fallback | Same matrix |
| Portal route, simulator key-source route, unknown critical extension | Explicit rejection in all three operations | Same matrix; these are experimental routes, not production rewiring |
| >1 MiB message, zero or >32 recipients | ResourceLimit | Same matrix; full product/process limits remain later |
| Provider-produced OCB, SHA-256 signature, unknown critical notation | Verification failure; no plaintext | `wire_profile_and_critical_extension_rejection`, with successful GCM/SHA-512 control |
| Wrong recipient/signer, modified/truncated wire | Verification failure | Typed matrix plus retained cross-provider negative corpus |
| Unavailable/unhealthy/entropy status | No backend operation | `mock_failures_never_release_staging_or_fallback`: **mock** status and call counts |
| Error/panic after staging bytes; incomplete verification; oversized output | Structured error, no VerifiedPlaintext, no retry | Same **mock** test; synthetic staging is not native entropy evidence |
| Real selected-backend RNG/provider failure | No generated key/envelope/success | Diagnostic tests below |
| Native provider becomes unavailable after actual healthy random probe | Backend(Panic), no ciphertext or plaintext | `real_late_provider_panic_is_contained`, `real_late_provider_open_releases_nothing` |

`VerifiedPlaintext` has private storage and no Debug/Display/Serialize. The service
constructs it only after the trusted provider returns complete integrity and
composite-signature verification and limits pass. Tentative data stays private;
error or unwind drops it. There is no output callback/stream. Buffer dropping is
not a zeroization guarantee. Providers remain trusted components; a fabricated
success assertion by a malicious provider is outside this contract's guarantee.
Real successful opens still read to EOF and verify via the retained provider APIs.

## Genuine native failure evidence and limitations

The [external review package](m2-external-review.md) gives exact source paths and
the native call chain. Sequoia uses a private OnceLock OpenSSL context and an
HMAC-DRBG/SHA-512 per random request, not merely process-default RAND_bytes.

- **Empty test seed source:** in a fresh child, supported RAND_set_seed_source_type
  installs OpenSSL TEST-RAND with no entropy/nonce. RAND_get0_primary forces source
  creation and fails. Sequoia random, key generation and encryption reject with
  native reasons including `generate error`, `error retrieving nonce` and
  `error instantiating drbg`. This exercises actual RNG initialization failure;
  it does **not** simulate a Windows BCryptGenRandom failure specifically.
- **Provider unavailability:** supported EVP_set_default_properties selects a
  nonexistent provider in that same private context. Real random/keygen return
  errors with `unsupported`. Raw encryption panics at
  `packet/key/v6.rs:282` (mandatory SHA-256 assumption). The typed boundary
  rejects failed preflight; a separate post-health injection proves that an
  actual native panic during send/open is caught as Backend(Panic).
- **Health/self-test:** the default provider has no self-test callback in its
  dispatch. OpenSSL returns 1 when that callback is absent. Executed
  OSSL_PROVIDER_self_test returning 1 therefore is **not** a KAT/FIPS assurance.
  This configuration has no FIPS health state/corrupt-self-test hook to exercise.
  The contract tests rejection of supplied failed-health status using a mock,
  honestly distinguished from the real native failures.
- Initial approaches corrected: the process-default RAND route was ruled out by
  source inspection; initial context accessor used a private module instead of
  its re-export (compile failure); an ambiguous Rust Recipient import was fixed.
  The first executable provider probe exposed the native panic (2 passed/1 failed).
  That finding led to whole-operation containment, not weaker crypto assertions.
  No OpenSSL source/algorithm modification, custom production RNG or provider
  substitution was introduced. Raw failed-attempt logs remain retained.

Successful expected-panic tests can contain Rust panic-hook diagnostics. They are
not hidden failed tests. Only synthetic/public fixture data and native reason
strings appear in these logs. Production subprocess stderr must be controlled;
catch_unwind cannot contain abort/OOM/segfault, and no such claim is made.

## Exit decision and remaining work

**M2 engineering proof complete; M2 exit pending external expert review.**
Keep M2 PARTIAL until the §54 cryptographer/protocol review accepts the composition,
profile, secret boundaries and documented assurance limits or requests changes.
The external package is prepared locally; it has not been sent to anyone.

Independent human review must assess the observed native panic, absent default
provider self-test, deprecated context constructor's allocation-failure fallback,
warning relevance and compiler/side-channel limitations. These are disclosed
questions, not AI sign-off. Linux/IPC/process sandboxing/packaging, full MIME/client
interoperability, historical OQS/ciphertext compatibility, licensing and release
approval retain their later gates. No M3 or production migration is begun.

## Final local review

Inspected 40 intended status/M2 source/document/evidence files. The bounded
credential/private-key/local-account-path content scan had zero hits; no
binary/archive/PDF/key-file extensions were in that candidate set. This is not
a universal secret-detector guarantee. Reference PDF remains excluded/untouched.
All 15 experiment input hashes in the new audit match the final source/scripts/
locks; documentation updates after execution do not change compiled proof code.
`git diff --check` passes; only IMPLEMENTATION_STATUS.md is a tracked modification,
with M2 additions untracked. No staging, M2 commit, push or merge. The package
is reviewable locally; no external approval or communication is implied.
