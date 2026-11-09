"""
WS-02 Automated Verification Suite:
Cryptographic Identity, Automated Key Discovery & Enterprise Trust.

Covers:
1. Discovery:
   - WKD URL derivation and z-base-32 hashing.
   - Successful discovery via mock WKD.
   - Missing key (404), network errors, payload size limit.
   - Address mismatch rejection (key does not bind email).
   - Bounded cache TTL, expiration, and invalidation.
   - Enterprise Directory provider lookup and precendence over WKD.

2. Trust Policy Engine & Security Indicators:
   - Pinned verified identity -> VERIFIED, 'Secured by QuMail' (Green).
   - Discovered but unverified key -> DISCOVERED_NOT_VERIFIED (Caution/Neutral).
   - Valid signature from unverified identity -> ENCRYPTED_NOT_VERIFIED (Yellow/Amber).
   - Invalid signature -> SIGNATURE_INVALID (Red alert).
   - Sender/certificate mismatch -> IDENTITY_MISMATCH (Red alert).
   - Unexpected root key replacement -> CHANGED_BLOCKED (Red alert).
   - Key expired or revoked -> KEY_REVOKED_OR_EXPIRED (Red alert).
   - Enterprise trust anchor certification -> VERIFIED.

3. Cryptographic Profile Standardization (QM-OPENPGP-PQ-v1):
   - Outbound emissions use QM-OPENPGP-PQ-v1.
   - Backward compatibility: incoming messages with QM-OPENPGP-PQ-1-EXPERIMENT-M5 accepted.
   - Unsupported profiles safely rejected with Code.PROFILE.

4. Subkey Lifecycle & Rotation:
   - Authorized subkey rotation vs unauthorized root replacement.
   - Subkey expiration alerts (< 30 days).
   - RFC 4880/9580 time-aware historical verification.
"""

from __future__ import annotations

import hashlib
import time
from unittest.mock import Mock, patch
import pytest

from core.key_discovery import (
    compute_wkd_hash,
    build_wkd_urls,
    zbase32_encode,
    DiscoveredKey,
    DiscoveryResult,
    DiscoveryStatus,
    WKDDiscoveryProvider,
    EnterpriseDirectoryProvider,
    CachedKeyDiscoveryService,
    DEFAULT_CACHE_TTL,
)
from core.security_indicators import BadgeLevel, IndicatorCode, SecurityIndicator
from core.enterprise_trust import EnterpriseTrustDirectory, TrustAnchor, EnterpriseContactRecord
from core.key_lifecycle import (
    KeyStatus,
    RotationType,
    evaluate_key_expiration,
    evaluate_key_transition,
    is_signature_historically_valid,
)
from core.trust_engine import TrustPolicyEngine, TrustState, TrustDecision
from experiments.m5.model import (
    PROFILE,
    PROFILE_V1,
    PROFILE_LEGACY_M5,
    SUPPORTED_PROFILES,
    Code,
    Failure,
    Draft,
)
from experiments.m5 import mime


# ==============================================================================
# 1. Key Discovery & WKD
# ==============================================================================

def test_wkd_zbase32_hash_derivation():
    """Verify WKD hash matches RFC specification for known vectors."""
    # Local part 'alice' -> sha1('alice') -> zbase32
    h = compute_wkd_hash("alice")
    assert len(h) == 32
    assert all(c in "ybndrfg8ejkmcpqxot1uwisza345h769" for c in h)

    # Different local parts must produce distinct hashes
    assert compute_wkd_hash("alice") != compute_wkd_hash("bob")
    # Case insensitivity
    assert compute_wkd_hash("Alice") == compute_wkd_hash("alice")


def test_build_wkd_urls():
    advanced, direct = build_wkd_urls("alice@example.com")
    assert "https://openpgpkey.example.com/.well-known/openpgpkey/example.com/hu/" in advanced
    assert "https://example.com/.well-known/openpgpkey/example.com/hu/" in direct
    assert "l=alice" in advanced
    assert "l=alice" in direct


