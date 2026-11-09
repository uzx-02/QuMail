"""
WS-02 Security Assurance & Acceptance Suite.

Covers targeted security remediation required for WS-02 closeout:
1. Historical signature verification (distinguishing claimed time from trusted timestamp evidence,
   backdating defense, compromise handling).
2. WKD network security (SSRF IP validation, HTTPS-to-HTTP downgrade, redirect pinning,
   oversized payload ceiling, content-type checks, timeout handling, non-blocking execution).
3. Enterprise trust validation (Ed25519 admin signatures, domain scoping, revocation propagation,
   conflicting WKD resolution, policy unavailability).
4. Module 1.5 wire compatibility (complete inbound parsing, legacy signature verification,
   identity and replay check preservation, v1 profile roundtrip, unsupported profile rejection,
   no cryptographic downgrade).
"""

import datetime
import hashlib
import io
import ipaddress
from pathlib import Path
import socket
import ssl
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pyasn1.codec.der import decoder, encoder
from pyasn1.type import univ, useful
from pyasn1_modules import rfc2459, rfc3161, rfc5652

from core.enterprise_trust import (
    EnterpriseContactRecord,
    EnterpriseTrustDirectory,
    PolicyAuthType,
    TrustAnchor,
    compute_contact_authorization_payload,
)
from core.key_discovery import (
    DEFAULT_HTTP_TIMEOUT,
    CachedKeyDiscoveryService,
    DiscoveredKey,
    DiscoveryResult,
    DiscoveryStatus,
    SecurityError,
    WKDDiscoveryProvider,
    build_wkd_urls,
    is_ip_prohibited,
    secure_wkd_fetch,
    validate_domain,
)
from core.key_lifecycle import (
    HistoricalValidity,
    HistoricalVerificationResult,
    KeyStatus,
    RFC3161VerificationResult,
    RevocationReason,
    TimestampEvidence,
    TimestampEvidenceSource,
    is_signature_historically_valid,
    verify_historical_signature,
    verify_rfc3161_token_offline,
)
from core.security_indicators import BadgeLevel, IndicatorCode
from core.trust_engine import TrustDecision, TrustPolicyEngine, TrustState

# Module 1.5 Cryptographic Fixtures & Services
from experiments.m3.types import EmailAddress, UserId, KeyHandle
from experiments.m3.vault import Vault
from experiments.m4.model import AccountAccess, State
from experiments.m5 import mime
from experiments.m5.model import (
    PROFILE_LEGACY_M5,
    PROFILE_V1,
    SUPPORTED_PROFILES,
    Attachment,
    Budget,
    Code as M5Code,
    Draft,
    Failure as M5Failure,
    Replay,
)
from experiments.m5.provider import Provider as M5Provider
from experiments.m5.services import Compose, OpenMessage, encode_draft
from tests.test_cryptographic_roundtrip import crypto_env, IsolatedMemoryStore


# ============================================================================
# Section 1: Historical Signature Verification Tests
# ============================================================================

def test_historical_signature_valid_with_trusted_tsa_evidence():
    """1. Signature created before expiry with trustworthy RFC 3161 TSA evidence."""
    evidence = TimestampEvidence(
        source=TimestampEvidenceSource.RFC3161_TSA,
        verified_time_utc=1500,
        proof=b"mock-tsa-token",
        is_verified=True,
    )
    result = verify_historical_signature(
        claimed_signature_time_utc=1490,
        key_valid_from=1000,
        key_expires_at=2000,
        timestamp_evidence=evidence,
        current_time=3000,  # Key is now expired in current time
    )
    assert result.status == HistoricalValidity.VALID_HISTORICAL
    assert result.is_valid is True
    assert result.effective_time_utc == 1500
    assert result.evidence_source == TimestampEvidenceSource.RFC3161_TSA


def test_historical_signature_created_after_expiry():
    """2. Signature created after key expiry rejected even with evidence."""
    evidence = TimestampEvidence(
        source=TimestampEvidenceSource.RFC3161_TSA,
        verified_time_utc=2100,
        proof=b"mock-tsa-token",
        is_verified=True,
    )
    result = verify_historical_signature(
        claimed_signature_time_utc=2050,
        key_valid_from=1000,
        key_expires_at=2000,
        timestamp_evidence=evidence,
        current_time=3000,
    )
    assert result.status == HistoricalValidity.EXPIRED_AT_CREATION
    assert result.is_valid is False


def test_historical_signature_backdated_without_trusted_time_evidence():
    """3. Backdated signature claiming pre-expiry date rejected when key is currently expired."""
    result = verify_historical_signature(
        claimed_signature_time_utc=1500,  # Claims to be within validity window
        key_valid_from=1000,
        key_expires_at=2000,
        timestamp_evidence=None,  # No independent trusted evidence!
        current_time=3000,        # Key is currently expired!
    )
    # MUST NOT grant historical validity based solely on claimed signature creation-time
    assert result.status == HistoricalValidity.INDETERMINATE_NO_TRUSTED_TIME
    assert result.is_valid is False
    assert "backdating defense" in result.explanation.lower()


def test_historical_signature_predating_revocation_with_evidence():
    """4. Signature predating a revocation (key superseded) with trusted vault receipt evidence."""
    evidence = TimestampEvidence(
        source=TimestampEvidenceSource.AUTHENTICATED_RECEIPT,
        verified_time_utc=1300,
        proof="sha256-receipt-digest",
        is_verified=True,
    )
    result = verify_historical_signature(
        claimed_signature_time_utc=1290,
        key_valid_from=1000,
        key_expires_at=3000,
        revocation_timestamp=1400,
        revocation_reason=RevocationReason.KEY_SUPERSEDED,
        timestamp_evidence=evidence,
        current_time=2500,
    )
    assert result.status == HistoricalValidity.VALID_HISTORICAL
    assert result.is_valid is True
    assert result.effective_time_utc == 1300


def test_historical_signature_predating_revocation_without_evidence():
    """5. Signature claiming to predate revocation without trusted evidence is indeterminate."""
    result = verify_historical_signature(
        claimed_signature_time_utc=1300,  # Claims to predate revocation at 1400
        key_valid_from=1000,
        key_expires_at=3000,
        revocation_timestamp=1400,
        revocation_reason=RevocationReason.KEY_SUPERSEDED,
        timestamp_evidence=None,
        current_time=2500,
    )
    assert result.status == HistoricalValidity.INDETERMINATE_NO_TRUSTED_TIME
    assert result.is_valid is False


def test_historical_signature_created_after_revocation():
    """6. Signature created after revocation is explicitly rejected."""
    evidence = TimestampEvidence(
        source=TimestampEvidenceSource.RFC3161_TSA,
        verified_time_utc=1500,
        proof=b"token",
        is_verified=True,
    )
    result = verify_historical_signature(
        claimed_signature_time_utc=1450,
        key_valid_from=1000,
        key_expires_at=3000,
        revocation_timestamp=1400,
        revocation_reason=RevocationReason.KEY_SUPERSEDED,
        timestamp_evidence=evidence,
        current_time=2500,
    )
    assert result.status == HistoricalValidity.REVOKED_AT_CREATION
    assert result.is_valid is False


def test_historical_signature_missing_or_malformed_evidence():
    """7. Malformed, unverified, or contradictory timestamp evidence rejected."""
    unverified_evidence = TimestampEvidence(
        source=TimestampEvidenceSource.RFC3161_TSA,
        verified_time_utc=1500,
        proof=b"tampered",
        is_verified=False,
    )
    result = verify_historical_signature(
        claimed_signature_time_utc=1400,
        key_valid_from=1000,
        key_expires_at=2000,
        timestamp_evidence=unverified_evidence,
        current_time=3000,
    )
    assert result.status == HistoricalValidity.INVALID_EVIDENCE
    assert result.is_valid is False

    # Paradoxical evidence: claimed time postdates trusted timestamp
    paradox_evidence = TimestampEvidence(
        source=TimestampEvidenceSource.RFC3161_TSA,
        verified_time_utc=1200,
        proof=b"token",
        is_verified=True,
    )
    result2 = verify_historical_signature(
        claimed_signature_time_utc=1400,  # Claimed 1400 > token 1200!
        key_valid_from=1000,
        key_expires_at=2000,
        timestamp_evidence=paradox_evidence,
        current_time=3000,
    )
    assert result2.status == HistoricalValidity.INVALID_EVIDENCE
    assert result2.is_valid is False


