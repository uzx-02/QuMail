# QuMail — Google Integration Architecture & Scope Decision
## Canonical Scope Analysis, CASA Framework Classification, and Transport Strategy

**Milestone:** M7 — Module 1.5 Architecture Assessment  
**Working Branch:** `codex/m7-security-roundtrip`  
**Author:** Technical Architecture & Security Lead  
**Scope:** Canonical Google OAuth scope analysis, least-privilege assessment, CASA Assurance Levels (AL1 vs AL2), and transport architecture evaluation.

---

## 1. Executive Summary & Architectural Decision

> [!IMPORTANT]
> **Definitive Decision:** **Retain standard IMAP4rev1 and ESMTP over TLS with XOAUTH2.**  
> QuMail will not migrate to the proprietary Gmail REST API. The existing, working IMAP and SMTP transport adapters remain the approved canonical architecture for both acceptance testing and the corporate product.

### Core Justifications:
1. **Accurate Scope Reality:** Under Google's API Services User Data Policy, `https://www.googleapis.com/auth/gmail.readonly` is legally categorized as a **RESTRICTED** scope, exactly like `https://mail.google.com/`. Switching to the Gmail REST API to read email provides **zero regulatory relief** from Google's restricted-scope verification requirements.
2. **Provider Agnosticism & Multi-Provider Roadmap:** Standard IMAP (RFC 3501 / RFC 9051) and ESMTP (RFC 5321) with SASL XOAUTH2 are vendor-neutral internet standards supported across Google Workspace, Microsoft 365, Yahoo, Fastmail, and private corporate MTAs (Dovecot/Postfix). Adopting Google-proprietary REST endpoints would fragment the transport layer and introduce unnecessary vendor lock-in.
3. **MIME Compatibility:** The Gmail REST API accepts standard RFC 2822 / RFC 5322 messages via the `raw` base64url-encoded field. While this allows transmitting `multipart/encrypted` OpenPGP payloads without dismantling inner MIME parts, it introduces JSON wrapping, base64url encoding/decoding overhead, and HTTP batch size limits compared to direct socket streaming over TLS.
4. **Desktop Security Model:** QuMail functions as an installed desktop client (OAuth Client Type: Desktop App). All encryption, key derivation, and message decryption execute locally on the employee's machine. Zero plaintext or decryption keys are transmitted to or stored on third-party cloud infrastructure.

---

## 2. Google OAuth Scope Classification

Google classifies OAuth 2.0 scopes into Non-Sensitive, Sensitive, and Restricted tiers:

| Scope URI | Google Classification | Scope Definition & Capabilities | Verification Requirement |
|---|---|---|---|
| `openid` | **Non-Sensitive** | Authenticate user identity via OIDC | Standard Developer Registration |
| `https://www.googleapis.com/auth/userinfo.email` | **Non-Sensitive** | Read user primary email address | Standard Developer Registration |
| `https://www.googleapis.com/auth/gmail.send` | **Sensitive** | Send email on user's behalf | OAuth App Verification (Google Trust & Safety) |
| `https://www.googleapis.com/auth/gmail.labels` | **Sensitive** | Manage mailbox labels and folders | OAuth App Verification (Google Trust & Safety) |
| `https://www.googleapis.com/auth/gmail.metadata` | **Sensitive** | View headers and metadata (no message bodies) | OAuth App Verification (Google Trust & Safety) |
| `https://www.googleapis.com/auth/gmail.readonly` | **RESTRICTED** | Read all email bodies and attachments | OAuth Verification + CASA Security Assessment |
| `https://www.googleapis.com/auth/gmail.compose` | **RESTRICTED** | Create drafts and send messages | OAuth Verification + CASA Security Assessment |
| `https://www.googleapis.com/auth/gmail.modify` | **RESTRICTED** | Read, compose, modify, and delete messages | OAuth Verification + CASA Security Assessment |
| `https://mail.google.com/` | **RESTRICTED** | Full IMAP, SMTP, and mailbox control | OAuth Verification + CASA Security Assessment |

---

## 3. Compliance Framework: OAuth Verification vs. CASA Security Assessment

