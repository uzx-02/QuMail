"""Provider-upgrade regression checks; not proof of a secure mail protocol."""
import pytest

from crypto import level3_mlkem

pytestmark = pytest.mark.native_crypto


@pytest.mark.parametrize("mutation", ["wrong_key", "payload", "kem_ciphertext", "nonce", "tag"])
def test_research_provider_rejects_wrong_key_and_tampering(mutation):
    public, private = level3_mlkem.generate_keypair()
    encrypted = level3_mlkem.encrypt(b"M1 nonsensitive fixture", public, private)
    metadata = encrypted["metadata"].copy()
    payload = encrypted["ciphertext"]
    if mutation == "wrong_key":
        _, private = level3_mlkem.generate_keypair()
    elif mutation == "payload":
        payload = bytes([payload[0] ^ 1]) + payload[1:]
    else:
        value = bytes.fromhex(metadata[mutation])
        metadata[mutation] = (bytes([value[0] ^ 1]) + value[1:]).hex()
    with pytest.raises(level3_mlkem.MLKEMDecryptionError):
        level3_mlkem.decrypt(payload, private, metadata["kem_ciphertext"], metadata["nonce"], metadata["tag"])
