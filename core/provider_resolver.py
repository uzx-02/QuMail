"""
Native Cryptographic Provider Path Resolver & Integrity Verification.

Provides runtime resolution for QuMail's native Rust cryptographic helpers
(qumail-m3-provider and qumail-m5-provider) across repository development,
packaged single-directory distributions, and custom deployment layouts.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys


class ProviderError(Exception):
    """Base error for native provider resolution or execution issues."""
    pass


class ProviderNotFoundError(ProviderError):
    """Raised when an expected native cryptographic provider executable cannot be located."""
    pass


class ProviderIncompatibleError(ProviderError):
    """Raised when an existing native provider binary fails compatibility or integrity checks."""
    pass


_VALID_NAMES = {
    # Canonical functional names
    "qumail-vault-provider": "qumail-vault-provider",
    "qumail-crypto-provider": "qumail-crypto-provider",
    "vault": "qumail-vault-provider",
    "crypto": "qumail-crypto-provider",
    # Backward-compatible milestone aliases
    "qumail-m3-provider": "qumail-vault-provider",
    "qumail-m5-provider": "qumail-crypto-provider",
    "m3": "qumail-vault-provider",
    "m5": "qumail-crypto-provider",
}


def _normalize_name(name: str) -> str:
    cleaned = name.lower().removesuffix(".exe")
    canonical = _VALID_NAMES.get(cleaned)
    if not canonical:
        raise ValueError(
            f"Unknown provider name: {name!r}. Must be 'qumail-vault-provider' or 'qumail-crypto-provider'."
        )
    return canonical


def get_application_root() -> Path:
    """Return the base directory of the QuMail application or repository."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent.resolve()
    # Relative to core/provider_resolver.py -> parent of core is repo root
    return Path(__file__).resolve().parents[1]


def resolve_provider(name: str = "qumail-crypto-provider") -> Path:
    """
    Resolve the absolute path to a native provider executable.

    Search priority order:
      1. Explicit environment variable override:
         - QUMAIL_PROVIDER_PATH (generic override)
         - QUMAIL_VAULT_PROVIDER_PATH / QUMAIL_CRYPTO_PROVIDER_PATH (domain override)
         - QUMAIL_M3_PROVIDER_PATH / QUMAIL_M5_PROVIDER_PATH (legacy override)
      2. PyInstaller bundle directory: sys._MEIPASS / 'bin' / f'{canonical}.exe'
      3. Application-owned bin/ directory: <app_root> / 'bin' / f'{canonical}.exe'
      4. Application root: <sys.executable parent> / 'bin' / f'{canonical}.exe'
      5. Cargo release target: <app_root> / 'tmp/m2/target/release' / f'{canonical}.exe'
      6. Cargo debug target (development fallback): <app_root> / 'tmp/m2/target/debug' / f'{canonical}.exe'

    Raises:
        ProviderNotFoundError: If no valid executable can be located.
    """
    canonical = _normalize_name(name)
    app_root = get_application_root()

    # Canonical exe names with legacy fallbacks
    if canonical == "qumail-vault-provider":
        exe_names = ["qumail-vault-provider.exe", "qumail-m3-provider.exe"] if sys.platform == "win32" else ["qumail-vault-provider", "qumail-m3-provider"]
        env_keys = ["QUMAIL_PROVIDER_PATH", "QUMAIL_VAULT_PROVIDER_PATH", "QUMAIL_M3_PROVIDER_PATH"]
        env_hint = "QUMAIL_VAULT_PROVIDER_PATH"
    else:
        exe_names = ["qumail-crypto-provider.exe", "qumail-m5-provider.exe"] if sys.platform == "win32" else ["qumail-crypto-provider", "qumail-m5-provider"]
        env_keys = ["QUMAIL_PROVIDER_PATH", "QUMAIL_CRYPTO_PROVIDER_PATH", "QUMAIL_M5_PROVIDER_PATH"]
        env_hint = "QUMAIL_CRYPTO_PROVIDER_PATH"

    searched: list[Path] = []

    # 1. Environment variable override
    for key in env_keys:
        val = os.environ.get(key)
        if val:
            candidate = Path(val).resolve()
            if candidate.is_file():
                return candidate
            raise ProviderNotFoundError(
                f"Environment variable '{key}' was set to '{val}', but no file was found at specified location."
            )

    for exe_name in exe_names:
        # 2. PyInstaller bundle
        if hasattr(sys, "_MEIPASS"):
            candidate = Path(sys._MEIPASS) / "bin" / exe_name
            searched.append(candidate)
            if candidate.is_file():
                return candidate.resolve()

        # 3. PyInstaller onedir _internal directory
        candidate = app_root / "_internal" / "bin" / exe_name
        searched.append(candidate)
        if candidate.is_file():
            return candidate.resolve()

        # 4. Application-owned bin/ directory (standard distribution layout)
        candidate = app_root / "bin" / exe_name
        searched.append(candidate)
        if candidate.is_file():
            return candidate.resolve()

        # 5. Adjacent to current python executable (installed layout)
        candidate = Path(sys.executable).parent / "bin" / exe_name
        searched.append(candidate)
        if candidate.is_file():
            return candidate.resolve()

        # 6. Cargo Target Release (development release build)
        candidate = app_root / "tmp/m2/target/release" / exe_name
        searched.append(candidate)
        if candidate.is_file():
            return candidate.resolve()

        # 7. Cargo Target Debug (development debug build fallback)
        candidate = app_root / "tmp/m2/target/debug" / exe_name
        searched.append(candidate)
        if candidate.is_file():
            return candidate.resolve()

    locations = "\n  - ".join(str(p) for p in searched)
    env_hint = (
        "QUMAIL_VAULT_PROVIDER_PATH (or QUMAIL_M3_PROVIDER_PATH)"
        if "vault" in canonical or canonical == "qumail-m3-provider"
        else "QUMAIL_CRYPTO_PROVIDER_PATH (or QUMAIL_M5_PROVIDER_PATH)"
    )
    raise ProviderNotFoundError(
        f"Native cryptographic provider '{name}' ({canonical}) could not be located.\n"
        f"Searched candidate locations:\n  - {locations}\n\n"
        f"To compile the native provider locally, run:\n"
        f"  powershell -ExecutionPolicy Bypass -File tools/build_providers.ps1\n\n"
        f"Alternatively, set the {env_hint} environment variable to your build output path.\n"
    )


