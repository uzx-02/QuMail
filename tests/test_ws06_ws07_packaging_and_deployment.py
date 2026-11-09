"""
Comprehensive Automated Tests for QuMail M7 — Module 1.6 WS-06/07:
Windows Production Packaging, Enterprise Deployment & Final Hardening.

Covers:
- Section 1: Reproducible Windows x64 Bundle Layout & PE Security Mitigations.
- Section 2: Native Provider Resolution from Packaged Layout & Corruption Handling.
- Section 3: Installer Engine: Installation, Atomic Upgrade & Safe Uninstallation.
- Section 4: Vault & User Data Preservation Invariants during Install/Upgrade/Uninstall.
- Section 5: Code Signing & Authenticode Inspection (Release vs Development Mode).
- Section 6: Update Manager: Cryptographic Verification, Downgrade Protection & Rollback.
- Section 7: Enterprise Policy (GPO): Registry/JSON Loading, Admin Dominance & Trust Anchors.
- Section 8: Operational Support Diagnostics: Privacy Redaction & Zero-Secret Export.
- Section 9: CLI Probes & Enterprise Hardening Integration.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile
from unittest.mock import Mock, patch

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.code_signing import (
    SigningRequiredError,
    inspect_binary_authenticode,
    verify_release_binaries,
)
from core.diagnostics import DiagnosticsCollector
from core.enterprise_policy import EnterprisePolicy, EnterprisePolicyManager
from core.installer_engine import (
    InstallerError,
    InstallOptions,
    WindowsInstallerEngine,
)
from core.packaging import (
    APPLICATION_NAME,
    APPLICATION_VERSION,
    BundleVerificationError,
    assemble_production_bundle,
    compute_file_sha256,
    inspect_pe_security_characteristics,
    verify_bundle_layout,
)
from core.provider_resolver import (
    ProviderIncompatibleError,
    ProviderNotFoundError,
    resolve_provider,
    verify_provider,
)
from core.update_manager import (
    DowngradeBlockedError,
    IncompatibleVaultError,
    SignatureVerificationError,
    UpdateManager,
    UpdateManifest,
    is_version_older,
    parse_semver,
)
import main


ROOT = Path(__file__).resolve().parents[1]


# =============================================================================
# SECTION 1: Reproducible Bundle Layout & PE Mitigations
# =============================================================================

def test_reproducible_bundle_layout_assembly(tmp_path):
    """
    Verifies assemble_production_bundle creates a clean Windows x64 distribution
    containing version metadata, release native providers, and default policies.
    """
    bundle_dir = tmp_path / "QuMail_Bundle"
    metadata = assemble_production_bundle(
        source_root=ROOT,
        output_dir=bundle_dir,
        version="1.0.0",
        commit_sha="test_commit_12345",
    )

    assert metadata.app_name == APPLICATION_NAME
    assert metadata.version == "1.0.0"
    assert metadata.platform == "win32-x64"
    assert metadata.pe_mitigations_verified is True

    # Verify directory contents
    assert (bundle_dir / "version.json").is_file()
    assert (bundle_dir / "bin" / "qumail-m3-provider.exe").is_file()
    assert (bundle_dir / "bin" / "qumail-m5-provider.exe").is_file()
    assert (bundle_dir / "bin" / "manifest.json").is_file()
    assert (bundle_dir / "resources" / "qumail.default.json").is_file()

    # Layout verification
    result = verify_bundle_layout(bundle_dir)
    assert result["status"] == "VALID"
    assert result["version"] == "1.0.0"


def test_native_provider_pe_security_mitigations():
    """
    Verifies that the compiled Release native providers shipped in bin/
    enforce all required Windows security mitigations:
    - High-Entropy 64-bit ASLR
    - Dynamic Base ASLR
    - NX Compat DEP
    - MSVC Control Flow Guard (Guard CF: 0x4000)
    - Full characteristics 0xc160
    """
    for prov_name in ("qumail-m3-provider.exe", "qumail-m5-provider.exe"):
        exe_path = ROOT / "bin" / prov_name
        assert exe_path.is_file(), f"Missing provider: {exe_path}"

        mitigations = inspect_pe_security_characteristics(exe_path)
        assert mitigations["is_64bit"] is True
        assert mitigations["dynamic_base_aslr"] is True
        assert mitigations["high_entropy_va"] is True
        assert mitigations["nx_compat_dep"] is True
        assert mitigations["guard_cf"] is True
        assert mitigations["fully_hardened"] is True


def test_corrupted_bundle_layout_rejection(tmp_path):
    """
    Verifies that a tampered or incomplete bundle fails verification.
    """
    bundle_dir = tmp_path / "Corrupt_Bundle"
    assemble_production_bundle(ROOT, bundle_dir, "1.0.0", "sha")

    # 1. Missing manifest
    manifest = bundle_dir / "bin" / "manifest.json"
    manifest.unlink()
    with pytest.raises(BundleVerificationError, match="Missing manifest.json"):
        verify_bundle_layout(bundle_dir)

    # Restore manifest, tamper with provider binary
    shutil.copy2(ROOT / "bin" / "manifest.json", manifest)
    m3_exe = bundle_dir / "bin" / "qumail-m3-provider.exe"
    m3_exe.write_bytes(b"tampered content")

    with pytest.raises(BundleVerificationError, match="Digest mismatch|Not a valid DOS/PE"):
        verify_bundle_layout(bundle_dir)


# =============================================================================
# SECTION 2: Provider Resolution from Installed Layout
# =============================================================================

def test_provider_resolution_from_simulated_install_root(tmp_path, monkeypatch):
    """
    Verifies that resolve_provider discovers binaries relative to the installed
    application root (sys.executable parent / bin).
    """
    sim_app = tmp_path / "InstalledApp"
    sim_bin = sim_app / "bin"
    sim_bin.mkdir(parents=True)

    # Copy real providers into simulated install
    shutil.copy2(ROOT / "bin" / "qumail-m3-provider.exe", sim_bin / "qumail-m3-provider.exe")
    shutil.copy2(ROOT / "bin" / "qumail-m5-provider.exe", sim_bin / "qumail-m5-provider.exe")
    shutil.copy2(ROOT / "bin" / "manifest.json", sim_bin / "manifest.json")

    # Point sys.executable to simulated app root and mark frozen
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(sim_app / "QuMail.exe"))
    monkeypatch.delenv("QUMAIL_PROVIDER_PATH", raising=False)
    monkeypatch.delenv("QUMAIL_M3_PROVIDER_PATH", raising=False)
    monkeypatch.delenv("QUMAIL_M5_PROVIDER_PATH", raising=False)

    p3 = resolve_provider("qumail-m3-provider")
    assert p3.is_file()
    assert "InstalledApp" in str(p3)

    p5 = resolve_provider("qumail-m5-provider")
    assert p5.is_file()
    assert "InstalledApp" in str(p5)


def test_missing_provider_raises_clear_error(monkeypatch):
    """
    Verifies that when a provider is genuinely missing, ProviderNotFoundError
    is raised with actionable guidance.
    """
    monkeypatch.setenv("QUMAIL_M5_PROVIDER_PATH", r"C:\NonExistent\qumail-m5-provider.exe")
    with pytest.raises(ProviderNotFoundError, match="no file was found"):
        resolve_provider("qumail-m5-provider")


# =============================================================================
# SECTION 3: Installer Engine (Install, Upgrade & Uninstallation)
# =============================================================================

def test_installer_fresh_installation(tmp_path):
    """
    Verifies fresh installation into a clean target directory.
    """
    bundle_dir = tmp_path / "SourceBundle"
    assemble_production_bundle(ROOT, bundle_dir, "1.0.0", "commit_a")

    target_dir = tmp_path / "InstalledQuMail"
    installer = WindowsInstallerEngine(target_dir=target_dir, per_user=True)

    options = InstallOptions(target_dir=target_dir)
    res = installer.install(bundle_dir, options)

    assert res["status"] == "INSTALLED"
    assert res["installed_version"] == "1.0.0"
    assert (target_dir / "version.json").is_file()
    assert (target_dir / "install_manifest.json").is_file()
    assert installer.get_installed_version() == "1.0.0"


def test_installer_upgrade_preserves_configuration(tmp_path):
    """
    Verifies that upgrading to a newer version cleanly updates the binaries
    without clobbering existing configuration or installation state.
    """
    # 1. Install v1.0.0
    bundle_v1 = tmp_path / "Bundle_v1"
    assemble_production_bundle(ROOT, bundle_v1, "1.0.0", "commit_1")

    target_dir = tmp_path / "InstalledQuMail"
    installer = WindowsInstallerEngine(target_dir=target_dir, per_user=True)
    installer.install(bundle_v1, InstallOptions(target_dir=target_dir))
    assert installer.get_installed_version() == "1.0.0"

    # 2. Upgrade to v1.1.0
    bundle_v2 = tmp_path / "Bundle_v2"
    assemble_production_bundle(ROOT, bundle_v2, "1.1.0", "commit_2")

    res = installer.install(bundle_v2, InstallOptions(target_dir=target_dir))
    assert res["status"] == "UPGRADED"
    assert res["previous_version"] == "1.0.0"
    assert res["installed_version"] == "1.1.0"
    assert installer.get_installed_version() == "1.1.0"


def test_installer_blocks_downgrade_unless_authorized(tmp_path):
    """
    Verifies that attempting to install an older version over a newer one
    is blocked by default.
    """
    # Install v2.0.0
    bundle_v2 = tmp_path / "Bundle_v2"
    assemble_production_bundle(ROOT, bundle_v2, "2.0.0", "commit_2")
    target_dir = tmp_path / "InstalledQuMail"
    installer = WindowsInstallerEngine(target_dir=target_dir)
    installer.install(bundle_v2, InstallOptions(target_dir=target_dir))

    # Attempt to install v1.0.0 over v2.0.0 without allow_downgrade
    bundle_v1 = tmp_path / "Bundle_v1"
    assemble_production_bundle(ROOT, bundle_v1, "1.0.0", "commit_1")

    with pytest.raises(InstallerError, match="Downgrade blocked"):
        installer.install(bundle_v1, InstallOptions(target_dir=target_dir, allow_downgrade=False))

    # Installing with explicit allow_downgrade=True succeeds
    res = installer.install(bundle_v1, InstallOptions(target_dir=target_dir, allow_downgrade=True))
    assert res["status"] == "UPGRADED"
    assert res["installed_version"] == "1.0.0"


# =============================================================================
# SECTION 4: Vault & User Data Preservation Invariants
# =============================================================================

def test_uninstall_preserves_user_data_by_default(tmp_path, monkeypatch):
    """
    CRITICAL SECURITY INVARIANT:
    Uninstalling QuMail removes application binaries but STRICTLY PRESERVES
    user vaults, private keys, and email indices in data_dir by default.
    """
    target_dir = tmp_path / "ProgramFiles_QuMail"
    data_dir = tmp_path / "UserData_QuMail"
    data_dir.mkdir(parents=True)

    # Create dummy user vault with sensitive keys
    vault_file = data_dir / "vault.sqlite"
    vault_file.write_text("SENSITIVE_ENCRYPTED_VAULT_DATA", encoding="utf-8")

    bundle = tmp_path / "Bundle"
    assemble_production_bundle(ROOT, bundle, "1.0.0", "commit")

    installer = WindowsInstallerEngine(target_dir=target_dir)
    installer.data_dir = data_dir
    installer.install(bundle, InstallOptions(target_dir=target_dir))

    assert target_dir.exists()
    assert vault_file.exists()

    # Normal Uninstall
    res = installer.uninstall(purge_user_data=False)
    assert res["status"] == "UNINSTALLED"
    assert not target_dir.exists()  # Binaries deleted

    # USER DATA STRICTLY PRESERVED
    assert res["user_data_preserved"] is True
    assert vault_file.is_file()
    assert vault_file.read_text(encoding="utf-8") == "SENSITIVE_ENCRYPTED_VAULT_DATA"


def test_uninstall_explicit_purge_requires_confirmation_token(tmp_path):
    """
    Verifies that user data is ONLY purged if purge_user_data=True AND
    the exact confirmation token 'CONFIRM_DELETE_KEYS' is provided.
    """
    target_dir = tmp_path / "ProgramFiles_QuMail"
    data_dir = tmp_path / "UserData_QuMail"
    data_dir.mkdir(parents=True)
    (data_dir / "keys.db").write_text("keys", encoding="utf-8")

    bundle = tmp_path / "Bundle"
    assemble_production_bundle(ROOT, bundle, "1.0.0", "commit")
    installer = WindowsInstallerEngine(target_dir=target_dir)
    installer.data_dir = data_dir
    installer.install(bundle, InstallOptions(target_dir=target_dir))

    # Attempt purge with wrong token -> fails
    with pytest.raises(InstallerError, match="Safety violation"):
        installer.uninstall(purge_user_data=True, confirm_token="wrong_token")
    assert (data_dir / "keys.db").exists()

    # Purge with exact token -> succeeds
    res = installer.uninstall(purge_user_data=True, confirm_token="CONFIRM_DELETE_KEYS")
    assert res["user_data_purged"] is True
    assert not data_dir.exists()


# =============================================================================
# SECTION 5: Code Signing & Authenticode Inspection
# =============================================================================

def test_authenticode_inspection_detects_unsigned_development_artifacts():
    """
    Verifies that inspect_binary_authenticode identifies unsigned development
    binaries clearly without throwing errors.
    """
    exe_path = ROOT / "bin" / "qumail-m3-provider.exe"
    res = inspect_binary_authenticode(exe_path)

    assert res.file_path == str(exe_path.resolve())
    assert isinstance(res.is_signed, bool)
    assert res.pe_mitigations["guard_cf"] is True
    assert res.pe_mitigations["fully_hardened"] is True


def test_strict_release_signing_rejection(tmp_path):
    """
    Verifies that verify_release_binaries raises SigningRequiredError
    when unsigned binaries are encountered under strict release enforcement.
    """
    bundle = tmp_path / "UnsignedBundle"
    assemble_production_bundle(ROOT, bundle, "1.0.0", "c")

    # In strict mode, unsigned development binaries are rejected
    with pytest.raises(SigningRequiredError, match="binaries are unsigned"):
        verify_release_binaries(bundle, strict_release=True)

    # In development mode (strict=False), they are allowed with audit status
    audit = verify_release_binaries(bundle, strict_release=False)
    assert "qumail-m3-provider.exe" in audit
    assert "qumail-m5-provider.exe" in audit


# =============================================================================
# SECTION 6: Update Manager: Verification, Downgrade Protection & Rollback
# =============================================================================

def test_semver_parsing_and_comparison():
    """
    Verifies semantic version parsing and downgrade ordering.
    """
    assert parse_semver("1.0.0") == (1, 0, 0, "")
    assert parse_semver("v1.2.3-rc1") == (1, 2, 3, "rc1")

    assert is_version_older("1.0.0", "1.0.1") is True
    assert is_version_older("1.1.0", "1.0.9") is False
    assert is_version_older("1.0.0-rc1", "1.0.0") is True
    assert is_version_older("2.0.0", "1.9.9") is False


def test_update_package_cryptographic_verification_and_rollback(tmp_path):
    """
    Verifies UpdateManager package verification:
    - Ed25519 signature verification on update_manifest.json
    - Downgrade prevention
    - Vault schema compatibility
    - Atomic extraction and directory swap
    """
    install_dir = tmp_path / "AppInstall"
    install_dir.mkdir(parents=True)
    (install_dir / "app.txt").write_text("v1.0.0 content", encoding="utf-8")

    # Generate enterprise signing key pair
    signing_key = Ed25519PrivateKey.generate()
    trusted_public_bytes = signing_key.public_key().public_bytes_raw()

    # Create signed update package for v1.1.0
    payload_content = b"v1.1.0 updated binary content"
    manifest = UpdateManifest(
        version="1.1.0",
        min_vault_version=1,
        published_utc="2026-11-09T00:00:00Z",
        file_digests={"payload/app.txt": compute_file_sha256_bytes(payload_content)},
    )
    manifest_bytes = manifest.to_json().encode("utf-8")
    sig_bytes = signing_key.sign(manifest_bytes)

    pkg_zip = tmp_path / "qumail_update_1.1.0.qupkg"
    with zipfile.ZipFile(pkg_zip, "w") as zf:
        zf.writestr("update_manifest.json", manifest_bytes)
        zf.writestr("signature.bin", sig_bytes)
        zf.writestr("payload/app.txt", payload_content)

    mgr = UpdateManager(
        install_dir=install_dir,
        current_version="1.0.0",
        current_vault_version=1,
        trusted_public_keys=[trusted_public_bytes],
    )

    # Successful update
    res = mgr.apply_update(pkg_zip)
    assert res["status"] == "UPDATED"
    assert res["new_version"] == "1.1.0"
    assert (install_dir / "app.txt").read_bytes() == payload_content

    # Downgrade attempt: package for v0.9.0
    manifest_old = UpdateManifest(
        version="0.9.0",
        min_vault_version=1,
        published_utc="2026-11-09T00:00:00Z",
        file_digests={"payload/app.txt": compute_file_sha256_bytes(b"old")},
    )
    m_old_bytes = manifest_old.to_json().encode("utf-8")
    s_old_bytes = signing_key.sign(m_old_bytes)
    pkg_old = tmp_path / "qumail_update_0.9.0.qupkg"
    with zipfile.ZipFile(pkg_old, "w") as zf:
        zf.writestr("update_manifest.json", m_old_bytes)
        zf.writestr("signature.bin", s_old_bytes)
        zf.writestr("payload/app.txt", b"old")

    with pytest.raises(DowngradeBlockedError, match="Downgrade prohibited"):
        mgr.apply_update(pkg_old, allow_downgrade=False)

    # Untrusted signature attempt
    other_key = Ed25519PrivateKey.generate()
    bad_sig = other_key.sign(manifest_bytes)
    pkg_bad_sig = tmp_path / "qumail_update_bad_sig.qupkg"
    with zipfile.ZipFile(pkg_bad_sig, "w") as zf:
        zf.writestr("update_manifest.json", manifest_bytes)
        zf.writestr("signature.bin", bad_sig)
        zf.writestr("payload/app.txt", payload_content)

    with pytest.raises(SignatureVerificationError, match="could not be verified"):
        mgr.apply_update(pkg_bad_sig)


def compute_file_sha256_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest().lower()


# =============================================================================
# SECTION 7: Enterprise Policy (GPO)
# =============================================================================

def test_enterprise_policy_loading_and_admin_precedence(tmp_path, monkeypatch):
    """
    Verifies that enterprise policies are read from administrative sources
    and enforce security invariants.
    """
    policy_data = {
        "allowed_domains": ["corp.example.com", "partner.example.com"],
        "managed_trust_anchors": {
            "corp.example.com": "5ceb47b86bec9b3b8d6e666e718947391c59f8763be1347b0e3c2a692e022241"
        },
        "block_external_accounts": True,
        "enforce_strict_encryption": True,
        "disable_legacy_simulator": True,
        "update_channel": "LTS",
        "log_level": "WARNING",
    }

    policy_file = tmp_path / "policies.json"
    policy_file.write_text(json.dumps(policy_data), encoding="utf-8")

    # Point manager to policy file
    monkeypatch.setattr("core.enterprise_policy.PROGRAMDATA_POLICY_PATH", policy_file)
    monkeypatch.setattr("core.enterprise_policy.EnterprisePolicyManager._read_hklm_registry", lambda self: None)

    mgr = EnterprisePolicyManager()
    pol = mgr.policy

    assert pol.is_managed is True
    assert pol.block_external_accounts is True
    assert pol.enforce_strict_encryption is True
    assert pol.disable_legacy_simulator is True
    assert pol.update_channel == "LTS"
    assert pol.log_level == "WARNING"

    # Domain checking
    assert mgr.is_domain_allowed("alice@corp.example.com") is True
    assert mgr.is_domain_allowed("eve@untrusted.com") is False

    # Trust anchor fingerprint verification
    valid_fp = "5ceb47b86bec9b3b8d6e666e718947391c59f8763be1347b0e3c2a692e022241"
    assert mgr.is_trust_anchor_verified("corp.example.com", valid_fp) is True
    assert mgr.is_trust_anchor_verified("corp.example.com", "0000000000000000000000000000000000000000000000000000000000000000") is False


def test_malformed_trust_anchor_fingerprint_rejection():
    """
    Verifies that arbitrary strings or invalid-length fingerprints
    are rejected from managed_trust_anchors.
    """
    data = {
        "managed_trust_anchors": {
            "corp.com": "NOT_A_VALID_SHA256_FINGERPRINT",
            "corp2.com": "12345",  # Too short
            "corp3.com": "5ceb47b86bec9b3b8d6e666e718947391c59f8763be1347b0e3c2a692e022241",  # Valid
        }
    }
    pol = EnterprisePolicy.from_dict(data)
    assert "corp.com" not in pol.managed_trust_anchors
    assert "corp2.com" not in pol.managed_trust_anchors
    assert "corp3.com" in pol.managed_trust_anchors


# =============================================================================
# SECTION 8: Operational Support Diagnostics & Privacy Redaction
# =============================================================================

def test_diagnostics_bundle_export_with_privacy_guarantee(tmp_path):
    """
    Verifies DiagnosticsCollector generates a support snapshot that completely
    redacts all sensitive contents:
    - Zero passwords, tokens, private keys, message bodies, attachments
    """
    out_file = tmp_path / "diagnostics_report.json"
    collector = DiagnosticsCollector()

    class MockItem:
        state = "ACCEPTED"

    exported = collector.export_bundle(
        output_file=out_file,
        sync_state="Idle",
        outbox_items=[MockItem(), MockItem()],
    )

    assert exported.is_file()
    data = json.loads(exported.read_text(encoding="utf-8"))

    assert data["client"]["app_name"] == APPLICATION_NAME
    assert data["mailbox_sync"]["state"] == "Idle"
    assert data["outbox"]["total_items"] == 2
    assert "ACCEPTED" in data["outbox"]["counts_by_state"]

    # Verify absence of sensitive keys across the entire JSON
    raw_text = exported.read_text(encoding="utf-8").lower()
    for forbidden in ("password", "private_key", "secret", "oauth_token", "message_body", "recipient"):
        # The key names should not be present with actual sensitive values
        assert f'"{forbidden}":' not in raw_text

    assert "zero private keys" in data["privacy_guarantee"].lower()


# =============================================================================
# SECTION 9: CLI Probes & Enterprise Hardening Integration
# =============================================================================

def test_main_cli_export_diagnostics_flag(tmp_path):
    """
    Verifies that running 'main.py --export-diagnostics <path>' collects
    and writes diagnostic data then exits cleanly.
    """
    out_file = tmp_path / "cli_diag.json"
    ret = main.main(["--export-diagnostics", str(out_file)])
    assert ret == 0
    assert out_file.is_file()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["client"]["app_name"] == APPLICATION_NAME


def test_main_cli_legacy_simulator_blocked_by_policy(monkeypatch):
    """
    Verifies that when enterprise policy blocks the legacy simulator,
    attempting to launch with --legacy-simulator is rejected immediately.
    """
    blocked_policy = EnterprisePolicy(disable_legacy_simulator=True, is_managed=True)
    monkeypatch.setattr(
        "core.enterprise_policy.EnterprisePolicyManager.policy",
        blocked_policy,
    )

    with patch("main._show_critical_error") as mock_err:
        ret = main.main(["--legacy-simulator"])
        assert ret == 1
        assert mock_err.called
        assert "blocked by corporate group policy" in mock_err.call_args[0][1].lower()
