# main.py — QuMail desktop entry point.
# Single responsibility: parse application configuration and launch the appropriate UI.
# Modern secure mailbox client is the default entry point.
# Starts the legacy development key simulator only with explicit --legacy-simulator / --dev-simulator.

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
import threading

from core.logging_config import configure_logging, get_logger
from core.provider_resolver import resolve_provider, verify_provider, ProviderNotFoundError

logger = get_logger("bootstrap")


def get_default_vault_path() -> Path:
    """Return the default operating-system vault path for the user."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "QuMail" / "vault.sqlite"
        return Path.home() / "AppData" / "Local" / "QuMail" / "vault.sqlite"
    return Path.home() / ".qumail" / "vault.sqlite"


def _start_kme_server() -> None:
    """
    Start the virtual KME Flask server in a background daemon thread.
    Called ONLY when explicit legacy simulator mode is requested.
    """
    try:
        from kme.virtual_node import app
        from core.config import KME_HOST, KME_PORT

        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)

        app.run(host=KME_HOST, port=KME_PORT, debug=False, use_reloader=False)
    except Exception as exc:
        logger.warning("Virtual KME node failed to start: %s", exc)


def _show_critical_error(title: str, message: str) -> None:
    logger.critical("%s: %s", title, message)
    print(f"\n[ERROR] {title}\n{message}\n", file=sys.stderr)
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is not None and "pytest" not in sys.modules:
            QMessageBox.critical(None, title, message)
    except Exception:
        pass


def _launch_desktop() -> int:
    """Launch the legacy research prototype MainWindow with prominent simulation disclaimers."""
    from PyQt6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([sys.argv[0]])
    window = MainWindow()
    window.show()
    return app.exec()


def _launch_identity(vault: str | Path, client: str | Path | None = None) -> int:
    """Launch isolated M3 Identity & Settings window."""
    from PyQt6.QtWidgets import QApplication
    from core.identity_service import IdentityService
    from ui.identity_settings import IdentitySettings

    try:
        helper = resolve_provider("qumail-m3-provider")
    except ProviderNotFoundError as exc:
        _show_critical_error(
            "QuMail — Missing Cryptographic Engine",
            f"The native cryptographic provider is required but was not found.\n\n"
            f"{exc}\n\n"
            "Run 'powershell -File tools/build_providers.ps1' to compile it.",
        )
        return 1

    app = QApplication.instance() or QApplication([sys.argv[0]])
    service = IdentityService.configured(vault, helper, client)
    window = IdentitySettings(service)
    app.aboutToQuit.connect(window.dispose)
    window.show()
    return app.exec()


def _launch_mailbox(vault: str | Path, client: str | Path | None = None, gmail_enabled: bool = False) -> int:
    """Launch the modern secure QuMail mailbox client."""
    from PyQt6.QtWidgets import QApplication
    from core.identity_service import IdentityService
    from transport.development_google import client_configuration, SCOPES
    from transport.bounded_google import BoundedGoogleAuthorization as GoogleAuthorization
    from mailbox_client.gmail import MAIL_SCOPE
    from ui.mailbox_window import MailboxWindow

    try:
        helper = resolve_provider("qumail-m3-provider")
    except ProviderNotFoundError as exc:
        _show_critical_error(
            "QuMail — Missing Cryptographic Engine",
            f"The native cryptographic provider is required but was not found.\n\n"
            f"{exc}\n\n"
            "Run 'powershell -File tools/build_providers.ps1' to compile it.",
        )
        return 1

    app = QApplication.instance() or QApplication([sys.argv[0]])
    service = IdentityService.configured(vault, helper)
    if client:
        service.google = GoogleAuthorization(client_configuration(client), SCOPES + (MAIL_SCOPE,))
    window = MailboxWindow(service, gmail_enabled=gmail_enabled)
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    """Primary application entry point."""
    parser = argparse.ArgumentParser(
        prog="qumail",
        description="QuMail 1.0 — Post-Quantum Secure Corporate Email Client",
    )

    # Mode selectors
    parser.add_argument(
        "--legacy-simulator",
        "--dev-simulator",
        action="store_true",
        dest="legacy_simulator",
        help="start unauthenticated loopback CSPRNG research simulator (NOT secure; lab research only)",
    )
    parser.add_argument(
        "--dev-identity",
        action="store_true",
        help="isolated M3 identity and key management settings; sending disabled",
    )
    parser.add_argument(
        "--dev-mailbox",
        action="store_true",
        help="launch modern secure mailbox client (default behavior if no mode specified)",
    )

    # Configuration options
    parser.add_argument(
        "--vault",
        "--dev-vault",
        dest="vault",
        help="explicit SQLite vault path (defaults to local/user vault)",
    )
    parser.add_argument(
        "--google-client",
        help="explicit provisioned Google Desktop client secrets JSON",
    )
    parser.add_argument(
        "--submit",
        "--dev-gmail-submit",
        action="store_true",
        dest="submit",
        help="enable live Gmail SMTP transmission (disabled by default in development)",
    )
    parser.add_argument(
        "--check-provider",
        action="store_true",
        help="verify native cryptographic provider installation and security mitigations, then exit",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="application logging severity level",
    )

    args = parser.parse_args(argv)

    # Initialize centralized logging
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    configure_logging(level=log_level)

    # Quick diagnostic probe
    if args.check_provider:
        print("QuMail Native Provider Diagnostic Probe:")
        all_ok = True
        for prov_name in ("qumail-m3-provider", "qumail-m5-provider"):
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

    # Legacy research simulator path (MUST be explicitly requested)
    if args.legacy_simulator:
        if args.dev_identity or args.dev_mailbox or args.vault:
            parser.error("--legacy-simulator is mutually exclusive with modern secure mailbox / vault modes")
        print("\n" + "=" * 70)
        print("[WARNING] RUNNING IN LEGACY RESEARCH SIMULATOR MODE")
        print("This mode uses unauthenticated loopback keys and contains known research limitations.")
        print("It is NOT the secure QuMail product.")
        print("=" * 70 + "\n")
        logger.warning("Launching legacy research simulator; QKD and authentication disabled.")
        threading.Thread(target=_start_kme_server, daemon=True, name="qumail-dev-simulator").start()
        return _launch_desktop()

    # Isolated identity / settings mode
    if args.dev_identity:
        if not args.vault:
            parser.error("--dev-identity requires --vault / --dev-vault")
        if args.submit:
            parser.error("--submit / --dev-gmail-submit is not supported in identity-only mode")
        return _launch_identity(args.vault, args.google_client)

    # Default and primary route: Modern Secure Mailbox Client
    # Discover vault path if not explicitly provided
    vault_path = args.vault
    if not vault_path:
        local_dev_vault = Path("qumail_vault.sqlite").resolve()
        default_sys_vault = get_default_vault_path()
        if local_dev_vault.is_file():
            vault_path = str(local_dev_vault)
        elif default_sys_vault.is_file():
            vault_path = str(default_sys_vault)
        else:
            vault_path = str(default_sys_vault)

    return _launch_mailbox(vault_path, args.google_client, gmail_enabled=args.submit)


if __name__ == "__main__":
    raise SystemExit(main())
