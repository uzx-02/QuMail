# ADR 008 — Account-scoped M6 compose, attachments and Gmail submission

2026-10-21, Asia/Calcutta. Bounded development decision under ADR 004/006; not
independent approval. Continues ADR 007 from verified `2c0eed635bb66740f8365ee89b81e04470a7f515`.
Canonical scope: §43 protected references/forwarding, §54 M6, QM-MAIL-005/006/007,
QM-PRIV-002/003, QM-PERF-001/002, QM-UX-001/002, T07/T12/T15.

## Decision

`mailbox_client.workflows.Workflows` is the account-scoped application boundary.
It reuses M3 vault/session ownership, M5 Compose/OpenMessage and M4 SubmitOutbox;
there is no presentation controller, shared demo ciphertext or fixture enrollment.
`ui.mail_actions` runs these operations on the mailbox worker pool. Dispatch captures
account lease, session generation and cancellation epoch. Source-dependent display
also captures the inbox epoch. Switching/locking/cancelling clears visible plaintext
and invalidates old completions. Durable network outcomes are still committed to the
original account, including after UI cancellation; UI clearing cannot recall mail.

Encrypted drafts can be edited only while Draft. Preparation rechecks every current
recipient certificate and freezes the complete existing M5 MIME bytes. Save edits
before Prepare saved. Explicit cancellation discards Draft or moves Prepared to
Failed without transmitting. Active submission cancellation uses M4's conservative
Unknown semantics after DATA. Retry requires explicit duplicate-risk acknowledgment
for Unknown and rechecks bindings without regenerating bytes. No automatic retries.
Interrupted Submitting intent recovers to Unknown using unchanged operation ownership.
Offline inspection/recovery/retry now permits a None transport; submit rejects it.

The M4 SMTP protocol engine is shared by two concrete adapters. LoopbackSMTP still
requires numeric IPv4 loopback and retains all fixture constraints. GmailSMTP fixes
`smtp.gmail.com:587`, system CA validation, hostname verification and TLS >=1.2,
mandatory STARTTLS, fresh EHLO and XOAUTH2 only. Credentials are resolved after TLS
from the exact account's active vault context, with explicit full mail scope and
M3 identity-checked refresh. No identity-only scopes, passwords, alternate endpoints
or fallback. An OAuth error challenge receives an empty response, then fails.
External transport requires an explicit SubmitOutbox opt-in; the application creates
GmailSMTP only with `--dev-gmail-submit`, disabled by default. Protocol fixtures
redirect sockets to loopback and install a disposable trusted CA; they keep Gmail
hostname checks active. They do not prove Google's live behavior.

Protected attachments remain authenticated M5 content and qualified limits are
unchanged. Compose imports at most 16 KiB, validates aggregate size/name/type, and
never executes content. Export requires a successfully verified opened message and
an explicit new absolute local file. Incoming filenames are never joined into paths;
traversal, ADS/device/reserved/reparse paths and existing destinations are rejected.
Exclusive creation prevents silent overwrite; failed/cancelled writes remove their
partial output. Export is deliberate plaintext disclosure to the selected location,
not an ordinary cache. File types remain claims; no automatic viewer or execution.
These checks do not protect against an already compromised OS or privileged local
filesystem races, and Python does not guarantee memory zeroization.

Reply takes the authenticated inner author, Message-ID and references only from a
verified-identity protected message. Forward requires explicit new recipients,
includes verified attachments, and states that the original author did not endorse
forwarding. The new sender signs a new M5 object; original signatures are not copied
as endorsement. Conventional reply/forward requires explicit recipient confirmation,
retains an unverified-identity label and discards outer reply references. Every new
preparation checks recipient trust/current keys; failures never downgrade to plaintext.
Bcc remains unavailable. Reference grouping is bounded to opened verified identities
on the current header page. Signed references are author claims, not proof that the
referenced message exists or was approved by its purported author.

Outer From may select an existing local signer certificate as a lookup hint. M5
still verifies the full signature, certificate address binding and authenticated
inner author. No certificate discovery or automatic trust promotion. Unknown/hint
mismatch needs explicit local certificate selection; failures release no plaintext.

## Evidence and limits

See the current section of m6-validation.md and evidence/m6-workflows/input-hashes.json.
Real provider tests, real local TLS tests, synthetic OAuth/crash state and delayed
UI adapter tests are distinguished. The unchanged M5 MIME/provider profile is still
experimental; independent MIME-peer qualification and expert review remain gates.