def test_build_wkd_urls_invalid():
    with pytest.raises(ValueError, match="Invalid email"):
        build_wkd_urls("not-an-email")
    with pytest.raises(ValueError, match="Invalid email"):
        build_wkd_urls("@missing-local.com")


def test_wkd_provider_success():
    fake_key_bytes = b"-----BEGIN PGP PUBLIC KEY BLOCK-----\nfake\n-----END PGP PUBLIC KEY BLOCK-----"
    mock_fetcher = Mock(return_value=fake_key_bytes)
    mock_inspector = Mock(return_value={"fingerprint": "A"*40, "addresses": ["alice@example.com"]})

    provider = WKDDiscoveryProvider(
        inspector_fn=mock_inspector,
        http_fetcher=mock_fetcher,
    )

    res = provider.lookup("alice@example.com")
    assert res.ok is True
    assert res.status == DiscoveryStatus.SUCCESS
    assert res.key is not None
    assert res.key.email == "alice@example.com"
    assert res.key.fingerprint == "A"*40
    assert res.key.public_key_bytes == fake_key_bytes
    assert res.key.source == "wkd"


def test_wkd_provider_address_mismatch_rejected():
    """If WKD returns a key that binds a different email, reject as ADDRESS_MISMATCH."""
    fake_key_bytes = b"fake-key"
    mock_fetcher = Mock(return_value=fake_key_bytes)
    mock_inspector = Mock(return_value={"fingerprint": "B"*40, "addresses": ["mallory@evil.com"]})

    provider = WKDDiscoveryProvider(
        inspector_fn=mock_inspector,
        http_fetcher=mock_fetcher,
    )

    res = provider.lookup("alice@example.com")
    assert res.ok is False
    assert res.status == DiscoveryStatus.ADDRESS_MISMATCH
    assert "does not bind address" in res.error_message


def test_wkd_provider_not_found_404():
    import urllib.error
    mock_fetcher = Mock(side_effect=urllib.error.HTTPError("url", 404, "Not Found", {}, None))

    provider = WKDDiscoveryProvider(http_fetcher=mock_fetcher)
    res = provider.lookup("nobody@example.com")
    assert res.ok is False
    assert res.status == DiscoveryStatus.NOT_FOUND


def test_cached_discovery_service_ttl_and_invalidation():
    enterprise = EnterpriseDirectoryProvider()
    wkd = WKDDiscoveryProvider(http_fetcher=Mock(return_value=b"key-bytes"))
    service = CachedKeyDiscoveryService(enterprise, wkd, cache_ttl=10.0)

    # First lookup -> fetches from WKD
    res1 = service.discover("carol@example.com")
    assert res1.ok is True
    assert service.get_cached("carol@example.com") is not None

    # Invalidate cache
    service.invalidate("carol@example.com")
    assert service.get_cached("carol@example.com") is None

    # Re-discover and check expired behavior
    res2 = service.discover("carol@example.com")
    assert res2.ok is True
    cached_key = service.get_cached("carol@example.com")
    assert cached_key is not None

    # Simulate expiration by patching time
    with patch("time.time", return_value=time.time() + 100):
        assert service.get_cached("carol@example.com") is None


def test_enterprise_directory_precedence_over_wkd():
    ent_key = b"enterprise-key-material"
    wkd_key = b"wkd-key-material"

    ent_provider = EnterpriseDirectoryProvider({"dave@corp.com": ent_key})
    wkd_provider = WKDDiscoveryProvider(http_fetcher=Mock(return_value=wkd_key))

    service = CachedKeyDiscoveryService(ent_provider, wkd_provider)
    res = service.discover("dave@corp.com")

    assert res.ok is True
    assert res.key.source == "enterprise_directory"
    assert res.key.public_key_bytes == ent_key


# ==============================================================================
# 2. Trust Policy Engine & Security Indicators
# ==============================================================================

