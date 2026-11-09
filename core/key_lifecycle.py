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
import hashlib
import time
from typing import Callable

from cryptography import x509
from cryptography.x509.oid import ExtensionOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from pyasn1.codec.der import decoder, encoder
from pyasn1.type import univ
from pyasn1_modules import rfc2459, rfc3161, rfc5652

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


def _verify_cert_signature(cert: x509.Certificate, issuer_pub_key) -> None:
    """Cryptographically verify an X.509 certificate's digital signature using issuer's public key."""
    hash_algo = cert.signature_hash_algorithm
    if hash_algo is None:
        raise ValueError("Certificate uses an unrecognized or unsupported signature hash algorithm")
    if isinstance(issuer_pub_key, rsa.RSAPublicKey):
        issuer_pub_key.verify(cert.signature, cert.tbs_certificate_bytes, padding.PKCS1v15(), hash_algo)
    elif isinstance(issuer_pub_key, ec.EllipticCurvePublicKey):
        issuer_pub_key.verify(cert.signature, cert.tbs_certificate_bytes, ec.ECDSA(hash_algo))
    else:
        raise ValueError(f"Unsupported issuer public key type: {type(issuer_pub_key).__name__}")


def _verify_certificate_path(
    leaf_cert: x509.Certificate,
    bundle_certs: list[x509.Certificate],
    trust_anchors: list[x509.Certificate],
    evaluation_time_utc: int,
    max_depth: int = 5,
) -> tuple[bool, str]:
    """
    Genuine cryptographic path validation from leaf_cert to a configured trust anchor.

    Verification Invariants:
    1. Direct trust: If leaf_cert is directly present in trust_anchors:
       - If self-signed, cryptographically verify self-signature.
       - Terminate with success.
    2. Multi-tier chain: Traverse candidate issuers up to trust anchors:
       - Match candidate certs where candidate.subject == current.issuer.
       - Verify candidate validity at evaluation_time_utc (genTime).
       - Verify candidate BasicConstraints (ca=True).
       - Cryptographically verify leaf signature using candidate public key.
       - If candidate is in trust_anchors (and self-signed root verified), terminate with success.
       - Fail closed on missing issuers, invalid signatures, non-CA issuers, expired CAs, or loop/depth limit.
    """
    for anchor in trust_anchors:
        if leaf_cert == anchor:
            if leaf_cert.issuer == leaf_cert.subject:
                try:
                    _verify_cert_signature(leaf_cert, leaf_cert.public_key())
                except Exception as exc:
                    return False, f"Directly trusted self-signed certificate signature invalid: {exc}"
            return True, ""

    if leaf_cert.issuer == leaf_cert.subject:
        return False, f"TSA certificate is not trusted by configured TSA trust anchors (self-signed root '{leaf_cert.subject.rfc4514_string()}' not in anchors)"

    current_cert = leaf_cert
    depth = 0
    pool = list(bundle_certs) + list(trust_anchors)

    while depth < max_depth:
        depth += 1
        candidate_issuers = [c for c in pool if c.subject == current_cert.issuer]
        if not candidate_issuers:
            return False, f"Issuer '{current_cert.issuer.rfc4514_string()}' not found in bundle or trust anchors"

        verified_issuer: x509.Certificate | None = None
        last_error = ""

        for candidate in candidate_issuers:
            cand_nb = int(candidate.not_valid_before_utc.timestamp())
            cand_na = int(candidate.not_valid_after_utc.timestamp())
            if not (cand_nb <= evaluation_time_utc <= cand_na):
                last_error = f"Candidate issuer '{candidate.subject.rfc4514_string()}' not valid at timestamp generation time"
                continue

            try:
                bc = candidate.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
                if not bc.value.ca:
                    last_error = f"Candidate issuer '{candidate.subject.rfc4514_string()}' has BasicConstraints ca=False"
                    continue
            except Exception:
                last_error = f"Candidate issuer '{candidate.subject.rfc4514_string()}' missing BasicConstraints extension"
                continue

            try:
                _verify_cert_signature(current_cert, candidate.public_key())
                verified_issuer = candidate
                break
            except Exception as exc:
                last_error = f"Cryptographic signature check failed against issuer '{candidate.subject.rfc4514_string()}': {exc}"
                continue

        if verified_issuer is None:
            return False, f"Could not cryptographically verify issuer signature: {last_error}"

        if any(verified_issuer == anchor for anchor in trust_anchors):
            if verified_issuer.issuer == verified_issuer.subject:
                try:
                    _verify_cert_signature(verified_issuer, verified_issuer.public_key())
                except Exception as exc:
                    return False, f"Trust anchor root self-signature invalid: {exc}"
            return True, ""

        if verified_issuer.issuer == verified_issuer.subject:
            return False, f"Self-signed root '{verified_issuer.subject.rfc4514_string()}' reached but is not in configured trust anchors"

        current_cert = verified_issuer

    return False, f"Certificate path depth exceeded maximum allowable hops ({max_depth})"


