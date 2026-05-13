"""tests/test_tqr_roundtrip.py — End-to-end TQR encrypt/decrypt roundtrip tests.

Tests the full tqr.encrypt() → tqr.decrypt() pipeline for all three levels,
using a mocked KME client so no live KME is required. This verifies that
Levels 1 and 2 complete a full round-trip through the TQR dispatcher.

Item 7 from the v1 completion plan.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path for direct execution.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kme.key_models import QuantumKey


def _make_mock_key(sae_id: str, key_size_bits: int) -> QuantumKey:
    """Return a fresh deterministic QuantumKey for testing."""
    key_bytes = bytes([0xAB] * (key_size_bits // 8))
    return QuantumKey(
        key_id="test-key-uuid",
        key_value=key_bytes,
        sae_id=sae_id,
        issued_at="2026-01-01T00:00:00Z",
    )


class TestTQRRoundtrip(unittest.TestCase):
    """Verify that tqr.encrypt() and tqr.decrypt() are inverses for all levels."""

    PLAINTEXT = b"QuMail v1 roundtrip verification payload."

    def _roundtrip(self, level: int) -> None:
        """Helper: encrypt at given level then decrypt, check plaintext matches."""
        from crypto.tqr import encrypt, decrypt

        mock_key = _make_mock_key("test-sae", key_size_bits=len(self.PLAINTEXT) * 8 if level == 1 else 256)

        with patch("crypto.tqr.kme_client") as mock_client:
            mock_client.request_key.return_value = mock_key
            mock_client.retrieve_key.return_value = mock_key

            result_dict, private_key = encrypt(
                plaintext=self.PLAINTEXT,
                tqr_level=level,
                sae_id="test-sae",
                recipient_is_qumail=True,
            )

        ciphertext = result_dict["ciphertext"]
        metadata   = result_dict["metadata"]

        self.assertIsInstance(ciphertext, bytes, "ciphertext must be bytes")
        self.assertNotEqual(ciphertext, self.PLAINTEXT, "ciphertext must differ from plaintext")
        self.assertEqual(metadata.get("tqr_level"), level, "metadata must record correct level")

        # Decrypt — Level 1/2 need the mock KME for key retrieval.
        with patch("crypto.tqr.kme_client") as mock_client:
            mock_client.request_key.return_value = mock_key
            mock_client.retrieve_key.return_value = mock_key

            recovered = decrypt(
                ciphertext=ciphertext,
                metadata=metadata,
                private_key=private_key,
            )

        self.assertEqual(recovered, self.PLAINTEXT, f"Level {level} plaintext mismatch after roundtrip")

    def test_level1_otp_roundtrip(self) -> None:
        """Level 1 OTP: encrypt then decrypt must recover original plaintext."""
        self._roundtrip(level=1)

    def test_level2_aes_roundtrip(self) -> None:
        """Level 2 AES-256-GCM: encrypt then decrypt must recover original plaintext."""
        self._roundtrip(level=2)

    def test_level3_mlkem_roundtrip(self) -> None:
        """Level 3 ML-KEM: encrypt then decrypt using returned private key."""
        try:
            import oqs  # noqa: F401
        except ImportError:
            self.skipTest("liboqs is not available in this test environment — skipping Level 3.")
        self._roundtrip(level=3)


if __name__ == "__main__":
    unittest.main()