def test_historical_signature_compromised_key_handling():
    """8. Key revoked due to compromise rejects post-compromise signatures; accepts proven prior receipts."""
    # Post-compromise evidence rejected
    evidence_after = TimestampEvidence(
        source=TimestampEvidenceSource.RFC3161_TSA,
        verified_time_utc=1600,
        proof=b"token",
        is_verified=True,
    )
    result_after = verify_historical_signature(
        claimed_signature_time_utc=1300,  # Attacker backdates claimed time
        key_valid_from=1000,
        key_expires_at=3000,
        revocation_timestamp=1500,
        revocation_reason=RevocationReason.KEY_COMPROMISED,
        timestamp_evidence=evidence_after,
        current_time=2000,
    )
    assert result_after.status == HistoricalValidity.KEY_COMPROMISED
    assert result_after.is_valid is False

    # Pre-compromise receipt strictly predating compromise is accepted
    evidence_before = TimestampEvidence(
        source=TimestampEvidenceSource.AUTHENTICATED_RECEIPT,
        verified_time_utc=1400,  # Strictly before compromise at 1500
        proof="prior-vault-hash",
        is_verified=True,
    )
    result_before = verify_historical_signature(
        claimed_signature_time_utc=1390,
        key_valid_from=1000,
        key_expires_at=3000,
        revocation_timestamp=1500,
        revocation_reason=RevocationReason.KEY_COMPROMISED,
        timestamp_evidence=evidence_before,
        current_time=2000,
    )
    assert result_before.status == HistoricalValidity.VALID_HISTORICAL
    assert result_before.is_valid is True


# ============================================================================
# Section 2: WKD Network Security & SSRF Protection Tests
# ============================================================================

def test_wkd_domain_sanitization_rejects_hostile_syntax():
    """Domain validator strictly rejects control chars, path traversal, colons, spaces, and credentials."""
    hostile_domains = [
        "company.com/../../evil",
        "localhost:8080",
        "127.0.0.1",
        "[::1]",
        "user:pass@company.com",
        "company.com\r\nInjected-Header: evil",
        "company .com",
        "company.com;rm -rf",
    ]
    for d in hostile_domains:
        with pytest.raises(ValueError):
            validate_domain(d)
        with pytest.raises(ValueError):
            build_wkd_urls(f"alice@{d}")


def test_ip_prohibited_filter():
    """Verify is_ip_prohibited catches all loopback, RFC 1918, link-local, carrier-NAT, and multicast IPs."""
    prohibited_ips = [
        "127.0.0.1", "127.0.0.53", "10.0.0.1", "10.254.0.1",
        "172.16.0.1", "172.31.255.254", "192.168.1.1", "169.254.169.254",
        "100.64.0.1", "224.0.0.1", "0.0.0.0", "240.0.0.1",
        "::1", "fe80::1", "fc00::1", "fd00::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1",
    ]
    for ip in prohibited_ips:
        assert is_ip_prohibited(ipaddress.ip_address(ip)) is True

    # Public internet IP should NOT be prohibited
    assert is_ip_prohibited(ipaddress.ip_address("93.184.216.34")) is False
    assert is_ip_prohibited(ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946")) is False


def test_secure_wkd_fetch_rejects_http_downgrade():
    """Insecure http:// URL must be immediately rejected."""
    with pytest.raises(SecurityError, match="HTTPS required"):
        secure_wkd_fetch("http://openpgpkey.company.com/key", expected_domain="company.com")


def test_secure_wkd_fetch_rejects_unauthorized_host():
    """URL pointing to a foreign domain must be immediately rejected."""
    with pytest.raises(SecurityError, match="outside authorized domain"):
        secure_wkd_fetch("https://evil.com/key", expected_domain="company.com")


def test_secure_wkd_fetch_rejects_ssrf_dns_resolution():
    """Destination resolving to loopback or private RFC 1918 IP raises SecurityError."""
    # Mock DNS resolving to loopback 127.0.0.1
    mock_dns_loopback = lambda host, port, proto: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    with pytest.raises(SecurityError, match="SSRF defense"):
        secure_wkd_fetch("https://openpgpkey.company.com/key", expected_domain="company.com", dns_resolver=mock_dns_loopback)

    # Mock DNS resolving to AWS metadata link-local 169.254.169.254
    mock_dns_metadata = lambda host, port, proto: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))]
    with pytest.raises(SecurityError, match="SSRF defense"):
        secure_wkd_fetch("https://openpgpkey.company.com/key", expected_domain="company.com", dns_resolver=mock_dns_metadata)


class MockTLSSocket:
    """Mock socket simulating HTTP response streams."""
    def __init__(self, response_bytes: bytes):
        self.stream = io.BytesIO(response_bytes)
        self.sent = bytearray()
        self.closed = False

    def sendall(self, data: bytes):
        self.sent.extend(data)

    def recv(self, size: int) -> bytes:
        return self.stream.read(size)

    def close(self):
        self.closed = True


class MockSSLContext:
    """Mock SSLContext wrapping our MockTLSSocket."""
    def wrap_socket(self, sock, server_hostname=None):
        return sock


def test_secure_wkd_fetch_redirect_to_http_rejected():
    """Redirect to HTTP scheme must be rejected during redirect revalidation."""
    redirect_resp = (
        b"HTTP/1.1 302 Found\r\n"
        b"Location: http://openpgpkey.company.com/hu/hash\r\n"
        b"Content-Length: 0\r\n\r\n"
    )
    mock_dns = lambda host, port, proto: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    mock_sock = MockTLSSocket(redirect_resp)

    with pytest.raises(SecurityError, match="HTTPS required"):
        secure_wkd_fetch(
            "https://openpgpkey.company.com/hu/hash",
            expected_domain="company.com",
            dns_resolver=mock_dns,
            ssl_context=MockSSLContext(),
            socket_factory=lambda addr, timeout: mock_sock,
        )


def test_secure_wkd_fetch_redirect_to_another_host_rejected():
    """Redirect to an external domain must be rejected during redirect revalidation."""
    redirect_resp = (
        b"HTTP/1.1 302 Found\r\n"
        b"Location: https://evil.com/hu/hash\r\n"
        b"Content-Length: 0\r\n\r\n"
    )
    mock_dns = lambda host, port, proto: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    mock_sock = MockTLSSocket(redirect_resp)

    with pytest.raises(SecurityError, match="outside authorized domain"):
        secure_wkd_fetch(
            "https://openpgpkey.company.com/hu/hash",
            expected_domain="company.com",
            dns_resolver=mock_dns,
            ssl_context=MockSSLContext(),
            socket_factory=lambda addr, timeout: mock_sock,
        )


def test_secure_wkd_fetch_oversized_payload_rejected():
    """Responses exceeding the 64 KiB ceiling are truncated and aborted."""
    # 70 KiB of body data
    oversized_data = b"A" * (70 * 1024)
    resp = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/octet-stream\r\n\r\n" + oversized_data
    )
    mock_dns = lambda host, port, proto: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    mock_sock = MockTLSSocket(resp)

    with pytest.raises(ValueError, match="exceeded maximum size limit"):
        secure_wkd_fetch(
            "https://openpgpkey.company.com/hu/hash",
            expected_domain="company.com",
            dns_resolver=mock_dns,
            ssl_context=MockSSLContext(),
            socket_factory=lambda addr, timeout: mock_sock,
        )


def test_secure_wkd_fetch_html_response_rejected():
    """HTML responses (e.g. captive portals, 200 OK web pages) are rejected."""
    html_resp = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/html; charset=utf-8\r\n\r\n"
        b"<!DOCTYPE html><html><body>Login Portal</body></html>"
    )
    mock_dns = lambda host, port, proto: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    mock_sock = MockTLSSocket(html_resp)

    with pytest.raises(ValueError, match="Prohibited content-type"):
        secure_wkd_fetch(
            "https://openpgpkey.company.com/hu/hash",
            expected_domain="company.com",
            dns_resolver=mock_dns,
            ssl_context=MockSSLContext(),
            socket_factory=lambda addr, timeout: mock_sock,
        )


def test_wkd_provider_timeout_and_network_error_handled_cleanly():
    """Network timeouts and connection errors return NETWORK_ERROR status without crashing."""
    def timeout_fetcher(url: str) -> bytes:
        raise TimeoutError("Connection to WKD endpoint timed out after 5.0s")

    provider = WKDDiscoveryProvider(http_fetcher=timeout_fetcher)
    res = provider.lookup("bob@company.com")
    assert res.ok is False
    assert res.status == DiscoveryStatus.NETWORK_ERROR
    assert "timed out" in res.error_message


