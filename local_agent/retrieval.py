#!/usr/bin/env python3
"""Hybrid (lexical + dense) retrieval over the project documentation tree
(UPGRADE 05 Job 2; default path switched 2026-09-02ab).

`search` / `search_docs` default to `HybridScorer`: BM25 fused with CPU-only
`nomic-embed-text` via Reciprocal Rank Fusion. No rank_bm25, no sklearn, no
FlashRank/onnxruntime — the dense side reuses the Ollama endpoint already
proven by `exemplar_embeddings.py`. If that endpoint is down, `HybridScorer`
falls back to lexical-only ranking so the tool keeps working fully offline.

Stage 3 cross-encoder reranking (FlashRank / `ms-marco-MiniLM-L-6-v2`) is an
explicitly deferred new runtime dependency, not part of this default path.

Usage:
    import retrieval
    results = retrieval.search("duration ladder retries")
    # [{"source": ..., "heading": ..., "text": ..., "score": ...}, ...]

    retrieval.rebuild()   # force full re-index and return stats dict

    # Default is already HybridScorer; passing one explicitly is equivalent:
    results = retrieval.search("duration ladder retries", scorer=retrieval.HybridScorer())

    python local_agent/retrieval.py --rebuild
    python local_agent/retrieval.py duration ladder

    # Force lexical-only (used by tests / comparisons):
    results = retrieval.search("duration ladder retries", scorer=retrieval.LexicalScorer())
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
from pathlib import Path
from typing import Protocol, runtime_checkable

from atomic_io import atomic_write_text

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INDEX_FILE = HERE / "knowledge" / "retrieval_index.json"

CHUNK_CHARS = 3000   # ~800 tokens at ~3.75 chars/token
OVERLAP_CHARS = 375  # ~100-token overlap

SOURCE_GLOBS: list[str] = [
    "docs/**/*.md",
    "CLAUDE.md",
    "README.md",
    "CHANGELOG/*.md",
    "START_*.md",
    "FINISH_LOCAL_AGENT.md",
    "local_agent/UPGRADE/*.md",
    "outputs/equal_shares/runtime/agent_questions.md",
]

_SKIP_DIR_PARTS: frozenset[str] = frozenset({"archive", "_quarantine"})
_SKIP_NAME_RE = re.compile(r"_QUARANTINE_|\.BACKUP|SUPERSEDED", re.I)


# ── scorer interface ──────────────────────────────────────────────────────────

@runtime_checkable
class ScorerProtocol(Protocol):
    def score(self, query: str, chunks: list[dict]) -> list[tuple[float, dict]]: ...


class LexicalScorer:
    """BM25 implementation. ~35 lines, no external dependencies."""
    K1, B = 1.5, 0.75

    @staticmethod
    def _tok(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", text.lower())

    def score(self, query: str, chunks: list[dict]) -> list[tuple[float, dict]]:
        if not chunks:
            return []
        q_terms = self._tok(query)
        if not q_terms:
            return [(0.0, c) for c in chunks]

        tf: list[dict[str, int]] = []
        df: dict[str, int] = {}
        lengths: list[int] = []
        for ch in chunks:
            toks = self._tok(ch.get("text", ""))
            lengths.append(len(toks))
            freq: dict[str, int] = {}
            for t in toks:
                freq[t] = freq.get(t, 0) + 1
            tf.append(freq)
            for t in set(freq):
                df[t] = df.get(t, 0) + 1

        N = len(chunks)
        avgdl = sum(lengths) / max(N, 1)
        results: list[tuple[float, dict]] = []
        for i, ch in enumerate(chunks):
            dl = lengths[i]
            s = 0.0
            for t in q_terms:
                n = df.get(t, 0)
                if not n:
                    continue
                idf = math.log((N - n + 0.5) / (n + 0.5) + 1)
                f = tf[i].get(t, 0)
                s += idf * f * (self.K1 + 1) / (
                    f + self.K1 * (1 - self.B + self.B * dl / avgdl))
            results.append((s, ch))
        return sorted(results, key=lambda x: -x[0])


EMBED_MODEL = "nomic-embed-text:latest"
EMBEDDING_CACHE_FILE = HERE / "knowledge" / "retrieval_embeddings.json"
_EMBED_CACHE: dict | None = None
_EMBED_CACHE_LOCK = threading.Lock()
_EMBED_BATCH = 64
# Below this cosine similarity, a chunk is treated as unrelated rather than
# a weak match — matches HybridScorer's "empty result means the docs don't
# establish the claim" contract. Heuristic, not measured against this
# corpus; revisit once real query traffic exists (see RAG_EVALUATION.md).
MIN_EMBED_SIMILARITY = 0.35
RRF_K = 60  # standard Reciprocal Rank Fusion constant


def _chunk_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _load_embedding_cache() -> dict:
    global _EMBED_CACHE
    if _EMBED_CACHE is not None:
        return _EMBED_CACHE
    cache: dict = {}
    if EMBEDDING_CACHE_FILE.is_file():
        try:
            cache = json.loads(EMBEDDING_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    cache.setdefault("model", EMBED_MODEL)
    cache.setdefault("vectors", {})
    _EMBED_CACHE = cache
    return cache


def _save_embedding_cache(cache: dict) -> None:
    atomic_write_text(EMBEDDING_CACHE_FILE, json.dumps(cache))


class EmbeddingScorer:
    """Dense retrieval scorer backed by the local CPU-only `nomic-embed-text`
    Ollama endpoint — same model, host, and `keep_alive="0"` convention
    already proven by `exemplar_embeddings.py`. Never touches the RTX 5080.

    Embeddings are cached on disk (`knowledge/retrieval_embeddings.json`),
    keyed by each chunk's own id and validated by a hash of its text, so an
    edited file only re-embeds the chunks that actually changed.

    UPGRADE 05 Job 2, implemented 2026-09-02 (see RAG_EVALUATION.md Stage 1).
    Used by the default `HybridScorer` path as of 2026-09-02ab.
    """

    def __init__(self, model: str = EMBED_MODEL, host: str | None = None):
        self.model = model
        self.host = host

    def _embed(self, texts: list[str]) -> list[list[float]]:
        import ollama_client as oll
        import router
        host = self.host or router.CPU_HOST
        return oll.embed(texts, model=self.model, host=host)

    def vectors_for(self, chunks: list[dict]) -> dict[str, list[float]]:
        """Return {chunk_id: vector}, embedding + caching only what's missing
        or stale. Public so HybridScorer/tests can reuse it without a second
        embedding pass.

        Uses a 3-pass approach so the lock is never held during the potentially
        slow embedding network call (farm or local Ollama):
          Pass 1 — read cache under lock, identify stale chunks.
          Pass 2 — compute vectors for stale chunks outside the lock
                   (tries farm first, falls back to local _embed).
          Pass 3 — write new vectors back to cache under lock.
        """
        if not chunks:
            return {}
        result: dict[str, list[float]] = {}
        stale: list[dict] = []

        # Pass 1: read cache, identify what needs embedding.
        with _EMBED_CACHE_LOCK:
            cache = _load_embedding_cache()
            for ch in chunks:
                entry = cache["vectors"].get(ch["id"])
                h = _chunk_hash(ch.get("text", ""))
                if entry and entry.get("hash") == h and entry.get("vector"):
                    result[ch["id"]] = entry["vector"]
                else:
                    stale.append(ch)

        if not stale:
            return result

        # Pass 2: compute embeddings outside the lock (network calls may be slow).
        new_vectors: dict[str, list[float]] = {}
        # Farm embed is eligible when farm_status.json is healthy (dashboard
        # overall block). Warm mac_worker is ~0.58s so a short block on the
        # search_docs turn is acceptable; a down/stale farm skips Celery
        # entirely and _embed() runs locally — same None-fallback as before.
        try:
            import farm_offload
            if farm_offload.should_route(farm_offload.KIND_EMBED, blocking=True):
                cap = int(getattr(farm_offload, "FARM_EMBED_MAX_CHUNKS", 8))
                farm_slice = [
                    {"id": ch["id"], "text": ch.get("text", "")}
                    for ch in stale[:cap]
                ]
                fv = farm_offload.try_embed_on_farm(farm_slice)
                if fv:
                    new_vectors.update(fv)
        except ImportError:
            pass
        local_stale = [ch for ch in stale if ch["id"] not in new_vectors]
        for start in range(0, len(local_stale), _EMBED_BATCH):
            batch = local_stale[start:start + _EMBED_BATCH]
            embedded = self._embed([c.get("text", "") for c in batch])
            for ch, vector in zip(batch, embedded):
                new_vectors[ch["id"]] = vector

        # Pass 3: write new vectors to cache under lock.
        if new_vectors:
            ch_by_id = {c["id"]: c for c in stale}
            with _EMBED_CACHE_LOCK:
                cache = _load_embedding_cache()
                changed = False
                for cid, vector in new_vectors.items():
                    ch = ch_by_id.get(cid)
                    if ch is None:
                        continue
                    h = _chunk_hash(ch.get("text", ""))
                    cache["vectors"][cid] = {"hash": h, "vector": vector}
                    result[cid] = vector
                    changed = True
                if changed:
                    cache["model"] = self.model
                    _save_embedding_cache(cache)
        return result

    def score(self, query: str, chunks: list[dict]) -> list[tuple[float, dict]]:
        if not chunks:
            return []
        vectors = self.vectors_for(chunks)
        query_vector = self._embed([query])[0]
        results = [
            (_cosine(query_vector, vectors.get(ch["id"], [])), ch)
            for ch in chunks
        ]
        return sorted(results, key=lambda x: -x[0])


class HybridScorer:
    """Fuses `LexicalScorer` (BM25) and `EmbeddingScorer` (dense) rankings
    with Reciprocal Rank Fusion — RRF operates on rank, not raw score, which
    matters because BM25 and cosine similarity are not on comparable scales
    (RAG_EVALUATION.md Stage 2).

    Only chunks that clear a relevance bar from *either* side make it into
    the result at all — a lexical hit (BM25 score > 0) or an embedding hit
    at or above `MIN_EMBED_SIMILARITY`. This preserves the existing
    contract that an empty result means "the local docs don't establish
    this," rather than always returning the corpus's nearest chunks
    regardless of how unrelated they are — RRF scores are otherwise always
    positive for anything in the fused pool, so without this filter nothing
    would ever come back empty.

    Falls back to lexical-only ranking if the embedding endpoint is
    unavailable (Ollama not running, model not pulled, etc.) rather than
    breaking `search_docs` — this tool must keep working fully offline.
    """

    def __init__(self, lexical: ScorerProtocol | None = None,
                 embedding: "EmbeddingScorer | None" = None):
        self.lexical = lexical or LexicalScorer()
        self.embedding = embedding or EmbeddingScorer()

    def score(self, query: str, chunks: list[dict]) -> list[tuple[float, dict]]:
        if not chunks:
            return []
        lexical_ranked = self.lexical.score(query, chunks)
        lexical_pool_ids = {ch["id"] for score, ch in lexical_ranked if score > 0}

        try:
            embedding_ranked = self.embedding.score(query, chunks)
        except Exception:
            # No local embedding endpoint reachable — degrade to lexical-only
            # fusion rather than failing search_docs outright.
            embedding_ranked = []
        embed_pool_ids = {
            ch["id"] for score, ch in embedding_ranked if score >= MIN_EMBED_SIMILARITY
        }

        pool_ids = lexical_pool_ids | embed_pool_ids
        if not pool_ids:
            return []

        by_id = {ch["id"]: ch for ch in chunks}
        rrf: dict[str, float] = {cid: 0.0 for cid in pool_ids}
        for rank, (_, ch) in enumerate(lexical_ranked):
            if ch["id"] in rrf:
                rrf[ch["id"]] += 1.0 / (RRF_K + rank + 1)
        for rank, (_, ch) in enumerate(embedding_ranked):
            if ch["id"] in rrf:
                rrf[ch["id"]] += 1.0 / (RRF_K + rank + 1)

        results: list[tuple[float, dict]] = []
        for cid, score in rrf.items():
            chunk = dict(by_id[cid])  # shallow copy; do not mutate the index
            lex = cid in lexical_pool_ids
            emb = cid in embed_pool_ids
            if lex and emb:
                chunk["_match_by"] = "both"
            elif emb:
                chunk["_match_by"] = "embedding"
            else:
                chunk["_match_by"] = "lexical"
            results.append((score, chunk))
        return sorted(results, key=lambda x: -x[0])


_DEFAULT_SCORER: ScorerProtocol = HybridScorer()
_INDEX_CACHE: dict | None = None
# search_docs is in tools.CONCURRENCY_SAFE_TOOLS, so agent.py's hop loop may
# call it from several threads at once, and it can race with a sequential
# run_build "rebuild" call happening on the main thread in the same hop.
# Without this lock, two threads finding a cold _INDEX_CACHE would both
# write knowledge/retrieval_index.json.tmp independently before either
# os.replace()'s it, which can corrupt the on-disk index. See CHANGELOG.
_INDEX_LOCK = threading.Lock()
_QUERY_STOP: frozenset[str] = frozenset({
    "the", "and", "for", "with", "from", "that", "this", "what", "when", "where",
    "which", "about", "does", "did", "are", "was", "were", "should", "would",
    "project", "documentation", "docs", "current",
})


# ── file filtering ────────────────────────────────────────────────────────────

def _should_skip(path: Path) -> bool:
    parts_lower = {p.lower() for p in path.parts}
    if parts_lower & _SKIP_DIR_PARTS:
        return True
    return bool(_SKIP_NAME_RE.search(path.name))


def _is_superseded(text: str) -> bool:
    """True if the file opens with a SUPERSEDED banner in the first five lines."""
    for line in text.strip().split("\n")[:5]:
        clean = re.sub(r"[#*_`>]", "", line).strip().upper()
        if clean.startswith("SUPERSEDED"):
            return True
    return False


# ── chunking ──────────────────────────────────────────────────────────────────

def _file_key(path: Path) -> str:
    try:
        st = path.stat()
        return f"{int(st.st_mtime)}:{st.st_size}"
    except Exception:
        return "0:0"


def _heading_before(headings: list[tuple[int, str]], pos: int) -> str:
    """Last heading whose start position is at or before `pos`."""
    result = ""
    for hp, ht in headings:
        if hp <= pos:
            result = ht
        else:
            break
    return result


def _chunk(source_rel: str, text: str) -> list[dict]:
    """Split text into overlapping chunks, breaking at headings where possible."""
    heading_re = re.compile(r"^#{1,6} .+", re.M)
    headings: list[tuple[int, str]] = [
        (m.start(), m.group(0).strip()) for m in heading_re.finditer(text)]
    head_starts = [hp for hp, _ in headings]

    chunks: list[dict] = []
    start = 0
    chunk_id = 0

    while start < len(text):
        end = min(start + CHUNK_CHARS, len(text))

        if end < len(text):
            # Prefer the last heading start in the window so the next chunk
            # begins at a clean section boundary.
            break_at = end
            for hp in head_starts:
                if start + OVERLAP_CHARS < hp <= end:
                    break_at = hp        # keep updating — want the rightmost
            if break_at == end:
                nl = text.rfind("\n", start + OVERLAP_CHARS, end)
                if nl > start:
                    break_at = nl
            end = break_at

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({
                "id": f"{source_rel}:{chunk_id}",
                "source": source_rel,
                "heading": _heading_before(headings, start),
                "text": chunk_text,
            })
            chunk_id += 1

        if end >= len(text):
            break
        start = max(start + 1, end - OVERLAP_CHARS)

    return chunks


def _build_file_chunks(path: Path) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    if _is_superseded(text):
        return []
    rel = str(path.relative_to(ROOT)).replace("\\", "/")
    return _chunk(rel, text)


def _collect_files() -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for glob in SOURCE_GLOBS:
        for p in sorted(ROOT.glob(glob)):
            key = str(p.resolve())
            if key in seen or not p.is_file() or _should_skip(p):
                continue
            seen.add(key)
            result.append(p)
    return result


# ── index management ──────────────────────────────────────────────────────────

def load_index(force_rebuild: bool = False) -> dict:
    """Load the chunk index from disk, rebuilding only files whose mtime+size changed."""
    global _INDEX_CACHE
    stored: dict = {"files": {}}
    if not force_rebuild and INDEX_FILE.is_file():
        try:
            stored = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            stored = {"files": {}}

    files = _collect_files()
    new_files: dict = {}
    changed = False

    for path in files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        key = _file_key(path)
        old = stored.get("files", {}).get(rel)
        if old and old.get("key") == key:
            new_files[rel] = old
        else:
            new_files[rel] = {"key": key, "chunks": _build_file_chunks(path)}
            changed = True

    if set(new_files) != set(stored.get("files", {})):
        changed = True

    if changed or "chunks" not in stored:
        all_chunks = [c for fd in new_files.values() for c in fd["chunks"]]
        data: dict = {
            "files": new_files,
            "chunks": all_chunks,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        atomic_write_text(INDEX_FILE, json.dumps(data))
        _INDEX_CACHE = data
        return data

    stored["chunks"] = stored.get("chunks") or [
        c for fd in stored["files"].values() for c in fd["chunks"]]
    _INDEX_CACHE = stored
    return stored


def _get_index() -> dict:
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    with _INDEX_LOCK:
        # Re-check: another thread may have finished building it while this
        # one was waiting for the lock (double-checked locking).
        if _INDEX_CACHE is None:
            _INDEX_CACHE = load_index()
        return _INDEX_CACHE


# ── public API ────────────────────────────────────────────────────────────────

def search(query: str, max_results: int = 5,
           scorer: ScorerProtocol | None = None) -> list[dict]:
    """Return the top-scoring chunks matching `query`.

    Each result: {"source": rel_path, "heading": str, "text": str, "score": float}
    """
    idx = _get_index()
    chunks = idx.get("chunks", [])
    sc = scorer or _DEFAULT_SCORER
    ranked = sc.score(query, chunks)
    results = []
    for score, chunk in ranked[:max_results]:
        if score <= 0:
            break
        row = {
            "source": chunk["source"],
            "heading": chunk.get("heading", ""),
            "text": chunk["text"][:1500],
            "score": round(score, 3),
        }
        match_by = chunk.get("_match_by")
        if match_by:
            row["match_by"] = match_by
        results.append(row)
    return results


def search_relevant(query: str, max_results: int = 5) -> list[dict]:
    """Return hits that are lexically grounded or hybrid semantic matches.

    Lexical near-misses (a BM25 hit that shares no meaningful query terms)
    are still dropped. Embedding-only hits from `HybridScorer` are kept —
    they already cleared `MIN_EMBED_SIMILARITY` — so the default hybrid
    path cannot have its semantic matches stripped by this grader. An empty
    result still means the agent must say the local documents did not
    establish the claim.
    """
    terms = {term for term in LexicalScorer._tok(query) if term not in _QUERY_STOP}
    candidates = search(query, max_results=max(max_results * 3, 8))
    relevant: list[dict] = []
    for item in candidates:
        chunk_terms = set(LexicalScorer._tok(
            f"{item.get('heading', '')}\n{item.get('text', '')}"))
        overlap_terms = terms & chunk_terms
        match_by = item.get("match_by", "")
        semantic_ok = match_by in ("embedding", "both")
        if overlap_terms or semantic_ok:
            copied = dict(item)
            copied["matched_terms"] = sorted(overlap_terms)[:8]
            if semantic_ok and not overlap_terms:
                copied["semantic_match"] = True
            relevant.append(copied)
        if len(relevant) >= max_results:
            break
    return relevant


def rebuild() -> dict:
    """Force a full index rebuild. Returns {"files", "chunks", "index_size_kb"}."""
    global _INDEX_CACHE
    with _INDEX_LOCK:
        _INDEX_CACHE = None
        idx = load_index(force_rebuild=True)
    size_kb = INDEX_FILE.stat().st_size / 1024 if INDEX_FILE.is_file() else 0.0
    return {
        "files": len(idx.get("files", {})),
        "chunks": len(idx.get("chunks", [])),
        "index_size_kb": round(size_kb, 1),
    }


if __name__ == "__main__":
    import sys

    def _safe(s: str) -> str:
        return s.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8", errors="replace")

    if "--rebuild" in sys.argv or len(sys.argv) == 1:
        stats = rebuild()
        print(f"index: {stats['files']} files  {stats['chunks']} chunks  "
              f"{stats['index_size_kb']} KB  -> {INDEX_FILE}")
    else:
        q = " ".join(sys.argv[1:])
        hits = search(q)
        if not hits:
            print("no results")
        else:
            for r in hits:
                print(f"\n[{r['score']:.3f}] {r['source']} -- {_safe(r['heading'])}")
                print(_safe(r["text"][:500]))
