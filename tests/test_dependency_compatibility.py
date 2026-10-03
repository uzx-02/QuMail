"""Exercise used APIs after the advisory-driven cryptography update."""
from pathlib import Path

from cryptography import x509
from cryptography.fernet import Fernet


def test_fernet_wrap_unwrap_roundtrip():
    wrapper = Fernet(Fernet.generate_key())
    assert wrapper.decrypt(wrapper.encrypt(b"fixture-only-secret")) == b"fixture-only-secret"


def test_local_legacy_certificate_generation_api(monkeypatch, tmp_path):
    from portal import portal_server
    monkeypatch.setattr(portal_server.tempfile, "mkdtemp", lambda: str(tmp_path))
    certificate, key = portal_server._generate_tls_cert()
    parsed = x509.load_pem_x509_certificate(Path(certificate).read_bytes())
    assert parsed.public_key().key_size == 2048
    assert Path(key).is_file()
    # This tests API compatibility, not trusted TLS deployment (F14 remains open).
