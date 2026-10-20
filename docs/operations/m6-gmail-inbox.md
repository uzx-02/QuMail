# Gmail-first M6 inbox: setup and development contract

Development only; production approval remains pending. This application path has
no presentation accounts, sample inbox, local mail-server fallback or sending.
M5's historical fixture harness remains separately runnable for regression evidence.

## Launch and account setup

From the repository root, using the existing environment/helpers:

```powershell
./.venv-m1-clean/Scripts/python.exe main.py --dev-mailbox --dev-vault "C:\path\to\explicit-development-vault.sqlite" --google-client "C:\path\to\provisioned-desktop-client.json"
```

Choose an explicit development vault location. No migration or automatic import
from existing credential caches occurs. Without a client file, the application can
open Settings but cannot enroll/reauthorize Google. Existing valid mail-scoped tokens
in the explicitly selected vault can be used; expired tokens require configured
refresh credentials. Missing configuration produces an actionable error, not samples.

1. Open **Settings**. **Create vault** for a new path or **Unlock** an existing M3
   development vault. Enter the expected Google address and **Connect Google**.
   Complete the external browser interaction yourself. Select the enrolled account.
2. Previously identity-only accounts need **Reauthorize selected** from this mailbox
   launch. Mail access is an explicit additional scope; identity authorization alone
   is insufficient. New Yahoo enrollment remains unavailable.
3. **Refresh headers** retrieves only INBOX header/flag/size data. **Older** scans
   earlier bounded UID windows; a sparse window may be empty but have an Older page.
4. Select a row and **Open selected** for an on-demand PEEK fetch. Conventional mail
   is plain text and unverified. HTML-only mail shows a placeholder; no remote images,
   scripts, embedded-message processing or attachment opening occurs.
5. For modern protected mail, import the sender's public certificate in Settings and
   select it in the inbox's signer control. Independent fingerprint verification is
   separate. Successful signature validation does not automatically verify identity.
   Failed modern verification releases no message; it never falls back to a legacy reader.
6. Only **Mark read**/**Mark unread** changes the provider flag. Refresh, selection,
   fetch and successful decryption do not. **Cancel**, account switch and **Lock**
   clear displayed content and invalidate late results. After cancelling a flag change,
   refresh to learn whether Gmail applied it. Closing locks the vault and stops work.

## Provider setup and live acceptance (not executed here)

Use an explicitly provisioned Google Desktop OAuth client, a configured consent
screen and approved test users. The mailbox launch requests OpenID/email identity
scopes plus the full IMAP `https://mail.google.com/` scope. This restricted scope is
broader than the read/flag functionality currently exposed; Google distribution
verification/policy obligations are not resolved by local tests. Workspace policy
may separately restrict IMAP or the client. No domain-wide delegation is implemented.

With two provisioned Google test accounts, verify browser enrollment/reauthorization,
same-provider switching, refresh after expiry, INBOX header pagination and on-demand
open. Compare unread flags in Gmail before/after refresh and open; then verify explicit
Mark read/unread. Cancel a slow request and switch accounts during retrieval. Deliver
an independently authorized M5-compatible fixture through an external test process,
then verify protected opening with the selected public certificate. Record provider
responses as sanitized outcomes, never tokens or private message bodies. This session
did not send mail, open live authorization or change any cloud configuration.

Official references consulted 2026-10-20:
[Google XOAUTH2](https://developers.google.com/workspace/gmail/imap/xoauth2-protocol)
defines the IMAP scope and authentication/error challenge; the adapter returns an
empty response to Google's error challenge.
[Python imaplib](https://docs.python.org/3.12/library/imaplib.html) provides TLS, UID
commands and read-only selection. The implementation adds pre-allocation literal
limits and cancellation polling; it never disables certificate/hostname verification.

## Qualified boundaries

INBOX only; manual retrieval; up to 30 headers from each 200-UID search window;
8 KiB fetched header literal; 256 KiB complete message (inherited M5 wire cap);
1 MiB aggregate response bytes per connection; 16 KiB response line. Conventional
MIME is bounded to 64 parts/depth eight; only text/plain renders. Existing M5's
stricter protected MIME limits apply unchanged. The encrypted header cache contains
one page per account, replaced on refresh/paging; no offline body cache or automatic
resumption. The existing vault's 8 MiB account limit still applies.

Worker budget is 30 seconds after dispatch, with 50 ms nonblocking TLS polling once
connected. Initial DNS/TLS setup, OAuth HTTP requests and SQLite waits retain their
documented limits; the complete lifecycle is not claimed to cancel within one second.
No message/credential/subject is written to application logs. The UI shows outer
metadata as transport claims and keeps cryptographic and identity results separate.

Tests: `python -m experiments.m6.run_tests` (or `--reverse`). These use only a local
TLS IMAP server, synthetic identities and disposable Windows vaults. See
[validation](m6-validation.md) and [ADR 007](../adrs/007-m6-gmail-mailbox-slice.md).
