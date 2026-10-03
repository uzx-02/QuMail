"""Pinned research-only OQS loader. Never builds or downloads native code.

0.16.0.1 has no disable-auto-install flag. Its version parser rejects the sentinel
below *before* running subprocesses. Pinning its source digest makes this a reviewed
boundary, not an assumption about future bindings. ADR 002 records this limitation.
"""
import ctypes
import hashlib
import importlib
from importlib import metadata
import os
from pathlib import Path
import sys
import threading

BINDING_VERSION = "0.16.0.1"
NATIVE_VERSION = "0.16.0"
BINDING_SOURCE_SHA256 = "307c2a35c2571585eb8eac5397bfd03e79c462e1c7dfc6e8e76694e8103b6255"
_NO_INSTALL = "qumail-runtime-install-forbidden"
_lock = threading.Lock()
_provider = None
ORIGINAL_BINDING_VERSION = "0.14.1"


class LegacyProviderUnavailable(RuntimeError):
    """No validated local research provider; never substitute another algorithm."""


def main(argv=None):
    """Report the blocked original pin or explicitly check the research lane."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="QuMail legacy provider availability; no installation")
    parser.add_argument("--research", action="store_true", help="check the separately pinned research pair")
    args = parser.parse_args(argv)
    report = {
        "original_binding": ORIGINAL_BINDING_VERSION,
        "original_status": "blocked: unavailable from PyPI at M1 verification; no live lookup performed",
        "historical_ciphertext_compatibility": "unverified",
        "production_approved": False,
    }
    if args.research:
        try:
            provider = load_oqs()
            report.update(research_status="available", binding=BINDING_VERSION, native=NATIVE_VERSION,
                          native_sha256=hashlib.sha256(Path(provider.native()._name).read_bytes()).hexdigest())
        except (LegacyProviderUnavailable, OSError) as exc:
            report.update(research_status="unavailable", reason=str(exc))
        print(json.dumps(report, indent=2))
        return 0 if report["research_status"] == "available" else 1
    print(json.dumps(report, indent=2))
    return 1


def load_oqs():
    global _provider
    with _lock:
        if _provider is not None:
            return _provider
        try:
            distribution = metadata.distribution("liboqs-python")
        except metadata.PackageNotFoundError as exc:
            raise LegacyProviderUnavailable("Install the locked research binding; native crypto is unavailable.") from exc
        if distribution.version != BINDING_VERSION:
            raise LegacyProviderUnavailable("Unapproved research binding version.")
        source = Path(distribution.locate_file("oqs/oqs.py"))
        try:
            source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
        except OSError as exc:
            raise LegacyProviderUnavailable("Reviewed research binding source is unavailable.") from exc
        if source_digest != BINDING_SOURCE_SHA256:
            raise LegacyProviderUnavailable("Research binding source does not match the reviewed digest.")

        root = os.environ.get("OQS_INSTALL_PATH")
        if not root or not Path(root).is_absolute():
            raise LegacyProviderUnavailable("Set OQS_INSTALL_PATH to the absolute pinned native build directory.")
        relative = {"win32": "bin/liboqs.dll", "linux": "lib/liboqs.so"}.get(sys.platform)
        if relative is None:
            raise LegacyProviderUnavailable("Native research provider is unvalidated on this platform.")
        library = Path(root) / relative
        if sys.platform == "win32" and not library.is_file():
            library = Path(root) / "bin/oqs.dll"  # MSVC name; MinGW uses liboqs.dll.
        if not library.is_file():
            raise LegacyProviderUnavailable("Pinned native OQS library is absent; runtime installation is forbidden.")
        try:
            native = ctypes.CDLL(str(library))
            native.OQS_version.restype = ctypes.c_char_p
            if native.OQS_version().decode("ascii") != NATIVE_VERSION:
                raise LegacyProviderUnavailable("Unapproved native OQS version.")
            if "oqs" in sys.modules:
                raise LegacyProviderUnavailable("OQS must be loaded through the QuMail research boundary first.")
            previous = os.environ.get("PYOQS_VERSION")
            os.environ["PYOQS_VERSION"] = _NO_INSTALL
            try:
                provider = importlib.import_module("oqs")
            finally:
                if previous is None:
                    os.environ.pop("PYOQS_VERSION", None)
                else:
                    os.environ["PYOQS_VERSION"] = previous
            loaded = Path(provider.native()._name)
            if not loaded.is_absolute() or loaded.resolve() != library.resolve():
                raise LegacyProviderUnavailable("OQS selected a library outside the explicit research build.")
            if provider.oqs_version() != NATIVE_VERSION or "ML-KEM-768" not in provider.get_enabled_kem_mechanisms():
                raise LegacyProviderUnavailable("Native provider does not supply the pinned ML-KEM capability.")
        except (OSError, ValueError, RuntimeError, SystemExit) as exc:
            raise LegacyProviderUnavailable("Native research provider failed validation; no fallback.") from exc
        _provider = provider
        return provider


if __name__ == "__main__":
    raise SystemExit(main())