def inspect_pe_mitigations(path: Path | str) -> dict[str, object]:
    """
    Parse the Windows PE header of an executable to verify security mitigations.

    Checks IMAGE_OPTIONAL_HEADER.DllCharacteristics for ASLR, DEP, and CFG.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")

    with open(p, "rb") as f:
        data = f.read(4096)

    if len(data) < 64 or data[:2] != b"MZ":
        return {"is_pe": False, "error": "Not a valid DOS/PE file"}

    pe_offset = struct.unpack("<I", data[0x3C:0x40])[0]
    if len(data) < pe_offset + 24 or data[pe_offset:pe_offset+4] != b"PE\x00\x00":
        return {"is_pe": False, "error": "Invalid PE signature"}

    machine, num_sections, _, _, _, opt_hdr_size, characteristics = struct.unpack(
        "<HHIIIHH", data[pe_offset+4:pe_offset+24]
    )
    opt_offset = pe_offset + 24
    if opt_hdr_size < 72 or len(data) < opt_offset + opt_hdr_size:
        return {"is_pe": False, "error": "Truncated optional header"}

    magic = struct.unpack("<H", data[opt_offset:opt_offset+2])[0]
    is_pe32_plus = (magic == 0x20B)  # 64-bit PE

    # DllCharacteristics is at offset 70 in standard PE optional header
    dll_char_offset = opt_offset + 70
    dll_characteristics = struct.unpack("<H", data[dll_char_offset:dll_char_offset+2])[0]

    return {
        "is_pe": True,
        "machine": "x86_64" if machine == 0x8664 else hex(machine),
        "is_pe32_plus": is_pe32_plus,
        "dll_characteristics": dll_characteristics,
        "dll_characteristics_hex": hex(dll_characteristics),
        "dynamic_base_aslr": bool(dll_characteristics & 0x0040),
        "high_entropy_va_64bit_aslr": bool(dll_characteristics & 0x0020),
        "nx_compat_dep": bool(dll_characteristics & 0x0100),
        "guard_cf_control_flow_guard": bool(dll_characteristics & 0x4000),
        "terminal_server_aware": bool(dll_characteristics & 0x8000),
    }


def compute_sha256(path: Path | str) -> str:
    """Calculate the SHA-256 digest of a binary file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(manifest_path: Path | None = None) -> dict[str, object] | None:
    """Load and parse bin/manifest.json if present."""
    if manifest_path is None:
        manifest_path = get_application_root() / "bin" / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def verify_provider(name: str = "qumail-m5-provider") -> dict[str, object]:
    """
    Resolve and thoroughly verify a provider executable's existence,
    mitigation flags, and manifest consistency.
    """
    canonical = _normalize_name(name)
    path = resolve_provider(canonical)
    file_size = path.stat().st_size
    digest = compute_sha256(path)
    pe_info = inspect_pe_mitigations(path) if sys.platform == "win32" else {"is_pe": False}

    manifest_data = load_manifest()
    manifest_match = None
    if manifest_data:
        providers = manifest_data.get("providers", {})
        entry = providers.get(canonical)
        if not entry:
            fallback_key = "qumail-m3-provider" if "vault" in canonical else "qumail-m5-provider"
            entry = providers.get(fallback_key)
        if entry and "sha256" in entry:
            manifest_match = (entry["sha256"].lower() == digest.lower())

    return {
        "name": canonical,
        "path": str(path),
        "size_bytes": file_size,
        "sha256": digest,
        "pe_mitigations": pe_info,
        "manifest_match": manifest_match,
    }


if __name__ == "__main__":
    print("QuMail Native Provider Verification:")
    for prov in ("qumail-m3-provider", "qumail-m5-provider"):
        try:
            res = verify_provider(prov)
            print(f"\n[OK] {prov}:")
            print(f"  Path: {res['path']}")
            print(f"  Size: {res['size_bytes']:,} bytes")
            print(f"  SHA-256: {res['sha256']}")
            print(f"  ASLR: {res['pe_mitigations'].get('dynamic_base_aslr')}")
            print(f"  DEP:  {res['pe_mitigations'].get('nx_compat_dep')}")
            print(f"  CFG:  {res['pe_mitigations'].get('guard_cf_control_flow_guard')}")
            print(f"  Manifest match: {res['manifest_match']}")
        except Exception as exc:
            print(f"\n[FAIL] {prov}: {exc}")
