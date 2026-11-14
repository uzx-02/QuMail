# main.py — QuMail Desktop Entry Point.
# Single responsibility: parse application configuration and launch the modern React 19 + Microsoft Edge WebView2 client.
# All legacy PyQt6 code has been completely purged.

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys

from core.config import get_vault_path
from core.logging_config import configure_logging, get_logger
from core.provider_resolver import resolve_provider, verify_provider, ProviderNotFoundError

# Immunize SSLContext.__new__ against missing codex-rejected-cas.pem in Windows / PyInstaller environments
try:
    import ssl
    if not getattr(ssl.SSLContext, "_is_qumail_patched", False):
        from _ssl import _SSLContext

        def _safe_ssl_context_new(cls, protocol=None, *args, **kwargs):
            if protocol is None:
                protocol = getattr(ssl, "PROTOCOL_TLS_CLIENT", ssl.PROTOCOL_TLS)
            self = _SSLContext.__new__(cls, protocol)
            try:
                ssl_dir = os.path.dirname(getattr(ssl, "__file__", ""))
                pem_path = os.path.join(ssl_dir, "codex-rejected-cas.pem")
                if pem_path and os.path.isfile(pem_path):
                    _SSLContext.load_verify_locations(self, cafile=pem_path)
            except Exception:
                pass
            return self

        ssl.SSLContext.__new__ = _safe_ssl_context_new
        ssl.SSLContext._is_qumail_patched = True
except Exception:
    pass

logger = get_logger("bootstrap")


def _show_critical_error(title: str, message: str) -> None:
    """Log and print critical startup errors."""
    logger.critical("%s: %s", title, message)
    print(f"\n[ERROR] {title}\n{message}\n", file=sys.stderr)


