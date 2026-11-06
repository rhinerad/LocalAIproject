#!/usr/bin/env python3
"""Repeatable harness evaluation for local-agent reasoning infrastructure.

This is not a benchmark of world knowledge or a claim of hosted-model parity.
It verifies the observable machinery around a model: tool selection transport,
retrieval evidence, plan persistence, failure recovery, and remote denial. All
model calls are mocked so running it never loads a model or starts a render.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import agentic_state
import ollama_client as oll
import remote_security
import tools


class _Route:
    tier, host, model = "cpu", "127.0.0.1:11435", "eval-stub"
    def options(self): return {}
    def as_dict(self): return {"tier": self.tier, "host": self.host, "model": self.model}


def _run(name: str, fn) -> dict:
    try:
        fn()
        return {"name": name, "passed": True}
    except Exception as exc:  # Evaluation must report every failure, not abort early.
        return {"name": name, "passed": False, "error": f"{type(exc).__name__}: {exc}"}


def evaluate() -> dict:
    results: list[dict] = []

    def multi_tool_one_hop():
        turns = iter([
            [oll.ToolCall([
                {"function": {"name": "duration_ladder", "arguments": {"clip": "00B"}}},
                {"function": {"name": "duration_ladder", "arguments": {"clip": "00A"}}},
            ])], ["Both ladders are available."]])
        events = []
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", side_effect=lambda *_a, **_k: iter(next(turns))):
            reply = agent.answer([{"role": "user", "content": "compare 00B and 00A ladders"}],
                                 on_event=lambda kind, value: events.append((kind, value)))
        assert reply == "Both ladders are available."
        assert sum(kind == "tool" for kind, _ in events) == 2

    def docs_are_prefetched():
        context = remote_security.ToolContext(source="desktop", conversation_id="evaldocs1")
        seen: list[str] = []
        def fake_call(name, args, **_kwargs):
            seen.append(name)
            return json.dumps({"results": [{"source": "docs/policy.md", "heading": "# Policy",
                                               "text": "Current routing policy is documented."}]})
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.router, "decide", return_value=_Route()), \
            patch.object(agent.oll, "chat_stream", return_value=iter(["The documentation establishes it."])), \
            patch.object(agent.tools, "call", fake_call):
            agent.answer([{"role": "user", "content":
                          "According to the Equal Shares current documentation, why is this routing policy used?"}],
                         tool_context=context, prefer="cpu")
        assert seen == ["search_docs"]

    def plan_and_followup_survive():
        with tempfile.TemporaryDirectory() as td, patch.object(agentic_state, "DIR", Path(td)):
            first = agentic_state.begin_turn(
                "evalplan1", "Inspect the routing evidence; verify fallback safeguards; report results.")
            assert first and first.get("_new_task")
            agentic_state.observe_tool("evalplan1", "search_docs", {"query": "routing"}, "evidence")
            second = agentic_state.begin_turn("evalplan1", "Continue with the routing verification.")
            assert second and second["observations"][-1]["tool"] == "search_docs"

    def failed_observation_blocks():
        with tempfile.TemporaryDirectory() as td, patch.object(agentic_state, "DIR", Path(td)):
            agentic_state.begin_turn("evalfail1", "Inspect the project; verify safeguards; report the result.")
            agentic_state.observe_tool("evalfail1", "read_doc", {}, "ERROR: unavailable")
            assert agentic_state.load("evalfail1")["status"] == "blocked"

    def remote_render_remains_denied():
        outcome = tools.call("start_batch_render", {"folder": "C:/not-a-job"},
                             context=remote_security.ToolContext(source="phone"))
        assert "not permitted" in outcome

    for name, fn in [
        ("native multi-tool call executes both calls in one hop", multi_tool_one_hop),
        ("documentation question receives source-labelled retrieval", docs_are_prefetched),
        ("same-task follow-up retains plan evidence", plan_and_followup_survive),
        ("failed observation becomes blocked", failed_observation_blocks),
        ("remote render remains default-deny", remote_render_remains_denied),
    ]:
        results.append(_run(name, fn))
    return {
        "suite": "agentic_harness_baseline",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_calls": "mocked; no model loaded",
        "passed": sum(1 for result in results if result["passed"]),
        "total": len(results),
        "results": results,
    }


def main() -> int:
    report = evaluate()
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