Google enforces a clear two-part compliance boundary for applications accessing user data:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       GOOGLE CLOUD COMPLIANCE BOUNDARY                      │
├──────────────────────────────────────┬──────────────────────────────────────┤
│ 1. OAuth App Verification            │ 2. Restricted Scope CASA Assessment  │
│ (Brand Trust & User Transparency)    │ (Technical Application Security)     │
├──────────────────────────────────────┼──────────────────────────────────────┤
│ • Handled by Google Trust & Safety   │ • Governed by App Defense Alliance   │
│ • Domain verification in Search      │ • Technical assessment against OWASP │
│   Console                            │   Application Security Verification  │
│ • Published Privacy Policy review    │   Standard (ASVS)                    │
│ • In-app branding and consent flow   │ • Evaluates storage, crypto, network │
│   video walk-through                 │   isolation, and dependency hygiene  │
│ • Applies to Sensitive & Restricted  │ • Mandatory for RESTRICTED scopes    │
└──────────────────────────────────────┴──────────────────────────────────────┘
```

### The CASA Framework: Assurance Levels (AL1 vs. AL2)
Under the Cloud Application Security Assessment (CASA) framework, requirements are risk-based and categorized into Assurance Levels rather than universal flat requirements:

- **CASA Assurance Level 1 (AL1):**  
  A standardized self-assessment questionnaire and automated configuration scan based on OWASP ASVS Level 1. AL1 evaluates basic application security controls and carries no lab testing fees.
- **CASA Assurance Level 2 (AL2):**  
  An independent third-party technical assessment conducted by an App Defense Alliance Authorized Lab (e.g., Bishop Fox, Leviathan Security Group, NCC Group). Required for applications with broader data exposure, higher user volume, or multi-tenant cloud processing. Assessment pricing is not universal or fixed by Google; lab pricing varies based on codebase complexity, architecture (pure desktop vs. cloud-hosted backend), and specific API scopes utilized.

### 3.1 Deployment Models & Governance: QuMail Explanatory Taxonomy

To evaluate development and deployment options under Google's OAuth 2.0 and API policies, QuMail utilizes a four-category explanatory taxonomy. *(Note: These four categories represent QuMail's operational model for architectural clarity and evaluation; they are not four formal categories defined as such by Google).*

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        GOOGLE OAUTH 2.0 DEPLOYMENT & COMPLIANCE TIERS                  │
│                          (QuMail Explanatory Operational Model)                        │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ Category                 │ Scope / Identity Rules   │ Compliance & Assessment Burden   │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 1. External Testing Mode │ Personal Gmail or        │ • Standard verification waived   │
│    (Active Development)  │ unverified project;      │   for testing phase only.        │
│                          │ User Type: "External",   │ • Hard cap of 100 Test Users.    │
│                          │ Status: "Testing".       │ • 7-day refresh token lifespan.  │
│                          │                          │ • "Unverified app" screen.       │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 2. Internal Organization │ Project owned by Google  │ • Exempt from public OAuth brand │
│    Application           │ Workspace / Cloud        │   verification consent flow.     │
│    (Enterprise Intranet) │ Identity Organization;   │ • Security assessment (CASA/ASVS)│
│                          │ User Type: "Internal".   │   depends on architecture & data │
│                          │                          │   routing (not automatic waiver).│
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 3. Domain-Wide Admin     │ External multi-tenant    │ • Bypasses individual user       │
│    Installation          │ app installed domain-    │   consent prompts.               │
│    (Workspace Admin      │ wide by customer domain  │ • DOES NOT remove restricted-    │
│    Approval)             │ administrator.           │   scope verification/CASA        │
│                          │                          │   requirements for developer.    │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ 4. Public External       │ User Type: "External",   │ • Mandatory Google Trust & Safety│
│    Distribution          │ Status: "In Production", │   OAuth App Verification.        │
│    (General Commercial)  │ multi-tenant consumer    │ • Mandatory CASA assessment for  │
│                          │ and business users.      │   Restricted scopes.             │
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

#### Detailed Deployment Analysis:

1. **Category 1: External Testing Mode (Current Development Status)**
   - **Configuration:** Project created under developer account; User Type = "External", Publishing Status = "Testing".
   - **Explicit User Allowlist:** Strictly limited to up to **100 explicitly invited Test Users** listed by email in Google Cloud Console. Unlisted accounts are rejected with `403 access_denied: QuMail has not completed the Google verification process`.
   - **Consent Experience:** Displays the unverified app warning interstitial (*"Google hasn't verified this app"*). Users must explicitly click *Advanced* $\rightarrow$ *"Go to QuMail (unsafe)"*.
   - **Token Lifetime:** Refresh tokens expire automatically after **7 days** (per Google policy for unverified projects in Testing mode with external user type and sensitive/restricted scopes). Staging accounts must re-authenticate weekly.
   - **Regulatory Scope:** Testing mode is strictly an engineering sandbox; it does **not** grant a blanket waiver from Google API Services User Data Policies or applicable security obligations.

2. **Category 2: Internal-Only Organization Applications (Corporate Intranet Exception)**
   - **Strict Prerequisite Conditions:**
     1. The Google Cloud project **must be owned by a verified Google Workspace or Cloud Identity Organization resource** (not a personal `@gmail.com` account).
     2. The OAuth consent screen User Type **must be explicitly configured as "Internal"** (an option available solely when an Organization resource owns the project).
     3. Authentication is programmatically restricted to users belonging to that specific Google Workspace or Cloud Identity organization.
   - **OAuth Verification vs. Security Assessment Applicability:**
     - *OAuth Verification Exemption:* Google officially waives the public OAuth brand/app verification process for Internal applications because data access is confined within the enterprise owning the project. Tokens do not expire in 7 days, there is no 100-user limit, and employees do not encounter the unverified-app warning screen.
     - *Security Assessment (CASA) Reality:* Internal application status does **not** categorically exempt an organization from all CASA or security-assessment obligations. If an internal application routes restricted data through a third-party server, relies on external cloud backends, or integrates with third-party software vendors, enterprise security policies, Cloud Marketplace rules, or API governance frameworks may still trigger CASA or independent security assessment requirements. The applicable obligations must be determined based on the actual deployment architecture, hosting environment, and data flows.

3. **Category 3: Domain-Wide Installation by a Workspace Administrator (Admin Pre-Approval)**
   - **Mechanism:** A Workspace domain administrator can install an application for all or specific organizational units via Google Workspace Marketplace or configure administrative API Controls / Security Settings.
   - **Operational Effect:** Administrative installation grants pre-authorization on behalf of domain users, which can remove brand-verification warning dialogs in documented enterprise scenarios.
   - **Critical Scope Verification Reality:** Domain-wide admin installation is fundamentally distinct from the Internal user type. It does **not** automatically remove Google's restricted-scope or sensitive-scope verification requirements for the developer of an external application. An external application requesting Restricted scopes (`https://mail.google.com/` or `https://www.googleapis.com/auth/gmail.readonly`) remains subject to Google Trust & Safety review and applicable CASA assessments before general marketplace availability.

