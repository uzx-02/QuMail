"""
QuMail Enterprise Group Policy (GPO) Reader & Administrative Configuration.

Reads and enforces enterprise policies from machine-level Windows Registry:
  HKLM\\SOFTWARE\\Policies\\QuMail
with secondary administrative fallback from:
  %PROGRAMDATA%\\QuMail\\policies.json

SECURITY INVARIANTS:
1. Machine-level administrator policies CANNOT be overridden by user-level
   configuration (HKCU or local JSON).
2. Enterprise trust anchors require cryptographic verification (SHA-256 fingerprint
   or certified certificate), not claimed string labels.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

logger = logging.getLogger("qumail.enterprise_policy")

GPO_REGISTRY_KEY = r"SOFTWARE\Policies\QuMail"
PROGRAMDATA_POLICY_PATH = Path(os.path.expandvars(r"%PROGRAMDATA%\QuMail\policies.json"))


class PolicyError(Exception):
    """Base error for enterprise policy operations."""
    pass


@dataclass
class EnterprisePolicy:
    """
    Enforced enterprise settings configured by IT administrators.
    """
    # Organization Trust & Domain Constraints
    allowed_domains: list[str] = field(default_factory=list)
    managed_trust_anchors: dict[str, str] = field(default_factory=dict)  # domain -> cert SHA-256 fingerprint
    block_external_accounts: bool = False
    enforce_strict_encryption: bool = True

    # Application & Updates
    update_channel: str = "Production"  # "Production", "LTS", "Beta"
    update_server_url: str = "https://updates.qumail.enterprise.invalid/v1"
    disable_auto_updates: bool = False
    disable_legacy_simulator: bool = True

    # Logging & Diagnostics
    log_level: str = "INFO"  # "DEBUG", "INFO", "WARNING", "ERROR"
    allow_diagnostics_export: bool = True
    allow_remote_telemetry: bool = False

    # Administrative Metadata
    policy_source: str = "DEFAULT"  # "REGISTRY_HKLM", "PROGRAMDATA_FILE", "DEFAULT"
    is_managed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: str = "CUSTOM") -> EnterprisePolicy:
        # Validate trust anchors
        raw_anchors = data.get("managed_trust_anchors", {})
        validated_anchors = {}
        for domain, fp in raw_anchors.items():
            clean_fp = fp.replace(":", "").replace(" ", "").lower()
            if len(clean_fp) != 64 or not all(c in "0123456789abcdef" for c in clean_fp):
                logger.warning("Rejecting invalid trust anchor fingerprint for domain %s: %s", domain, fp)
                continue
            validated_anchors[domain.lower().strip()] = clean_fp

        return cls(
            allowed_domains=[d.lower().strip() for d in data.get("allowed_domains", []) if d.strip()],
            managed_trust_anchors=validated_anchors,
            block_external_accounts=bool(data.get("block_external_accounts", False)),
            enforce_strict_encryption=bool(data.get("enforce_strict_encryption", True)),
            update_channel=data.get("update_channel", "Production"),
            update_server_url=data.get("update_server_url", "https://updates.qumail.enterprise.invalid/v1"),
            disable_auto_updates=bool(data.get("disable_auto_updates", False)),
            disable_legacy_simulator=bool(data.get("disable_legacy_simulator", True)),
            log_level=data.get("log_level", "INFO"),
            allow_diagnostics_export=bool(data.get("allow_diagnostics_export", True)),
            allow_remote_telemetry=bool(data.get("allow_remote_telemetry", False)),
            policy_source=source,
            is_managed=(source != "DEFAULT"),
        )


class EnterprisePolicyManager:
    """
    Loads, validates, and evaluates enterprise policies.
    """

    def __init__(self, override_policy: EnterprisePolicy | None = None):
        self._policy = override_policy or self._load_policy()

    @property
    def policy(self) -> EnterprisePolicy:
        return self._policy

    def reload(self) -> EnterprisePolicy:
        self._policy = self._load_policy()
        return self._policy

    def _load_policy(self) -> EnterprisePolicy:
        """
        Priority order:
        1. Windows Registry: HKLM\\SOFTWARE\\Policies\\QuMail (administrator GPO)
        2. Machine File: %PROGRAMDATA%\\QuMail\\policies.json
        3. Default safe enterprise baseline
        """
        # 1. Try Windows Registry (HKLM)
        if sys.platform == "win32":
            reg_policy = self._read_hklm_registry()
            if reg_policy:
                return EnterprisePolicy.from_dict(reg_policy, source="REGISTRY_HKLM")

        # 2. Try ProgramData JSON
        if PROGRAMDATA_POLICY_PATH.is_file():
            try:
                data = json.loads(PROGRAMDATA_POLICY_PATH.read_text(encoding="utf-8"))
                return EnterprisePolicy.from_dict(data, source="PROGRAMDATA_FILE")
            except Exception as e:
                logger.error("Failed to read enterprise policies from %s: %e", PROGRAMDATA_POLICY_PATH, e)

        # 3. Default safe baseline
        return EnterprisePolicy(policy_source="DEFAULT", is_managed=False)

    def _read_hklm_registry(self) -> dict[str, Any] | None:
        """Read policy values from HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\QuMail."""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, GPO_REGISTRY_KEY, 0, winreg.KEY_READ) as key:
                data: dict[str, Any] = {}
                num_values = winreg.QueryInfoKey(key)[1]
                for i in range(num_values):
                    name, val, val_type = winreg.EnumValue(key, i)
                    # Convert DWORD 0/1 to bool
                    if val_type == winreg.REG_DWORD:
                        data[name] = bool(val)
                    elif val_type == winreg.REG_SZ:
                        # Attempt JSON decode for complex structures (lists/dicts)
                        if val.startswith("{") or val.startswith("["):
                            try:
                                data[name] = json.loads(val)
                            except Exception:
                                data[name] = val
                        else:
                            data[name] = val
                    else:
                        data[name] = val
                return data
        except FileNotFoundError:
            # Policy key does not exist (unmanaged workstation)
            return None
        except Exception as e:
            logger.warning("Could not read HKLM policy registry key: %s", e)
            return None

    def is_domain_allowed(self, email_address: str) -> bool:
        """Evaluate if an email address is authorized under corporate policy."""
        if not self._policy.allowed_domains:
            # No restriction configured
            return True
        domain = email_address.split("@")[-1].lower().strip()
        return domain in self._policy.allowed_domains

    def is_trust_anchor_verified(self, domain: str, cert_fingerprint: str) -> bool:
        """
        Verify if a remote domain's signing certificate matches an administratively
        provisioned enterprise trust anchor.
        """
        clean_domain = domain.lower().strip()
        expected_fp = self._policy.managed_trust_anchors.get(clean_domain)
        if not expected_fp:
            return False
        clean_actual = cert_fingerprint.replace(":", "").replace(" ", "").lower()
        return clean_actual == expected_fp