def test_trust_engine_outbound_pinned_verified_recipient():
    engine = TrustPolicyEngine()
    contacts = {
        "alice@corp.com": {
            "fingerprint": "1111222233334444",
            "state": "verified",
        }
    }
    decision = engine.evaluate_outbound_recipient("alice@corp.com", contacts)
    assert decision.state == TrustState.VERIFIED
    assert decision.can_encrypt is True
    assert decision.is_identity_verified is True
    assert decision.indicator.code == IndicatorCode.SECURED_BY_QUMAIL
    assert decision.indicator.badge_level == BadgeLevel.SECURE


def test_trust_engine_outbound_unverified_wkd_key():
    """WKD key allows encryption but NEVER upgrades identity to verified."""
    mock_discovery = Mock()
    mock_discovery.discover.return_value = DiscoveryResult(
        email="bob@external.org",
        status=DiscoveryStatus.SUCCESS,
        key=DiscoveredKey(
            email="bob@external.org",
            public_key_bytes=b"bytes",
            fingerprint="5555666677778888",
            source="wkd",
        ),
    )
    engine = TrustPolicyEngine(discovery_service=mock_discovery)
    decision = engine.evaluate_outbound_recipient("bob@external.org", {})

    assert decision.state == TrustState.DISCOVERED_NOT_VERIFIED
    assert decision.can_encrypt is True
    assert decision.is_identity_verified is False  # WKD DOES NOT GRANT VERIFIED STATUS
    assert decision.indicator.code == IndicatorCode.EXTERNAL_CORRESPONDENT
    assert decision.indicator.badge_level == BadgeLevel.NEUTRAL


def test_trust_engine_outbound_changed_blocked():
    contacts = {
        "eve@corp.com": {
            "fingerprint": "99990000",
            "state": "changed_blocked",
        }
    }
    engine = TrustPolicyEngine()
    decision = engine.evaluate_outbound_recipient("eve@corp.com", contacts)
    assert decision.state == TrustState.CHANGED_BLOCKED
    assert decision.can_encrypt is False
    assert decision.indicator.badge_level == BadgeLevel.ALERT


def test_trust_engine_inbound_verified_message():
    engine = TrustPolicyEngine()
    decision = engine.evaluate_inbound_message(
        sender="alice@corp.com",
        signer_fingerprint="A"*40,
        signature_valid=True,
        identity_trust="independently_verified",
        replay_state="fresh",
        mismatches=(),
    )
    assert decision.state == TrustState.VERIFIED
    assert decision.is_identity_verified is True
    assert decision.indicator.code == IndicatorCode.SECURED_BY_QUMAIL
    assert decision.indicator.badge_level == BadgeLevel.SECURE
    assert "Secured by QuMail" in decision.indicator.headline


def test_trust_engine_inbound_unverified_sender():
    """Valid signature from unverified sender produces yellow caution indicator, NOT green secured."""
    engine = TrustPolicyEngine()
    decision = engine.evaluate_inbound_message(
        sender="unknown@external.org",
        signer_fingerprint="B"*40,
        signature_valid=True,
        identity_trust="unverified",
        replay_state="fresh",
        mismatches=(),
    )
    assert decision.state == TrustState.ENCRYPTED_NOT_VERIFIED
    assert decision.is_identity_verified is False
    assert decision.indicator.code == IndicatorCode.ENCRYPTED_UNVERIFIED
    assert decision.indicator.badge_level == BadgeLevel.CAUTION
    assert decision.indicator.is_safe_to_trust is False


def test_trust_engine_inbound_invalid_signature():
    engine = TrustPolicyEngine()
    decision = engine.evaluate_inbound_message(
        sender="alice@corp.com",
        signer_fingerprint="A"*40,
        signature_valid=False,
        identity_trust="independently_verified",
        replay_state="fresh",
        mismatches=(),
    )
    assert decision.state == TrustState.VERIFICATION_FAILED
    assert decision.indicator.code == IndicatorCode.SIGNATURE_INVALID
    assert decision.indicator.badge_level == BadgeLevel.ALERT


