# QuMail — Quantum-Secure Email Client

> **Protecting India's communications — today and in the quantum era.**

QuMail is a desktop email client that adds a transparent, standards-compliant layer of post-quantum cryptography to standard webmail providers — Gmail and Yahoo — without requiring any changes from the underlying email infrastructure or the recipient's setup. It is the only open-source civilian email client designed from the ground up to integrate Quantum Key Distribution (QKD) workflows with mainstream SMTP/IMAP providers, while simultaneously supporting NIST FIPS 203 ML-KEM as a software-only fallback when QKD infrastructure is not yet available.

Built in direct alignment with **ISRO Problem Statement PS 25179** and **India's Critical Information Infrastructure PQC deadline of December 31, 2028**.

---

## Table of Contents

- [The Problem](#the-problem)
- [Solution Overview](#solution-overview)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Security Standards](#security-standards)
- [Prerequisites](#prerequisites)
- [Setup and Configuration](#setup-and-configuration)
- [Gmail OAuth2 Setup](#gmail-oauth2-setup)
- [Running the Application](#running-the-application)
- [Portal Deployment — Cloud Run](#portal-deployment--cloud-run)
- [Project Status](#project-status)
- [Codebase Structure](#codebase-structure)
- [Known Limitations](#known-limitations)
- [Roadmap](#roadmap)
- [Acknowledgements](#acknowledgements)

---

## The Problem

### Harvest Now, Decrypt Later

"Harvest Now, Decrypt Later" (HNDL) is not a theoretical future threat — it is an active, ongoing operation. State-sponsored adversaries are intercepting and archiving encrypted email traffic today, with the explicit intent to decrypt it retrospectively once cryptographically relevant quantum computers (CRQCs) become available. The NSA, CISA, India's National Quantum Mission, and CERT-In have all formally acknowledged HNDL as a current operational reality.

Standard email, despite relying on TLS in transit, is structurally exposed to this threat. Every message traverses multiple intermediate relays, any of which can be tapped. The payload is encrypted with RSA or ECC-based key exchange — algorithms that a sufficiently powerful quantum computer can break in hours using Shor's algorithm. A June 2025 study confirmed that approximately one million superconducting physical qubits would be sufficient to break RSA-2048, pulling projected CRQC timelines forward significantly.

### India's Statutory Deadline

India's Critical Information Infrastructure (CII) has a statutory deadline of **December 31, 2028** to achieve full Post-Quantum Cryptography adoption. 1.26 million Indian government email accounts have been migrated to a secure platform — yet PQC and QKD adoption in email remains in the low single digits as of 2026. The software layer that bridges India's growing quantum infrastructure to everyday email does not yet exist for civilian use.

### The Gap

| Solution | Gap |
|---|---|
| Proton Mail / Tuta | PQC only (ML-KEM), no QKD — closed ecosystem, no Gmail/Yahoo compatibility |
| Defence-grade QKD tools | Military use only — no civilian access pathway |
| Gmail / Outlook / Yahoo | Zero quantum protection — RSA-based, no PQC roadmap |
| Open-source PQMail projects | No mainstream provider compatibility — no user-facing client |

**QuMail is designed to fill this gap.** It works with the email providers people already use. It requires no new infrastructure from recipients. And its architecture is a drop-in interface — when India's civilian QKD backbone goes live, QuMail connects to it with a single configuration change.

---

## Solution Overview

QuMail integrates three components into a single desktop application:

**1. QKME Orchestrator** — A Key Management Entity interface built against the ETSI GS QKD 014 REST standard. Before every send, a unique 256-bit quantum-derived key tagged by UUID is requested and delivered to the encryption layer. In v1, this runs against a locally simulated Virtual Node. In v2, the Virtual Node is replaced with a live KME — no other code changes required.

**2. Tiered Quantum Resilience (TQR) Architecture** — Three selectable encryption levels per email, calibrated to the sender's threat model and available infrastructure. The level is selected per-message and downgraded automatically when recipient constraints require it.

**3. Email Transport and UI Layer** — Standard SMTP and IMAP with OAuth2 for Gmail and Yahoo. Every session generates a tamper-evident JSON encryption certificate. The PyQt6 desktop interface exposes security level selection as a simple toggle with real-time key exchange status visibility.

---

## How It Works

### The Three TQR Levels

#### Level 1 — Quantum OTP (Maximum Security)
Encrypts the message using a One-Time Pad where the key is delivered exclusively via the Quantum Network (KME). The key is physics-guaranteed random when connected to a live QKD channel — unconditionally secure regardless of any computing power, classical or quantum. In simulation, entropy is sourced from a CSPRNG (Python `secrets`), which is computationally secure. The software interface is identical; only the entropy source upgrades when the QKD backbone connects.

**Threat model:** Unconditional security against any computationally unbounded adversary when using a live QKD source. Computationally secure (AES-256 equivalent) in simulation.

#### Level 2 — QKD-Seeded AES-256-GCM (High Security)
Encrypts using AES-256-GCM with a 256-bit key delivered by the Quantum Network rather than negotiated over the internet. Combines quantum-sourced entropy with the efficiency needed for large payloads and high-volume email. The practical default for enterprise deployments.

**Threat model:** Secure against all classical adversaries. Against quantum adversaries, Grover's algorithm halves effective key length — AES-256 provides AES-128 equivalent security against quantum attacks, which NIST considers safe through 2035+.

#### Level 3 — ML-KEM FIPS 203 (Quantum-Safe Fallback)
Uses ML-KEM-768 (NIST FIPS 203, formerly CRYSTALS-Kyber) to encapsulate the encryption key, hybridised with AES-256-GCM for the message payload. Requires no QKD connection — the software-only fallback for environments where QKD infrastructure is unavailable, and the automatic selection when sending to a non-QuMail recipient.

**Threat model:** Secure against both classical and quantum adversaries. ML-KEM-768 provides NIST security level 3 — equivalent to AES-192 against quantum attacks.

### Send and Receive Flow

```
┌─────────────────────────────────────────────────────────────┐
│  QUMAIL-TO-QUMAIL (Levels 1, 2, or 3)                       │
│                                                             │
│  Sender                                                     │
│    │                                                        │
│    ├─→ [KME Key Request] ──→ Virtual Node ──→ 256-bit Key   │
│    │                                                        │
│    ├─→ [TQR Encrypt] ──→ { ciphertext, metadata }           │
│    │                                                        │
│    ├─→ [MIME Wrap — RFC 3156 multipart/encrypted]           │
│    │                                                        │
│    └─→ SMTP ──→ Gmail / Yahoo relay ──→ Recipient inbox     │
│                                                             │
│  Recipient                                                  │
│    │                                                        │
│    ├─→ IMAP fetch ──→ [MIME Unwrap] ──→ { ciphertext }      │
│    │                                                        │
│    ├─→ [KME Key Lookup by UUID]                             │
│    │                                                        │
│    └─→ [TQR Decrypt] ──→ Plaintext displayed in inbox       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  NON-QUMAIL RECIPIENT (Level 3 — Automatic Downgrade)       │
│                                                             │
│  Sender                                                     │
│    │                                                        │
│    ├─→ [Recipient Check] ──→ No SAE ID found in KME         │
│    │                                                        │
│    ├─→ [Auto TQR Downgrade → Level 3]                       │
│    │                                                        │
│    ├─→ [ML-KEM Encrypt] ──→ ciphertext stored in Firestore  │
│    │                                                        │
│    ├─→ SMTP ──→ Email with time-limited HTTPS portal link   │
│    │                                                        │
│    └─→ Private key stored exclusively in Firestore session  │
│                                                             │
│  Recipient                                                  │
│    │                                                        │
│    ├─→ Opens HTTPS portal link in any browser               │
│    │                                                        │
│    ├─→ [Cloud Run] ──→ [Firestore session lookup]           │
│    │                                                        │
│    ├─→ [ML-KEM Decrypt] ──→ Plaintext rendered in browser   │
│    │                                                        │
│    └─→ Session marked consumed — replay returns 410         │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture

QuMail is built on a strict single-responsibility modular architecture. Dependencies flow in one direction only — UI imports from lower layers; lower layers never import from UI.

```
QuMail/
│
├── main.py                  Entry point only. Launches PyQt6. No logic.
│
├── core/                    App-wide config constants and in-memory session state.
├── kme/                     ETSI GS QKD 014 Virtual Node + REST client + key models.
├── crypto/                  TQR dispatcher + Level 1 OTP, Level 2 AES, Level 3 ML-KEM.
├── transport/               SMTP send, IMAP receive, OAuth2 (Gmail + Yahoo), recipient check.
├── mime/                    RFC 3156 MIME encapsulation and decapsulation. Pure formatting.
├── portal/                  Cloud Run HTTPS portal for non-QuMail recipients.
├── certificates/            JSON + PDF encryption audit trail. One certificate per send.
├── ui/                      PyQt6 desktop interface. Consumes lower layers. No business logic.
└── tests/                   Unit tests per module + E2E TQR roundtrip (all 3 levels ✅).
```

### Dependency Flow

```
UI  →  transport / crypto / certificates / kme
transport  →  mime / kme_client / core
crypto (tqr.py only)  →  kme_client / level1 / level2 / level3
mime  →  (nothing — pure formatting)
certificates  →  (nothing — pure output)
kme_client  →  (nothing — pure REST calls)
core  →  (nothing — pure config/state)
portal  →  crypto (via portal_crypto.py isolation bridge)
```

---

## Security Standards

| Standard | Role in QuMail |
|---|---|
| **NIST FIPS 203** | Defines the ML-KEM-768 parameters used in Level 3 encryption and the automatic insecure-recipient downgrade path |
| **ETSI GS QKD 014** | Defines the REST API architecture implemented by the Virtual KME — the drop-in interface for a live QKD node in v2 |
| **RFC 3156** | Dictates the `multipart/encrypted` MIME structure used to encapsulate all encrypted payloads — indistinguishable from standard encrypted attachments to mail relay AI filters |
| **AES-256-GCM** | Authenticated symmetric bulk encryption used in Level 2 (QKD-seeded) and Level 3 (ML-KEM hybrid) |
| **ISRO PS 25179** | The foundational ISRO problem statement whose protocol specifications (ETSI GS QKD 014, FIPS 203) and infrastructure vision directly shaped QuMail's architecture |

---

## Prerequisites

### System Requirements

- **OS:** Linux (primary — tested on Ubuntu 22.04 / Pop!_OS 22.04). Windows v1 target — PyInstaller packaging in v2.
- **Python:** 3.12
- **Docker:** Required for Cloud Run portal deployment only
- **liboqs C library 0.15.0** — must be built from source before installing Python dependencies

#### Build liboqs C library on Ubuntu

```bash
# Install build dependencies
sudo apt-get update && sudo apt-get install -y \
    cmake ninja-build gcc g++ git libssl-dev python3-dev

# Clone and build — pinned to 0.15.0
git clone --depth 1 --branch 0.15.0 \
    https://github.com/open-quantum-safe/liboqs.git /tmp/liboqs

cmake -S /tmp/liboqs -B /tmp/liboqs/build \
    -DBUILD_SHARED_LIBS=ON \
    -DOQS_BUILD_ONLY_LIB=ON \
    -GNinja

cmake --build /tmp/liboqs/build
sudo cmake --install /tmp/liboqs/build
sudo ldconfig

# Verify
python3 -c "import oqs; print(oqs.oqs_version())"
# Expected output: 0.15.0
```

> **Version note:** `requirements.txt` pins `liboqs-python==0.14.1` (Python bindings). The underlying C library must be `0.15.0`. A version mismatch will produce a `UserWarning` at runtime but will not prevent operation. This delta is tracked in `BUGS.md` and will be resolved in v2 when a compatible liboqs-python release is available.

### Python Dependencies

All Python dependencies are pinned to exact versions in `requirements.txt`.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

| Package | Version | Purpose |
|---|---|---|
| `PyQt6` | 6.10.2 | Desktop UI framework |
| `Flask` | 3.1.3 | Virtual KME ETSI QKD 014 REST server |
| `cryptography` | 46.0.5 | AES-256-GCM (Level 2), TLS cert generation |
| `liboqs-python` | 0.14.1 | ML-KEM FIPS 203 Python bindings (requires native C lib) |
| `google-auth` | 2.49.1 | Gmail OAuth2 token management |
| `google-auth-oauthlib` | 1.3.0 | Gmail OAuth2 flow |
| `fpdf2` | 2.8.4 | PDF encryption certificate export |
| `requests` | 2.33.0 | KME REST client HTTP calls |
| `google-cloud-firestore` | 2.20.2 | Cloud Run portal session store |

---

## Setup and Configuration

### 1. Clone the repository

```bash
git clone https://github.com/uzx-02/QuMail.git
cd QuMail
```

### 2. Create and activate virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Build and install liboqs C library

Follow the [build instructions above](#build-liboqs-c-library-on-ubuntu) exactly. The Python bindings will fail to load if the native library is not installed system-wide first.

### 4. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 5. Create the secrets directory

```bash
mkdir -p secrets
```

The `secrets/` directory is covered by `.gitignore` — never commit its contents.

---

## Gmail OAuth2 Setup

QuMail uses Gmail's OAuth2 API for send and receive. This requires a one-time setup in Google Cloud Console.

**Step 1 — Create a Google Cloud Project**

Go to [console.cloud.google.com](https://console.cloud.google.com), create a new project, and enable the **Gmail API** under APIs & Services.

**Step 2 — Configure OAuth2 Consent Screen**

Navigate to APIs & Services → OAuth consent screen. Set the application type to **Desktop app**. Add your Gmail address as a test user.

**Step 3 — Create OAuth2 Credentials**

Navigate to APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID. Select **Desktop app**. Download the JSON credentials file.

**Step 4 — Place credentials in secrets/**

Rename the downloaded file to `gmail_client_secret.json` and place it at:

```
secrets/gmail_client_secret.json
```

The `secrets/gmail_token.json` file will be created automatically on first login.

**Required OAuth2 scopes** (configured in `core/config.py`):
```
https://mail.google.com/
openid
https://www.googleapis.com/auth/userinfo.email
```

---

## Running the Application

### Start the application

```bash
source venv/bin/activate
python3 main.py
```

On first launch, the OAuth2 browser flow will open automatically for Gmail authentication. The Virtual KME node starts in the background on `127.0.0.1:5000`.

### Environment variables (optional overrides)

| Variable | Default | Purpose |
|---|---|---|
| `PORTAL_MODE` | `local` | Set to `cloud` to use Cloud Run portal instead of local HTTPS server |
| `PORTAL_HOST` | `127.0.0.1` | Override portal hostname — set to Cloud Run URL in cloud mode |
| `GOOGLE_CLOUD_PROJECT` | — | Required in cloud mode for Firestore authentication |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Path to GCP service account key (desktop side, cloud mode) |

For local development with no cloud configuration, no environment variables are needed. The application runs fully self-contained.

---

## Portal Deployment — Cloud Run

When QuMail sends a Level 3 email to a non-QuMail recipient, it generates a time-limited single-use HTTPS portal link. In `PORTAL_MODE=local`, this portal runs on `127.0.0.1:5001`. For production use accessible from any network, the portal is deployed to Google Cloud Run.

### What the portal deployment requires

- A GCP project with billing enabled
- Cloud Firestore database in **Native mode** (`asia-south1` recommended)
- TTL policies configured on `portal_sessions.expires_at` and `portal_rate_limits.expires_at`
- A dedicated service account with `roles/datastore.user` permission
- Docker installed locally for image build and push

### Cloud Run environment variables

```
PORTAL_MODE=cloud
PORTAL_HOST=<your-cloud-run-service-url>  # without https:// prefix
GOOGLE_CLOUD_PROJECT=<your-gcp-project-id>
```

### Session isolation guarantee

Every portal session is keyed by a 128-bit UUID. No collection-level queries exist in `portal_server.py` — every Firestore access is a direct document read or write by explicit UUID. The `_mark_consumed()` function uses a Firestore transaction with optimistic concurrency, guaranteeing that under concurrent access exactly one request receives the plaintext and all subsequent requests return 410.

### Rebuild and deploy

```bash
# Build
docker build --no-cache -f portal/Dockerfile \
  -t <region>-docker.pkg.dev/<project-id>/<repo>/qumail-portal:v1 .

# Push
docker push <region>-docker.pkg.dev/<project-id>/<repo>/qumail-portal:v1

# Deploy
gcloud run deploy qumail-portal \
  --image=<image-path> \
  --region=<region> \
  --service-account=<sa>@<project>.iam.gserviceaccount.com \
  --allow-unauthenticated \
  --min-instances=1 \
  --max-instances=10 \
  --memory=512Mi \
  --cpu=1 \
  --set-env-vars="PORTAL_MODE=cloud,GOOGLE_CLOUD_PROJECT=<project-id>" \
  --port=8080
```

---

## Project Status

| Feature | Status | Notes |
|---|---|---|
| Inbox load (Gmail) | ✅ Working | 80 messages in under 3 seconds |
| Inbox message click + decrypt | ✅ Working | Level 2 verified live |
| Level 1 OTP send | ✅ Verified | Padding fix applied for messages under 16 bytes |
| Level 1 OTP inbox decrypt | ✅ Verified | Full round-trip confirmed |
| Level 2 AES send + receive | ✅ Verified | Full round-trip including self-transfer |
| Level 3 ML-KEM send + portal | ✅ Working | Single-use portal enforced |
| Level 3 ML-KEM inbox decrypt | ✅ Verified | E2E verification complete |
| Non-QuMail recipient portal | ✅ Working | Automatic TQR downgrade to Level 3 |
| Cloud Run portal deployment | ✅ Live | Firestore session store, multi-instance isolation |
| SAE registry persistence | ✅ Fixed | Persists across virtual node restarts via JSON |
| OAuth token renewal | ✅ Working | Re-authenticate button in Settings |
| Compose field privacy | ✅ Fixed | Fields cleared on account switch |
| Encryption certificate output | ✅ Working | JSON + PDF per sent message |
| Portal replay protection | ✅ Working | Firestore transaction, consumed flag |
| Portal TTL expiry | ✅ Working | Firestore native TTL policy on expires_at |
| Yahoo send/receive | ⚠️ Partial | Custom PKCE flow — unverified end-to-end |
| Windows PyInstaller build | ❌ Pending | v2 deliverable |
| SMTP Subject encryption | ❌ Pending | Metadata leakage known — v2 roadmap |

**v1 complete as of March 2026. v2 planning in progress.**

---

## Codebase Structure

```
QuMail/
│
├── INSTRUCTIONS.md          AI agent rules. Read before every task.
├── ARCHITECTURE.md          Full module map, dependency flow, completion status.
├── CHANGELOG.md             Session-by-session record of all changes.
├── BUGS.md                  Out-of-scope issues logged during development.
├── DEFERRED.md              Alternative approaches and future version ideas.
├── README.md                This file.
├── requirements.txt         All Python dependencies — exact versions pinned.
│
├── main.py                  Entry point only. ~20 lines. No logic.
│
├── core/
│   ├── config.py            Single source of truth for all constants.
│   └── session.py           In-memory runtime state. PyQt6 signal-connected.
│
├── kme/
│   ├── virtual_node.py      Flask server — ETSI GS QKD 014 REST endpoints.
│   ├── kme_client.py        REST client for key requests. Only file that talks to KME.
│   └── key_models.py        QuantumKey and KeyRequest dataclasses.
│
├── crypto/
│   ├── tqr.py               TQR dispatcher — sole entry point into crypto layer.
│   ├── level1_otp.py        One-Time Pad using QKD-delivered key.
│   ├── level2_aes.py        AES-256-GCM seeded with QKD-delivered key.
│   └── level3_mlkem.py      ML-KEM-768 + AES-256-GCM hybrid (FIPS 203).
│
├── transport/
│   ├── smtp_sender.py       Sends encrypted payload via SMTP. No crypto calls.
│   ├── imap_receiver.py     Fetches and parses incoming mail via IMAP.
│   ├── oauth2_gmail.py      Gmail OAuth2 token acquisition and refresh.
│   ├── oauth2_yahoo.py      Yahoo OAuth2 PKCE flow.
│   └── recipient_check.py   Queries KME for recipient SAE ID. Returns bool + metadata.
│
├── mime/
│   ├── encapsulator.py      Wraps ciphertext in RFC 3156 multipart/encrypted.
│   └── decapsulator.py      Parses incoming QuMail MIME, extracts ciphertext + metadata.
│
├── portal/
│   ├── portal_server.py     Firestore-backed session store + HTTP handler.
│   ├── portal_crypto.py     Decryption bridge — isolation layer over crypto/tqr.py.
│   ├── cloud_entrypoint.py  Cloud Run entry point — plain HTTP on port 8080.
│   ├── Dockerfile           Cloud Run container — liboqs 0.15.0 pinned build.
│   └── templates/
│       └── portal.html      Self-contained portal page — no CDN dependencies.
│
├── certificates/
│   ├── cert_generator.py    Generates JSON cert per send session.
│   └── pdf_export.py        Converts JSON cert to PDF via fpdf2.
│
├── ui/
│   ├── main_window.py       App shell. Navigation. Loads child windows.
│   ├── compose_window.py    Compose UI. TQR level toggle. Orchestrates send.
│   ├── inbox_view.py        Inbox list and message viewer. Orchestrates decrypt.
│   ├── key_status_widget.py Reusable KME connection + key exchange status widget.
│   └── settings_window.py   OAuth2 setup, TQR default, KME endpoint config.
│
├── tests/
│   ├── test_kme.py
│   ├── test_crypto.py
│   ├── test_transport.py
│   ├── test_mime.py
│   ├── test_certificates.py
│   └── test_tqr_roundtrip.py    ✅ All 3 TQR levels pass E2E roundtrip
│
└── secrets/                 Gitignored. OAuth tokens, KME registry, Firestore key.
```

---

## Known Limitations

**SMTP header metadata:** Message body and attachments are fully encrypted and opaque to any relay. However, standard SMTP headers (To, From, Date) are transmitted in plaintext as required by the protocol. Traffic analysis can identify that a QuMail session occurred between two addresses even without decrypting the payload. Nested message encapsulation (Subject encryption) is planned for v2.

**liboqs version delta:** The Python bindings (`liboqs-python==0.14.1`) lag behind the C library (`0.15.0`). Both are functional together but produce a `UserWarning` at startup. Resolves when a compatible liboqs-python release is available.

**Single-user desktop only:** `core/session.py` is in-memory and single-user by design in v1. Multi-user support is a v2 architecture item.

**Virtual KME only:** The QKD key delivery uses a locally simulated ETSI GS QKD 014 Virtual Node. Live KME integration is the primary v2 engineering deliverable.

**Portal localhost-only without Cloud Run:** The insecure recipient portal runs on `127.0.0.1:5001` in local mode — accessible only on the sender's machine. Cloud Run deployment (see above) enables public access.

**In-memory KME key loss on restart:** The Virtual KME node (`kme/virtual_node.py`) stores all issued keys in an in-memory dictionary. If the application is restarted between sending and receiving a Level 1 or Level 2 message, all issued keys are lost and decryption will fail with a "Key not found" error. This is a v1 limitation of the simulated node. Full key persistence is planned for v2.

**Yahoo OAuth2 requires manual app registration:** Yahoo send and receive requires a registered Yahoo Developer App. You must set `QUMAIL_YAHOO_CLIENT_ID` and `QUMAIL_YAHOO_CLIENT_SECRET` as environment variables before the Yahoo OAuth2 flow can execute. Without them, connecting a Yahoo account will fail immediately at the auth step. Gmail works out of the box once `secrets/gmail_client_secret.json` is placed. Yahoo is not plug-and-play.

**`google-auth-oauthlib` upstream archived:** The `google-auth-oauthlib` library (used for the Gmail OAuth2 browser flow) was archived by Google in February 2026 and will no longer receive security patches. It is fully functional for v1. A maintained replacement will be evaluated before v2 ships.

---

## Roadmap

### v2 — Infrastructure Integration
- Live ETSI QKD 014 node connection (C-DOT / NQM Thematic Hub, IIT Madras)
- Windows PyInstaller single-executable packaging
- SMTP Subject line encryption via nested message encapsulation
- Yahoo OAuth2 hardening with off-the-shelf library
- Multi-user support with organisational key management dashboard
- Integration test suite expansion
- Linux packaging

### v3 — Platform Scale
- Android client
- ISRO SAQTI satellite QKD channel readiness
- NIC / MeitY government secure email infrastructure integration
- Chat and voice encryption extensions
- CERT-In certification pathway

---

## Acknowledgements

**ISRO Problem Statement PS 25179** — The foundational institutional mandate whose protocol specifications and infrastructure vision directly shaped QuMail's architecture. ISRO explicitly permits KME simulation for demonstration purposes and names ETSI GS QKD 014 as the target key delivery protocol.

**Open Quantum Safe project** — The `liboqs` library and Python bindings that power QuMail's Level 3 ML-KEM FIPS 203 implementation. [github.com/open-quantum-safe/liboqs](https://github.com/open-quantum-safe/liboqs)

**HackToon 1.0, AIKTC** — 2nd Runner Up. Thank you to the coordinators and the HackToon team for organising an exceptional platform for student builders.

---

*QuMail v1.0 — March 2026 | Team OblivionX*