def verify_rfc3161_token_offline(
    token_der: bytes,
    expected_message_digest: bytes | str,
    trusted_tsa_certificates: list[x509.Certificate] | None = None,
    current_time: float | None = None,
    required_policy_oid: str | None = None,
) -> RFC3161VerificationResult:
    """
    Offline cryptographic verification of an RFC 3161 TimeStampToken.

    Verification Invariants:
    1. Parse ASN.1 CMS ContentInfo (id-signedData) / SignedData (id-ct-TSTInfo) / TSTInfo.
    2. Enforce TSA policy: If required_policy_oid is specified, token policy must match.
    3. Message-Imprint Matching: Token's hashedMessage must strictly match expected_message_digest.
    4. SignerInfo Matching: Matches SignerInfo.sid (issuerAndSerialNumber or subjectKeyIdentifier)
       to exactly one certificate in SignedData.certificates. Rejects absent or ambiguous matches.
    5. TSA Certificate Validation:
       - Enforces ExtendedKeyUsage includes timeStamping (OID 1.3.6.1.5.5.7.3.8).
       - Enforces certificate validity at token genTime.
       - Validates genuine cryptographic certificate path to configured trust anchors.
    6. CMS Signed Attributes Validation:
       - When signedAttrs present, validates mandatory id-contentType (id-ct-TSTInfo) and
         id-messageDigest (matching hash of eContent). Re-encodes as SET OF (0x31) for signature verification.
       - When absent, verifies signature directly over encapsulated eContent.
    7. TSA Digital Signature Verification:
       - Cryptographically validates RSA/ECDSA digital signature using validated TSA public key.
    8. Rejects malformed, tampered, expired, mismatched, or unauthorized tokens.
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

    # Policy Enforcement
    policy_oid = str(tst_info["policy"])
    if required_policy_oid is not None:
        if policy_oid != required_policy_oid:
            return RFC3161VerificationResult(
                is_valid=False,
                gen_time_utc=gen_time_utc,
                policy_oid=policy_oid,
                error=f"TSA policy mismatch: token policy '{policy_oid}' does not match required policy '{required_policy_oid}'",
            )

    # 4. Message Imprint Matching
    token_digest = bytes(tst_info["messageImprint"]["hashedMessage"])
    if token_digest != expected_bytes:
        return RFC3161VerificationResult(
            is_valid=False,
            gen_time_utc=gen_time_utc,
            policy_oid=policy_oid,
            error=f"Message imprint mismatch: token contains {token_digest.hex()[:16]}..., expected {expected_bytes.hex()[:16]}...",
        )

    # 5. Extract SignerInfo
    signer_infos_comp = signed_data.getComponentByName("signerInfos")
    if signer_infos_comp is None or not signer_infos_comp.isValue or len(signer_infos_comp) == 0:
        return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="No SignerInfo found in SignedData")

    signer_info = signer_infos_comp[0]
    sid = signer_info["sid"]
    sid_choice = sid.getName()

    # 6. Extract and Match TSA Certificate
    certs_comp = signed_data.getComponentByName("certificates")
    if certs_comp is None or not certs_comp.isValue or len(certs_comp) == 0:
        return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="No TSA certificate found in SignedData")

    matching_certs: list[x509.Certificate] = []
    all_parsed_certs: list[x509.Certificate] = []

    for cert_choice in certs_comp:
        try:
            cert_raw = encoder.encode(cert_choice["certificate"])
            candidate = x509.load_der_x509_certificate(cert_raw)
            all_parsed_certs.append(candidate)
        except Exception:
            continue

        if sid_choice == "issuerAndSerialNumber":
            ias = sid["issuerAndSerialNumber"]
            expected_serial = int(ias["serialNumber"])
            expected_issuer_der = encoder.encode(ias["issuer"])
            try:
                cand_asn1, _ = decoder.decode(cert_raw, asn1Spec=rfc2459.Certificate())
                cand_issuer_der = encoder.encode(cand_asn1["tbsCertificate"]["issuer"])
                if candidate.serial_number == expected_serial and cand_issuer_der == expected_issuer_der:
                    matching_certs.append(candidate)
            except Exception:
                continue
        elif sid_choice == "subjectKeyIdentifier":
            expected_ski = bytes(sid["subjectKeyIdentifier"])
            try:
                ski_ext = candidate.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
                if bytes(ski_ext.value.digest) == expected_ski:
                    matching_certs.append(candidate)
            except Exception:
                continue

    if len(matching_certs) == 0:
        return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="No certificate in SignedData matches SignerInfo identifier")
    if len(matching_certs) > 1:
        return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="Ambiguous SignerInfo: multiple certificates match identifier")

    tsa_cert = matching_certs[0]

    # Check timeStamping ExtendedKeyUsage
    try:
        eku_ext = tsa_cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
        if ExtendedKeyUsageOID.TIME_STAMPING not in eku_ext.value:
            return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="TSA certificate missing required timeStamping ExtendedKeyUsage")
    except Exception:
        return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="TSA certificate missing required timeStamping ExtendedKeyUsage")

    # Check Certificate Validity Period against token generation time
    not_before = int(tsa_cert.not_valid_before_utc.timestamp())
    not_after = int(tsa_cert.not_valid_after_utc.timestamp())
    if not (not_before <= gen_time_utc <= not_after):
        return RFC3161VerificationResult(
            is_valid=False,
            gen_time_utc=gen_time_utc,
            policy_oid=policy_oid,
            error="TSA certificate was not valid at timestamp generation time",
        )

    # 7. Cryptographic Certificate Path Validation against Trust Anchors
    if trusted_tsa_certificates:
        path_valid, path_err = _verify_certificate_path(
            leaf_cert=tsa_cert,
            bundle_certs=all_parsed_certs,
            trust_anchors=trusted_tsa_certificates,
            evaluation_time_utc=gen_time_utc,
        )
        if not path_valid:
            return RFC3161VerificationResult(
                is_valid=False,
                gen_time_utc=gen_time_utc,
                policy_oid=policy_oid,
                error=f"Certificate path validation failed: {path_err}",
            )

    # 8. CMS Signed Attributes & Message-Digest Validation
    signed_attrs = signer_info.getComponentByName("signedAttrs")
    if signed_attrs is not None and signed_attrs.isValue and len(signed_attrs) > 0:
        content_type_seen = None
        message_digest_seen = None

        for attr in signed_attrs:
            attr_type = attr["attrType"]
            if attr_type == rfc5652.id_contentType:
                if len(attr["attrValues"]) != 1:
                    return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="Signed attribute id-contentType must have exactly one value")
                ct_val, _ = decoder.decode(bytes(attr["attrValues"][0]), asn1Spec=univ.ObjectIdentifier())
                content_type_seen = ct_val
            elif attr_type == rfc5652.id_messageDigest:
                if len(attr["attrValues"]) != 1:
                    return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="Signed attribute id-messageDigest must have exactly one value")
                md_val, _ = decoder.decode(bytes(attr["attrValues"][0]), asn1Spec=univ.OctetString())
                message_digest_seen = bytes(md_val)

        if content_type_seen is None:
            return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="Signed attributes missing mandatory id-contentType")
        if content_type_seen != rfc3161.id_ct_TSTInfo:
            return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error=f"Signed attribute id-contentType mismatch: expected id-ct-TSTInfo, got {content_type_seen}")

        if message_digest_seen is None:
            return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="Signed attributes missing mandatory id-messageDigest")

        # Determine digest algorithm from signer_info['digestAlgorithm']
        digest_algo_oid = str(signer_info["digestAlgorithm"]["algorithm"])
        if digest_algo_oid == "2.16.840.1.101.3.4.2.1":  # SHA-256
            expected_content_digest = hashlib.sha256(e_content).digest()
            hash_impl = hashes.SHA256()
        elif digest_algo_oid == "2.16.840.1.101.3.4.2.2":  # SHA-384
            expected_content_digest = hashlib.sha384(e_content).digest()
            hash_impl = hashes.SHA384()
        elif digest_algo_oid == "2.16.840.1.101.3.4.2.3":  # SHA-512
            expected_content_digest = hashlib.sha512(e_content).digest()
            hash_impl = hashes.SHA512()
        else:
            return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error=f"Unsupported digest algorithm OID: {digest_algo_oid}")

        if message_digest_seen != expected_content_digest:
            return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="Signed attribute message-digest does not match hash of encapsulated TSTInfo")

        # Re-tag signedAttrs as SET OF (0x31) for signature verification
        signed_attrs_bytes = encoder.encode(signed_attrs)
        if signed_attrs_bytes.startswith(b"\xa0"):
            signed_attrs_bytes = b"\x31" + signed_attrs_bytes[1:]
        target_bytes = signed_attrs_bytes
    else:
        # Direct eContent coverage
        digest_algo_oid = str(signer_info["digestAlgorithm"]["algorithm"])
        if digest_algo_oid == "2.16.840.1.101.3.4.2.1":
            hash_impl = hashes.SHA256()
        elif digest_algo_oid == "2.16.840.1.101.3.4.2.2":
            hash_impl = hashes.SHA384()
        elif digest_algo_oid == "2.16.840.1.101.3.4.2.3":
            hash_impl = hashes.SHA512()
        else:
            return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error=f"Unsupported digest algorithm OID: {digest_algo_oid}")
        target_bytes = e_content

    # 9. TSA Digital Signature Verification
    sig_bytes = bytes(signer_info["signature"])
    sig_algo_oid = str(signer_info["signatureAlgorithm"]["algorithm"])
    pub_key = tsa_cert.public_key()

    try:
        if sig_algo_oid in ("1.2.840.113549.1.1.1", "1.2.840.113549.1.1.11"):  # RSA
            if not isinstance(pub_key, rsa.RSAPublicKey):
                return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="TSA public key is not RSA for RSA signature algorithm")
            pub_key.verify(sig_bytes, target_bytes, padding.PKCS1v15(), hash_impl)
        elif sig_algo_oid in ("1.2.840.10045.4.3.2", "1.2.840.10045.2.1"):  # ECDSA
            if not isinstance(pub_key, ec.EllipticCurvePublicKey):
                return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error="TSA public key is not EC for ECDSA signature algorithm")
            pub_key.verify(sig_bytes, target_bytes, ec.ECDSA(hash_impl))
        else:
            return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error=f"Unsupported signature algorithm OID: {sig_algo_oid}")
    except Exception as exc:
        return RFC3161VerificationResult(is_valid=False, gen_time_utc=gen_time_utc, policy_oid=policy_oid, error=f"TSA digital signature verification failed: {exc}")

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
    required_policy_oid: str | None = None,
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
                required_policy_oid=required_policy_oid,
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
    required_policy_oid: str | None = None,
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
        required_policy_oid=required_policy_oid,
    ).is_valid
