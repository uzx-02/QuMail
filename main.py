# main.py — QuMail desktop entry point.
# Single responsibility: initialize QApplication and launch MainWindow.
# Auto-starts the virtual KME Flask server in a daemon thread so the
# Quantum Network status is live as soon as the window appears.
# Does not contain business logic, transport calls, or direct crypto operations.

import sys
import threading
import time

from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow


def _start_kme_server() -> None:
    """
    Start the virtual KME Flask server in a background daemon thread.

    Uses werkzeug's threaded WSGI server via Flask's built-in run().
    The thread is marked daemon so it terminates automatically with the
    main process — no explicit shutdown is needed.

    Called once before the Qt event loop starts so the first KME status
    poll (fired by KeyStatusWidget on construction) hits a live server.
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


def main() -> int:
    """Start the QuMail desktop application and return the process exit code."""
    # --- Start virtual KME before UI ---
    kme_thread = threading.Thread(target=_start_kme_server, daemon=True, name="kme-virtual-node")
    kme_thread.start()

    # Give Flask ~600 ms to bind its port before the first Qt poll fires.
    # This is a best-effort warm-up; if the server isn't ready the widget
    # retries automatically every 5 minutes (and the user can hit Refresh).
    time.sleep(0.6)

    # --- Launch Qt app ---
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
