#!/usr/bin/env python3
"""Pluggable web-search backends.

The research loop in deep_research.py talks only to SearchBackend.search().
Swapping DuckDuckGo for a keyed API is a new class, a registry entry, and
EQUAL_SHARES_SEARCH_BACKEND (+ EQUAL_SHARES_SEARCH_API_KEY). Do not rewrite
the gather/synthesize logic when adding Brave, Serper, Tavily, or xAI.

    EQUAL_SHARES_SEARCH_BACKEND   default "duckduckgo"
    EQUAL_SHARES_SEARCH_API_KEY   required by keyed stubs; unused by DDG
"""
from __future__ import annotations

import html.parser
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

USER_AGENT = "Mozilla/5.0 (compatible)"


class SearchError(RuntimeError):
    """Typed search failure. `code` is one of the stable strings web_search maps."""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


class SearchBackend(Protocol):
    name: str

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        """Return [{"title", "url", "snippet"}, ...]. Never a silent empty list."""
        ...


def _unwrap_ddg_href(href: str) -> str:
    href = (href or "").strip()
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    qs = urllib.parse.parse_qs(parsed.query)
    if qs.get("uddg"):
        return urllib.parse.unquote(qs["uddg"][0])
    return href


class _LiteResultParser(html.parser.HTMLParser):
    """Pull title/url/snippet rows out of DuckDuckGo's lite HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.snippets: list[str] = []
        self._in_link = False
        self._in_snippet = False
        self._href = ""
        self._title: list[str] = []
        self._snip: list[str] = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        cls = data.get("class", "")
        if tag == "a" and ("result-link" in cls.split() or data.get("rel") == "nofollow"):
            href = data.get("href") or ""
            if href:
                self._in_link = True
                self._href = href
                self._title = []
        if tag in {"td", "span"} and "result-snippet" in cls.split():
            self._in_snippet = True
            self._snip = []

    def handle_endtag(self, tag):
        if tag == "a" and self._in_link:
            title = "".join(self._title).strip()
            url = _unwrap_ddg_href(self._href)
            if title and url:
                self.links.append((title, url))
            self._in_link = False
        if tag in {"td", "span"} and self._in_snippet:
            snippet = " ".join("".join(self._snip).split())
            self.snippets.append(snippet)
            self._in_snippet = False

    def handle_data(self, data):
        if self._in_link:
            self._title.append(data)
        if self._in_snippet:
            self._snip.append(data)


class DuckDuckGoBackend:
    """Stdlib scrape of lite.duckduckgo.com. No API key."""

    name = "duckduckgo"

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        query = str(query or "").strip()
        if not query:
            raise SearchError("parse-failure", "empty query")
        max_results = max(1, min(int(max_results), 12))
        url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote_plus(query)

        def attempt() -> tuple[list[dict] | None, str | None]:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    status = resp.status
                    raw = resp.read(300_000).decode("utf-8", errors="replace")
            except urllib.error.URLError as exc:
                inner = getattr(exc, "reason", exc)
                if isinstance(inner, OSError):
                    return None, "no-internet"
                return None, f"network: {inner}"
            except Exception as exc:
                return None, f"error: {type(exc).__name__}: {exc}"
            if status == 429:
                return None, "rate-limited"
            if status != 200:
                return None, f"http-{status}"
            if len(raw) < 500 and "duckduckgo" not in raw.lower():
                return None, "rate-limited"
            lowered = raw.lower()
            if "no results." in lowered:
                return None, "zero-results"
            parser = _LiteResultParser()
            try:
                parser.feed(raw)
            except Exception:
                return None, "parse-failure"
            items: list[dict] = []
            seen: set[str] = set()
            for i, (title, href) in enumerate(parser.links):
                if not href.startswith(("http://", "https://")):
                    continue
                if "duckduckgo.com" in urllib.parse.urlparse(href).netloc:
                    continue
                key = href.split("#", 1)[0]
                if key in seen:
                    continue
                seen.add(key)
                snippet = parser.snippets[i] if i < len(parser.snippets) else ""
                items.append({"title": title, "url": href, "snippet": snippet})
                if len(items) >= max_results:
                    break
            if not items:
                return None, "parse-failure"
            return items, None

        items, err = attempt()
        if err in ("rate-limited",) or (err and str(err).startswith("network:")):
            time.sleep(2)
            items, err = attempt()
        if err:
            raise SearchError(err, err)
        return items or []


class KeyedSearchBackend:
    """Placeholder for a future HTTP search API. Not implemented on purpose."""

    def __init__(self, name: str):
        self.name = name

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        key = os.environ.get("EQUAL_SHARES_SEARCH_API_KEY", "").strip()
        if not key:
            raise SearchError(
                "needs-api-key",
                f"set EQUAL_SHARES_SEARCH_API_KEY and enable this backend "
                f"(EQUAL_SHARES_SEARCH_BACKEND={self.name})",
            )
        raise SearchError(
            "not-implemented",
            f"{self.name} is a stub: add a ~20-line SearchBackend class, a "
            "registry entry, and call the vendor HTTP API with the key.",
        )


# Adding a keyed API later: implement SearchBackend, register it here, set
# EQUAL_SHARES_SEARCH_BACKEND and EQUAL_SHARES_SEARCH_API_KEY. deep_research
# does not change.
BACKENDS: dict[str, type | tuple] = {
    "duckduckgo": DuckDuckGoBackend,
    "brave": ("stub", "brave"),
    "serper": ("stub", "serper"),
    "tavily": ("stub", "tavily"),
    "xai": ("stub", "xai"),
}


def get_backend(name: str | None = None) -> SearchBackend:
    chosen = (name or os.environ.get("EQUAL_SHARES_SEARCH_BACKEND") or "duckduckgo")
    chosen = str(chosen).strip().lower() or "duckduckgo"
    spec = BACKENDS.get(chosen)
    if spec is None:
        raise SearchError(
            "unknown-backend",
            f"unknown search backend {chosen!r}; "
            f"known: {sorted(BACKENDS)} "
            "(set EQUAL_SHARES_SEARCH_BACKEND)",
        )
    if spec is DuckDuckGoBackend:
        return DuckDuckGoBackend()
    if isinstance(spec, tuple) and spec[0] == "stub":
        return KeyedSearchBackend(spec[1])
    return spec()  # type: ignore[misc]


def format_results_text(query: str, items: list[dict], *,
                        backend: str = "duckduckgo", max_chars: int = 6000) -> str:
    lines = [f"[{backend}: {query}]", ""]
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. {item.get('title') or ''}")
        if item.get("url"):
            lines.append(f"   {item['url']}")
        if item.get("snippet"):
            lines.append(f"   {item['snippet']}")
        lines.append("")
    text = "\n".join(lines).strip()
    suffix = f"\n\n[truncated at {max_chars} chars]" if len(text) > max_chars else ""
    return text[:max_chars] + suffix


def web_search_error_text(query: str, err: SearchError, *, backend: str) -> str:
    code = err.code
    if code == "no-internet":
        return "SEARCH UNAVAILABLE: No internet connection (hotspot off or unreachable)."
    if code == "rate-limited":
        if backend == "duckduckgo":
            return ("SEARCH UNAVAILABLE: DuckDuckGo is rate-limiting this IP. "
                    "Try again in a few minutes.")
        return f"SEARCH UNAVAILABLE: {backend} is rate-limiting this IP."
    if code == "zero-results":
        return f"SEARCH: No results found for {query!r}."
    if code == "parse-failure":
        if backend == "duckduckgo":
            return ("SEARCH FAILED: Got a response but couldn't extract any results — "
                    "DuckDuckGo's page structure may have changed.")
        return f"SEARCH FAILED: {backend} returned a page that could not be parsed."
    if code == "needs-api-key":
        return f"SEARCH UNAVAILABLE: {err}"
    if code == "unknown-backend":
        return f"SEARCH FAILED: {err}"
    return f"SEARCH FAILED: {err}"
