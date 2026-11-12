# QuMail — Post-Quantum Secure Email Client

QuMail is a post-quantum secure desktop email client for Windows 10/11 x64, engineered to protect communications against "Harvest Now, Decrypt Later" (HNDL) quantum threats.

---

## Key Capabilities

1. **Genuine Post-Quantum Cryptography (NIST FIPS Standards)**
   - **ML-KEM-768 (FIPS 203)** for quantum-resistant key encapsulation.
   - **ML-DSA-65 (FIPS 204)** for quantum-resistant digital signatures.
   - **AES-256-GCM** authenticated payload encryption with ephemeral session keys.
   - Cryptographic primitives executed via compiled native 64-bit Rust provider binaries with hardware-isolated execution boundaries.

2. **Cloudflare Edge Directory & Multi-Device Sealing**
   - **Blind Indexed Identity**: Normalized email addresses are protected via HMAC-SHA256 with a hardware pepper; zero plaintext email addresses or identity correlations exist in the directory database.
   - **Multi-Device Support**: Messages are automatically encapsulated for all registered active devices belonging to the recipient, as well as the sender's own device for verified Sent folder records.
   - **Direct Google ID-Token Verification**: Instant cryptographic registration using authenticated Google OIDC ID tokens.

3. **Secure Web Link Portal (External Communications)**
   - **Zero-Knowledge Gateway**: Cloudflare Worker + D1 ephemeral portal for communicating securely with recipients who do not yet run QuMail.
   - **URL Fragment Confidentiality**: Cryptographic key fragments (`#key=...`) remain strictly on the client side and are never transmitted to Cloudflare or external networks.
   - **Brevo OTP Challenge**: Recipient identity is verified via an ephemeral 6-digit email passcode before payload release.
   - **Single-Use Burn & Strict CSP**: Links automatically burn after decryption or expiration, enforced by strict Content Security Policies.

4. **Modern, Pure-Python Desktop Architecture**
   - **React 19 + TypeScript Frontend**: Clean, responsive email interface running on Microsoft Edge WebView2 (`pywebview`).
   - **Zero Legacy Bloat**: Completely independent of Qt / PyQt6.
   - **Persistent DPAPI Vault**: Local SQLite key vault secured by Windows Data Protection API (DPAPI). Keys persist cleanly across sign-outs and restarts.

---

## Repository Structure

```
QuMail/
├── bin/                        # Verified 64-bit Rust cryptographic provider binaries & manifest
│   ├── qumail-vault-provider.exe  # DPAPI vault & keypair generation
│   ├── qumail-crypto-provider.exe # ML-KEM-768 / ML-DSA-65 message sealing & opening
│   └── manifest.json           # SHA-256 integrity hashes & security metadata
├── cloud_directory/            # Cloudflare Worker & D1 Database backend
│   ├── src/index.ts            # Blind-indexed directory, Brevo OTP & WebLink engine
│   └── wrangler.toml           # Worker deployment configuration
├── core/                       # Python domain models, vault services & crypto envelope
├── frontend/                   # Modern React 19 + TypeScript + Vite user interface
│   ├── src/                    # Components, state models, and JavaScript bridge hooks
│   └── dist/                   # Bundled production frontend assets
├── transport/                  # IMAP, SMTP, and OAuth2 transport drivers
├── tests/                      # Automated test suite
├── launch_react_desktop.py     # Desktop runtime, IPC bridge, and crypto workflow orchestration
├── main.py                     # Primary desktop entrypoint
├── Launch-QuMail.ps1           # Production launcher script
└── QuMail.spec                 # Windows PyInstaller bundling specification
```

---

## Quick Start

### Prerequisites
- **Operating System:** Windows 10 / 11 (64-bit x64)
- **Python:** 3.12 (64-bit)
- **Node.js:** 20+ (for building the React frontend)
- **Microsoft Edge WebView2 Runtime** (pre-installed on Windows 10/11)

### Building from Source

1. **Install Python Dependencies:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Build Frontend Bundle:**
   ```powershell
   cd frontend
   npm install
   npm run build
   cd ..
   ```

3. **Compile Windows Application (.exe):**
   ```powershell
   pyinstaller QuMail.spec --noconfirm
   ```

4. **Launch Application:**
   ```powershell
   .\Launch-QuMail.ps1
   # Or run the compiled executable directly:
   .\dist\QuMail-App\QuMail.exe
   ```

---

## Security Architecture

- **Zero-Trust Network Model**: Communications require explicit Post-Quantum verification. If a recipient is not enrolled in the Cloud Directory, Maximum Security mode fails closed and guides the user to the Secure Web Link portal.
- **Strict Memory Zeroization**: Plaintext payloads and private subkeys are wiped from memory immediately after encryption/decryption cycles.
- **Windows DPAPI Vault**: Root identities and subkeys are stored locally in `%LOCALAPPDATA%\QuMail\vault.sqlite`, protected by hardware-backed OS DPAPI keys.
