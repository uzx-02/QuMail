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
