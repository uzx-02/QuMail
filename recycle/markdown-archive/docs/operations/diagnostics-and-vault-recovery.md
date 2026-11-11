# QuMail M7 — Diagnostics, Privacy Redaction & Vault Recovery Guide

**Milestone:** M7 — Module 1.6  
**Workstreams:** WS-06 & WS-07  
**Document:** Diagnostics and Vault Recovery Specification  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  
**Status:** Approved & Implemented  

---

## 1. Operational Support Diagnostics

QuMail provides a privacy-preserving diagnostic collection framework (`core/diagnostics.py`) designed to assist IT helpdesks and enterprise support engineers in diagnosing workstation issues without compromising employee privacy or confidentiality.

### 1.1 Strict Zero-Leakage Guarantee
The diagnostic collector enforces automated redaction and structural isolation. A generated diagnostic snapshot **NEVER** contains:
- Email message bodies, subject lines, or snippets
- Attachment filenames, metadata, or file payloads
- Passwords, OAuth tokens, or authorization headers
- Post-quantum private keys or symmetric session keys
- Windows DPAPI master key blobs or database encryption keys
- Personal contact lists or correspondents' email addresses

### 1.2 Collected Non-Sensitive Diagnostics
- **Client Metadata:** QuMail version, build timestamp, Git commit SHA, application directory.
- **Environment:** Windows version, OS build, system architecture, Python/PyQt runtime versions.
- **Native Providers:** Provider paths, file sizes, SHA-256 digests, and verified PE mitigations (`0xc160`).
- **Enterprise Policy:** Managed state, policy source (`REGISTRY_HKLM`), active update channel, allowed domain count, log level.
- **Vault Status:** Database file presence and size in bytes (zero secret keys or account data).
- **Mailbox Sync:** Current state (`Idle`, `Synchronizing…`, `Reconnecting…`, `Offline`).
- **Outbox Spool:** Total queue count, count by delivery state (`ACCEPTED`, `DRAFT`, `UNKNOWN`).

### 1.3 User-Controlled Export
Diagnostics are **never** transmitted silently or automatically over the network. Export is initiated strictly through explicit user or administrative action:
1. **Interactive UI:** Open Settings (`⚙️`) $\rightarrow$ Security tab $\rightarrow$ Click `📋 Export Support Diagnostics (Privacy-Safe)` $\rightarrow$ Save JSON bundle.
2. **Command Line:** Run `QuMail.exe --export-diagnostics C:\Path\diagnostics.json`.

---

## 2. Vault Architecture & Credential Protection Boundaries

### 2.1 Cryptographic Storage Architecture
- **Vault Database:** Stored at `%LOCALAPPDATA%\QuMail\vaults\account.sqlite` using SQLite WAL mode.
- **Key Derivation & DPAPI:** Master cryptographic keys protecting the local database are sealed using the Windows Data Protection API (DPAPI) via Win32 `CryptProtectData` and stored in Windows Credential Manager (`CredWriteW`) under target `QuMail:<email>`.
- **Account Context Isolation:** Each employee account maintains its own distinct cryptographic lease and transaction boundary (`experiments/m4/model.py:Lease`).

### 2.2 Realistic Process Memory Limitations
While QuMail zeroizes decrypted buffers where possible and minimizes the lifetime of sensitive secrets, standard Python memory management does not provide kernel-level memory locking (`mlock`) across all runtime allocations. Administrators must be aware that:
- Core dumps or deep hibernation files may capture transient heap state.
- Host workstations must enforce endpoint security (BitLocker Full Disk Encryption, Windows Defender Credential Guard) to protect process memory from unauthorized local administrators.

---

## 3. DPAPI Profile Loss & Disaster Recovery Limitations

### 3.1 Understanding DPAPI Boundaries
Windows DPAPI derives encryption keys from the logged-in user's Windows credentials and domain SID.  
**Critical Recovery Limitation:**  
If a user's Windows profile is deleted, corrupted, or if an administrator performs a hard, uncoordinated Windows password reset that desynchronizes the DPAPI master key, the local vault's DPAPI-wrapped keys become mathematically unrecoverable from that Windows user account.

### 3.2 Vault Disaster Recovery Workflow
To recover from device failure, laptop loss, or corrupted Windows user profiles:
1. **Account Backup Package:** QuMail generates an encrypted, armored backup secret during initial account setup.
2. **Restoration on New Workstation:**
   - Install QuMail on the replacement workstation.
   - Launch QuMail and select `Import Existing Vault / Restore from Backup`.
   - Provide the armored backup secret and account passphrase.
   - QuMail derives the root key, creates a new local SQLite vault sealed with the new machine's DPAPI context, and restores account identity.
3. **No-Overwrite Invariant:**
   - The restoration wizard **never silently replaces** an existing vault file if one is already present.
   - If an existing vault is detected at the target path, QuMail requires the user to select an alternate path or explicitly archive the legacy vault first.
