#!/usr/bin/env python3
"""Run the hand-judged local-docs retrieval fixture against a scorer.

Default scorer is HybridScorer (the live search_docs path). A relevant chunk
at rank 6–50 is the FlashRank signal — Stage 3 only reorders Hybrid's fused
head. A miss entirely outside the scorer pool cannot be fixed by a reranker.

Usage (from repo root):
    python local_agent/eval_retrieval.py
    python local_agent/eval_retrieval.py --scorer lexical
    python local_agent/eval_retrieval.py --scorer hybrid --write-results
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import retrieval  # noqa: E402

FIXTURE_FILE = HERE / "evaluations" / "retrieval_hand_judged.json"
RESULTS_FILE = HERE / "evaluations" / "retrieval_hand_judged_last_run.json"


def load_fixture(path: Path | None = None) -> dict:
    target = path or FIXTURE_FILE
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data.get("queries"), list) or not data["queries"]:
        raise ValueError(f"{target} has no queries")
    return data


def validate_fixture(fixture: dict, chunks: list[dict] | None = None) -> list[str]:
    """Return human-readable problems. Empty list means the fixture is usable."""
    problems: list[str] = []
    queries = fixture.get("queries") or []
    n = len(queries)
    if n < 15 or n > 20:
        problems.append(f"expected 15-20 queries, got {n}")
    ids = [q.get("id") for q in queries]
    if len(ids) != len(set(ids)):
        problems.append("duplicate query id")
    by_id = {c["id"]: c for c in (chunks if chunks is not None else [])}
    for q in queries:
        qid = q.get("id") or "?"
        rel = q.get("relevant_chunk_ids") or []
        if not q.get("query"):
            problems.append(f"{qid}: empty query")
        if not rel:
            problems.append(f"{qid}: no relevant_chunk_ids")
        if chunks is not None:
            missing = [cid for cid in rel if cid not in by_id]
            if missing:
                problems.append(f"{qid}: missing from index: {missing}")
    return problems


def _scorer_named(name: str):
    key = (name or "hybrid").strip().lower()
    if key == "lexical":
        return retrieval.LexicalScorer(), "lexical"
    if key == "hybrid":
        return retrieval.HybridScorer(), "hybrid"
    raise ValueError(f"unknown scorer {name!r} (lexical|hybrid)")


def cpu_embed_listening(timeout_s: float = 1.0) -> bool:
    """True if router.CPU_HOST accepts a TCP connection (Ollama may still lack the model)."""
    import router
    host, _, port = router.CPU_HOST.partition(":")
    try:
        with socket.create_connection((host, int(port or "11435")), timeout=timeout_s):
            return True
    except OSError:
        return False


@contextmanager
def _fail_closed_embed():
    """Make Hybrid's embedding side raise immediately so it uses lexical fallback.

    Live Hybrid.score() otherwise waits on farm_offload (45s) then ollama_client.embed
    (120s/batch) when :11435 is down — 18 queries would hang for tens of minutes.
    """
    with patch("farm_offload.try_embed_on_farm", return_value=None), \
            patch("ollama_client.embed", side_effect=ConnectionError("cpu embed endpoint down")):
        yield


def evaluate(fixture: dict | None = None, scorer_name: str = "hybrid",
             chunks: list[dict] | None = None,
             fail_closed_embed: bool = False) -> dict:
    """Score every fixture query. Does not write files."""
    fixture = fixture or load_fixture()
    top_k = int(fixture.get("top_k") or 5)
    rerank_window = int(fixture.get("rerank_window") or 50)
    if chunks is None:
        chunks = retrieval._get_index().get("chunks") or []
    if fail_closed_embed and scorer_name.strip().lower() == "hybrid":
        with _fail_closed_embed():
            report = evaluate(fixture, scorer_name, chunks, fail_closed_embed=False)
        report["embed_mode"] = "lexical_fallback"
        report["embed_note"] = "fail-closed: CPU embed endpoint not used"
        return report
    scorer, resolved_name = _scorer_named(scorer_name)

    rows: list[dict] = []
    match_by_seen: set[str] = set()
    started = time.perf_counter()
    for q in fixture["queries"]:
        ranked = scorer.score(q["query"], chunks)
        for _score, ch in ranked:
            tag = ch.get("_match_by")
            if tag:
                match_by_seen.add(tag)
        order = [ch["id"] for _score, ch in ranked]
        relevant = list(q["relevant_chunk_ids"])
        ranks = {}
        for cid in relevant:
            try:
                ranks[cid] = order.index(cid) + 1
            except ValueError:
                ranks[cid] = None
        present = [r for r in ranks.values() if r is not None]
        best = min(present) if present else None
        row = {
            "id": q["id"],
            "query": q["query"],
            "kind": q.get("kind", ""),
            "relevant_chunk_ids": relevant,
            "ranks": ranks,
            "best_rank": best,
            "in_top_k": best is not None and best <= top_k,
            "in_rerank_window": best is not None and best <= rerank_window,
            "outside_top_k": best is None or best > top_k,
            "missing_from_pool": best is None,
            "flashrank_candidate": (
                best is not None and top_k < best <= rerank_window
            ),
            "top_k_ids": order[:top_k],
        }
        rows.append(row)

    outside = [r["id"] for r in rows if r["outside_top_k"]]
    flashrank = [r["id"] for r in rows if r["flashrank_candidate"]]
    missing = [r["id"] for r in rows if r["missing_from_pool"]]
    if resolved_name != "hybrid":
        embed_mode = "n/a"
    elif "embedding" in match_by_seen or "both" in match_by_seen:
        embed_mode = "live_or_cached"
    elif "lexical" in match_by_seen:
        embed_mode = "lexical_fallback"
    else:
        embed_mode = "unknown"
    return {
        "scorer": resolved_name,
        "embed_mode": embed_mode,
        "top_k": top_k,
        "rerank_window": rerank_window,
        "chunk_count": len(chunks),
        "elapsed_s": round(time.perf_counter() - started, 3),
        "n_queries": len(rows),
        "n_in_top_k": sum(1 for r in rows if r["in_top_k"]),
        "n_outside_top_k": len(outside),
        "n_flashrank_candidate": len(flashrank),
        "n_missing_from_pool": len(missing),
        "outside_top_k_ids": outside,
        "flashrank_candidate_ids": flashrank,
        "missing_from_pool_ids": missing,
        "queries": rows,
    }


def write_results(report: dict, path: Path | None = None) -> Path:
    target = path or RESULTS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(report)
    payload["written_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def _print_report(report: dict) -> None:
    print(
        f"scorer={report['scorer']}  embed={report['embed_mode']}  "
        f"chunks={report['chunk_count']}  {report['elapsed_s']}s"
    )
    print(
        f"in_top_{report['top_k']}={report['n_in_top_k']}/{report['n_queries']}  "
        f"outside_top_k={report['n_outside_top_k']}  "
        f"flashrank_window_only={report['n_flashrank_candidate']}  "
        f"missing_from_pool={report['n_missing_from_pool']}"
    )
    for row in report["queries"]:
        mark = "OK " if row["in_top_k"] else (
            "FR " if row["flashrank_candidate"] else "MISS"
        )
        print(
            f"  {mark} r={row['best_rank']!s:>4}  {row['id']}: {row['query']}"
        )
        if row["outside_top_k"]:
            print(f"       ranks={row['ranks']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorer", default="hybrid", choices=("hybrid", "lexical"))
    parser.add_argument("--write-results", action="store_true")
    parser.add_argument("--fixture", default=None)
    parser.add_argument(
        "--fail-closed-embed", action="store_true",
        help="Force Hybrid's embedding side to fail (lexical fallback). "
             "Auto-enabled for hybrid when CPU_HOST is not listening.")
    args = parser.parse_args()
    fixture = load_fixture(Path(args.fixture) if args.fixture else None)
    chunks = retrieval._get_index().get("chunks") or []
    problems = validate_fixture(fixture, chunks)
    if problems:
        print("fixture problems:")
        for p in problems:
            print(f"  - {p}")
        return 2
    fail_closed = bool(args.fail_closed_embed)
    if args.scorer == "hybrid" and not fail_closed and not cpu_embed_listening():
        print("CPU embed host not listening; Hybrid will fail-closed (lexical fallback)")
        fail_closed = True
    report = evaluate(fixture, scorer_name=args.scorer, chunks=chunks,
                      fail_closed_embed=fail_closed)
    _print_report(report)
    if args.write_results:
        path = write_results(report)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
