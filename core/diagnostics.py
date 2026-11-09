"""
QuMail Privacy-Safe Operational Diagnostics & Support Bundle Generator.

Collects non-sensitive operational diagnostics to aid IT support and enterprise
troubleshooting while guaranteeing strict zero-leakage of:
- Message bodies and headers
- Attachment contents
- Private keys and vault secrets
- OAuth tokens and passwords
- Sensitive contact communications
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any

from core.enterprise_policy import EnterprisePolicyManager
from core.packaging import (
    APPLICATION_NAME,
    APPLICATION_VERSION,
    get_application_root,
    inspect_pe_security_characteristics,
)
from core.provider_resolver import resolve_provider


@dataclass
class DiagnosticReport:
    """Structure of an exported privacy-safe diagnostic report."""
    generated_utc: str
    client: dict[str, Any]
    environment: dict[str, Any]
    providers: dict[str, Any]
    enterprise_policy: dict[str, Any]
    vault: dict[str, Any]
    mailbox_sync: dict[str, Any]
    outbox: dict[str, Any]
    privacy_guarantee: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


class DiagnosticsCollector:
    """
    Collects sanitized operational state for support staff.
    """

    def __init__(self, policy_manager: EnterprisePolicyManager | None = None):
        self.policy_manager = policy_manager or EnterprisePolicyManager()

    def collect(
        self,
        vault: Any | None = None,
        sync_state: str = "Unknown",
        outbox_items: list[Any] | None = None,
    ) -> DiagnosticReport:
        """Collect sanitized diagnostics snapshot."""
        now_utc = datetime.now(timezone.utc).isoformat()
        app_root = get_application_root()

        # 1. Client Metadata
        version_file = app_root / "version.json"
        commit_sha = "UNKNOWN"
        if version_file.is_file():
            try:
                vdata = json.loads(version_file.read_text(encoding="utf-8"))
                commit_sha = vdata.get("commit_sha", "UNKNOWN")
            except Exception:
                pass

        client_meta = {
            "app_name": APPLICATION_NAME,
            "version": APPLICATION_VERSION,
            "commit_sha": commit_sha,
            "app_root": str(app_root),
            "is_frozen": getattr(sys, "frozen", False),
        }

        # 2. Environment Information
        env_meta = {
            "os_name": os.name,
            "platform": sys.platform,
            "windows_version": platform.version(),
            "windows_release": platform.release(),
            "architecture": platform.machine(),
            "python_version": sys.version.split()[0],
        }

        # 3. Native Providers
        provider_meta: dict[str, Any] = {}
        for pname in ("qumail-m3-provider", "qumail-m5-provider"):
            try:
                p_path = resolve_provider(pname)
                pe_info = inspect_pe_security_characteristics(p_path)
                provider_meta[pname] = {
                    "available": True,
                    "path": str(p_path),
                    "size_bytes": p_path.stat().st_size,
                    "pe_mitigations": pe_info,
                }
            except Exception as e:
                provider_meta[pname] = {
                    "available": False,
                    "error": str(e),
                }

        # 4. Enterprise Policy
        pol = self.policy_manager.policy
        policy_meta = {
            "is_managed": pol.is_managed,
            "policy_source": pol.policy_source,
            "allowed_domains_count": len(pol.allowed_domains),
            "managed_trust_anchors_count": len(pol.managed_trust_anchors),
            "block_external_accounts": pol.block_external_accounts,
            "enforce_strict_encryption": pol.enforce_strict_encryption,
            "update_channel": pol.update_channel,
            "log_level": pol.log_level,
        }

        # 5. Vault Status (Sanitized: NO keys, NO secrets)
        vault_meta = {
            "available": vault is not None,
            "path": "[NONE]",
            "size_bytes": 0,
            "schema_version": 1,
        }
        if vault is not None and hasattr(vault, "_path"):
            vpath = Path(vault._path)
            vault_meta["path"] = str(vpath)
            if vpath.is_file():
                vault_meta["size_bytes"] = vpath.stat().st_size

        # 6. Synchronization Status
        sync_meta = {
            "state": sync_state,
        }

        # 7. Outbox Status (Sanitized: NO bodies, NO recipients)
        outbox_meta = {
            "total_items": 0,
            "counts_by_state": {},
        }
        if outbox_items is not None:
            outbox_meta["total_items"] = len(outbox_items)
            counts: dict[str, int] = {}
            for item in outbox_items:
                state_name = getattr(item, "state", "UNKNOWN")
                if hasattr(state_name, "value"):
                    state_name = state_name.value
                counts[str(state_name)] = counts.get(str(state_name), 0) + 1
            outbox_meta["counts_by_state"] = counts

        return DiagnosticReport(
            generated_utc=now_utc,
            client=client_meta,
            environment=env_meta,
            providers=provider_meta,
            enterprise_policy=policy_meta,
            vault=vault_meta,
            mailbox_sync=sync_meta,
            outbox=outbox_meta,
            privacy_guarantee=(
                "GUARANTEE: This diagnostic bundle contains zero private keys, passwords, "
                "OAuth credentials, message bodies, or attachment data."
            ),
        )

    def export_bundle(
        self,
        output_file: Path,
        vault: Any | None = None,
        sync_state: str = "Unknown",
        outbox_items: list[Any] | None = None,
    ) -> Path:
        """Export report to a local JSON file."""
        output_file = Path(output_file).resolve()
        output_file.parent.mkdir(parents=True, exist_ok=True)

        report = self.collect(vault=vault, sync_state=sync_state, outbox_items=outbox_items)
        output_file.write_text(report.to_json(), encoding="utf-8")
        return output_file
