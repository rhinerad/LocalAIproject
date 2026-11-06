#!/usr/bin/env python3
"""Tests for the deterministic Self-RAG document relevance filter."""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import retrieval


class RetrievalRelevanceTests(unittest.TestCase):
    def test_filters_lexical_near_miss_and_keeps_evidence_terms(self):
        candidates = [
            {"source": "docs/a.md", "heading": "# Routing policy",
             "text": "The routing fallback keeps GPU work isolated.", "score": 4.0},
            {"source": "docs/b.md", "heading": "# History",
             "text": "A generic project note without the requested concepts.", "score": 3.0},
        ]
        with patch.object(retrieval, "search", return_value=candidates):
            got = retrieval.search_relevant("routing fallback policy", max_results=5)
        self.assertEqual(["docs/a.md"], [item["source"] for item in got])
        self.assertIn("routing", got[0]["matched_terms"])

    def test_empty_when_no_query_terms_are_supported(self):
        with patch.object(retrieval, "search", return_value=[{
            "source": "docs/a.md", "heading": "# Other", "text": "Unrelated evidence.", "score": 2.0
        }]):
            self.assertEqual([], retrieval.search_relevant("thermal routing", max_results=5))


class RetrievalIndexConcurrencyTests(unittest.TestCase):
    """search_docs (which calls retrieval._get_index()) is in
    tools.CONCURRENCY_SAFE_TOOLS, so agent.py's hop loop may call it from
    several threads at once. Regression for the lazy-cache race this
    uncovered: two threads finding a cold _INDEX_CACHE would both
    independently call the expensive, file-writing load_index()."""

    def setUp(self):
        self._old_cache = retrieval._INDEX_CACHE
        retrieval._INDEX_CACHE = None

    def tearDown(self):
        retrieval._INDEX_CACHE = self._old_cache

    def test_concurrent_get_index_builds_only_once(self):
        build_count = {"n": 0}
        overlap_seen = {"seen": False}
        inside = {"n": 0}
        guard = threading.Lock()

        def slow_load_index(force_rebuild=False):
            with guard:
                inside["n"] += 1
                if inside["n"] > 1:
                    overlap_seen["seen"] = True
            build_count["n"] += 1
            time.sleep(0.1)
            with guard:
                inside["n"] -= 1
            return {"files": {}, "chunks": []}

        with patch.object(retrieval, "load_index", slow_load_index):
            threads = [threading.Thread(target=retrieval._get_index) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(1, build_count["n"],
                         "the expensive index build ran more than once for concurrent callers")
        self.assertFalse(overlap_seen["seen"],
                         "two threads were inside the index build at the same time")
        self.assertIsNotNone(retrieval._INDEX_CACHE)

    def test_rebuild_serializes_against_concurrent_get_index(self):
        # A sequential run_build("rebuild") call could land in the same hop
        # as concurrent search_docs calls (rebuild isn't in
        # CONCURRENCY_SAFE_TOOLS, but nothing stops it running on the main
        # thread while the safe tools run in the background pool). Both must
        # serialize on _INDEX_LOCK rather than one reading a half-built index.
        seen_during_rebuild = []
        started_rebuild = threading.Event()

        def slow_load_index(force_rebuild=False):
            # Mirror the real load_index()'s side effect of setting the
            # module-level cache itself, since rebuild() doesn't do that —
            # it relies on load_index() to.
            started_rebuild.set()
            time.sleep(0.15)
            data = {"files": {}, "chunks": [{"tag": "rebuilt"}]}
            retrieval._INDEX_CACHE = data
            return data

        def run_rebuild():
            with patch.object(retrieval, "load_index", slow_load_index):
                retrieval.rebuild()

        t = threading.Thread(target=run_rebuild)
        t.start()
        started_rebuild.wait(timeout=2)
        # rebuild() is holding _INDEX_LOCK and mid-sleep right now; a
        # concurrent _get_index() must block until it releases, never
        # observing a torn/half-set _INDEX_CACHE.
        with patch.object(retrieval, "load_index", return_value={"files": {}, "chunks": [{"tag": "fallback"}]}):
            idx = retrieval._get_index()
        t.join(timeout=2)
        seen_during_rebuild.append(idx)

        self.assertEqual([{"tag": "rebuilt"}], idx["chunks"],
                         "_get_index() should have blocked until rebuild() finished "
                         "and then reused its result, not raced past it")



class SearchRelevantSemanticKeepTests(unittest.TestCase):
    def test_keeps_embedding_only_hit_without_term_overlap(self):
        candidates = [{
            "source": "docs/a.md",
            "heading": "# Liveness",
            "text": "Broker reachability is confirmed by a TCP check, then inspect.ping().",
            "score": 0.03,
            "match_by": "embedding",
        }]
        with patch.object(retrieval, "search", return_value=candidates):
            got = retrieval.search_relevant(
                "tell whether queued task daemons died", max_results=5)
        self.assertEqual(["docs/a.md"], [item["source"] for item in got])
        self.assertTrue(got[0].get("semantic_match"))
        self.assertEqual(got[0].get("matched_terms"), [])

    def test_keeps_both_match_even_without_meaningful_overlap(self):
        candidates = [{
            "source": "docs/b.md",
            "heading": "# Other",
            "text": "Unrelated evidence.",
            "score": 0.02,
            "match_by": "both",
        }]
        with patch.object(retrieval, "search", return_value=candidates):
            got = retrieval.search_relevant("thermal routing", max_results=5)
        self.assertEqual(["docs/b.md"], [item["source"] for item in got])

if __name__ == "__main__":
    unittest.main(verbosity=2)
