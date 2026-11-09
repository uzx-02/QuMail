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

import io
import ipaddress
from pathlib import Path
import socket
import ssl
import threading
import time
from unittest.mock import MagicMock, patch
import pytest

from cryptography.hazmat.primitives.asymmetric import ed25519

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
    RevocationReason,
    TimestampEvidence,
    TimestampEvidenceSource,
    is_signature_historically_valid,
    verify_historical_signature,
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
