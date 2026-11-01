# ADR 009 — Optional ciphertext relay, local development qualification

Status: development decision; external backend/identity review and production
enablement pending. User authorized this optional lane alongside Google acceptance
on 2026-10-22. No QKD lane, public deployment or paid provisioning is authorized.

## Decision and boundaries

Keep `services/relay` separate from ordinary Gmail delivery and the legacy portal.
Use the existing M5 frozen, standard PGP/MIME encrypted envelope without changing
cryptography. Only ciphertext, visible routing headers, opaque principal/device
identifiers, digests, expiry, idempotency and lease state reach the relay. The
fixed outer subject is `Encrypted message`; extra outer headers are rejected.
Endpoint private keys, Gmail credentials and recovery secrets never enter this
API. The relay has no decrypt operation. MIME syntax validation is **not** proof
that a malicious uploader encrypted its input: honest endpoint preparation and
recipient cryptographic verification remain required.

The qualified development backend is a local SQLite WAL database, with separate
connections and `BEGIN IMMEDIATE` transactions across processes on one Windows
host. This is not distributed-cloud qualification. A missing/unusable database
fails closed; explicit `--create` refuses overwrite. No memory/legacy fallback.
All creation and per-request connections close explicitly; a Windows outage test
found and corrected the initialization connection leak.

Authentication is dedicated relay mutual TLS, with a dedicated client CA and
exact SHA-256 client-certificate allowlist mapping to an enrolled account/device.
Certificate subject strings, Google tokens and user-supplied principal fields do
not authorize requests. A server operator must provision that binding through an
approved enrollment channel; test fixtures establish it explicitly using real
disposable M3 account IDs and fresh transport credentials. This does not prove a
production enrollment authority. Registry revocation takes effect on restart;
online revocation/rotation must be qualified before any production deployment.

The endpoint bridge checks the selected account lease and recipient address/root
against the prepared envelope, compares exact persisted frozen bytes and rechecks
current account/key/contact policy through the existing M4/M5 vault repository
before upload. Changed/revoked recipient trust cannot be bypassed by presenting
an older envelope. No account transaction spans network I/O.
Operator-supplied principal-to-contact mapping is
an explicit trust input, not discovered from untrusted mail. Responses after
account change/cancellation are suppressed. Side effects may already have
committed: use the same owner/device/idempotency key to discover the result.
Never silently resend with a new key. Decryption and signature/identity checks
remain in the existing `OpenMessage` service, entirely at the recipient.

## Lease and retention contract

One initial lease per object, bound atomically to recipient principal, device and
request key; same lease retries for at most 300 seconds or object expiry. An
unrelated device/key cannot acquire another lease. Authorization checks occur
after acquiring the database transaction lock and again before final lease
publication. Default lifetime 3600 seconds, maximum 86400. An authenticated ACK
deletes the primary row's payload and records a consumed tombstone; repeated ACK
is accepted only within the original authorized lease window. Download after ACK
is denied. Expired objects are denied immediately; a one-second local sweeper
clears expired payloads when storage is available. Store outage delays cleanup,
never authorizes access. A download authorized before expiry can finish later;
bytes already obtained cannot be revoked or erased from endpoint memory.

`secure_delete` is enabled, but a NULL primary payload is not proof of forensic
erasure from WAL, snapshots, OS caches or backups. This lane creates no backups;
an operator's snapshot retention must be separately declared. Tombstones retain
opaque routing IDs, request digest and timing until explicit operator database
retirement. Records and active bytes/objects have global/per-principal limits;
exhaustion fails closed. Automatic tombstone deletion would risk resurrecting an
old idempotent upload and is deliberately absent. No exactly-once human reading
or self-destruct claim. Expired/consumed delivery needs explicit sender creation
of a new object; it is never automatic.

## Evidence and unresolved gates

See [validation](../operations/m7-validation.md) for actual results and hashes.
Real endpoint cryptography, mTLS, durable restart, 128 competing lease requests in
eight processes, same-device retry, ACK, expiry and outage are locally tested.
Ordinary email is unchanged and independent. Tests do not establish independent
expert approval, cloud IAM correctness, remote backup erasure or production PKI.

Existing configuration inspection found only the legacy server-decryption portal
and an installed Firestore SDK. No project/backend credentials were configured,
no ADC/personal credential search was performed, and no cloud connection was
attempted. The Google OAuth project is not by itself a provisioned relay backend.
On 2026-10-23 the user explicitly selected local-only qualification: cloud
deployment is outside this workstream, not an implementation blocker. Any future
cloud qualification needs an explicitly selected existing private backend,
database/endpoint configuration and normal workload authentication; no desktop
service-account key. A cloud adapter must requalify T10 transactions, quotas,
expiry and failure behavior against that backend before its use. No cloud IAM or
deployment manifest is claimed implemented for an unselected provider.

Canonical references: §54 M7; § optional ciphertext relay; I01/I10/I12;
QM-PORTAL-001/002/003; T10. QKD remains excluded: no hardware, simulator-derived
security or custom combiner. ADR 004/006 development exceptions and all earlier
compatibility, provider assurance, licensing and release gates remain intact.
