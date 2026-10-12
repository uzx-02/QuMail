# ADR 005: bounded M4 development and durable outbox proof

Date: 2026-10-11 (Asia/Calcutta). Status: accepted for local development only.
Canonical references: §§43, 46–47, 50–51 T07/T09, 54 M4; QM-MAIL-001/004,
QM-REL-001/003 and invariants I03/I06/I09. The specification is unchanged.

## Current SMTP/TLS qualification amendment — 2026-10-12

The owner explicitly authorizes loopback-only SMTP/TLS qualification, short
storage transactions and bounded development integration while live Google and
independent review remain pending. ADR 004 and the development-ordering exception
below remain unchanged. This is not live-provider or production approval.

The earlier coarse-lock/simulation-only decision below describes b833e8b and is
superseded for the new controlled path by these decisions:

- `LoopbackSMTP` uses Python smtplib/ssl facilities with bounded response parsing,
  absolute deadlines, cancellation-aware socket reads/writes, required STARTTLS,
  certificate and hostname validation, fresh EHLO and TLS-before-resolution/AUTH.
  Only numeric IPv4 loopback is accepted. Fixture trust roots never enter OS trust.
- Frozen sender joins recipients/profile/root/subkey/byte identity in the prepared
  record. Reject invalid SMTP framing rather than rewriting persisted bytes. Reject
  any required recipient refusal before DATA. Retrying never rebuilds the envelope.
- A stable per-operation OS file lock spans the attempt; SQLite claim/result
  transactions are short. Persist a random durable attempt identity. Recovery
  cannot steal an active worker on elapsed time; kernel release after process death
  permits conservative Unknown recovery. Other account/vault writes remain possible.
- Result persistence belongs to the original account even after UI selection changes.
  The small opt-in outbox panel uses coherent M3 snapshots, off-thread work and
  generation checks; stale results cannot update another account's display.
- Fix the creation-connection leak at M3 Vault.create with deterministic closure,
  also close setup failures in Vault.connection, and remove the GC workaround.
  This is an explicit M3 source change with affected regressions rerun. Earlier
  M3 checkpoint/evidence is preserved rather than asserted to match changed bytes.
- Accepted derives from an observed final successful DATA response. Later cleanup
  or optional receipt failures cannot change it. Possible acceptance without a
  final response remains Unknown; explicit duplicate-risk retry is still required.

The fixture envelope is a standard MIME/base64 test container around existing
provider-generated ciphertext. It is not the M5 protected-header mail profile.
Private fixture certificate files exist only in ignored disposable paths. Synthetic
credential resolvers live in fixtures; a vault resolver refuses identity-only
Google scopes. No live credentials/caches or external mail servers are used.

The full [qualification report](../operations/m4-smtp-tls-validation.md) records
real socket/TLS, process, SQLite and Qt observations separately from synthetic
identity/credential data and source inspection. The bounded engineering criteria
pass; M4 remains PARTIAL for the full application milestone because unchanged
legacy compose still has F07 and is not yet wired to this service. Full MIME is
M5, not an invented M4 blocker. Review, live-provider, licensing and release gates
remain separate. No independent approval, push, merge, deployment or release.

## Preserved b833e8b design record (2026-10-11)

Its coarse SQLite lock, simulation-only transport and missing qualification
statements are historical and superseded by the amendment above.

## Explicit development ordering exception

The owner authorizes bounded M4 while M3 live Google acceptance remains pending.
Verified parent checkpoint: `1af13a1ee8a58016bdca2dfa25055eb689ec7fd8` on preserved
`codex/m3-identity-vault`. M3 bounded integration engineering is complete; M3
milestone acceptance remains partial. M4 may use the implemented identity/vault
interfaces with controlled accounts and injected transports. Synthetic authorization
does not establish live-provider support. ADR 004 remains in force; this exception
grants development permission, not unconditional M2/M3 completion. Independent
cryptographic/protocol and enrollment/recovery review remains required before
production cryptographic enablement or a security release. None is claimed here.

Work is isolated on `codex/m4-durable-outbox`. Preserve the M1/M2/M3 branches,
proof inputs and outputs, legacy data/readers, and uncommitted reviewer draft.
No default application entry point, real mail sending or migration is changed.

## Application and storage decision

`experiments/m4` contains Qt-independent typed PrepareMessage/SubmitOutbox
services, immutable PreparedEnvelope/Binding results, account selection leases,
account/key/credential handles, and explicit repository/builder/transport
interfaces. A session switch cancels its lease; no global token or display state
is installed by a result. The M3 vault adapter enforces account/device/subject,
current lifecycle, pinned roots and signing/encryption subkey fingerprints.
Unknown, unverified, changed, expired or revoked capabilities fail closed.