Full M6 remains PARTIAL. Windows-local engineering is available; live Google
OAuth/IMAP/SMTP acceptance, usable-security/accessibility walkthrough and supported
platform qualification remain outstanding. Existing small M5 limits are not the
specification's larger release target. DNS/connect, OAuth HTTP and SQLite timing
limits still prevent a universal sub-second cancellation claim. Native assurance,
historical compatibility, licensing, restricted-scope distribution approval and
security release gates are unchanged. No M7/M8, migration, external send or release.


## Windows connection/usability amendment — 2026-10-21

From `6f4d5fcb62ae0fbae7be68739e0242a4468d750d`, isolate OS DNS and Google OAuth
waits in hidden bounded private subprocesses. Run the unchanged Google verifier;
no identity/token semantic change. Resolve only fixed Gmail endpoints, then use
cancellable nonblocking TCP/verified TLS. IMAP setup has a shared 8 s budget;
authorization 210 s and refresh 30 s, clamped to its caller. Kill/reap and close
pipes on cancellation; remote consent/refresh side effects cannot be undone.
No secrets in argv/logs/files, alternative provider, password or TLS bypass.

Add names/focus order, busy/state controls and actionable errors without redesign.
Escape clears/cancels compose. Settings hide retains timer/executor; final disposal
cancels/shuts them down. Retain Unknown after possible side effects, no recall claim.

Final 65 M6/13 focused and 54 M3 checks pass; see current validation. This is not
hard real-time or human accessibility evidence. **Engineering remains partial:**
synchronous Settings native/vault commits delay UI. Stage preparation/commit with
account-generation and recovery-secret delivery guarantees; moving the mutable
service wholesale to a thread is unsafe. Live Google/deferred review are separate
from this locally actionable work. No production/release approval.


## Settings responsiveness and recovery custody amendment — 2026-10-21

Continue from `f39bc5429658ec3009b9ce10c3f1cd39c21db3ef`. Replace synchronous
Settings dispatch with immutable owner/vault/generation requests to one worker,
one admission slot, no queued destructive work. Keep service/session publication
and every widget operation on GUI. Use worker-owned vault objects/connections and
the unchanged native/provider implementation. Read-only refresh does not advance
the generation or discard concurrent mail results; account selection uses cached
views, refreshed asynchronously. Stale results cannot reinstall another owner.

`Vault.commit` is a narrow default-preserving seam. The Settings subclass adds
an encrypted owner receipt and obtains a short synchronized authorization reservation
before COMMIT. Disk I/O occurs outside the session mutex. Cancellation before that
reservation rejects; after it, the authorized original-account effect may finish.
Do not promise rollback. Inspect outcomes after unlocking/selecting the owner.
Creation/enrollment may require Unlock to discover durable account state. Recent
receipts are bounded to 16; export intents are separately bounded to 16 and never
silently pruned. Receipt metadata is not a release audit ledger.

Change the recovery ceremony explicitly: prepare in memory, disclose secret to the
current owner, require re-entry/affirmation of offline custody, then admit package
persistence. No package exists before acknowledgment. Cancellation/lock/close can
therefore clear the unacknowledged stage safely. After acknowledgment only ciphertext
is needed by the worker; the user already holds the secret even if display, COMMIT
or completion delivery fails. This is an operator assertion, not proof of physical
custody. No durable secret retention, clipboard copy, temporary plaintext or escrow.
Python/Qt memory zeroization remains unproven. Recovery format, archive-only restore,
historical keys and independent replacement-root verification remain unchanged.

Backup/public export intent precedes file persistence; completion and transfer
suspension follow it. Filesystem/SQLite are not atomic. Failed persistence or
cancelled/failed final commit leaves source active, potentially with a package and
intent receipt. An authorized final commit may complete despite late cancellation.
Inspect owner state/digest before retrying; never discard user data automatically.

Native calls keep their 30 s timeout; SQLite busy waits 5 s. GUI cancellation is
responsive in controlled delayed phases, but worker draining/process exit can wait
for an in-flight native/file/commit operation. No universal subsecond OS promise.
The [Settings validation](../operations/m6-settings-validation.md) records real
Windows vault/crypto, controlled delays and synthetic OAuth separately. Existing
ADR 004/006 review deferrals remain; no independent approval or production release.
