# M6 Gmail mail: controls and development acceptance

Development only. Production approval and live Google acceptance remain pending.
The application uses real account-scoped services; no presentation accounts, sample
inbox, local-server fallback or existing credential-cache discovery.

## Launch and account setup

From the repository root with the existing environment and built helpers:

```powershell
./.venv-m1-clean/Scripts/python.exe main.py --dev-mailbox --dev-vault "C:\path\to\explicit-development-vault.sqlite" --google-client "C:\path\to\provisioned-desktop-client.json"
```

In **Settings**, **Create vault** or **Unlock**, enter the expected Google address,
**Connect Google**, and complete the browser interaction yourself. Select the account.
Previously identity-only accounts require **Reauthorize selected** with the mail
scope. Public certificates are imported/exported and fingerprints verified in
Settings; verification is separate from importing or validating a signature.
New Yahoo enrollment remains unavailable. Without a client file, existing valid
mail-scoped tokens can be used, but enrollment/refresh needing client configuration
fails explicitly. No real credentials are supplied or searched for.

Submission is disabled by default. A separately authorized live test can add
`--dev-gmail-submit` to the command. This enables **Submit once** to fixed Gmail
STARTTLS/XOAUTH2; it does not grant production approval. This implementation task
sent no external mail and performed no live authorization or cloud configuration.

## Inbox and protected content

- **Refresh headers** / **Older** list bounded INBOX UID windows without fetching
  bodies. Selection does not fetch. **Open selected** uses BODY.PEEK and displays
  plain text; HTML, scripts and remote resources remain blocked.
- Protected mail uses a local signer-certificate lookup hint from outer From, or
  the explicit signer selector. Full M5 verification still precedes any body or
  attachment release. Missing keys require Settings import/selection; successful
  verification does not grant contact trust. Changed/expired/revoked keys require
  resolution and renewed verification, never a bypass. Modern failures cannot
  fall back to conventional plaintext or the legacy reader.
- **Save attachment asâ€¦** exports the selected verified attachment to an explicitly
  chosen NEW local file. Existing files and unsafe paths are rejected, never
  overwritten. Filenames/types are untrusted claims. Export deliberately leaves
  plaintext at that location; nothing opens or executes it automatically.
- **Reply** uses authenticated inner author/references for verified protected mail.
  Conventional mail requires explicit recipient entry/confirmation and remains
  labeled unverified. **Forward** always requires explicit recipients, re-encrypts
  the quote and protected attachments, and does not imply original endorsement.
  Replies do not automatically copy attachments; add them explicitly if intended.
  Quoting over the qualified size limit fails explicitly; no silent truncation.
- **Group opened threads** groups authenticated references from verified identities
  opened on the current page. Outer references never establish a verified group.
  Refresh/Older clears this in-memory grouping. References are signed author claims,
  not proof of another message's existence or consent. This is basic page-local
  threading, not a complete historical conversation index.
- Only **Mark read** / **Mark unread** mutates Seen. Listing, refresh, open and
  verification do not. **Cancel**, account switch and **Lock** invalidate late
  results and clear plaintext. An interrupted flag change may already have reached
  Gmail; refresh to confirm. Close locks the vault.

## Compose, durable outbox and archive

1. **Compose / outbox**, **New**; enter **To**, optional **Cc**, **Subject** and body.
   Bcc is unavailable. **Add attachment** / **Remove attachment** manage bounded
   files. **Include encrypted sender archive** is enabled by default.
2. **Verify recipients** checks every current contact certificate. This is not a
   trust bypass: use Settings to resolve missing, changed, expired or revoked keys.
3. **Save encrypted draft**, then **Refresh outbox**, select its operation and
   **Prepare saved**. **Edit draft** reloads a Draft; save edits before preparation.
   Preparation rechecks all recipients and persists frozen signed/encrypted MIME.
   It never sends. The editor is cleared on success.
4. With explicit Gmail submission opt-in, select Prepared and **Submit once**;
   confirm the action. **Refresh outbox** shows the durable state. **Accepted** means
   server acceptance, not delivery/decryption. **Failed** is rejection/stopped before
   DATA; **Unknown** may already be accepted. No automatic retries.
5. **Explicit retry** revalidates keys and restores Prepared using exactly the
   original bytes; acknowledge possible duplicates for Unknown. **Submit once** is
   a separate action. Maximum three attempts. **Discard / cancel saved** discards a
   draft or cancels Prepared. **Cancel active work / clear plaintext** stops local
   work; it cannot recall mail and can leave Unknown. Refresh to inspect the result.
6. **Open archive** verifies the saved frozen sender copy using its original local
   key handle, independently of transport success. Archive must have been included;
   otherwise opening fails. Restart, unlock the same vault and **Refresh outbox**
   to recover saved operations; interrupted intent becomes Unknown, never a resend.

## Qualified limits and exposed metadata

Current M5 limits: 3 To/Cc recipients plus optional sender archive, 8 KiB UTF-8 body,
4 attachments / 16 KiB aggregate, 64 KiB inner MIME and 256 KiB complete wire message.
Filenames are bounded ASCII; accepted claimed types are text/plain, image/png,
application/pdf and application/octet-stream. These are lower experimental limits,
not the full release-scale target. Up to 16 retained outbox operations per account;
there is no automatic deletion/garbage collection. The vault's 8 MiB account cap
also applies. Prepared/accepted history is not silently pruned.

Inbox: up to 30 headers per 200-UID window; sparse pages may be empty with Older
available. Account + mailbox + UIDVALIDITY + UID identifies cache entries. One
bounded encrypted header page is retained; bodies and opened attachments are not
cached to ordinary files. Conventional MIME is bounded to 64 parts/depth eight;
attachments in conventional mail are not exported by this verified-content flow.
Outer routing addresses, timing, size and the generic encrypted subject remain
visible; inner subject/author/references/attachments are protected by existing M5.
No sensitive content, token or key is written to application logs.

Mail workers use a 30-second operation budget. IMAP DNS/TCP/TLS/greeting has an
8-second shared setup cap; SMTP DNS/TCP is similarly bounded. DNS/Google HTTP run
in cancellable private children, with 50 ms polling. Enrollment allows 210 s;
refresh 30 s clamped to remaining caller budget. Cancellation cannot undo remote
consent, flags or message acceptance; close leftover browser tabs explicitly.
Settings native/vault work now runs on one bounded worker. Cancel/Lock/selection
remain responsive in tested phases; a native call (30 s timeout), SQLite wait
(5 s) or authorized filesystem/commit operation may still drain after cancellation.
Use Inspect outcomes for the original owner. Backup requires secret acknowledgment
before writing. See [Settings validation](m6-settings-validation.md). No hard
real-time or memory-zeroization claim.

## Live acceptance, separately pending

Use the [single Google acceptance checklist](m6-google-acceptance.md) for client,
two accounts, browser/refresh, retrieval, certificates, separately authorized sends,
sanitized evidence and cleanup. Live/human/distribution/release gates remain pending.

Primary references consulted 2026-10-20/21:
[Google IMAP/SMTP endpoints](https://developers.google.com/workspace/gmail/imap/imap-smtp),
[Google XOAUTH2 and mail scope](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol),
[Python imaplib](https://docs.python.org/3.12/library/imaplib.html).
See [validation](m6-validation.md) and [ADR 008](../adrs/008-m6-mail-workflows.md).
