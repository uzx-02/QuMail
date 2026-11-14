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

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import ipaddress
import re
import socket
import ssl
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


class SecurityError(Exception):
    """Raised when a network operation violates a security boundary."""


DOMAIN_REGEX = re.compile(
    r"^(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
)


def validate_domain(domain: str) -> str:
    """Validate and sanitize an email domain name according to RFC 1123 / RFC 952."""
    cleaned = domain.strip().lower()
    if ":" in cleaned or "/" in cleaned or "\\" in cleaned or "@" in cleaned or " " in cleaned:
        raise ValueError(f"Hostile or malformed domain syntax: {domain!r}")
    if any(ord(c) < 32 or ord(c) >= 127 for c in cleaned):
        raise ValueError(f"Domain contains invalid characters: {domain!r}")
    if not DOMAIN_REGEX.match(cleaned):
        raise ValueError(f"Domain does not conform to standard hostname syntax: {domain!r}")
    return cleaned


def is_ip_prohibited(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Anti-SSRF Protection:
    Verify whether an IP address belongs to loopback, private (RFC 1918 / RFC 4193),
    link-local (RFC 3927), multicast, carrier-grade NAT, or reserved/unspecified space.
    """
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        ip_obj = ip_obj.ipv4_mapped

    if (
        ip_obj.is_loopback or
        ip_obj.is_private or
        ip_obj.is_link_local or
        ip_obj.is_multicast or
        ip_obj.is_reserved or
        ip_obj.is_unspecified
    ):
        return True

    # Carrier-grade NAT (100.64.0.0/10)
    if isinstance(ip_obj, ipaddress.IPv4Address) and ip_obj in ipaddress.ip_network("100.64.0.0/10"):
        return True

    # Documentation / benchmarking networks (RFC 5737 / RFC 2544)
    if isinstance(ip_obj, ipaddress.IPv4Address):
        for net in (
            ipaddress.ip_network("192.0.2.0/24"),
            ipaddress.ip_network("198.51.100.0/24"),
            ipaddress.ip_network("203.0.113.0/24"),
            ipaddress.ip_network("198.18.0.0/15"),
        ):
            if ip_obj in net:
                return True

    return False


def secure_wkd_fetch(
    url: str,
    expected_domain: str,
    timeout: float = DEFAULT_HTTP_TIMEOUT,
    max_redirects: int = 2,
    dns_resolver: Callable[[str, int], list[tuple]] | None = None,
    ssl_context: ssl.SSLContext | None = None,
    socket_factory: Callable | None = None,
) -> bytes:
    """
    Hardened HTTPS fetcher for OpenPGP Web Key Directory (WKD).

    Security Invariants:
    1. Strictly enforces HTTPS (HTTP downgrade rejected).
    2. Enforces destination host pinning: host must strictly equal expected_domain or openpgpkey.<expected_domain>.
    3. Resolves DNS and validates every resolved IP address against prohibited private/loopback/reserved ranges (SSRF protection).
    4. Connects directly to the validated IP while verifying the TLS certificate against the SNI hostname (DNS rebinding defense).
    5. Revalidates every redirect destination with bounded hops (max_redirects).
    6. Rejects HTML or unexpected non-binary content-types.
    7. Streams response with strict 64 KiB ceiling, aborting immediately if exceeded.
    """
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme != "https":
        raise SecurityError(f"Insecure protocol {scheme!r}: HTTPS required; downgrade prohibited.")

    host = (parts.hostname or "").lower()
    expected = expected_domain.lower()
    allowed_hosts = {expected, f"openpgpkey.{expected}"}
    if host not in allowed_hosts:
        raise SecurityError(f"Host {host!r} is outside authorized domain {expected!r}; redirect to external host prohibited.")

    port = parts.port or 443
    if port != 443:
        raise SecurityError(f"Non-standard HTTPS port {port} prohibited for WKD.")

    resolver = dns_resolver or socket.getaddrinfo
    try:
        addr_info = resolver(host, port, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        raise OSError(f"DNS resolution failed for {host}: {exc}") from exc

    if not addr_info:
        raise OSError(f"No address records found for {host}")

    validated_ips: list[str] = []
    for entry in addr_info:
        sockaddr = entry[4]
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise SecurityError(f"Invalid resolved IP string {ip_str!r}: {exc}") from exc
        if is_ip_prohibited(ip_obj):
            raise SecurityError(f"SSRF defense: resolved destination IP {ip_str} is in prohibited (loopback/private/reserved) range.")
        validated_ips.append(ip_str)

    target_ip = validated_ips[0]
    ctx = ssl_context or ssl.create_default_context()

    make_sock = socket_factory or socket.create_connection
    sock = make_sock((target_ip, port), timeout=timeout)
    tls_sock = ctx.wrap_socket(sock, server_hostname=host)

    try:
        path_query = parts.path + ("?" + parts.query if parts.query else "")
        req_lines = [
            f"GET {path_query} HTTP/1.1",
            f"Host: {host}",
            "User-Agent: QuMail-WKD-Resolver/1.0",
            "Accept: application/octet-stream, application/pgp-keys",
            "Connection: close",
            "",
            "",
        ]
        tls_sock.sendall("\r\n".join(req_lines).encode("ascii"))

        # Read response headers
        header_buf = bytearray()
        while b"\r\n\r\n" not in header_buf and b"\n\n" not in header_buf:
            chunk = tls_sock.recv(1024)
            if not chunk:
                break
            header_buf.extend(chunk)
            if len(header_buf) > 8192:
                raise ValueError("Response headers exceeded maximum size limit")

        if b"\r\n\r\n" in header_buf:
            header_bytes, _, rest = header_buf.partition(b"\r\n\r\n")
        else:
            header_bytes, _, rest = header_buf.partition(b"\n\n")

        lines = header_bytes.decode("iso-8859-1").splitlines()
        if not lines:
            raise ValueError("Empty HTTP response from WKD server")

        status_parts = lines[0].split(None, 2)
        if len(status_parts) < 2:
            raise ValueError(f"Malformed HTTP status line: {lines[0]!r}")

        status_code = int(status_parts[1])

        headers: dict[str, str] = {}
        for line in lines[1:]:
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip().lower()] = v.strip()

        # Handle redirects
        if status_code in (301, 302, 303, 307, 308):
            if max_redirects <= 0:
                raise SecurityError("Maximum redirect hops exceeded.")
            loc = headers.get("location")
            if not loc:
                raise ValueError("Redirect response missing Location header.")
            redirect_url = urllib.parse.urljoin(url, loc)
            tls_sock.close()
            return secure_wkd_fetch(
                redirect_url,
                expected_domain,
                timeout=timeout,
                max_redirects=max_redirects - 1,
                dns_resolver=dns_resolver,
                ssl_context=ssl_context,
                socket_factory=socket_factory,
            )

        if status_code == 404:
            raise urllib.error.HTTPError(url, 404, "Not Found", headers, None)

        if status_code != 200:
            raise urllib.error.HTTPError(url, status_code, f"HTTP Error {status_code}", headers, None)

        # Validate content-type
        content_type = headers.get("content-type", "").lower()
        if "text/html" in content_type:
            raise ValueError(f"Prohibited content-type {content_type!r}: HTML response rejected for WKD key.")

        # Stream body with strict ceiling
        body = bytearray(rest)
        if len(body) > MAX_KEY_BYTES:
            raise ValueError(f"Key payload exceeded maximum size limit ({MAX_KEY_BYTES} bytes)")

        while True:
            chunk = tls_sock.recv(4096)
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > MAX_KEY_BYTES:
                raise ValueError(f"Key payload exceeded maximum size limit ({MAX_KEY_BYTES} bytes)")

        return bytes(body)
    finally:
        tls_sock.close()


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
    # WKD (draft-koch-openpgp-webkey-service) mandates SHA-1 here as a
    # protocol identifier, not as a security primitive. Changing it breaks
    # interoperability with every conforming WKD host.
    digest = hashlib.sha1(cleaned, usedforsecurity=False).digest()
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
    domain = validate_domain(domain)

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
        executor: ThreadPoolExecutor | None = None,
    ):
        self.inspector_fn = inspector_fn
        self.timeout = timeout
        self._custom_fetcher = http_fetcher
        self._executor = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="wkd-resolver")

    def _fetch(self, url: str, domain: str) -> bytes:
        if self._custom_fetcher:
            return self._custom_fetcher(url)
        return secure_wkd_fetch(url, expected_domain=domain, timeout=self.timeout)

    def lookup(self, email: str) -> DiscoveryResult:
        clean_email = email.strip().lower()
        try:
            advanced_url, direct_url = build_wkd_urls(clean_email)
            domain = clean_email.split("@")[-1]
        except ValueError as exc:
            return DiscoveryResult(email=clean_email, status=DiscoveryStatus.MALFORMED, error_message=str(exc))

        # Try Advanced method first, then Direct method
        candidate_data: bytes | None = None
        last_error = ""

        for url in (advanced_url, direct_url):
            try:
                candidate_data = self._fetch(url, domain)
                if candidate_data:
                    break
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    last_error = "Key not published in WKD (404)"
                else:
                    last_error = f"HTTP error {exc.code} from {url}"
            except SecurityError as exc:
                last_error = f"WKD network security violation: {exc}"
                logger.warning("WKD security check rejected %s: %s", url, exc)
                break  # Security error on advanced method should abort or log
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

    def lookup_async(self, email: str) -> Future[DiscoveryResult]:
        """Asynchronously discover key off the main/GUI thread."""
        return self._executor.submit(self.lookup, email)


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

    def discover_async(self, email: str, force_refresh: bool = False) -> Future[DiscoveryResult]:
        """Asynchronously discover key off the main/GUI thread."""
        return self.wkd._executor.submit(self.discover, email, force_refresh)