4. **Category 4: Public External Distribution (Commercial Release)**
   - **Requirements:** For broad distribution across consumer Gmail accounts (`@gmail.com`) and unmanaged third-party domains, the application must complete:
     - Google Trust & Safety Brand & Domain Verification (Search Console domain ownership, published privacy policy, video walkthrough).
     - Cloud Application Security Assessment (CASA Tier 2 / AL2 authorized lab testing or AL1 self-assessment, depending on risk profile, scopes, and data handling architecture as determined by the App Defense Alliance framework).
   - **Operational Benefit:** Permanent refresh tokens, unlimited global user base, verified Google brand trust status.

---

## 4. Architectural Comparison: IMAP/SMTP vs. Gmail API vs. Hybrid

### Option A: Standard IMAP + SMTP over TLS with XOAUTH2 (Current & Canonical)
- **Inbound Protocol:** IMAP4rev1 (`imap.gmail.com:993`) via TLS socket using `BODY.PEEK[]`.
- **Outbound Protocol:** ESMTP (`smtp.gmail.com:587` or `:465`) via STARTTLS/TLS using `AUTH XOAUTH2`.
- **MIME Handling:** Native streaming of RFC 5322 / RFC 3156 `multipart/encrypted` byte streams.
- **Evaluation:**
  - **Code Reuse:** 100% reuse of existing maintained adapters (`mailbox_client`, `experiments/m4`, `experiments/m5`).
  - **Multi-Provider Support:** Identical codebase connects to Google, Microsoft 365, Yahoo, and private corporate Dovecot/Postfix servers.
  - **Scope:** Uses `https://mail.google.com/` (Restricted).
  - **Verdict:** **Approved Standard.**

### Option B: Gmail REST API (`gmail.v1`)
- **Inbound Protocol:** HTTP GET `https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}`.
- **Outbound Protocol:** HTTP POST `https://gmail.googleapis.com/gmail/v1/users/me/messages/send` with `{ "raw": "<base64url>" }`.
- **MIME Handling:** The `raw` field accepts full RFC 2822 messages encoded as base64url strings, preserving encrypted OpenPGP payloads without dismantling MIME parts.
- **Evaluation:**
  - **Code Reuse:** Requires replacing working socket transport code with new HTTP client, rate limiter, and paging logic.
  - **Scope Benefit:** Requires `gmail.readonly` (Restricted) + `gmail.send` (Sensitive). Since `gmail.readonly` is Restricted, **zero CASA relief is achieved**.
  - **Provider Lock-In:** Google-only proprietary protocol; cannot connect to Outlook or private corporate servers.
  - **Verdict:** **Rejected.**

### Option C: Hybrid Architecture (Gmail REST API Send + IMAP Read)
- **Evaluation:** Combines two distinct transport stacks without any compliance or security benefit. Retaining IMAP still requires `mail.google.com`, leaving the application in the Restricted tier.
- **Verdict:** **Rejected.**

---

## 5. Architectural Recommendation Sign-Off

1. Standardize permanently on **IMAP4rev1 + ESMTP over TLS with SASL XOAUTH2**.
2. Retain `https://mail.google.com/` + `openid` + `userinfo.email` as the production scope set.
3. For enterprise deployment, recommend Google Workspace Domain Administrator pre-authorization.
4. For future commercial distribution, proceed with standard Google OAuth App Verification followed by CASA AL1/AL2 validation.
