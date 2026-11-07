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
import operator
import re
import threading
import time
from array import array
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


# ── precomputed lexical statistics ───────────────────────────────────────────
#
# BM25 needs per-chunk term frequencies and corpus document frequencies.  They
# used to be recomputed (re-tokenising all ~2,000 chunks) on every query.  They
# are now computed once per chunk list — load_index() warms them — and reused
# while the same list object is being searched.  The cache holds a reference to
# the list, so identity cannot be recycled while it is cached; a length check
# guards against in-place appends.

_LEX_LOCK = threading.Lock()
_LEX_CACHE: dict = {}


def _lexical_stats(chunks: list[dict]) -> tuple[list[dict[str, int]], dict[str, int], list[int]]:
    with _LEX_LOCK:
        cached = _LEX_CACHE.get("stats")
        if (cached is not None and _LEX_CACHE.get("ref") is chunks
                and _LEX_CACHE.get("len") == len(chunks)):
            return cached
    tf: list[dict[str, int]] = []
    df: dict[str, int] = {}
    lengths: list[int] = []
    for ch in chunks:
        toks = re.findall(r"[a-z0-9]+", str(ch.get("text", "")).lower())
        lengths.append(len(toks))
        freq: dict[str, int] = {}
        for t in toks:
            freq[t] = freq.get(t, 0) + 1
        tf.append(freq)
        for t in freq:
            df[t] = df.get(t, 0) + 1
    stats = (tf, df, lengths)
    with _LEX_LOCK:
        _LEX_CACHE.clear()
        _LEX_CACHE.update({"ref": chunks, "len": len(chunks), "stats": stats})
    return stats


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

        tf, df, lengths = _lexical_stats(chunks)
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
# 2: vectors keyed by chunk-text sha1 (was chunk id + hash field).
CACHE_VERSION = 2
# Below this cosine similarity, a chunk is treated as unrelated rather than
# a weak match — matches HybridScorer's "empty result means the docs don't
# establish the claim" contract. Heuristic, not measured against this
# corpus; revisit once real query traffic exists (see RAG_EVALUATION.md).
MIN_EMBED_SIMILARITY = 0.35
RRF_K = 60  # standard Reciprocal Rank Fusion constant


def _chunk_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()


def _hash_of(chunk: dict) -> str:
    """Content hash of a chunk; precomputed by load_index(), computed otherwise."""
    h = chunk.get("hash")
    if isinstance(h, str) and h:
        return h
    return _chunk_hash(chunk.get("text", ""))


def _cosine(a, b) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(map(operator.mul, a, b))
    na = math.sqrt(sum(map(operator.mul, a, a)))
    nb = math.sqrt(sum(map(operator.mul, b, b)))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# In-memory scoring form of cached vectors: content hash -> (array('f'), norm).
# 2,042 x 768 Python floats as lists cost ~50 MB and a norm recomputation per
# query; float32 arrays with the norm precomputed cost ~6 MB and one dot each.
_FAST_VECTORS: dict[str, tuple[array, float]] = {}
_FAST_LOCK = threading.Lock()


def _fast(vector) -> tuple[array, float]:
    arr = vector if isinstance(vector, array) else array("f", (float(x) for x in vector))
    return arr, math.sqrt(sum(map(operator.mul, arr, arr)))


def _fast_for(h: str, vector) -> tuple[array, float]:
    with _FAST_LOCK:
        hit = _FAST_VECTORS.get(h)
    if hit is not None and len(hit[0]) == len(vector):
        return hit
    hit = _fast(vector)
    with _FAST_LOCK:
        _FAST_VECTORS[h] = hit
    return hit


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
    if not isinstance(cache, dict):
        cache = {}
    cache.setdefault("model", EMBED_MODEL)
    if not isinstance(cache.get("vectors"), dict):
        cache["vectors"] = {}
    _migrate_cache(cache)
    _EMBED_CACHE = cache
    return cache


def _migrate_cache(cache: dict) -> None:
    """Re-key legacy ``{chunk_id: {"hash", "vector"}}`` entries by content hash.

    Content-hash keys mean a renamed/moved file or a chunk whose id shifted
    does not force a re-embed, and identical text is embedded once.
    """
    vectors = cache["vectors"]
    legacy = [k for k, v in vectors.items() if isinstance(v, dict)]
    for key in legacy:
        entry = vectors.pop(key)
        h, vec = entry.get("hash"), entry.get("vector")
        if isinstance(h, str) and isinstance(vec, list) and vec:
            vectors.setdefault(h, vec)
    cache["version"] = CACHE_VERSION


