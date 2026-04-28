"""Reusable outbound URL validation for corpus ingest."""

import ipaddress
import socket
from urllib.parse import urlsplit


_RESOLUTION_CACHE: dict[str, tuple[str, ...]] = {}


class UnsafeUrlError(ValueError):
    """Raised when a URL is unsafe for outbound ingestion."""


def validate_public_url(url: str, *, allow_private: bool = False) -> str:
    """Validate an outbound ingest URL and return a normalized value."""
    candidate = url.strip()
    if not candidate:
        raise UnsafeUrlError("url must not be empty")

    try:
        parsed = urlsplit(candidate)
    except Exception as exc:
        raise UnsafeUrlError("url is invalid") from exc

    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("url must use http or https")
    if not parsed.netloc:
        raise UnsafeUrlError("url must include a host")

    try:
        username = parsed.username
        password = parsed.password
        host = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("url contains an invalid host or port") from exc

    if username or password:
        raise UnsafeUrlError("url must not include credentials")
    if not host:
        raise UnsafeUrlError("url must include a host")

    if not allow_private:
        for address in _resolve_host_addresses(host):
            ip = ipaddress.ip_address(address)
            if _is_non_public_ip(ip):
                raise UnsafeUrlError(
                    f"url host resolves to a non-public address: {ip.compressed}"
                )

    return parsed.geturl()


def _resolve_host_addresses(host: str) -> tuple[str, ...]:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        cached = _RESOLUTION_CACHE.get(host)
        if cached is not None:
            return cached

        try:
            results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeUrlError("url host could not be resolved") from exc

        addresses: list[str] = []
        for _, _, _, _, sockaddr in results:
            address = sockaddr[0]
            if address not in addresses:
                addresses.append(address)

        if not addresses:
            raise UnsafeUrlError("url host could not be resolved")

        resolved = tuple(addresses)
        _RESOLUTION_CACHE[host] = resolved
        return resolved

    return (ip.compressed,)


def _is_non_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
        or ip.is_reserved
    )
