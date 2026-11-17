"""Regression tests for outbound URL trust boundaries."""

import pytest

from core.cloud_directory import _validated_https_url
from core.hsm.etsi_qkd import ETSI014Client, _validate_kme_url


@pytest.mark.parametrize("url", [
    "https://directory.example.test/api/v1",
    "https://directory.example.test/api/v1?mode=test",
])
def test_directory_accepts_direct_https_urls(url):
    assert _validated_https_url(url) == url


@pytest.mark.parametrize("url", [
    "http://directory.example.test/api/v1",
    "file:///etc/passwd",
    "ftp://directory.example.test/a",
    "https:///missing-host",
    "https://user:pass@directory.example.test/a",
])
def test_directory_rejects_untrusted_url_forms(url):
    with pytest.raises(ValueError):
        _validated_https_url(url)


def test_qkd_allows_only_explicit_loopback_http_simulator():
    assert _validate_kme_url("http://127.0.0.1:8443/api/v1").startswith("http://127.0.0.1")
    assert _validate_kme_url("https://kme.example.test/api/v1").startswith("https://")
    with pytest.raises(ValueError):
        ETSI014Client("http://kme.example.test/api/v1")
    with pytest.raises(ValueError):
        ETSI014Client("file:///tmp/kme")
