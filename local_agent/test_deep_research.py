#!/usr/bin/env python3
"""Stdlib tests for deep_research orchestration."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import deep_research
import search_backend
import tools


class _FakeBackend:
    name = "duckduckgo"

    def __init__(self, hits=None, error=None):
        self.hits = hits or [
            {"title": "Alpha", "url": "https://example.com/a", "snippet": "A"},
            {"title": "Beta", "url": "https://example.com/b", "snippet": "B"},
            {"title": "Gamma", "url": "https://example.com/c", "snippet": "C"},
        ]
        self.error = error
        self.queries: list[str] = []

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        self.queries.append(query)
        if self.error:
            raise self.error
        return list(self.hits)


def _fetch(args: dict) -> str:
    url = args["url"]
    return f"[{url}]\n\nExtract from {url} stating a verifiable fact."


def _reason_factory(plan_json, synth_json):
    def _reason(prompt: str, *, kind: str) -> tuple[str, str]:
        if kind == "plan":
            return plan_json, "routed cpu/stub"
        return synth_json, "routed cpu/stub"
    return _reason


class DeepResearchTests(unittest.TestCase):

    def test_schema_registered(self):
        self.assertIn("deep_research", tools.TOOLS)
        names = {item["function"]["name"] for item in tools.schemas()}
        self.assertIn("deep_research", names)
        params = next(item["function"]["parameters"] for item in tools.schemas()
                      if item["function"]["name"] == "deep_research")
        self.assertEqual(["question"], params["required"])

    def test_structured_answer_cites_mocked_urls_and_caps(self):
        backend = _FakeBackend()
        synth = json.dumps({
            "answer": "Alpha happened (https://example.com/a). Beta followed (https://example.com/b).",
            "gaps": [],
        })
        raw = deep_research.deep_research(
            {"question": "What happened?", "max_rounds": 2, "max_sources": 2},
            backend=backend,
            fetch=_fetch,
            reason=_reason_factory('{"queries":["q1","q2","q3"]}', synth),
        )
        data = json.loads(raw)
        self.assertEqual("What happened?", data["question"])
        self.assertIn("https://example.com/a", data["answer"])
        self.assertEqual(2, len(data["sources"]))
        self.assertEqual(["https://example.com/a", "https://example.com/b"],
                         [s["url"] for s in data["sources"]])
        self.assertLessEqual(len(data["sources"]), 2)
        self.assertEqual("duckduckgo", data["backend"])
        self.assertEqual(["q1", "q2", "q3"], data["sub_queries"])
        self.assertEqual(1, data["rounds_used"])

    def test_max_rounds_cap(self):
        backend = _FakeBackend()
        calls = {"n": 0}

        def reason(prompt, *, kind):
            calls["n"] += 1
            if kind == "plan":
                return '{"queries":["only"]}', "ok"
            return json.dumps({
                "answer": "Incomplete (https://example.com/a).",
                "gaps": ["need more on gamma"],
            }), "ok"

        data = json.loads(deep_research.deep_research(
            {"question": "topic", "max_rounds": 9, "max_sources": 6},
            backend=backend,
            fetch=_fetch,
            reason=reason,
        ))
        self.assertLessEqual(data["rounds_used"], 4)
        self.assertGreaterEqual(data["rounds_used"], 2)

    def test_no_internet_is_clean_message(self):
        backend = _FakeBackend(error=search_backend.SearchError("no-internet", "down"))
        with patch.object(tools, "search_docs", return_value='{"results":[]}'):
            data = json.loads(deep_research.deep_research(
                {"question": "topic", "max_rounds": 1, "max_sources": 3},
                backend=backend,
                fetch=_fetch,
                reason=_reason_factory('{"queries":["topic"]}', "{}"),
            ))
        self.assertIn("No internet", data["answer"])
        self.assertEqual([], data["sources"])
        self.assertTrue(any("SEARCH UNAVAILABLE" in n for n in data["notes"]))

    def test_missing_question_raises(self):
        with self.assertRaises(tools.ToolError):
            deep_research.deep_research({})

    def test_unsupported_citation_is_removed(self):
        answer, gaps = deep_research._parse_synthesis(
            'Claim (https://example.com/a) and invented (https://bad.example/x).',
            [{"title": "Alpha", "url": "https://example.com/a", "extract": "fact"}],
        )
        self.assertIn("https://example.com/a", answer)
        self.assertNotIn("https://bad.example/x", answer)
        self.assertIn("[unverified citation removed]", answer)
        self.assertTrue(any("not in the gathered" in gap for gap in gaps))


if __name__ == "__main__":
    unittest.main()
