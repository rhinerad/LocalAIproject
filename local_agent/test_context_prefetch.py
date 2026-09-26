#!/usr/bin/env python3
"""Regression coverage for the pre-model context injection seam."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import context_prefetch


class ContextPrefetchTests(unittest.TestCase):
    def test_early_url_and_remaining_stages_keep_historical_order(self) -> None:
        seen: list[str] = []
        prefetcher = context_prefetch.ContextPrefetcher(
            url_evidence=lambda: seen.append("url"),
            project_docs=lambda: seen.append("project"),
            prior_chats=lambda: seen.append("prior"),
            difficulty_plan=lambda: seen.append("difficulty"),
            exemplars=lambda: seen.append("exemplars") or ["example-1"],
        )
        prefetcher.inject_early_url_evidence()
        self.assertEqual(["url"], seen)
        self.assertEqual(["example-1"], prefetcher.inject_remaining())
        self.assertEqual(["url", "project", "prior", "difficulty", "exemplars"], seen)

    def test_named_policy_preserves_the_existing_limits(self) -> None:
        self.assertEqual(2400, context_prefetch.BUDGETS.tool_result_chars)
        self.assertEqual(3500, context_prefetch.BUDGETS.url_evidence_chars)
        self.assertEqual(3200, context_prefetch.BUDGETS.exemplar_chars)


if __name__ == "__main__":
    unittest.main(verbosity=2)
