# ADR 010 — Zero-Friction Product Flow, Public Key Directory & External Recipient Handling

**Status:** Proposed Architecture & Product Evolution Strategy  
**Date:** 2026-11-10  
**Authors:** Antigravity (Implementation Engineer) & Mohammed Uzair Shaikh (Project Owner)  
**Target Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Branch:** `codex/m7-module-1-6-ws06-ws07`  

---

## 1. Context and Problem Statement

In early research milestones (M1–M3), cryptographic verification and message sealing were evaluated using a single-machine developer harness where Alice and Bob's accounts were alternately selected to export and import public certificates.

With the successful completion of **M7 Module 1.6 (WS-01 through WS-07)**, QuMail now provides a complete three-pane desktop email client, background IMAP synchronization, a durable outbox, Windows MSI/Inno packaging, and Group Policy management.

However, as QuMail prepares for initial 10-person enterprise and pilot deployments, a fundamental operational challenge arises regarding **key distribution and external correspondents**:
1. **The Adoption Friction of Manual Key Sharing:** Non-technical employees cannot be expected to manually export armored public key files and email them to colleagues before sending their first encrypted email.
2. **The Decentralized Mailbox Challenge:** When two users communicate between personal or unmanaged mail domains (e.g., Alice on `@gmail.com` and Bob on `@outlook.com`), there is no shared Active Directory or OpenPGP Web Key Directory (WKD) server hosted on those public mail providers.
3. **The Non-User Recipient Problem:** If Alice sends an email to Bob, and Bob does not use QuMail, requiring Bob to download and install a desktop Windows application simply to read one communication causes severe recipient abandonment.

---

## 2. Evaluation of Alternative Approaches

### 2.1 Rejected Option: In-Band Asynchronous Email Handshake (Automated SMTP Ping-Pong)
The owner and implementation engineer analyzed an automated 3-way handshake over email (Alice auto-sends public key $\rightarrow$ Bob's QuMail auto-replies with his key $\rightarrow$ Alice encrypts and sends the original message).

**Reasons for Rejection:**
- **Offline Recipient Latency:** If Bob's laptop is asleep or turned off, Bob's client cannot auto-reply. Alice's confidential draft would remain frozen in her outbox for hours or days.
- **Gmail Bot & Spam Detection:** Rapid automated back-and-forth emails between newly contacted addresses trigger Google Workspace and Microsoft 365 automated bot detection, risking temporary account suspension.
- **Inbox Clutter:** If Bob views his inbox on his mobile phone via Apple Mail or standard Gmail web, machine-generated handshake emails clutter his inbox.
- **Mail Loops & Quota Risk:** Auto-responders or bounce messages could trigger infinite loops, exhausting Gmail's 500–2,000 daily sending quota.

### 2.2 Accepted Strategic Architecture: The Two-Pillar Product Model

The product flow is evolved into two complementary pillars:

```
                               Alice drafts email in QuMail
                                            │
                                Is recipient on QuMail?
                                ┌───────────┴───────────┐
                               YES                      NO
                                │                       │
                     [Pillar 1: Native E2EE]    [Pillar 2: Secure Web Link]
                                │                       │
                     Fetches Bob's Public Key    Encrypts payload & sends:
                     from QuMail Directory.      "Alice sent you a secure message.
                                │                 Click here to view."
                                │                       │
                     100% Post-Quantum Local     Bob opens link in ANY browser,
                     Encryption in desktop app.  enters 6-digit OTP, reads & replies.
                                │                       │
                                ▼                       ▼
                     Direct Desktop Client      Zero-Install Recipient Portal
```

---

## 3. Decision Specifications

### 3.1 Pillar 1: QuMail Public Key Directory (QuMail-to-QuMail)
- **Role:** Centralized, public directory mapping email addresses to their active post-quantum public keys (`ML-KEM-768` + `Ed25519`).
- **Cryptographic Boundary:**
  - The directory server stores **ONLY public keys** and verification metadata.
  - **Zero Private Secrets:** Private keys, database master passwords, DPAPI blobs, OAuth tokens, and email plaintext are **STRICTLY PROHIBITED** from ever touching the directory server.
  - Public keys are public by definition (analogous to telephone numbers in a phone directory).
- **Client Integration:**
  - Upon first-run account enrollment, the desktop client optionally registers its public key via an authenticated HTTPS REST endpoint.
  - During draft composition (`mailbox_client/workflows.py`), if a recipient's public key is not in the local vault or WKD, QuMail queries the directory server over HTTPS in $<100\text{ ms}$.
  - The email is encrypted and sealed locally on Alice's workstation before entering SMTP transmission.
  - **Zero Handshake Latency:** Works seamlessly even if Bob's computer is turned off.

### 3.2 Pillar 2: External Non-QuMail Recipient Experience (Secure Web Link)
- **Role:** Allows QuMail users to communicate securely with external partners, accountants, and clients who do not have QuMail installed.
- **Workflow:**
  1. QuMail detects the recipient does not possess post-quantum keys.
  2. The message is symmetrically encrypted using an ephemeral AES-256-GCM session key.
  3. The encrypted payload is published to a secure web access portal.
  4. The external recipient receives an invitation email: *"Alice has sent you an encrypted communication via QuMail [View Secure Message]"*.
  5. The recipient opens the link in their web browser (desktop or mobile), enters a One-Time Passcode (OTP) sent to their email to prove domain ownership, and views the decrypted message.
  6. The recipient can reply securely through the web portal, which re-encrypts the response back to Alice's QuMail client.
- **Security Boundary:** The desktop client's core post-quantum vault remains completely local and protected by Windows DPAPI. The web link model operates as an external relay adapter.

---

## 4. Zero-Cost 10-Client Pilot Blueprint

To validate this workflow for an immediate 10-person pilot without incurring enterprise cloud infrastructure costs:
1. **Lightweight Directory Server:** Implemented as a minimal Python FastAPI application backed by SQLite.
2. **Free Hosting Tier:** Deployed on **Render.com** (Free Web Service) or **Cloudflare Workers** (Free Tier / D1 database), providing free automated HTTPS SSL certificates (`https://qumail-keys.onrender.com`).
3. **Bandwidth & Compute Requirements:** 10 clients generate $<100\text{ KB}$ of public key traffic per day, easily fitting within free tier boundaries forever.

---

## 5. Security & Invariant Consequences

1. **Local Vault Protection Preserved:** All existing M3 vault structures, DPAPI boundaries, M4 durable outbox semantics, and M5 OpenPGP-PQ wire specifications remain completely unmodified.
2. **Honest Security Indicators:** 
   - Directory-fetched keys without enterprise CA certification display the amber **`CAUTION: Identity Unverified`** badge, maintaining compliance with the WS-02 trust contract.
   - Corporate GPO-provisioned keys display the green **`SECURE`** badge.
3. **No Automatic Downgrades:** Plaintext release continues to strictly require valid cryptographic verification.
