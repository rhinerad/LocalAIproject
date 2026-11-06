"""HTTPS fetcher with SSRF controls. No archives, executables, or model weights."""
from __future__ import annotations

import ipaddress
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .discovery import FetchedAsset

ALLOWED_HOSTS = frozenset({
    "github.com",
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
    "api.github.com",
    "civitai.com",
    "www.civitai.com",
    "comfyworkflows.com",
    "www.comfyworkflows.com",
    "docs.comfy.org",
})
BLOCKED_SUFFIXES = (
    ".zip", ".7z", ".rar", ".exe", ".dll", ".msi", ".bat", ".ps1", ".cmd",
    ".gguf", ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".whl",
)
MAX_BYTES = 2_000_000
CONNECT_TIMEOUT = 8.0
READ_TIMEOUT = 15.0


class FetchError(ValueError):
    pass


def _host_allowed(host: str) -> bool:
    host = host.lower().rstrip(".")
    if host in ALLOWED_HOSTS:
        return True
    return False


def _is_public_ip(addr: str) -> bool:
    ip = ipaddress.ip_address(addr)
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        or ip.is_reserved
    )


def resolve_public(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addrs = sorted({item[4][0] for item in infos})
    if not addrs:
        raise FetchError("dns_empty")
    for addr in addrs:
        if not _is_public_ip(addr):
            raise FetchError(f"blocked_address:{addr}")
    return addrs


def _check_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise FetchError("https_only")
    if parsed.username or parsed.password:
        raise FetchError("credentials_in_url")
    host = parsed.hostname or ""
    if not _host_allowed(host):
        raise FetchError(f"host_not_allowed:{host}")
    path = (parsed.path or "").lower()
    if any(path.endswith(suf) for suf in BLOCKED_SUFFIXES):
        raise FetchError("blocked_file_type")
    resolve_public(host)
    return parsed


class SecureFetcher:
    async def fetch_json(self, url: str, max_bytes: int = MAX_BYTES) -> FetchedAsset:
        return fetch_json_sync(url, max_bytes=max_bytes)


def fetch_json_sync(url: str, max_bytes: int = MAX_BYTES) -> FetchedAsset:
    current = url
    for _ in range(4):
        parsed = _check_url(current)
        req = urllib.request.Request(
            current,
            headers={"User-Agent": "gvd-tool-router/1.0", "Accept": "application/json,text/plain"},
            method="GET",
        )
        context = ssl.create_default_context()

        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        try:
            opener = urllib.request.build_opener(
                urllib.request.HTTPSHandler(context=context),
                _NoRedirect(),
            )
            resp = opener.open(req, timeout=CONNECT_TIMEOUT)
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                loc = exc.headers.get("Location") or ""
                if not loc:
                    raise FetchError("redirect_missing") from exc
                current = urllib.parse.urljoin(current, loc)
                _check_url(current)
                continue
            if exc.code in {429, 500, 502, 503, 504}:
                raise FetchError(f"http_{exc.code}") from exc
            raise FetchError(f"http_{exc.code}") from exc
        except urllib.error.URLError as exc:
            raise FetchError(f"network:{type(exc.reason).__name__}") from exc
        final = resp.geturl() or current
        _check_url(final)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        body = resp.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise FetchError("oversized_workflow")
        if "json" not in ctype and not final.lower().endswith(".json"):
            # Still accept if body is JSON object/array.
            stripped = body.lstrip()
            if not stripped[:1] in (b"{", b"["):
                raise FetchError("not_json")
        return FetchedAsset(body=body, final_url=final, content_type=ctype)
    raise FetchError("too_many_redirects")
