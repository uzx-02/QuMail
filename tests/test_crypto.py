"""tests/test_crypto.py — Unit tests for crypto modules and TQR entrypoint."""

import unittest

from kme.key_models import QuantumKey
from crypto.level1_otp import encrypt as otp_encrypt, decrypt as otp_decrypt
from crypto.level2_aes import encrypt as aes_encrypt, decrypt as aes_decrypt


class TestCrypto(unittest.TestCase):
    """Covers Level 1/2 round-trips and Level 3 TQR flow."""

    def test_level1_otp_roundtrip(self) -> None:
        key_bytes = b"\x10\x20\x30\x40"
        key = QuantumKey(key_id="k1", key_value=key_bytes, sae_id="sae-a", issued_at="now")
        plaintext = b"test"
        out = otp_encrypt(plaintext, key)
        recovered = otp_decrypt(out["ciphertext"], key)
        self.assertEqual(recovered, plaintext)
        self.assertEqual(out["metadata"]["tqr_level"], 1)

    def test_level2_aes_roundtrip(self) -> None:
        key = QuantumKey(key_id="k2", key_value=b"A" * 32, sae_id="sae-b", issued_at="now")
        plaintext = b"hello level2"
        out = aes_encrypt(plaintext, key)
        recovered = aes_decrypt(
            out["ciphertext"],
            key,
            nonce_hex=out["metadata"]["nonce"],
            tag_hex=out["metadata"]["tag"],
        )
        self.assertEqual(recovered, plaintext)
        self.assertEqual(out["metadata"]["tqr_level"], 2)

    def test_level3_tqr_roundtrip(self) -> None:
        try:
            import oqs  # noqa: F401
            from crypto.tqr import decrypt as tqr_decrypt, encrypt as tqr_encrypt
        except Exception:
            self.skipTest("liboqs is not available in this environment")

        plaintext = b"level3 message"
        result, private_key = tqr_encrypt(
            plaintext=plaintext,
            tqr_level=3,
            sae_id="unused-for-l3",
            recipient_is_qumail=True,
        )
        self.assertIsInstance(private_key, bytes)
        recovered = tqr_decrypt(
            ciphertext=result["ciphertext"],
            metadata=result["metadata"],
            private_key=private_key,
        )
        self.assertEqual(recovered, plaintext)


if __name__ == "__main__":
    unittest.main()