def test_wkd_provider_lookup_async_non_blocking():
    """Asynchronous lookup returns a Future and does not block the calling thread."""
    def fast_fetcher(url: str) -> bytes:
        return b"valid-mock-key-bytes"

    provider = WKDDiscoveryProvider(http_fetcher=fast_fetcher)
    future = provider.lookup_async("bob@company.com")
    res = future.result(timeout=2.0)
    assert res.ok is True
    assert res.key is not None
    assert res.key.email == "bob@company.com"


# ============================================================================
# Section 3: Enterprise Trust Validation Tests
# ============================================================================

@pytest.fixture
def enterprise_admin_keys():
    """Generate an authentic Ed25519 corporate administrator keypair."""
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    return priv, pub


def test_enterprise_trust_valid_administrator_authorization(enterprise_admin_keys):
    """21. Valid administrator-authorized employee identity certified and verified."""
    priv, pub = enterprise_admin_keys
    anchor = TrustAnchor(
        anchor_id="anchor-corp-root",
        organization="Acme Corporation",
        domains=("acme.corp",),
        root_fingerprint="A"*40,
        admin_public_key=pub,
        auth_type=PolicyAuthType.CRYPTOGRAPHICALLY_SIGNED,
    )
    directory = EnterpriseTrustDirectory()
    directory.add_trust_anchor(anchor)

    # Admin signs the contact enrollment payload
    email = "alice@acme.corp"
    fingerprint = "F"*40
    key_bytes = b"pgp-key-alice"
    payload = compute_contact_authorization_payload("anchor-corp-root", email, fingerprint)
    sig = priv.sign(payload)

    rec = directory.register_certified_contact(
        email=email,
        fingerprint=fingerprint,
        public_key_bytes=key_bytes,
        anchor_id="anchor-corp-root",
        admin_signature=sig,
    )
    assert rec.email == email
    assert directory.is_certified_by_enterprise(email, fingerprint) is True


def test_enterprise_trust_invalid_or_missing_signature(enterprise_admin_keys):
    """22. Missing or invalid administrator signature is strictly rejected."""
    priv, pub = enterprise_admin_keys
    anchor = TrustAnchor(
        anchor_id="anchor-corp-root",
        organization="Acme Corporation",
        domains=("acme.corp",),
        root_fingerprint="A"*40,
        admin_public_key=pub,
        auth_type=PolicyAuthType.CRYPTOGRAPHICALLY_SIGNED,
    )
    directory = EnterpriseTrustDirectory()
    directory.add_trust_anchor(anchor)

    # 1. Missing signature
    with pytest.raises(ValueError, match="Missing administrator authorization signature"):
        directory.register_certified_contact(
            email="alice@acme.corp",
            fingerprint="F"*40,
            public_key_bytes=b"key",
            anchor_id="anchor-corp-root",
            admin_signature=None,
        )

    # 2. Corrupted signature
    with pytest.raises(ValueError, match="Invalid administrator authorization signature"):
        directory.register_certified_contact(
            email="alice@acme.corp",
            fingerprint="F"*40,
            public_key_bytes=b"key",
            anchor_id="anchor-corp-root",
            admin_signature=b"\x00"*64,
        )


def test_enterprise_trust_wrong_domain_rejected(enterprise_admin_keys):
    """23. Anchor for acme.corp cannot authorize external or unrelated domains."""
    priv, pub = enterprise_admin_keys
    anchor = TrustAnchor(
        anchor_id="anchor-corp-root",
        organization="Acme Corporation",
        domains=("acme.corp",),
        root_fingerprint="A"*40,
        admin_public_key=pub,
    )
    directory = EnterpriseTrustDirectory()
    directory.add_trust_anchor(anchor)

    sig = priv.sign(b"dummy")
    # Wrong domain: evil.com
    with pytest.raises(ValueError, match="does not authorize domain"):
        directory.register_certified_contact(
            email="attacker@evil.com",
            fingerprint="F"*40,
            public_key_bytes=b"key",
            anchor_id="anchor-corp-root",
            admin_signature=sig,
        )

    # Subdomain spoofing: acme.corp.attacker.com
    with pytest.raises(ValueError, match="does not authorize domain"):
        directory.register_certified_contact(
            email="attacker@acme.corp.attacker.com",
            fingerprint="F"*40,
            public_key_bytes=b"key",
            anchor_id="anchor-corp-root",
            admin_signature=sig,
        )


def test_enterprise_trust_tampered_employee_certificate(enterprise_admin_keys):
    """24. Employee certificate with tampered fingerprint is rejected."""
    priv, pub = enterprise_admin_keys
    anchor = TrustAnchor(
        anchor_id="anchor-corp-root",
        organization="Acme Corporation",
        domains=("acme.corp",),
        root_fingerprint="A"*40,
        admin_public_key=pub,
    )
    directory = EnterpriseTrustDirectory()
    directory.add_trust_anchor(anchor)

    # Signed for fingerprint A
    payload = compute_contact_authorization_payload("anchor-corp-root", "bob@acme.corp", "A"*40)
    sig = priv.sign(payload)

    # Attempt to register with tampered fingerprint B
    with pytest.raises(ValueError, match="Invalid administrator authorization signature"):
        directory.register_certified_contact(
            email="bob@acme.corp",
            fingerprint="B"*40,
            public_key_bytes=b"key",
            anchor_id="anchor-corp-root",
            admin_signature=sig,
        )


def test_enterprise_trust_conflicting_wkd_precedence(enterprise_admin_keys):
    """25. Enterprise directory takes precedence; conflicting public WKD key is overridden."""
    priv, pub = enterprise_admin_keys
    anchor = TrustAnchor(
        anchor_id="anchor-corp-root",
        organization="Acme Corporation",
        domains=("acme.corp",),
        root_fingerprint="A"*40,
        admin_public_key=pub,
    )
    directory = EnterpriseTrustDirectory()
    directory.add_trust_anchor(anchor)

    email = "charlie@acme.corp"
    corp_fp = "1"*40
    sig = priv.sign(compute_contact_authorization_payload("anchor-corp-root", email, corp_fp))
    directory.register_certified_contact(email, corp_fp, b"corp-key", "anchor-corp-root", sig)

    # Mock WKD returning a DIFFERENT (rogue/stale) key
    rogue_fp = "2"*40
    mock_discovery = CachedKeyDiscoveryService()
    mock_discovery.wkd.lookup = MagicMock(return_value=DiscoveryResult(
        email=email,
        status=DiscoveryStatus.SUCCESS,
        key=DiscoveredKey(email=email, public_key_bytes=b"rogue-key", fingerprint=rogue_fp, source="wkd"),
    ))

    engine = TrustPolicyEngine(discovery_service=mock_discovery, enterprise_directory=directory)
    decision = engine.evaluate_outbound_recipient(email)

    # Must choose the certified enterprise key, NOT the conflicting WKD key
    assert decision.state == TrustState.VERIFIED
    assert decision.fingerprint == corp_fp
    assert decision.is_identity_verified is True
    assert decision.indicator.badge_level == BadgeLevel.SECURE


def test_enterprise_trust_revoked_anchor_invalidates_all_contacts(enterprise_admin_keys):
    """26. Revoking an enterprise anchor immediately revokes all contacts under it."""
    priv, pub = enterprise_admin_keys
    anchor = TrustAnchor(
        anchor_id="anchor-corp-root",
        organization="Acme Corporation",
        domains=("acme.corp",),
        root_fingerprint="A"*40,
        admin_public_key=pub,
    )
    directory = EnterpriseTrustDirectory()
    directory.add_trust_anchor(anchor)

    sig = priv.sign(compute_contact_authorization_payload("anchor-corp-root", "alice@acme.corp", "A"*40))
    directory.register_certified_contact("alice@acme.corp", "A"*40, b"key", "anchor-corp-root", sig)
    assert directory.is_certified_by_enterprise("alice@acme.corp", "A"*40) is True

    # Revoke anchor
    directory.revoke_trust_anchor("anchor-corp-root")
    assert directory.is_certified_by_enterprise("alice@acme.corp", "A"*40) is False

    engine = TrustPolicyEngine(enterprise_directory=directory)
    decision = engine.evaluate_outbound_recipient("alice@acme.corp")
    assert decision.state == TrustState.VERIFICATION_FAILED
    assert decision.can_encrypt is False


