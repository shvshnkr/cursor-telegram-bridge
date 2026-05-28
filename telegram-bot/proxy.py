"""SOCKS5 failover for Telegram Bot API HTTP calls only."""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
from typing import List, Optional
from urllib.parse import urlparse

_PROXY_URLS: List[str] = []
_ORIGINAL_SOCKET = socket.socket


def configure(proxy_urls: Optional[List[str]] = None) -> None:
    global _PROXY_URLS
    _PROXY_URLS = [u for u in (proxy_urls or []) if u]


def _parse_socks_url(proxy_url: str):
    parsed = urlparse(proxy_url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("socks5", "socks5h"):
        raise ValueError("Unsupported proxy scheme: %s" % scheme)
    host = parsed.hostname
    port = parsed.port or 1080
    if not host:
        raise ValueError("Invalid proxy URL: %s" % proxy_url)
    rdns = scheme == "socks5h"
    return host, port, rdns


def _open_direct(request: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(request, timeout=timeout)


def _open_via_socks(request: urllib.request.Request, proxy_url: str, timeout: float):
    import socks  # PySocks

    host, port, rdns = _parse_socks_url(proxy_url)
    socks.set_default_proxy(socks.SOCKS5, host, port, rdns=rdns)
    socket.socket = socks.socksocket
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    finally:
        socket.socket = _ORIGINAL_SOCKET
        socks.set_default_proxy()


def open_url(request: urllib.request.Request, timeout: float = 60):
    """Try each configured SOCKS proxy; fall back to direct if none configured."""
    errors = []
    for proxy_url in _PROXY_URLS:
        try:
            return _open_via_socks(request, proxy_url, timeout)
        except Exception as exc:
            errors.append("%s: %s" % (proxy_url, exc))
    if _PROXY_URLS:
        try:
            return _open_direct(request, timeout)
        except Exception as exc:
            errors.append("direct: %s" % exc)
            raise urllib.error.URLError(
                "All Telegram proxies failed: %s" % "; ".join(errors)
            ) from exc
    return _open_direct(request, timeout)
