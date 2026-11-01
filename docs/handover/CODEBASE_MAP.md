# Codebase map and runtime contracts

Source identity and observed state: [STATUS_AND_ROADMAP](STATUS_AND_ROADMAP.md).
These are inspected source facts, not an ideal target tree. Normative invariants:
[SECURITY_CONTRACTS](SECURITY_CONTRACTS.md). All paths below are repository-relative.

## Entry points and layers

| Path / actual symbol | Responsibility and caller |
|---|---|
| `main.py:main(argv=None)`, `_launch_mailbox(vault,client,gmail_enabled=False)` | Validates opt-in mode combinations; constructs Qt, IdentityService, bounded Google adapter and MailboxWindow. No simulator/legacy components in this path. |
| `ui/mailbox_window.py:MailboxWindow` | Account/header/message selection, worker lifecycle, refresh/open/Seen, clear stale plaintext; owns the mailbox application. |
| `ui/mail_actions.py` | Compose/outbox and verified-message actions through Workflows; explicit confirmations; no presentation accounts. |
| `ui/identity_settings.py:IdentitySettings` | Settings controls, asynchronous result publication and recovery-secret ceremony. Closing Settings locks; disposal drains/discards work. |
| `ui/mail_accessibility.py` | Accessible names/focus/status and fixed actionable error messages. Automated checks are not human usability approval. |
| `core/identity_service.py:IdentityService.configured(path,helper,client=None)` | GUI-side service/configuration, secure-store/provider references and coherent session. Older synchronous methods remain; current Settings uses Operations. |
| `core/account_session.py:DevelopmentSession`, `AccountView`, `Snapshot`, `Ticket` | Immutable complete account view before notification; original owner + generation + cancellation event. Separate from legacy `core/session.py`. |
| `core/settings_operations.py:Operations`, `Request`, `Guard`, `ScopedVault` | Single-worker admission, immutable requests, owned DB connections, commit authorization and encrypted outcome receipts. |
| `mailbox_client/service.py:MailboxService`, `Credentials` | Account-scoped mailbox requests, encrypted header cache, protected/conventional classification and credential refresh. |
| `mailbox_client/workflows.py:Workflows` | Draft/save/prepare/outbox/submit/retry/archive, reply/forward and explicit verified attachment export. |
| `experiments/m3` | Shared identity types, verified OAuth claims, Windows secure store, encrypted account aggregate, native certificate/lifecycle provider. |
| `experiments/m4` | Shared durable operation model/services, account repository adapter, ownership lock and bounded SMTP engine. |
| `experiments/m5` | Shared protected MIME/model/services, bounded native message IPC; separate fixture panel/demo. |
| `services/relay` | Independent optional loopback ciphertext API/store/client; not imported as an ordinary Gmail dependency. |

## Account, worker and Settings flow

`AccountContext(account,device,issuer,subject)` and `KeyHandle` are distinct typed
opaque values in `experiments/m3/types.py`; addresses are not account IDs or key paths.
`DevelopmentSession.install()` installs all fields under an RLock before `changed`.
`begin()/invalidate()/current()` control tickets; mail has separate M4
`AccountAccess.select(context)` and `Lease(context,generation,cancelled)`.

`Operations.start(operation,*args)` captures original absolute vault path/ID,
owner, args, generation and deadline. One future prevents overlapping destructive
Settings operations. `execute(request,session,store,provider,google)` works on its
own Vault, never widgets or the mutable service. Read/outcomes refreshes do not
invalidate unrelated mail workers. GUI polls `take()` and validates ownership
before publishing. `cancel()/close()` invalidate tickets; late results are discarded.

`Guard.reserve()` checks authorization under session mutex immediately before a
durable step, then releases it before disk I/O. `ScopedVault.commit(db)` adds a
bounded encrypted owner receipt in the same transaction. Cancellation after reserve
may finish the original owner's write; `inspect_outcome` means investigate, not
rolled back. Settings **Inspect outcomes** exposes receipts and export-intent hashes
after selecting/unlocking the original account. Detailed ceremony and limits:
[Settings validation](../operations/m6-settings-validation.md),
[recovery instructions](../operations/m3-recovery.md).