def test_enterprise_trust_expired_or_revoked_contact_blocks_wkd_fallback(enterprise_admin_keys):
    """28. Expired or revoked enterprise contact blocks sending; silent WKD fallback is rejected."""
    priv, pub = enterprise_admin_keys
    anchor = TrustAnchor(
        anchor_id="anchor-corp-root",
        organization="Acme Corporation",
        domains=("acme.corp",),
        root_fingerprint="A"*40,
        admin_public_key=pub,
    )
    directory = EnterpriseTrustDirectory()
    directory.add_trust_anchor(anchor)

    email = "terminated@acme.corp"
    sig = priv.sign(compute_contact_authorization_payload("anchor-corp-root", email, "T"*40))
    # Register contact with revoked state
    rec = directory.register_certified_contact(email, "T"*40, b"key", "anchor-corp-root", sig)
    directory._contacts[email] = EnterpriseContactRecord(
        email=rec.email,
        fingerprint=rec.fingerprint,
        public_key_bytes=rec.public_key_bytes,
        authorized_by_anchor=rec.authorized_by_anchor,
        is_revoked=True,
    )

    # Even if WKD returns a public key for this address:
    mock_discovery = CachedKeyDiscoveryService()
    mock_discovery.wkd.lookup = MagicMock(return_value=DiscoveryResult(
        email=email,
        status=DiscoveryStatus.SUCCESS,
        key=DiscoveredKey(email=email, public_key_bytes=b"pub-key", fingerprint="W"*40, source="wkd"),
    ))

    engine = TrustPolicyEngine(discovery_service=mock_discovery, enterprise_directory=directory)
    decision = engine.evaluate_outbound_recipient(email)

    # Sending MUST be blocked; no silent fallback to WKD!
    assert decision.state == TrustState.VERIFICATION_FAILED
    assert decision.can_encrypt is False
    assert decision.indicator.code == IndicatorCode.KEY_REVOKED_OR_EXPIRED
    assert "public wkd fallback prohibited" in decision.reasons[0].lower()


def test_enterprise_trust_unavailable_policy_cannot_certify():
    """29. Unavailable enterprise policy directory cannot elevate any key to verified."""
    directory = EnterpriseTrustDirectory(is_available=False)
    assert directory.is_certified_by_enterprise("alice@acme.corp", "A"*40) is False
    assert directory.get_contact_record("alice@acme.corp") is None


# ============================================================================
# Section 4: Module 1.5 Wire Compatibility Tests (Native Provider)
# ============================================================================

def test_module_1_5_legacy_message_complete_inbound_parsing_and_verification(crypto_env):
    """
    30 & 31 & 32: Complete inbound parsing, signature verification, identity trust,
    and replay protection of an accepted Module 1.5 message (QM-OPENPGP-PQ-1-EXPERIMENT-M5).
    """
    vault = crypto_env["vault"]
    access = crypto_env["access"]
    p_m5 = crypto_env["p_m5"]
    ctx_alice, key_alice, addr_alice = crypto_env["alice"]
    ctx_bob, key_bob, addr_bob = crypto_env["bob"]

    lease_alice = access.select(ctx_alice)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    # 1. Alice drafts a message
    draft = Draft(
        to=(addr_bob,),
        cc=(),
        subject="Module 1.5 Acceptance Verification",
        body="Testing legacy M5 profile compatibility with modern parser.",
        attachments=(),
    )

    # Build raw inner message explicitly tagged with legacy M5 profile
    date_str = "Mon, 09 Nov 2026 12:00:00 +0000"
    msg_id = "<m15-compat-test-001@example.invalid>"

    # Use mime.build_inner, but customize to legacy profile
    inner_v1 = mime.build_inner(addr_alice, draft, msg_id, date_str)
    # Replace profile with legacy M5 profile
    inner_legacy = inner_v1.replace(
        f"X-QuMail-Profile: {PROFILE_V1}".encode("ascii"),
        f"X-QuMail-Profile: {PROFILE_LEGACY_M5}".encode("ascii"),
    )

    # Verify parse_inner accepts legacy profile
    sender, parsed_draft, ident, date, snapshots = mime.parse_inner(inner_legacy)
    assert sender == addr_alice
    assert parsed_draft.body == draft.body
    assert ident == msg_id

    # 2. Encrypt and sign using native Rust provider
    with vault.transaction(ctx_alice) as data_alice:
        alice_key_row = vault.key(data_alice, ctx_alice, key_alice, active=True)
        bob_public = vault.recipient(data_alice, EmailAddress(addr_bob))

    seal_res = p_m5.call(
        "seal",
        budget,
        certificate=bytes(alice_key_row["secret"]),
        recipients=[bob_public],
        data=inner_legacy,
    )
    legacy_armor = seal_res["data"]

    # Build outer wire envelope
    legacy_wire = mime.build_outer(addr_alice, draft, msg_id, date_str, legacy_armor)

    # 3. Bob opens and verifies the legacy message
    lease_bob = access.select(ctx_bob)
    opener = OpenMessage(vault, access, p_m5)

    alice_public = vault.export_public(ctx_alice, key_alice)
    opened = opener.open(lease_bob, key_bob, legacy_wire, alice_public, budget)

    # Verify complete cryptographic and identity properties
    assert opened.sender == addr_alice
    assert opened.subject == "Module 1.5 Acceptance Verification"
    assert opened.body == draft.body
    assert opened.signature_valid is True
    assert opened.identity_trust == "independently_verified"
    assert opened.replay == Replay.FRESH
    assert opened.mismatches == ()

    # 4. Duplicate replay detection
    opened_dup = opener.open(lease_bob, key_bob, legacy_wire, alice_public, budget)
    assert opened_dup.replay == Replay.DUPLICATE


def test_module_1_6_v1_profile_roundtrip(crypto_env):
    """33. New profile QM-OPENPGP-PQ-v1 complete native roundtrip."""
    vault = crypto_env["vault"]
    access = crypto_env["access"]
    p_m5 = crypto_env["p_m5"]
    ctx_alice, key_alice, addr_alice = crypto_env["alice"]
    ctx_bob, key_bob, addr_bob = crypto_env["bob"]

    lease_alice = access.select(ctx_alice)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    compose = Compose(vault, access, p_m5)
    draft = Draft(
        to=(addr_bob,),
        cc=(),
        subject="Modern V1 Profile Communication",
        body="Testing standard QM-OPENPGP-PQ-v1 roundtrip.",
        attachments=(Attachment("note.txt", "text/plain", b"Top Secret Payload"),),
    )

    op = compose.draft(lease_alice, draft, budget)
    envelope = compose.prepare(lease_alice, op, key_alice, budget)
    assert envelope.binding.profile == PROFILE_V1

    # Bob opens
    lease_bob = access.select(ctx_bob)
    opener = OpenMessage(vault, access, p_m5)
    alice_public = vault.export_public(ctx_alice, key_alice)

    opened = opener.open(lease_bob, key_bob, envelope.serialized, alice_public, budget)
    assert opened.signature_valid is True
    assert opened.identity_trust == "independently_verified"
    assert opened.replay == Replay.FRESH
    assert len(opened.attachments) == 1
    assert opened.attachments[0].name == "note.txt"
    assert opened.attachments[0].data == b"Top Secret Payload"


def test_unsupported_profile_strictly_rejected():
    """34. Unknown or spoofed profile markers rejected with Code.PROFILE."""
    draft = Draft(to=("bob@example.invalid",), cc=(), subject="Test", body="Body", attachments=())
    inner = mime.build_inner("alice@example.invalid", draft, "<test-01@example.invalid>", "Mon, 09 Nov 2026 12:00:00 +0000")

    # Replace profile with unsupported v99
    unsupported_inner = inner.replace(
        f"X-QuMail-Profile: {PROFILE_V1}".encode("ascii"),
        b"X-QuMail-Profile: QM-OPENPGP-PQ-UNSUPPORTED-v99",
    )
    with pytest.raises(M5Failure) as exc:
        mime.parse_inner(unsupported_inner)
    assert exc.value.code == M5Code.PROFILE


def test_contradictory_profile_metadata_rejected(crypto_env):
    """35. Mismatched or tampered inner profile header rejected."""
    draft = Draft(to=("bob@example.invalid",), cc=(), subject="Test", body="Body", attachments=())
    inner = mime.build_inner("alice@example.invalid", draft, "<test-02@example.invalid>", "Mon, 09 Nov 2026 12:00:00 +0000")

    # Corrupt profile header syntax
    corrupted_inner = inner.replace(
        b"X-QuMail-Profile:",
        b"X-QuMail-Profile-Malformed:",
    )
    with pytest.raises(M5Failure):
        mime.parse_inner(corrupted_inner)


