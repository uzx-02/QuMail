"""
QuMail Production Update Verification, Downgrade Protection & Atomic Rollback.

Enforces:
1. Cryptographic signature and digest verification of update packages.
2. Semantic version downgrade protection (prohibiting rollback to older vulnerable releases).
3. Vault schema compatibility checks prior to extraction.
4. Atomic directory update with automatic rollback upon failure or interruption.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any
import zipfile


class UpdateError(Exception):
    """Base error for update operations."""
    pass


class SignatureVerificationError(UpdateError):
    """Raised when an update package has an invalid, missing, or untrusted cryptographic signature."""
    pass


class DowngradeBlockedError(UpdateError):
    """Raised when an update package contains a version older than currently installed."""
    pass


class IncompatibleVaultError(UpdateError):
    """Raised when an update requires a vault schema incompatible with the current client."""
    pass


def parse_semver(version_str: str) -> tuple[int, int, int, str]:
    """
    Parse a semantic version string: '1.2.3', '1.2.3-rc1', 'v1.2.3'.
    Returns (major, minor, patch, prerelease).
    """
    cleaned = version_str.strip().lstrip("vV")
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:-([a-zA-Z0-9\._-]+))?$", cleaned)
    if not match:
        raise ValueError(f"Invalid semver string: {version_str!r}")

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3)) if match.group(3) is not None else 0
    prerelease = match.group(4) or ""
    return (major, minor, patch, prerelease)


def is_version_older(candidate: str, current: str) -> bool:
    """Return True if candidate is older than current version."""
    c_maj, c_min, c_pat, c_pre = parse_semver(candidate)
    curr_maj, curr_min, curr_pat, curr_pre = parse_semver(current)

    if (c_maj, c_min, c_pat) < (curr_maj, curr_min, curr_pat):
        return True
    if (c_maj, c_min, c_pat) > (curr_maj, curr_min, curr_pat):
        return False
    # Identical major.minor.patch
    if c_pre and not curr_pre:
        # prerelease is older than release
        return True
    if not c_pre and curr_pre:
        return False
    return c_pre < curr_pre


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


@dataclass
class UpdateManifest:
    version: str
    min_vault_version: int
    published_utc: str
    file_digests: dict[str, str]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> UpdateManifest:
        data = json.loads(text)
        return cls(**data)


class UpdateManager:
    """
    Verifies and applies production application updates.
    """

    def __init__(
        self,
        install_dir: Path,
        current_version: str,
        current_vault_version: int = 1,
        trusted_public_keys: list[bytes] | None = None,
    ):
        self.install_dir = Path(install_dir).resolve()
        self.current_version = current_version
        self.current_vault_version = current_vault_version
        self.trusted_public_keys = trusted_public_keys or []

    def verify_package(
        self,
        package_zip: Path,
        allow_downgrade: bool = False,
        allow_unsigned: bool = False,
    ) -> UpdateManifest:
        """
        Verify update archive:
        - Check archive structure.
        - Validate cryptographic signature of update_manifest.json.
        - Validate checksums of all bundled payload files.
        - Enforce downgrade protection.
        - Validate vault compatibility.
        """
        package_zip = Path(package_zip).resolve()
        if not package_zip.is_file():
            raise FileNotFoundError(f"Update package not found: {package_zip}")

        with zipfile.ZipFile(package_zip, "r") as zf:
            namelist = zf.namelist()
            if "update_manifest.json" not in namelist:
                raise UpdateError("Malformed update package: missing 'update_manifest.json'")

            manifest_bytes = zf.read("update_manifest.json")
            manifest = UpdateManifest.from_json(manifest_bytes.decode("utf-8"))

            # 1. Signature Verification
            if not allow_unsigned:
                if "signature.bin" not in namelist:
                    raise SignatureVerificationError(
                        "Package is unsigned: missing 'signature.bin'. Production updates must be signed."
                    )
                sig_bytes = zf.read("signature.bin")
                self._verify_manifest_signature(manifest_bytes, sig_bytes)

            # 2. File Checksums
            for rel_path, expected_hash in manifest.file_digests.items():
                if rel_path not in namelist:
                    raise UpdateError(f"Missing file declared in manifest: {rel_path}")
                content = zf.read(rel_path)
                actual_hash = compute_sha256(content)
                if actual_hash != expected_hash.lower():
                    raise UpdateError(
                        f"Checksum mismatch for '{rel_path}': expected {expected_hash}, computed {actual_hash}"
                    )

            # 3. Downgrade Protection
            if is_version_older(manifest.version, self.current_version):
                if not allow_downgrade:
                    raise DowngradeBlockedError(
                        f"Downgrade prohibited: candidate v{manifest.version} is older than currently installed "
                        f"v{self.current_version}. Downgrade requires explicit administrative authorization."
                    )

            # 4. Vault Compatibility Check
            if manifest.min_vault_version > self.current_vault_version:
                raise IncompatibleVaultError(
                    f"Update requires vault schema v{manifest.min_vault_version}, but current vault schema is "
                    f"v{self.current_vault_version}. Client database migration required before updating."
                )

            return manifest

    def _verify_manifest_signature(self, manifest_bytes: bytes, sig_bytes: bytes) -> None:
        """
        Verify signature using configured trust anchors.
        Supports standard Ed25519 signatures via cryptography.
        """
        if not self.trusted_public_keys:
            raise SignatureVerificationError("No enterprise update trust anchors configured on this machine.")

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature

        verified = False
        for raw_pub in self.trusted_public_keys:
            try:
                pub_key = Ed25519PublicKey.from_public_bytes(raw_pub)
                pub_key.verify(sig_bytes, manifest_bytes)
                verified = True
                break
            except (InvalidSignature, ValueError):
                continue

        if not verified:
            raise SignatureVerificationError("Update manifest signature could not be verified by any trusted enterprise key.")

    def apply_update(
        self,
        package_zip: Path,
        allow_downgrade: bool = False,
        allow_unsigned: bool = False,
    ) -> dict[str, Any]:
        """
        Verify package and atomically replace installation directory with rollback capability.
        """
        manifest = self.verify_package(package_zip, allow_downgrade, allow_unsigned)

        timestamp = int(datetime.now(timezone.utc).timestamp())
        backup_dir = self.install_dir.parent / f"{self.install_dir.name}_backup_{timestamp}"
        staging_dir = self.install_dir.parent / f"{self.install_dir.name}_staging_{timestamp}"

        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Extract to staging
            with zipfile.ZipFile(package_zip, "r") as zf:
                for item in zf.namelist():
                    if item.startswith("payload/"):
                        rel = item[len("payload/"):]
                        if rel:
                            dest = staging_dir / rel
                            if item.endswith("/"):
                                dest.mkdir(parents=True, exist_ok=True)
                            else:
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                with dest.open("wb") as out_f:
                                    out_f.write(zf.read(item))

            # Atomic directory swap
            if self.install_dir.exists():
                self.install_dir.rename(backup_dir)

            staging_dir.rename(self.install_dir)

            # Successful: clean up backup
            if backup_dir.exists():
                shutil.rmtree(backup_dir)

        except Exception as e:
            # Rollback
            if backup_dir.exists() and not self.install_dir.exists():
                backup_dir.rename(self.install_dir)
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            raise UpdateError(f"Atomic update failed, rolled back to original version {self.current_version}: {e}")

        return {
            "status": "UPDATED",
            "previous_version": self.current_version,
            "new_version": manifest.version,
            "install_dir": str(self.install_dir),
        }
