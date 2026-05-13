"""tests/test_certificates.py — Unit tests for cert JSON and PDF export."""

import os
import tempfile
import unittest


class TestCertificates(unittest.TestCase):
    """Validates cert generation and PDF conversion from disk JSON."""

    def test_generate_and_export_pdf(self) -> None:
        try:
            from certificates.cert_generator import generate
            from certificates.pdf_export import export
            import certificates.cert_generator as cert_gen_mod
        except Exception:
            self.skipTest("Certificate dependencies are not available in this environment")

        with tempfile.TemporaryDirectory() as tmpdir:
            old_dir = cert_gen_mod.CERT_OUTPUT_DIR
            cert_gen_mod.CERT_OUTPUT_DIR = tmpdir
            try:
                cert, json_path = generate(
                    tqr_level=2,
                    key_id="key-uuid-1",
                    sender="alice@example.com",
                    recipient_email="bob@example.com",
                )
                self.assertTrue(os.path.exists(json_path))
                self.assertEqual(cert.tqr_level, 2)
                pdf_path = export(json_path)
                self.assertTrue(os.path.exists(pdf_path))
                self.assertTrue(pdf_path.endswith(".pdf"))
            finally:
                cert_gen_mod.CERT_OUTPUT_DIR = old_dir


if __name__ == "__main__":
    unittest.main()
