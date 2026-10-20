> Continuation 2026-10-21: [ADR 008](008-m6-mail-workflows.md) adds account-scoped
> compose/outbox, attachment export, reply/forward and explicit Gmail submission.
> Its tested workflow boundary supersedes the feature exclusions below. This ADR
> remains the historical inbox-only decision at 2c0eed6; no approval is implied.

# ADR 007: Gmail-first development mailbox slice

Date: 2026-10-20. Accepted for bounded local development by the owner's instruction;
not independent review or production approval. Canonical references: §§43/47/54 M6,
T07/T12/T15, I13, QM-MAIL-006, QM-UX-001. ADR 004/006 review exceptions continue.

## Reconciliation

M1's retained successful hosted Windows/Ubuntu run is 37128055379 at
`023c941ec2ef284f6be28b5a9605f1dca9c28787`. Both job conclusions and their three
37-pass test orders were checked locally. This does not reopen M1 or represent a
new hosted execution. M2's engineering proof is committed at
`1fc4e55f09e173cec7634d0b2dc776097b552063`, whose parent is `5880dd4…`.

Actual starting HEAD is `b96abc45d975c208d37c03bed80e87f6b68c04c2`, directly after
known-good M5 `219dc97…`. Its two tracked changes are the 1,616-line presentation
panel and historical demo guide. No later tracked changes existed. Untracked
Start-QuMailDemo.ps1, reference PDF and reviewer draft are preserved and excluded.
The M5 branch is preserved; work uses local `codex/m6-gmail-inbox`.

The presentation shell's shared prepared-copy viewer and synthetic-identity controls
are unsuitable for a provider mailbox. Keep them in the explicit M5 fixture harness
for regression/presentation history, never as inbox data or a live account flow.
The new application path imports no demo/server/sample-account module. Retain the
dark palette, explicit account selection, worker publication checks and plain-text
widget approach; reuse M3 Settings/session/vault and M5 OpenMessage. Do not copy the
shell's presentation badges, stage navigation or shared-copy shortcut into the inbox.
Removing presentation behavior does not grant security approval.

## Decision and boundaries

Use standard-library IMAP over validated TLS to fixed `imap.gmail.com:993`, with
Google XOAUTH2 and explicit Desktop-client OAuth configuration. This provides the
UIDVALIDITY/UID semantics required by the bounded slice. Identity-only OAuth scopes
remain the M3 default. Only the explicit mailbox launch requests the additional
`https://mail.google.com/` scope; lacking/denied scope fails with reauthorization
required. Existing account tokens are resolved/refreshed only through the owned
vault context. No legacy token-cache discovery or service credentials.

All listing/opening uses EXAMINE and UID FETCH BODY.PEEK. Header refresh does not
fetch message bodies. Only explicit Mark read/Mark unread uses writable SELECT and
UID STORE, followed by confirmation of the actual flag. Neither CLOSE nor EXPUNGE
is used. A cancelled/disconnected STORE might already have reached the server;
refresh is required to reconcile, without claiming it did not occur.

Identity is (account context, INBOX, UIDVALIDITY, UID), never a sequence number or
Message-ID. Page cursors include UIDVALIDITY. The existing authenticated vault holds
only a bounded header page per account; replacement invalidates old UID namespaces.
Bodies are fetched on demand and retained in memory only. No new storage framework
or in-place migration. A backup can contain header cache; the UI never treats that
cache as current server evidence or automatically restores server flags.

Protected mail requires explicit selection of a locally imported signer certificate
and the unchanged M5 verification/recipient/replay boundary. Outer From is only a
transport claim. Modern verification failure cannot become conventional/legacy
plaintext. Conventional mail is labeled unverified and displayed using QPlainTextEdit;
HTML, remote resources, embedded messages and attachment execution are unavailable.
No inbox selection/open automatically marks read. Account/message generation and
cancellation checks prevent stale results publishing into another selection.

## Qualification and limits

The TLS fixture exercises actual IMAP wire commands with disposable certificate
trust and synthetic account credentials. A generated M5 protected message is fetched
and verified using the real helper. Mocked OAuth and delayed UI workers prove only
adapter/publication behavior; they are not Google acceptance. Existing native helpers,
crypto policies, durable outbox and transport/session sources are unchanged.

Windows TLS cancellation initially failed with cross-thread shutdown; nonblocking
TLS reads/writes now poll cancellation at 50 ms. Initial DNS/connect/TLS/greeting
still use the library connection phase with an eight-second socket timeout; DNS and
multiple handshake exchanges are not a hard whole-phase wall-clock guarantee.
The UI clears immediately, but a universal sub-second connect cancellation claim is
not made. OAuth requests retain M3's bounded HTTP timeouts and late-result rejection.

Full M6 remains PARTIAL: this is INBOX-only manual refresh/paging/open/flags. No
reply/forward, attachment export, background synchronization, MIME peer qualification,
real SMTP enablement, M7 or M8. Live Google authorization/IMAP acceptance, usability/
accessibility/platform qualification and independent reviews remain explicit gates.
Google restricted-scope app verification and existing provider/project/Qt licensing
conditions remain before distribution. No secrets, generated binaries or sample
inbox fallback are published.
