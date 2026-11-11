# Windows Production Build & Inno Setup Packaging Architecture

## 1. Overview

This document specifies the release build, layout verification, and packaging pipeline for the QuMail 1.0 desktop client on Windows 11 x64.

The distribution workflow compiles:
1. **Frontend:** React 19 single-page application compiled via Vite and TypeScript into `frontend/dist`.
2. **Native Providers:** Rust post-quantum cryptographic helpers (`qumail-m3-provider.exe` and `qumail-m5-provider.exe`) with authenticated `manifest.json`.
3. **Application Shell:** Python 3.12 + WebView2 runtime packaged via PyInstaller into `dist/QuMail-App`.
4. **Installer:** Inno Setup 6 compiler configuration (`deploy/QuMailSetup.iss`) targeting `dist/QuMail-App`.

---

## 2. Directory Layout Specification

The production application layout generated under `dist/QuMail-App` is structured as follows:

```
dist/QuMail-App/
├── QuMail.exe                  # Main application executable (launcher)
├── version.json                # Build provenance and version metadata
├── bin/                        # Verified native cryptographic helpers
│   ├── manifest.json           # SHA256 integrity manifest
│   ├── qumail-m3-provider.exe  # M3 identity and vault provider
│   └── qumail-m5-provider.exe  # M5 OpenPGP post-quantum seal/open provider
├── resources/                  # Default configuration and policy templates
│   └── qumail.default.json     # Initial configuration template
├── _internal/                  # PyInstaller shared libraries and runtimes
│   ├── python312.dll
│   ├── webview/
│   ├── cryptography/
│   └── ...
└── frontend/dist/              # Compiled React 19 UI assets
    ├── index.html
    └── assets/
        ├── index-*.css
        └── index-*.js
```

### 2.1 Verification Gate
Every build is programmatically validated against `core/packaging.py::verify_bundle_layout(bundle_root)`:
- `version.json` exists and parses cleanly.
- `bin/manifest.json` SHA256 digests match `qumail-m3-provider.exe` and `qumail-m5-provider.exe`.
- Native provider executables pass Windows PE mitigation checks (ASLR, DEP, Guard CF).
- `resources/qumail.default.json` exists with required configuration defaults.

---

## 3. PE Security Mitigations & Binary Hardening

Both native Rust helpers (`qumail-m3-provider.exe` and `qumail-m5-provider.exe`) are compiled with full Microsoft Windows security mitigations and validated via `core/packaging.py::inspect_pe_security_characteristics()`:

| Mitigation Flag | Bitmask | Required State | Description |
|---|---|---|---|
| **DynamicBase (ASLR)** | `0x0040` | `True` | Address Space Layout Randomization |
| **HighEntropyVA (64-bit ASLR)** | `0x0020` | `True` | 64-bit high-entropy address space |
| **NXCompat (DEP)** | `0x0100` | `True` | Data Execution Prevention / No-Execute |
| **GuardCF** | `0x4000` | `True` | Control Flow Guard protection |
| **TerminalServerAware** | `0x8000` | `True` | Terminal Services compatibility |

---

## 4. Inno Setup 6 Installer Configuration

The authoritative installer script is located at `deploy/QuMailSetup.iss`:
- **Target Source:** `#define SourceDistDir "..\dist\QuMail-App"`
- **Architecture Requirements:** `ArchitecturesInstallIn64BitMode=x64compatible`
- **Output:** `dist/Installer/QuMailSetup-1.0.0.exe`
- **Installation Modes:**
  - Administrative (Per-Machine): Installed to `C:\Program Files\QuMail`
  - Non-Administrative (Per-User): Installed to `%LOCALAPPDATA%\Programs\QuMail`
- **Data Protection Guarantee:**
  - Custom Pascal script in `CurUninstallStepChanged()` checks for existing vaults under `%LOCALAPPDATA%\QuMail`.
  - Prompts the user with default `MB_YESNO or MB_DEFBUTTON1` to preserve personal encrypted vaults and private keys upon uninstallation.

---

## 5. Build Execution Instructions

To assemble the complete Windows distribution from a clean repository checkout:

### Step 1: Build React 19 Frontend
```powershell
npm --prefix frontend run build
```

### Step 2: Build PyInstaller Desktop Executable
```powershell
.venv-m1-clean\Scripts\pyinstaller.exe --noconfirm QuMail-Modern.spec
```

### Step 3: Validate Bundle Integrity
```powershell
.venv-m1-clean\Scripts\python.exe -c "from pathlib import Path; from core.packaging import verify_bundle_layout; print(verify_bundle_layout(Path('dist/QuMail-App')))"
```

### Step 4: Compile Inno Setup Installer
```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" deploy\QuMailSetup.iss
```

---

## 6. Secrets Hygiene Audit

The build output has been audited against secret leakage:
- Zero OAuth refresh tokens, access tokens, or token cache files are bundled.
- Zero client secret JSON files are packaged in `dist/`.
- Zero user SQLite vaults (`*.sqlite`, `*.db`) are copied into distributions.
- Validated via automated test `tests/test_ws01_bootstrap_hygiene.py::test_privacy_filter_*`.
