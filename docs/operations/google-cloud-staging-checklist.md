# QuMail — Google Cloud Staging Configuration Checklist

**Branch:** `codex/m7-ux-overhaul`  
**Date:** 2026-11-08  
**Scope:** Offline preparation checklist. Execution requires project-owner authorization (Stage B).

> [!IMPORTANT]
> No items on this checklist have been executed. This is a configuration reference for the project owner and technical lead to complete before Stage B live-Google operations.

---

## 1. Google Cloud Project

| Step | Action | Notes |
|------|--------|-------|
| 1.1 | Create new GCP project | Suggested name: `qumail-dev` or `qumail-testing` |
| 1.2 | Enable **Gmail API** | APIs & Services → Library → Gmail API → Enable |
| 1.3 | Enable **Google People API** | Required for contact/profile resolution (optional for IMAP+SMTP path) |
| 1.4 | Note **Project ID** | Used in consent screen and OAuth client configuration |

---

## 2. OAuth Consent Screen

| Step | Action | Notes |
|------|--------|-------|
| 2.1 | Navigate to APIs & Services → OAuth consent screen | |
| 2.2 | Select **External** user type | Internal requires Workspace domain. External allows test users without domain. |
| 2.3 | App name | `QuMail` or `QuMail Development` |
| 2.4 | Support email | Project owner's email |
| 2.5 | Developer contact | Project owner's email |
| 2.6 | Authorized domains | Leave blank for desktop app (no redirect domain needed) |
| 2.7 | **Save and Continue** | |

---

## 3. OAuth Scopes

The required scope depends on the chosen integration architecture (see integration analysis document).

### Current architecture — IMAP + SMTP (requires restricted scope)

| Scope | Classification | Google requirement |
|-------|---------------|-------------------|
| `https://mail.google.com/` | **Restricted** | Security assessment + annual re-verification for production. Test-mode OK for ≤100 users. |
| `openid` | Non-sensitive | No review required |
| `userinfo.email` | Non-sensitive | No review required |

### Recommended alternative — Gmail API (avoids restricted scope)

| Scope | Classification | Google requirement |
|-------|---------------|-------------------|
| `https://www.googleapis.com/auth/gmail.send` | **Sensitive** | Verification required for public app; test-mode OK for ≤100 users |
| `https://www.googleapis.com/auth/gmail.readonly` | **Sensitive** | Same as above |
| `openid` | Non-sensitive | No review required |
| `userinfo.email` | Non-sensitive | No review required |

> [!NOTE]
> For a test-mode app with ≤100 added test users, neither Restricted nor Sensitive scope requires production OAuth verification. Verification is required only to publish to all Google users.

**Checklist steps:**

| Step | Action |
|------|--------|
| 3.1 | Add scopes matching chosen architecture |
| 3.2 | Note that restricted scope (`mail.google.com`) will show a "This app isn't verified" warning to test users |
| 3.3 | Save and Continue |

---

## 4. Test Users

| Step | Action | Notes |
|------|--------|-------|
| 4.1 | Add test user email addresses | Up to 100 users. These are the only accounts that can authorize in testing mode. |
| 4.2 | Confirm project owner's Gmail is added | Required for any live-Gmail acceptance testing |
| 4.3 | Save | Test users can proceed through the unverified-app screen |

---

## 5. OAuth Client Credentials

| Step | Action | Notes |
|------|--------|-------|
| 5.1 | Navigate to APIs & Services → Credentials → Create Credentials → OAuth Client ID | |
| 5.2 | Application type: **Desktop app** | Required for installed-app PKCE flow used by `development_google.py` |
| 5.3 | Name: `QuMail Desktop Dev` | |
| 5.4 | Authorized redirect URIs | Add `http://127.0.0.1` (loopback); `http://localhost` (optional fallback). The app uses a dynamic port on loopback. |
| 5.5 | **Create** | |
| 5.6 | Download JSON → save as `client_secret_*.json` | Store securely — never commit. Keep outside the repository. |
| 5.7 | Note Client ID suffix `.apps.googleusercontent.com` | Required by `client_configuration()` validation |

---

## 6. Using the Client JSON with QuMail

```powershell
# Production launcher (Stage B+)
.\.venv-m1-clean\Scripts\python.exe main.py `
    --dev-mailbox `
    --dev-vault "C:\path\to\your\vault.db" `
    --dev-google-client "C:\path\to\client_secret_xxx.json"
```

```powershell
# Preflight check only (no vault created)
pwsh -File tools/start_google_acceptance.ps1 `
    -GoogleClient "C:\path\to\client_secret_xxx.json" `
    -Vault "C:\path\to\vault.db" `
    -CheckOnly
```

> [!CAUTION]
> Do not pass the client JSON path as a shell variable that gets logged. Use an explicit literal path in the command.

---

## 7. Token Expiry and Refresh Limitations (Testing Mode)

| Item | Detail |
|------|--------|
| Access token lifetime | ~1 hour |
| Refresh token lifetime | **7 days** in testing mode (not published/verified app) |
| After 7 days | User must re-authorize; refresh token is revoked by Google |
| Mitigation | Re-run `Connect Google` in Settings → triggers new authorization flow |
| Production workaround | Publish the OAuth app (requires Google verification for sensitive/restricted scopes) |

---

## 8. Pre-Authorization Validation (M12-PRE-01)

Before requesting Google authorization, run the accepted preflight:

```powershell
pwsh -File tools/start_google_acceptance.ps1 `
    -GoogleClient "C:\path\to\client_secret.json" `
    -Vault "C:\path\to\vault.db" `
    -CheckOnly
```

Expected output: `PASS` with no vault creation, no network connection, no token access.

---

## Status

- [ ] GCP project created  
- [ ] Gmail API enabled  
- [ ] OAuth consent screen configured  
- [ ] Scopes selected (architecture decision pending — see integration analysis)  
- [ ] Test users added  
- [ ] Desktop OAuth client created and JSON downloaded  
- [ ] Client JSON stored securely outside repository  
- [ ] M12-PRE-01 preflight re-run with real client JSON → PASS  
- [ ] Project owner authorizes Stage B  
