"""Block SSRF targets for outbound HTTP (custom tools, MCP connections)."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata.google",
        "kubernetes.default",
        "kubernetes.default.svc",
    }
)


class UnsafeUrlError(ValueError):
    """URL points at a non-public / disallowed target."""


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _allowlist(patterns: Iterable[str]) -> tuple[str, ...]:
    return tuple(part.strip().lower() for part in patterns if part and part.strip())


def _host_allowlisted(host: str, patterns: tuple[str, ...]) -> bool:
    return any(
        host == pattern
        or (pattern.startswith("*.") and host.endswith(pattern[1:]))
        for pattern in patterns
    )


def _ip_allowlisted(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address, patterns: tuple[str, ...]
) -> bool:
    for pattern in patterns:
        try:
            network = ipaddress.ip_network(pattern, strict=False)
        except ValueError:
            continue
        if ip.version == network.version and ip in network:
            return True
    return False


def _check_hostname(
    hostname: str, *, resolve: bool, allowed_hosts: tuple[str, ...] = ()
) -> None:
    host = hostname.strip(".").lower()
    if not host:
        raise UnsafeUrlError("url host is empty")
    if "{" in host or "}" in host:
        raise UnsafeUrlError("url host must not contain template placeholders")
    if _host_allowlisted(host, allowed_hosts):
        return
    if host in _BLOCKED_HOSTNAMES or host.endswith(".localhost"):
        raise UnsafeUrlError(f"url host is not allowed: {hostname}")

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked_ip(literal) and not _ip_allowlisted(literal, allowed_hosts):
            raise UnsafeUrlError(f"url targets a non-public address: {hostname}")
        return

    if not resolve:
        return

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"url host cannot be resolved: {hostname}") from exc
    if not infos:
        raise UnsafeUrlError(f"url host cannot be resolved: {hostname}")
    for info in infos:
        sockaddr = info[4]
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        if _is_blocked_ip(ip) and not _ip_allowlisted(ip, allowed_hosts):
            raise UnsafeUrlError(
                f"url resolves to a non-public address: {hostname} → {ip}"
            )


def assert_public_http_url(
    url: str, *, resolve: bool = True, allowed_hosts: Iterable[str] = ()
) -> str:
    """Validate that `url` is http(s) and does not target private/metadata hosts.

    ``resolve=False`` — только схема/denylist/IP-литералы (для create/update offline).
    ``resolve=True`` — ещё и DNS → проверка всех адресов (invoke / MCP probe).
    ``allowed_hosts`` — явный allowlist приватных целей (host, ``*.suffix``, IP/CIDR);
    передаётся только MCP-клиентом из ``MCP_EGRESS_ALLOWED_HOSTS``.

    Returns the stripped URL on success; raises ``UnsafeUrlError`` otherwise.
    """
    text = (url or "").strip()
    if not text:
        raise UnsafeUrlError("url is empty")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("url must start with http:// or https://")
    if not parsed.hostname:
        raise UnsafeUrlError("url host is empty")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("url must not contain credentials")
    _check_hostname(
        parsed.hostname, resolve=resolve, allowed_hosts=_allowlist(allowed_hosts)
    )
    return text