Use a versioned `m4_outbox_v1` subrecord inside the existing authenticated account
aggregate. This is a disposable development database extension, not a migration
of user data or a replacement storage format. Existing OS master-key protection,
AES-GCM account/vault/revision binding and SQLite FULL transactions apply to the
entire aggregate, including drafts, routing metadata and attempts. Operation IDs
are random and authenticated inside that record; IDs are not authorization.
No content keys are exported by the OpenPGP provider or written by M4.

Persist encrypted draft first. Preparation atomically commits exact encrypted
payload bytes, stable per-operation Message-ID, digest, immutable recipients,
profile, root/subkey fingerprints, sender key handle, public certificate snapshots
and Prepared state. Remove the draft only in that same transaction. Key records
already exist durably in the account vault. A preparation failure preserves Draft
and permits no transport invocation. This proof uses the unmodified M3 provider
to generate a one-recipient OpenPGP payload. It is explicitly NOT a complete mail
envelope: M5 owns MIME/header binding and sender archive-encryption policy. The
stored public certificates/signing reference do not promise sender decryption of
recipient-only ciphertext. Multiple recipients at this fixture builder fail
explicitly; no alternative wire format or weaker profile is substituted.

## Side-effect ordering and uncertainty

1. Revalidate account, frozen recipient capabilities and credentials. Atomically
   claim Prepared as Submitting and append an attempt. Commit before transport.
2. Acquire a second BEGIN IMMEDIATE transaction, recheck the same attempt and
   current authorization, invoke the bounded injected transport, and persist its
   typed result. The development transport receives only a credential handle,
   never a token. Identity-only Google scopes are not SMTP permission.
3. Final server acceptance becomes Accepted, which does not assert delivery or
   decryption. Definitive rejection becomes Failed. Loss after possible acceptance,
   unclassified exception or invalid adapter result becomes Unknown. A failed
   result commit returns uncertainty, never success; Submitting remains on disk.
4. Restart recovery changes interrupted Submitting to Unknown without sending.
   Retry requires an explicit decision; Unknown additionally requires duplicate-
   risk acknowledgment. Load the exact committed bytes and identifiers. A changed
   root or rotated/revoked subkey blocks retry; it does not regenerate the payload.
   Reconciliation has a separate observation interface and never resubmits.
5. Optional receipt export is separate. Its failure or process interruption cannot
   overwrite Accepted with Failed.

The second transaction holds SQLite's writer lock across the simulated transport.
Concurrent submission/recovery cannot steal an active transaction. If recovery
wins the gap between intent commit and the second lock, the state/attempt check
blocks the original worker. This is deliberately coarse: other vault writers may
wait/fail busy. It is not a scalable production scheduling solution. Process death
releases the lock; recovery remains conservative. No expiring lease guesses that
a possibly active sender has stopped. SQLite's
[transaction documentation](https://www.sqlite.org/lang_transaction.html) and
[synchronous semantics](https://www.sqlite.org/pragma.html#pragma_synchronous)
were checked on 2026-10-11. Process-kill/SQLite tests do not establish physical
power-loss safety for every filesystem/controller; FULL still depends on the OS.

Limits: 64 KiB draft, 1 MiB envelope, 16 operations/account, three attempts/operation,
M3 aggregate 8 MiB, 5-second SQLite busy wait and a default 30-second operation
deadline. Transports must honor cancellation/deadline; arbitrary injected Python
code is trusted code, not a sandbox. Only deterministic simulation adapters are
supplied. No automatic retry/backoff loop exists; a future automatic transient
retry scheduler needs jitter, deadline and authentication-error qualification.
Explicit retries here are single attempts with a durable cap.

## Acceptance and remaining gates

See [M4 validation](../operations/m4-validation.md) for executable evidence and
acceptance disposition. M4 bounded simulation engineering does not satisfy real
SMTP/TLS/provider acceptance (QM-MAIL-001/T06/T07), production UI integration or
M5 MIME acceptance. F07 remains in unchanged legacy `_SendWorker`; this proof
establishes corrected ordering only in its new isolated services. M4 remains
PARTIAL for milestone acceptance, with its bounded engineering proof completed
when the recorded tests pass.

No license, distribution or cryptographic assurance gate is waived. M2 native
warnings/panic/constant-time limitations and the unavailable original OQS artifact
remain as recorded. M3 backup restore does not migrate/remap M4 operation account
IDs; restored outbox records fail ownership checks and need a future explicit
reconciliation/import design, never automatic resubmission. Archive removal,
database rollback resistance and same-user compromise limits remain unchanged.
No M5, real mail, push, merge, deployment or release is authorized by this ADR.
