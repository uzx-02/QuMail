"""
OpenPGP Automated Key Discovery Service (WS-02).

Implements:
1. OpenPGP Web Key Directory (WKD) URL derivation and retrieval (RFC 9580 / draft-koch-openpgp-webkey-service).
2. Enterprise directory provider interface for corporate identity systems.
3. Bounded-TTL discovery caching with expiration and invalidation.
4. Strict domain and address validation (validating that the returned public key
   binds the target email address).

SECURITY PRINCIPLE:
WKD is strictly a KEY DISCOVERY mechanism, NOT an identity-trust mechanism.
A successfully retrieved key is NEVER automatically upgraded to Verified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import re
import time
from typing import Callable, Protocol
import urllib.error
import urllib.parse
import urllib.request

from core.logging_config import get_logger

logger = get_logger("discovery")

# Standard z-base-32 alphabet as specified in draft-koch-openpgp-webkey-service
ZBASE32_ALPHABET = "ybndrfg8ejkmcpqxot1uwisza345h769"
MAX_KEY_BYTES = 64 * 1024  # 64 KiB ceiling for public key payloads
DEFAULT_CACHE_TTL = 86400  # 24 hours
DEFAULT_HTTP_TIMEOUT = 5.0  # seconds


def zbase32_encode(data: bytes) -> str:
    """Encode bytes using the z-base-32 alphabet."""
    result = []
    buffer = 0
    bits_in_buffer = 0

    for byte in data:
        buffer = (buffer << 8) | byte
        bits_in_buffer += 8
        while bits_in_buffer >= 5:
            bits_in_buffer -= 5
            index = (buffer >> bits_in_buffer) & 0x1F
            result.append(ZBASE32_ALPHABET[index])

    if bits_in_buffer > 0:
        index = (buffer << (5 - bits_in_buffer)) & 0x1F
        result.append(ZBASE32_ALPHABET[index])

    return "".join(result)


def compute_wkd_hash(local_part: str) -> str:
    """Compute the 32-character z-base-32 SHA-1 hash of a lowercase local-part."""
    cleaned = local_part.strip().lower().encode("utf-8")
    digest = hashlib.sha1(cleaned).digest()
    encoded = zbase32_encode(digest)
    return encoded[:32]


def build_wkd_urls(email: str) -> tuple[str, str]:
    """
    Derive the direct and advanced WKD URLs for a given email address.
    Returns: (advanced_url, direct_url)
    """
    if "@" not in email:
        raise ValueError(f"Invalid email address: {email!r}")

    local_part, _, domain = email.partition("@")
    local_part = local_part.strip().lower()
    domain = domain.strip().lower()

    if not local_part or not domain:
        raise ValueError(f"Invalid email address: {email!r}")

    hu = compute_wkd_hash(local_part)
    encoded_local = urllib.parse.quote(local_part, safe="")

    # Advanced method: https://openpgpkey.<domain>/.well-known/openpgpkey/<domain>/hu/<hash>?l=<local>
    advanced_url = f"https://openpgpkey.{domain}/.well-known/openpgpkey/{domain}/hu/{hu}?l={encoded_local}"
    # Direct method: https://<domain>/.well-known/openpgpkey/<domain>/hu/<hash>?l=<local>
    direct_url = f"https://{domain}/.well-known/openpgpkey/{domain}/hu/{hu}?l={encoded_local}"

    return advanced_url, direct_url


class DiscoveryStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    MALFORMED = "malformed_key"
    ADDRESS_MISMATCH = "address_mismatch"
    NETWORK_ERROR = "network_error"
    OUTAGE = "directory_outage"
    CONFLICT = "conflicting_records"
    EXPIRED = "expired_result"


@dataclass(frozen=True)
class DiscoveredKey:
    email: str
    public_key_bytes: bytes
    fingerprint: str
    source: str  # "wkd", "enterprise_directory", "vault_cache"
    discovered_at: float = field(default_factory=time.time)
    ttl_seconds: float = DEFAULT_CACHE_TTL

    @property
    def is_expired(self) -> bool:
        return time.time() > (self.discovered_at + self.ttl_seconds)


@dataclass(frozen=True)
class DiscoveryResult:
    email: str
    status: DiscoveryStatus
    key: DiscoveredKey | None = None
    error_message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == DiscoveryStatus.SUCCESS and self.key is not None


class KeyDirectoryProvider(Protocol):
    """Protocol for pluggable key directory providers (WKD, Enterprise LDAP, etc.)."""
    def lookup(self, email: str) -> DiscoveryResult:
        ...


class WKDDiscoveryProvider:
    """OpenPGP Web Key Directory discovery provider."""

    def __init__(
        self,
        inspector_fn: Callable[[bytes], dict] | None = None,
        timeout: float = DEFAULT_HTTP_TIMEOUT,
        http_fetcher: Callable[[str], bytes] | None = None,
    ):
        self.inspector_fn = inspector_fn
        self.timeout = timeout
        self._http_fetcher = http_fetcher or self._default_fetch

    def _default_fetch(self, url: str) -> bytes:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "QuMail-WKD-Resolver/1.0",
                "Accept": "application/octet-stream",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = resp.read(MAX_KEY_BYTES + 1)
            if len(data) > MAX_KEY_BYTES:
                raise ValueError("Key payload exceeded maximum size limit")
            return data

    def lookup(self, email: str) -> DiscoveryResult:
        clean_email = email.strip().lower()
        try:
            advanced_url, direct_url = build_wkd_urls(clean_email)
        except ValueError as exc:
            return DiscoveryResult(email=clean_email, status=DiscoveryStatus.MALFORMED, error_message=str(exc))

        # Try Advanced method first, then Direct method
        candidate_data: bytes | None = None
        last_error = ""

        for url in (advanced_url, direct_url):
            try:
                candidate_data = self._http_fetcher(url)
                if candidate_data:
                    break
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    last_error = "Key not published in WKD (404)"
                else:
                    last_error = f"HTTP error {exc.code} from {url}"
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = f"Network error contacting {url}: {exc}"
            except Exception as exc:
                last_error = f"WKD fetch error: {exc}"

        if not candidate_data:
            return DiscoveryResult(
                email=clean_email,
                status=DiscoveryStatus.NOT_FOUND if "404" in last_error else DiscoveryStatus.NETWORK_ERROR,
                error_message=last_error,
            )

        # Inspect and validate the returned key material
        if self.inspector_fn:
            try:
                info = self.inspector_fn(candidate_data)
                fingerprint = info.get("fingerprint", "")
                addresses = [a.lower() for a in info.get("addresses", [])]

                if clean_email not in addresses:
                    return DiscoveryResult(
                        email=clean_email,
                        status=DiscoveryStatus.ADDRESS_MISMATCH,
                        error_message=f"Key in WKD does not bind address {clean_email} (found {addresses})",
                    )

                discovered = DiscoveredKey(
                    email=clean_email,
                    public_key_bytes=candidate_data,
                    fingerprint=fingerprint,
                    source="wkd",
                )
                return DiscoveryResult(email=clean_email, status=DiscoveryStatus.SUCCESS, key=discovered)
            except Exception as exc:
                return DiscoveryResult(
                    email=clean_email,
                    status=DiscoveryStatus.MALFORMED,
                    error_message=f"Returned key material failed inspection: {exc}",
                )

        # Basic fallback when inspector_fn not provided
        h = hashlib.sha256(candidate_data).hexdigest()
        discovered = DiscoveredKey(
            email=clean_email,
            public_key_bytes=candidate_data,
            fingerprint=h,
            source="wkd",
        )
        return DiscoveryResult(email=clean_email, status=DiscoveryStatus.SUCCESS, key=discovered)


class EnterpriseDirectoryProvider:
    """Administrator-managed corporate key directory."""

    def __init__(self, directory: dict[str, bytes] | None = None, inspector_fn: Callable[[bytes], dict] | None = None):
        self._directory: dict[str, bytes] = {k.strip().lower(): v for k, v in (directory or {}).items()}
        self.inspector_fn = inspector_fn

    def register(self, email: str, public_key_bytes: bytes) -> None:
        self._directory[email.strip().lower()] = public_key_bytes

    def lookup(self, email: str) -> DiscoveryResult:
        clean = email.strip().lower()
        data = self._directory.get(clean)
        if not data:
            return DiscoveryResult(email=clean, status=DiscoveryStatus.NOT_FOUND, error_message="Not found in enterprise directory")

        fingerprint = hashlib.sha256(data).hexdigest()
        if self.inspector_fn:
            try:
                info = self.inspector_fn(data)
                fingerprint = info.get("fingerprint", fingerprint)
                addresses = [a.lower() for a in info.get("addresses", [])]
                if clean not in addresses:
                    return DiscoveryResult(
                        email=clean,
                        status=DiscoveryStatus.ADDRESS_MISMATCH,
                        error_message=f"Enterprise key does not bind address {clean}",
                    )
            except Exception as exc:
                return DiscoveryResult(
                    email=clean,
                    status=DiscoveryStatus.MALFORMED,
                    error_message=f"Enterprise key inspection failed: {exc}",
                )

        key = DiscoveredKey(
            email=clean,
            public_key_bytes=data,
            fingerprint=fingerprint,
            source="enterprise_directory",
        )
        return DiscoveryResult(email=clean, status=DiscoveryStatus.SUCCESS, key=key)


class CachedKeyDiscoveryService:
    """
    Central discovery coordinator.
    Evaluates:
      1. Bounded TTL Cache
      2. Enterprise Directory
      3. OpenPGP WKD
    """

    def __init__(
        self,
        enterprise_provider: EnterpriseDirectoryProvider | None = None,
        wkd_provider: WKDDiscoveryProvider | None = None,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        max_cache_entries: int = 512,
    ):
        self.enterprise = enterprise_provider or EnterpriseDirectoryProvider()
        self.wkd = wkd_provider or WKDDiscoveryProvider()
        self.cache_ttl = cache_ttl
        self.max_cache_entries = max_cache_entries
        self._cache: dict[str, DiscoveredKey] = {}

    def get_cached(self, email: str) -> DiscoveredKey | None:
        clean = email.strip().lower()
        entry = self._cache.get(clean)
        if entry is None:
            return None
        if entry.is_expired:
            del self._cache[clean]
            return None
        return entry

    def invalidate(self, email: str) -> None:
        self._cache.pop(email.strip().lower(), None)

    def discover(self, email: str, force_refresh: bool = False) -> DiscoveryResult:
        clean = email.strip().lower()

        # 1. Check Cache
        if not force_refresh:
            cached = self.get_cached(clean)
            if cached:
                return DiscoveryResult(email=clean, status=DiscoveryStatus.SUCCESS, key=cached)

        # 2. Check Enterprise Directory first (takes precedence over public WKD)
        res = self.enterprise.lookup(clean)
        if res.ok:
            self._save_cache(clean, res.key)
            return res

        # 3. Check Web Key Directory (WKD)
        res = self.wkd.lookup(clean)
        if res.ok:
            self._save_cache(clean, res.key)
            return res

        return res

    def _save_cache(self, email: str, key: DiscoveredKey | None) -> None:
        if not key:
            return
        if len(self._cache) >= self.max_cache_entries:
            # Simple FIFO eviction
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        cached_entry = DiscoveredKey(
            email=key.email,
            public_key_bytes=key.public_key_bytes,
            fingerprint=key.fingerprint,
            source=key.source,
            discovered_at=key.discovered_at,
            ttl_seconds=self.cache_ttl,
        )
        self._cache[email] = cached_entry