def test_no_cryptographic_downgrade(crypto_env):
    """36. Tampered ciphertext or wrong sender key strictly rejected by native engine."""
    vault = crypto_env["vault"]
    access = crypto_env["access"]
    p_m5 = crypto_env["p_m5"]
    ctx_alice, key_alice, addr_alice = crypto_env["alice"]
    ctx_bob, key_bob, addr_bob = crypto_env["bob"]
    ctx_charlie, key_charlie, addr_charlie = crypto_env["charlie"]

    lease_alice = access.select(ctx_alice)
    budget = Budget(threading.Event(), time.monotonic() + 30)

    compose = Compose(vault, access, p_m5)
    draft = Draft(to=(addr_bob,), cc=(), subject="Downgrade Test", body="Secret", attachments=())
    op = compose.draft(lease_alice, draft, budget)
    envelope = compose.prepare(lease_alice, op, key_alice, budget)

    # Now Bob selects his lease to open
    lease_bob = access.select(ctx_bob)
    opener = OpenMessage(vault, access, p_m5)
    # Attempt to open using Charlie's public key instead of Alice's authentic key
    charlie_public = vault.export_public(ctx_charlie, key_charlie)
    with pytest.raises(M5Failure):
        opener.open(lease_bob, key_bob, envelope.serialized, charlie_public, budget)

    # Attempt to open tampered ciphertext
    tampered_wire = envelope.serialized.replace(b"A", b"B", 1)
    alice_public = vault.export_public(ctx_alice, key_alice)
    with pytest.raises(M5Failure):
        opener.open(lease_bob, key_bob, tampered_wire, alice_public, budget)


# ============================================================================
# Section 5: Offline RFC 3161 Verification & Historical Evidence Clarification
# ============================================================================

def _make_synthetic_rfc3161_token(
    message_digest: bytes,
    gen_time_dt: datetime.datetime | None = None,
    include_eku: bool = True,
    cert_valid_not_before_dt: datetime.datetime | None = None,
    cert_valid_not_after_dt: datetime.datetime | None = None,
    corrupt_sig: bool = False,
    custom_key: rsa.RSAPrivateKey | None = None,
    custom_cert: x509.Certificate | None = None,
    include_signed_attrs: bool = True,
    omit_content_type: bool = False,
    duplicate_content_type: bool = False,
    bad_content_type_oid: str | None = None,
    omit_message_digest: bool = False,
    duplicate_message_digest: bool = False,
    corrupt_message_digest_attr: bool = False,
    custom_digest_algo_oid: str = "2.16.840.1.101.3.4.2.1",
    custom_policy_oid: str = "1.2.3.4.5",
    extra_certs: list[x509.Certificate] | None = None,
    include_leaf_key_usage: bool = True,
    leaf_key_usage_digital_signature: bool = True,
    leaf_key_usage_content_commitment: bool = True,
    leaf_key_usage_key_cert_sign: bool = False,
    leaf_key_usage_crl_sign: bool = False,
) -> tuple[bytes, x509.Certificate, rsa.RSAPrivateKey]:
    """Helper to generate authentic or intentionally flawed RFC 3161 TimeStampToken DER bytes."""
    key = custom_key or rsa.generate_private_key(65537, 2048)

    if custom_cert is None:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        nb = cert_valid_not_before_dt or (now_utc - datetime.timedelta(days=1))
        na = cert_valid_not_after_dt or (now_utc + datetime.timedelta(days=1))
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test TSA")])
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(1001)
            .not_valid_before(nb)
            .not_valid_after(na)
        )
        if include_eku:
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]),
                critical=False,
            )
        if include_leaf_key_usage:
            builder = builder.add_extension(
                x509.KeyUsage(
                    digital_signature=leaf_key_usage_digital_signature,
                    content_commitment=leaf_key_usage_content_commitment,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=leaf_key_usage_key_cert_sign,
                    crl_sign=leaf_key_usage_crl_sign,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
        cert = builder.sign(key, hashes.SHA256())
    else:
        cert = custom_cert

    if gen_time_dt is None:
        gen_time_dt = datetime.datetime.now(datetime.timezone.utc)

    # 1. TSTInfo
    tst = rfc3161.TSTInfo()
    tst["version"] = 1
    tst["policy"] = univ.ObjectIdentifier(custom_policy_oid)
    tst["messageImprint"] = rfc3161.MessageImprint()
    tst["messageImprint"]["hashAlgorithm"] = rfc2459.AlgorithmIdentifier()
    tst["messageImprint"]["hashAlgorithm"]["algorithm"] = univ.ObjectIdentifier("2.16.840.1.101.3.4.2.1")
    tst["messageImprint"]["hashedMessage"] = message_digest
    tst["serialNumber"] = 1001
    tst["genTime"] = useful.GeneralizedTime(gen_time_dt.strftime("%Y%m%d%H%M%SZ"))
    tst_der = encoder.encode(tst)

    # 2. SignedData
    sd = rfc5652.SignedData()
    sd["version"] = 3
    sd["digestAlgorithms"] = rfc5652.DigestAlgorithmIdentifiers()
    da = rfc5652.DigestAlgorithmIdentifier()
    da["algorithm"] = univ.ObjectIdentifier(custom_digest_algo_oid)
    sd["digestAlgorithms"].append(da)

    sd["encapContentInfo"] = rfc5652.EncapsulatedContentInfo()
    sd["encapContentInfo"]["eContentType"] = rfc3161.id_ct_TSTInfo
    sd["encapContentInfo"].setComponentByName("eContent", tst_der)

    sd.setComponentByName("certificates")
    all_certs = [cert] + (extra_certs or [])
    for c in all_certs:
        c_der = c.public_bytes(serialization.Encoding.DER)
        c_asn1, _ = decoder.decode(c_der, asn1Spec=rfc2459.Certificate())
        ch = rfc5652.CertificateChoices()
        ch["certificate"] = c_asn1
        sd["certificates"].append(ch)

    cert_der = cert.public_bytes(serialization.Encoding.DER)
    asn1_cert, _ = decoder.decode(cert_der, asn1Spec=rfc2459.Certificate())

    si = rfc5652.SignerInfo()
    si["version"] = 1
    si["sid"] = rfc5652.SignerIdentifier()
    si["sid"]["issuerAndSerialNumber"] = rfc5652.IssuerAndSerialNumber()
    si["sid"]["issuerAndSerialNumber"]["issuer"] = asn1_cert["tbsCertificate"]["issuer"]
    si["sid"]["issuerAndSerialNumber"]["serialNumber"] = asn1_cert["tbsCertificate"]["serialNumber"]
    si["digestAlgorithm"] = da
    si["signatureAlgorithm"] = rfc5652.SignatureAlgorithmIdentifier()
    si["signatureAlgorithm"]["algorithm"] = univ.ObjectIdentifier("1.2.840.113549.1.1.1")

    if include_signed_attrs:
        si.setComponentByName("signedAttrs")

        if not omit_content_type:
            ct_oid = univ.ObjectIdentifier(bad_content_type_oid if bad_content_type_oid else rfc3161.id_ct_TSTInfo)
            attr_ct = rfc5652.Attribute()
            attr_ct["attrType"] = rfc5652.id_contentType
            attr_ct.setComponentByName("attrValues")
            attr_ct["attrValues"].append(rfc5652.AttributeValue(encoder.encode(ct_oid)))
            si["signedAttrs"].append(attr_ct)

            if duplicate_content_type:
                dup_ct = rfc5652.Attribute()
                dup_ct["attrType"] = rfc5652.id_contentType
                dup_ct.setComponentByName("attrValues")
                dup_ct["attrValues"].append(rfc5652.AttributeValue(encoder.encode(ct_oid)))
                si["signedAttrs"].append(dup_ct)

        if not omit_message_digest:
            attr_md = rfc5652.Attribute()
            attr_md["attrType"] = rfc5652.id_messageDigest
            attr_md.setComponentByName("attrValues")
            md_bytes = hashlib.sha256(tst_der).digest()
            if corrupt_message_digest_attr:
                md_bytes = b"\x00" * 32
            attr_md["attrValues"].append(rfc5652.AttributeValue(encoder.encode(univ.OctetString(md_bytes))))
            si["signedAttrs"].append(attr_md)

            if duplicate_message_digest:
                dup_md = rfc5652.Attribute()
                dup_md["attrType"] = rfc5652.id_messageDigest
                dup_md.setComponentByName("attrValues")
                dup_md["attrValues"].append(rfc5652.AttributeValue(encoder.encode(univ.OctetString(md_bytes))))
                si["signedAttrs"].append(dup_md)

        signed_attrs_der = encoder.encode(si["signedAttrs"])
        if signed_attrs_der.startswith(b"\xa0"):
            signed_attrs_der = b"\x31" + signed_attrs_der[1:]
        sign_payload = signed_attrs_der
    else:
        sign_payload = tst_der

    sig = key.sign(sign_payload, padding.PKCS1v15(), hashes.SHA256())
    if corrupt_sig:
        sig_mut = bytearray(sig)
        sig_mut[10] ^= 0xFF
        sig = bytes(sig_mut)

    si["signature"] = univ.OctetString(sig)

    sd["signerInfos"] = rfc5652.SignerInfos()
    sd["signerInfos"].append(si)

    # 3. ContentInfo
    ci = rfc5652.ContentInfo()
    ci["contentType"] = rfc5652.id_signedData
    ci["content"] = encoder.encode(sd)

    return encoder.encode(ci), cert, key


def test_rfc3161_offline_verification_valid_token():
    """37. Cryptographically valid RFC 3161 token successfully verified offline."""
    digest = b"\xaa" * 32
    token_der, tsa_cert, _ = _make_synthetic_rfc3161_token(digest)

    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is True
    assert res.error == ""
    assert res.tsa_identity == "CN=Test TSA"
    assert res.policy_oid == "1.2.3.4.5"
    assert res.gen_time_utc is not None
    assert abs(res.gen_time_utc - int(time.time())) < 120


def test_rfc3161_offline_verification_mismatched_message_imprint():
    """38. RFC 3161 token with mismatched message digest rejected."""
    digest_a = b"\xaa" * 32
    digest_b = b"\xbb" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest_a)

    res = verify_rfc3161_token_offline(token_der, digest_b)
    assert res.is_valid is False
    assert "Message imprint mismatch" in res.error


def test_rfc3161_offline_verification_missing_eku():
    """39. TSA certificate lacking timeStamping ExtendedKeyUsage rejected."""
    digest = b"\xaa" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, include_eku=False)

    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "TSA certificate missing required timeStamping ExtendedKeyUsage" in res.error


