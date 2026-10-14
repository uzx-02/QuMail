# QuMail M5 — Presentation Demo Guide

**Convention:** Aavishkar Research Convention (internal round)
**Prototype:** Secure email with post-quantum identity, durable outbox, and verified open

---

## Quick launch

```powershell
# From the repository root — works offline, no credentials, no real email
powershell -ExecutionPolicy Bypass -File .\Start-QuMailDemo.ps1
```

Or directly:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
$env:QT_PLUGIN_PATH  = Join-Path $PWD '.venv-m1-clean/Lib/site-packages/PyQt6/Qt6/plugins'
.\.venv-m1-clean\Scripts\python.exe -s -m experiments.m5.demo --loopback
```

---

## Fixture accounts

| Display name | Address                    | Role                  |
|--------------|----------------------------|-----------------------|
| sender       | sender@example.invalid     | Message author        |
| recipient    | recipient@example.invalid  | Primary recipient     |
| second       | second@example.invalid     | CC recipient          |

Keys are generated fresh each run and deleted on close.
No system trust anchors, real credentials, or external mail are used.

---

## Ready-to-type demonstration message

**To:** `recipient@example.invalid`
**Cc:** `second@example.invalid`
**Subject:** `Aavishkar Research Prototype — Secure Channel`
**Body:**
```
This message demonstrates end-to-end cryptographic protection
using the QuMail M5 experimental pipeline.

Key properties:
- Protected subject and body via PGP/MIME with post-quantum key exchange
- Durable outbox: message committed to storage before SMTP is attempted
- Sender archive: the sender can also decrypt this copy
- Verified open: signature and identity trust verified before content display
```

---

## 3–5 minute presentation sequence

### 1. Launch (30 s)
Run `Start-QuMailDemo.ps1`.
Point out the **"LOCAL RESEARCH DEMO"** label — this is a self-contained offline fixture.

### 2. Compose (45 s)
- QuMail opens on the **Compose** page.
- The **From** dropdown shows `sender@example.invalid` — already selected.
- Fill in the To, Cc, Subject, and Body fields above (pre-filled by the launcher).
- The **"Include sender archival copy"** checkbox is checked.

Narrate: *"Every field goes into an authenticated encrypted draft before any network touch."*

### 3. Save Draft → Prepare (60 s)
- Click **☁ Save Draft** — status badge changes to **Draft Saved**.
  *"The draft is encrypted and written to a local SQLite outbox."*
- Click **🔒 Prepare Secure Message** — badge changes to **Prepared**.
  *"The full signed/encrypted PGP/MIME envelope is now durably stored.
  Submission can only happen after preparation; there is no compose-and-send shortcut."*
- Switch to the **Secure Outbox** page in the sidebar to show the persisted message.

### 4. Submit (30 s)
- Click **📤 Submit via Local TLS** — badge changes to **Accepted**.
  *"The loopback fixture SMTP server accepted the DATA command.
  This confirms transport-layer acceptance, not recipient mailbox delivery."*

### 5. Recipient open (60 s)
- Switch to the **Open Message** page.
- In the **From** selector, pick `recipient@example.invalid` (or use the sidebar identity switcher).
  Actually: use the From combobox at the top of the **Compose** page to switch accounts,
  then return to **Open Message** and click **🔓 Decrypt & Verify**.
- The verification banner appears in green:
  *"Signature valid — in-person verified contact."*
- The decrypted subject and body appear in the content area.
  *"Content is never displayed before the backend cryptographic verification returns successfully."*

### 6. Sender archive (30 s)
- Switch back to `sender@example.invalid` using the From combobox.
- On the **Open Message** page, click **🔓 Decrypt & Verify** again.
- The banner now shows **Local Enrolled Identity** and `[Sender archive copy]`.
  *"The sender can read their own copy. One envelope, multiple authenticated recipients."*

---

## Restart and cleanup

Closing the window deletes the disposable vault and Windows credential entry automatically.
To restart cleanly: simply re-run `Start-QuMailDemo.ps1`.

For a fully automated headless run:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv-m1-clean\Scripts\python.exe -m experiments.m5.demo --loopback --smoke
# Expected: {"fixture_only": true, "initial": "Accepted", "final": "Accepted", ...}
```

---

## Known limitations

| Limitation | Detail |
|---|---|
| Bcc | Not available in M5; envelope rejected at MIME validation |
| Attachments | Supported by backend; no file-picker UI wired in this demo |
| Reply / forward | M6 scope; no reply-chain UI |
| Inbox / IMAP | Not implemented; Open Message uses the local persisted ciphertext copy |
| Retry scenario | Use `--scenario auth-reject` or `--scenario final-loss` to demo Failed / Unknown states |
| External mail | No external connections; loopback fixture only |
| Production packaging | Native heap/CPU caps, Linux execution, and release approval are unqualified |

---

## Verification command (minimum)

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv-m1-clean\Scripts\python.exe -m experiments.m5.demo --loopback --smoke
```

Expected output (single JSON line, exit 0):
```json
{"fixture_only": true, "initial": "Accepted", "final": "Accepted", "recipient_copies": 2, "sender_archive": true, "persisted_bytes_match": true, "private_content_logged": false}
```

---

## Known-good fallback

```powershell
git checkout 219dc97  # restores original panel.py if needed
```

The cryptographic, storage, identity, and transport layers are unchanged from `219dc97`.
