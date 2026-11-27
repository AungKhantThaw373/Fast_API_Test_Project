"""Reject provider URLs that could reach the host or its metadata service."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

from app.config import settings


def _assert_public_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_private: bool = False,
) -> None:
    # Loopback and LAN addresses are only ever accepted for the bundled local
    # Ollama provider. Link-local addresses stay blocked even there: that range
    # contains cloud metadata endpoints such as 169.254.169.254.
    blocked = ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    if not allow_private and (ip.is_private or ip.is_loopback):
        blocked = True
    if blocked:
        raise ValueError("Provider URL points to a private or reserved address.")


def _assert_syntax(url: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ValueError("Enter a valid API base URL.") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid http:// or https:// API base URL.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API base URLs cannot contain credentials, query parameters, or a fragment.")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Enter a valid API base URL.")
    return parsed.hostname, parsed.scheme, port or (443 if parsed.scheme == "https" else 80)


def _resolve(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ValueError("That provider host could not be resolved.") from None
    return [str(info[4][0]) for info in infos]


async def assert_public_url(url: str, *, allow_private: bool = False) -> None:
    """Validate syntax, then resolve every address and reject non-public ones.

    ``allow_private`` exists for the local Ollama provider. It still rejects
    link-local, reserved, multicast, and unspecified addresses.

    This closes the ordinary SSRF path. DNS rebinding remains possible because
    the HTTP client resolves again; the manual documents that residual limit.
    """
    host, _scheme, port = _assert_syntax(url)
    try:
        _assert_public_ip(ipaddress.ip_address(host), allow_private=allow_private)
        return
    except ValueError as exc:
        if "private or reserved" in str(exc):
            raise
        # Not a literal address; resolve it below.

    if settings.PROVIDER_HOST_ALLOWLIST:
        allowed = {item.strip().lower() for item in settings.PROVIDER_HOST_ALLOWLIST.split(",") if item.strip()}
        if host.lower() not in allowed:
            raise ValueError("That provider host is not on this server's allowlist.")

    addresses = await asyncio.to_thread(_resolve, host, port)
    if not addresses:
        raise ValueError("That provider host could not be resolved.")
    for address in addresses:
        _assert_public_ip(ipaddress.ip_address(address), allow_private=allow_private)


def provider_http_client(**kwargs: object) -> httpx.AsyncClient:
    """The only client provider calls use: redirects are never followed."""
    return httpx.AsyncClient(follow_redirects=False, **kwargs)  # type: ignore[arg-type]