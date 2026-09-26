#!/usr/bin/env python3
"""Regression checks for the bounded agentic task harness (stdlib only)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import agentic_state
import ollama_client as oll
import remote_security


class _Route:
    tier, host, model = "cpu", "127.0.0.1:11435", "stub-model"
    def options(self): return {}
    def as_dict(self): return {"tier": self.tier, "host": self.host, "model": self.model}


class AgenticStateTests(unittest.TestCase):
    def test_checkpoint_is_bounded_and_records_observations(self):
        with tempfile.TemporaryDirectory() as td, patch.object(agentic_state, "DIR", Path(td)):
            state = agentic_state.begin_turn(
                "taskchat1",
                "Inspect the current configuration; compare the two model routes; "
                "verify the safeguards; then report the exact result.")
            self.assertEqual("active", state["status"])
            self.assertGreaterEqual(len(state["plan"]), 2)
            agentic_state.observe_tool("taskchat1", "search_docs", {"query": "routing"},
                                        "A" * 2000)
            restored = agentic_state.load("taskchat1")
            self.assertEqual("working", restored["plan"][0]["status"])
            self.assertLessEqual(len(restored["observations"][0]["summary"]), 521)
            self.assertIn("search_docs", agentic_state.prompt_block("taskchat1"))

    def test_failed_tool_blocks_instead_of_claiming_success(self):
        with tempfile.TemporaryDirectory() as td, patch.object(agentic_state, "DIR", Path(td)):
            agentic_state.begin_turn("taskchat2", "Inspect the project; verify the result; report it.")
            agentic_state.observe_tool("taskchat2", "read_doc", {}, "ERROR: protected file")
            state = agentic_state.load("taskchat2")
            self.assertEqual("blocked", state["status"])
            self.assertEqual("blocked", state["plan"][0]["status"])

    def test_checkpoint_retains_exact_failed_tool_path_for_followup(self):
        with tempfile.TemporaryDirectory() as td, patch.object(agentic_state, "DIR", Path(td)):
            agentic_state.begin_turn(
                "taskpath1",
                "Inspect the calibration JSONL, validate its schema, repair its formatting if needed, "
                "then verify the repaired file and report the result.")
            source = r"powerinfer_project\approved_tasks.jsonl"
            agentic_state.observe_tool("taskpath1", "validate_powerinfer_calibration",
                                       {"path": source}, json.dumps({
                                           "valid": False, "path": source,
                                           "reason": "Extra data"}))
            block = agentic_state.prompt_block("taskpath1")
            self.assertIn(source, block)
            self.assertIn("Exact active file paths", block)

    def test_substantive_followup_replans_instead_of_erasing_same_task(self):
        with tempfile.TemporaryDirectory() as td, patch.object(agentic_state, "DIR", Path(td)):
            agentic_state.begin_turn(
                "taskchatfollow",
                "Inspect the routing configuration; verify the fallback safeguards; report findings.")
            agentic_state.observe_tool("taskchatfollow", "search_docs", {"query": "routing"},
                                        "routing evidence")
            state = agentic_state.begin_turn(
                "taskchatfollow",
                "Continue by verifying the routing fallback behavior and report the evidence.")
            self.assertEqual("active", state["status"])
            self.assertEqual("search_docs", state["observations"][0]["tool"])
            self.assertEqual(1, len(state.get("updates", [])))

    def test_planner_cannot_replace_operator_task_goal(self):
        """A checklist proposal must never rewrite the active task identity."""
        with tempfile.TemporaryDirectory() as td, patch.object(agentic_state, "DIR", Path(td)):
            original = (
                "Inspect the approved PowerInfer calibration JSON; verify its schema and "
                "approval evidence; then report the safe non-GPU next step for the project.")
            agentic_state.begin_turn("taskchatgoal", original)
            saved = agentic_state.apply_proposed_plan("taskchatgoal", {
                "goal": "Recover a video render after a missing H3 prompt set",
                "steps": [
                    {"title": "Inspect the approved calibration input",
                     "success_condition": "The source is identified"},
                    {"title": "Report the validation evidence",
                     "success_condition": "The result is documented"},
                ],
                "needs_operator_decision": False,
            })
            self.assertEqual(original, saved["goal"])
            self.assertEqual("structured_local_model", saved["plan_source"])

    def test_unrelated_short_request_supersedes_instead_of_leaking_checkpoint(self):
        with tempfile.TemporaryDirectory() as td, patch.object(agentic_state, "DIR", Path(td)):
            agentic_state.begin_turn(
                "taskchatscope",
                "Verify phone rendering permissions; inspect the remote grant; then report the result.")
            fresh = agentic_state.begin_turn("taskchatscope", "Describe this attached image.")
            saved = agentic_state.load("taskchatscope")
            self.assertIsNone(fresh)
            self.assertEqual("superseded", saved["status"])
            self.assertEqual("Describe this attached image.", saved["superseded_by"])
            self.assertFalse(agentic_state.prompt_block("taskchatscope"))

    def test_retrieve_decision_is_limited_to_documentation_questions(self):
        self.assertIsNone(agentic_state.retrieval_query("write a short story about a river"))
        self.assertIsNotNone(agentic_state.retrieval_query(
            "According to current project documentation, why is the routing policy configured this way?"))

    def test_context_trimming_preserves_task_checkpoint_system_message(self):
        messages = [
            {"role": "system", "content": "base policy"},
            {"role": "system", "content": "Trusted task checkpoint"},
            {"role": "user", "content": "A" * 12000},
            {"role": "assistant", "content": "old"},
            {"role": "user", "content": "current request"},
        ]
        compacted = agent._trim_context(messages, 1200, [], lambda *_: None)
        self.assertEqual(["base policy", "Trusted task checkpoint"],
                         [message["content"] for message in compacted[:2]])

    def test_answer_reuses_checkpoint_and_records_native_tool_result(self):
        turns = iter([
            [oll.ToolCall([{"function": {"name": "search_docs",
                                            "arguments": {"query": "routing"}}}])],
            ["The routing rule was checked against the project documentation."],
        ])
        seen = []

        def fake_stream(messages, **_kwargs):
            seen.append(json.loads(json.dumps(messages)))
            yield from next(turns)

        request = ("Inspect the routing documentation, verify the current fallback "
                   "logic, and report the result with evidence.")
        context = remote_security.ToolContext(source="desktop", conversation_id="taskchat3")
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.planner, "propose", return_value=(None, "test planner unavailable")), \
             patch.object(agent.tools, "call", return_value='{"results": ["routing"]}'):
            reply = agent.answer([{"role": "user", "content": request}], tool_context=context)
            state = agentic_state.load("taskchat3")
        self.assertIn("routing rule", reply)
        self.assertTrue(any(message.get("content", "").startswith("Trusted task checkpoint")
                            for message in seen[0]))
        self.assertTrue(any(message.get("role") == "tool" and message.get("name") == "search_docs"
                            for message in seen[1]))
        self.assertEqual("search_docs", state["observations"][0]["tool"])

    def test_document_question_prefetches_filtered_evidence(self):
        seen_calls = []
        context = remote_security.ToolContext(source="desktop", conversation_id="taskchatdocs")

        def fake_call(name, args, **_kwargs):
            seen_calls.append((name, args))
            return json.dumps({"query": args["query"], "results": [{
                "source": "docs/routing.md", "heading": "# Routing",
                "text": "GPU work routes to the fallback safely."}]})

        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", return_value=iter(["The docs establish it."])), \
            patch.object(agent.planner, "propose", return_value=(None, "test planner unavailable")), \
            patch.object(agent.tools, "call", fake_call):
            reply = agent.answer([{"role": "user", "content":
                                  "According to the Equal Shares current documentation, why is the routing policy set this way?"}],
                                 tool_context=context)
        self.assertEqual("The docs establish it.", reply)
        self.assertEqual("search_docs", seen_calls[0][0])

    def test_new_complex_task_accepts_only_validated_structured_plan(self):
        context = remote_security.ToolContext(source="desktop", conversation_id="taskchatplan")
        proposal = {
            "goal": "Check routing", "source": "structured_local_model",
            "needs_operator_decision": False,
            "steps": [
                {"title": "Inspect routing evidence", "success_condition": "Evidence is available"},
                {"title": "Verify fallback safeguards", "success_condition": "Result is reported"},
            ],
        }
        request = "Inspect routing evidence, verify fallback safeguards, and report the supported result."
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(agent.router, "up", return_value=True), \
             patch.object(agent.oll, "chat_stream", return_value=iter(["Checked."])), \
             patch.object(agent.planner, "propose", return_value=(proposal, "structured plan accepted")):
            reply = agent.answer([{"role": "user", "content": request}], tool_context=context)
            state = agentic_state.load("taskchatplan")
        self.assertEqual("Checked.", reply)
        self.assertEqual("structured_local_model", state["plan_source"])
        self.assertEqual("Inspect routing evidence", state["plan"][0]["title"])

    def test_busy_gpu_skips_optional_planner_without_a_timeout_note(self):
        context = remote_security.ToolContext(source="desktop", conversation_id="taskchatbusy")
        events = []
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.router, "gpu_busy", return_value=(True, "ComfyUI busy", {})), \
             patch.object(agent.oll, "chat_stream", return_value=iter(["Answered on CPU."])), \
             patch.object(agent.planner, "propose") as propose:
            reply = agent.answer([{"role": "user", "content": "Compare these two results."}],
                                 tool_context=context,
                                 on_event=lambda kind, value: events.append((kind, value)))
        self.assertEqual("Answered on CPU.", reply)
        propose.assert_not_called()
        self.assertFalse(any("task plan kept deterministic" in value for _kind, value in events))
        progress = [value for kind, value in events if kind == "progress"]
        self.assertTrue(progress, "operator-facing work trace was not emitted")
        self.assertTrue(any("Reviewing the request" in value for value in progress),
                        "work trace did not identify the review stage")

    def test_non_render_turn_gets_scope_boundary_not_old_render_checkpoint(self):
        seen = []
        requests = []
        context = remote_security.ToolContext(source="phone", conversation_id="taskchatscopeagent")
        request = "Describe this attached image."

        def fake_stream(messages, **_kwargs):
            requests.append(messages)
            yield "It is an image."

        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            agentic_state.begin_turn(
                "taskchatscopeagent",
                "Verify phone rendering permissions; inspect the remote grant; then report the result.")
            reply = agent.answer([{"role": "user", "content": request}], tool_context=context,
                                 on_event=lambda kind, value: seen.append((kind, value)))
        self.assertEqual("It is an image.", reply)
        # The new direct request must have ended the stale checkpoint.
        self.assertFalse(any("task plan prepared" in value for kind, value in seen if kind == "note"))
        system_text = "\n".join(message.get("content", "") for message in requests[0]
                                if message.get("role") == "system")
        self.assertIn("Scope boundary for this turn", system_text)
        self.assertNotIn("Trusted task checkpoint", system_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
