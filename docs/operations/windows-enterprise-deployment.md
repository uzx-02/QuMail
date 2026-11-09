# QuMail M7 — Windows Enterprise Deployment & Group Policy Guide

**Milestone:** M7 — Module 1.6  
**Workstreams:** WS-06 & WS-07  
**Document:** Windows Enterprise Deployment Specification  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  
**Status:** Approved & Implemented  

---

## 1. Enterprise Architecture Overview

QuMail M7 provides comprehensive, policy-driven fleet management for Windows enterprise endpoints across Microsoft Active Directory, Group Policy (GPO), Microsoft Intune, and SCCM/MECM.

### Core Principles
1. **Machine-Level Policy Authority:** Administrative policies are anchored in `HKEY_LOCAL_MACHINE\SOFTWARE\Policies\QuMail`, protected by standard Windows administrator Access Control Lists (ACLs). Non-elevated standard users cannot tamper with or override corporate policy.
2. **Cryptographically Authenticated Trust Anchors:** Enterprise trust anchors are enforced by explicit certificate fingerprints (SHA-256), rejecting arbitrary unverified strings or uncertified domain labels.
3. **Zero Cryptographic Friction for Employees:** Endpoints provisioned via corporate policy configure approved corporate domains, trust anchors, and security rules automatically on first launch.

---

## 2. Group Policy Objects (GPO) & Administrative Templates

QuMail ships with standard administrative templates compatible with the Windows Group Policy Management Console (`gpmc.msc`):

- **Template Schema:** [`deploy/QuMail.admx`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/deploy/QuMail.admx)
- **Language Resources:** [`deploy/QuMail.adml`](file:///C:/Users/uzx/Desktop/Aavishkar-26/QuMail/deploy/QuMail.adml) (English US)

### Central Store Installation
To deploy policies across an Active Directory forest, copy the templates to the Domain Controller's Central Store:
```powershell
# Copy ADMX to Domain Policy Definitions
Copy-Item deploy/QuMail.admx \\<Domain>\sysvol\<Domain>\Policies\PolicyDefinitions\
# Copy ADML to Language Subfolder
Copy-Item deploy/QuMail.adml \\<Domain>\sysvol\<Domain>\Policies\PolicyDefinitions\en-US\
```

---

## 3. Supported Enterprise Policy Controls

| Policy Name | Registry Value | Type | Default | Description |
|---|---|:---:|:---:|---|
| **Prevent External Accounts** | `block_external_accounts` | `REG_DWORD` | `0` | When enabled (`1`), employees cannot add personal or third-party accounts. |
| **Enforce Strict Encryption** | `enforce_strict_encryption` | `REG_DWORD` | `1` | Prohibits transmitting unencrypted or unauthenticated emails to unverified recipients. |
| **Disable Legacy Simulator** | `disable_legacy_simulator` | `REG_DWORD` | `1` | Strictly blocks launching the legacy research prototype simulator via `--legacy-simulator`. |
| **Update Channel** | `update_channel` | `REG_SZ` | `"Production"` | Selects update stream (`"Production"`, `"LTS"`, or `"Beta"`). |
| **Update Server URL** | `update_server_url` | `REG_SZ` | Corporate URL | Base URL for fetching enterprise-approved signed update packages. |
| **Approved Domains** | `allowed_domains` | `REG_SZ` (JSON) | `[]` | JSON array of approved corporate email domains (e.g. `["corp.example.com"]`). |
| **Managed Trust Anchors** | `managed_trust_anchors` | `REG_SZ` (JSON) | `{}` | JSON map of domain to corporate CA certificate SHA-256 fingerprint. |
| **Logging Severity Level** | `log_level` | `REG_SZ` | `"INFO"` | Centralized logging verbosity (`"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`). |
| **Support Diagnostics Export** | `allow_diagnostics_export` | `REG_DWORD` | `1` | Controls whether users may export privacy-safe operational support bundles. |
| **Remote Telemetry** | `allow_remote_telemetry` | `REG_DWORD` | `0` | Prohibits automated diagnostic reporting (default False for zero data leakage). |

---

## 4. Policy Enforcement & Trust Anchor Verification

### 4.1 Administrator Dominance Invariant
The policy reader (`core/enterprise_policy.py`) evaluates policies in strict priority order:
1. `HKLM\SOFTWARE\Policies\QuMail` (Group Policy machine setting - cannot be overridden by user).
2. `%PROGRAMDATA%\QuMail\policies.json` (Local administrative machine configuration file).
3. Hardcoded safe production baseline.

User-level configuration stored in `HKEY_CURRENT_USER` or `%LOCALAPPDATA%` is **strictly ignored** for any setting defined by machine policy.

### 4.2 Cryptographic Trust Anchor Validation
When corporate domains are specified under `managed_trust_anchors`, the fingerprint is validated at configuration time:
- Fingerprints must be exactly 64 hexadecimal characters representing a SHA-256 digest.
- Malformed or invalid strings are rejected and logged with warnings.
- During recipient trust evaluation in `ui/compose_dialog.py` and `mailbox_client/workflows.py`, correspondents presenting certificates matching the provisioned fingerprint are certified as `SECURE` without requiring manual employee fingerprint comparisons.

---

## 5. Automated Deployment Scripts

### 5.1 Microsoft Intune / SCCM Deployment Command
```powershell
# Silent per-machine installation with suppression of restart
Start-Process -FilePath "QuMailSetup-1.0.0.exe" `
    -ArgumentList "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /ALLUSERS" `
    -Wait -NoNewWindow
```

### 5.2 Direct Registry Provisioning via PowerShell
```powershell
$policyKey = "HKLM:\SOFTWARE\Policies\QuMail"
if (!(Test-Path $policyKey)) { New-Item -Path $policyKey -Force | Out-Null }

Set-ItemProperty -Path $policyKey -Name "block_external_accounts" -Value 1 -Type DWord
Set-ItemProperty -Path $policyKey -Name "enforce_strict_encryption" -Value 1 -Type DWord
Set-ItemProperty -Path $policyKey -Name "disable_legacy_simulator" -Value 1 -Type DWord
Set-ItemProperty -Path $policyKey -Name "update_channel" -Value "Production" -Type String
Set-ItemProperty -Path $policyKey -Name "allowed_domains" -Value '["corp.example.com", "subsidiary.example.com"]' -Type String
Set-ItemProperty -Path $policyKey -Name "managed_trust_anchors" -Value '{"corp.example.com": "5ceb47b86bec9b3b8d6e666e718947391c59f8763be1347b0e3c2a692e022241"}' -Type String
```
