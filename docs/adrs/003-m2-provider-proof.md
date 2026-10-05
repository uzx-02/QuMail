# ADR 003: bounded OpenPGP provider proof and candidate profile

Updated: 2026-10-05. Status: **proposed; M2 PARTIAL, not production approval**.
**M2 engineering proof complete; M2 exit pending external expert review.**
Canonical references: specification §§35, 41–42, 51 T01/T03, 54 M2/M5/M6,
62 and Appendix C3. Supersedes no M1 decisions or legacy data formats.

## Verified facts and sources

RFC 9980 is published, not a draft. Its preferred composites have algorithm IDs
35 (ML-KEM-768+X25519) and 30 (ML-DSA-65+Ed25519). RFC 9580 provides the packet
and authenticated-content framework. The dated standards/errata, exact releases,
source hashes, licenses and advisory triage are in the
[evaluation](../operations/m2-provider-evaluation.md). Reported erratum 9023 is
not locally implemented as a replacement combiner.

The selected experimental pair is Sequoia OpenPGP **2.4.1**, defaults disabled,
`crypto-openssl`, using source-built **OpenSSL 3.5.9**, and independent rPGP
**0.21.0**, defaults disabled, `pqc`, using RustCrypto. Source refs, archive hashes,
native flags and transitives are locked in `experiments/m2/inputs.json` and
`Cargo.lock`. rPGP is an interoperability peer, not an approved fallback.

## Measured behavior

The [validation record](../operations/m2-validation.md) separates executed
Windows results from inspection and recommendations. Both directions exchange
signed/encrypted messages with separate sender/recipient keys and only recipient
public bytes at the sender API. Both providers generate usable certificates.
Two-recipient envelopes work with either receiver. Detached signatures made by
either provider fail in both verifiers when either component is individually
changed. Wrong recipient/signer, altered/truncated ciphertext, malformed inputs,
unsupported profiles and selected size limits fail without a returned plaintext.

The published RFC signature vector verifies in both providers; the published
encrypted-message vector is separately exercised in rPGP. These are distinct
from fresh independent exchanges, and do not constitute a full NIST primitive
KAT campaign. Neither independent mail-client rendering nor Linux execution is
claimed.

## Recommendation and bounded profile

Recommend Sequoia 2.4.1/OpenSSL 3.5.9 for the next **M2 qualification step**.
The candidate is not approved for production integration. Preserve the exact
experimental profile `M2-EXPERIMENT-RFC9980-AES256-GCM`:

- v6 certificate primary/signing key, algorithm 30; one v6 encryption subkey,
  algorithm 35; recipient certificates declare SEIPDv2 support.
- v6 recipient PKESK, SEIPDv2, AES-256/GCM, 4096-byte chunks; no compression.
  Providers own content keys, salt/nonces, KEM combination and packet encoding.
- One required v6 composite message signature, SHA-512 for newly generated proof
  messages. Published vectors retain their original hash algorithms.
- RFC 3156 combined sign/encrypt PGP/MIME, ASCII-armored OpenPGP payload;
  RFC 9788 `hp="cipher"` and `HP-Outer` snapshots inside signed/encrypted content.
  Protected Subject, From, To, Date, Message-ID and experimental profile marker;
  generic outer Subject. This proves a bounded header fixture, not a full mail UI.
- Strict experimental limits: 1 MiB input/output and 32 recipients. These are
  conservative proof limits, not qualification of §42's proposed product limits.

GCM compatibility is demonstrated; there is no need to relax the specified suite
or invent an alternative combiner. Freeze this **test fixture** for review. Do
not promote it to the production `QM-OPENPGP-PQ-1` registry yet.

## Python integration recommendation

Use a small pinned Rust helper process around Sequoia, called by a Python
`OpenPgpProvider` adapter through private stdin/stdout pipes with bounded,
length-prefixed binary frames and a versioned request schema. Do not parse human
CLI output. Keys/plaintext never enter argv, environment variables, debug logs
or ordinary temporary files. Sender requests contain recipient public
certificates only; signer/recipient secrets ultimately come from M3 key handles.
The proof currently uses ephemeral in-process keys, not those production handles.

One `CryptoPolicy` checks the exact allowlisted profile, recipient capabilities,
operation, provider health and limits before provider work. Unknown profile,
unsupported certificate/critical extension, unavailable provider, failed health
check and entropy failure cannot select another provider/profile or portal.
Define stable local errors `UnsupportedProfile`, `InvalidRecipient`,
`ProviderUnavailable`, `ProviderUnhealthy`, `ResourceLimit`, `Cancelled` and
`InvalidMessage`; collapse integrity/key/signature failures to `InvalidMessage`
at the remote-facing boundary, without promising timing indistinguishability.

