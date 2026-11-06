#!/usr/bin/env python3
"""CPU-only Chroma storage for *approved* local exemplars.

No staged item reaches this module.  The sole model is local Ollama
``nomic-embed-text`` on the CPU endpoint, with ``num_gpu: 0`` and four threads.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from atomic_io import atomic_write_text

try:
    import chromadb
    from chromadb.config import Settings
    _CHROMADB_AVAILABLE = True
    _CHROMADB_REASON = ""
except ImportError:
    chromadb = None  # type: ignore[assignment]
    Settings = None  # type: ignore[assignment]
    _CHROMADB_AVAILABLE = False
    _CHROMADB_REASON = (
        "chromadb is not installed (pip install chromadb). "
        "Exemplar retrieval and semantic deduplication are unavailable."
    )

import ollama_client as oll
import router

HERE = Path(__file__).resolve().parent
DB_DIR = HERE / "exemplar_store" / "chroma"
MODEL = "nomic-embed-text:latest"
_COLLECTIONS = {
    "video_prompt": "exemplars_video_prompts",
    "comfyui_workflow": "exemplars_comfyui",
    "screenplay_beat": "exemplars_screenplay_beats",
}
_WORKER: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()
_STOP = threading.Event()
_CLIENT = None
_CLIENT_PATH: Path | None = None
_CLIENT_LOCK = threading.Lock()


def _collection_name(category: str) -> str:
    try:
        return _COLLECTIONS[category]
    except KeyError as exc:
        raise ValueError(f"unsupported exemplar category {category!r}") from exc


def _client():
    if not _CHROMADB_AVAILABLE:
        raise RuntimeError(_CHROMADB_REASON)
    global _CLIENT, _CLIENT_PATH
    path = DB_DIR.resolve()
    with _CLIENT_LOCK:
        if _CLIENT is not None and _CLIENT_PATH == path:
            return _CLIENT
        # DB_DIR is static in production. Closing an old client here keeps tests
        # and an explicit store-path reconfiguration from retaining a Windows
        # file handle indefinitely.
        if _CLIENT is not None:
            close = getattr(_CLIENT, "close", None)
            if callable(close):
                close()
        path.mkdir(parents=True, exist_ok=True)
        # Explicitly suppress anonymous telemetry; this store never sends
        # content or usage data out of the workstation.
        _CLIENT = chromadb.PersistentClient(
            path=str(path), settings=Settings(anonymized_telemetry=False)
        )
        _CLIENT_PATH = path
        return _CLIENT


def _reset_client_for_tests() -> None:
    """Release the cached handle for isolated tests that use a temporary DB."""
    global _CLIENT, _CLIENT_PATH
    with _CLIENT_LOCK:
        if _CLIENT is not None:
            close = getattr(_CLIENT, "close", None)
            if callable(close):
                close()
        _CLIENT = None
        _CLIENT_PATH = None


def _collection(category: str):
    return _client().get_or_create_collection(
        _collection_name(category), metadata={"hnsw:space": "cosine"})


def _metadata(record: dict) -> dict:
    return {
        "source_dataset": str(record.get("source_dataset", "")),
        "license": str(record.get("license", "")),
        "category": str(record.get("category", "")),
        "style_domain": str(record.get("style_domain", "")),
        "title": str(record.get("title", ""))[:500],
        "status": "approved",
        "content_fingerprint": str(record.get("content_fingerprint", "")),
    }


def semantic_duplicate(category: str, content: str, threshold: float = 0.90) -> dict:
    """Compare a candidate to approved examples without storing the candidate."""
    if not _CHROMADB_AVAILABLE:
        return {"available": False, "duplicate": False, "reason": _CHROMADB_REASON,
                "install": "pip install chromadb"}
    col = _collection(category)
    if col.count() == 0:
        return {"available": True, "duplicate": False, "reason": "no approved exemplars"}
    vector = oll.embed(content, model=MODEL, host=router.CPU_HOST)[0]
    result = col.query(query_embeddings=[vector], n_results=1, include=["distances", "metadatas"])
    distances = (result.get("distances") or [[]])[0]
    ids = (result.get("ids") or [[]])[0]
    if not distances or not ids:
        return {"available": True, "duplicate": False, "reason": "no matching exemplar"}
    similarity = 1.0 - float(distances[0])
    return {"available": True, "duplicate": similarity > threshold,
            "similarity": round(similarity, 4), "threshold": threshold,
            "id": ids[0]}


def retrieve(query: str, categories: list[str], max_results: int = 2) -> list[dict]:
    """Return only provenance-labelled, approved, embedded examples.

    The returned body is deliberately bounded by the caller before it reaches a
    chat prompt. Pending/rejected files are not present in Chroma at all.
    """
    if not _CHROMADB_AVAILABLE:
        raise RuntimeError(_CHROMADB_REASON)
    wanted = [category for category in categories if category in _COLLECTIONS]
    if not wanted or max_results < 1:
        return []
    collections = [(category, _collection(category)) for category in wanted]
    collections = [(category, col) for category, col in collections if col.count()]
    if not collections:
        return []
    vector = oll.embed(query, model=MODEL, host=router.CPU_HOST)[0]
    found: list[dict] = []
    for category, col in collections:
        result = col.query(query_embeddings=[vector], n_results=min(max_results, col.count()),
                           include=["documents", "metadatas", "distances"])
        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for identifier, doc, meta, distance in zip(ids, docs, metas, distances):
            if str((meta or {}).get("status", "")) != "approved":
                continue
            found.append({"id": identifier, "category": category, "content": str(doc),
                          "metadata": meta or {}, "similarity": round(1.0 - float(distance), 4)})
    return sorted(found, key=lambda item: -item["similarity"])[:max_results]


def embed_record(record: dict) -> dict:
    """Embed one already-approved record, or defer while a CPU chat is active."""
    if not _CHROMADB_AVAILABLE:
        return {"status": "unavailable", "reason": _CHROMADB_REASON,
                "install": "pip install chromadb"}
    if record.get("status") != "approved":
        raise ValueError("only an approved exemplar can be embedded")
    if router.chat_busy():
        return {"status": "deferred", "reason": "a local chat is still streaming"}
    content = str(record.get("content", "")).strip()
    if not content:
        return {"status": "failed", "reason": "approved exemplar has no content"}
    vector = oll.embed(content, model=MODEL, host=router.CPU_HOST)[0]
    col = _collection(str(record.get("category", "")))
    col.upsert(ids=[str(record["id"])], documents=[content], embeddings=[vector],
               metadatas=[_metadata(record)])
    return {"status": "embedded", "model": MODEL, "collection": col.name,
            "dimensions": len(vector)}


def _atomic(path: Path, record: dict) -> None:
    atomic_write_text(path, json.dumps(record, ensure_ascii=False, indent=2))


def sync_approved(limit: int = 8) -> dict:
    """Finish deferred approved embeddings, bounded and CPU-chat-safe."""
    if not _CHROMADB_AVAILABLE:
        return {"embedded": 0, "deferred": False, "unavailable": True,
                "reason": _CHROMADB_REASON, "install": "pip install chromadb"}
    import exemplar_curator
    if router.chat_busy():
        return {"embedded": 0, "deferred": True}
    embedded, failures = 0, []
    paths = sorted(exemplar_curator.APPROVED.glob("*.json")) if exemplar_curator.APPROVED.is_dir() else []
    for path in paths[:max(0, limit)]:
        try:
            record = json.loads(path.read_text(encoding="utf8"))
            current = record.get("embedding") or {}
            if current.get("status") == "embedded" and current.get("model") == MODEL:
                continue
            result = embed_record(record)
            record["embedding"] = result
            _atomic(path, record)
            embedded += result.get("status") == "embedded"
        except Exception as exc:
            failures.append(f"{path.name}: {type(exc).__name__}: {exc}")
    return {"embedded": embedded, "deferred": False, "failures": failures}


def _worker() -> None:
    while not _STOP.wait(20.0):
        try:
            sync_approved()
        except Exception:
            # Each record remains approved and carries its own retry state. No
            # exception can turn a failed embedding into an active retrieval item.
            pass


def start_worker() -> None:
    if not _CHROMADB_AVAILABLE:
        return
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER and _WORKER.is_alive():
            return
        _STOP.clear()
        _WORKER = threading.Thread(target=_worker, name="exemplar-cpu-embed", daemon=True)
        _WORKER.start()
