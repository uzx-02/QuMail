# Deferred ESP32 entropy research addon

**Proposed; not implemented, not qualified, not a dependency of core mail.** Owner
concept: an ESP32 circuit using Zener-diode avalanche noise, attached to Windows,
detected by QuMail and potentially used in an optional research/security module.
Core Windows/Android delivery takes precedence. No circuit, firmware, driver,
entropy injection, QKD implementation or device testing was performed here.

Canonical boundaries: [specification](../../QuMail-1.0-Research-Audit-Specification.md)
§§21/44/54 M7, QM-QKD-001–004 and QM-CRYPTO-001/004. Existing `kme/virtual_node.py`
is an unauthenticated CSPRNG lab simulator, not this proposed board or real QKD.

## Distinctions that must survive the handover

| Concept | What it means; what the board does not automatically prove |
|---|---|
| Physical noise source | Measurements from a physical process; biased/correlated/failing/malicious samples are possible. Noise is not automatically usable entropy. |
| Entropy source | Noise source plus necessary processing/health-testing components and an assessed entropy claim. NIST's glossary distinguishes this construction from merely outputting bytes. [NIST entropy-source definition](https://csrc.nist.gov/glossary/term/entropy_source) |
| PRNG/DRBG | Deterministic generator seeded/reseeded under a specified construction; expansion does not manufacture new physical entropy. |
| HSM / key-custody device | Protects key generation/use/storage under a distinct threat model. An ESP32 serial noise feed is not an HSM and must never receive endpoint private keys merely to look secure. |
| QKD-methodology simulator | Classical demonstration of selected protocol concepts, separately labeled simulation; no quantum-channel security evidence. |
| Actual QKD | Qualified quantum hardware/channel and authenticated classical control with peer-SAE authorization and operational evidence. Receiving random serial bytes is not QKD. |

## Proposed research stages and acceptance boundaries

Each stage needs a separate bounded owner-authorized task after core delivery.

1. **Identify hardware, not security.** Record board/circuit revision, noise component,
   bias/supply/temperature assumptions, ADC/sampling chain and firmware source/hash.
   Define USB/serial identity/framing. VID/PID/port alone is spoofable. Explicit
   operator selection/provenance is required; detection never enables crypto use.
   Deliver a diagnostic inventory/transport test, not a “trusted randomness” badge.
2. **Bound the transport.** Length/version/sequence/status framing, bounded reads and
   buffers, deadlines, cancellation, reconnect/disconnect and rate limits. Test wrong
   devices, malformed/truncated/replayed frames, stalled reads, reset during frame,
   duplicate ports and concurrent access. Fail an explicitly required lab operation
   rather than silently changing source. Ordinary mail with optional device absent
   continues using its existing validated OS/provider baseline.
3. **Characterize the physical source.** Capture diagnostic samples separately from
   real key-generation operations, with environmental/restart conditions and source
   metadata. Assess dependence, min-entropy and conditioning requirements with
   qualified expertise. Do not commit sensitive operational entropy samples. Tests
   for stuck/repeated/biased output are necessary fault checks, not a proof of
   unpredictability or “pure/unbiased random” output.
4. **Health and conditioning design.** Define justified startup/continuous health
   checks, thresholds and alarm behavior under the assessed source model. NIST
   SP 800-90B covers entropy-source design/validation; its landing page lists two
   potential errata (2025-05-29), which future work must consult. Do not pick arbitrary
   statistical thresholds or assume passing a randomness battery proves entropy.
   [NIST SP 800-90B](https://csrc.nist.gov/pubs/sp/800/90/b/final).
5. **Threat-model the host/device boundary.** Consider spoofed/malicious firmware,
   controllable noise, USB/serial injection/replay, electrical/environmental failure,
   physical substitution and hostile host. Authenticate provenance where feasible;
   no claim that the host cannot be compromised. Keep endpoint secrets off the device.
6. **Provider-supported integration decision.** Investigate only a maintained
   provider-supported entropy-source/reseed interface with documented security
   properties and independent review. Preserve OS/provider baseline randomness and
   selected suite. Do not improvise XOR mixing, KDF, nonce rules, QKD/PQC combiner or
   replacement protocol. Current Sequoia private-context behavior matters; changing
   process-default RNG settings may not reach it. No hardware input in production
   until exact backend failure/health/source behavior is qualified.
7. **Claims and optional lab behavior.** UI distinguishes detected/selected/healthy
   under tested criteria/rejected/disconnected, never “quantum secure.” Explicitly
   required lab mode fails on unavailable/failed source; optional mode may use the
   unchanged baseline only as its documented policy, not silent fallback from a
   claimed hardware guarantee. Retain exact firmware/build/source/measurement and
   fault evidence before any security claim. A separate QKD-methodology simulator
   cannot change these claims or feed production E2EE keys.

No hardware qualification is a current M1–M6 blocker. Either optional M7 lane may
remain excluded. Before shipping hardware support, independently review electrical
safety, entropy/conditioning and operational failure behavior; functional detection
or a model's review is not approval.

## Android is a separate extension

Windows serial detection does not prove Android USB support. Future Android USB-host
permission/lifecycle, transport, supported-device and disconnect tests need their own
qualification. Android Keystore is a custody API with device/algorithm-dependent
security properties; it is neither this entropy board nor evidence of hardware-backed
PQ operations. [Android Keystore documentation](https://developer.android.com/privacy-and-security/keystore).
Keep this work behind the [Android/core roadmap](STATUS_AND_ROADMAP.md), not inside
the initial port. References were consulted on 2026-11-01; recheck their revisions
before implementing or making a cryptographic claim.
