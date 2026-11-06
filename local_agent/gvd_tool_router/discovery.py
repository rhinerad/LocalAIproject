"""Discovery orchestration from the spec. Adapters are injected; no installer."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

ALLOWED_CAPABILITIES = {
    "narrative_identity", "video_continuation", "montage_morph",
    "fast_action", "still_generation", "tts", "lipsync", "video_inpainting",
    "motion_reference",
}


@dataclass(frozen=True)
class DiscoveryHit:
    page_url: str
    title: str


@dataclass(frozen=True)
class CandidateAsset:
    page_url: str
    download_url: str
    publisher: str
    immutable_revision: str | None
    provenance: dict[str, Any]


@dataclass(frozen=True)
class FetchedAsset:
    body: bytes
    final_url: str
    content_type: str


class SearchAdapter(Protocol):
    async def search(self, query: str, limit: int) -> list[DiscoveryHit]: ...


class SourceResolver(Protocol):
    async def workflow_assets(self, hit: DiscoveryHit) -> list[CandidateAsset]: ...


class SecureFetcher(Protocol):
    async def fetch_json(self, url: str, max_bytes: int) -> FetchedAsset: ...


class QuarantineStore(Protocol):
    async def contains(self, digest: str) -> bool: ...
    async def put_atomic(self, digest: str, body: bytes,
                         metadata: dict[str, Any]) -> None: ...
    async def mark(self, digest: str, state: str, reasons: list[str]) -> None: ...


class StaticValidator(Protocol):
    def inspect(self, graph: Any) -> tuple[str, list[str]]: ...


class ValidationQueue(Protocol):
    async def enqueue(self, digest: str, capability: str) -> None: ...


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_nonfinite(value):
    raise ValueError("non-finite JSON number")


async def discover_workflows(
    capability: str, search: SearchAdapter, resolver: SourceResolver,
    fetcher: SecureFetcher, store: QuarantineStore,
    validator: StaticValidator, queue: ValidationQueue,
    max_candidates: int = 10,
) -> list[dict[str, Any]]:
    if capability not in ALLOWED_CAPABILITIES:
        raise ValueError("unsupported discovery capability")
    if not 1 <= max_candidates <= 10:
        raise ValueError("candidate budget must be 1..10")
    phrase = capability.replace("_", " ")
    domains = ("github.com", "civitai.com", "comfyworkflows.com")
    results: list[dict[str, Any]] = []
    seen_pages: set[str] = set()
    attempted = 0
    for domain in domains:
        query = f"site:{domain} ComfyUI {phrase} RTX 5080 16GB workflow"
        try:
            hits = await search.search(query, limit=10)
        except Exception as exc:
            results.append({"state": "source_unavailable",
                            "source": domain, "error_type": type(exc).__name__})
            continue
        for hit in hits[:10]:
            if hit.page_url in seen_pages:
                continue
            seen_pages.add(hit.page_url)
            try:
                assets = await resolver.workflow_assets(hit)
            except Exception as exc:
                results.append({"state": "resolution_failed",
                                "page": hit.page_url,
                                "error_type": type(exc).__name__})
                continue
            for asset in assets[:3]:
                if attempted >= max_candidates:
                    return results
                attempted += 1
                digest = None
                try:
                    fetched = await fetcher.fetch_json(
                        asset.download_url, max_bytes=2_000_000)
                    if len(fetched.body) > 2_000_000:
                        raise ValueError("oversized workflow")
                    digest = hashlib.sha256(fetched.body).hexdigest()
                    if await store.contains(digest):
                        results.append({"digest": digest, "state": "duplicate"})
                        continue
                    await store.put_atomic(digest, fetched.body, {
                        "query": query, "page_url": asset.page_url,
                        "final_url": fetched.final_url,
                        "publisher": asset.publisher,
                        "revision": asset.immutable_revision,
                        "provenance": asset.provenance,
                    })
                    graph = json.loads(
                        fetched.body.decode("utf-8"),
                        object_pairs_hook=reject_duplicate_keys,
                        parse_constant=reject_nonfinite,
                    )
                    verdict, reasons = validator.inspect(graph)
                    if verdict not in {"reject", "ui_export_required", "api_candidate"}:
                        raise ValueError("invalid static verdict")
                    state = {
                        "reject": "rejected",
                        "ui_export_required": "quarantined",
                        "api_candidate": "validation_pending",
                    }[verdict]
                    await store.mark(digest, state, reasons)
                    if state == "validation_pending":
                        await queue.enqueue(digest, capability)
                    results.append({"digest": digest, "state": state,
                                    "reasons": reasons})
                except Exception as exc:
                    if digest is not None:
                        await store.mark(digest, "quarantined",
                                         [type(exc).__name__])
                    results.append({"digest": digest, "state": "quarantined",
                                    "error_type": type(exc).__name__})
    return results
