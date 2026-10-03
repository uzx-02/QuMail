"""tests/test_transport.py — Unit tests for transport-layer helpers."""

import os
import stat
import tempfile
import unittest
from unittest.mock import patch

from transport.recipient_check import check_recipient


class TestTransport(unittest.TestCase):
    """Covers recipient detection and secure token file creation behavior."""

    @patch("transport.recipient_check.kme_client.lookup_sae")
    def test_recipient_check_registered(self, mock_lookup) -> None:
        mock_lookup.return_value = (True, "sae-1")
        status = check_recipient("user@gmail.com")
        self.assertTrue(status.is_qumail)
        self.assertEqual(status.sae_id, "sae-1")

    def test_gmail_secure_permission_helper(self) -> None:
        import transport.oauth2_gmail as gmail_oauth
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gmail_token.json")
            gmail_oauth._ensure_secret_dir(path)
            with open(path, "w", encoding="utf-8") as f:
                f.write("{}")
            with patch.object(gmail_oauth.os, "chmod", wraps=os.chmod) as chmod:
                gmail_oauth._secure_file_permissions(path)
                chmod.assert_called_once_with(path, stat.S_IRUSR | stat.S_IWUSR)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            # Windows chmod does not establish a user-only ACL (F08 remains open).
            self.assertTrue(os.access(path, os.R_OK | os.W_OK))

    def test_yahoo_secure_permission_helper(self) -> None:
        import transport.oauth2_yahoo as yahoo_oauth
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "yahoo_token.json")
            yahoo_oauth._ensure_secret_dir(path)
            with open(path, "w", encoding="utf-8") as f:
                f.write("{}")
            with patch.object(yahoo_oauth.os, "chmod", wraps=os.chmod) as chmod:
                yahoo_oauth._secure_file_permissions(path)
                chmod.assert_called_once_with(path, stat.S_IRUSR | stat.S_IWUSR)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertTrue(os.access(path, os.R_OK | os.W_OK))


if __name__ == "__main__":
    unittest.main()