def test_rfc3161_offline_verification_expired_tsa_cert():
    """40. TSA certificate not valid at timestamp generation time rejected."""
    digest = b"\xaa" * 32
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    # Cert validity expired in 2024
    nb = now_utc - datetime.timedelta(days=700)
    na = now_utc - datetime.timedelta(days=365)
    # Token generated now (after cert expired)
    token_der, _, _ = _make_synthetic_rfc3161_token(
        digest,
        gen_time_dt=now_utc,
        cert_valid_not_before_dt=nb,
        cert_valid_not_after_dt=na,
    )

    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "TSA certificate was not valid at timestamp generation time" in res.error


def test_rfc3161_offline_verification_untrusted_tsa_root():
    """41. TSA certificate rejected when trust anchors are specified and cert is not anchored."""
    digest = b"\xaa" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest)

    # Generate an independent untrusted anchor
    anchor_key = rsa.generate_private_key(65537, 2048)
    anchor_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Unrelated Anchor Root")])
    unrelated_anchor = (
        x509.CertificateBuilder()
        .subject_name(anchor_subject)
        .issuer_name(anchor_subject)
        .public_key(anchor_key.public_key())
        .serial_number(9999)
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
        .sign(anchor_key, hashes.SHA256())
    )

    res = verify_rfc3161_token_offline(token_der, digest, trusted_tsa_certificates=[unrelated_anchor])
    assert res.is_valid is False
    assert "not trusted by configured TSA trust anchors" in res.error


def test_rfc3161_offline_verification_tampered_signature():
    """42. RFC 3161 token with modified signature bytes rejected."""
    digest = b"\xaa" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, corrupt_sig=True)

    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "TSA digital signature verification failed" in res.error


def test_notary_evidence_marked_unsupported():
    """43. Evidence with TRUSTED_NOTARY explicitly rejected as unsupported in Module 1.6."""
    evidence = TimestampEvidence(
        source=TimestampEvidenceSource.TRUSTED_NOTARY,
        verified_time_utc=1500,
        proof=b"notary-envelope-bytes",
        is_verified=True,
    )
    res = verify_historical_signature(
        claimed_signature_time_utc=1490,
        key_valid_from=1000,
        key_expires_at=2000,
        timestamp_evidence=evidence,
        current_time=3000,
    )
    assert res.status == HistoricalValidity.INVALID_EVIDENCE
    assert res.is_valid is False
    assert "unsupported in Module 1.6" in res.explanation


def test_historical_signature_with_verified_rfc3161_proof():
    """44. verify_historical_signature performs end-to-end RFC 3161 verification."""
    digest = b"\xca\xfe" * 16
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, gen_time_dt=now_utc)
    gen_time_utc = int(now_utc.timestamp())

    evidence = TimestampEvidence(
        source=TimestampEvidenceSource.RFC3161_TSA,
        verified_time_utc=gen_time_utc,
        proof=token_der,
        is_verified=True,
    )

    # Key was valid when token was generated, but is now expired
    key_valid_from = gen_time_utc - 10000
    key_expires_at = gen_time_utc + 100
    current_time = gen_time_utc + 5000  # Key expired now

    res = verify_historical_signature(
        claimed_signature_time_utc=gen_time_utc - 10,
        key_valid_from=key_valid_from,
        key_expires_at=key_expires_at,
        timestamp_evidence=evidence,
        current_time=current_time,
        expected_message_digest=digest,
    )
    assert res.status == HistoricalValidity.VALID_HISTORICAL
    assert res.is_valid is True
    assert res.effective_time_utc == gen_time_utc
    assert res.evidence_source == TimestampEvidenceSource.RFC3161_TSA


def test_historical_signature_with_tampered_rfc3161_proof_rejected():
    """45. verify_historical_signature rejects tampered RFC 3161 token proof."""
    digest = b"\xca\xfe" * 16
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, gen_time_dt=now_utc, corrupt_sig=True)

    evidence = TimestampEvidence(
        source=TimestampEvidenceSource.RFC3161_TSA,
        verified_time_utc=int(now_utc.timestamp()),
        proof=token_der,
        is_verified=True,
    )

    res = verify_historical_signature(
        claimed_signature_time_utc=int(now_utc.timestamp()) - 10,
        key_valid_from=int(now_utc.timestamp()) - 1000,
        key_expires_at=int(now_utc.timestamp()) + 100,
        timestamp_evidence=evidence,
        current_time=int(now_utc.timestamp()) + 500,
        expected_message_digest=digest,
    )
    assert res.status == HistoricalValidity.INVALID_EVIDENCE
    assert res.is_valid is False
    assert "RFC 3161 TSA token verification failed" in res.explanation


def test_authenticated_receipt_evidence_observation_clarification():
    """46. Authenticated receipt confirms prior QuMail observation, not sender signature time."""
    # Under Module 1.5/1.6, local vault receipt records sha256(inner_mime) and first_seen timestamp.
    # It establishes that QuMail verified and observed the message prior to key revocation.
    vault_receipt_time = 1500
    evidence = TimestampEvidence(
        source=TimestampEvidenceSource.AUTHENTICATED_RECEIPT,
        verified_time_utc=vault_receipt_time,
        proof="d3b07384d113edec49eaa6238ad5ff00",
        is_verified=True,
    )

    # Key was later revoked due to compromise at time 2000
    res = verify_historical_signature(
        claimed_signature_time_utc=1400,
        key_valid_from=1000,
        key_expires_at=5000,
        revocation_timestamp=2000,
        revocation_reason=RevocationReason.KEY_COMPROMISED,
        timestamp_evidence=evidence,
        current_time=3000,
    )
    # Since vault observed and committed receipt at 1500 < 2000, prior observation is valid
    assert res.status == HistoricalValidity.VALID_HISTORICAL
    assert res.is_valid is True
    assert res.effective_time_utc == vault_receipt_time

    # If vault receipt was recorded AFTER key compromise date, observation does not protect it
    late_evidence = TimestampEvidence(
        source=TimestampEvidenceSource.AUTHENTICATED_RECEIPT,
        verified_time_utc=2500,  # Observed after compromise at 2000!
        proof="d3b07384d113edec49eaa6238ad5ff00",
        is_verified=True,
    )
    res_late = verify_historical_signature(
        claimed_signature_time_utc=1400,  # Claims pre-compromise
        key_valid_from=1000,
        key_expires_at=5000,
        revocation_timestamp=2000,
        revocation_reason=RevocationReason.KEY_COMPROMISED,
        timestamp_evidence=late_evidence,
        current_time=3000,
    )
    assert res_late.status == HistoricalValidity.KEY_COMPROMISED
    assert res_late.is_valid is False


