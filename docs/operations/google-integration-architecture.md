# QuMail — Google Integration Architecture & Scope Decision

**Branch:** `codex/m7-e2e-completion`  
**Date:** 2026-11-08  
**Author:** Technical Architecture & Security Team  
**Scope:** Canonical Google OAuth scope analysis, least-privilege assessment, CASA tier compliance, and transport architecture decision.

---

## 1. Executive Summary & Core Decision

> [!IMPORTANT]
> **Definitive Decision:** **Retain and standardize on Option A (Gmail IMAP + SMTP over TLS with XOAUTH2).**
> Do not migrate to the proprietary Gmail REST API. The current working IMAP/SMTP transport adapter remains the approved standard for both the current acceptance milestone and the corporate product.

### Key Justifications:
1. **Scope Classification Reality:** Correcting the previous misclassification: **`https://www.googleapis.com/auth/gmail.readonly` is a RESTRICTED scope** under Google's API Services User Data Policy, exactly like `https://mail.google.com/`. Switching to the Gmail API for message retrieval provides **zero compliance relief** regarding Google's Cloud Application Security Assessment (CASA Tier 2 / Tier 3) requirement.
2. **Provider Agnosticism:** IMAP (RFC 3501/RFC 9051) and SMTP (RFC 5321) with SASL XOAUTH2 are vendor-neutral internet standards supported by Google Workspace, Microsoft 365, Yahoo, Fastmail, and self-hosted corporate mail transfer agents. Migrating to the Gmail REST API would create vendor lock-in and require separate proprietary adapters for every corporate provider.
3. **MIME Integrity:** The existing cryptographic pipeline generates standard RFC 5322 / RFC 3156 `multipart/encrypted` OpenPGP payloads. IMAP and SMTP handle raw MIME byte streams natively, whereas Gmail REST API introduces base64url JSON serialization overhead and strict payload size constraints.
4. **Desktop App Security Profile:** For corporate deployments, QuMail executes purely as an installed desktop client (Desktop App client type) storing data locally in an encrypted SQLite vault (`qumail_acceptance_vault.sqlite`). No server-side ingestion or third-party cloud data processing exists.

---

## 2. Exhaustive Scope Classification & Least-Privilege Analysis

Google Cloud divides Gmail OAuth 2.0 scopes into three distinct tiers:

| Scope URI | Google Tier | Permitted Operations | CASA Verification Tier |
|---|---|---|---|
| `openid` | Non-Sensitive | Authenticate user identity | No review required |
| `https://www.googleapis.com/auth/userinfo.email` | Non-Sensitive | Read user email address | No review required |
| `https://www.googleapis.com/auth/gmail.send` | **Sensitive** | Send email on user's behalf | Standard OAuth App Verification |
| `https://www.googleapis.com/auth/gmail.labels` | **Sensitive** | Read/write mailbox labels | Standard OAuth App Verification |
| `https://www.googleapis.com/auth/gmail.metadata` | **Sensitive** | View headers and metadata (no bodies) | Standard OAuth App Verification |
| `https://www.googleapis.com/auth/gmail.readonly` | **RESTRICTED** | Read all email bodies and attachments | **CASA Tier 2 / Tier 3 Assessment Required** |
| `https://www.googleapis.com/auth/gmail.modify` | **RESTRICTED** | Read, compose, update, and trash mail | **CASA Tier 2 / Tier 3 Assessment Required** |
| `https://www.googleapis.com/auth/gmail.compose` | **RESTRICTED** | Create drafts and send messages | **CASA Tier 2 / Tier 3 Assessment Required** |
| `https://mail.google.com/` | **RESTRICTED** | Full IMAP, SMTP, and mailbox control | **CASA Tier 2 / Tier 3 Assessment Required** |