def cached_vector(cache: dict, chunk: dict) -> list[float] | None:
    """The cached vector for ``chunk``'s current text, or None if stale/missing.

    Accepts both the content-hash layout and the legacy id-keyed layout (a
    caller may hand in a cache dict that was never migrated)."""
    vectors = cache.get("vectors") or {}
    h = _hash_of(chunk)
    vec = vectors.get(h)
    if isinstance(vec, list) and vec:
        return vec
    entry = vectors.get(chunk.get("id"))
    if isinstance(entry, dict) and entry.get("hash") == h and entry.get("vector"):
        return entry["vector"]
    return None


def store_vector(cache: dict, chunk: dict, vector) -> None:
    cache.setdefault("vectors", {})[_hash_of(chunk)] = [float(x) for x in vector]


def _save_embedding_cache(cache: dict) -> None:
    cache["version"] = CACHE_VERSION
    atomic_write_text(EMBEDDING_CACHE_FILE, json.dumps(cache))


def prune_embedding_cache(live_hashes: set[str]) -> int:
    """Drop cached vectors whose text no longer exists in the index.

    Returns the number of entries removed (the file is rewritten only if >0).
    """
    with _EMBED_CACHE_LOCK:
        cache = _load_embedding_cache()
        vectors = cache["vectors"]
        orphans = [h for h in vectors if h not in live_hashes]
        for h in orphans:
            del vectors[h]
        if orphans:
            _save_embedding_cache(cache)
    with _FAST_LOCK:
        for h in [h for h in _FAST_VECTORS if h not in live_hashes]:
            del _FAST_VECTORS[h]
    return len(orphans)


