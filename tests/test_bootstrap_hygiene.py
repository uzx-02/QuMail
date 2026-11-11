"""
WS-01 Verification Suite: Bootstrap, Native Engine Hygiene & Privacy-Safe Logging.

Validates:
1. Provider resolver search order, overrides, and failure diagnostics.
2. Binary PE security mitigations (ASLR, DEP, Control Flow Guard).
3. Manifest integrity and hash verification.
4. PrivacyFilter redaction of OAuth access tokens, refresh tokens, private keys, and passwords.
5. Codebase hygiene: zero hardcoded provider paths in production code.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
import re
from unittest.mock import patch
import pytest

from core.provider_resolver import (
    resolve_provider,
    verify_provider,
    inspect_pe_mitigations,
    load_manifest,
    ProviderNotFoundError,
)
from core.logging_config import PrivacyFilter, configure_logging, log_sanitized_error


# ==============================================================================
# 1. Provider Resolver Search Order & Overrides
# ==============================================================================

def test_resolve_provider_invalid_name():
    with pytest.raises(ValueError, match="Unknown provider"):
        resolve_provider("invalid-provider")


def test_resolve_provider_env_var_override(tmp_path: Path):
    fake_exe = tmp_path / "custom-provider.exe"
    fake_exe.write_bytes(b"MZ" + b"\x00" * 100)

    with patch.dict("os.environ", {"QUMAIL_M5_PROVIDER_PATH": str(fake_exe)}):
        resolved = resolve_provider("qumail-m5-provider")
        assert resolved == fake_exe.resolve()


def test_resolve_provider_env_var_not_found():
    with patch.dict("os.environ", {"QUMAIL_M5_PROVIDER_PATH": "C:\\nonexistent\\provider.exe"}):
        with pytest.raises(ProviderNotFoundError, match="no file was found at specified location"):
            resolve_provider("qumail-m5-provider")


def test_resolve_provider_default_finds_staged_bin():
    """Default resolution without env vars must resolve to bin/qumail-*.exe."""
    m3_path = resolve_provider("qumail-m3-provider")
    m5_path = resolve_provider("qumail-m5-provider")

    assert m3_path.is_file()
    assert m5_path.is_file()
    assert "bin" in m3_path.parts
    assert "bin" in m5_path.parts


def test_resolve_provider_failure_diagnostic_message(tmp_path: Path):
    """When no provider exists anywhere, ProviderNotFoundError contains actionable build instructions."""
    with patch("core.provider_resolver.get_application_root", return_value=tmp_path), \
         patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ProviderNotFoundError) as exc_info:
            resolve_provider("qumail-m5-provider")
        
        msg = str(exc_info.value)
        assert "qumail-m5-provider" in msg
        assert "tools/build_providers.ps1" in msg
        assert "QUMAIL_M5_PROVIDER_PATH" in msg


# ==============================================================================
# 2. Native Engine PE Security Mitigations & Manifest Integrity
# ==============================================================================

def test_manifest_loads_and_contains_both_providers():
    manifest = load_manifest()
    assert manifest is not None
    assert "providers" in manifest
    assert "qumail-m3-provider" in manifest["providers"]
    assert "qumail-m5-provider" in manifest["providers"]

    assert "x86_64-pc-windows-msvc" in manifest["toolchain"]
    assert manifest["build_profile"] == "release"
    assert "control-flow-guard" in manifest["rustflags"]

    m5_data = manifest["providers"]["qumail-m5-provider"]
    assert m5_data["binary"] == "qumail-m5-provider.exe"
    assert m5_data["pe_mitigations"]["guard_cf_control_flow_guard"] is True


def test_staged_providers_pe_security_mitigations():
    """Verify that both staged binaries meet enterprise Windows exploit mitigation standards."""
    for provider in ("qumail-m3-provider", "qumail-m5-provider"):
        path = resolve_provider(provider)
        mitigations = inspect_pe_mitigations(path)

        assert mitigations["is_pe"], f"{provider} is not a valid PE binary"
        assert mitigations["is_pe32_plus"], f"{provider} is not a 64-bit PE32+ binary"
        assert mitigations["machine"] == "x86_64", f"{provider} machine is not x86_64"
        assert mitigations["high_entropy_va_64bit_aslr"], f"{provider} missing 64-bit ASLR"
        assert mitigations["dynamic_base_aslr"], f"{provider} missing ASLR (DYNAMICBASE)"
        assert mitigations["nx_compat_dep"], f"{provider} missing DEP/NX (NXCOMPAT)"
        assert mitigations["guard_cf_control_flow_guard"], f"{provider} missing Control Flow Guard"
        assert mitigations["dll_characteristics"] == 0xc160


def test_verify_provider_validates_hash_against_manifest():
    for provider in ("qumail-m3-provider", "qumail-m5-provider"):
        info = verify_provider(provider)
        assert info["manifest_match"] is True
        assert len(info["sha256"]) == 64
        assert info["pe_mitigations"]["guard_cf_control_flow_guard"] is True


# ==============================================================================
# 3. PrivacyFilter & Structured Logging
# ==============================================================================

def test_privacy_filter_redacts_oauth_access_tokens():
    filt = PrivacyFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Sent with token Bearer ya29.a0AfH6SMB_secret_access_token_12345 in header",
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert "ya29.a0AfH6SMB_secret_access_token_12345" not in record.msg
    assert "[REDACTED_OAUTH_TOKEN]" in record.msg


def test_privacy_filter_redacts_refresh_tokens():
    filt = PrivacyFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Refresh token: 1//04abcdefghij1234567890_KLMNOP",
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert "1//04abcdefghij1234567890_KLMNOP" not in record.msg
    assert "[REDACTED_REFRESH_TOKEN]" in record.msg


def test_privacy_filter_redacts_private_key_blocks():
    filt = PrivacyFilter()
    raw = (
        "Here is key:\n"
        "-----BEGIN ED25519 PRIVATE KEY-----\n"
        "MC4CAQAwBQYDK2VwBCIEIP...secret_bytes...\n"
        "-----END ED25519 PRIVATE KEY-----\n"
        "end of log"
    )
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg=raw,
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert "secret_bytes" not in record.msg
    assert "[REDACTED_PRIVATE_KEY_BLOCK]" in record.msg


def test_privacy_filter_scrubs_formatted_arguments():
    filt = PrivacyFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="User %s auth with password %s and token %s",
        args=("alice@test.org", "password=SuperSecret123!", "Bearer ya29.foo_bar"),
        exc_info=None,
    )
    filt.filter(record)
    # Formatted message should not leak credentials
    formatted = record.getMessage()
    assert "SuperSecret123!" not in formatted
    assert "ya29.foo_bar" not in formatted


def test_log_sanitized_error_redacts_token_in_exception(caplog):
    test_logger = logging.getLogger("test_sanitized")
    test_logger.setLevel(logging.DEBUG)
    test_logger.addFilter(PrivacyFilter())
    
    try:
        raise ValueError("Failed connecting with token ya29.secret_token_val")
    except ValueError as exc:
        with caplog.at_level(logging.DEBUG):
            log_sanitized_error(test_logger, "Operation error", exc)
    
    assert "ya29.secret_token_val" not in caplog.text
    assert "[REDACTED_OAUTH_TOKEN]" in caplog.text


# ==============================================================================
# 4. Codebase Hygiene: Zero Hardcoded Provider Paths in Production
# ==============================================================================

def test_no_hardcoded_tmp_provider_paths_in_production_modules():
    """
    Ensure no production module references 'tmp/cargo-build', 'target/debug',
    or hardcoded provider paths directly.
    """
    repo_root = Path(__file__).resolve().parent.parent
    checked_dirs = [
        repo_root / "core",
        repo_root / "mailbox_client",
        repo_root / "ui",
        repo_root / "transport",
    ]
    checked_files = [repo_root / "main.py"]

    for d in checked_dirs:
        for py in d.rglob("*.py"):
            checked_files.append(py)

    hardcoded_patterns = [
        re.compile(r'tmp[/\\]cargo-build[/\\]qumail', re.IGNORECASE),
        re.compile(r'tmp/cargo-build', re.IGNORECASE),
        re.compile(r'target[/\\]debug[/\\]qumail', re.IGNORECASE),
    ]

    violations = []
    for f in checked_files:
        # Exclude provider_resolver.py which contains fallback search paths
        if f.name == "provider_resolver.py":
            continue
        text = f.read_text(encoding="utf-8")
        for pat in hardcoded_patterns:
            matches = pat.findall(text)
            if matches:
                violations.append(f"{f.relative_to(repo_root)}: matched '{matches[0]}'")

    assert not violations, f"Hardcoded provider paths found in production code:\n" + "\n".join(violations)