def _launch_react_desktop(
    vault: str | Path | None = None,
    dev_mode: bool = False,
    port: int = 0,
    account: str = "",
) -> int:
    """Launch the modern React 19 + Microsoft Edge WebView2 desktop client."""
    try:
        resolve_provider("qumail-vault-provider")
    except ProviderNotFoundError as exc:
        _show_critical_error(
            "QuMail — Missing Cryptographic Engine",
            f"The native cryptographic provider is required but was not found.\n\n"
            f"{exc}\n\n"
            "Run 'powershell -File tools/build_providers.ps1' to compile it.",
        )
        return 1

    import launch_react_desktop
    import webview

    frontend_dist = launch_react_desktop.FRONTEND_DIST

    if dev_mode:
        target_url = "http://localhost:5173"
        logger.info("Connecting to Vite development server at %s", target_url)
    else:
        index_html = frontend_dist / "index.html"
        if not index_html.exists():
            _show_critical_error(
                "QuMail — Frontend Bundle Missing",
                f"Production frontend build not found at {frontend_dist}.\n"
                "Please build the React application first:\n"
                "  cd frontend\n"
                "  npm run build\n",
            )
            return 1

        srv_port = port if port > 0 else launch_react_desktop._find_free_port()
        launch_react_desktop.start_local_server(srv_port)
        target_url = f"http://127.0.0.1:{srv_port}/index.html"
        logger.info("Serving modern React frontend at %s", target_url)

    js_api = launch_react_desktop.QuMailJsApi(account_email=account, vault_path=vault)

    window = webview.create_window(
        title="QuMail 1.0 — Post-Quantum Secure Corporate Email",
        url=target_url,
        js_api=js_api,
        width=1280,
        height=840,
        min_size=(1024, 680),
        text_select=True,
        frameless=True,
        fullscreen=True,
    )
    if hasattr(js_api, "set_window"):
        js_api.set_window(window)

    logger.info("Launching Microsoft Edge WebView2 modern desktop shell...")
    webview.start(debug=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Primary application entry point."""
    parser = argparse.ArgumentParser(
        prog="qumail",
        description="QuMail 1.0 — Post-Quantum Secure Corporate Email Client (React 19 + Edge WebView2)",
    )

    # Configuration options
    parser.add_argument(
        "--vault",
        "--dev-vault",
        dest="vault",
        default="",
        help="explicit SQLite vault path (defaults to local/user vault)",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="connect to live Vite development server (http://localhost:5173)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="local HTTP loopback port for frontend distribution (0 = auto-select)",
    )
    parser.add_argument(
        "--account",
        type=str,
        default="",
        help="default email address to initialize",
    )
    parser.add_argument(
        "--dev-mailbox",
        action="store_true",
        help="launch modern mailbox client (default behavior)",
    )
    parser.add_argument(
        "--legacy-simulator",
        "--dev-simulator",
        dest="legacy_simulator",
        action="store_true",
        help="legacy simulator (purged; blocked by enterprise policy)",
    )
    parser.add_argument(
        "--check-provider",
        action="store_true",
        help="verify native cryptographic provider installation and security mitigations, then exit",
    )
    parser.add_argument(
        "--export-diagnostics",
        metavar="PATH",
        help="export privacy-safe operational support diagnostics to specified JSON file and exit",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="application logging severity level",
    )

    args = parser.parse_args(argv)

    # Load enterprise policy
    from core.enterprise_policy import EnterprisePolicyManager
    policy_mgr = EnterprisePolicyManager()
    active_policy = policy_mgr.policy

    # Legacy simulator block / purge handler
    if args.legacy_simulator:
        if active_policy.disable_legacy_simulator:
            _show_critical_error(
                "QuMail — Administrative Policy Block",
                "Launching the legacy prototype simulator is blocked by corporate Group Policy.",
            )
            return 1
        _show_critical_error(
            "QuMail — Legacy Simulator Removed",
            "The legacy PyQt6 simulator has been permanently purged from QuMail. Please use the modern React interface.",
        )
        return 1

    # Initialize centralized logging
    log_level = getattr(logging, args.log_level.upper(), getattr(logging, active_policy.log_level.upper(), logging.INFO))
    configure_logging(level=log_level)

    # Export diagnostics probe
    if args.export_diagnostics:
        from core.diagnostics import DiagnosticsCollector
        collector = DiagnosticsCollector(policy_manager=policy_mgr)
        out_p = Path(args.export_diagnostics).resolve()
        collector.export_bundle(out_p)
        print(f"Operational diagnostics exported successfully to: {out_p}")
        return 0

    # Quick diagnostic probe
    if args.check_provider:
        print("QuMail Native Provider Diagnostic Probe:")
        all_ok = True
        for prov_name in ("qumail-vault-provider", "qumail-crypto-provider"):
            try:
                info = verify_provider(prov_name)
                print(f"\n[OK] {prov_name}:")
                print(f"  Path: {info['path']}")
                print(f"  Size: {info['size_bytes']:,} bytes")
                print(f"  SHA-256: {info['sha256']}")
                pe = info.get("pe_mitigations", {})
                print(f"  64-bit ASLR: {pe.get('high_entropy_va_64bit_aslr')}")
                print(f"  DEP (NX):    {pe.get('nx_compat_dep')}")
                print(f"  CFG Guard:   {pe.get('guard_cf_control_flow_guard')}")
                print(f"  Manifest:    {info.get('manifest_match')}")
            except Exception as exc:
                print(f"\n[FAIL] {prov_name}: {exc}")
                all_ok = False
        return 0 if all_ok else 1

    # Safe vault path discovery
    vault_path = args.vault
    if not vault_path:
        local_dev_vault = Path("qumail_vault.sqlite").resolve()
        if local_dev_vault.is_file():
            vault_path = str(local_dev_vault)
        else:
            vault_path = str(get_vault_path())

    return _launch_react_desktop(
        vault=vault_path,
        dev_mode=args.dev,
        port=args.port,
        account=args.account,
    )


if __name__ == "__main__":
    raise SystemExit(main())