class EmbeddingScorer:
    """Dense retrieval scorer backed by the local CPU-only `nomic-embed-text`
    Ollama endpoint (see `ollama_client.EMBED_KEEP_ALIVE`). Never touches the
    RTX 5080.

    Embeddings are cached on disk (`knowledge/retrieval_embeddings.json`,
    gitignored), keyed by a hash of each chunk's text, so an edited file only
    re-embeds the chunks that actually changed and a moved file re-embeds
    nothing.  New vectors are persisted after every batch, so an interrupted
    first build keeps what it finished.

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

    def _persist(self, new_vectors: dict[str, list[float]], ch_by_id: dict,
                 result: dict[str, list[float]]) -> None:
        """Write one batch of vectors to the cache file under the lock."""
        changed = False
        with _EMBED_CACHE_LOCK:
            cache = _load_embedding_cache()
            for cid, vector in new_vectors.items():
                ch = ch_by_id.get(cid)
                if ch is None or not vector:
                    continue
                store_vector(cache, ch, vector)
                result[cid] = vector
                changed = True
            if changed:
                cache["model"] = self.model
                _save_embedding_cache(cache)

    def vectors_for(self, chunks: list[dict]) -> dict[str, list[float]]:
        """Return {chunk_id: vector}, embedding + caching only what's missing
        or stale. Public so HybridScorer/tests can reuse it without a second
        embedding pass.

        The lock is never held during the potentially slow embedding call:
          Pass 1 - read cache under lock, identify stale chunks.
          Pass 2 - compute vectors for stale chunks outside the lock
                   (farm first, then local _embed), persisting each batch
                   under the lock as soon as it arrives.
        """
        if not chunks:
            return {}
        result: dict[str, list[float]] = {}
        stale: list[dict] = []

        # Pass 1: read cache, identify what needs embedding.
        with _EMBED_CACHE_LOCK:
            cache = _load_embedding_cache()
            for ch in chunks:
                vec = cached_vector(cache, ch)
                if vec:
                    result[ch["id"]] = vec
                else:
                    stale.append(ch)

        if not stale:
            return result
        ch_by_id = {c["id"]: c for c in stale}

        # Pass 2: farm slice first (validated by farm_offload), then local.
        # Farm embed is eligible when farm_status.json is healthy (dashboard
        # overall block). Warm mac_worker is ~0.58s so a short block on the
        # search_docs turn is acceptable; a down/stale farm skips Celery
        # entirely and _embed() runs locally.
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
                    self._persist(fv, ch_by_id, result)
        except ImportError:
            pass
        local_stale = [ch for ch in stale if ch["id"] not in result]
        for start in range(0, len(local_stale), _EMBED_BATCH):
            batch = local_stale[start:start + _EMBED_BATCH]
            embedded = self._embed([c.get("text", "") for c in batch])
            self._persist({ch["id"]: vector for ch, vector in zip(batch, embedded)},
                          ch_by_id, result)
        return result

    def score(self, query: str, chunks: list[dict]) -> list[tuple[float, dict]]:
        if not chunks:
            return []
        vectors = self.vectors_for(chunks)
        qa, qn = _fast(self._embed([query])[0])
        results: list[tuple[float, dict]] = []
        for ch in chunks:
            vec = vectors.get(ch["id"])
            if not vec or qn == 0.0 or len(vec) != len(qa):
                results.append((0.0, ch))
                continue
            va, vn = _fast_for(_hash_of(ch), vec)
            sim = sum(map(operator.mul, qa, va)) / (qn * vn) if vn else 0.0
            results.append((sim, ch))
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

def _file_stat(path: Path) -> str:
    try:
        st = path.stat()
        return f"{int(st.st_mtime)}:{st.st_size}"
    except Exception:
        return "0:0"


def _file_key(path: Path) -> str:
    """Content key: sha1 of the file bytes (CRLF and LF checkouts differ, which
    is correct: their chunk text differs too)."""
    try:
        return "sha1:" + hashlib.sha1(path.read_bytes()).hexdigest()
    except Exception:
        return "sha1:unreadable"


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
                "hash": _chunk_hash(chunk_text),
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
    """Load the chunk index from disk, re-chunking only files whose content changed.

    Files are keyed by a hash of their bytes (audit P2: ``mtime:size`` keys made
    every fresh clone re-chunk and rewrite the whole index); mtime+size is kept
    only as a fast path that skips reading unchanged files.
    """
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

    stored_files = stored.get("files") if isinstance(stored.get("files"), dict) else {}
    for path in files:
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        stat = _file_stat(path)
        old = stored_files.get(rel)
        if old and old.get("stat") == stat and old.get("key"):
            new_files[rel] = old          # fast path: unchanged on this machine
            continue
        key = _file_key(path)
        if old and old.get("key") == key:
            # Same content, new mtime (a fresh clone, a checkout): keep the
            # chunks and record the new stat so the next load is fast.
            new_files[rel] = dict(old, stat=stat)
        else:
            new_files[rel] = {"key": key, "stat": stat,
                              "chunks": _build_file_chunks(path)}
        changed = True

    if set(new_files) != set(stored_files):
        changed = True

    # Precompute content hashes (persisted in the index) for the embedding
    # cache lookups; older index files lack them.
    for fd in new_files.values():
        for c in fd.get("chunks") or []:
            if not c.get("hash"):
                c["hash"] = _chunk_hash(c.get("text", ""))
                changed = True

    all_chunks = [c for fd in new_files.values() for c in fd.get("chunks") or []]
    if changed or "chunks" not in stored:
        data: dict = {
            "files": new_files,
            "chunks": all_chunks,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        atomic_write_text(INDEX_FILE, json.dumps(data))
        _prune_orphan_vectors(all_chunks)
    else:
        data = dict(stored, files=new_files, chunks=all_chunks)
    _lexical_stats(all_chunks)            # warm BM25 tf/df for the first query
    _INDEX_CACHE = data
    return data


def _prune_orphan_vectors(chunks: list[dict]) -> None:
    """Drop cached vectors for text that left the index.

    Only when the embedding cache lives beside the index file, so a caller
    (or test) that redirected one of the two cannot prune the other with an
    unrelated chunk set.  Never fatal: a failed prune just leaves orphans.
    """
    if EMBEDDING_CACHE_FILE.parent != INDEX_FILE.parent or not EMBEDDING_CACHE_FILE.is_file():
        return
    try:
        prune_embedding_cache({_hash_of(c) for c in chunks})
    except Exception:
        pass


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
