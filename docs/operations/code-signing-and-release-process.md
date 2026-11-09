# QuMail M7 — Code Signing, Authenticode & Release Verification Process

**Milestone:** M7 — Module 1.6  
**Workstreams:** WS-06 & WS-07  
**Document:** Code Signing and Release Process Specification  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  
**Status:** Approved & Implemented  

---

## 1. Executive Summary

QuMail enforces a strict cryptographic code signing policy for production software distribution on Windows endpoints.

Digital signatures verify binary authenticity, establish publisher identity, prevent tampering, and satisfy Windows SmartScreen and enterprise endpoint detection and response (EDR) trust requirements.

### Release Mode vs Development Mode
- **Production Release Mode (`strict_release=True`):** Unsigned executables, unverified digests, or missing Authenticode signatures are **strictly rejected** by the packaging and verification pipeline.
- **Development Mode (`strict_release=False`):** Local developer builds and CI dry-runs permit unsigned artifacts while recording full audit manifests, clearly flagging binaries as `DEVELOPMENT_UNSIGNED` without requiring commercial signing certificates during active development.

---

## 2. Authenticode Specification and Shipped Binaries

All executable artifacts distributed to end-user workstations must carry an Authenticode digital signature with an RFC 3161 timestamp:

1. **Main Application Executable:** `QuMail.exe`
2. **Native Cryptographic Providers:** `bin/qumail-m3-provider.exe`, `bin/qumail-m5-provider.exe`
3. **Windows Installer Package:** `QuMailSetup-<version>.exe`
4. **Update Archive Payloads:** All `.exe` and `.dll` payloads inside `.qupkg` update archives.

### Signature Structure
Signatures conform to Microsoft Authenticode PKCS#7 / CMS format stored inside the PE Optional Header Security Directory (`IMAGE_DIRECTORY_ENTRY_SECURITY`):
- Digest Algorithm: `SHA-256`
- Signature Algorithm: `RSA-3072+` or `ECDSA P-256/P-384`
- Timestamp Protocol: RFC 3161 counter-signature (`http://timestamp.digicert.com`)

---

## 3. PE Security Characteristics & Binary Mitigations

In addition to digital signatures, shipped native binaries enforce compiler-level Windows exploit mitigations. Verification via `core/packaging.py:inspect_pe_security_characteristics` confirms:

| Mitigation Property | Mask / Flag | Status | Purpose |
|---|:---:|:---:|---|
| **64-bit High Entropy VA** | `0x0020` | **ENABLED** | Expands virtual address space randomization to 64-bit entropy. |
| **Dynamic Base (ASLR)** | `0x0040` | **ENABLED** | Randomizes executable and module base load addresses on startup. |
| **NX Compat (DEP)** | `0x0100` | **ENABLED** | Prevents execution of data pages (Data Execution Prevention). |
| **Control Flow Guard (CFG)** | `0x4000` | **ENABLED** | Validates indirect call targets to prevent Return-Oriented Programming (ROP). |
| **Terminal Server Aware** | `0x8000` | **ENABLED** | Multi-session Windows terminal server compatibility. |
| **Combined Flags** | `0xC160` | **VERIFIED** | Full security hardening characteristics for Windows x64. |

---

## 4. Production Signing Workflow

### 4.1 Prerequisites
- Commercial Code Signing Certificate (EV or Standard) issued by an authorized CA (DigiCert, Sectigo, GlobalSign).
- Hardware Security Module (HSM), FIPS 140-2 Level 2 USB token (e.g. YubiKey 5 FIPS), or Azure Key Vault Managed HSM.
- Microsoft Windows SDK `signtool.exe` (installed with Windows SDK 10.0.22621.0+).

### 4.2 Automated Signing Invocation (`tools/sign_release.ps1`)
```powershell
param(
    [Parameter(Mandatory=$true)][string]$DistDir,
    [Parameter(Mandatory=$false)][string]$CertThumbprint,
    [Parameter(Mandatory=$false)][string]$TimestampServer = "http://timestamp.digicert.com"
)

$signtool = "C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe"
$targets = Get-ChildItem -Path $DistDir -Recurse -Include *.exe, *.dll

foreach ($target in $targets) {
    Write-Host "Signing $($target.FullName)..." -ForegroundColor Cyan
    & $signtool sign /fd SHA256 /tr $TimestampServer /td SHA256 /sha1 $CertThumbprint $target.FullName
    if ($LASTEXITCODE -ne 0) { throw "Signing failed for $($target.FullName)" }
}
```

---

## 5. Verification Commands

### 5.1 Verification via Microsoft SignTool
```powershell
signtool verify /pa /v dist\QuMail\QuMail.exe
signtool verify /pa /v dist\QuMail\bin\qumail-m5-provider.exe
```

### 5.2 Verification via PowerShell
```powershell
Get-AuthenticodeSignature dist\QuMail\QuMail.exe | Format-List
```

### 5.3 Automated Python Verification
```powershell
python -c "from core.code_signing import inspect_binary_authenticode; from pathlib import Path; print(inspect_binary_authenticode(Path('dist/QuMail/QuMail.exe')))"
```

---

## 6. Key Management, Renewal & Revocation

1. **Zero Secret Storage in Repository:** Private keys, `.pfx` certificates, and hardware token PINs are strictly prohibited from Git tracking. All signing must occur on isolated, hardened build agents or through secure cloud HSM proxies.
2. **Annual Certificate Renewal:** Code signing certificates must be renewed 30 days prior to expiration. Timestamped signatures remain valid indefinitely even after the signing certificate expires.
3. **Revocation Response:** If a signing key is suspected of compromise:
   - Contact the issuing CA immediately to revoke the certificate with an explicit revocation timestamp.
   - Update `UpdateManager` enterprise trust anchors to reject update packages signed by the revoked key.
   - Issue an emergency signed update package signed with the replacement key.
