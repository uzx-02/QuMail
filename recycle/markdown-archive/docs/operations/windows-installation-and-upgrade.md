# QuMail M7 — Windows Installation, Upgrade & Maintenance Guide

**Milestone:** M7 — Module 1.6  
**Workstreams:** WS-06 & WS-07  
**Document:** Windows Installation and Upgrade Specification  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  
**Status:** Approved & Implemented  

---

## 1. Executive Overview

QuMail M7 delivers a conventional, reproducible Windows x64 installation and maintenance experience designed for both individual enterprise employees and corporate IT administrative deployments.

The installation architecture guarantees **Zero Cryptographic Friction** while strictly preserving all security boundaries and user data:
1. **Per-Machine & Per-User Support:** Installs to `C:\Program Files\QuMail` (administrative) or `%LOCALAPPDATA%\Programs\QuMail` (standard user without elevation).
2. **Safe Atomic Upgrades:** Binaries and dependencies are swapped atomically via temporary staging; if an upgrade is interrupted, automatic rollback restores the previous working version.
3. **Strict Vault Preservation Invariant:** User vaults, account configurations, post-quantum private keys, and email indices in `%LOCALAPPDATA%\QuMail\` are **NEVER** modified, overwritten, or silently deleted during installation, upgrade, or uninstallation.
4. **Zero Developer Path Dependencies:** Release bundles resolve native providers relative to the installed application root (`bin/`), completely decoupled from developer repositories, Cargo build trees, or Conda environments.

---

## 2. Directory Layout & Distribution Architecture

The standalone Windows x64 distribution bundle (`dist/QuMail/`) conforms to the following standardized layout:

```
<InstallRoot>/                  (e.g., C:\Program Files\QuMail or %LOCALAPPDATA%\Programs\QuMail)
├── QuMail.exe                  (Main application executable)
├── version.json                (Build metadata, provenance, Git commit SHA, timestamp)
├── install_manifest.json       (Installation record, target paths, upgrade history)
├── bin/
│   ├── qumail-m3-provider.exe  (Rust Release provider: Identity, DPAPI vault, Ed25519)
│   ├── qumail-m5-provider.exe  (Rust Release provider: ML-KEM-768, composite signing, MIME)
│   └── manifest.json           (Cryptographic SHA-256 digests and PE mitigation records)
├── resources/
│   └── qumail.default.json     (Default application configuration template)
├── policies/
│   ├── QuMail.admx             (Enterprise Group Policy administrative template)
│   └── en-US/QuMail.adml       (Language-specific GPO string table)
└── [Python & PyQt6 Runtime]    (Self-contained runtimes, Qt platform plugins, C-extensions)
```

### User Data & Vault Isolation
All user state is stored in per-user isolated directories outside the application installation folder:
- **Encrypted SQLite Vaults:** `%LOCALAPPDATA%\QuMail\vaults\`
- **Local Mailbox Index:** `%LOCALAPPDATA%\QuMail\index\`
- **Local Operational Logs:** `%LOCALAPPDATA%\QuMail\logs\`
- **Windows Credential Manager:** `QuMail:<email>` (OAuth tokens and master keys)

---

## 3. Installer Implementation: Inno Setup (`deploy/QuMailSetup.iss`)

QuMail provides a production-grade Inno Setup script supporting:
- 64-bit Windows execution (`ArchitecturesInstallIn64BitMode=x64compatible`).
- Administrative and non-administrative installations (`PrivilegesRequiredOverridesAllowed=dialog commandline`).
- Automatic application closure before upgrade (`CloseApplications=yes`).
- Start Menu and optional Desktop shortcuts.
- Registry registration under `HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\QuMail` (or `HKCU`).

### Silent Installation Switches (SCCM / Intune / Command Line)

| Switch | Purpose |
|---|---|
| `/VERYSILENT` | Suppresses all wizard windows and progress dialogs. |
| `/SUPPRESSMSGBOXES` | Suppresses message boxes, choosing safe default responses. |
| `/NORESTART` | Prevents the system from rebooting if a file was in use. |
| `/ALLUSERS` | Forces per-machine installation to `Program Files` (requires admin). |
| `/CURRENTUSER` | Forces per-user installation to `%LOCALAPPDATA%\Programs`. |
| `/DIR="C:\Path"` | Overrides the default installation directory. |

#### Example Administrative Command:
```powershell
QuMailSetup-1.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /ALLUSERS
```

---

## 4. Safe Upgrade and Downgrade Protection

### 4.1 Atomic Upgrade Workflow
1. The installer verifies the cryptographic integrity and PE mitigations of the candidate release bundle.
2. The running QuMail process is gracefully requested to shut down, closing background sync workers and flushing database WAL journals.
3. Candidate files are staged in `<InstallDir>.staging_<timestamp>`.
4. The existing `<InstallDir>` is renamed to `<InstallDir>.backup_<timestamp>`.
5. `<InstallDir>.staging` is renamed to `<InstallDir>`.
6. Upon successful launch verification, `<InstallDir>.backup` is safely purged. If any failure occurs, the backup is restored immediately.

### 4.2 Downgrade Protection Policy
- Candidate version semantic versioning (`major.minor.patch-prerelease`) is compared against the currently installed version using `core/update_manager.py:is_version_older`.
- Installing an older version over a newer version is **BLOCKED** by default with `DowngradeBlockedError` to prevent exploitation of known vulnerabilities in retired versions.
- Administrative downgrade override requires explicit authorization (`allow_downgrade=True`).

---

## 5. Uninstallation and Data Preservation Invariant

### 5.1 Default Behavior: User Data Retention
When an employee or IT administrator uninstalls QuMail:
- Application binaries, DLLs, shortcuts, and registry keys are removed.
- **The user's encrypted vault, private keys, contact certificates, and email cache are RETAINED.**
- If the employee reinstalls QuMail in the future, their encrypted mailbox and key history remain intact without data loss.

### 5.2 Explicit User Data Purge
During interactive uninstallation, the user is presented with a clear dialog:
> *"Do you want to retain your personal encrypted vaults, post-quantum private keys, and email index?*  
> *Select YES to preserve your encrypted keys and mail data (Recommended to prevent data loss).*  
> *Select NO only if you want to permanently delete all local keys and vaults."*

If the user selects NO, a second critical confirmation warning appears.  
In automated / programmatic environments, data purging requires the explicit security confirmation token:
```python
installer.uninstall(purge_user_data=True, confirm_token="CONFIRM_DELETE_KEYS")
```
Uninstallation without the exact token aborts with `InstallerError` before deleting any user data.