## Vault, keys and recovery persistence

`Vault.create(path,store,provider)` refuses existing paths. WindowsCredentialStore
stores one random 32-byte master under an opaque vault ID using CredWriteW/ReadW;
no adjacent-key fallback. Vault contains `vault(id)` and
`accounts(id,revision,blob)`. Record schema is authenticated version 1; AAD includes
`QuMail-M3-record-v1/{vault}/{account}/{revision}`. AES-256-GCM wraps entire aggregates.
`transaction(ctx,active=False)` checks owner/lifecycle, uses BEGIN IMMEDIATE, updates
revision and encrypted blob, commits with FULL synchronous semantics; per-connection
five-second writer wait and bounded records. No general schema migration framework
is implemented. OS-store creation and SQLite cannot be one atomic transaction.

Account aggregates include keys/contact trust/OAuth, lifecycle and history; later
adapters add outbox, mailbox/replay state and Settings receipts/intents. Do not edit
encrypted JSON independently or restore a database without its proper master key.
Whole-database rollback resistance and hostile same-user races are not solved by AEAD.

`enroll(identity,address,user,tokens=None)`, `import_contact(ctx,address,public)`,
`pin_contact(ctx,address,fingerprint,method)` and `recipient(data,address)` enforce
certified binding, explicit pins and current lifecycle. A certification-only v6
composite root certifies separate signing/encryption subkeys. `rotate` retains
encrypted historical snapshots; `revoke` blocks new operations; `replace_root`
requires renewed contact verification. One active enrolled device is a product
constraint, not a server-enforced guarantee against cloned offline backups.

GUI backup uses `prepare_backup` → memory-only `Recovery` → explicit **I saved the
secret separately; write package** → `write_backup`. No file exists before custody
acknowledgment. No automatic durable secret retention. Export intent precedes file
write; final receipt follows. Transfer additionally suspends source only after
successful persistence/final commit. Ordinary backup leaves it active. Restore
authenticates package/authorized identity transactionally, excludes OAuth tokens,
creates new local IDs and defaults archive-only. Explicit activation of unchanged
root requires prior-device retirement acknowledgment; replacement root changes trust.

## Provider and message boundary

`experiments/m3/provider.py:Provider.call(op,**values)` invokes the pinned M3 helper
with version-1 JSON on private pipes, byte arrays encoded as integer lists, 8 MiB
pipe limit, 30-second timeout and suppressed native stderr. This is the **actual**
IPC; the older ADR 003 length-prefixed recommendation is not the current transport.
`experiments/m5/provider.py:Provider.call(op,budget,**values)` adds profile validation,
50 ms cancellation polling, process termination/wait and strict response checking.
No secret argv/environment/temp files; nonzero/partial/invalid response is failure.
Native parsing and cryptographic operations are in the respective `provider/src`.
M5 includes the unchanged M3 provider source and uses a qualified worker stack.

