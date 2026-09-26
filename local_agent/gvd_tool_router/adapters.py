"""Search, GitHub/Civitai resolvers, static validator, durable validation queue."""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import urlparse

from .binder import inspect_graph
from .discovery import CandidateAsset, DiscoveryHit
from .paths import GvdLayout
from .store import connect, mark_discovery, pending_discovery

JSON_HREF_RE = re.compile(r"""https?://[^\s"'<>]+\.json(?:\?[^\s"'<>]*)?""", re.I)
GITHUB_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)(?:/|$)", re.I)

CACHE_TTL_S = 24 * 3600
MAX_HITS_PER_RUN = 30


class SearchCache:
    def __init__(self, layout: GvdLayout):
        self.path = layout.state_dir / "search_cache.json"
        self.layout = layout

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def get(self, query: str) -> list[DiscoveryHit] | None:
        rows = self._load()
        hit = rows.get(query)
        if not hit:
            return None
        if time.time() - float(hit.get("ts") or 0) > CACHE_TTL_S:
            return None
        return [DiscoveryHit(h["page_url"], h["title"]) for h in hit.get("hits") or []]

    def put(self, query: str, hits: list[DiscoveryHit]) -> None:
        rows = self._load()
        rows[query] = {
            "ts": time.time(),
            "hits": [{"page_url": h.page_url, "title": h.title} for h in hits],
        }
        self.layout.state_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, indent=2), encoding="utf-8")


class LocalSearchAdapter:
    """Wraps local_agent.search_backend; SOURCE_UNAVAILABLE on failure."""

    def __init__(self, layout: GvdLayout):
        self.cache = SearchCache(layout)

    async def search(self, query: str, limit: int) -> list[DiscoveryHit]:
        cached = self.cache.get(query)
        if cached is not None:
            return cached[:limit]
        try:
            import search_backend
            backend = search_backend.get_backend() if hasattr(search_backend, "get_backend") else None
            if backend is None:
                from search_backend import DuckDuckGoBackend
                backend = DuckDuckGoBackend()
            raw = backend.search(query, max_results=min(limit, 10))
        except Exception as exc:
            raise RuntimeError(f"source_unavailable:{type(exc).__name__}") from exc
        hits = []
        for row in raw or []:
            url = str(row.get("url") or "")
            title = str(row.get("title") or url)
            if url.startswith("https://"):
                hits.append(DiscoveryHit(url, title))
        self.cache.put(query, hits)
        return hits[:limit]


class WorkflowSourceResolver:
    async def workflow_assets(self, hit: DiscoveryHit) -> list[CandidateAsset]:
        url = hit.page_url
        parsed = urlparse(url)
        assets: list[CandidateAsset] = []
        if parsed.path.lower().endswith(".json"):
            assets.append(CandidateAsset(
                page_url=url, download_url=url, publisher=parsed.netloc,
                immutable_revision=None, provenance={"kind": "direct_json"},
            ))
            return assets
        gh = GITHUB_RE.match(url)
        if gh:
            owner, repo = gh.group(1), gh.group(2)
            raw = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/workflow.json"
            assets.append(CandidateAsset(
                page_url=url, download_url=raw, publisher=f"github:{owner}/{repo}",
                immutable_revision=None, provenance={"kind": "github_guess_workflow_json"},
            ))
        return assets


class BinderStaticValidator:
    def inspect(self, graph: Any) -> tuple[str, list[str]]:
        return inspect_graph(graph)


class SqliteValidationQueue:
    def __init__(self, layout: GvdLayout):
        self.layout = layout

    async def enqueue(self, digest: str, capability: str) -> None:
        conn = connect(self.layout)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS validation_jobs (
                job_key TEXT PRIMARY KEY,
                digest TEXT NOT NULL,
                capability TEXT NOT NULL,
                state TEXT NOT NULL,
                created REAL NOT NULL,
                updated REAL NOT NULL
            )"""
        )
        key = f"{digest}:{capability}"
        now = time.time()
        conn.execute(
            """INSERT INTO validation_jobs(job_key, digest, capability, state, created, updated)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(job_key) DO UPDATE SET updated=excluded.updated""",
            (key, digest, capability, "validation_pending", now, now),
        )
        mark_discovery(conn, digest, "validation_pending", capability)
        conn.commit()
        conn.close()

    def reconcile(self) -> int:
        """Re-enqueue discovery rows that crashed between mark and queue."""
        conn = connect(self.layout)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS validation_jobs (
                job_key TEXT PRIMARY KEY,
                digest TEXT NOT NULL,
                capability TEXT NOT NULL,
                state TEXT NOT NULL,
                created REAL NOT NULL,
                updated REAL NOT NULL
            )"""
        )
        pending = pending_discovery(conn)
        restored = 0
        now = time.time()
        for row in pending:
            key = f"{row['digest']}:{row['capability'] or 'unknown'}"
            exists = conn.execute(
                "SELECT 1 FROM validation_jobs WHERE job_key=?", (key,)
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """INSERT INTO validation_jobs(job_key, digest, capability, state, created, updated)
                   VALUES (?,?,?,?,?,?)""",
                (key, row["digest"], row["capability"] or "", "validation_pending", now, now),
            )
            restored += 1
        conn.commit()
        conn.close()
        return restored
