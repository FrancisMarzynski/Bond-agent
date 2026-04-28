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
        raise UnsafeUrlError("Adres URL nie może być pusty.")

    try:
        parsed = urlsplit(candidate)
    except Exception as exc:
        raise UnsafeUrlError("Adres URL jest nieprawidłowy.") from exc

    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("Adres URL musi używać schematu http lub https.")
    if not parsed.netloc:
        raise UnsafeUrlError("Adres URL musi zawierać host.")

    try:
        username = parsed.username
        password = parsed.password
        host = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("Adres URL zawiera nieprawidłowy host lub port.") from exc

    if username or password:
        raise UnsafeUrlError("Adres URL nie może zawierać danych logowania.")
    if not host:
        raise UnsafeUrlError("Adres URL musi zawierać host.")

    if not allow_private:
        for address in _resolve_host_addresses(host):
            ip = ipaddress.ip_address(address)
            if _is_non_public_ip(ip):
                raise UnsafeUrlError(
                    f"Host adresu URL rozwiązuje się do niepublicznego adresu: {ip.compressed}"
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
            raise UnsafeUrlError("Nie udało się rozwiązać hosta podanego w adresie URL.") from exc

        addresses: list[str] = []
        for _, _, _, _, sockaddr in results:
            address = sockaddr[0]
            if address not in addresses:
                addresses.append(address)

        if not addresses:
            raise UnsafeUrlError("Nie udało się rozwiązać hosta podanego w adresie URL.")

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
