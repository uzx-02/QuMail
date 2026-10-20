# main.py — QuMail desktop entry point.
# Single responsibility: initialize QApplication and launch MainWindow.
# Starts the development key simulator only with --dev-simulator.
# Does not contain business logic, transport calls, or direct crypto operations.

import argparse
import sys
import threading


def _start_kme_server() -> None:
    """
    Start the virtual KME Flask server in a background daemon thread.

    Uses werkzeug's threaded WSGI server via Flask's built-in run().
    The thread is marked daemon so it terminates automatically with the
    main process — no explicit shutdown is needed.

    Called only for explicit laboratory startup. The first status poll can
    precede server readiness; HTTP liveness does not establish real QKD.
    """
    try:
        from kme.virtual_node import app
        from core.config import KME_HOST, KME_PORT

        import logging
        # Silence Flask/werkzeug startup chatter — it pollutes the terminal.
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.ERROR)

        app.run(host=KME_HOST, port=KME_PORT, debug=False, use_reloader=False)
    except Exception as exc:
        # Non-fatal: the UI still launches; status bar shows Offline.
        print(f"[KME] Virtual node failed to start: {exc}")


def _launch_desktop() -> int:
    from PyQt6.QtWidgets import QApplication
    from ui.main_window import MainWindow

    app = QApplication([sys.argv[0]])
    window = MainWindow()
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    """Launch the development client; simulator startup requires explicit opt-in."""
    parser = argparse.ArgumentParser(description="QuMail 1.0 development prototype; not production-ready")
    parser.add_argument("--dev-simulator", action="store_true",
                        help="start unauthenticated loopback CSPRNG simulator (not real QKD)")
    parser.add_argument('--dev-identity',action='store_true',help='isolated M3 Settings; all sending disabled')
    parser.add_argument('--dev-mailbox',action='store_true',help='Gmail-first development mail; submission disabled by default')
    parser.add_argument('--dev-gmail-submit',action='store_true',help='explicitly enable development Gmail SMTP submission')
    parser.add_argument('--dev-vault',help='explicit development SQLite vault path (no legacy migration)')
    parser.add_argument('--google-client',help='explicit provisioned Google Desktop test-client JSON')
    args = parser.parse_args(argv)
    if args.dev_mailbox:
        if args.dev_identity or args.dev_simulator or not args.dev_vault:
            parser.error('--dev-mailbox requires --dev-vault and excludes other development modes')
        if args.dev_gmail_submit: return _launch_mailbox(args.dev_vault,args.google_client,True)
        return _launch_mailbox(args.dev_vault,args.google_client)
    if args.dev_gmail_submit: parser.error('--dev-gmail-submit requires --dev-mailbox')
    if args.dev_identity:
        if args.dev_simulator or not args.dev_vault:
            parser.error('--dev-identity requires --dev-vault and cannot start the simulator')
        return _launch_identity(args.dev_vault,args.google_client)
    if args.dev_vault or args.google_client:
        parser.error('--dev-vault and --google-client require --dev-identity or --dev-mailbox')
    if args.dev_simulator:
        print("Development simulator enabled: CSPRNG keys, no caller authentication, no real QKD.")
        threading.Thread(target=_start_kme_server, daemon=True, name="qumail-dev-simulator").start()
    return _launch_desktop()


def _launch_identity(vault,client):
    from pathlib import Path
    from PyQt6.QtWidgets import QApplication
    from core.identity_service import IdentityService
    from ui.identity_settings import IdentitySettings
    app=QApplication([sys.argv[0]])
    helper=Path(__file__).parent/'tmp/m2/target/debug/qumail-m3-provider.exe'
    service=IdentityService.configured(vault,helper,client)
    window=IdentitySettings(service); window.show()
    return app.exec()


def _launch_mailbox(vault,client,gmail_enabled=False):
    from pathlib import Path
    from PyQt6.QtWidgets import QApplication
    from core.identity_service import IdentityService
    from transport.development_google import GoogleAuthorization,client_configuration,SCOPES
    from mailbox_client.gmail import MAIL_SCOPE
    from ui.mailbox_window import MailboxWindow
    app=QApplication([sys.argv[0]])
    helper=Path(__file__).parent/'tmp/m2/target/debug/qumail-m3-provider.exe'
    service=IdentityService.configured(vault,helper)
    if client:
        service.google=GoogleAuthorization(client_configuration(client),SCOPES+(MAIL_SCOPE,))
    window=MailboxWindow(service,gmail_enabled=gmail_enabled); window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