def test_rfc3161_offline_verification_multi_cert_bundle_and_path_validation():
    """47. SignerInfo matches TSA leaf in multi-cert bundle and validates path to root CA."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    root_k = rsa.generate_private_key(65537, 2048)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Corp Root CA")])
    root_c = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_k.public_key())
        .serial_number(1)
        .not_valid_before(now_utc - datetime.timedelta(days=10))
        .not_valid_after(now_utc + datetime.timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(root_k, hashes.SHA256())
    )

    tsa_k = rsa.generate_private_key(65537, 2048)
    tsa_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Corp TSA Server")])
    tsa_c = (
        x509.CertificateBuilder()
        .subject_name(tsa_name)
        .issuer_name(root_name)
        .public_key(tsa_k.public_key())
        .serial_number(2)
        .not_valid_before(now_utc - datetime.timedelta(days=5))
        .not_valid_after(now_utc + datetime.timedelta(days=5))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=False)
        .sign(root_k, hashes.SHA256())
    )

    digest = b"\xde\xad" * 16
    token_der, _, _ = _make_synthetic_rfc3161_token(
        digest,
        custom_key=tsa_k,
        custom_cert=tsa_c,
        extra_certs=[root_c],
    )

    res = verify_rfc3161_token_offline(token_der, digest, trusted_tsa_certificates=[root_c])
    assert res.is_valid is True
    assert res.error == ""
    assert res.tsa_identity == "CN=Corp TSA Server"


def test_rfc3161_offline_verification_fake_root_same_subject_rejected():
    """48. Fake root CA with identical Subject name fails cryptographic signature verification."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    root_k = rsa.generate_private_key(65537, 2048)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Legit Root CA")])
    root_c = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_k.public_key())
        .serial_number(1)
        .not_valid_before(now_utc - datetime.timedelta(days=10))
        .not_valid_after(now_utc + datetime.timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(root_k, hashes.SHA256())
    )

    tsa_k = rsa.generate_private_key(65537, 2048)
    tsa_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Legit TSA Server")])
    tsa_c = (
        x509.CertificateBuilder()
        .subject_name(tsa_name)
        .issuer_name(root_name)
        .public_key(tsa_k.public_key())
        .serial_number(2)
        .not_valid_before(now_utc - datetime.timedelta(days=5))
        .not_valid_after(now_utc + datetime.timedelta(days=5))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=False)
        .sign(root_k, hashes.SHA256())
    )

    digest = b"\xbe\xef" * 16
    token_der, _, _ = _make_synthetic_rfc3161_token(
        digest,
        custom_key=tsa_k,
        custom_cert=tsa_c,
    )

    # Attacker crafts a fake root with identical subject name but different private key
    fake_k = rsa.generate_private_key(65537, 2048)
    fake_root = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(fake_k.public_key())
        .serial_number(999)
        .not_valid_before(now_utc - datetime.timedelta(days=10))
        .not_valid_after(now_utc + datetime.timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(fake_k, hashes.SHA256())
    )

    # Must fail cryptographic signature verification of the leaf against fake root
    res = verify_rfc3161_token_offline(token_der, digest, trusted_tsa_certificates=[fake_root])
    assert res.is_valid is False
    assert "Cryptographic signature check failed against issuer" in res.error


def test_rfc3161_offline_verification_signed_attrs_and_digest_mismatch_rejected():
    """49. CMS signed attributes are validated and message-digest mismatch is rejected."""
    digest = b"\x55" * 32

    # 1. Authentic signedAttrs
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, include_signed_attrs=True)
    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is True

    # 2. Tampered message-digest signed attribute
    tampered_der, _, _ = _make_synthetic_rfc3161_token(
        digest,
        include_signed_attrs=True,
        corrupt_message_digest_attr=True,
    )
    res_tampered = verify_rfc3161_token_offline(tampered_der, digest)
    assert res_tampered.is_valid is False
    assert "Signed attribute message-digest does not match hash of encapsulated TSTInfo" in res_tampered.error


def test_rfc3161_offline_verification_policy_enforcement():
    """50. TSA policy OID is checked; fails closed when required policy mismatches."""
    digest = b"\x77" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, custom_policy_oid="1.2.840.113549.1.9.16.3.1")

    # Matching policy
    res_ok = verify_rfc3161_token_offline(
        token_der,
        digest,
        required_policy_oid="1.2.840.113549.1.9.16.3.1",
    )
    assert res_ok.is_valid is True

    # Mismatched policy fails closed
    res_bad = verify_rfc3161_token_offline(
        token_der,
        digest,
        required_policy_oid="1.2.840.113549.1.9.16.3.999",
    )
    assert res_bad.is_valid is False
    assert "TSA policy mismatch" in res_bad.error


def test_local_receipt_absence_and_wall_clock_limitations():
    """51. Documented receipt semantics: wall-clock timestamp and absence/rollback limits."""
    # 1. Observation timestamp is wall-clock time (int(time.time())), not monotonic time
    wall_clock_now = int(time.time())
    evidence = TimestampEvidence(
        source=TimestampEvidenceSource.AUTHENTICATED_RECEIPT,
        verified_time_utc=wall_clock_now,
        proof="digest-receipt-001",
        is_verified=True,
    )
    assert evidence.verified_time_utc == wall_clock_now

    # 2. Receipt absence or whole-database deletion must NEVER be treated as proof that
    #    a message was NOT previously observed. Absence simply leaves historical validity indeterminate.
    res_no_evidence = verify_historical_signature(
        claimed_signature_time_utc=wall_clock_now - 1000,
        key_valid_from=wall_clock_now - 5000,
        key_expires_at=wall_clock_now - 500,  # Key is now expired
        timestamp_evidence=None,               # Missing receipt or database restored from backup!
        current_time=wall_clock_now,
    )
    assert res_no_evidence.status == HistoricalValidity.INDETERMINATE_NO_TRUSTED_TIME
    assert res_no_evidence.is_valid is False
    # Backdating defense: cannot conclude message is authentic, but absence does not prove it wasn't seen
    assert "backdating defense" in res_no_evidence.explanation.lower()


def test_rfc3161_offline_verification_absent_signed_attrs_rejected():
    """52. RFC 3161 token without CMS signedAttrs is strictly rejected (no direct signature fallback)."""
    digest = b"\x11" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, include_signed_attrs=False)
    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "RFC 3161 requires mandatory CMS signedAttrs" in res.error


def test_rfc3161_offline_verification_missing_content_type_rejected():
    """53. RFC 3161 signedAttrs missing id-contentType attribute is rejected."""
    digest = b"\x22" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, omit_content_type=True)
    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "Signed attributes missing mandatory id-contentType" in res.error


def test_rfc3161_offline_verification_duplicate_content_type_rejected():
    """54. RFC 3161 signedAttrs with duplicated id-contentType attributes is rejected."""
    digest = b"\x33" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, duplicate_content_type=True)
    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "Signed attributes contains duplicate id-contentType" in res.error


def test_rfc3161_offline_verification_incorrect_content_type_rejected():
    """55. RFC 3161 signedAttrs where id-contentType is not id-ct-TSTInfo is rejected."""
    digest = b"\x44" * 32
    # Use id-data (1.2.840.113549.1.7.1) instead of id-ct-TSTInfo (1.2.840.113549.1.9.16.1.4)
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, bad_content_type_oid="1.2.840.113549.1.7.1")
    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "expected id-ct-TSTInfo" in res.error


def test_rfc3161_offline_verification_missing_message_digest_rejected():
    """56. RFC 3161 signedAttrs missing id-messageDigest attribute is rejected."""
    digest = b"\x55" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, omit_message_digest=True)
    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "Signed attributes missing mandatory id-messageDigest" in res.error


def test_rfc3161_offline_verification_duplicate_message_digest_rejected():
    """57. RFC 3161 signedAttrs with duplicated id-messageDigest attributes is rejected."""
    digest = b"\x66" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, duplicate_message_digest=True)
    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "Signed attributes contains duplicate id-messageDigest" in res.error


