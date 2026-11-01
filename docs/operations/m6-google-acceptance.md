# Desktop handover correction — 2026-11-01

The later launcher failure was reproduced in normal desktop File Explorer: the old
acceptance folder is absent there although tool subprocesses can see it. Earlier
preflight success is tool-context evidence only. No vault was copied/replaced and
no new account was created. A distinct desktop-path shortcut was prepared but not
launched before the owner stopped work for handover. Durable A enrollment remains
unknown, not a verified live pass. No new browser authorization or send occurred.

Next: [the exact desktop dry-run task](../handover/STATUS_AND_ROADMAP.md#ordered-work-items-and-stopping-boundaries),
then the owner performs the existing manual checklist. Check actual normal-desktop
paths and selected vault before deciding Unlock versus intentional new creation;
never recreate an inaccessible old root silently. The record below preserves prior
attempts, not proof the same vault is available in the user's desktop session.

## Preserved live attempt record

# Live Google continuation and manual handoff — 2026-11-01

**Live acceptance remains incomplete. The owner now performs the manual checks.**
Use the concise [manual sequence and result template](google-manual-acceptance.md).
Do not restart project/client setup or create a new vault/root unnecessarily.

Actual work on 2026-10-22/23: the owner configured an External/Testing Google
Desktop client and listed both designated controlled accounts as test users.
The explicitly supplied JSON schema/endpoints were validated without displaying
contents. QuMail launched with Gmail submission explicitly enabled, using a NEW
owner-approved disposable vault outside Git and Windows secure storage. No
personal token caches were discovered or reused. Three bounded non-sensitive
sends between A/B are authorized; mail scope alone is not send authorization.

Real A browser callbacks and token exchange executed. Enrollment failed closed
at identity verification, initially hidden by a generic status. Fixed enum-only
stage reporting then confirmed Google's maintained verifier rejected token time.
The owner synchronized Windows time; a separate public-certificate endpoint
check showed server Date within one second, but a fresh token still triggered
the time check. A bounded, cancellable not-yet-valid-token wait now retries full
signature/audience/time verification for up to 20 seconds; zero clock-skew
allowance remains. Expired tokens and signature failures are never retried as
not-yet-valid tokens. Nonce, issuer, subject, address and consent checks remain.
Browser callback wait remains three minutes; interrupted/late callbacks cannot
install an account. Fixed diagnostics never include token payloads or URLs.

After the correction the owner reported that enrollment appeared to work. This
was **not subsequently verified by the agent** and is not recorded as a passed
live step. B enrollment, both refreshes, retrieval/flags, certificate exchange,
three SMTP submissions, recipient verification, attachment export and sender
archive all remain unexecuted or unverified in this record. No external send was
executed or observed by the agent. On resuming, inspect any existing A account
and refresh/reauthorize it rather than creating a replacement root.

No live tokens, private keys, callback URLs, client JSON or vault data are in the
checkpoint/evidence. The owner was asked to report sanitized UI results only.
Independent usable-security/accessibility and cryptographic review remain
separate gates under existing development exceptions. The local M7 relay is
independent; cloud deployment is explicitly outside this workstream.

## Preserved reusable checklist (originally prepared before live testing)


Use two dedicated, controlled Google test accounts, A and B. The original checklist below was prepared before execution. Current outcomes
are recorded above; local fixtures are not Google evidence. Independent review remains
deferred under ADR 004/006; completing this checklist is not production approval.

1. **Supply configuration.** Provision a Google OAuth **Desktop app** client through
   the normal Google console, configure the consent audience/test users for A/B,
   and permit the requested OpenID/email and `https://mail.google.com/` scopes.
   Supply the local path to the downloaded client JSON, the two expected addresses,
   and a NEW disposable vault path. Do not paste secrets or use personal caches.
   Workspace policy may require administrator permission. App verification and
   distribution permissions remain separate gates. Retain client JSON privately.

   From the repository root, using the installed environment and existing helpers:

   ```powershell
   ./.venv-m1-clean/Scripts/python.exe main.py --dev-mailbox --dev-vault "C:\chosen\test-vault.sqlite" --google-client "C:\chosen\desktop-client.json"
   ```

2. **Enroll and refresh, without sending.** Settings → Create vault; enter A's
   expected address → Connect Google. The account owner completes the external
   browser interaction and mail-scope consent. Repeat for B. Verify the selected
   account and full local root fingerprint after each enrollment. Identity-only
   consent is insufficient; use Reauthorize selected when necessary. Exercise
   Refresh Google for each account, then close/reopen and unlock. Cancel a browser
   flow and try an unexpected account: neither may install another identity.
   Local cancellation cannot revoke consent already granted at Google; close any
   remaining browser tab explicitly. New Yahoo enrollment is unavailable.

3. **Retrieval and isolation.** Select A, Refresh headers, Open selected, Older;
   repeat for B. Compare read/unread state in Gmail before/after refresh/open: it
   must not change. Exercise Mark read and Mark unread separately and confirm the
   intended message only. Switch accounts, Cancel and Lock during retrieval:
   previous plaintext must clear and late results must not repopulate it. Record
   account aliases plus mailbox/UIDVALIDITY/UID, not just table row numbers.

4. **Certificates and trust.** Export my public certificate for A and B; import
   each into the other's local contacts with the correct expected address. Compare
   the FULL root fingerprint through a separate trusted channel, then Verify
   fingerprint. Import/signature validity alone must not grant verified trust.
   Check missing/changed keys block preparation and explain the remedy. Never
   exchange private keys, vault contents or recovery secrets.

5. **Separate permission to send.** Inbox authorization, mail scope and this
   checklist are not permission to transmit messages. Obtain explicit permission
   for the bounded A→B protected message, B→A reply and B→A forward before this
   step. Only then restart with `--dev-gmail-submit`. Compose / outbox → New:
   small non-sensitive body, one small text attachment (aggregate <=16 KiB),
   Include encrypted sender archive. Verify recipients → Save encrypted draft →
   Refresh outbox → select Draft → Prepare saved → select Prepared → Submit once.
   Confirm exactly once. Accepted means SMTP server acceptance, not delivery.
   Failed/Unknown require inspection, not blind retry; Unknown may already have
   reached Gmail. Do not force a real outage merely to create uncertainty.

6. **End-to-end checks.** B retrieves/opens the actual received message: verified
   inner author/body/attachment, with unchanged Seen until explicit Mark read.
   Save attachment as… to a NEW chosen file; never auto-open it. A opens its saved
   archive. B replies using the authenticated author/references; B forwards only
   after explicitly selecting A. Recheck current recipient trust each time. The
   forward must not imply original-signer endorsement. Check keyboard Tab/Shift+Tab,
   focus indication, Space activation, Escape clearing, readable errors and the
   separation of identity, signature and delivery states. Human accessibility
   findings remain distinct from automated Qt checks.

7. **Sanitized evidence and cleanup.** Record exact Git SHA, OS/Python/provider
   versions, client type/scope names, A/B aliases, steps/timing, outbox outcomes,
   UID identities and Seen comparisons. Record actual refresh success separately
   from enrollment. Never retain tokens, callback URLs, client JSON, private keys,
   recovery secrets or message plaintext in logs/screenshots. Close/lock QuMail.
   Explicitly remove only this test's messages in Gmail and deliberately exported
   files when authorized. Retire the disposable vault/its owned Windows credential
   entry through a separately reviewed cleanup operation; deleting a database
   alone does not clean Credential Manager. Never bulk-delete credential caches.
   Revoke this test application's consent through Google if no longer needed.

**Next user input:** the client-JSON path, new vault path, expected A/B addresses,
availability to complete both browser flows, and whether authorization is retrieval
only or includes the three specified test sends. No cloud provisioning or external
mail was performed while preparing this document.

Provider references retained from the current implementation:
[Google IMAP/SMTP](https://developers.google.com/workspace/gmail/imap/imap-smtp),
[XOAUTH2 scope/protocol](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol).
See [controls](m6-gmail-inbox.md) and [current validation](m6-validation.md).
