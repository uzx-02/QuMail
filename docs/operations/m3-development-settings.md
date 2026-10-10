# M3 development Settings and Google acceptance

Updated 2026-10-10. This is a disabled-by-default development path under ADR 004.
Independent review is deferred until before production enablement/security release;
its absence does not stop this authorized development. Sending is disabled.

## Start without reading legacy data

Build the pinned helper with `./experiments/m3/build-provider.ps1`, using the
existing documented M2 toolchain/native setup. From the repository root:

```powershell
./.venv-m1-clean/Scripts/python.exe main.py --dev-identity --dev-vault tmp/m3-app/vault.sqlite
```

This opens the development identity Settings window. It never constructs legacy
MainWindow, Session, inbox/compose workers, TQR, simulator, portal or transport
sending. `--dev-simulator` cannot be combined with this mode. Omitting
`--dev-identity` retains the legacy default behavior and does not open the modern
vault. Neither path migrates data. Use a separate development vault, not a legacy
data directory. Create vault and Unlock/Lock are explicit controls; lock removes
the selected context and cancels outstanding authorization work. OS storage must
be available; no password/file-key fallback exists.

The Settings selector switches complete immutable account views. Root, account,
device and key handle belong to that one view; no OAuth/private material is stored
in the view or legacy global session. Starting authorization, switching accounts,
locking, cancellation and closing invalidate generation tickets. Workers perform
authorization/refresh only; a current ticket is required before the GUI thread
can commit credentials/account enrollment. Stale results/errors are discarded.
At most two unfinished authorization workers are allowed. Network calls have
15-second timeouts; loopback wait has a three-minute deadline and cancellation.

## Provision a Google test client explicitly

No test client/account configuration was supplied or searched for in this task.
No live authorization or Gmail support acceptance is claimed. To obtain it:

1. Create an owner-controlled Google Cloud project and OAuth consent configuration
   in testing mode. Add the intended test-account email(s). Create a **Desktop app**
   OAuth client; download its client JSON to a private location outside Git.
2. Request only OpenID and authorized email identity here. This path requests
   `openid` and `https://www.googleapis.com/auth/userinfo.email`; it does not request
   Gmail SMTP/IMAP access or claim transport authorization. Provision two test
   accounts under the same provider to validate isolation.
3. Launch with the explicit client file:

```powershell
./.venv-m1-clean/Scripts/python.exe main.py --dev-identity --dev-vault tmp/m3-app/vault.sqlite --google-client "C:\private-test-config\desktop-client.json"
```

Only that selected client file is read; no existing OAuth caches are consulted.
Token endpoint must match the fixed official Google endpoint. The client file's
Google authorization URI may be `/o/oauth2/auth` or `/o/oauth2/v2/auth`; both
explicitly select the documented v2 endpoint at runtime. Other endpoints are
rejected. Client
configuration is not copied into the repository or vault. Desktop clients cannot
keep a client secret confidential; PKCE protects the authorization-code exchange.
Google documents desktop system-browser authorization and ephemeral loopback IP
redirects in its [native-app guide](https://developers.google.com/identity/protocols/oauth2/native-app).

## Google implementation and live acceptance steps

Enter the expected test-account address, then Connect Google. Complete the external
browser interaction yourself. Each attempt uses random state and nonce,
google-auth-oauthlib 1.3.0 S256 PKCE, and a listener bound only to `127.0.0.1` on an
OS-selected port. It checks exact callback path/Host/port, single code/state and
state equality; callback URLs and codes are not logged. Token exchange remains
HTTPS through maintained libraries; no global insecure-transport switch is set.

google-auth 2.49.1 verifies the ID-token signature/issuer/audience/expiry. Nonce,
authorized-party, expected subject on reauthorization, expected email and Google
address authority are checked separately. Non-Gmail addresses require a matching
hosted-domain claim; unproven aliases are rejected. See Google's
[ID-token validation guidance](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token)
and [OpenID Connect semantics](https://developers.google.com/identity/openid-connect/openid-connect).

Account certificate, metadata and credentials are written in one authenticated
SQLite transaction only after verification and a current generation check.
Cancel, mismatch, secure-store failure and commit failure cannot install a partial
account. A post-commit display failure may require Unlock to rediscover a complete
committed account; it must not be mistaken for a partial enrollment.

Refresh uses google-auth Credentials and the fixed Google TLS userinfo endpoint
to verify the fresh access token's subject and authorized email. A refresh ID
token is optional; if present it is also verified. Refresh does not invent a
nonce requirement absent from that response. Wrong identity or revoked/failed
refresh leaves stored credentials unchanged; use Reauthorize selected for a new
browser ceremony bound to the selected subject/address. Yahoo has no new flow
and remains explicitly unavailable.

For live acceptance, record client type (not its secret), OS/library versions,
test-case outcomes and sanitized provider error categories, never tokens/codes:

- Connect both provisioned accounts; confirm separate roots/opaque records and
  selection. Check refresh and reauthorization remain bound to each subject.
- Cancel in the browser and in Settings; try another browser account; switch or
  lock while authorizing/refreshing. No stale token, key or status may be installed.
- Remove/revoke only disposable test credentials at the provider and repeat
  refresh/reauthorization. Record denial, timeouts, consent and token-lifetime
  behavior; testing-mode limitations belong in acceptance evidence.
- Repeat through a clean development vault and explicit encrypted recovery.
  Keep all generated keys/backups/OS entries private and clean up only those test
  artifacts. There is no mail send or production approval step in this acceptance.

Passing local fixtures does not substitute for this live evidence.

## Certificate, trust and recovery controls

Import a public certificate for an explicit contact address. Self-signatures and
address bindings are necessary but do not grant trust. Select the contact and
enter the entire fingerprint independently verified in person, by independent
voice or QR. The table distinguishes unverified, independently verified, changed,
expired and revoked. Failed status lookup clears the table and reports unavailable
rather than showing a stale verified assertion. Rotate/revoke controls operate
only on the selected account; public export never includes private key material.

Encrypted backup leaves the source lifecycle unchanged. Transfer device asks for
confirmation and suspends locally only after successful package persistence and
vault commit. Outputs use new files, never overwrite an existing backup. The
random recovery secret is intentionally shown locally once and is not logged,
saved or automatically copied to the clipboard. Store it offline separately.

Restore requires a clean vault, recovery secret and fresh matching Google
authorization. Historical keys are restored transactionally into archive-only
state. Activate unchanged root requires explicit acknowledgment that prior devices
are retired; its fingerprint stays unchanged. Replace root creates a different
fingerprint and requires renewed verification by contacts. Neither can prove an
offline copy was erased. See [recovery policy](m3-recovery.md).

This is Windows development support. Local crypto/storage actions are synchronous
in this small Settings panel; OAuth waits run off-thread. Production UI performance,
memory/crash containment, filesystem-race hardening, broader platform support,
licensing/distribution and security-release qualification remain later gates.
