"""Shared SSRF guard for outbound HTTP(S) downloads.

Validates that a URL points to a public network address before the
application fetches it. Extracted from the generated-image import guard in
``backend/app/api/ai.py`` so that every user-supplied download URL
(``asset_downloader``, generated image import) goes through one implementation.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any, NamedTuple
from urllib.parse import urlparse


class PublicUrlBlockedError(ValueError):
    """Raised when a URL must not be fetched (non-public target, bad scheme, userinfo)."""


class PublicUrlUnresolvedError(PublicUrlBlockedError):
    """Raised when the URL hostname cannot be resolved at validation time."""


class ResolvedPublicUrl(NamedTuple):
    parsed: Any
    hostname: str
    resolved_ip: str
    port: int


def is_public_ip_address(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(ip.is_global) and not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def resolve_public_http_url(url: str, *, label: str = "下载地址") -> ResolvedPublicUrl:
    """Validate ``url`` and return its DNS-pinned public resolution.

    Raises ``PublicUrlBlockedError`` (a ``ValueError``) when the URL is not an
    http(s) URL, carries userinfo, or resolves to any non-public address
    (private/loopback/link-local/reserved/CGNAT ranges), and
    ``PublicUrlUnresolvedError`` when the hostname cannot be resolved.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise PublicUrlBlockedError(f"{label}仅支持 http/https 公网地址")
    if parsed.username or parsed.password:
        raise PublicUrlBlockedError(f"{label}不支持携带用户名密码")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        literal_ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if not is_public_ip_address(str(literal_ip)):
            raise PublicUrlBlockedError(f"{label}不允许指向内网地址")
        resolved_ip = str(literal_ip)
    else:
        try:
            addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise PublicUrlUnresolvedError(f"{label}无法解析") from exc
        public_ips: list[str] = []
        for address in addresses:
            ip_text = str(address[4][0])
            if not is_public_ip_address(ip_text):
                raise PublicUrlBlockedError(f"{label}不允许指向内网地址")
            if ip_text not in public_ips:
                public_ips.append(ip_text)
        if not public_ips:
            raise PublicUrlUnresolvedError(f"{label}无法解析")
        resolved_ip = public_ips[0]
    return ResolvedPublicUrl(parsed=parsed, hostname=parsed.hostname, resolved_ip=resolved_ip, port=port)


def assert_public_http_url(url: str, *, label: str = "下载地址") -> None:
    resolve_public_http_url(url, label=label)
