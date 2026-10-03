# ADR 001: M1 baseline and truthful prototype boundaries

Date: 2026-10-03. Status: accepted for M1 development; not release approval.

## Context

Specification §§13–18, 35, 54 and Appendix B describe the same audited commit as
the checkout. The legacy protocol remains unsafe (F01–F19). Installation cannot
resolve the declared OQS binding; tests hide dependency failures as skips, and the
KME tests share limiter/registry/key state. Windows adds two POSIX-only assertions.

## Decision and interface

Retain existing module boundaries and callable crypto/MIME behavior. Create a
hash-locked portable development/test lane with native ML-KEM tests explicitly
marked. The default full suite must attempt those tests and fail if the native
provider is absent. An explicitly selected portable run is not full validation.
No production provider is approved by a passing legacy round trip.

Tests use temporary working directories before collection, per-test simulator and
portal stores, fixed limiter clocks and no real network. Dependency import errors
are errors, never generic skips. Required validation rejects skips/xfails.
The Qt application fixture lasts for the entire test session: reversed/shuffled
runs exposed deletion of the shared Session QObject when a module-scoped
QApplication was destroyed. This is a test-lifetime correction, not a production
session redesign. Failed and passing run evidence is retained.

Ordinary desktop startup does not start the KME; `--dev-simulator` explicitly
starts the loopback development service. Status labels describe HTTP simulator
liveness, not QKD or identity assurance. Legacy cryptographic modes remain
characterization-only prototype functionality. M2 will gate production writes.

Public docs and visible labels describe actual behavior. Numeric fields remain
legacy wire identifiers, not an ordered security scale. Unsigned exports are
local records, not certificates of identity or delivery.

## Trust, storage and migration

No message/key migration, deletion, new packet construction or private-key
redistribution. Existing paths/data remain intact. Test isolation never reads a
user's registry/token/key directory. Runtime native auto-install is forbidden;
missing or unvalidated native inputs produce an explicit unavailable error.

## Validation and rollback

Run existing and new tests in normal/reversed/seeded order; characterize SMTP
before persistence, cloud memory fallback, OTP mutation and metadata dispatch.
Verify opt-in startup, UI claims and native unavailability. Review changes against
QM-QKD-001, QM-TEST-001, QM-DOC-001/002, F03/F16/F17/F19.
Rollback source/dependency changes using Git with a separate environment, retaining
all existing keys/messages. Never interpret rollback as production approval.

## Limitations

Portable test success does not demonstrate native crypto, Gmail/Yahoo E2E,
Windows ACL protection, real Firestore, ETSI conformance or release readiness.
M2 follows only once the documented M1 exit criteria are met.
The initially missing hosted evidence is now satisfied at commit
`023c941ec2ef284f6be28b5a9605f1dca9c28787`: run 37128055379 passed Windows and
Ubuntu, all three orders, with 37 passed/five warnings/zero skips per invocation.
M1 baseline completion does not close original-artifact compatibility, licensing,
independent interoperability or production-provider/release gates. See the exact
acceptance assessment and historical failures in the M1 validation report.
