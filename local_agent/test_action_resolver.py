#!/usr/bin/env python3
"""Regression tests for the action-resolution layer (stdlib only, no Ollama).

Five failure scenarios the operator reported — each has a unit test for
classify() and an integration test through agent.answer(). Layer B adds
CPU/farm-only intents (web_search, capabilities, list_memory, relative
list_dir) that must not fire on the default GPU profile.

  1. "you were supposed to fix it. Why didn't you?"
  2. "continue with the PowerInfer project using the JSON I approved"
  3. start_current_chat_render with no H3 prompt set
  4. "show me the folder with the prompts"
  5. "fix the formatting error"

Run:
    python local_agent/test_action_resolver.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import action_resolver
import agent
import agentic_state
import remote_security
import tools

# A pending-path callable that always returns None (no evidence)
_NO_PATH = lambda h, c: None


def _make_route(tier="cpu", backend="ollama"):
    r = SimpleNamespace(
        tier=tier, host="127.0.0.1:11435", model="stub",
        backend=backend, detail={},
    )
    r.options = lambda: {}
    r.as_dict = lambda: {"tier": r.tier, "host": r.host, "model": r.model,
                         "backend": r.backend}
    r.reason = ""
    return r


# ── classify() unit tests ──────────────────────────────────────────────────────

class ClassifyUnitTests(unittest.TestCase):
    """Direct tests of action_resolver.classify() — no model or I/O needed."""

    # ── ComfyUI stop ──────────────────────────────────────────────────────────

    def test_stop_comfyui_exact(self):
        plan = action_resolver.classify(
            "stop comfyui", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual("comfyui_stop", plan.intent)
        self.assertEqual([("stop_all_comfyui", {})], plan.steps)

    def test_kill_render_classified_as_comfyui_stop(self):
        plan = action_resolver.classify(
            "kill render", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual("comfyui_stop", plan.intent)

    def test_stop_comfyui_specialist_scope_ignored_for_safety(self):
        # Safety action: always resolves regardless of specialist scope.
        plan = action_resolver.classify(
            "stop comfyui", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=True)
        self.assertIsNotNone(plan)
        self.assertEqual("comfyui_stop", plan.intent)

    # ── JSONL repair ──────────────────────────────────────────────────────────

    def test_fix_it_with_pending_path_classified_as_jsonl_repair(self):
        path = "powerinfer_project/tasks.jsonl"
        history = [
            {"role": "tool", "name": "validate_powerinfer_calibration",
             "content": json.dumps({"valid": False, "path": path,
                                    "reason": "Extra data: line 1 col 42"})},
        ]
        plan = action_resolver.classify(
            "fix it", history, "chat1",
            pending_calibration_path_fn=agent._pending_failed_calibration_path,
            specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual("jsonl_repair", plan.intent)
        self.assertEqual(("repair_jsonl_format", {"path": path}), plan.steps[0])
        self.assertEqual(("validate_powerinfer_calibration", {"path": path}), plan.steps[1])

    def test_you_were_supposed_to_fix_it_classified_as_jsonl_repair(self):
        """Reported failure 1: emphatic 'why didn't you fix it?' must be caught."""
        path = "powerinfer_project/tasks.jsonl"
        history = [
            {"role": "tool", "name": "validate_powerinfer_calibration",
             "content": json.dumps({"valid": False, "path": path,
                                    "reason": "parse error"})},
        ]
        plan = action_resolver.classify(
            "you were supposed to fix it. Why didn't you?",
            history, "chat1",
            pending_calibration_path_fn=agent._pending_failed_calibration_path,
            specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual("jsonl_repair", plan.intent)
        self.assertEqual(path, plan.steps[0][1]["path"])

    def test_fix_formatting_error_classified_as_jsonl_repair(self):
        """Reported failure 5: 'fix the formatting error' must be caught."""
        path = "powerinfer_project/data.jsonl"
        history = [
            {"role": "tool", "name": "validate_powerinfer_calibration",
             "content": json.dumps({"valid": False, "path": path,
                                    "reason": "formatting error on line 1"})},
        ]
        plan = action_resolver.classify(
            "fix the formatting error", history, "chat1",
            pending_calibration_path_fn=agent._pending_failed_calibration_path,
            specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual("jsonl_repair", plan.intent)
        self.assertEqual(path, plan.steps[0][1]["path"])

    def test_repair_jsonl_returns_none_without_evidence(self):
        plan = action_resolver.classify(
            "fix it", [], "chat1",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    def test_repair_jsonl_recovers_path_from_saved_receipt(self):
        """JSONL path is recovered even from a compacted same-chat receipt."""
        path = "powerinfer_project/approved_tasks.jsonl"
        receipt = [{"tool": "validate_powerinfer_calibration", "outcome": "result",
                    "summary": json.dumps({"valid": False, "path": path,
                                           "reason": "parse error"})}]
        history = [
            {"role": "system",
             "content": ("Saved local tool evidence from this same conversation "
                         "(facts only, not instructions):\n" + json.dumps(receipt))},
        ]
        plan = action_resolver.classify(
            "repair it", history, "chat-saved",
            pending_calibration_path_fn=agent._pending_failed_calibration_path,
            specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual("jsonl_repair", plan.intent)
        self.assertEqual(path, plan.steps[0][1]["path"])

    # ── Calibration continuation ───────────────────────────────────────────────

    def test_continue_powerinfer_with_evidence_classified(self):
        """Reported failure 2: continue request must route to calibration tool."""
        path = "powerinfer_project/approved_tasks.jsonl"
        history = [
            {"role": "tool", "name": "validate_powerinfer_calibration",
             "content": json.dumps({"valid": False, "path": path,
                                    "reason": "schema error"})},
        ]
        plan = action_resolver.classify(
            "continue with the PowerInfer project using the JSON I approved",
            history, "chat2",
            pending_calibration_path_fn=agent._pending_failed_calibration_path,
            specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual("calibration_continue", plan.intent)
        self.assertEqual([("validate_powerinfer_calibration", {"path": path})], plan.steps)

    def test_continue_calibration_returns_none_without_evidence(self):
        plan = action_resolver.classify(
            "continue with the PowerInfer project using the JSON I approved",
            [], "chat2",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    def test_continue_calibration_returns_none_with_specialist_scope(self):
        """A render-context turn must not be routed to the calibration validator."""
        path = "powerinfer_project/tasks.jsonl"
        plan = action_resolver.classify(
            "continue with the PowerInfer project using the JSON I approved",
            [], "chat2",
            pending_calibration_path_fn=lambda h, c: path,
            specialist_scope=True)
        self.assertIsNone(plan)

    def test_use_approved_json_with_evidence_classified(self):
        path = "calibration/pairs.jsonl"
        plan = action_resolver.classify(
            "use the approved JSON",
            [], "chat3",
            pending_calibration_path_fn=lambda h, c: path,
            specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual("calibration_continue", plan.intent)
        self.assertEqual(path, plan.steps[0][1]["path"])

    # ── List directory ─────────────────────────────────────────────────────────

    def test_show_prompts_folder_classified_as_list_dir(self):
        """Reported failure 4: 'show me the folder with the prompts' must list dir."""
        plan = action_resolver.classify(
            "show me the folder with the prompts", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual("list_dir", plan.intent)
        self.assertEqual(
            "outputs/equal_shares/prompts_native_r2v",
            plan.steps[0][1]["path"])

    def test_list_prompts_folder_alias(self):
        plan = action_resolver.classify(
            "list the prompts folder", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNotNone(plan)
        self.assertEqual("list_dir", plan.intent)
        self.assertEqual(
            "outputs/equal_shares/prompts_native_r2v",
            plan.steps[0][1]["path"])

    def test_list_dir_with_explicit_path(self):
        with tempfile.TemporaryDirectory() as td:
            plan = action_resolver.classify(
                f"list the files in {td}", [], "",
                pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
            self.assertIsNotNone(plan)
            self.assertEqual("list_dir", plan.intent)
            self.assertIn(td.replace("\\", "/")[:10],
                          plan.steps[0][1]["path"].replace("\\", "/"))

    def test_list_dir_without_path_returns_none(self):
        plan = action_resolver.classify(
            "show me the folder", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        # No explicit path, no alias matched — should not resolve
        self.assertIsNone(plan)

    # ── Read file ──────────────────────────────────────────────────────────────

    def test_read_file_with_explicit_path(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "notes.txt"
            f.write_text("hello", encoding="utf-8")
            plan = action_resolver.classify(
                f"read the file at {f}", [], "",
                pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
            self.assertIsNotNone(plan)
            self.assertEqual("read_file", plan.intent)
            self.assertIn(str(f)[:20], plan.steps[0][1]["path"])

    def test_read_file_without_path_returns_none(self):
        plan = action_resolver.classify(
            "read the file", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    # ── Non-matching inputs ───────────────────────────────────────────────────

    def test_casual_greeting_returns_none(self):
        plan = action_resolver.classify(
            "hi there", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    def test_ordinary_question_returns_none(self):
        plan = action_resolver.classify(
            "what is PowerInfer?", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    def test_start_render_returns_none(self):
        # start render is handled by agent.py's own block, not the resolver.
        plan = action_resolver.classify(
            "start render", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    def test_empty_message_returns_none(self):
        plan = action_resolver.classify(
            "", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    # ── CPU-only extras (Layer B) ─────────────────────────────────────────────

    def test_web_search_cpu_classified(self):
        plan = action_resolver.classify(
            "search the web for python dataclasses", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False,
            profile="cpu")
        self.assertIsNotNone(plan)
        self.assertEqual("web_search", plan.intent)
        self.assertEqual(
            [("web_search", {"query": "python dataclasses"})], plan.steps)

    def test_web_search_gpu_returns_none(self):
        plan = action_resolver.classify(
            "search the web for python dataclasses", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    def test_web_search_without_query_returns_none(self):
        plan = action_resolver.classify(
            "search the web", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False,
            profile="cpu")
        self.assertIsNone(plan)

    def test_web_search_with_url_returns_none(self):
        plan = action_resolver.classify(
            "search the web for https://example.com/docs", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False,
            profile="cpu")
        self.assertIsNone(plan)

    def test_capabilities_cpu_classified(self):
        plan = action_resolver.classify(
            "what tools do you have", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False,
            profile="cpu")
        self.assertIsNotNone(plan)
        self.assertEqual("capabilities", plan.intent)
        self.assertEqual([("capabilities", {})], plan.steps)

    def test_capabilities_gpu_returns_none(self):
        plan = action_resolver.classify(
            "what tools do you have", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    def test_list_memory_cpu_classified(self):
        plan = action_resolver.classify(
            "what do you remember", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False,
            profile="cpu")
        self.assertIsNotNone(plan)
        self.assertEqual("list_memory", plan.intent)
        self.assertEqual([("list_memory", {})], plan.steps)

    def test_list_memory_gpu_returns_none(self):
        plan = action_resolver.classify(
            "what do you remember", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    def test_relative_list_dir_cpu_classified(self):
        """Live 2026-09-04o miss: bare folder name on compact list_dir."""
        plan = action_resolver.classify(
            "list the files in the local_agent folder. The path is local_agent.",
            [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False,
            profile="cpu")
        self.assertIsNotNone(plan)
        self.assertEqual("list_dir", plan.intent)
        self.assertEqual([("list_dir", {"path": "local_agent"})], plan.steps)

    def test_relative_list_dir_gpu_returns_none(self):
        plan = action_resolver.classify(
            "list the files in the local_agent folder. The path is local_agent.",
            [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False)
        self.assertIsNone(plan)

    def test_cpu_profile_does_not_steal_safety_stop(self):
        plan = action_resolver.classify(
            "stop comfyui", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False,
            profile="cpu")
        self.assertIsNotNone(plan)
        self.assertEqual("comfyui_stop", plan.intent)

    def test_cpu_greeting_still_returns_none(self):
        plan = action_resolver.classify(
            "hi there", [], "",
            pending_calibration_path_fn=_NO_PATH, specialist_scope=False,
            profile="cpu")
        self.assertIsNone(plan)


# ── agent.answer() integration tests ──────────────────────────────────────────

class AgentAnswerIntegrationTests(unittest.TestCase):
    """Verify reported failure scenarios through the full agent.answer() path."""

    def test_failure1_emphatic_fix_request_calls_repair_tool(self):
        """Reported failure 1: 'you were supposed to fix it' must invoke repair."""
        path = "powerinfer_project/tasks.jsonl"
        history = [
            {"role": "tool", "name": "validate_powerinfer_calibration",
             "content": json.dumps({"valid": False, "path": path,
                                    "reason": "Extra data: line 1 col 42"})},
            {"role": "user",
             "content": "you were supposed to fix it. Why didn't you?"},
        ]
        calls = []

        def fake_call(name, args, **_kw):
            calls.append((name, args))
            if name == "repair_jsonl_format":
                return json.dumps({"repaired": True, "path": path, "records": 6})
            if name == "validate_powerinfer_calibration":
                return json.dumps({"valid": True, "path": path})
            raise AssertionError(f"unexpected tool: {name}")

        context = remote_security.ToolContext(source="desktop", conversation_id="f1test")
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for this repair")):
            reply = agent.answer(history, tool_context=context)

        self.assertEqual([("repair_jsonl_format", {"path": path}),
                          ("validate_powerinfer_calibration", {"path": path})], calls)
        self.assertIn("Repaired JSONL", reply)
        # Validation passed — the reply should confirm that
        self.assertIn("intake check passed", reply)

    def test_failure2_continue_powerinfer_calls_calibration_not_batch(self):
        """Reported failure 2: 'continue using the JSON I approved' must use validator."""
        path = "powerinfer_project/approved_tasks.jsonl"
        history = [
            {"role": "tool", "name": "validate_powerinfer_calibration",
             "content": json.dumps({"valid": False, "path": path,
                                    "reason": "pair_id must be a non-empty string"})},
            {"role": "user",
             "content": "continue with the PowerInfer project using the JSON I approved"},
        ]
        calls = []

        def fake_call(name, args, **_kw):
            calls.append((name, args))
            return json.dumps({"valid": False, "path": path,
                               "reason": "still invalid: pair_id missing"})

        context = remote_security.ToolContext(source="desktop", conversation_id="f2test")
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for calibration continue")):
            reply = agent.answer(history, tool_context=context)

        # Must have called the calibration validator, not batch tools
        self.assertIn(("validate_powerinfer_calibration", {"path": path}), calls)
        self.assertFalse(
            any(n in {"batch_plan", "batch_render", "start_batch_render"} for n, _ in calls),
            "batch tools must not be called for a calibration-continue request")
        # Reply is the raw tool result (JSON string)
        self.assertIsInstance(reply, str)

    def test_failure3_start_render_no_h3_prompts_returns_deterministic_refusal(self):
        """Reported failure 3: missing H3 prompt set must not produce model prose."""
        refusal_json = json.dumps({
            "error": "no prompts",
            "detail": "this chat has no complete fenced h3 prompt set to render",
        })
        context = remote_security.ToolContext(source="desktop", conversation_id="f3test")
        with patch.object(agent.oll, "chat_stream") as stream, \
             patch.object(agent.tools, "call", return_value=refusal_json):
            reply = agent.answer(
                [{"role": "user", "content": "start render"}],
                tool_context=context)
        stream.assert_not_called()
        self.assertIn("No render was started", reply)
        self.assertIn("no complete fenced H3 prompt", reply)

    def test_failure4_show_prompts_folder_calls_list_dir(self):
        """Reported failure 4: 'show me the folder with the prompts' must list dir."""
        calls = []

        def fake_call(name, args, **_kw):
            calls.append((name, args))
            return ("outputs/equal_shares/prompts_native_r2v\n"
                    "    prompt_00A.txt\n    prompt_00B.txt")

        with patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for list_dir")):
            reply = agent.answer([{
                "role": "user",
                "content": "show me the folder with the prompts",
            }])

        self.assertEqual(
            [("list_dir", {"path": "outputs/equal_shares/prompts_native_r2v"})],
            calls,
        )
        self.assertIn("prompts_native_r2v", reply)

    def test_failure5_fix_formatting_error_calls_repair_and_validate(self):
        """Reported failure 5: 'fix the formatting error' must invoke repair tool."""
        path = "powerinfer_project/data.jsonl"
        history = [
            {"role": "tool", "name": "validate_powerinfer_calibration",
             "content": json.dumps({"valid": False, "path": path,
                                    "reason": "formatting error on line 1"})},
            {"role": "user", "content": "fix the formatting error"},
        ]
        calls = []

        def fake_call(name, args, **_kw):
            calls.append((name, args))
            if name == "repair_jsonl_format":
                return json.dumps({"repaired": True, "path": path, "records": 5})
            return json.dumps({"valid": False, "path": path,
                               "reason": "pair_id must be a non-empty string"})

        context = remote_security.ToolContext(source="desktop", conversation_id="f5test")
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for this repair")):
            reply = agent.answer(history, tool_context=context)

        self.assertIn(("repair_jsonl_format", {"path": path}), calls)
        self.assertIn(("validate_powerinfer_calibration", {"path": path}), calls)
        self.assertIn("Repaired JSONL container formatting", reply)

    # ── Guards still active after resolver ───────────────────────────────────

    def test_resolver_does_not_bypass_protected_file_guard(self):
        """The resolver still routes through tools.call, which enforces all guards."""
        with tempfile.TemporaryDirectory() as td:
            # A path that happens to match a read_file request but
            # is a normal file — tools.read_file should handle it.
            f = Path(td) / "safe.txt"
            f.write_text("ok content", encoding="utf-8")
            calls = []

            def fake_call(name, args, **_kw):
                calls.append((name, args))
                return "ok content"

            with patch.object(agent.tools, "call", fake_call), \
                 patch.object(agent.oll, "chat_stream",
                               side_effect=AssertionError("model should not run")):
                reply = agent.answer([{
                    "role": "user",
                    "content": f"read the file at {f}",
                }])
            self.assertIn(("read_file", {"path": str(f)}), calls)

    def test_ordinary_question_still_uses_model(self):
        """Resolver must return None for ordinary questions, leaving model in charge."""
        import ollama_client as oll

        def fake_stream(_messages, **_kwargs):
            yield "PowerInfer is a sparse inference engine."

        with patch.object(agent.router, "decide", return_value=_make_route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer([{
                "role": "user",
                "content": "what is PowerInfer?",
            }])
        self.assertEqual("PowerInfer is a sparse inference engine.", reply)

    def test_cpu_web_search_calls_tool_not_model(self):
        calls = []

        def fake_call(name, args, **_kw):
            calls.append((name, args))
            return "[duckduckgo] python dataclasses\n1. docs.python.org"

        with patch.object(agent.router, "decide", return_value=_make_route()), \
             patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for cpu web_search")):
            reply = agent.answer([{
                "role": "user",
                "content": "search the web for python dataclasses",
            }])
        self.assertEqual([("web_search", {"query": "python dataclasses"})], calls)
        self.assertIn("python dataclasses", reply)

    def test_cpu_capabilities_calls_tool_not_model(self):
        calls = []

        def fake_call(name, args, **_kw):
            calls.append((name, args))
            return '{"see_image": true, "transcribe": true}'

        with patch.object(agent.router, "decide", return_value=_make_route()), \
             patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for cpu capabilities")):
            reply = agent.answer([{
                "role": "user",
                "content": "what tools do you have",
            }])
        self.assertEqual([("capabilities", {})], calls)
        self.assertIn("see_image", reply)

    def test_cpu_list_memory_calls_tool_not_model(self):
        calls = []

        def fake_call(name, args, **_kw):
            calls.append((name, args))
            return "[Source: persistent memory]\n[]"

        with patch.object(agent.router, "decide", return_value=_make_route()), \
             patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for cpu list_memory")):
            reply = agent.answer([{
                "role": "user",
                "content": "what do you remember",
            }])
        self.assertEqual([("list_memory", {})], calls)
        self.assertIn("persistent memory", reply)

    def test_cpu_relative_list_dir_calls_tool_not_model(self):
        calls = []

        def fake_call(name, args, **_kw):
            calls.append((name, args))
            return "local_agent\n    action_resolver.py\n    tools.py"

        with patch.object(agent.router, "decide", return_value=_make_route()), \
             patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for cpu relative list_dir")):
            reply = agent.answer([{
                "role": "user",
                "content": ("Using the available tools, list the files in the "
                            "local_agent folder. The path is local_agent."),
            }])
        self.assertEqual([("list_dir", {"path": "local_agent"})], calls)
        self.assertIn("action_resolver.py", reply)

    def test_gpu_web_search_still_uses_model(self):
        """GPU free-form must not gain the CPU-only web_search regex."""

        def fake_stream(_messages, **_kwargs):
            yield "I will search for that."

        with patch.object(agent.router, "decide",
                          return_value=_make_route(tier="gpu")), \
             patch.object(agent.tools, "call",
                          side_effect=AssertionError("gpu web_search must not short-circuit")), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer([{
                "role": "user",
                "content": "search the web for python dataclasses",
            }])
        self.assertEqual("I will search for that.", reply)


if __name__ == "__main__":
    unittest.main(verbosity=2)