### Correcting the Previous Assessment:
- Earlier planning documentation mistakenly assumed that replacing `https://mail.google.com/` with `gmail.readonly` + `gmail.send` would avoid a Restricted Scope security assessment.
- **That assumption was legally and technically false.** Under Google's updated policy (effective since 2019 and revised under CASA in 2022), any application reading message bodies (`gmail.readonly`) is classified as **Restricted** and requires an annual Cloud Application Security Assessment (CASA Tier 2 or Tier 3 via an authorized lab such as Bishop Fox, Leviathan, or NCC Group).
- Therefore, there is **no compliance benefit** to adopting the Gmail REST API for a client that reads email.

---

## 3. Detailed Architecture Comparison

### Option A: Standard IMAP + SMTP over TLS with XOAUTH2 (Current & Approved)
- **Reading:** IMAP4rev1 (`imap.gmail.com:993`) via TLS socket. Uses `BODY.PEEK[]` to fetch headers and MIME envelopes without altering server `\Seen` flags.
- **Sending:** ESMTP (`smtp.gmail.com:587`) via STARTTLS. Authenticates with `AUTH XOAUTH2`.
- **Scopes:** `https://mail.google.com/` + `openid` + `userinfo.email`.
- **Status:** **Implemented, tested on loopback, and verified live by Project Owner.**
- **Strengths:**
  - Standard RFC protocol; zero code rewrite.
  - Multi-provider compatible (Yahoo, Outlook, Dovecot, Postfix).
  - Handles streaming encrypted payloads without base64url JSON re-encoding.
  - Live Gmail connection already proven.

### Option B: Gmail REST API (`gmail.v1`)
- **Reading:** HTTP GET `https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}`.
- **Sending:** HTTP POST `https://gmail.googleapis.com/gmail/v1/users/me/messages/send` with `{ "raw": "<base64url>" }`.
- **Scopes:** `gmail.readonly` (Restricted) + `gmail.send` (Sensitive).
- **Status:** Not implemented.
- **Weaknesses:**
  - Requires writing and qualifying an entirely new REST network transport module.
  - Still triggers the same CASA Restricted Scope assessment due to `gmail.readonly`.
  - Rate-limited to 250 quota units/sec per user; large batch operations consume quota rapidly.
  - Does not support non-Google email accounts.

### Option C: Hybrid Architecture (Gmail REST API for Send + IMAP for Read)
- **Reading:** IMAP via `mail.google.com`.
- **Sending:** Gmail REST API via `gmail.send`.
- **Status:** Not recommended.
- **Weaknesses:**
  - Combines the complexity of both architectures with zero security or compliance gain.
  - Still requires `mail.google.com` for IMAP, leaving the app in the Restricted tier anyway.

---

## 4. Google Verification & Production Path Roadmap

| Development Phase | Target Audience | Scope Classification Impact | Practical Action Required |
|---|---|---|---|
| **Phase 1: Acceptance & Staging (Current)** | Designated test accounts (≤100 users) | Testing status | Add test users in GCP Console. **No Google verification or CASA audit required.** |
| **Phase 2: Internal Enterprise Workspace** | Google Workspace organization domain | Internal user type | Workspace Domain Admin grants domain-wide pre-authorization. **Bypasses CASA review entirely.** |
| **Phase 3: Public Commercial Release** | General public Gmail users | Restricted Scope (`mail.google.com`) | 1. Google OAuth Brand Verification.<br>2. Annual CASA Tier 2 self-assessment or Tier 3 lab audit.<br>3. Publish privacy policy specifying zero server-side storage. |

---

## 5. Architectural Contract Sign-Off

1. `transport/imap_receiver.py` and `transport/smtp_sender.py` remain the canonical, maintained email transport adapters.
2. `transport/development_google.py` and `transport/bounded_google.py` continue to negotiate `SCOPES + (MAIL_SCOPE,)`.
3. All future enterprise integrations (Exchange/Outlook, Yahoo, custom IMAP/SMTP) will extend the standardized socket/SASL pipeline rather than fragmenting into proprietary REST SDKs.
