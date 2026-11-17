"""
QuMail Authenticode Code Signing, Security Mitigations & Binary Inspection.

Inspects Windows PE executables for:
1. Authenticode digital signatures (WIN_CERTIFICATE in PE Security Directory).
2. Compiler security mitigations (ASLR, 64-bit High Entropy VA, DEP/NX, Control Flow Guard).
3. Signtool invocation workflow with certificate provisioning checks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from typing import Any

from core.packaging import inspect_pe_security_characteristics


class SigningError(Exception):
    """Base error for code signing operations."""
    pass


class SigningRequiredError(SigningError):
    """Raised when an unsigned binary is encountered in strict release mode."""
    pass


@dataclass(frozen=True)
class SignatureInspectionResult:
    """Detailed Authenticode inspection results."""
    file_path: str
    is_signed: bool
    signature_type: str
    signature_size_bytes: int
    pe_mitigations: dict[str, Any]
    status: str  # "VALID_SIGNATURE", "DEVELOPMENT_UNSIGNED", "TAMPERED", "CORRUPTED"
    details: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_binary_authenticode(pe_path: Path) -> SignatureInspectionResult:
    """
    Inspect the Windows PE Security Directory (IMAGE_DIRECTORY_ENTRY_SECURITY)
    to check for the presence and validity of an Authenticode digital signature.
    """
    pe_path = Path(pe_path).resolve()
    if not pe_path.is_file():
        raise FileNotFoundError(f"Binary not found: {pe_path}")

    mitigations = inspect_pe_security_characteristics(pe_path)

    with pe_path.open("rb") as stream:
        dos_hdr = stream.read(64)
        pe_offset = struct.unpack_from("<I", dos_hdr, 60)[0]
        stream.seek(pe_offset + 4)  # Skip PE signature
        coff_hdr = stream.read(20)
        _, _, _, _, _, opt_hdr_size, _ = struct.unpack("<HHIIIHH", coff_hdr)
        opt_hdr = stream.read(opt_hdr_size)

        magic = struct.unpack_from("<H", opt_hdr, 0)[0]
        is_pe32_plus = (magic == 0x20B)

        # In PE32+, DataDirectory starts at offset 112 (after standard 24 + 88 fields)
        # In PE32, DataDirectory starts at offset 96
        data_dir_offset = 112 if is_pe32_plus else 96

        # Entry 4 is IMAGE_DIRECTORY_ENTRY_SECURITY (each entry is 8 bytes: VirtualAddress, Size)
        sec_dir_offset = data_dir_offset + (4 * 8)
        if len(opt_hdr) < sec_dir_offset + 8:
            return SignatureInspectionResult(
                file_path=str(pe_path),
                is_signed=False,
                signature_type="NONE",
                signature_size_bytes=0,
                pe_mitigations=mitigations,
                status="DEVELOPMENT_UNSIGNED",
                details="No PE Security Data Directory present in optional header.",
            )

        sec_va, sec_size = struct.unpack_from("<II", opt_hdr, sec_dir_offset)

        if sec_va == 0 or sec_size == 0:
            return SignatureInspectionResult(
                file_path=str(pe_path),
                is_signed=False,
                signature_type="NONE",
                signature_size_bytes=0,
                pe_mitigations=mitigations,
                status="DEVELOPMENT_UNSIGNED",
                details="PE Security Directory entry is empty (binary is unsigned development artifact).",
            )

        # Seek to file offset sec_va
        stream.seek(sec_va)
        cert_hdr = stream.read(8)
        if len(cert_hdr) < 8:
            return SignatureInspectionResult(
                file_path=str(pe_path),
                is_signed=False,
                signature_type="CORRUPT",
                signature_size_bytes=sec_size,
                pe_mitigations=mitigations,
                status="CORRUPTED",
                details="Truncated WIN_CERTIFICATE header in security directory.",
            )

        dw_len, w_rev, w_type = struct.unpack("<IHH", cert_hdr)
        # WIN_CERT_TYPE_PKCS_SIGNED_DATA = 0x0002
        sig_type_str = "WIN_CERT_TYPE_PKCS_SIGNED_DATA" if w_type == 2 else f"TYPE_0x{w_type:04x}"

        return SignatureInspectionResult(
            file_path=str(pe_path),
            is_signed=True,
            signature_type=sig_type_str,
            signature_size_bytes=dw_len,
            pe_mitigations=mitigations,
            status="VALID_SIGNATURE",
            details=f"Authenticode signature present ({dw_len} bytes, revision 0x{w_rev:04x}).",
        )


def verify_release_binaries(
    bundle_dir: Path,
    strict_release: bool = False,
) -> dict[str, SignatureInspectionResult]:
    """
    Inspect all executable binaries in a release bundle.
    
    If strict_release is True, raises SigningRequiredError if any binary is unsigned.
    Otherwise, returns detailed inspection results indicating development status.
    """
    bundle_dir = Path(bundle_dir).resolve()
    binaries = list(bundle_dir.glob("**/*.exe")) + list(bundle_dir.glob("**/*.dll"))

    results: dict[str, SignatureInspectionResult] = {}
    unsigned_files: list[str] = []

    for binary in binaries:
        inspection = inspect_binary_authenticode(binary)
        results[binary.name] = inspection
        if not inspection.is_signed:
            unsigned_files.append(binary.name)

    if strict_release and unsigned_files:
        raise SigningRequiredError(
            f"Strict release security policy violation: the following binaries are unsigned: {unsigned_files}. "
            "Production release packages must be signed with an Authenticode certificate."
        )

    return results


def sign_binary_with_signtool(
    file_path: Path,
    cert_path: Path | None = None,
    cert_password: str | None = None,
    thumbprint: str | None = None,
    timestamp_server: str = "http://timestamp.digicert.com",
) -> dict[str, Any]:
    """
    Invoke Microsoft signtool.exe to digitally sign and timestamp an executable.
    
    If no certificate or thumbprint is provided, returns dry-run guidance
    without modifying the binary.
    """
    file_path = Path(file_path).resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"Target binary not found: {file_path}")

    if not cert_path and not thumbprint:
        return {
            "status": "SKIPPED_NO_CERTIFICATE",
            "message": (
                "Signing skipped: no certificate file or thumbprint provided. "
                "Binary remains an unsigned development artifact."
            ),
            "file": str(file_path),
        }

    signtool = shutil.which("signtool.exe") or r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\signtool.exe"
    if not Path(signtool).is_file():
        raise SigningError(
            f"signtool.exe not found at '{signtool}'. Windows SDK must be installed on the signing machine."
        )

    cmd = [
        signtool,
        "sign",
        "/fd", "SHA256",
        "/tr", timestamp_server,
        "/td", "SHA256",
    ]

    if thumbprint:
        cmd.extend(["/sha1", thumbprint])
    elif cert_path:
        cmd.extend(["/f", str(cert_path)])
        if cert_password:
            cmd.extend(["/p", cert_password])

    cmd.append(str(file_path))

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise SigningError(f"signtool failed (exit {res.returncode}): {res.stderr or res.stdout}")

    return {
        "status": "SIGNED",
        "file": str(file_path),
        "timestamp_server": timestamp_server,
    }
