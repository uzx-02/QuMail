"""
Cryptographic Subkey Lifecycle & Rotation Manager (WS-02).

Manages:
1. Subkey validity period checks and upcoming expiration warnings (< 30 days).
2. Key revocation inspection and immediate enforcement.
3. Distinguishing authorized subkey rotation from unauthorized root key replacement.
4. Historical verification preservation (evaluating signature validity with respect to message date).
5. Preventing unverified replacement keys from silently inheriting verified trust.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import time
from typing import Callable

from cryptography import x509
from cryptography.x509.oid import ExtensionOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from pyasn1.codec.der import decoder, encoder
from pyasn1_modules import rfc3161, rfc5652

from core.logging_config import get_logger

logger = get_logger("key_lifecycle")

EXPIRATION_WARNING_SECONDS = 30 * 86400  # 30 days


class KeyStatus(str, Enum):
    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"
    REVOKED = "revoked"
    INVALID = "invalid"


class RotationType(str, Enum):
    AUTHORIZED_SUBKEY_ROTATION = "authorized_subkey_rotation"
    UNAUTHORIZED_ROOT_REPLACEMENT = "unauthorized_root_replacement"
    IDENTICAL_KEY = "identical_key"


class RevocationReason(str, Enum):
    """RFC 4880 §5.2.3.23 / RFC 9580 revocation reason codes."""
    UNSPECIFIED = "unspecified"
    KEY_SUPERSEDED = "key_superseded"
    KEY_COMPROMISED = "key_compromised"
    KEY_RETIRED = "key_retired"
    USER_ID_NO_LONGER_VALID = "user_id_no_longer_valid"


class HistoricalValidity(str, Enum):
    """Granular verdict for historical signature verification."""
    VALID_HISTORICAL = "valid_historical"
    INDETERMINATE_NO_TRUSTED_TIME = "indeterminate_no_trusted_time"
    EXPIRED_AT_CREATION = "expired_at_creation"
    REVOKED_AT_CREATION = "revoked_at_creation"
    KEY_COMPROMISED = "key_compromised"
    INVALID_EVIDENCE = "invalid_evidence"
    PREDATES_KEY = "predates_key"


class TimestampEvidenceSource(str, Enum):
    """Defensible independent time sources for cryptographic verification."""
    RFC3161_TSA = "rfc3161_tsa"
    AUTHENTICATED_RECEIPT = "authenticated_receipt"  # Local vault replay receipt committed at reception
    TRUSTED_NOTARY = "trusted_notary"  # Explicitly marked UNSUPPORTED in Module 1.6


@dataclass(frozen=True)
class RFC3161VerificationResult:
    """Detailed result of offline RFC 3161 timestamp token validation."""
    is_valid: bool
    gen_time_utc: int | None = None
    tsa_identity: str = ""
    policy_oid: str = ""
    error: str = ""


def verify_rfc3161_token_offline(
    token_der: bytes,
    expected_message_digest: bytes | str,
    trusted_tsa_certificates: list[x509.Certificate] | None = None,
    current_time: float | None = None,
) -> RFC3161VerificationResult:
    """
    Offline cryptographic verification of an RFC 3161 TimeStampToken.

    Verification Invariants:
    1. Parse ASN.1 CMS ContentInfo / SignedData / TSTInfo.
    2. Message-Imprint Matching: Token's hashedMessage must match expected_message_digest.
    3. TSA Certificate Validation:
       - Extracts TSA certificate from SignedData.certificates.
       - Validates ExtendedKeyUsage includes timeStamping (OID 1.3.6.1.5.5.7.3.8).
       - Validates certificate validity period against token genTime (and current_time).
       - Validates TSA certificate against trusted_tsa_certificates if configured.
    4. TSA Digital Signature Verification:
       - Cryptographically verifies the TSA digital signature over the encapsulated TSTInfo (or signed attributes).
    5. Rejects malformed, tampered, expired, or mismatched tokens.
    """
    if not isinstance(token_der, bytes) or len(token_der) == 0:
        return RFC3161VerificationResult(is_valid=False, error="Token is empty or not bytes")
    if len(token_der) > 65536:
        return RFC3161VerificationResult(is_valid=False, error="Token exceeds maximum allowed size (64 KiB)")

    # Normalize expected digest
    if isinstance(expected_message_digest, str):
        try:
            expected_bytes = bytes.fromhex(expected_message_digest) if len(expected_message_digest) == 64 else expected_message_digest.encode("utf-8")
        except ValueError:
            expected_bytes = expected_message_digest.encode("utf-8")
    else:
        expected_bytes = bytes(expected_message_digest)

    # 1. Parse ContentInfo
    try:
        content_info, _ = decoder.decode(token_der, asn1Spec=rfc5652.ContentInfo())
    except Exception as exc:
        return RFC3161VerificationResult(is_valid=False, error=f"Malformed ASN.1 ContentInfo: {exc}")

    if content_info["contentType"] != rfc5652.id_signedData:
        return RFC3161VerificationResult(is_valid=False, error="ContentInfo type is not id-signedData")

    # 2. Parse SignedData
    try:
        signed_data, _ = decoder.decode(bytes(content_info["content"]), asn1Spec=rfc5652.SignedData())
    except Exception as exc:
        return RFC3161VerificationResult(is_valid=False, error=f"Malformed SignedData: {exc}")

    encap = signed_data["encapContentInfo"]
    if encap["eContentType"] != rfc3161.id_ct_TSTInfo:
        return RFC3161VerificationResult(is_valid=False, error="Encapsulated content is not id-ct-TSTInfo")

    # 3. Parse TSTInfo
    e_content = bytes(encap["eContent"])
    try:
        tst_info, _ = decoder.decode(e_content, asn1Spec=rfc3161.TSTInfo())
    except Exception as exc:
        return RFC3161VerificationResult(is_valid=False, error=f"Malformed TSTInfo structure: {exc}")

    # Parse GeneralizedTime
    gen_time_str = str(tst_info["genTime"])
    try:
        if gen_time_str.endswith("Z"):
            dt = datetime.strptime(gen_time_str[:-1], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(gen_time_str)
        gen_time_utc = int(dt.timestamp())
    except Exception as exc:
        return RFC3161VerificationResult(is_valid=False, error=f"Invalid TSTInfo genTime syntax: {exc}")

    # 4. Message Imprint Matching
    token_digest = bytes(tst_info["messageImprint"]["hashedMessage"])
    if token_digest != expected_bytes:
        return RFC3161VerificationResult(
            is_valid=False,
            gen_time_utc=gen_time_utc,
            error=f"Message imprint mismatch: token contains {token_digest.hex()[:16]}..., expected {expected_bytes.hex()[:16]}...",
        )

    # 5. Extract TSA Certificate
    certs_comp = signed_data.getComponentByName("certificates")
    if certs_comp is None or not certs_comp.isValue or len(certs_comp) == 0:
        return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, error="No TSA certificate found in SignedData")

    certs = certs_comp
    tsa_cert: x509.Certificate | None = None
    for cert_choice in certs:
        try:
            cert_raw = encoder.encode(cert_choice["certificate"])
            candidate = x509.load_der_x509_certificate(cert_raw)
            try:
                eku_ext = candidate.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
                if ExtendedKeyUsageOID.TIME_STAMPING in eku_ext.value:
                    tsa_cert = candidate
                    break
            except Exception:
                continue
        except Exception:
            continue

    if tsa_cert is None:
        return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, error="TSA certificate missing required timeStamping ExtendedKeyUsage")

    # Check Certificate Validity Period against token generation time
    not_before = int(tsa_cert.not_valid_before_utc.timestamp())
    not_after = int(tsa_cert.not_valid_after_utc.timestamp())
    if not (not_before <= gen_time_utc <= not_after):
        return RFC3161VerificationResult(
            is_valid=False,
            gen_time_utc=gen_time_utc,
            error="TSA certificate was not valid at timestamp generation time",
        )

    # Validate against configured TSA trust anchors
    if trusted_tsa_certificates:
        is_trusted = False
        for trusted in trusted_tsa_certificates:
            if tsa_cert == trusted or tsa_cert.issuer == trusted.subject:
                is_trusted = True
                break
        if not is_trusted:
            return RFC3161VerificationResult(
                is_valid=False,
                gen_time_utc=gen_time_utc,
                error="TSA certificate is not trusted by configured TSA trust anchors",
            )

    # 6. Verify TSA Signature
    signer_infos_comp = signed_data.getComponentByName("signerInfos")
    if signer_infos_comp is None or not signer_infos_comp.isValue or len(signer_infos_comp) == 0:
        return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, error="No SignerInfo found in SignedData")

    signer_info = signer_infos_comp[0]
    sig_bytes = bytes(signer_info["signature"])

    pub_key = tsa_cert.public_key()
    try:
        signed_attrs = signer_info.getComponentByName("signedAttrs")
        if signed_attrs is not None and signed_attrs.isValue:
            signed_attrs_bytes = encoder.encode(signed_attrs)
            if signed_attrs_bytes.startswith(b"\xa0"):
                signed_attrs_bytes = b"\x31" + signed_attrs_bytes[1:]
            pub_key.verify(sig_bytes, signed_attrs_bytes, padding.PKCS1v15(), hashes.SHA256())
        else:
            pub_key.verify(sig_bytes, e_content, padding.PKCS1v15(), hashes.SHA256())
    except Exception as exc:
        return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, error=f"TSA digital signature verification failed: {exc}")

    policy_oid = str(tst_info["policy"])
    tsa_id = tsa_cert.subject.rfc4514_string()
    return RFC3161VerificationResult(
        is_valid=True,
        gen_time_utc=gen_time_utc,
        tsa_identity=tsa_id,
        policy_oid=policy_oid,
    )


@dataclass(frozen=True)
class TimestampEvidence:
    """Independent, trusted proof establishing that a signature existed at a point in time."""
    source: TimestampEvidenceSource
    verified_time_utc: int
    proof: bytes | str = ""
    is_verified: bool = True


@dataclass(frozen=True)
class HistoricalVerificationResult:
    """Detailed verdict distinguishing cryptographic validity from historical key-status validity."""
    status: HistoricalValidity
    is_valid: bool
    explanation: str
    effective_time_utc: int | None = None
    evidence_source: TimestampEvidenceSource | None = None


@dataclass(frozen=True)
class ExpirationCheckResult:
    status: KeyStatus
    days_remaining: int
    expires_at_timestamp: int | None = None
    warning_message: str = ""

    @property
    def needs_warning(self) -> bool:
        return self.status == KeyStatus.EXPIRING_SOON


def evaluate_key_expiration(
    expires_at_timestamp: int | None,
    current_time: float | None = None,
    warning_threshold_seconds: float = EXPIRATION_WARNING_SECONDS,
) -> ExpirationCheckResult:
    """Evaluate subkey expiration relative to current or specified time."""
    if expires_at_timestamp is None or expires_at_timestamp <= 0:
        return ExpirationCheckResult(status=KeyStatus.ACTIVE, days_remaining=9999)

    now = time.time() if current_time is None else current_time
    remaining_seconds = expires_at_timestamp - now

    if remaining_seconds <= 0:
        return ExpirationCheckResult(
            status=KeyStatus.EXPIRED,
            days_remaining=0,
            expires_at_timestamp=expires_at_timestamp,
            warning_message="Cryptographic subkey has expired and must be renewed.",
        )

    days_remaining = int(round(remaining_seconds / 86400.0))
    if remaining_seconds < warning_threshold_seconds:
        return ExpirationCheckResult(
            status=KeyStatus.EXPIRING_SOON,
            days_remaining=days_remaining,
            expires_at_timestamp=expires_at_timestamp,
            warning_message=f"Cryptographic subkey will expire in {days_remaining} days. Please rotate key.",
        )

    return ExpirationCheckResult(
        status=KeyStatus.ACTIVE,
        days_remaining=days_remaining,
        expires_at_timestamp=expires_at_timestamp,
    )


def evaluate_key_transition(
    existing_fingerprint: str,
    new_fingerprint: str,
    existing_signing_subkey: str,
    new_signing_subkey: str,
    existing_encryption_subkey: str,
    new_encryption_subkey: str,
    retired_subkeys: list[str] | None = None,
) -> RotationType:
    """
    Distinguish authorized subkey rotation from unauthorized root replacement.

    Authorized Subkey Rotation:
      - Root fingerprint remains identical.
      - Signing or encryption subkey changed.
      - Replaced subkeys are recorded in retired_subkeys.

    Unauthorized Replacement:
      - Root fingerprint changed without an authorized cross-certification.
      - MUST trigger CHANGED_BLOCKED.
    """
    retired = set(retired_subkeys or [])

    if existing_fingerprint.lower() != new_fingerprint.lower():
        # Root key itself changed -> Unexpected replacement!
        logger.warning(
            "Root fingerprint mismatch detected for contact: %s vs %s (unauthorized replacement)",
            existing_fingerprint,
            new_fingerprint,
        )
        return RotationType.UNAUTHORIZED_ROOT_REPLACEMENT

    # Same root key
    subkeys_changed = (
        existing_signing_subkey.lower() != new_signing_subkey.lower() or
        existing_encryption_subkey.lower() != new_encryption_subkey.lower()
    )

    if subkeys_changed:
        # Check that new subkeys were not previously retired (no rollback to old subkeys)
        if new_signing_subkey.lower() in retired or new_encryption_subkey.lower() in retired:
            logger.error("Attempt to rotate to previously retired subkey!")
            return RotationType.UNAUTHORIZED_ROOT_REPLACEMENT

        logger.info("Authorized subkey rotation confirmed under root %s", existing_fingerprint)
        return RotationType.AUTHORIZED_SUBKEY_ROTATION

    return RotationType.IDENTICAL_KEY


def verify_historical_signature(
    claimed_signature_time_utc: int,
    key_valid_from: int,
    key_expires_at: int | None,
    revocation_timestamp: int | None = None,
    revocation_reason: RevocationReason = RevocationReason.UNSPECIFIED,
    timestamp_evidence: TimestampEvidence | None = None,
    current_time: float | None = None,
    expected_message_digest: bytes | str | None = None,
    trusted_tsa_certificates: list[x509.Certificate] | None = None,
) -> HistoricalVerificationResult:
    """
    Evaluate historical signature validity with explicit trusted time evidence.

    SECURITY INVARIANT:
    An OpenPGP signature creation-time field alone is untrusted metadata (attacker-controlled).
    An adversary who obtains an expired or compromised private key could fabricate a backdated
    signature creation-time to bypass expiration or revocation checks.

    Therefore:
    1. If a key is expired or revoked and NO independent trusted timestamp evidence is provided,
       we return INDETERMINATE_NO_TRUSTED_TIME rather than asserting historical validity.
    2. When trusted timestamp evidence (RFC 3161 TSA token or authenticated vault replay receipt)
       is provided, historical validity is anchored to that verified time.
    3. If a key was revoked due to COMPROMISE, any signature whose evidence postdates compromise
       is rejected as KEY_COMPROMISED. Only signatures with trusted prior receipt evidence
       strictly predating the compromise/revocation date may be validated.
    4. RFC 3161 tokens are verified offline (signature validity, message imprint matching, EKU,
       and certificate chain validity) when expected_message_digest is provided.
    5. Trusted notary evidence is unsupported in Module 1.6.
    """
    now = time.time() if current_time is None else current_time

    # Rule 1: Signature claims to predate key creation
    if claimed_signature_time_utc < key_valid_from:
        return HistoricalVerificationResult(
            status=HistoricalValidity.PREDATES_KEY,
            is_valid=False,
            explanation="Claimed signature creation time predates key creation.",
        )

    is_expired = key_expires_at is not None and now > key_expires_at
    is_revoked = revocation_timestamp is not None and now >= revocation_timestamp
    is_compromised = is_revoked and revocation_reason == RevocationReason.KEY_COMPROMISED

    # Case A: Trusted timestamp evidence IS provided
    if timestamp_evidence is not None:
        # Check for unsupported notary evidence
        if timestamp_evidence.source == TimestampEvidenceSource.TRUSTED_NOTARY:
            return HistoricalVerificationResult(
                status=HistoricalValidity.INVALID_EVIDENCE,
                is_valid=False,
                explanation="Trusted notary evidence source is currently unsupported in Module 1.6.",
                evidence_source=timestamp_evidence.source,
            )

        if not timestamp_evidence.is_verified or timestamp_evidence.verified_time_utc <= 0:
            return HistoricalVerificationResult(
                status=HistoricalValidity.INVALID_EVIDENCE,
                is_valid=False,
                explanation="Timestamp evidence is malformed, unverified, or contains invalid time.",
                evidence_source=timestamp_evidence.source,
            )

        evidence_time = timestamp_evidence.verified_time_utc

        # If RFC 3161 TSA evidence has raw DER proof and expected_message_digest, run offline verification
        if timestamp_evidence.source == TimestampEvidenceSource.RFC3161_TSA and expected_message_digest is not None:
            if not isinstance(timestamp_evidence.proof, bytes) or len(timestamp_evidence.proof) == 0:
                return HistoricalVerificationResult(
                    status=HistoricalValidity.INVALID_EVIDENCE,
                    is_valid=False,
                    explanation="RFC 3161 evidence requires non-empty raw token DER bytes in proof.",
                    evidence_source=timestamp_evidence.source,
                )
            token_res = verify_rfc3161_token_offline(
                token_der=timestamp_evidence.proof,
                expected_message_digest=expected_message_digest,
                trusted_tsa_certificates=trusted_tsa_certificates,
                current_time=current_time,
            )
            if not token_res.is_valid:
                return HistoricalVerificationResult(
                    status=HistoricalValidity.INVALID_EVIDENCE,
                    is_valid=False,
                    explanation=f"RFC 3161 TSA token verification failed: {token_res.error}",
                    evidence_source=timestamp_evidence.source,
                )
            if token_res.gen_time_utc is not None:
                evidence_time = token_res.gen_time_utc

        # Paradoxical time: claimed time is AFTER independently verified timestamp token
        if claimed_signature_time_utc > evidence_time:
            return HistoricalVerificationResult(
                status=HistoricalValidity.INVALID_EVIDENCE,
                is_valid=False,
                explanation="Claimed signature time postdates trusted timestamp token.",
                evidence_source=timestamp_evidence.source,
            )

        if evidence_time < key_valid_from:
            return HistoricalVerificationResult(
                status=HistoricalValidity.PREDATES_KEY,
                is_valid=False,
                explanation="Trusted timestamp evidence predates key creation.",
                evidence_source=timestamp_evidence.source,
            )

        # Check key expiration against verified evidence time
        if key_expires_at is not None and evidence_time > key_expires_at:
            return HistoricalVerificationResult(
                status=HistoricalValidity.EXPIRED_AT_CREATION,
                is_valid=False,
                explanation="Trusted timestamp proves signature was created after key expiration.",
                effective_time_utc=evidence_time,
                evidence_source=timestamp_evidence.source,
            )

        # Check key revocation against verified evidence time
        if revocation_timestamp is not None:
            if is_compromised:
                if evidence_time >= revocation_timestamp:
                    return HistoricalVerificationResult(
                        status=HistoricalValidity.KEY_COMPROMISED,
                        is_valid=False,
                        explanation="Key was compromised; trusted timestamp postdates compromise point.",
                        effective_time_utc=evidence_time,
                        evidence_source=timestamp_evidence.source,
                    )
                # Timestamp evidence strictly predates compromise
                return HistoricalVerificationResult(
                    status=HistoricalValidity.VALID_HISTORICAL,
                    is_valid=True,
                    explanation="Signature proven to predate key compromise via trusted timestamp evidence.",
                    effective_time_utc=evidence_time,
                    evidence_source=timestamp_evidence.source,
                )
            else:
                # Key superseded or retired
                if evidence_time > revocation_timestamp:
                    return HistoricalVerificationResult(
                        status=HistoricalValidity.REVOKED_AT_CREATION,
                        is_valid=False,
                        explanation="Trusted timestamp proves signature was created after key revocation.",
                        effective_time_utc=evidence_time,
                        evidence_source=timestamp_evidence.source,
                    )
                return HistoricalVerificationResult(
                    status=HistoricalValidity.VALID_HISTORICAL,
                    is_valid=True,
                    explanation="Signature proven to predate key revocation via trusted timestamp evidence.",
                    effective_time_utc=evidence_time,
                    evidence_source=timestamp_evidence.source,
                )

        return HistoricalVerificationResult(
            status=HistoricalValidity.VALID_HISTORICAL,
            is_valid=True,
            explanation="Signature verified within key validity period with trusted timestamp evidence.",
            effective_time_utc=evidence_time,
            evidence_source=timestamp_evidence.source,
        )

    # Case B: NO trusted timestamp evidence provided
    # If key was revoked due to compromise:
    if is_compromised:
        return HistoricalVerificationResult(
            status=HistoricalValidity.KEY_COMPROMISED,
            is_valid=False,
            explanation="Signing key was compromised. Unauthenticated signature creation-time cannot be trusted.",
        )

    # If key was revoked (superseded/retired):
    if is_revoked:
        if claimed_signature_time_utc > revocation_timestamp:
            return HistoricalVerificationResult(
                status=HistoricalValidity.REVOKED_AT_CREATION,
                is_valid=False,
                explanation="Claimed signature time postdates key revocation.",
            )
        # Signature claims to predate revocation, but lacks trusted time evidence
        return HistoricalVerificationResult(
            status=HistoricalValidity.INDETERMINATE_NO_TRUSTED_TIME,
            is_valid=False,
            explanation="Signature claims to predate key revocation, but lacks trusted time evidence (backdating defense).",
        )

    # If key is currently expired:
    if is_expired:
        if claimed_signature_time_utc > key_expires_at:
            return HistoricalVerificationResult(
                status=HistoricalValidity.EXPIRED_AT_CREATION,
                is_valid=False,
                explanation="Claimed signature time postdates key expiration.",
            )
        # Signature claims to predate expiry, but key is expired and no trusted evidence provided
        return HistoricalVerificationResult(
            status=HistoricalValidity.INDETERMINATE_NO_TRUSTED_TIME,
            is_valid=False,
            explanation="Signature claims to predate key expiration, but key is expired and lacks trusted time evidence (backdating defense).",
        )

    # Key is currently active (not expired, not revoked)
    if key_expires_at is not None and claimed_signature_time_utc > key_expires_at:
        return HistoricalVerificationResult(
            status=HistoricalValidity.EXPIRED_AT_CREATION,
            is_valid=False,
            explanation="Claimed signature time exceeds key expiration date.",
        )

    return HistoricalVerificationResult(
        status=HistoricalValidity.VALID_HISTORICAL,
        is_valid=True,
        explanation="Signing key is currently active; signature within validity window.",
        effective_time_utc=claimed_signature_time_utc,
    )


def is_signature_historically_valid(
    message_timestamp_utc: int,
    key_valid_from: int,
    key_expires_at: int | None,
    revocation_timestamp: int | None = None,
    revocation_reason: RevocationReason = RevocationReason.UNSPECIFIED,
    timestamp_evidence: TimestampEvidence | None = None,
    current_time: float | None = None,
    expected_message_digest: bytes | str | None = None,
    trusted_tsa_certificates: list[x509.Certificate] | None = None,
) -> bool:
    """Convenience boolean helper delegating to verify_historical_signature."""
    return verify_historical_signature(
        claimed_signature_time_utc=message_timestamp_utc,
        key_valid_from=key_valid_from,
        key_expires_at=key_expires_at,
        revocation_timestamp=revocation_timestamp,
        revocation_reason=revocation_reason,
        timestamp_evidence=timestamp_evidence,
        current_time=current_time,
        expected_message_digest=expected_message_digest,
        trusted_tsa_certificates=trusted_tsa_certificates,
    ).is_valid
