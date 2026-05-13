# core/session.py — Runtime session state. In-memory only (v1).
# This is the single object passed between modules to share live state.
# Do not persist this to disk. Do not import crypto or transport here.

from PyQt6.QtCore import QObject, pyqtSignal

from core.config import TQR_DEFAULT


class Session(QObject):
    account_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        # --- Account ---
        self._active_account: str | None = None     # e.g. "user@gmail.com"
        self.provider: str | None = None            # "gmail" or "yahoo"
        self.oauth_token: dict | None = None        # token dict from OAuth2 flow

        # --- KME ---
        self.kme_connected: bool = False            # True if virtual node is reachable
        self.kme_sae_id: str | None = None          # This client's registered SAE ID

        # --- Encryption ---
        self.tqr_level: int = TQR_DEFAULT           # Active TQR level for this session

        # --- Last Send ---
        self.last_key_uuid: str | None = None       # UUID of last key used
        self.last_cert_path: str | None = None      # Path to last generated cert

    @property
    def active_account(self) -> str | None:
        return self._active_account

    @active_account.setter
    def active_account(self, email: str | None) -> None:
        if self._active_account != email:
            self._active_account = email
            self.account_changed.emit(email or "")

    def reset(self):
        """Clear session state — called on logout or account switch."""
        self._active_account = None
        self.provider = None
        self.oauth_token = None
        self.kme_connected = False
        self.kme_sae_id = None
        self.tqr_level = TQR_DEFAULT
        self.last_key_uuid = None
        self.last_cert_path = None
        self.account_changed.emit("")


# Single shared instance imported by other modules.
session = Session()
