#!/usr/bin/env python3
"""Stdlib tests for agentic_retrieval (RAG_EVALUATION.md Stage 4).

All model/search calls are injected fakes — no real Ollama call, no GPU,
no real document index touched.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agentic_retrieval
import tools


def _chunk(source: str, heading: str, text: str) -> dict:
    return {"source": source, "heading": heading, "text": text}


def _reason_queue(responses: list[str]):
    """Returns a `reason` callable that yields each response in order,
    regardless of prompt content — mirrors test_deep_research.py's
    `_reason_factory` but for a single-kind ("grade") call sequence."""
    calls: list[str] = []

    def _reason(prompt: str, *, kind: str) -> tuple[str, str]:
        calls.append(kind)
        idx = len(calls) - 1
        if idx >= len(responses):
            return "", "no more fake responses"
        return responses[idx], "routed cpu/stub"
    return _reason


class SchemaAndScopeTests(unittest.TestCase):
    def test_schema_registered(self):
        self.assertIn("agentic_search_docs", tools.TOOLS)
        names = {item["function"]["name"] for item in tools.schemas()}
        self.assertIn("agentic_search_docs", names)
        params = next(item["function"]["parameters"] for item in tools.schemas()
                      if item["function"]["name"] == "agentic_search_docs")
        self.assertEqual(["question"], params["required"])

    def test_project_only_and_not_concurrency_safe(self):
        # Same corpus/scope as search_docs (project docs), and — like
        # deep_research — it calls the model, so it must stay off the
        # concurrency-safe list (sequential tool execution only).
        self.assertIn("agentic_search_docs", tools.PROJECT_ONLY_TOOLS)
        self.assertNotIn("agentic_search_docs", tools.CONCURRENCY_SAFE_TOOLS)
        self.assertIn("search_docs", tools.CONCURRENCY_SAFE_TOOLS)
        self.assertIn("search_docs", tools.PROJECT_ONLY_TOOLS)
        desc = tools.TOOLS["agentic_search_docs"][1].lower()
        self.assertIn("preferred", desc)
        self.assertIn("hybrid", tools.TOOLS["search_docs"][1].lower())


class AgenticSearchDocsTests(unittest.TestCase):
    def test_requires_question(self):
        with self.assertRaises(tools.ToolError):
            agentic_retrieval.agentic_search_docs({})

    def test_sufficient_on_first_round_no_retry(self):
        def fake_search(query, max_results):
            return [_chunk("docs/routing.md", "# Routing", "The router prefers CPU when idle.")]

        reason = _reason_queue([json.dumps({
            "answer": "The router prefers CPU when idle (docs/routing.md).",
            "sufficient": True,
            "gaps": [],
        })])

        raw = agentic_retrieval.agentic_search_docs(
            {"question": "What does the router prefer?"}, search=fake_search, reason=reason)
        data = json.loads(raw)
        self.assertEqual(data["rounds_used"], 1)
        self.assertIn("docs/routing.md", data["answer"])
        self.assertEqual(len(data["sources"]), 1)

    def test_retries_with_rewritten_query_then_succeeds(self):
        calls = {"n": 0}

        def fake_search(query, max_results):
            calls["n"] += 1
            if calls["n"] == 1:
                return [_chunk("docs/unrelated.md", "# Other", "Nothing relevant here.")]
            return [_chunk("docs/thermal.md", "# Thermal", "GPU jobs wait for 60C.")]

        reason = _reason_queue([
            json.dumps({"answer": "Not established.", "sufficient": False,
                        "gaps": ["thermal cooldown temperature"]}),
            json.dumps({"answer": "GPU jobs wait for 60C (docs/thermal.md).",
                        "sufficient": True, "gaps": []}),
        ])

        raw = agentic_retrieval.agentic_search_docs(
            {"question": "What temperature must the GPU cool to?", "max_rounds": 3},
            search=fake_search, reason=reason)
        data = json.loads(raw)
        self.assertEqual(data["rounds_used"], 2)
        self.assertIn("docs/thermal.md", data["answer"])
        self.assertIn("thermal cooldown temperature", data["queries_used"])

    def test_no_evidence_and_no_model_gives_honest_fallback(self):
        def fake_search(query, max_results):
            return []

        def fake_reason(prompt, *, kind):
            return "", "local reasoning model unavailable (no route)"

        raw = agentic_retrieval.agentic_search_docs(
            {"question": "Anything?"}, search=fake_search, reason=fake_reason)
        data = json.loads(raw)
        self.assertIn("did not establish", data["answer"])
        self.assertEqual(data["sources"], [])

    def test_strips_fabricated_citation_not_in_evidence(self):
        def fake_search(query, max_results):
            return [_chunk("docs/real.md", "# Real", "The real fact is here.")]

        reason = _reason_queue([json.dumps({
            "answer": "The real fact is here (docs/real.md), also see (docs/invented.md).",
            "sufficient": True,
            "gaps": [],
        })])

        raw = agentic_retrieval.agentic_search_docs(
            {"question": "What is the real fact?", "max_rounds": 1},
            search=fake_search, reason=reason)
        data = json.loads(raw)
        self.assertIn("docs/real.md", data["answer"])
        self.assertIn("[unverified citation removed]", data["answer"])
        self.assertNotIn("docs/invented.md", data["answer"])

    def test_max_rounds_clamped(self):
        def fake_search(query, max_results):
            return [_chunk("docs/x.md", "", "text")]

        reason = _reason_queue([json.dumps({
            "answer": "ok (docs/x.md)", "sufficient": False, "gaps": ["q2"],
        })] * 10)

        raw = agentic_retrieval.agentic_search_docs(
            {"question": "q", "max_rounds": 999}, search=fake_search, reason=reason)
        data = json.loads(raw)
        # Clamped to agentic_retrieval.MAX_ROUNDS (3), not the requested 999.
        self.assertLessEqual(data["rounds_used"], agentic_retrieval.MAX_ROUNDS)



if __name__ == "__main__":
    unittest.main()
