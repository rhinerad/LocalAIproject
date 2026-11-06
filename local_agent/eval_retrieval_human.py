#!/usr/bin/env python3
"""Side-by-side lexical vs live-dense HybridScorer for human judgment.

Prefers workstation CPU Ollama (:11435, nomic-embed-text). Farm embed is
the fallback for query/chunk vectors when :11435 is down. Hybrid fusion is
the real HybridScorer RRF. Lexical is LexicalScorer — what search_docs
returns today when the dense side fail-closes.

Usage (from repo root):
    python -u local_agent/eval_retrieval_human.py
    python -u local_agent/eval_retrieval_human.py --skip-warm
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Line-buffer when redirected.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import eval_retrieval
import farm_offload
import retrieval

OUT_JSON = HERE / "evaluations" / "retrieval_human_side_by_side.json"
OUT_MD = HERE / "evaluations" / "retrieval_human_side_by_side.md"
SNIPPET_CHARS = 420
WARM_BATCH = 8
QUERY_PREFIX = "_human_eval_query:"


class FarmQueryEmbeddingScorer(retrieval.EmbeddingScorer):
    """Production chunk cache/farm path; query embed via farm, not :11435."""

    def score(self, query: str, chunks: list[dict]) -> list[tuple[float, dict]]:
        if not chunks:
            return []
        vectors = self.vectors_for(chunks)
        qmap = farm_offload.try_embed_on_farm(
            [{"id": "_query", "text": query}], timeout_s=30.0)
        if not qmap or "_query" not in qmap:
            raise ConnectionError("farm query embed failed")
        qvec = qmap["_query"]
        results = [
            (retrieval._cosine(qvec, vectors.get(ch["id"], [])), ch)
            for ch in chunks
        ]
        return sorted(results, key=lambda x: -x[0])


def _cache_fresh_ids(chunks: list[dict]) -> tuple[set[str], list[dict]]:
    cache = retrieval._load_embedding_cache()
    fresh: set[str] = set()
    stale: list[dict] = []
    for ch in chunks:
        entry = cache.get("vectors", {}).get(ch["id"])
        h = retrieval._chunk_hash(ch.get("text", ""))
        if entry and entry.get("hash") == h and entry.get("vector"):
            fresh.add(ch["id"])
        else:
            stale.append(ch)
    return fresh, stale


def _write_vectors(new_vectors: dict[str, list[float]], chunks_by_id: dict) -> int:
    if not new_vectors:
        return 0
    written = 0
    with retrieval._EMBED_CACHE_LOCK:
        cache = retrieval._load_embedding_cache()
        for cid, vector in new_vectors.items():
            ch = chunks_by_id.get(cid)
            if ch is None:
                continue
            cache["vectors"][cid] = {
                "hash": retrieval._chunk_hash(ch.get("text", "")),
                "vector": vector,
            }
            written += 1
        cache["model"] = retrieval.EMBED_MODEL
        retrieval._save_embedding_cache(cache)
    return written


def _local_cpu_up() -> bool:
    return eval_retrieval.cpu_embed_listening(timeout_s=1.0)


def warm_local(chunks: list[dict], batch_size: int = 64) -> dict:
    """Embed stale chunks on local CPU Ollama, skipping the farm queue."""
    from unittest.mock import patch
    started = time.perf_counter()
    fresh, stale = _cache_fresh_ids(chunks)
    print(f"cache fresh={len(fresh)} stale={len(stale)} total={len(chunks)} via=local_cpu")
    scorer = retrieval.EmbeddingScorer()
    done = 0
    with patch("farm_offload.try_embed_on_farm", return_value=None):
        for i in range(0, len(stale), batch_size):
            batch = stale[i:i + batch_size]
            t0 = time.perf_counter()
            scorer.vectors_for(batch)
            done += len(batch)
            print(f"  local warm {done}/{len(stale)} {time.perf_counter() - t0:.2f}s", flush=True)
    fresh_after, stale_after = _cache_fresh_ids(chunks)
    return {
        "fresh_before": len(fresh),
        "stale_before": len(stale),
        "fresh_after": len(fresh_after),
        "stale_after": len(stale_after),
        "failed_ids": [c["id"] for c in stale_after][:20],
        "n_failed": len(stale_after),
        "farm_calls": 0,
        "farm_ok": 0,
        "elapsed_s": round(time.perf_counter() - started, 3),
        "coverage": round(len(fresh_after) / max(len(chunks), 1), 4),
        "via": "local_cpu",
    }


def warm_missing(chunks: list[dict], batch_size: int = WARM_BATCH) -> dict:
    started = time.perf_counter()
    fresh, stale = _cache_fresh_ids(chunks)
    by_id = {c["id"]: c for c in chunks}
    failed: list[str] = []
    farm_calls = 0
    farm_ok = 0
    print(f"cache fresh={len(fresh)} stale={len(stale)} total={len(chunks)}")
    i = 0
    while i < len(stale):
        if not farm_offload.should_route(farm_offload.KIND_EMBED, blocking=True):
            print("farm embed not routable; stopping warm")
            failed.extend(c["id"] for c in stale[i:])
            break
        size = batch_size
        payload = [{"id": c["id"], "text": c.get("text", "")} for c in stale[i:i + size]]
        farm_calls += 1
        t0 = time.perf_counter()
        got = farm_offload.try_embed_on_farm(payload, timeout_s=30.0)
        elapsed = time.perf_counter() - t0
        if not got:
            if size > 1:
                print(f"  batch {i} size={size} failed in {elapsed:.1f}s; retry size=1")
                payload = [payload[0]]
                farm_calls += 1
                t0 = time.perf_counter()
                got = farm_offload.try_embed_on_farm(payload, timeout_s=30.0)
                elapsed = time.perf_counter() - t0
                size = 1
        if not got:
            print(f"  FAIL id={stale[i]['id']} after {elapsed:.1f}s")
            failed.append(stale[i]["id"])
            i += 1
            continue
        n = _write_vectors(got, by_id)
        farm_ok += 1
        i += size
        if farm_ok % 5 == 0 or i >= len(stale):
            print(f"  warmed {min(i, len(stale))}/{len(stale)} last_batch={n} {elapsed:.2f}s")
    fresh_after, stale_after = _cache_fresh_ids(chunks)
    return {
        "fresh_before": len(fresh),
        "stale_before": len(stale),
        "fresh_after": len(fresh_after),
        "stale_after": len(stale_after),
        "failed_ids": failed[:20],
        "n_failed": len(failed),
        "farm_calls": farm_calls,
        "farm_ok": farm_ok,
        "elapsed_s": round(time.perf_counter() - started, 3),
        "coverage": round(len(fresh_after) / max(len(chunks), 1), 4),
    }


def _search_rows(ranked: list[tuple[float, dict]], max_results: int) -> list[dict]:
    rows: list[dict] = []
    for score, chunk in ranked[:max_results]:
        if score <= 0:
            break
        row = {
            "id": chunk["id"],
            "source": chunk.get("source", ""),
            "heading": chunk.get("heading", ""),
            "text": chunk.get("text", "")[:1500],
            "score": round(float(score), 4),
        }
        match_by = chunk.get("_match_by")
        if match_by:
            row["match_by"] = match_by
        rows.append(row)
    return rows


def _filter_relevant(query: str, candidates: list[dict], max_results: int) -> list[dict]:
    terms = {t for t in retrieval.LexicalScorer._tok(query) if t not in retrieval._QUERY_STOP}
    relevant: list[dict] = []
    for item in candidates:
        chunk_terms = set(retrieval.LexicalScorer._tok(
            f"{item.get('heading', '')}\n{item.get('text', '')}"))
        overlap = terms & chunk_terms
        match_by = item.get("match_by", "")
        semantic_ok = match_by in ("embedding", "both")
        if overlap or semantic_ok:
            copied = dict(item)
            copied["matched_terms"] = sorted(overlap)[:8]
            if semantic_ok and not overlap:
                copied["semantic_match"] = True
            relevant.append(copied)
        if len(relevant) >= max_results:
            break
    return relevant


def _snippet(text: str) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= SNIPPET_CHARS:
        return compact
    return compact[:SNIPPET_CHARS - 1] + "…"


def _present(rows: list[dict], gold: set[str]) -> list[dict]:
    out = []
    for i, row in enumerate(rows, 1):
        out.append({
            "rank": i,
            "id": row.get("id", ""),
            "source": row.get("source", ""),
            "heading": row.get("heading", ""),
            "gold": row.get("id") in gold,
            "match_by": row.get("match_by"),
            "score": row.get("score"),
            "semantic_match": bool(row.get("semantic_match")),
            "matched_terms": row.get("matched_terms") or [],
            "snippet": _snippet(row.get("text", "")),
        })
    return out


def _best_rank(order: list[str], gold: list[str]) -> int | None:
    ranks = []
    for cid in gold:
        try:
            ranks.append(order.index(cid) + 1)
        except ValueError:
            continue
    return min(ranks) if ranks else None


def evaluate_side_by_side(chunks: list[dict], fixture: dict) -> dict:
    top_k = int(fixture.get("top_k") or 5)
    candidate_n = max(top_k * 3, 8)
    lexical = retrieval.LexicalScorer()
    if _local_cpu_up():
        hybrid = retrieval.HybridScorer()
        print("hybrid via local CPU Ollama :11435", flush=True)
    else:
        hybrid = retrieval.HybridScorer(embedding=FarmQueryEmbeddingScorer())
        print("hybrid via farm nomic-embed-text (CPU :11435 down)", flush=True)
    rows = []
    match_by_seen: set[str] = set()
    started = time.perf_counter()
    for q in fixture["queries"]:
        query = q["query"]
        gold = list(q["relevant_chunk_ids"])
        gold_set = set(gold)
        lex_ranked = lexical.score(query, chunks)
        hy_ranked = hybrid.score(query, chunks)
        for _s, ch in hy_ranked:
            tag = ch.get("_match_by")
            if tag:
                match_by_seen.add(tag)
        lex_order = [ch["id"] for _s, ch in lex_ranked]
        hy_order = [ch["id"] for _s, ch in hy_ranked]
        lex_docs = _filter_relevant(query, _search_rows(lex_ranked, candidate_n), top_k)
        hy_docs = _filter_relevant(query, _search_rows(hy_ranked, candidate_n), top_k)
        lex_ids = [r["id"] for r in lex_docs]
        hy_ids = [r["id"] for r in hy_docs]
        lex_best = _best_rank(lex_order, gold)
        hy_best = _best_rank(hy_order, gold)
        lex_in = any(i in gold_set for i in lex_ids)
        hy_in = any(i in gold_set for i in hy_ids)
        same = lex_ids == hy_ids
        if same:
            disagreement = "identical"
        elif hy_in and not lex_in:
            disagreement = "hybrid_recovers_gold"
        elif lex_in and not hy_in:
            disagreement = "lexical_keeps_gold_hybrid_drops"
        elif hy_in and lex_in and hy_ids[0] != lex_ids[0]:
            disagreement = "both_have_gold_different_order"
        else:
            disagreement = "different_no_gold_or_partial"
        rows.append({
            "id": q["id"],
            "query": query,
            "kind": q.get("kind", ""),
            "intent": q.get("intent", ""),
            "relevant_chunk_ids": gold,
            "lexical_best_rank": lex_best,
            "hybrid_best_rank": hy_best,
            "lexical_gold_in_search_docs": lex_in,
            "hybrid_gold_in_search_docs": hy_in,
            "disagreement": disagreement,
            "lexical_search_docs": _present(lex_docs, gold_set),
            "hybrid_search_docs": _present(hy_docs, gold_set),
        })
        print(
            f"  {q['id']}: lex_rank={lex_best} hy_rank={hy_best} "
            f"docs_gold L={int(lex_in)} H={int(hy_in)} {disagreement}"
        )
    n = len(rows)
    return {
        "scorers": {
            "lexical": "LexicalScorer (search_docs fail-closed / explicit lexical)",
            "hybrid": "HybridScorer RRF + farm nomic-embed-text:latest",
        },
        "match_by_seen": sorted(match_by_seen),
        "embed_mode": (
            "live_or_cached" if match_by_seen & {"embedding", "both"} else "unknown"
        ),
        "top_k": top_k,
        "candidate_window": candidate_n,
        "chunk_count": len(chunks),
        "elapsed_s": round(time.perf_counter() - started, 3),
        "n_queries": n,
        "n_lexical_gold_in_search_docs": sum(1 for r in rows if r["lexical_gold_in_search_docs"]),
        "n_hybrid_gold_in_search_docs": sum(1 for r in rows if r["hybrid_gold_in_search_docs"]),
        "n_lexical_top5_rank": sum(
            1 for r in rows if r["lexical_best_rank"] is not None and r["lexical_best_rank"] <= top_k
        ),
        "n_hybrid_top5_rank": sum(
            1 for r in rows if r["hybrid_best_rank"] is not None and r["hybrid_best_rank"] <= top_k
        ),
        "n_identical_result_sets": sum(1 for r in rows if r["disagreement"] == "identical"),
        "n_hybrid_recovers_gold": sum(1 for r in rows if r["disagreement"] == "hybrid_recovers_gold"),
        "n_lexical_keeps_gold_hybrid_drops": sum(
            1 for r in rows if r["disagreement"] == "lexical_keeps_gold_hybrid_drops"
        ),
        "queries": rows,
    }


def _md_hit(hit: dict) -> str:
    gold = " **GOLD**" if hit.get("gold") else ""
    mb = hit.get("match_by") or "lexical"
    heading = hit.get("heading") or "(no heading)"
    return (
        f"{hit['rank']}. `{hit['id']}`{gold}  \n"
        f"   match_by={mb} score={hit.get('score')}  \n"
        f"   {heading}  \n"
        f"   {_snippet(hit.get('snippet', ''))}\n"
    )


def write_markdown(report: dict, warm: dict, path: Path) -> None:
    lines = [
        "# Lexical vs Hybrid search_docs — human quality comparison",
        "",
        "Judge **which result set would actually answer the question better**,",
        "not only whether the gold chunk id is in top-5.",
        "",
        f"- chunks: {report['chunk_count']}",
        f"- embed_mode: {report['embed_mode']}  match_by seen: {report['match_by_seen']}",
        f"- cache coverage after warm: {warm.get('coverage')} "
        f"({warm.get('fresh_after')}/{report['chunk_count']})",
        f"- farm warm: {warm.get('farm_ok')}/{warm.get('farm_calls')} ok "
        f"in {warm.get('elapsed_s')}s",
        f"- scoring elapsed: {report['elapsed_s']}s",
        "",
        "## Mechanical summary (supporting, not the decision)",
        "",
        f"- gold in search_docs top-5: lexical "
        f"{report['n_lexical_gold_in_search_docs']}/{report['n_queries']}, "
        f"hybrid {report['n_hybrid_gold_in_search_docs']}/{report['n_queries']}",
        f"- gold rank ≤5 (raw scorer, before search_relevant filter): lexical "
        f"{report['n_lexical_top5_rank']}/{report['n_queries']}, "
        f"hybrid {report['n_hybrid_top5_rank']}/{report['n_queries']}",
        f"- identical result sets: {report['n_identical_result_sets']}",
        f"- hybrid recovers gold lexical missed: {report['n_hybrid_recovers_gold']}",
        f"- lexical keeps gold hybrid dropped: {report['n_lexical_keeps_gold_hybrid_drops']}",
        "",
        "## Per-query",
        "",
    ]
    for q in report["queries"]:
        lines.append(f"### {q['id']}")
        lines.append("")
        lines.append(f"**Query:** {q['query']}")
        lines.append("")
        lines.append(f"**Intent:** {q.get('intent') or '(none)'}")
        lines.append("")
        lines.append(
            f"**Gold ids:** {', '.join('`'+g+'`' for g in q['relevant_chunk_ids'])}"
        )
        lines.append("")
        lines.append(
            f"**Ranks (raw scorer):** lexical={q['lexical_best_rank']}  "
            f"hybrid={q['hybrid_best_rank']}  "
            f"search_docs gold: L={q['lexical_gold_in_search_docs']} "
            f"H={q['hybrid_gold_in_search_docs']}  "
            f"**{q['disagreement']}**"
        )
        lines.append("")
        lines.append("**Lexical search_docs**")
        lines.append("")
        if q["lexical_search_docs"]:
            lines.extend(_md_hit(h) for h in q["lexical_search_docs"])
        else:
            lines.append("(empty)")
            lines.append("")
        lines.append("**Hybrid search_docs**")
        lines.append("")
        if q["hybrid_search_docs"]:
            lines.extend(_md_hit(h) for h in q["hybrid_search_docs"])
        else:
            lines.append("(empty)")
            lines.append("")
        lines.append("---")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-warm", action="store_true")
    parser.add_argument("--batch-size", type=int, default=WARM_BATCH)
    args = parser.parse_args()
    fixture = eval_retrieval.load_fixture()
    chunks = retrieval._get_index().get("chunks") or []
    problems = eval_retrieval.validate_fixture(fixture, chunks)
    if problems:
        print("fixture problems:")
        for p in problems:
            print(f"  - {p}")
        return 2
    local_up = _local_cpu_up()
    farm_ok = farm_offload.should_route(farm_offload.KIND_EMBED, blocking=True)
    print(f"cpu :11435 listening={local_up} farm_embed={farm_ok}", flush=True)
    if not local_up and not farm_ok:
        print("neither local CPU Ollama nor farm embed is available")
        return 3
    if args.skip_warm:
        fresh, stale = _cache_fresh_ids(chunks)
        warm = {
            "fresh_before": len(fresh),
            "stale_before": len(stale),
            "fresh_after": len(fresh),
            "stale_after": len(stale),
            "failed_ids": [],
            "n_failed": 0,
            "farm_calls": 0,
            "farm_ok": 0,
            "elapsed_s": 0.0,
            "coverage": round(len(fresh) / max(len(chunks), 1), 4),
            "skipped": True,
        }
        print(f"skip-warm coverage={warm['coverage']}", flush=True)
    elif local_up:
        warm = warm_local(chunks, batch_size=64)
    else:
        warm = warm_missing(chunks, batch_size=args.batch_size)
        print(
            f"warm done coverage={warm['coverage']} "
            f"failed={warm['n_failed']} {warm['elapsed_s']}s"
        )
    if warm["coverage"] < 0.9:
        print(f"coverage {warm['coverage']} < 0.9; refusing to call this live-dense")
        return 4
    print("scoring 18 queries…")
    report = evaluate_side_by_side(chunks, fixture)
    report["warm"] = warm
    report["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if report["embed_mode"] != "live_or_cached":
        print(f"embed_mode={report['embed_mode']} match_by={report['match_by_seen']}")
        print("dense side did not tag embedding hits; refusing")
        return 5
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, warm, OUT_MD)
    print(
        f"search_docs gold L={report['n_lexical_gold_in_search_docs']}/"
        f"{report['n_queries']} H={report['n_hybrid_gold_in_search_docs']}/"
        f"{report['n_queries']}"
    )
    print(
        f"raw top-5 L={report['n_lexical_top5_rank']}/{report['n_queries']} "
        f"H={report['n_hybrid_top5_rank']}/{report['n_queries']}"
    )
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
