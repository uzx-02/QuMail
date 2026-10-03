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
    args = parser.parse_args(argv)
    if args.dev_simulator:
        print("Development simulator enabled: CSPRNG keys, no caller authentication, no real QKD.")
        threading.Thread(target=_start_kme_server, daemon=True, name="qumail-dev-simulator").start()
    return _launch_desktop()


if __name__ == "__main__":
    raise SystemExit(main())