M2 `src/contract.rs` is an isolated typed policy proof, not a globally wired policy
service. Production-wide centralization remains a release/consolidation task. The
application reuses M3 current-recipient checks and M5 allowlisted profile validation.
Exact suite/wire choices: [M5 validation](../operations/m5-validation.md#exact-wire-profile-and-compatibility).

`Compose.draft(lease,draft,budget)` and `prepare(lease,operation,key,budget)` use
`Repository(VaultOutbox)` and M4 PrepareMessage. `MessageBuilder.build` constructs
bounded protected inner MIME, provider sign/encrypt, then RFC 3156 outer MIME.
`OpenMessage.open(lease,key_handle,wire,signer_public,budget)` verifies entire native
output, authenticated author/recipient/profile/metadata, then persists replay
identity/digest before returning frozen `OpenedMessage`. Signature, identity trust,
outer mismatch and replay/conflict are distinct fields. `verified_confidential`
is stricter than “decryption succeeded.” Legacy classification retains original
bytes and never rescues a modern verification failure.

## Outbox and network

M4 `PreparedEnvelope` binds operation, account, message ID, recipient roots/subkeys,
profile, exact serialized bytes and digest. `SubmitOutbox(repository,transport,
allow_external=False)` commits Submitting before SMTP; completion records to the
original owner even if UI selection changed. State enum: Draft, Prepared,
Submitting, Accepted, Unknown, Failed. `recover` reconciles interrupted ownership;
`retry(...acknowledge_duplicate_risk=False)` never prepares different bytes.
`export_receipt` cannot rewrite delivery status. `ownership.py` prevents competing
process workers submitting the same operation. See [M4 TLS contract](../operations/m4-smtp-tls-validation.md).

`mailbox_client/smtp.py:GmailSMTP` selects smtp.gmail.com:587 with validating
STARTTLS and scoped XOAUTH2 after TLS; LoopbackSMTP retains numeric-loopback policy.
`GmailMailbox` uses imap.gmail.com:993, EXAMINE and UID BODY.PEEK; only `set_seen`
uses write selection/UID STORE. `MessageKey` includes account/mailbox/UIDVALIDITY/UID.
Pages are bounded to 30; bodies are fetched on demand, not plaintext-cached.
`connection.py`, `transport/network_worker.py` bound DNS/connect/TLS; bounded Google
processes isolate blocking authorization. Cancellation cannot undo possible SMTP
acceptance or a STORE already sent. Hard OS/native cancellation latency is not promised.

Google `client_configuration(path)` accepts explicit Desktop `installed` JSON only.
`BoundedGoogleAuthorization` wraps maintained external-browser state/S256 PKCE/
loopback handling and full ID-token verification, then subject/address/scopes checks.
Refresh verifies bound identity through fixed TLS userinfo semantics, not an invented
refresh nonce. Only verified owned results enter Vault. Yahoo modern enrollment is
unavailable. Exact live status is [the Google record](../operations/m6-google-acceptance.md).

## Display and optional relay

Conventional messages are unverified plain text; no HTML/remote resources. Local
contact lookup may select a signer certificate but never grants trust. Workflows
`derive(...forward=False,recipients=(),confirmed=False)` uses authenticated inner
author/references for protected reply; forward requires explicit recipients and
denies original-endorsement implications. Conventional reply needs confirmation.
Only verified inner relationships establish page-local threads. `export` checks
owner/signature, validates chosen path and writes exclusively; no silent overwrite,
automatic open or execute. See model constants for currently much smaller limits.

Relay `Store.upload/lease/download/acknowledge` use independent SQLite connections,
WAL and immediate transactions. Server maps exact client-cert digest to
`Peer(principal,device)` using a dedicated CA/allowlist. `Client.upload` rechecks
current vault trust and exact persisted outbox bytes. Recipient locally invokes
M5 OpenMessage before explicit ACK. The server has TLS keys but **no endpoint
decryption keys or plaintext message body**. Single-host multi-process evidence
does not imply cloud/distributed-filesystem support. Normative API/quotas/retention:
[relay operations](../operations/m7-relay.md), [ADR 009](../adrs/009-m7-local-ciphertext-relay.md).

## Legacy and eventual consolidation

Default `ui/main_window.py`, `ui/compose_window.py`, `ui/inbox_view.py` still use
`core/session.py`, `crypto/tqr.py`, `mime/`, `kme/`, `portal/`, old OAuth caches and
local records. F01–F19 are not globally closed: sender-owned recipient secrets,
unauthenticated simulator, server-decrypting portal/memory fallback, SMTP-before-key
persistence and weak local wrapping remain legacy defects. Preserve callable readers,
ciphertext, metadata and keys; no in-place migration or production enablement here.

**Proposed later consolidation:** first freeze public interfaces/contract tests, then
move M3 types/vault/provider, M4 model/services/adapters and M5 model/MIME/provider
into reviewed core/application/storage/protocol packages in separate mechanical
checkpoints. Preserve import shims, wire bytes, storage versions and regression
evidence. Keep M2 diagnostic tests, demo controllers and fixture servers isolated.
Do not perform this move during handover or the immediate launcher task.
