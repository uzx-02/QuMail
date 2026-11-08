# QuMail — Google Integration Architecture Comparison

**Branch:** `codex/m7-ux-overhaul`  
**Date:** 2026-11-08  
**Scope:** Offline architectural analysis. No live Google operations executed.

---

## 1. Architecture Options

### Option A — IMAP + SMTP (Current Implementation)

**How it works:** Uses Gmail IMAP (`imap.gmail.com:993`) for reading and SMTP (`smtp.gmail.com:587`) for sending, authenticated with XOAUTH2 access tokens.

**Current scope:** `https://mail.google.com/` (single, all-access Gmail scope)

**Code path:**
- `transport/imap_receiver.py` — IMAP fetch with XOAUTH2
- `transport/smtp_sender.py` — SMTP submit with XOAUTH2  
- `transport/oauth2_gmail.py` — Token acquisition
- `transport/bounded_google.py` / `development_google.py` — M3 OAuth flow

| Attribute | Detail |
|-----------|--------|
| Scope | `https://mail.google.com/` — **Restricted** (highest sensitivity level) |
| Google review requirement | Security assessment + annual re-verification for production public apps |
| Test-mode (≤100 users) | Works without Google verification |
| MIME compatibility | Full raw MIME access; arbitrary headers/attachments including OpenPGP |
| Implementation status | Implemented; SMTP path tested via loopback integration test |
| Live Gmail test status | Not yet executed (Stage B pending) |

**Verdict:** Technically complete. The restricted scope is a **production-deployment blocker** for public release; it is not a blocker for internal/test-mode operation with ≤100 invited test users.

---

### Option B — Gmail API Only

**How it works:** Uses Google's REST Gmail API (`https://www.googleapis.com/gmail/v1/`) for all send and receive operations via JSON/base64 MIME encoding.

**Required scopes:**
- `https://www.googleapis.com/auth/gmail.send` — Sensitive (not Restricted)
- `https://www.googleapis.com/auth/gmail.readonly` — Sensitive (not Restricted)

**Key considerations:**

| Attribute | Detail |
|-----------|--------|
| Scope | Sensitive (not Restricted) — lower compliance bar for production |
| Google review requirement | OAuth verification for public app, but no security assessment |
| MIME compatibility | Messages sent as `raw` base64-encoded RFC 2822 MIME — **OpenPGP/MIME payloads fully supported** |
| Implementation status | **Not implemented** — requires new transport adapter |
| Implementation effort | ~1–2 days: replace IMAP/SMTP adapters with `google-api-python-client` calls |
| Rate limits | Per-user: 250 quota units/second; 1 billion units/day |

**Critical finding:** The Gmail API `users.messages.send` endpoint accepts a `raw` base64url-encoded RFC 2822 message. This means QuMail's existing encrypted MIME encapsulation layer (`experiments/m5/mime.py`) produces compatible payloads without modification. The Gmail API path avoids the restricted scope while supporting the same encrypted MIME workflow.

**Verdict:** **Recommended for production path.** Requires new transport adapter but avoids restricted-scope security assessment. The existing encryption/MIME pipeline is unaffected.

---

### Option C — Hybrid (Gmail API send + IMAP receive)

**How it works:** Use Gmail API for outbound (avoids restricted scope for SMTP), retain IMAP adapter for inbound (requires `mail.google.com` for IMAP, or use `gmail.readonly` via API).

**Assessment:** No advantage over Option B. Using `gmail.readonly` via Gmail API for receive provides the same scope reduction as full Gmail API. Hybrid adds complexity without benefit. **Not recommended.**

---

## 2. Recommended Architecture

**Short-term (testing, ≤100 users):** Option A — current IMAP+SMTP path is sufficient. The restricted scope is acceptable for test-mode operation under the 100-user limit.

**Long-term (public/production release):** Option B — Gmail API with `gmail.send` + `gmail.readonly` scopes. Avoids restricted-scope security assessment. The M5 MIME pipeline is compatible.

---

## 3. Scope Comparison Summary

| Scope | Classification | Test-mode OK | Production path |
|-------|---------------|-------------|----------------|
| `https://mail.google.com/` | Restricted | ✅ ≤100 users | Requires security assessment |
| `gmail.send` + `gmail.readonly` | Sensitive | ✅ ≤100 users | OAuth verification only (no security assessment) |
| `openid` + `userinfo.email` | Non-sensitive | ✅ | No review required |

---

## 4. Current SCOPES Declaration

From `transport/development_google.py` line 23:

```python
SCOPES = ('openid', 'https://www.googleapis.com/auth/userinfo.email')
```

This is the **identity-only scope** used for the M3 OAuth enrollment flow (account verification, not mail access). The Gmail mail scopes (`mail.google.com`) are separately configured in the IMAP/SMTP transport layer via XOAUTH2.

The identity SCOPES are non-sensitive and require no Google review regardless of architecture choice.

---

## 5. Impact of Architecture Choice on Existing Code

| Component | Option A impact | Option B impact |
|-----------|----------------|----------------|
| `experiments/m5/mime.py` | Unchanged | Unchanged |
| `experiments/m4/` outbox | Unchanged | Unchanged |
| `transport/imap_receiver.py` | Used as-is | Replaced by Gmail API adapter |
| `transport/smtp_sender.py` | Used as-is | Replaced by Gmail API adapter |
| `transport/bounded_google.py` | Unchanged | Unchanged |
| `transport/development_google.py` | Unchanged | Unchanged (identity scopes unaffected) |
| `mailbox_client/gmail.py` | Used as-is | Needs Gmail API adapter |
| `mailbox_client/service.py` | Unchanged | Unchanged |

**No backend service, vault, outbox, or cryptographic component requires modification for either architecture choice.**
