"""tests/test_mime.py — Unit tests for MIME encapsulation/decapsulation."""

import unittest

from mime.encapsulator import encapsulate
from mime.decapsulator import decapsulate


class TestMime(unittest.TestCase):
    """Ensures QuMail MIME round-trip preserves payload and metadata."""

    def test_encapsulate_decapsulate_roundtrip(self) -> None:
        ciphertext = b"\x00\x01\x02payload"
        metadata = {"tqr_level": 2, "key_id": "abc", "nonce": "01", "tag": "02"}
        msg = encapsulate(
            sender="alice@example.com",
            recipient="bob@example.com",
            subject="s",
            ciphertext=ciphertext,
            metadata=metadata,
        )
        out_cipher, out_meta = decapsulate(msg)
        self.assertEqual(out_cipher, ciphertext)
        self.assertEqual(out_meta["tqr_level"], 2)
        self.assertEqual(out_meta["key_id"], "abc")


if __name__ == "__main__":
    unittest.main()
