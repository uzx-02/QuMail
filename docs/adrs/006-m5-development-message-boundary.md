# ADR 006: bounded M5 protected-message and compose development

Date: 2026-10-14 (Asia/Calcutta); work began 2026-10-12.
Status: accepted for local development only, by the owner's explicit instruction.
Canonical references: specification §§41–43, 47, 54 M5; T01/T02/T04/T05/T07/T09.

## Authority and preserved boundary

The owner authorizes M5 and opt-in compose integration using the qualified M4
services while live-provider acceptance and independent review are pending.
ADR 004/005 exceptions continue. This changes development ordering, not the
canonical acceptance requirements or approval for production/security release.
M1 remains complete at its baseline scope. M2/M3/M4 are not retroactively marked
unconditionally complete. No independent expert approval is represented.

Local branch `codex/m5-protected-compose` starts at verified M4 checkpoint
`b00693cbaba92037b3dec8c9e35d866650a5018f`. Earlier source, helpers, locks, branches,
evidence, legacy readers/data, PDF and reviewer draft remain unchanged. Default
startup does not import M5. No real credentials or external mail are used.

## Message and provider decision

Use RFC 3156 §§4/6.2 combined signed-and-encrypted PGP/MIME, armored by the provider,
with RFC 9788 `hp="cipher"` directly on the authenticated MIME payload. There is
no intervening `message/rfc822`, JSON ciphertext wrapper or custom packet encoder.
The experimental application marker is **`QM-OPENPGP-PQ-1-EXPERIMENT-M5`**.
The provider still receives the frozen **`M2-EXPERIMENT-RFC9980-AES256-GCM`** policy.
Neither marker approves production `QM-OPENPGP-PQ-1`.

The unchanged M3 certificate model has a v6 certification-only algorithm-30 root,
one active v6 algorithm-30 signing subkey and one active v6 algorithm-35 encryption
subkey. Algorithms remain ML-DSA-65+Ed25519 and ML-KEM-768+X25519; message signatures
are v6/SHA-512, recipient PKESKs v6, content SEIPDv2/AES-256/GCM with 4096-byte
chunks and no compression. Sequoia 2.4.1/OpenSSL 3.5.9 owns keys, composition,
randomness, nonce/chunk rules, signatures, packets and armor. rPGP 0.21.0 remains
an independent test peer, never an automatic fallback.

The M5 helper includes the unchanged M3 provider source. Its package/lock are
separate; dependency versions/features/checksums are unchanged. Additional IPC
operations accept a list of public recipient certificates and emit armored data
or completely verified plaintext. The Python boundary kills timed-out/cancelled
processes and rejects failed, partial or oversized responses. Private material
uses anonymous pipes only; no keys/plaintext in argv, environment or logs.

Actual executable peer tests initially terminated with Windows `0xc00000fd`
(stack overflow), despite passing Rust unit tests. The helper now executes on an
explicit 8 MiB worker stack. This bounds that stack and fixes the measured failure;
it is not a heap cap or cryptographic assurance claim. Nonzero exits/panics never
produce a success result. Native warning/constant-time/context-allocation concerns
remain in the preserved M2 review package. `no-asm` and successful tests are not
constant-time evidence.

## Protected metadata, recipients and persistence

M4 generates Message-ID once when the encrypted draft is saved. The saved draft
also fixes Date, To/Cc, Subject, reply references and archive choice. The complete
authenticated MIME includes From, those fields, the M5 marker, body and attachment
names/types/bytes. Header confidentiality policy keeps bare routing From/To/Cc,
Date and Message-ID outside, replaces Subject with `Encrypted message`, and removes
profile/archive/reply-reference fields from the outer section. Each deliberately
exposed non-structural field has an exact protected `HP-Outer` snapshot. No legacy
display pseudo-headers are generated. This is an explicit experimental HCP choice,
not a claim to use the exact registered `hcp_baseline` transformation.

Every intended recipient passes the existing M3 verified-contact and current
certificate/subkey checks. Public inspection uses the same M3 helper through
cancellable pipes with the operation deadline. Sender archival encryption is an
explicit additional public certificate recipient, not a signing-key reference.
It is not an extra SMTP recipient. Bcc is rejected; no split/privacy envelope is
invented. A missing/changed/expired/revoked recipient blocks the whole operation.

M5 supplies a builder/repository adapter to unchanged M4 PrepareMessage/SubmitOutbox.
Complete serialized MIME commits before SMTP. Retry loads the exact stored bytes
and Message-ID. M4 still owns operation locking, short network claim/result
transactions, conservative Unknown recovery and receipt isolation. Crypto during
preparation runs on a GUI worker within the existing bounded vault transaction;
network I/O never holds that transaction. It can still delay another writer during
preparation; this is a documented development throughput limit.

## Receive and trust decision

OpenMessage accepts an explicit candidate public certificate, not an outer-header
identity assertion. Only complete provider integrity/signature success permits
inner parsing. Then it checks the application profile, certificate address binding,
intended recipient or declared sender archive, MIME/metadata budgets, and replay
persistence. No partial provider stream becomes a message result.

The immutable result separates signature validity, local/enrolled or independently
pinned identity trust, header discrepancies, archive status and replay status.
An unverified/changed/revoked signer does not gain verified-confidential status
from a valid signature. Candidate signer certificates must currently pass M3's
inspection policy; historical expired/revoked signer acceptance needs a separately
reviewed time-aware policy. Existing M3 historical decryption remains unchanged.

Replay key is account scope + signer root + protected Message-ID; digest is SHA-256
of the exact authenticated canonical MIME bytes. A first-seen digest is committed
inside the encrypted vault before content is returned. Exact repeats are duplicates;
a different digest under the same identity is a conflict and is never labeled
verified-confidential. The original digest is retained. No notifications/actions
exist in this development view. History is bounded, survives reopen and is included
in M3's authenticated account backup; whole-backup rollback remains a replay risk.

Legacy classification returns original bytes and an explicit unverified label.
It invokes no legacy reader, mutates no data and cannot be selected after modern
verification failure. Existing legacy formats and compatibility blockers remain.

## Qualification and remaining gates

[M5 validation](../operations/m5-validation.md) records executable evidence,
actual budgets, primary standards/errata and exact source/helper hashes. The
independent exchange is crypto interoperability with shared MIME/armor/policy
wrappers. It is not independent mail-client rendering/interoperability.

The bounded development implementation is reviewable; full M5 remains PARTIAL
until production/independent-client/protocol-review gates are met. Live Google,
independent cryptographic and enrollment/recovery review remain required before
production enablement/security release, without becoming routine development
stops. Linux, OS heap containment, distribution licensing, original 0.14.1 artifact,
authentic legacy ciphertext and production approval remain separately tracked.
No new project license or Qt redistribution determination is made. No M6 inbox,
HTML rendering, push, merge, release, deployment or user-data migration.
