# Google manual acceptance — resume the provisioned test, 2026-11-01

The owner now performs live testing. This is a checklist, not a success record.
Use only the two already designated controlled Google accounts (A and B), the
existing disposable acceptance vault and the supplied Desktop-client JSON. Keep
Google Auth Platform in **Testing** with both accounts listed as test users.
Do not create another vault or root if A already appears after enrollment.

## Launch

Close earlier QuMail instances normally. From the repository root, first run the
machine-specific launcher in check-only mode:

```powershell
powershell -NoProfile -File .\tmp\m7\Start-GoogleAcceptance.ps1 -CheckOnly
```

Expect `Desktop client configuration: valid`, `Existing vault found`, and
`Preflight passed`. Then launch with the same command without `-CheckOnly`:

```powershell
powershell -NoProfile -File .\tmp\m7\Start-GoogleAcceptance.ps1
```

The ignored private wrapper contains the already supplied client/vault path
references, not credentials. It calls the versioned
`tools/start_google_acceptance.ps1`. This validates the Desktop client before
launching, uses the installed environment/helpers, and keeps errors visible.
The earlier `C:\chosen` example was a placeholder and must not be run literally.
No placeholder path is required by this sequence.

If preflight says the existing vault is missing or inaccessible, **stop and report
that output**; do not create a replacement or delete Credential Manager entries.
The generic launcher accepts explicit `-GoogleClient` and `-Vault` paths for an
intentional configuration change. `-AllowNewVault` must be supplied explicitly
for a deliberately NEW disposable vault; it only permits the app to start with
a new path. Creation still requires Settings → Create vault. It never restores
missing keys/accounts and is not the remedy for an inaccessible old vault.

## Click sequence and expected results

1. **Accounts.** Settings → **Unlock**. If A already appears in **Settings account**,
   select it and use **Refresh Google**. Otherwise enter A's expected address →
   **Connect Google**. Complete browser consent within three minutes, then wait
   for account/root details in Settings. The browser return page alone is not a
   pass. If refresh is rejected, use **Reauthorize selected**; do not create a new
   identity/root. Repeat for B. Confirm each selected address and root fingerprint.
   A fresh token may need up to 20 seconds to become valid; full verification is
   rerun with zero clock-skew allowance. Continued token-time rejection requires
   correct Windows date/time. Do not share callback URLs, tokens or client JSON.

2. **Public certificates and trust.** Select A → **Export my public certificate**
   to a NEW `A-public.asc` outside Git; record A's full root fingerprint directly
   from that account's Settings. Repeat for B. While A is selected, **Import public
   certificate**, enter B's exact address and select `B-public.asc`. Select its
   contact row → **Verify fingerprint**: compare the complete fingerprint against
   B's original Settings display, not just the imported copy; record the actual
   channel used. Repeat B importing/verifying A. For this single-operator test,
   a direct local comparison exercises the control but does not establish remote
   out-of-band identity assurance. Do not claim an independent human review.

3. **Return to the mailbox.** Minimize Settings or switch to the main QuMail window.
   **Closing Settings locks the vault**, so do not close it while testing mailbox
   actions. Select A in the main account selector → **Refresh headers**. Repeat
   with B. Record success/errors without copying unrelated message subjects or
   bodies. Fetching headers must not change read/unread state.

4. **One A → B protected message.** Prepare a small local `acceptance-note.txt`
   containing `Controlled QuMail acceptance attachment.` Select A → **Compose /
   outbox** → **New**. To: B only; subject `QuMail controlled acceptance`; body
   `A to B: protected acceptance test.` Keep **Include encrypted sender archive**
   checked, add the file with **Add attachment**, then **Verify recipients** →
   **Save encrypted draft** → **Refresh outbox**. Select its Draft row →
   **Prepare saved** → select the Prepared row → **Submit once** and confirm
   exactly once. Record **Accepted**, **Failed** or **Unknown**. Accepted is SMTP
   acceptance, not delivery. If Failed/Unknown, stop this send and report the
   status; do not use **Explicit retry** without investigating duplicate risk.
   No Bcc or extra recipients. Qualified attachment aggregate is <=16 KiB.

5. **Recipient and archive.** Select B → **Refresh headers**; identify the new
   message by A/time (outer subject is `Encrypted message`). Record its read state,
   then **Open selected**. Confirm authenticated inner subject/body, valid
   signature, verified identity and the expected attachment. Opening must leave
   its prior read state unchanged. **Save attachment as…** to a NEW chosen file;
   compare its bytes/content with the original. No automatic execution/opening.
   Select A → **Compose / outbox**, select the sent row → **Open archive**; confirm
   the same body and attachment.

6. **Two B → A sends only.** Open the verified original as B → **Reply**. Confirm
   A is the recipient and add a small reply; verify recipients, save, prepare and
   submit once as above. Reopen the original → **Forward**, explicitly choose A
   when requested, verify the recipient and the intended attachment/quoted body,
   then save/prepare/submit once. Forwarding must not imply A endorsed B's new
   message. Select A, refresh and open both actual arrivals; confirm their
   signatures, identity, authenticated references and expected content. Stop if
   either submission is Unknown; no automatic retries or plaintext fallback.

7. **Read state and isolation.** On these test messages only, **Mark read**, refresh
   and confirm Read; **Mark unread**, refresh and confirm Unread. Repeat **Open
   selected**, then refresh: it must remain Unread. Start a refresh/open and use
   **Cancel**; switch A/B during work; use **Lock** during work. Old plaintext,
   attachments and worker results must not reappear under the other account or
   after lock. Unlock and select again; never recreate the vault. Close/reopen
   once and confirm the durable outbox/archive are still correctly account-owned.
   Do not interrupt a real SMTP send just to manufacture an Unknown outcome.

## Report and cleanup

Send only this compact result, with exact UI error text if any:

```text
Checkpoint:
A enrollment / refresh:
B enrollment / refresh:
Mutual certificate comparison / trust:
A→B: outbox state / received+verified / attachment / sender archive:
B→A reply: outbox state / received+verified:
B→A forward: outbox state / received+verified:
PEEK and explicit read/unread:
Cancel / switch / lock / restart isolation:
First failing step and exact sanitized UI status:
```

No tokens, recovery secrets, callback URLs, client JSON, private keys or unrelated
inbox contents. Screenshots must be cropped/redacted if used. At the end, lock
and close QuMail. Retain the disposable vault for investigation; do not manually
delete its Windows Credential Manager entry. Remove only explicitly identified
test messages/files when intended by the owner. No bulk mailbox or cache cleanup.
M7 relay is separately locally qualified; cloud deployment is outside this
workstream. Neither this test nor successful mail delivery grants production or
independent-review approval.
