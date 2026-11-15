#!/usr/bin/env python3
"""Audit 2026-11-02 finding 5: tool calls returned by the Mac farm never run here.
Also the stable escalation key (finding 17) and dict guards after json.loads."""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent  # noqa: E402
import farm_offload  # noqa: E402
import router  # noqa: E402


class _Route:
    def __init__(self, tier, host, model, backend="ollama"):
        self.tier, self.host, self.model, self.backend = tier, host, model, backend
        self.gpu_busy, self.reason, self.detail = False, "test route", {}

    def options(self):
        return {"num_gpu": 0, "num_ctx": 8192}

    def as_dict(self):
        return {"tier": self.tier, "host": self.host, "model": self.model,
                "backend": self.backend, "gpu_busy": self.gpu_busy, "reason": self.reason}


_RUN_CODE = {"function": {"name": "run_code", "arguments": {"code": "print('owned')"}}}


class SanitizeFarmResultTests(unittest.TestCase):
    def test_tool_calls_are_counted_and_dropped(self) -> None:
        text, dropped = agent._sanitize_farm_result({"content": "hi", "tool_calls": [_RUN_CODE, _RUN_CODE]})
        self.assertEqual(("hi", 2), (text, dropped))

    def test_non_string_content_is_empty(self) -> None:
        self.assertEqual(("", 0), agent._sanitize_farm_result({"content": {"x": 1}}))
        self.assertEqual(("", 0), agent._sanitize_farm_result({"content": None}))
        self.assertEqual(("", 0), agent._sanitize_farm_result("not a dict"))
        self.assertEqual(("", 0), agent._sanitize_farm_result({"error": "down", "content": "x"}))

    def test_text_is_capped(self) -> None:
        text, _ = agent._sanitize_farm_result({"content": "x" * (agent.FARM_TEXT_MAX_CHARS + 500)})
        self.assertEqual(agent.FARM_TEXT_MAX_CHARS, len(text))


class FarmToolCallsNeverRunTests(unittest.TestCase):
    def _run(self, farm_result, *, local_text="local answer"):
        farm_route = _Route("farm", "farm", "qwythos", backend="farm")
        cpu_route = _Route("cpu", router.CPU_HOST, "equal-shares-cpu")
        decisions: list[bool] = []
        streams: list[str] = []
        events: list[tuple[str, str]] = []

        def fake_decide(*_a, skip_farm=False, **_k):
            decisions.append(skip_farm)
            return cpu_route if skip_farm else farm_route

        def fake_stream(_msgs, model=None, **_k):
            streams.append(str(model))
            yield local_text

        tools_call = MagicMock(return_value="{}")
        with patch.object(agent.router, "decide", side_effect=fake_decide), \
             patch.object(farm_offload, "try_qwythos_on_farm", return_value=farm_result), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", tools_call):
            reply = agent.answer([{"role": "user", "content": "Where is TODO.md?"}],
                                 on_event=lambda k, p: events.append((k, p)),
                                 model=None, prefer="auto")
        return reply, tools_call, decisions, streams, events

    def test_farm_tool_calls_without_text_fall_back_to_the_local_model(self) -> None:
        reply, tools_call, decisions, streams, events = self._run(
            {"content": "", "tool_calls": [_RUN_CODE], "model": "qwythos"})
        self.assertEqual("local answer", reply)
        self.assertNotIn("run_code", [c.args[0] for c in tools_call.call_args_list])
        self.assertIn(True, decisions)              # re-decided with skip_farm=True
        self.assertEqual(["equal-shares-cpu"], streams)
        notes = [p for k, p in events if k == "note"]
        self.assertTrue(any("discarded" in n and "tool call" in n for n in notes), notes)

    def test_farm_text_is_used_but_its_tool_calls_are_discarded(self) -> None:
        reply, tools_call, _d, streams, events = self._run(
            {"content": "The TODO file is at the repo root.", "tool_calls": [_RUN_CODE]})
        self.assertEqual("The TODO file is at the repo root.", reply)
        self.assertNotIn("run_code", [c.args[0] for c in tools_call.call_args_list])
        self.assertEqual([], streams)
        self.assertTrue(any("discarded" in p for k, p in events if k == "note"))

    def test_farm_text_shaped_like_a_json_tool_call_is_not_promoted(self) -> None:
        payload = json.dumps({"name": "run_code", "arguments": {"code": "print('owned')"}})
        reply, tools_call, _d, _s, _e = self._run({"content": payload, "tool_calls": []})
        self.assertEqual(payload, reply)
        self.assertNotIn("run_code", [c.args[0] for c in tools_call.call_args_list])

    def test_non_dict_farm_result_falls_back_locally(self) -> None:
        reply, tools_call, _d, streams, _e = self._run(["not", "a", "dict"])
        self.assertEqual("local answer", reply)
        self.assertEqual(["equal-shares-cpu"], streams)


class EscalationKeyTests(unittest.TestCase):
    def test_key_is_sha256_based_and_stable(self) -> None:
        gate = MagicMock(return_value={"granted": False, "mode": "ask"})
        text = "design a compiler for a new language and compare three backends"
        with patch("difficulty.needs_escalation", return_value=True), \
             patch("gpu_gate.request", gate), \
             patch.object(agent.router, "gpu_busy", return_value=(False, "free", {})):
            for _ in range(2):
                agent._prefetch_difficulty_plan(
                    [{"role": "system", "content": "s"}], text, "cid1",
                    router.FALLBACK_REASONING_MODEL, "auto", lambda k, p: None)
        keys = [c.kwargs["key"] for c in gate.call_args_list]
        expected = "escalate:cid1:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        self.assertEqual([expected, expected], keys)


class JsonDictGuardTests(unittest.TestCase):
    def test_search_docs_label_survives_a_list_result(self) -> None:
        self.assertIsNone(agent._tool_source_label("search_docs", "[1, 2, 3]"))
        self.assertIsNone(agent._tool_source_label("search_docs", '"just a string"'))

    def test_gvd_router_questions_survive_non_dict_results(self) -> None:
        tool = next(iter(agent._GVD_ROUTER_TOOLS))
        self.assertIsNone(agent._gvd_router_questions([(tool, "[]")]))
        self.assertIsNone(agent._gvd_router_questions([(tool, "42")]))


if __name__ == "__main__":
    unittest.main()
