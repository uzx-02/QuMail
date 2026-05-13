# BUGS.md — Out-of-Scope Bugs & Issues

## Log

### [2026-03-28] Level 3 inbox decryption private key unavailable

- **Found in:** `ui/inbox_view.py` and `crypto/tqr.py` interface expectations
- **Found during:** UI verification and integration pass
- **Description:** Level 3 decryption requires `private_key` in `tqr.decrypt()`, but there is no v1 receive-side retrieval path for QuMail-to-QuMail inbox messages. The UI currently shows a plain-language notice instead of decrypted content.
- **Severity:** High
- **Status:** ✅ FIXED (2026-03-28) — `_persist_send_key()` in `compose_window.py` now saves the ML-KEM private key as a Fernet-encrypted file in `secrets/send_keys/<cert_id>.key` after every Level 3 send. `_load_send_key()` in `inbox_view.py` reads and decrypts it at open time and passes it to `tqr.decrypt()`. End-to-end verification of Level 3 inbox decrypt pending.

### [2026-03-28] Inbox Refresh hangs indefinitely — IMAP fetch not completing

- **Found in:** `ui/inbox_view.py` (`_FetchInboxWorker`), `transport/imap_receiver.py` (`fetch_inbox`)
- **Found during:** E2E inbox verification pass
- **Description:** Clicking "Refresh" in the Inbox tab causes the UI to hang on "Fetching messages…" indefinitely. Root causes identified: (1) `_IMAP_TIMEOUT_SEC` was never passed to `imaplib.IMAP4_SSL()` so the socket had no timeout; (2) the SSL socket timeout was not re-applied after wrapping; (3) `worker_obj` was a local variable and could be garbage-collected mid-run by Python GC; (4) signals used default connection type instead of `QueuedConnection`.
- **Severity:** High
- **Status:** ✅ FIXED (2026-03-28) — Applied `timeout=_IMAP_TIMEOUT_SEC` to `IMAP4_SSL` constructor + explicit `sock.settimeout()` on SSL socket; stored worker as `self._inbox_worker`; used `Qt.ConnectionType.QueuedConnection` for `finished`/`failed` signals. Verified: 80 messages load in <3s.

### [2026-03-28] Message click crashes app — QThread destroyed while running

- **Found in:** `ui/inbox_view.py` (`_on_message_selected`, `_FetchMessageWorker`)
- **Found during:** Post-inbox-fix E2E click test
- **Description:** `worker_obj` in `_on_message_selected` was a local variable like in `_load_inbox`. Python GC collected it while the background thread was still running, producing `QThread: Destroyed while thread '' is still running` and a core dump.
- **Severity:** High
- **Status:** ✅ FIXED (2026-03-28) — Stored as `self._msg_worker`; applied `QueuedConnection` on signals. Verified: clicking a Level 2 message now decrypts and renders body text.

### [2026-03-28] Level 1 OTP key size rejected by KME virtual node

- **Found in:** `kme/virtual_node.py` (line ~87)
- **Found during:** Level 1 (Maximum Security) send test
- **Description:** `virtual_node.py` hardcoded `if key_size not in (128, 256): return 400`. Level 1 OTP requires a key equal in length to the plaintext, which is never exactly 128 or 256 bits for a real message.
- **Severity:** High
- **Status:** ✅ FIXED (2026-03-28) — Replaced strict enum check with range validation: `128 ≤ key_size ≤ 524288, must be multiple of 8`. Live verification pending after app restart.

### [2026-03-28] No OAuth token refresh / re-authentication option

- **Found in:** `ui/settings_window.py`
- **Found during:** Loading inbox for second Gmail account
- **Description:** "IMAP authentication failed: [AUTHENTICATIONFAILED] Invalid credentials" — the stored OAuth token expired but Settings had no option to re-run the browser flow without fully disconnecting and reconnecting.
- **Severity:** Medium
- **Status:** ✅ FIXED (2026-03-28) — Added **Re-authenticate** button to Settings → Account section. Deletes the cached token file and immediately re-runs the OAuth browser flow for the current provider. User verified: fresh token obtained successfully.

### [2026-03-28] `datetime.utcnow()` deprecated in Python 3.12 — `_generate_tls_cert()`

- **Found in:** `portal/portal_server.py`, `_generate_tls_cert()` (the `.not_valid_before()` and `.not_valid_after()` calls)
- **Found during:** Cloud Run portal migration session
- **Description:** `datetime.datetime.utcnow()` is deprecated as of Python 3.12 and will be removed in a future version. The correct replacement is `datetime.now(timezone.utc)`. The `cryptography` library's `CertificateBuilder` accepts timezone-aware datetimes.
- **Severity:** Low — no functional impact in Python 3.12; will become an error in a future Python release
- **Status:** Open

### [2026-03-30] liboqs-python version delta (0.14.1 bindings vs 0.15.0 C lib)

- **Found in:** Dockerfile & requirements.txt
- **Found during:** Cloud Run portal migration
- **Description:** liboqs-python v0.14.1 bindings conflict with the 0.15.0 native C library.
- **Severity:** Medium
- **Status:** ✅ FIXED (2026-03-30) — Resolved in Dockerfile by pinning `--branch 0.15.0`.

### [2026-03-30] Missing kme/ directory in Dockerfile

- **Found in:** `portal/Dockerfile`
- **Found during:** Cloud Run deployment
- **Description:** Missing directory caused `ModuleNotFoundError` on Cloud Run.
- **Severity:** High
- **Status:** ✅ FIXED (2026-03-30) — Resolved by adding `COPY kme/ ./kme/` to the Dockerfile.

### [2026-03-30] Empty session_id from root URL GET

- **Found in:** `portal/portal_server.py`
- **Found during:** Cloud Run smoke test
- **Description:** Empty `session_id` from root URL GET request caused Firestore invalid path error.
- **Severity:** Medium
- **Status:** ✅ FIXED (2026-03-30) — Resolved by adding empty string guard in `_PortalHandler.do_GET`.
