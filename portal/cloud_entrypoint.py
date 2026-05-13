# portal/cloud_entrypoint.py — Cloud Run entry point for the QuMail portal service.
# Single responsibility: start a plain HTTP server on port 8080 and serve requests
# through portal_server._PortalHandler.
#
# Cloud Run terminates TLS at the Google-managed load balancer — this server speaks
# plain HTTP internally. Do NOT call portal_server.start() here; that function is
# for local development only (it binds HTTPS with a self-signed cert).
#
# This file is only copied into the Docker image and only executed in cloud mode.
# It is never imported by the desktop application.
#
# Environment variables expected at runtime:
#   PORTAL_MODE              = "cloud"   (set in Cloud Run deploy command)
#   PORTAL_HOST              = "<cloud-run-service-url>"  (e.g. qumail-portal-xxxx.run.app)
#   PORTAL_COLLECTION        = "portal_sessions"          (optional override)
#   GOOGLE_CLOUD_PROJECT     = "<gcp-project-id>"         (optional — auto-detected from metadata)
#   GOOGLE_APPLICATION_CREDENTIALS  (not needed in Cloud Run — service identity is used)
#
# Do not import from transport/, mime/, certificates/, kme/, or ui/.

import logging
import os
from http.server import HTTPServer

# Ensure PORTAL_MODE is set before portal_server is imported so that the module-level
# _PORTAL_MODE constant is initialised to "cloud" immediately.
os.environ.setdefault("PORTAL_MODE", "cloud")

from portal.portal_server import _PortalHandler, _ReusableHTTPServer  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
_LOGGER = logging.getLogger(__name__)

# Cloud Run injects PORT env var; default to 8080 per Cloud Run convention.
_PORT = int(os.getenv("PORT", "8080"))
_HOST = "0.0.0.0"


def main() -> None:
    """Start the plain HTTP server and serve forever."""
    server = _ReusableHTTPServer((_HOST, _PORT), _PortalHandler)
    _LOGGER.info(
        "QuMail portal cloud entry point started on %s:%s (PORTAL_MODE=cloud).",
        _HOST, _PORT,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _LOGGER.info("Portal cloud entry point shutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
