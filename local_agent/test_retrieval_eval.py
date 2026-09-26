#!/usr/bin/env python3
"""Integrity tests for the hand-judged retrieval fixture.

Does not require Ollama. Hybrid quality is recorded by eval_retrieval.py,
not asserted here — a top-5 miss is the FlashRank signal, not a test failure.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import eval_retrieval
import retrieval


class HandJudgedFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = eval_retrieval.load_fixture()
        raw = json.loads(retrieval.INDEX_FILE.read_text(encoding="utf-8"))
        cls.disk_chunks = raw.get("chunks") or []

    def test_query_count_and_unique_ids(self):
        queries = self.fixture["queries"]
        self.assertGreaterEqual(len(queries), 15)
        self.assertLessEqual(len(queries), 20)
        ids = [q["id"] for q in queries]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_relevant_chunk_exists_on_disk_index(self):
        problems = eval_retrieval.validate_fixture(self.fixture, self.disk_chunks)
        self.assertEqual(problems, [])

    def test_top_k_and_rerank_window_match_stage3_sketch(self):
        self.assertEqual(self.fixture["top_k"], 5)
        self.assertEqual(self.fixture["rerank_window"], 50)

    def test_kinds_are_labeled(self):
        kinds = {q.get("kind") for q in self.fixture["queries"]}
        self.assertTrue(kinds <= {"lexical", "paraphrase"})
        self.assertIn("paraphrase", kinds)


class LexicalEvalSmokeTests(unittest.TestCase):
    def test_lexical_run_returns_a_row_per_query(self):
        fixture = eval_retrieval.load_fixture()
        chunks = json.loads(retrieval.INDEX_FILE.read_text(encoding="utf-8")).get(
            "chunks") or []
        report = eval_retrieval.evaluate(
            fixture, scorer_name="lexical", chunks=chunks)
        self.assertEqual(report["scorer"], "lexical")
        self.assertEqual(report["n_queries"], len(fixture["queries"]))
        self.assertEqual(len(report["queries"]), len(fixture["queries"]))
        for row in report["queries"]:
            self.assertIn("best_rank", row)
            self.assertEqual(
                set(row["ranks"]), set(row["relevant_chunk_ids"]))

    def test_hybrid_fail_closed_matches_lexical_best_ranks(self):
        fixture = eval_retrieval.load_fixture()
        chunks = json.loads(retrieval.INDEX_FILE.read_text(encoding="utf-8")).get(
            "chunks") or []
        lex = eval_retrieval.evaluate(fixture, "lexical", chunks)
        hy = eval_retrieval.evaluate(
            fixture, "hybrid", chunks, fail_closed_embed=True)
        self.assertEqual(hy["embed_mode"], "lexical_fallback")
        for a, b in zip(lex["queries"], hy["queries"]):
            self.assertEqual(a["id"], b["id"])
            self.assertEqual(a["best_rank"], b["best_rank"], a["id"])


if __name__ == "__main__":
    unittest.main()