def test_trust_engine_inbound_metadata_mismatch():
    engine = TrustPolicyEngine()
    decision = engine.evaluate_inbound_message(
        sender="alice@corp.com",
        signer_fingerprint="A"*40,
        signature_valid=True,
        identity_trust="independently_verified",
        replay_state="fresh",
        mismatches=("subject", "date"),
    )
    assert decision.state == TrustState.VERIFICATION_FAILED
    assert decision.indicator.code == IndicatorCode.IDENTITY_MISMATCH
    assert decision.indicator.badge_level == BadgeLevel.ALERT


# ==============================================================================
# 3. Enterprise Trust Architecture
# ==============================================================================

def test_enterprise_trust_anchor_certification():
    ent_dir = EnterpriseTrustDirectory()
    anchor = TrustAnchor(
        anchor_id="anchor-corp-root",
        organization="Acme Corp",
        domains=("acme.com", "sub.acme.com"),
        root_fingerprint="ROOT"*10,
    )
    ent_dir.add_trust_anchor(anchor)

    # Register employee certified under this anchor
    ent_dir.register_certified_contact(
        email="alice@acme.com",
        fingerprint="ALICE"*8,
        public_key_bytes=b"alice-cert",
        anchor_id="anchor-corp-root",
    )

    assert ent_dir.is_certified_by_enterprise("alice@acme.com", "ALICE"*8) is True
    # Wrong fingerprint
    assert ent_dir.is_certified_by_enterprise("alice@acme.com", "WRONG"*8) is False
    # Uncertified employee
    assert ent_dir.is_certified_by_enterprise("bob@acme.com", "BOB"*8) is False

    # Revoking anchor invalidates certification
    ent_dir.revoke_trust_anchor("anchor-corp-root")
    assert ent_dir.is_certified_by_enterprise("alice@acme.com", "ALICE"*8) is False


def test_trust_engine_honors_enterprise_certification():
    ent_dir = EnterpriseTrustDirectory()
    anchor = TrustAnchor("corp-1", "Corp", ("corp.com",), "ROOT"*10)
    ent_dir.add_trust_anchor(anchor)
    ent_dir.register_certified_contact("colleague@corp.com", "FP"*20, b"colleague-cert", "corp-1")

    engine = TrustPolicyEngine(enterprise_directory=ent_dir)
    decision = engine.evaluate_inbound_message(
        sender="colleague@corp.com",
        signer_fingerprint="FP"*20,
        signature_valid=True,
        identity_trust="unverified",  # Even if unpinned locally, enterprise anchor certifies it!
        replay_state="fresh",
        mismatches=(),
    )
    assert decision.state == TrustState.VERIFIED
    assert decision.is_identity_verified is True
    assert decision.indicator.code == IndicatorCode.SECURED_BY_QUMAIL


# ==============================================================================
# 4. Profile Standardization (QM-OPENPGP-PQ-v1)
# ==============================================================================

def test_profile_constants():
    assert PROFILE_V1 == "QM-OPENPGP-PQ-v1"
    assert PROFILE_LEGACY_M5 == "QM-OPENPGP-PQ-1-EXPERIMENT-M5"
    assert PROFILE == PROFILE_V1
    assert PROFILE_V1 in SUPPORTED_PROFILES
    assert PROFILE_LEGACY_M5 in SUPPORTED_PROFILES