The helper buffers private output until EOF/final AEAD validation, the required
composite signature and intended profile checks have succeeded. Only then emit
one complete success frame with signer fingerprint and authenticated bytes.
Cryptographic verification is distinct from trusted account identity. Python
must reject partial/multiple/oversized frames, nonzero exit, timeout, cancellation
and unexpected EOF, discard buffered output and never retry with weaker policy.
Native panic/abort becomes provider failure, not success with partial stdout.
Use explicit time/output/key-size/recipient/depth budgets and OS process memory
limits; Windows Job Object and Linux process-limit behavior require tests.
No promise of complete zeroization or constant-time IPC/error timing is made.

The isolated Rust `contract.rs` now implements and tests this policy/provider
boundary with explicit profile/rejection/failure types and private
`VerifiedPlaintext`. The lower-level interop adapters retain their provider API
errors inside that boundary. Whole-operation unwind containment covers native
parsing/fingerprinting panics as well as provider calls. There is no fallback.
The synthetic trust input does not constitute M3 identity verification.
Python IPC, OS process limits and the production helper remain a recommendation,
**not implemented or tested integration**. Unwind catching does not contain
abort/OOM/segfault; production isolation and stderr behavior remain later gates.

## Completed engineering proof and pending review

1. Typed `CryptoPolicy`/`OpenPgpProvider` matrix passes in the isolated experiment:
   unknown/weak/malformed/unsupported profiles, routes, trust inputs, limits,
   provider status/errors, incomplete verification and actual wire-profile
   deviations reject. Production TQR/portal entry points are unchanged under
   the user's boundary; their defects are not declared fixed.
2. Real selected-backend failure evidence now exists. A separately locked
   diagnostic Sequoia copy adds only a context accessor and feature (651-file
   audit); native library/transitives are unchanged. Supported OpenSSL controls
   in fresh child processes cause random-source initialization failure and
   provider unavailability on the actual private context. Random/keygen/seal
   fail; post-health provider loss causes native panics contained by typed
   seal/open with no output. These are distinct from mock propagation tests.
   This build's default provider has no self-test callback: its self_test return
   of 1 is not a FIPS/KAT guarantee. OS entropy failure specifically and allocation
   failure remain untested assurance questions; no custom production RNG exists.
3. **Pending:** the §54 external cryptographer/protocol review. The
   [review package](../operations/m2-external-review.md) covers composition,
   verification/secret boundaries, actual native panic, context-allocation
   fallback, 871 MSVC/231 Perl diagnostics, 22 diagnostic-lane Rust warnings and
   constant-time limitations. This task's inspection/tests are not sign-off.

Both orders execute the same 17 distinct tests: 12 unmodified-provider contract/
interop tests plus five diagnostic tests; legacy suite remains 37 passed/five
warnings. Exact working-tree hashes and outputs are in validation. Freeze the
candidate fixture for external review; do not approve a production registry entry.
Engineering requirements at this bounded M2 scope pass. External review prevents
M2 COMPLETE and may require further M2 corrections; it is not silently deferred.

## Later gates, preservation and rollback

M3 owns recipient identity enrollment/vault handles; M4 durable preparation and
sending; M5 production MIME integration, comprehensive malformed protected
headers, intended-recipient checks and legacy read/new-write isolation; M6 safe
rendering, outer mismatch warnings and reply/forward behavior. M8 owns broad
platform/package/adversarial qualification. Linux and fresh Windows helper builds
are still required before claiming those supported distributions. A common MIME
test wrapper is not independent MUA interoperability.

LGPL/OpenSSL/transitive obligations, project license and Qt redistribution remain
owner/distribution gates. No license is invented. liboqs 0.14.1 reproduction,
authentic historical ciphertext, independent legacy interoperability and release
approval remain ADR 002 gates. The 42 M1 warnings are assessed in the evaluation;
their exclusion from the new dependency graph is not constant-time assurance.

No production imports, TQR changes, user-key migration, ciphertext rewriting or
M1 evidence edits. Rollback consists of setting aside the isolated experiment and
proposed documents; retain M1 branches/data/evidence. No M2 commit, push, merge,
installer, release or deployment is authorized by this decision.
