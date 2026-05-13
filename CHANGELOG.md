# CHANGELOG.md — Session-by-Session Development Record
**Log every meaningful change made during a session before closing it.**  
One block per session. Most recent session at the top.

---

## How to Log an Entry

```
## [YYYY-MM-DD] — Session Title
### Added
- (new files or features created)
### Modified
- (existing files changed and why)
### Fixed
- (bugs resolved, with reference to BUGS.md entry if applicable)
### Notes
- (anything worth remembering about decisions made this session)
```

---

## Log

## [2026-03-30] — Session 3: Cloud Run Portal Migration (v1 Closeout)
**Overall v1 progress moved from ~78% to 100%. Portal is cloud-ready.**
### Added
- `portal/cloud_entrypoint.py` — Cloud Run entry point. Sets `PORTAL_MODE=cloud`, starts a plain HTTP server on `0.0.0.0:8080`. Never called locally. TLS terminated at Cloud Run load balancer.
- `google-cloud-firestore==2.20.2` to `requirements.txt` — sole new dependency for the migration.
- `kme/` directory added to Dockerfile to resolve Cloud Run ModuleNotFoundError.
### Modified
- `portal/portal_server.py` — Full migration to Cloud Firestore for session state:
  - Deleted `_SESSION_STORE`, `_RATE_LIMIT_BUCKETS`, `_STORE_LOCK`, `_RATE_LIMIT_LOCK`.
  - Added `_firestore_client` singleton (thread-safe lazy init via `_get_firestore()`).
  - `store_session()` writes to Firestore; `expires_at` stored as UTC datetime (native TTL field).
  - `_get_session_for_portal()` and `retrieve_private_key()` do plain Firestore document reads.
  - `_mark_consumed()` uses a Firestore `@db.transaction()` — atomic read-then-conditional-write; prevents replay under any race condition across Cloud Run instances.
  - `_is_rate_limited()` uses a Firestore transaction for the per-IP sliding-window counter.
  - Empty `session_id` guard in `do_GET` added to prevent Firestore invalid path errors.
  - `start()` is a logged no-op when `PORTAL_MODE=cloud`; unchanged in local mode.
  - URL construction uses `os.getenv("PORTAL_HOST", PORTAL_HOST)` — falls back to `config.py` constant locally, uses Cloud Run URL in cloud mode. `core/config.py` not modified.
  - Added `Access-Control-Allow-Origin` CORS header scoped to portal's own origin.
- `ui/compose_window.py` — Compose field clear on account switch fix applied. Guard skips `start_portal()` when `PORTAL_MODE=cloud`. `store_session()` still runs unconditionally (writes to Firestore in both modes).
- `ARCHITECTURE.md` — Added `cloud_entrypoint.py` to portal module map; Remote portal access marked ✅; overall completion updated to 100%; version bumped to 1.2.
- `Dockerfile` — liboqs version pinned to `--branch 0.15.0`.
- Cloud Run deployment configured with `min-instances=0` for cost management.
- Artifact Registry cleaned of stale images.
### Fixed
- SAE registry persistence bug resolved.
### Notes
- `core/config.py` is untouched. `portal_crypto.py` and `portal.html` are untouched.
- Pre-deployment GCP steps (Firestore Native mode DB, TTL policy on `expires_at`, `qumail-portal-sa` service account, `roles/datastore.user`) documented in the migration plan and completed.
- `secrets/firestore_key.json` confirmed covered by the existing `secrets/` blanket rule in `.gitignore`.

---

