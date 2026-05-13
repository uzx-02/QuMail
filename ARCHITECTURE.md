# ARCHITECTURE.md — QuMail Directory Structure & Module Map
**Read INSTRUCTIONS.md before reading this file.**  
**This structure is frozen for v1. Do not reorganize without explicit instruction.**

---

## Project Root Layout

```
QuMail/
│
├── INSTRUCTIONS.md          ← AI agent rules. Read first, always.
├── ARCHITECTURE.md          ← This file. Module map and responsibilities.
├── DEFERRED.md              ← Logged alternative ideas for future versions.
├── BUGS.md                  ← Out-of-scope bugs found during development.
├── CHANGELOG.md             ← Record of completed changes per session.
├── README.md                ← Human-readable project overview.
├── requirements.txt         ← All Python dependencies. Edit only when instructed.
│
├── main.py                  ← Entry point only. Launches the PyQt6 app. No logic here.
│
├── core/                    ← App-wide shared config and session state.
├── kme/                     ← QKME Orchestrator — Virtual KME + client interface.
├── crypto/                  ← TQR Cryptographic Agility Layer — all 3 encryption levels.
├── transport/               ← Email send/receive, OAuth2, recipient detection.
├── mime/                    ← MIME encapsulation and decapsulation (RFC 3156).
├── portal/                  ← Insecure recipient secure web portal.
├── certificates/            ← Encryption audit trail — JSON + PDF output.
├── ui/                      ← PyQt6 desktop interface — all windows and widgets.
└── tests/                   ← Unit tests, one file per module.
```

---

## Module Responsibilities

### `main.py`
- Single responsibility: initialize the app and launch the main UI window.
- No business logic, no imports from crypto or transport.
- If this file exceeds ~30 lines, something is wrong.

---

### `core/`
```
core/
├── __init__.py
├── config.py       ← App-wide constants (ports, paths, default TQR level, timeouts).
└── session.py      ← Current session state (active account, KME connection status).
```
- `config.py` is the single source of truth for all hardcoded values.
- `session.py` holds runtime state passed between modules. Not a database — in-memory only (v1).

---

### `kme/`
```
kme/
├── __init__.py
├── virtual_node.py   ← Flask server simulating an ETSI GS QKD 014 KME. Runs locally.
├── kme_client.py     ← REST client that requests keys from the KME (virtual or live).
└── key_models.py     ← Data models: key object (UUID, key bytes, timestamp, SAE ID).
```
- `virtual_node.py` exposes the ETSI QKD 014 REST endpoints (`/api/v1/keys`).
- `kme_client.py` is the only file that talks to the KME. All crypto modules request keys through here.
- In v2, only `virtual_node.py` is replaced with a live KME connection. `kme_client.py` stays identical.
- **No other module imports directly from `virtual_node.py`.**

---

### `crypto/`
```
crypto/
├── __init__.py
├── tqr.py            ← TQR dispatcher. Accepts level (1/2/3), calls the correct module.
├── level1_otp.py     ← Level 1: One-Time Pad using QKD-delivered key.
├── level2_aes.py     ← Level 2: AES-256-GCM seeded with QKD-delivered key.
└── level3_mlkem.py   ← Level 3: ML-KEM FIPS 203 (liboqs). No QKD required.
```
- `tqr.py` is the only entry point into the crypto layer. Nothing calls `level1_otp.py` directly.
- Each level file handles only its own encrypt/decrypt logic. No cross-imports between levels.
- All three modules return a consistent output format: `{ ciphertext, metadata }`.

---

### `transport/`
```
transport/
├── __init__.py
├── smtp_sender.py      ← Sends encrypted email via SMTP using authenticated session.
├── imap_receiver.py    ← Fetches and parses incoming mail via IMAP.
├── oauth2_gmail.py     ← Gmail OAuth2 token acquisition and refresh.
├── oauth2_yahoo.py     ← Yahoo OAuth2 token acquisition and refresh.
└── recipient_check.py  ← Queries KME for recipient SAE ID. Flags non-QuMail endpoints.
```
- `smtp_sender.py` and `imap_receiver.py` receive an already-encrypted payload. They do not call crypto modules.
- OAuth2 files handle only authentication. Token storage is handled by `core/session.py`.
- `recipient_check.py` returns a simple boolean + metadata. Triggers TQR downgrade logic in `crypto/tqr.py`.

---

### `mime/`
```
mime/
├── __init__.py
├── encapsulator.py   ← Wraps ciphertext in RFC 3156 multipart/encrypted MIME structure.
└── decapsulator.py   ← Parses incoming QuMail MIME, extracts ciphertext and KME metadata.
```
- `encapsulator.py` is called after encryption, before sending. Accepts `{ ciphertext, metadata }`.
- `decapsulator.py` is called after receiving, before decryption. Returns `{ ciphertext, metadata }`.
- These files do not perform any encryption or transport. Pure MIME formatting only.

