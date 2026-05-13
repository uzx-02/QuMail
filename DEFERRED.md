# DEFERRED.md — Alternative Approaches & Future Suggestions

## Log

### [2026-03-28] Replace google-auth-oauthlib in v2

- **Found during:** requirements.txt version audit
- **Current approach:** google-auth-oauthlib==1.3.0 used for Gmail OAuth2 flow
- **Suggested alternative:** Evaluate a maintained alternative or implement OAuth2 PKCE flow directly using the `requests` library before v2 development begins
- **Why deferred:** Library works fully for v1. Archival means no future security patches — not an immediate risk but must be resolved before v2 ships

### [2026-03-28] Level 1 OTP key sizing — real KME key pool exhaustion risk

- **Found during:** crypto/ design decision — Level 1 OTP key length strategy
- **Current approach:** `level1_otp.py` requests a single QKD key sized to match
  the plaintext length exactly (`key_size = len(plaintext) * 8` bits) via `KeyRequest`.
  This is valid and cost-free on the v1 Virtual Node (CSPRNG-backed, no pool limit).
- **Suggested alternative:** Before v2 (live KME), enforce a maximum plaintext size
  for Level 1 (e.g. 32 KB), or implement key-block streaming (multiple sequential
  key requests concatenated) with UUID logging for each segment. Physical QKD channels
  generate keys at ~1–10 Mbps under ideal conditions — large attachments will exhaust
  the key pool faster than it replenishes.
- **Why deferred:** Virtual Node has no pool constraint. Real KME integration is a v2
  concern. The data model already supports variable `key_size`, so the interface
  requires no change — only a policy decision on the size cap.

  ### [2026-03-28] ML-KEM-768 parameter set — evaluate upgrade to ML-KEM-1024 for v2

- **Found during:** crypto/level3_mlkem.py implementation
- **Current approach:** ML-KEM-768 (FIPS 203) — NIST security level 2, equivalent to
  AES-128 quantum security. Chosen for v1 as a practical balance of security and overhead.
- **Suggested alternative:** Evaluate ML-KEM-1024 (NIST security level 3, AES-192
  equivalent) before v2, particularly if QuMail is targeting government or CII-adjacent
  use cases where CERT-In or NQM guidelines may mandate higher PQC security levels.
  Only `_ML_KEM_ALGORITHM` constant in level3_mlkem.py needs changing — no structural
  code change required.
- **Why deferred:** ML-KEM-768 exceeds civilian threat model requirements for v1.
  Parameter upgrade decision should follow CERT-In / NQM policy guidance before v2.

  ### [2026-03-28] ML-KEM shared secret used directly as AES key — consider HKDF in v2

- **Found during:** crypto/level3_mlkem.py implementation
- **Current approach:** The 32-byte ML-KEM-768 shared secret is used directly as the
  AES-256-GCM key with no KDF step. This is valid — ML-KEM shared secrets are uniformly
  random by design, so a KDF adds no entropy. Same rationale applied to Level 2.
- **Suggested alternative:** Introduce HKDF-SHA256 (from the `cryptography` library)
  before v2 as a defence-in-depth measure. Some security auditors and compliance
  frameworks (e.g. FIPS 140-3 operational environments) require a formal key derivation
  step even when the input is already high-entropy, to ensure algorithm separation.
  Change is isolated to level3_mlkem.py and level2_aes.py — no interface change.
- **Why deferred:** No compliance requirement mandates it for v1. Adding HKDF now would
  be complexity with no practical security gain at this stage.

### [2026-03-28] Replace local OAuth key file with OS keyring

- **Found during:** OWASP hardening pass for OAuth token storage
- **Current approach:** OAuth tokens are encrypted at rest using a local Fernet master key
  (`secrets/oauth_master.key`) with restrictive file permissions.
- **Suggested alternative:** Store OAuth tokens and key material in OS credential stores
  (Windows Credential Manager / macOS Keychain / libsecret on Linux) to reduce local
  key-exfiltration risk if the app directory is compromised.
- **Why deferred:** v1 must stay dependency-light and cross-platform-simple. OS keyring
  integration introduces platform-conditional behavior and additional packaging work.

### [2026-03-28] Deploy portal server to public cloud for remote recipient access