def test_rfc3161_offline_verification_unsupported_digest_algorithm_rejected():
    """58. SignerInfo declaring unsupported digest algorithm OID is rejected."""
    digest = b"\x77" * 32
    # Use MD5 OID 1.2.840.113549.2.5
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, custom_digest_algo_oid="1.2.840.113549.2.5")
    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "Unsupported digest algorithm OID" in res.error


def test_rfc3161_offline_verification_tsa_leaf_invalid_key_usage_rejected():
    """59. TSA leaf certificate KeyUsage requirements strictly enforced."""
    digest = b"\x88" * 32

    # Case A: Asserting key_cert_sign is forbidden for TSA leaf
    tok_a, _, _ = _make_synthetic_rfc3161_token(digest, leaf_key_usage_key_cert_sign=True)
    res_a = verify_rfc3161_token_offline(tok_a, digest)
    assert res_a.is_valid is False
    assert "must not have keyCertSign or crlSign" in res_a.error

    # Case B: Asserting crl_sign is forbidden for TSA leaf
    tok_b, _, _ = _make_synthetic_rfc3161_token(digest, leaf_key_usage_crl_sign=True)
    res_b = verify_rfc3161_token_offline(tok_b, digest)
    assert res_b.is_valid is False
    assert "must not have keyCertSign or crlSign" in res_b.error

    # Case C: Missing digitalSignature and contentCommitment
    tok_c, _, _ = _make_synthetic_rfc3161_token(
        digest,
        leaf_key_usage_digital_signature=False,
        leaf_key_usage_content_commitment=False,
    )
    res_c = verify_rfc3161_token_offline(tok_c, digest)
    assert res_c.is_valid is False
    assert "missing required digitalSignature or contentCommitment" in res_c.error


def test_rfc3161_offline_verification_ca_key_usage_and_basic_constraints():
    """60. Certificate-path validation enforces CA BasicConstraints and keyCertSign."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    root_k = rsa.generate_private_key(65537, 2048)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA Root")])

    # Case A: CA lacking keyCertSign in KeyUsage
    root_ca_no_certsign = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_k.public_key())
        .serial_number(1)
        .not_valid_before(now_utc - datetime.timedelta(days=10))
        .not_valid_after(now_utc + datetime.timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,  # Forbidden for issuing CA!
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(root_k, hashes.SHA256())
    )

    tsa_k = rsa.generate_private_key(65537, 2048)
    tsa_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test TSA Leaf")])
    tsa_cert = (
        x509.CertificateBuilder()
        .subject_name(tsa_name)
        .issuer_name(root_name)
        .public_key(tsa_k.public_key())
        .serial_number(2)
        .not_valid_before(now_utc - datetime.timedelta(days=5))
        .not_valid_after(now_utc + datetime.timedelta(days=5))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=False)
        .sign(root_k, hashes.SHA256())
    )

    digest = b"\x99" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, custom_key=tsa_k, custom_cert=tsa_cert, extra_certs=[root_ca_no_certsign])
    res_a = verify_rfc3161_token_offline(token_der, digest, trusted_tsa_certificates=[root_ca_no_certsign])
    assert res_a.is_valid is False
    assert "KeyUsage does not permit keyCertSign" in res_a.error

    # Case B: CA with BasicConstraints ca=False
    root_ca_not_ca = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_k.public_key())
        .serial_number(3)
        .not_valid_before(now_utc - datetime.timedelta(days=10))
        .not_valid_after(now_utc + datetime.timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)  # ca=False!
        .sign(root_k, hashes.SHA256())
    )
    res_b = verify_rfc3161_token_offline(token_der, digest, trusted_tsa_certificates=[root_ca_not_ca])
    assert res_b.is_valid is False
    assert "BasicConstraints ca=False" in res_b.error


def test_rfc3161_offline_verification_ca_path_len_constraint_exceeded():
    """61. Certificate-path validation enforces pathLenConstraint."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    root_k = rsa.generate_private_key(65537, 2048)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Constrained Root CA")])
    # Root permits at most 0 intermediate CAs (direct issuance only)
    root_c = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_k.public_key())
        .serial_number(1)
        .not_valid_before(now_utc - datetime.timedelta(days=10))
        .not_valid_after(now_utc + datetime.timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(root_k, hashes.SHA256())
    )

    # Intermediate CA (depth 1 intermediate)
    inter_k = rsa.generate_private_key(65537, 2048)
    inter_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Intermediate CA")])
    inter_c = (
        x509.CertificateBuilder()
        .subject_name(inter_name)
        .issuer_name(root_name)
        .public_key(inter_k.public_key())
        .serial_number(2)
        .not_valid_before(now_utc - datetime.timedelta(days=5))
        .not_valid_after(now_utc + datetime.timedelta(days=5))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(root_k, hashes.SHA256())
    )

    # Sub-intermediate CA (depth 2 intermediate -> intermediate_count = 1 >= pathLen 0)
    sub_k = rsa.generate_private_key(65537, 2048)
    sub_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Sub Intermediate CA")])
    sub_c = (
        x509.CertificateBuilder()
        .subject_name(sub_name)
        .issuer_name(inter_name)
        .public_key(sub_k.public_key())
        .serial_number(3)
        .not_valid_before(now_utc - datetime.timedelta(days=5))
        .not_valid_after(now_utc + datetime.timedelta(days=5))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(inter_k, hashes.SHA256())
    )

    # TSA leaf issued by sub_c
    leaf_k = rsa.generate_private_key(65537, 2048)
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Leaf TSA")])
    leaf_c = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(sub_name)
        .public_key(leaf_k.public_key())
        .serial_number(4)
        .not_valid_before(now_utc - datetime.timedelta(days=2))
        .not_valid_after(now_utc + datetime.timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=False)
        .sign(sub_k, hashes.SHA256())
    )

    digest = b"\xab" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(
        digest,
        custom_key=leaf_k,
        custom_cert=leaf_c,
        extra_certs=[sub_c, inter_c, root_c],
    )
    res = verify_rfc3161_token_offline(token_der, digest, trusted_tsa_certificates=[root_c])
    assert res.is_valid is False
    assert "pathLenConstraint exceeded" in res.error


def test_rfc3161_offline_verification_unrecognized_critical_extension():
    """62. Certificate with unrecognized critical extension fails closed."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    key = rsa.generate_private_key(65537, 2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Critical Ext TSA")])

    # Add unknown critical extension OID 2.999.1.2.3
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now_utc - datetime.timedelta(days=1))
        .not_valid_after(now_utc + datetime.timedelta(days=1))
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=False)
        .add_extension(x509.UnrecognizedExtension(x509.ObjectIdentifier("2.999.1.2.3"), b"secret-ext"), critical=True)
        .sign(key, hashes.SHA256())
    )

    digest = b"\xcd" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, custom_key=key, custom_cert=cert)
    res = verify_rfc3161_token_offline(token_der, digest)
    assert res.is_valid is False
    assert "contains unrecognized critical extension '2.999.1.2.3'" in res.error


def test_rfc3161_offline_verification_prohibited_weak_hash_algorithm():
    """63. Certificate signed with weak or prohibited hash algorithm (SHA-1) is rejected."""
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    root_k = rsa.generate_private_key(65537, 2048)
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Weak Hash Root CA")])
    root_c = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_k.public_key())
        .serial_number(1)
        .not_valid_before(now_utc - datetime.timedelta(days=10))
        .not_valid_after(now_utc + datetime.timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(root_k, hashes.SHA256())
    )

    tsa_k = rsa.generate_private_key(65537, 2048)
    tsa_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Leaf TSA")])
    tsa_c = (
        x509.CertificateBuilder()
        .subject_name(tsa_name)
        .issuer_name(root_name)
        .public_key(tsa_k.public_key())
        .serial_number(2)
        .not_valid_before(now_utc - datetime.timedelta(days=5))
        .not_valid_after(now_utc + datetime.timedelta(days=5))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=False)
        .sign(root_k, hashes.SHA256())
    )

    digest = b"\xef" * 32
    token_der, _, _ = _make_synthetic_rfc3161_token(digest, custom_key=tsa_k, custom_cert=tsa_c, extra_certs=[root_c])

    # Simulate a certificate signed with legacy SHA-1 hash algorithm
    with patch.object(type(tsa_c), "signature_hash_algorithm", new_callable=lambda: property(lambda self: hashes.SHA1())):
        res = verify_rfc3161_token_offline(token_der, digest, trusted_tsa_certificates=[root_c])
        assert res.is_valid is False
        assert "weak or prohibited hash algorithm 'sha1'" in res.error