## [2026-03-28] — v1 Completion Sprint (Audit-Driven)
**Overall v1 progress moved from ~55% to ~78%.**
### Added
- `tests/test_tqr_roundtrip.py` — Full E2E roundtrip tests for all 3 TQR levels using a mock KME. 3/3 pass (Level 1 OTP ✅, Level 2 AES ✅, Level 3 ML-KEM ✅).
- **Re-authenticate button** in `ui/settings_window.py` — deletes stale OAuth token and re-runs the browser OAuth2 flow without losing session state.
- Encrypted ML-KEM private key persistence in `secrets/send_keys/<cert_id>.key` via `_persist_send_key()` in `compose_window.py`.
- `_load_send_key()` helper in `ui/inbox_view.py` — loads and Fernet-decrypts the private key at inbox message open time.
- `SEND_KEYS_DIR` constant in `core/config.py`.
- Copy Link button + amber security-framing banner in portal success dialog (`compose_window.py`).
- Plain-text `MIMEText` body in `mime/encapsulator.py` — recipient now sees human-readable instructions instead of mystery binary attachments.
### Modified
- `transport/imap_receiver.py` — Applied IMAP SSL socket timeout correctly (`timeout=_IMAP_TIMEOUT_SEC` + `sock.settimeout()`); moved `import re` to module level; reduced `_IMAP_TIMEOUT_SEC` to 15s; added debug `print` traces throughout `fetch_inbox`.
- `ui/inbox_view.py` — Fixed GC bug: `_FetchInboxWorker` stored as `self._inbox_worker`; `_FetchMessageWorker` stored as `self._msg_worker`; both use `Qt.ConnectionType.QueuedConnection` for cross-thread signals.
- `kme/virtual_node.py` — Replaced hardcoded `{128, 256}` key size restriction with flexible range check (128–524288 bits, multiple of 8) to support Level 1 OTP variable-length keys.
- `portal/portal_server.py` — Added `_ReusableHTTPServer` with `allow_reuse_address=True` to eliminate port 5001 conflict on app restart.
- `QuMail_Project_Abstract.md` — Qualified Level 1 OTP language to distinguish CSPRNG (prototype) vs. physics-guaranteed (live QKD hardware).
### Fixed
- Inbox hang (HIGH) — see `BUGS.md`
- Message click crash (HIGH) — see `BUGS.md`
- Level 1 OTP key rejection (HIGH) — see `BUGS.md`
- OAuth token expiry with no recovery path (MEDIUM) — see `BUGS.md`
### Verified Live
- Inbox loads 80 messages in <3 seconds (Gmail)
- Level 2 QuMail-to-QuMail full E2E: send → inbox → click → decrypted body renders ✅ **(First successful full round-trip)**
- Non-QuMail messages correctly blocked with privacy notice ✅
- pytest `tests/test_tqr_roundtrip.py` → 3/3 passed

---

## [2026-03-28] — Security Hardening and Test Suite
### Added
- Full unit test implementations in `tests/test_kme.py`, `tests/test_crypto.py`, `tests/test_transport.py`, `tests/test_mime.py`, and `tests/test_certificates.py`
- Security rate-limiting controls for portal and virtual KME request paths
### Modified
- `crypto/level3_mlkem.py` and `crypto/tqr.py` to fix Level 3 private-key handling correctness
- `transport/oauth2_gmail.py` and `transport/oauth2_yahoo.py` to encrypt OAuth token files at rest and enforce restrictive file permissions
- `portal/portal_server.py` to sanitize error output, add anti-abuse headers, and add rate limiting
- `kme/virtual_node.py` to enforce per-IP throttling and security logging
- `ui/inbox_view.py` to avoid leaking raw internal exception details to end users
- `ui/settings_window.py` and `core/config.py` to enforce safer local-only v1 KME endpoint usage and env-based Yahoo secret config
### Fixed
- Corrected Level 3 encryption/decryption key lifecycle bug where an incorrect key material path could break secure decapsulation semantics
### Notes
- Test run result: `python3 -m unittest discover -s tests -p "test_*.py"` → OK (`10` tests, `5` skipped due to optional dependencies not installed in this environment)

## [2026-03-28] — UI Integration Recovery
### Added
- `ui/settings_window.py` — account OAuth2 connect/disconnect, default TQR selector, KME endpoint controls
- `main.py` — minimal PyQt6 entrypoint that launches `MainWindow`
### Modified
- `ui/compose_window.py` — aligned recipient check and `tqr.encrypt()` calls with actual public interfaces
- `core/config.py` — added missing OAuth2 constants consumed by transport auth modules
- `BUGS.md` — logged known Level 3 inbox private key retrieval gap
### Fixed
- Resolved send-path API mismatches that would have failed at runtime (`check_recipient` import/signature and `tqr.encrypt` argument contract)
### Notes
- Compile pass completed successfully with `python3 -m compileall .`

## [2026-03-28] — Project Scaffolding
### Added
- `INSTRUCTIONS.md` — AI agent rules and frozen goal state
- `ARCHITECTURE.md` — Full directory structure and module responsibility map
- `DEFERRED.md` — Template for logging deferred suggestions
- `BUGS.md` — Template for logging out-of-scope bugs
- `CHANGELOG.md` — This file
### Notes
- README.md intentionally deferred to end of project
- Directory structure and all v1 decisions are frozen