- **Found during:** Audit Report v1 — Secure Portal not publicly accessible
- **Current approach:** Portal binds to `127.0.0.1:5001` — only accessible on the sender's machine.
- **Suggested alternative:** Deploy to Google Cloud Run with a stable public HTTPS endpoint and Let's Encrypt certificate. Sender's QuMail registers the encrypted session payload with the remote portal at send time.
- **Why deferred:** Requires cloud infrastructure, domain name, and cert setup. Planned for v2.
- **Status:** ✅ COMPLETED (2026-03-28) — Implemented in Cloud Run migration session. `portal_server.py` rewritten with Firestore session store; `cloud_entrypoint.py` added as Cloud Run entry point; `compose_window.py` guards local server start. GCP infrastructure setup pending (see migration plan Section 8–9).

### [2026-03-28] Yahoo OAuth2 end-to-end verification

- **Found during:** Audit Reports v1 and v2 — Yahoo send/receive unverified
- **Current approach:** Yahoo OAuth2 code mirrors Gmail, but `QUMAIL_YAHOO_CLIENT_ID` was never registered.
- **Suggested alternative:** Register a Yahoo Developer App, set env vars, run full send + inbox test.
- **Why deferred:** Gmail coverage sufficient for v1 demo. Yahoo is lower-priority for the ISRO context.

### [2026-03-28] Windows build packaging and liboqs.dll bundling

- **Found during:** Audit Reports v1 and v2 — Windows target unverified
- **Current approach:** All development on Linux. `liboqs.so` loaded via the venv-installed `oqs` package.
- **Suggested alternative:** Test on Windows with `liboqs.dll`. Validate PyInstaller spec bundles the correct shared library.
- **Why deferred:** No Windows test machine available. Scheduled for v1 pre-submission verification.

### [2026-03-28] Replace debug print statements with structured logging in imap_receiver.py

- **Found during:** v1 completion sprint — added to diagnose inbox hang
- **Current approach:** `fetch_inbox()` emits raw `print()` trace statements to stdout.
- **Suggested alternative:** Replace with `logging.debug()` using a module-level logger, silent at default `WARNING` level.
- **Why deferred:** Debug prints aid demo troubleshooting. Remove before any public release or submission build.

### [2026-03-28] Replace `{{SESSION_ID}}` byte substitution with Jinja2 template rendering

- **Found during:** Cloud Run portal migration session — reviewing `portal_server.py` GET handler
- **Current approach:** `portal.html` session ID is injected by a raw `bytes.replace(b"{{SESSION_ID}}", ...)` call in `_PortalHandler.do_GET()`. Fragile if the template byte layout changes or if the session ID appears elsewhere in the HTML.
- **Why deferred:** v1 template has exactly one substitution point; the byte-replace approach is reliable for this scope. Jinja2 integration adds minor complexity not justified before v1 ships.

### [2026-03-30] SMTP Subject line encryption via nested message encapsulation

- **Found during:** Codebase Intelligence Audit Report (Section 5)
- **Current approach:** Standard SMTP routing headers (including Subject, To, From) are transmitted in plaintext.
- **Suggested alternative:** Encrypt the entire original message (including the original subject) inside a wrapper MIME message (nested message encapsulation) to mitigate metadata leakage.
- **Why deferred:** Deferred to v2 to address metadata leakage identified in audit without blocking the v1 core release.

### [2026-03-30] Streaming encryption for large attachments

- **Found during:** Codebase Intelligence Audit Report (Section 8)
- **Current approach:** Entire message payloads and MIME structures are handled sequentially in synchronous memory.
- **Suggested alternative:** Implement chunked streaming encryption/decryption APIs.
- **Why deferred:** Deferred to v2. Large file attachments are out of scope for the v1 implementation.

### [2026-03-30] Cloud Armor GCP-layer rate limiting

- **Found during:** Portal security review / Cloud Run migration
- **Current approach:** Local rate-limiting achieved via a Firestore sliding window inside the Python handler.
- **Suggested alternative:** Offload rate limiting to Google Cloud Armor at the load balancer level before it hits the application tier.
- **Why deferred:** In-code rate limiting is perfectly sufficient for v1. Cloud Armor is a premium networking feature slated for v2 production hardening.