---

### `portal/`
```
portal/
├── __init__.py
├── portal_server.py      ← Session store (Firestore) + HTTPS/HTTP handler. Serves time-limited single-use portal link.
├── portal_crypto.py      ← Decrypts message client-side for the portal recipient.
├── cloud_entrypoint.py   ← Cloud Run entry point. Plain HTTP on port 8080. Never used locally.
└── templates/
    └── portal.html       ← HTML page served to insecure recipient. No frameworks.
```
- Activated only when `recipient_check.py` flags a non-QuMail recipient.
- `portal_server.py` persists sessions in Cloud Firestore (shared across all Cloud Run instances).
- In local mode (`PORTAL_MODE=local`, default), `start()` runs an HTTPS server on `PORTAL_HOST:PORTAL_PORT`.
- In cloud mode (`PORTAL_MODE=cloud`), `cloud_entrypoint.py` is the entry point; `start()` is a no-op.
- Portal Cloud Run Service URL: `https://qumail-portal-xxxx.run.app` (internal use only).
- `portal.html` must be self-contained. No CDN dependencies in v1.

---

### `certificates/`
```
certificates/
├── __init__.py
├── cert_generator.py   ← Generates JSON encryption certificate per session.
└── pdf_export.py       ← Converts JSON cert to PDF using fpdf2.
```
- Called at end of every send session. One certificate per sent email.
- JSON cert contains: key UUID, algorithm used, TQR level, timestamp, sender, recipient hash.
- `pdf_export.py` reads the JSON cert. It does not generate its own data.

---

### `ui/`
```
ui/
├── __init__.py
├── main_window.py        ← App shell. Hosts navigation and loads child windows.
├── compose_window.py     ← Email compose UI. TQR level toggle. Calls transport + crypto.
├── inbox_view.py         ← Inbox list. Message viewer. Calls imap_receiver + decapsulator.
├── key_status_widget.py  ← Reusable widget. Shows live KME connection + key exchange status.
└── settings_window.py    ← Account setup (OAuth2), TQR default level, KME endpoint config.
```
- UI files call into other modules but are never called by them (one-way dependency).
- No business logic in UI files. UI triggers actions; logic lives in core modules.
- `key_status_widget.py` is a reusable component embedded in other windows, not a standalone window.

---

### `tests/`
```
tests/
├── test_kme.py              ← Tests for virtual_node and kme_client.
├── test_crypto.py           ← Tests for all 3 TQR levels via tqr.py dispatcher.
├── test_transport.py        ← Tests for SMTP send, IMAP receive, recipient check.
├── test_mime.py             ← Tests for encapsulate/decapsulate round-trip.
├── test_certificates.py     ← Tests for JSON cert generation and PDF export.
└── test_tqr_roundtrip.py    ← E2E TQR encrypt→decrypt roundtrip (mock KME). All 3 levels. ✅ 3/3 pass.
```
- Tests use the module's public interface only. Never import private functions.
- v1 tests are unit tests only. No integration tests until v2.

---

## Dependency Flow (What Can Call What)

```
UI  →  transport / crypto / certificates / kme
transport  →  mime / kme_client / core
crypto (tqr.py only)  →  kme_client / level1 / level2 / level3
mime  →  (nothing — pure formatting)
certificates  →  (nothing — pure output)
kme_client  →  (nothing — pure REST calls)
portal  →  Firestore (Google Cloud) / portal_crypto
core  →  (nothing — pure config/state)
```

**Rule:** Dependencies only flow downward. Lower layers never import from UI or transport.

---

## Key Constraints (Repeat of INSTRUCTIONS.md §4 — enforced here too)

- One responsibility per file.
- No file should need more than one other module's context to be understood.
- If a file grows beyond ~150 lines, flag it for a split review before continuing.
- All inter-module data is passed as plain dicts or dataclasses. No shared globals.

---

## v1 Completion Status (as of 2026-03-28)

| Area | Status |
|---|---|
| Inbox load (Gmail) | ✅ Working — 80 messages in <3s |
| Inbox message click + decrypt | ✅ Working — Level 2 verified live |
| Level 1 OTP send | ✅ Verified |
| Level 2 AES send + receive | ✅ Full round-trip verified |
| Level 3 ML-KEM send + portal | ✅ Working |
| Level 3 ML-KEM inbox decrypt | ✅ E2E verification complete |
| OAuth token renewal | ✅ Re-authenticate button added |
| Portal port conflict on restart | ✅ Fixed (`SO_REUSEADDR`) |
| Email body for recipient | ✅ Plain-text body added |
| Yahoo send/receive | ✅ Verified |
| Windows build | ✅ Verified |
| Remote portal access | ✅ Cloud Run — Firestore session store, multi-instance isolation, smoke tests defined |

**Overall v1 completeness: 100%**

---

*Last updated: March 2026 | Version: 1.2 | Scope: v1 only*

