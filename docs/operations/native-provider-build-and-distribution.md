# QuMail Native Provider Build & Distribution Guide
## Compilation, Exploit Mitigations, Manifest Verification & Runtime Resolution

**Milestone:** M7 — Module 1.6  
**Document:** Operations Guide — Native Cryptographic Engine  
**Author:** Antigravity (Implementation Engineer)  
**Reviewer:** ChatGPT (Technical Lead & Security Architect)  
**Project Owner:** Mohammed Uzair Shaikh  
**Date:** 2026-11-09  

---

## 1. Architecture and Native Engine Roles

QuMail utilizes two high-performance, memory-safe native Rust helper executables to perform cryptographic and vault operations without compromising execution speed or exposing cryptographic primitives to Python runtime overhead:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            QuMail Python Runtime                            │
│  (UI / MailboxWindow / IdentitySettings / Inbound Service / Outbox Engine)  │
└───────────────────────┬─────────────────────────────┬───────────────────────┘
                        │ Subprocess IPC              │ Subprocess IPC
                        ▼ (JSON / Stdin / Stdout)     ▼ (JSON / Stdin / Stdout)
┌──────────────────────────────────────────┐ ┌──────────────────────────────────────────┐
│          qumail-m3-provider.exe          │ │          qumail-m5-provider.exe          │
│  * Cryptographic identity generation     │ │  * RFC 3156 / RFC 9788 OpenPGP-PQ MIME │
│  * Master root & subkey lifecycle        │ │  * Composite Ed25519 signing           │
│  * Self-certifications & binding sigs    │ │  * Hybrid post-quantum key encapsulation│
│  * Windows DPAPI master key storage      │ │  * OpenPGP decryption & signature verify│
│  * AES-256-GCM vault database crypto     │ │  * Armor parsing & stream hygiene       │
└──────────────────────────────────────────┘ └──────────────────────────────────────────┘
```

Both providers operate strictly via standard input/output pipes using bounded, schema-validated JSON payloads. They run as unprivileged user-mode helper processes.

---

## 2. Toolchain Prerequisites

To compile the native provider binaries on Windows:

1. **Rust Toolchain:**
   * Rust `rustc` and `cargo` 1.80+ (or current stable/nightly).
   * Host target: `x86_64-pc-windows-msvc`.
   * Check installation:
     ```powershell
     rustc --version
     cargo --version
     ```
2. **Microsoft C++ Build Tools:**
   * Microsoft Visual Studio 2022 Build Tools (or Visual Studio Community/Professional).
   * Workload: "Desktop development with C++" (specifically MSVC v143 x64/x86 build tools and Windows 10/11 SDK).
   * Required for MSVC linker (`link.exe`) and Control Flow Guard instrumentation.

---

## 3. Exploit Mitigations and Hardened Compilation

Enterprise deployment requires all native executables to enforce modern Windows platform exploit defenses. Compilation must not use unhardened debug configurations.

### 3.1 Required PE Mitigation Flags

Every compiled provider binary must exhibit the following PE header attributes:

| Mitigation | Header Flag | Hex Mask | Description |
|---|---|:---:|---|
| **64-bit High Entropy ASLR** | `IMAGE_DLLCHARACTERISTICS_HIGH_ENTROPY_VA` | `0x0020` | Allows 64-bit address space layout randomization across 8 TB virtual space. |
| **Dynamic Base (ASLR)** | `IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE` | `0x0040` | Binary can be rebased at load time to randomize memory segments. |
| **DEP / NX Compatibility** | `IMAGE_DLLCHARACTERISTICS_NX_COMPAT` | `0x0100` | Enforces hardware Data Execution Prevention (marks stack/heap non-executable). |
| **Control Flow Guard (CFG)** | `IMAGE_DLLCHARACTERISTICS_GUARD_CF` | `0x4000` | Microsoft Exploit Guard mitigation verifying indirect call target validity. |
| **Terminal Server Aware** | `IMAGE_DLLCHARACTERISTICS_TERMINAL_SERVER_AWARE` | `0x8000` | Optimized for Windows Terminal Services / Multi-user environments. |

Combining these flags yields the canonical MSVC hardened DllCharacteristics mask: `0xc160`.

### 3.2 Compilation Command

To compile with full optimizations and Control Flow Guard enabled:

```powershell
$env:RUSTFLAGS = "-C control-flow-guard"
cargo build --manifest-path experiments/m2/Cargo.toml --release
```

---

## 4. Automated Build Script (`tools/build_providers.ps1`)

An automated PowerShell build script is provided in the repository root. It automates compilation, verification, staging, and manifest generation:

```powershell
powershell -ExecutionPolicy Bypass -File tools/build_providers.ps1
```

### Script Execution Flow:
1. Validates that `cargo` and MSVC toolchains are available.
2. Sets `$env:RUSTFLAGS = "-C control-flow-guard"`.
3. Invokes `cargo build --manifest-path experiments/m2/Cargo.toml --release`.
4. Copies `qumail-m3-provider.exe` and `qumail-m5-provider.exe` into `bin/`.
5. Reads the PE header of each binary and validates `DllCharacteristics == 0xc160`.
6. Calculates the SHA-256 digest of each binary.
7. Writes the comprehensive metadata manifest to `bin/manifest.json`.

---

## 5. Distribution Layout & Version Control Hygiene

### 5.1 Repository Directory Structure

```
QuMail/
├── bin/
│   ├── .gitkeep                 # Tracked in Git
│   ├── manifest.json            # Tracked in Git (cryptographic provenance)
│   ├── qumail-m3-provider.exe   # IGNORED in Git (.gitignore)
│   └── qumail-m5-provider.exe   # IGNORED in Git (.gitignore)
├── core/
│   └── provider_resolver.py     # Runtime dynamic path resolver & PE inspector
├── tools/
│   └── build_providers.ps1      # PowerShell build automation script
```

### 5.2 Version Control Policy
* **Never commit binary `.exe` files into Git.** The repository `.gitignore` explicitly filters `*.exe` and `bin/*.exe`.
* **Track the manifest:** `bin/manifest.json` is committed to version control. It establishes the authoritative cryptographic hash and mitigation benchmark for build reproducibility.

---

## 6. Manifest Schema (`bin/manifest.json`)

The generated manifest provides runtime verification data:

```json
{
  "schema_version": "1.0",
  "generated_utc": "2026-11-09T02:58:44.058094+00:00",
  "compiler": "rustc 1.99.0 / cargo 1.99.0",
  "toolchain": "nightly-x86_64-pc-windows-msvc",
  "crypto_libraries": {
    "sequoia_openpgp": "2.4.1",
    "openssl": "3.5.9",
    "rpgp": "0.21.0"
  },
  "build_profile": "release",
  "rustflags": "-C control-flow-guard",
  "providers": {
    "qumail-m3-provider": {
      "binary": "qumail-m3-provider.exe",
      "version": "0.1.0",
      "size_bytes": 8381440,
      "sha256": "4e5eebe6f3d268d012b057934a9f47c6482158e7bd0e3e8733082388d6b79695",
      "pe_mitigations": {
        "high_entropy_va_64bit_aslr": true,
        "dynamic_base_aslr": true,
        "nx_compat_dep": true,
        "guard_cf_control_flow_guard": true,
        "terminal_server_aware": true,
        "dll_characteristics_hex": "0xc160"
      }
    },
    "qumail-m5-provider": {
      "binary": "qumail-m5-provider.exe",
      "version": "0.1.0",
      "size_bytes": 10672640,
      "sha256": "23ac6a50174ef8f5504c549a9f3b515153ffbff62f946bd518ca6e3603005c6b",
      "pe_mitigations": {
        "high_entropy_va_64bit_aslr": true,
        "dynamic_base_aslr": true,
        "nx_compat_dep": true,
        "guard_cf_control_flow_guard": true,
        "terminal_server_aware": true,
        "dll_characteristics_hex": "0xc160"
      }
    }
  }
}
```

---

## 7. Runtime Resolution & Overrides (`core/provider_resolver.py`)

At runtime, the Python application resolves the native provider path via `core.provider_resolver.resolve_provider(name)`.

### 7.1 Resolution Hierarchy

1. **Environment Variable Override:**
   * `QUMAIL_PROVIDER_PATH`: Generic override for all providers.
   * `QUMAIL_M3_PROVIDER_PATH`: Specific override for `qumail-m3-provider.exe`.
   * `QUMAIL_M5_PROVIDER_PATH`: Specific override for `qumail-m5-provider.exe`.
   *(If set, the resolver checks the path immediately. If the path does not exist, it raises `ProviderNotFoundError` with diagnostic guidance rather than silently continuing.)*
2. **PyInstaller Distribution Bundle:**
   * Checks `sys._MEIPASS / "bin" / "<name>.exe"` when running inside a frozen PyInstaller executable.
3. **Application Staging Directory:**
   * Checks `<app_root> / "bin" / "<name>.exe"` (standard production distribution).
4. **Current Python Environment:**
   * Checks `<sys.executable parent> / "bin" / "<name>.exe"` (for pip/wheel installations).
5. **Cargo Release Build Directory:**
   * Checks `<app_root> / "tmp/m2/target/release" / "<name>.exe"` (local developer release build).
6. **Cargo Debug Build Directory:**
   * Checks `<app_root> / "tmp/m2/target/debug" / "<name>.exe"` (local developer debug fallback).

### 7.2 CLI Diagnostic Check

To verify provider status and PE mitigations without launching the GUI:

```powershell
.venv-m1-clean\Scripts\python.exe main.py --check-provider
```

Example output:
```text
QuMail Native Cryptographic Provider Verification:

[OK] qumail-m3-provider:
  Path: C:\Users\uzx\Desktop\Aavishkar-26\QuMail\bin\qumail-m3-provider.exe
  Size: 8,381,440 bytes
  SHA-256: 4e5eebe6f3d268d012b057934a9f47c6482158e7bd0e3e8733082388d6b79695
  ASLR: True
  DEP:  True
  CFG:  True
  Manifest match: True

[OK] qumail-m5-provider:
  Path: C:\Users\uzx\Desktop\Aavishkar-26\QuMail\bin\qumail-m5-provider.exe
  Size: 10,672,640 bytes
  SHA-256: 23ac6a50174ef8f5504c549a9f3b515153ffbff62f946bd518ca6e3603005c6b
  ASLR: True
  DEP:  True
  CFG:  True
  Manifest match: True
```

---

## 8. Troubleshooting Checklist

| Symptom | Cause | Solution |
|---|---|---|
| `ProviderNotFoundError: Native cryptographic provider 'qumail-m5-provider' could not be located` | Binaries have not been compiled into `bin/` | Run `powershell -ExecutionPolicy Bypass -File tools/build_providers.ps1` |
| `ProviderNotFoundError: Environment variable 'QUMAIL_M5_PROVIDER_PATH' was set to ..., but no file was found` | Stale or misspelled environment variable | Verify path or clear environment variable: `Remove-Item Env:QUMAIL_M5_PROVIDER_PATH` |
| Linker error `LNK1104: cannot open file 'advapi32.lib'` during build | Missing Windows SDK components | Open Visual Studio Installer and ensure "Windows 10/11 SDK" is checked under Desktop C++ |
| Manifest mismatch reported by `--check-provider` | Binary recompiled locally without updating `manifest.json` | Run `tools/build_providers.ps1` to re-generate the manifest, or run `core/provider_resolver.py` directly |