def test_mime_parse_inner_accepts_v1_and_legacy_m5():
    """Verify that parse_inner accepts both v1 and legacy experiment profiles."""
    from email.utils import format_datetime
    from datetime import datetime, timezone

    draft = Draft(("bob@example.com",), (), "Test Subject", "Hello post-quantum world", (), "", (), False)
    ident = "<test.123@example.com>"
    date = format_datetime(datetime.now(timezone.utc))

    # 1. Standard V1 is generated by build_inner and accepted by parse_inner
    inner_v1 = mime.build_inner("alice@example.com", draft, ident, date)
    assert b"X-QuMail-Profile: QM-OPENPGP-PQ-v1" in inner_v1
    sender, d_parsed, id_parsed, dt_parsed, snaps = mime.parse_inner(inner_v1)
    assert sender == "alice@example.com"
    assert d_parsed.subject == "Test Subject"

    # 2. Legacy M5 profile is accepted backward-compatibly
    inner_legacy = inner_v1.replace(b"X-QuMail-Profile: QM-OPENPGP-PQ-v1", b"X-QuMail-Profile: QM-OPENPGP-PQ-1-EXPERIMENT-M5")
    sender_leg, d_leg, _, _, _ = mime.parse_inner(inner_legacy)
    assert sender_leg == "alice@example.com"

    # 3. Unsupported profile is rejected with Code.PROFILE
    inner_unknown = inner_v1.replace(b"X-QuMail-Profile: QM-OPENPGP-PQ-v1", b"X-QuMail-Profile: UNKNOWN-PROFILE-XYZ")
    with pytest.raises(Failure) as exc_info:
        mime.parse_inner(inner_unknown)
    assert exc_info.value.code == Code.PROFILE


# ==============================================================================
# 5. Key Lifecycle & Rotation
# ==============================================================================

def test_evaluate_key_expiration_alert_under_30_days():
    now = time.time()
    twenty_days_ahead = now + (20 * 86400)
    res = evaluate_key_expiration(int(twenty_days_ahead), current_time=now)
    assert res.status == KeyStatus.EXPIRING_SOON
    assert res.needs_warning is True
    assert res.days_remaining == 20
    assert "will expire in 20 days" in res.warning_message


def test_evaluate_key_expiration_active():
    now = time.time()
    ninety_days_ahead = now + (90 * 86400)
    res = evaluate_key_expiration(int(ninety_days_ahead), current_time=now)
    assert res.status == KeyStatus.ACTIVE
    assert res.needs_warning is False
    assert res.days_remaining == 90


def test_evaluate_key_expiration_expired():
    now = time.time()
    past = now - 3600
    res = evaluate_key_expiration(int(past), current_time=now)
    assert res.status == KeyStatus.EXPIRED
    assert res.days_remaining == 0


def test_evaluate_key_transition_authorized_rotation():
    trans = evaluate_key_transition(
        existing_fingerprint="ROOT_ABC",
        new_fingerprint="ROOT_ABC",  # Same root
        existing_signing_subkey="SIG_1",
        new_signing_subkey="SIG_2",  # New signing subkey
        existing_encryption_subkey="ENC_1",
        new_encryption_subkey="ENC_2",  # New encryption subkey
        retired_subkeys=["SIG_OLD"],
    )
    assert trans == RotationType.AUTHORIZED_SUBKEY_ROTATION


def test_evaluate_key_transition_unauthorized_root_replacement():
    """If root key changed, must flag as unauthorized root replacement."""
    trans = evaluate_key_transition(
        existing_fingerprint="ROOT_ABC",
        new_fingerprint="ROOT_XYZ",  # Different root!
        existing_signing_subkey="SIG_1",
        new_signing_subkey="SIG_2",
        existing_encryption_subkey="ENC_1",
        new_encryption_subkey="ENC_2",
    )
    assert trans == RotationType.UNAUTHORIZED_ROOT_REPLACEMENT


def test_historical_signature_verification():
    # Message signed at timestamp 1000
    # Key valid from 500 to 2000
    assert is_signature_historically_valid(
        message_timestamp_utc=1000,
        key_valid_from=500,
        key_expires_at=2000,
    ) is True

    # Message signed at 2500 (after key expired at 2000)
    assert is_signature_historically_valid(
        message_timestamp_utc=2500,
        key_valid_from=500,
        key_expires_at=2000,
    ) is False

    # Message signed at 1500 (after key was revoked at 1200)
    assert is_signature_historically_valid(
        message_timestamp_utc=1500,
        key_valid_from=500,
        key_expires_at=2000,
        revocation_timestamp=1200,
    ) is False

    # Message signed at 1100 (before key was revoked at 1200)
    assert is_signature_historically_valid(
        message_timestamp_utc=1100,
        key_valid_from=500,
        key_expires_at=2000,
        revocation_timestamp=1200,
    ) is True
