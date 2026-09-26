#!/usr/bin/env python3
"""Regression checks for Ollama native function calling (stdlib only)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import agentic_state
import capabilities
import chat_render_jobs
import chat_retrieval
import file_edit_gate
import gpu_gate
import ollama_client
import ollama_client as oll
import remote_security
import router
import store
import tools


class _Route:
    def __init__(self, tier="cpu", host="127.0.0.1:11435", model="stub-model",
                 backend="ollama"):
        self.tier = tier
        self.host = host
        self.model = model
        self.backend = backend
        self.detail = {}
        self.reason = ""
        self.gpu_busy = False

    def options(self):
        return {}

    def as_dict(self):
        return {"tier": self.tier, "host": self.host, "model": self.model,
                "backend": self.backend}


class NativeToolTests(unittest.TestCase):

    def setUp(self):
        # Agent-answer tests can exercise the real gateway branch.  Keep their
        # synthetic approval requests out of the operator's live sidebar state.
        self._gate_dir = tempfile.TemporaryDirectory()
        self._old_gate_file = gpu_gate.STATE_FILE
        gpu_gate.STATE_FILE = Path(self._gate_dir.name) / "gpu_gate.json"
        self._old_file_edit_gate = file_edit_gate.STATE_FILE
        file_edit_gate.STATE_FILE = Path(self._gate_dir.name) / "file_edit_gate.json"
        os.environ["LOCAL_AGENT_TRACING"] = "0"

    def tearDown(self):
        gpu_gate.STATE_FILE = self._old_gate_file
        file_edit_gate.STATE_FILE = self._old_file_edit_gate
        self._gate_dir.cleanup()

    def test_thinking_markup_is_never_visible(self):
        stream = ollama_client._VisibleTextFilter()
        self.assertEqual("", stream.feed("<thi"))
        self.assertEqual("", stream.feed("nk>private"))
        self.assertEqual("", stream.feed(" reasoning</th"))
        self.assertEqual("Answer", stream.feed("ink> Answer"))

        dangling = ollama_client._VisibleTextFilter()
        self.assertEqual("", dangling.feed("internal preamble</think>"))
        self.assertEqual("Visible", dangling.feed(" Visible").strip())
        self.assertEqual("Clean", ollama_client._visible_text("<think>x</think> Clean"))

    def test_chat_stream_sends_think_false(self):
        sent = {}

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def __iter__(self):
                return iter([
                    (json.dumps({"message": {"content": "hi"}, "done": True}) + "\n").encode(),
                ])

        def fake_urlopen(req, timeout=None):
            sent["payload"] = json.loads(req.data.decode())
            return _Resp()

        with patch.object(oll.urllib.request, "urlopen", fake_urlopen):
            pieces = list(oll.chat_stream(
                [], model="stub", think=False, host="127.0.0.1:11435"))
        self.assertEqual(2, len(pieces))
        self.assertEqual("hi", pieces[0])
        self.assertIsInstance(pieces[1], oll.StreamEnd)
        self.assertIs(False, sent["payload"]["think"])

    def test_chat_stream_logs_thinking_length_when_content_empty(self):
        thinking = "n" * 200
        logged = []

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def __iter__(self):
                return iter([
                    (json.dumps({"message": {"content": "", "thinking": thinking}})
                     + "\n").encode(),
                    (json.dumps({"message": {"content": ""}, "done": True}) + "\n").encode(),
                ])

        def fake_urlopen(_req, timeout=None):
            return _Resp()

        with patch.object(oll.urllib.request, "urlopen", fake_urlopen), \
             patch.object(oll, "_log_empty_thinking",
                          lambda n, **kw: logged.append((n, kw))):
            pieces = list(oll.chat_stream(
                [], model="stub-8b", think=False, host="127.0.0.1:11435"))
        self.assertEqual(1, len(pieces))
        self.assertIsInstance(pieces[0], oll.StreamEnd)
        self.assertEqual(200, pieces[0].thinking_chars)
        self.assertEqual(0, pieces[0].visible_chars)
        self.assertEqual(
            [(200, {"think": False, "model": "stub-8b", "unclosed_think_chars": 0})],
            logged)

    def test_plain_text_chat_never_starts_vision_runtime(self):
        # A normal chat may route to a reasoning model, but VLM ownership is
        # reserved for explicit media jobs. This is mocked so it never loads
        # either type of model during regression.
        with patch.object(agent.router, "gpu_busy", return_value=(True, "test", {})), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", return_value=iter(["Plain response."])), \
             patch.object(capabilities, "ensure_qwen25_vl_runtime") as ensure:
            reply = agent.answer([{"role": "user", "content": "Explain a concept plainly."}],
                                 prefer="cpu")
        self.assertEqual("Plain response.", reply)
        ensure.assert_not_called()

    def test_stream_end_is_not_stored_as_text(self):
        events = []
        trailer = oll.StreamEnd(
            {"eval_count": 12, "prompt_eval_count": 34,
             "total_duration": 1, "eval_duration": 1},
            thinking_chars=0, visible_chars=5,
        )

        def fake_stream(*_a, **_kw):
            yield "Hello"
            yield trailer

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(
                [{"role": "user", "content": "hi"}],
                lambda k, p: events.append((k, p)))
        self.assertEqual("Hello", reply)
        self.assertNotIn("StreamEnd", reply)
        token_payloads = [p for k, p in events if k == "token"]
        self.assertEqual(["Hello"], token_payloads)
        self.assertFalse(any("StreamEnd" in str(p) for k, p in events))
    def test_all_schemas_and_enums(self):
        schemas = tools.schemas()
        self.assertEqual(len(tools.TOOLS), len(schemas))
        by_name = {}
        for item in schemas:
            self.assertEqual("function", item["type"])
            fn = item["function"]
            by_name[fn["name"]] = fn
            self.assertIsInstance(fn["description"], str)
            self.assertTrue(fn["description"])
            params = fn["parameters"]
            self.assertEqual("object", params["type"])
            self.assertIsInstance(params["properties"], dict)
            self.assertTrue(set(params.get("required", ())) <= set(params["properties"]))
        self.assertEqual(set(tools.TOOLS), set(by_name))
        self.assertEqual(sorted(tools.BUILD),
                         by_name["run_build"]["parameters"]["properties"]["action"]["enum"])
        self.assertEqual(sorted(tools.GPU),
                         by_name["propose_gpu"]["parameters"]["properties"]["action"]["enum"])
        self.assertEqual(
            ["proven_facts", "golden_reference", "prompt_rules", "runbook",
             "claude_md", "agent_questions"],
            by_name["read_doc"]["parameters"]["properties"]["name"]["enum"])
        general_names = {item["function"]["name"]
                         for item in tools.schemas(include_project=False)}
        self.assertIn("validate_powerinfer_calibration", general_names)

    def test_powerinfer_calibration_intake_is_cpu_only_and_does_not_unlock_work(self):
        path = (HERE.parent / "review-only" / "turbosparse-mistral-projected-abliteration" /
                "operator-source-safe-subset.UNAPPROVED.jsonl")
        result = json.loads(tools.call("validate_powerinfer_calibration", {"path": str(path)}))
        self.assertFalse(result["valid"])
        self.assertIn("No model, predictor, GPU, render, or registry action ran.",
                      result["next_step"])

    def test_repair_jsonl_format_converts_only_a_top_level_object_array(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "input.jsonl"
            target.write_text(json.dumps([{"task": "one"}, {"task": "two"}]), encoding="utf-8")
            with patch.object(tools, "ROOT", root):
                result = json.loads(tools.call("repair_jsonl_format", {"path": str(target)}))
            self.assertTrue(result["repaired"])
            self.assertTrue(result["file_changed"])
            self.assertFalse(result["approval_changed"])
            self.assertEqual([{"task": "one"}, {"task": "two"}],
                             [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()])

    def test_chat_passes_tools(self):
        sent = {}

        def fake_post(path, payload, **_kwargs):
            sent.update(payload)
            return {"message": {"content": "", "tool_calls": [
                {"function": {"name": "project_state", "arguments": {}}}
            ]}}

        schemas = tools.schemas()
        with patch.object(oll, "_post", fake_post):
            text, calls = oll.chat([], model="stub", tools=schemas)
        self.assertEqual("", text)
        self.assertEqual("project_state", calls[0]["function"]["name"])
        self.assertIs(sent["tools"], schemas)

    def test_chat_passes_explicit_keep_alive(self):
        sent = {}

        def fake_post(_path, payload, **_kwargs):
            sent.update(payload)
            return {"message": {"content": "ok"}}

        with patch.object(oll, "_post", fake_post):
            text, _ = oll.chat([], model="stub", keep_alive="5m")
        self.assertEqual("ok", text)
        self.assertEqual("5m", sent["keep_alive"])

    def test_chat_passes_json_schema_format(self):
        sent = {}
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

        def fake_post(_path, payload, **_kwargs):
            sent.update(payload)
            return {"message": {"content": '{"ok":true}'}}

        with patch.object(oll, "_post", fake_post):
            text, calls = oll.chat([], model="stub", response_format=schema)
        self.assertEqual('{"ok":true}', text)
        self.assertEqual([], calls)
        self.assertIs(schema, sent["format"])

    def test_multiple_calls_one_hop_and_named_results(self):
        seen_messages = []
        events = []
        turns = iter([
            [oll.ToolCall([
                {"function": {"name": "duration_ladder", "arguments": {"clip": "00B"}}},
                {"function": {"name": "duration_ladder", "arguments": {"clip": "00A"}}},
            ])],
            ["Both ladders were compared."],
        ])

        def fake_stream(messages, **kwargs):
            self.assertEqual(len(tools.TOOLS), len(kwargs["tools"]))
            seen_messages.append(json.loads(json.dumps(messages)))
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route(tier="gpu")), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer([{"role": "user", "content":
                                  "Compare the Equal Shares ladders for 00B and 00A"}],
                                 lambda k, p: events.append((k, p)))
        self.assertEqual("Both ladders were compared.", reply)
        self.assertEqual(2, sum(k == "tool" for k, _ in events))
        tool_msgs = [m for m in seen_messages[1] if m["role"] == "tool"]
        self.assertEqual(["duration_ladder", "duration_ladder"],
                         [m["name"] for m in tool_msgs])
        self.assertTrue(all(m["content"].startswith("[") for m in tool_msgs))

    def test_sse_hop_index_on_json_kinds_across_hops(self):
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {
                "name": "duration_ladder", "arguments": {"clip": "00B"}}}])],
            [oll.ToolCall([{"function": {
                "name": "duration_ladder", "arguments": {"clip": "00A"}}}])],
            ["Compared both clips."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(
                [{"role": "user", "content": "compare 00B and 00A ladders"}],
                lambda k, p: events.append((k, p)))
        self.assertEqual("Compared both clips.", reply)

        json_hops = []
        for kind, payload in events:
            if kind in agent._JSON_SSE_KINDS:
                obj = json.loads(payload)
                self.assertIn("hop", obj)
                json_hops.append(obj["hop"])
            elif kind in ("tool_result", "note", "token"):
                if payload.lstrip().startswith("{"):
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(obj, dict):
                        self.assertNotIn("hop", obj, kind)

        self.assertIn(0, json_hops)
        self.assertIn(1, json_hops)
        seen_one = False
        for hop in json_hops:
            if hop == 1:
                seen_one = True
            elif seen_one:
                self.assertGreaterEqual(hop, 1)
        tool_hops = [
            json.loads(p)["hop"] for k, p in events if k == "tool"
        ]
        self.assertEqual([0, 1], tool_hops)

    def test_early_return_tool_sse_has_hop_null(self):
        events = []
        plan = agent.action_resolver.ActionPlan(
            intent="list_dir", steps=[("list_dir", {"path": "."})])

        with patch.object(agent.action_resolver, "classify", return_value=plan), \
             patch.object(agent.tools, "call", return_value=".\n    file.txt"), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("hop loop must not run")):
            reply = agent.answer(
                [{"role": "user", "content": "list the files here"}],
                lambda k, p: events.append((k, p)))
        self.assertIn("file.txt", reply)
        tool_payload = json.loads(next(p for k, p in events if k == "tool"))
        self.assertEqual("list_dir", tool_payload["tool"])
        self.assertIsNone(tool_payload["hop"])
        result = next(p for k, p in events if k == "tool_result")
        self.assertTrue(result.startswith("."))
        self.assertNotIn('"hop"', result)

    def test_concurrency_safe_tools_run_in_parallel_within_one_hop(self):
        call_times = {}
        lock = threading.Lock()

        def slow_call(name, args, context=None):
            start = time.monotonic()
            time.sleep(0.3)
            with lock:
                call_times[name] = (start, time.monotonic())
            return f"ok:{name}"

        turns = iter([
            [oll.ToolCall([
                {"function": {"name": "web_search", "arguments": {"query": "a"}}},
                {"function": {"name": "fetch_url", "arguments": {"url": "http://x"}}},
            ])],
            ["Done."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=slow_call):
            t0 = time.monotonic()
            reply = agent.answer([{"role": "user", "content": "search two things"}])
            elapsed = time.monotonic() - t0

        self.assertEqual("Done.", reply)
        self.assertEqual({"web_search", "fetch_url"}, set(call_times))
        starts = [s for s, _ in call_times.values()]
        ends = [e for _, e in call_times.values()]
        # Parallelism is the overlap of the two 0.3s tool bodies, not the
        # wall-clock of answer(). answer() also pays GPU telemetry, prefetch,
        # and prompt assembly; that overhead has been measured at 0.09–1.6s
        # here and is what made `elapsed < 0.55` flake (0.56–1.92s) while
        # the tools still overlapped in a ~0.30s window. Sequential
        # execution would make this window >= 0.6s. Observed concurrent
        # window is 0.296–0.313s; 0.45 leaves ~140ms of thread-start jitter
        # without accepting a serialized hop.
        self.assertGreater(min(ends), max(starts), "the two calls did not overlap")
        self.assertLess(max(ends) - min(starts), 0.45)
        self.assertLess(elapsed, 5.0, "answer() hung; parallel-hop itself is bounded above")

    def test_read_only_followup_reuses_one_gpu_snapshot(self):
        """A read-only hop must not pay a second slow GPU telemetry probe."""
        gpu_checks = 0

        def fake_gpu_busy():
            nonlocal gpu_checks
            gpu_checks += 1
            return True, "test busy", {}

        turns = iter([
            [oll.ToolCall([{"function": {"name": "web_search",
                                            "arguments": {"query": "a"}}}])],
            ["Done."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "gpu_busy", side_effect=fake_gpu_busy), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value="read-only evidence"):
            self.assertEqual("Done.", agent.answer([
                {"role": "user", "content": "search for a thing"}]))

        self.assertEqual(1, gpu_checks)

    def test_ad_hoc_turn_never_searches_prior_chats_without_identity(self):
        """Cross-chat recall needs a durable conversation boundary."""
        with patch.object(chat_retrieval, "search") as search:
            msgs: list[dict] = []
            agent._prefetch_prior_chat_context(
                msgs, "find a file", "", False, lambda _kind, _value: None)
        search.assert_not_called()

    def test_unsafe_tool_stays_sequential_even_alongside_a_safe_one(self):
        order = []

        def mixed_call(name, args, context=None):
            if name == "write_file":
                order.append("write_file_start")
                time.sleep(0.05)
                order.append("write_file_end")
                return "wrote it"
            time.sleep(0.2)
            return f"ok:{name}"

        turns = iter([
            [oll.ToolCall([
                {"function": {"name": "web_search", "arguments": {"query": "a"}}},
                {"function": {"name": "write_file", "arguments": {"path": "x.txt", "content": "y"}}},
            ])],
            ["Both done."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=mixed_call):
            reply = agent.answer([{"role": "user", "content": "search and write"}])

        self.assertEqual("Both done.", reply)
        # write_file must run start-to-finish without another call's work
        # interleaved mid-way — proof it never entered the thread pool.
        self.assertEqual(["write_file_start", "write_file_end"], order)

    def test_main_thread_tool_exception_in_mixed_hop_is_caught_not_raised(self):
        """Unsafe-tool raise on the main thread converts to ERROR string, not a crash.

        When a hop mixes safe (pooled) and unsafe (main-thread) tools, a
        RuntimeError from the unsafe call must be caught with the same
        try/except that wraps fut.result() for pooled calls — not allowed to
        propagate out of answer() and bypass the terminal-guard logic.
        """
        seen_tool_msgs: list[dict] = []

        def mixed_call(name, args, context=None):
            if name == "write_file":
                raise RuntimeError("injected failure")
            return "ok:safe"

        turns = iter([
            [oll.ToolCall([
                {"function": {"name": "web_search", "arguments": {"query": "a"}}},
                {"function": {"name": "write_file", "arguments": {"path": "x.txt", "content": "y"}}},
            ])],
            ["Recovered."],
        ])

        def fake_stream(messages, **_kwargs):
            for m in messages:
                if m.get("role") == "tool":
                    seen_tool_msgs.append(m)
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=mixed_call):
            reply = agent.answer([{"role": "user", "content": "search and write"}])

        self.assertEqual("Recovered.", reply)  # answer() returned, did not raise
        write_results = [m["content"] for m in seen_tool_msgs if m.get("name") == "write_file"]
        self.assertEqual(1, len(write_results))
        self.assertIn("ERROR", write_results[0])
        self.assertIn("RuntimeError", write_results[0])
        self.assertIn("injected failure", write_results[0])

    def test_main_thread_tool_exception_in_single_tool_hop_is_caught_not_raised(self):
        """Unsafe single-tool raise converts to ERROR string, not a crash.

        The sequential else-branch (all tools unsafe, or only one tool total)
        had the same unguarded run_one() call as the mixed-hop main-thread path.
        The write_file error guard intercepts the ERROR result and returns a
        canned message containing the exception detail — answer() returns
        instead of raising, and the exception text appears in the reply.
        """
        def raising_call(name, args, context=None):
            raise RuntimeError("injected failure")

        turns = iter([
            [oll.ToolCall([
                {"function": {"name": "write_file", "arguments": {"path": "x.txt", "content": "y"}}},
            ])],
        ])

        def fake_stream(messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=raising_call):
            reply = agent.answer([{"role": "user", "content": "write a file"}])

        # answer() returned (did not raise) — the exception was caught and
        # converted to an ERROR string; the write_file guard then interpolated
        # the exception detail into the canned message it returned.
        self.assertIn("No file was created or changed", reply)
        self.assertIn("RuntimeError", reply)
        self.assertIn("injected failure", reply)

    def test_execute_plan_tool_exception_is_caught_not_raised(self):
        """Action-resolver sequential tools.call raise converts to ERROR, not a crash.

        _execute_plan is the hop-loop sibling: it runs tools.call in a plain
        for-loop inside answer() with no try/except. A RuntimeError from
        list_dir must become an ERROR string reply so finish_turn can run.
        """
        def raising_call(name, args, context=None):
            raise RuntimeError("injected failure")

        with patch.object(agent.tools, "call", side_effect=raising_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for list_dir")):
            reply = agent.answer([{
                "role": "user",
                "content": r"list the files in the folder C:\Users\rhine\tmp\notes",
            }])

        self.assertIn("ERROR", reply)
        self.assertIn("RuntimeError", reply)
        self.assertIn("injected failure", reply)

    def test_execute_plan_second_step_still_runs_after_first_raises(self):
        """JSONL-repair two-step plan keeps going after a first-step raise.

        Matching the hop-loop sequential branch: one tool's exception becomes
        an ERROR result and later steps still run. The existing repair-summary
        guard then interpolates the exception into the canned reply.
        """
        path = "powerinfer_project/data.jsonl"
        history = [
            {"role": "tool", "name": "validate_powerinfer_calibration",
             "content": json.dumps({"valid": False, "path": path,
                                    "reason": "formatting error on line 1"})},
            {"role": "user", "content": "fix the formatting error"},
        ]
        calls = []

        def fake_call(name, args, context=None):
            calls.append(name)
            if name == "repair_jsonl_format":
                raise RuntimeError("injected failure")
            return json.dumps({"valid": False, "path": path,
                               "reason": "still invalid"})

        context = remote_security.ToolContext(source="desktop", conversation_id="exc-jsonl")
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.tools, "call", side_effect=fake_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for this repair")):
            reply = agent.answer(history, tool_context=context)

        self.assertEqual(["repair_jsonl_format", "validate_powerinfer_calibration"], calls)
        self.assertIn("No file was changed", reply)
        self.assertIn("RuntimeError", reply)
        self.assertIn("injected failure", reply)

    def test_execute_plan_prompt_pack_stops_after_failed_ingest(self):
        """Prompt-pack plans must not export the old source after ingest fails."""
        plan = agent.action_resolver.ActionPlan(
            intent="prompt_pack_ingest_export",
            steps=[("ingest_prompt_pack", {"text": "pack"}),
                   ("export_prompt_pack_outputs", {"export_all": True, "chunk_size": 24})])
        calls = []

        def fake_call(name, args, context=None):
            calls.append(name)
            if name == "ingest_prompt_pack":
                raise RuntimeError("injected ingest failure")
            return json.dumps({"exported_count": 99})

        with tempfile.TemporaryDirectory() as td,              patch.object(agentic_state, "DIR", Path(td)),              patch.object(agent.tools, "call", side_effect=fake_call):
            reply = agent._execute_plan(plan, "pp-ingest-fail", None, lambda k, p: None)

        self.assertEqual(["ingest_prompt_pack"], calls)
        self.assertIn("injected ingest failure", reply)

    def test_url_prefetch_tool_exception_is_caught_not_raised(self):
        """Pre-hop fetch_url/list_memory raise converts to ERROR; the model still runs."""
        events: list[tuple[str, str]] = []

        def raising_call(name, args, context=None):
            raise RuntimeError("injected failure")

        def fake_stream(_messages, **_kwargs):
            yield "Recovered."

        def on_event(kind, payload):
            events.append((kind, payload))

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=raising_call):
            reply = agent.answer([{
                "role": "user",
                "content": "Look at https://example.com/page and check persistent memory",
            }], on_event=on_event)

        self.assertEqual("Recovered.", reply)
        tool_results = [payload for kind, payload in events if kind == "tool_result"]
        self.assertGreaterEqual(len(tool_results), 2)
        joined = "\n".join(tool_results)
        self.assertIn("ERROR", joined)
        self.assertIn("RuntimeError", joined)
        self.assertIn("injected failure", joined)

    def test_start_current_chat_render_shortcut_exception_is_caught_not_raised(self):
        """Deterministic start-render shortcut converts a tools.call raise to ERROR."""
        def raising_call(name, args, context=None):
            raise RuntimeError("injected failure")

        context = remote_security.ToolContext(source="desktop", conversation_id="exc-render")
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.tools, "call", side_effect=raising_call), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("model must not run for start render")):
            reply = agent.answer(
                [{"role": "user", "content": "start render"}],
                tool_context=context)

        self.assertIn("ERROR", reply)
        self.assertIn("RuntimeError", reply)
        self.assertIn("injected failure", reply)

    def test_sonic_pi_ensure_exception_is_caught_not_raised(self):
        """ensure_sonic_pi raise converts to ERROR; the hop-loop still runs."""
        def raising_call(name, args, context=None):
            if name == "ensure_sonic_pi":
                raise RuntimeError("injected failure")
            return "ok"

        events: list[tuple[str, str]] = []

        def fake_stream(_messages, **_kwargs):
            yield "Recovered."

        def on_event(kind, payload):
            events.append((kind, payload))

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=raising_call):
            reply = agent.answer([{
                "role": "user",
                "content": "play a note in sonic pi",
            }], on_event=on_event)

        self.assertEqual("Recovered.", reply)
        tool_results = [payload for kind, payload in events if kind == "tool_result"]
        self.assertTrue(any("ERROR" in p and "RuntimeError" in p
                            and "injected failure" in p for p in tool_results))

    def test_parallel_tool_results_keep_original_call_order_in_the_transcript(self):
        seen_messages = []
        durations = iter([0.2, 0.01])  # first is slower but must still appear first

        def variable_call(name, args, context=None):
            time.sleep(next(durations))
            return f"result_for:{name}:{args.get('query')}"

        turns = iter([
            [oll.ToolCall([
                {"function": {"name": "web_search", "arguments": {"query": "first"}}},
                {"function": {"name": "web_search", "arguments": {"query": "second"}}},
            ])],
            ["ok"],
        ])

        def fake_stream(messages, **_kwargs):
            seen_messages.append(json.loads(json.dumps(messages)))
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=variable_call):
            agent.answer([{"role": "user", "content": "two searches"}])

        tool_msgs = [m for m in seen_messages[1] if m["role"] == "tool"]
        self.assertEqual(["result_for:web_search:first", "result_for:web_search:second"],
                         [m["content"] for m in tool_msgs])

    def test_oversized_tool_result_is_an_artifact_pointer_in_next_hop(self):
        seen_messages = []
        turns = iter([
            [oll.ToolCall([{"function": {"name": "project_state", "arguments": {}}}])],
            ["Reviewed the stored result."],
        ])

        def fake_stream(messages, **_kwargs):
            seen_messages.append(json.loads(json.dumps(messages)))
            yield from next(turns)

        with tempfile.TemporaryDirectory() as td, \
             patch.object(agent.artifacts, "ARTIFACT_DIR", Path(td)), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value="X" * 3000):
            self.assertEqual("Reviewed the stored result.", agent.answer([
                {"role": "user", "content": "show state"}]))
        tool_message = next(m for m in seen_messages[1] if m["role"] == "tool")
        self.assertIn("output pruned; artifact_id=", tool_message["content"])
        self.assertLessEqual(len(tool_message["content"]), agent.MAX_TOOL_RESULT_CONTEXT_CHARS)

    def test_read_artifact_default_slice_stays_in_next_hop_not_pruned(self):
        """Escape-hatch JSON is larger than the prune budget; it must not
        become another pointer (2026-09-05dj matryoshka loop)."""
        seen_messages = []
        original = "HEADING-LINE\n" + ("abcdefghij" * 800)  # 13 + 8000
        hops = {"n": 0}

        def fake_stream(messages, **_kwargs):
            seen_messages.append(json.loads(json.dumps(messages)))
            hops["n"] += 1
            if hops["n"] == 1:
                yield oll.ToolCall([{
                    "function": {
                        "name": "read_artifact",
                        "arguments": {"artifact_id": artifact_id},
                    },
                }])
            else:
                yield "The heading is HEADING-LINE."

        with tempfile.TemporaryDirectory() as td, \
             patch.object(agent.artifacts, "ARTIFACT_DIR", Path(td)), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            artifact_id = agent.artifacts.store("tool:read_file", original)
            reply = agent.answer([{"role": "user", "content": "read the stored slice"}])
            kinds = [
                json.loads(path.read_text(encoding="utf8"))["kind"]
                for path in Path(td).glob("*.json")
            ]

        self.assertEqual("The heading is HEADING-LINE.", reply)
        self.assertEqual(2, hops["n"])
        tool_message = next(m for m in seen_messages[1] if m["role"] == "tool")
        self.assertEqual("read_artifact", tool_message.get("name"))
        self.assertNotIn("output pruned", tool_message["content"])
        self.assertGreater(len(tool_message["content"]), agent.MAX_TOOL_RESULT_CONTEXT_CHARS)
        payload = json.loads(tool_message["content"])
        self.assertEqual(artifact_id, payload["artifact_id"])
        self.assertEqual("tool:read_file", payload["kind"])
        self.assertEqual(4000, payload["length"])
        self.assertEqual(original[:4000], payload["text"])
        self.assertTrue(payload["more_remaining"])
        self.assertEqual(4000, payload["next_offset"])
        self.assertNotIn("tool:read_artifact", kinds)
        self.assertEqual(["tool:read_file"], kinds)

    def test_read_artifact_follow_up_page_uses_next_offset_not_wrapper_id(self):
        """After an unpruned first page, paging must keep the original id
        and offset=next_offset — not a new wrapper artifact."""
        seen_messages = []
        recorded_calls = []
        original = "".join(f"{i:04d}" for i in range(2500))  # 10000 chars
        hops = {"n": 0}

        def fake_stream(messages, **_kwargs):
            seen_messages.append(json.loads(json.dumps(messages)))
            hops["n"] += 1
            if hops["n"] == 1:
                yield oll.ToolCall([{
                    "function": {
                        "name": "read_artifact",
                        "arguments": {"artifact_id": artifact_id},
                    },
                }])
                return
            if hops["n"] == 2:
                first = json.loads(next(
                    m["content"] for m in messages if m.get("role") == "tool"))
                yield oll.ToolCall([{
                    "function": {
                        "name": "read_artifact",
                        "arguments": {
                            "artifact_id": first["artifact_id"],
                            "offset": first["next_offset"],
                            "length": 4000,
                        },
                    },
                }])
                return
            yield "Paged the rest of the original."

        real_call = agent.tools.call

        def spy_call(name, args, context=None, **kwargs):
            recorded_calls.append((name, dict(args or {})))
            return real_call(name, args, context=context, **kwargs)

        with tempfile.TemporaryDirectory() as td, \
             patch.object(agent.artifacts, "ARTIFACT_DIR", Path(td)), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", spy_call):
            artifact_id = agent.artifacts.store("tool:read_file", original)
            reply = agent.answer([{"role": "user", "content": "page through the artifact"}])
            kinds = [
                json.loads(path.read_text(encoding="utf8"))["kind"]
                for path in Path(td).glob("*.json")
            ]

        self.assertEqual("Paged the rest of the original.", reply)
        self.assertEqual(3, hops["n"])
        self.assertEqual(2, len(recorded_calls))
        self.assertEqual("read_artifact", recorded_calls[0][0])
        self.assertEqual(artifact_id, recorded_calls[0][1]["artifact_id"])
        self.assertEqual("read_artifact", recorded_calls[1][0])
        self.assertEqual(artifact_id, recorded_calls[1][1]["artifact_id"])
        self.assertEqual(4000, recorded_calls[1][1]["offset"])
        page1 = json.loads(next(m["content"] for m in seen_messages[1]
                                if m.get("role") == "tool"))
        page2 = json.loads([m["content"] for m in seen_messages[2]
                            if m.get("role") == "tool"][-1])
        self.assertEqual(original[:4000], page1["text"])
        self.assertEqual(4000, page1["next_offset"])
        self.assertEqual(original[4000:8000], page2["text"])
        self.assertEqual(artifact_id, page2["artifact_id"])
        self.assertNotIn("output pruned", page1["text"])
        self.assertFalse(page2["text"].lstrip().startswith("{"))
        self.assertEqual(["tool:read_file"], kinds)

    def test_repeated_identical_failing_tool_call_stops_the_loop_early(self):
        # Stuck-loop guard: the same tool + same arguments failing
        # REPEATED_FAILURE_LIMIT times in a row must end the turn instead of
        # burning the remaining hops on a call that cannot succeed without a
        # change the model isn't making.
        call_count = 0

        def fake_stream(_messages, **_kwargs):
            nonlocal call_count
            call_count += 1
            yield oll.ToolCall([{"function": {"name": "duration_ladder",
                                              "arguments": {"clip": "00B"}}}])

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value="ERROR: clip 00B not found"):
            reply = agent.answer([{"role": "user", "content": "check 00B"}])

        self.assertIn("Stopped:", reply)
        self.assertIn("duration_ladder", reply)
        self.assertEqual(agent.REPEATED_FAILURE_LIMIT, call_count)

    def test_failing_tool_call_with_varying_arguments_is_not_treated_as_stuck(self):
        clips = iter(["00A", "00B", "00C", "00D", "00E", "00F", "00G"])

        def fake_stream(_messages, **_kwargs):
            yield oll.ToolCall([{"function": {"name": "duration_ladder",
                                              "arguments": {"clip": next(clips)}}}])

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value="ERROR: not found"):
            reply = agent.answer([{"role": "user", "content": "check several clips"}])

        self.assertNotIn("Stopped:", reply)

    def test_varying_exception_args_sig_hits_max_tool_hops_instead_of_hanging(self):
        """Unique raise + unique args_sig dodges the stuck guard; hop limit must stop it.

        After the main-thread exception fix, a raise becomes an ERROR string and
        the hop loop continues. If arguments also change every hop, the
        repeated-failure guard (same name + same args_sig, REPEATED_FAILURE_LIMIT
        times) cannot fire. MAX_TOOL_HOPS is the backstop that has to terminate
        the turn cleanly rather than hanging.
        """
        model_turns = 0
        tool_calls = 0
        notes: list[str] = []

        def fake_stream(_messages, **_kwargs):
            nonlocal model_turns
            model_turns += 1
            yield oll.ToolCall([{
                "function": {
                    "name": "web_search",
                    "arguments": {"query": f"q{model_turns}"},
                }
            }])

        def raising_call(name, args, context=None):
            nonlocal tool_calls
            tool_calls += 1
            raise RuntimeError(f"injected failure #{tool_calls}")

        def on_event(kind, payload=""):
            if kind == "note":
                notes.append(str(payload))

        started = time.monotonic()
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=raising_call):
            reply = agent.answer(
                [{"role": "user", "content": "search several things"}],
                on_event=on_event,
            )
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 5.0, "hop loop hung instead of hitting MAX_TOOL_HOPS")
        self.assertNotIn("Stopped:", reply)
        self.assertEqual(agent.MAX_TOOL_HOPS + 1, model_turns)
        self.assertEqual(agent.MAX_TOOL_HOPS, tool_calls)
        self.assertTrue(
            any("hop limit" in n for n in notes),
            notes,
        )

    def test_failing_tool_call_that_then_succeeds_is_not_treated_as_stuck(self):
        # Two identical failures followed by a real success (a transient
        # failure recovering) must not trip a guard tuned for three-in-a-row.
        outcomes = iter(["ERROR: transient", "ERROR: transient", "ok now"])
        hops = 0

        def fake_stream(_messages, **_kwargs):
            nonlocal hops
            hops += 1
            if hops <= 3:
                yield oll.ToolCall([{"function": {"name": "duration_ladder",
                                                  "arguments": {"clip": "00B"}}}])
            else:
                yield "Done."

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=lambda *_a, **_k: next(outcomes)):
            reply = agent.answer([{"role": "user", "content": "check 00B"}])

        self.assertNotIn("Stopped:", reply)

    def test_read_artifact_pages_through_a_pruned_tool_result(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agent.artifacts, "ARTIFACT_DIR", Path(td)):
            artifact_id = agent.artifacts.store("test:kind", "0123456789" * 500)

            first = json.loads(tools.call("read_artifact",
                                          {"artifact_id": artifact_id, "offset": 0, "length": 10}))
            self.assertEqual("0123456789", first["text"])
            self.assertTrue(first["more_remaining"])
            self.assertEqual(10, first["next_offset"])

            last = json.loads(tools.call("read_artifact",
                                         {"artifact_id": artifact_id, "offset": 4990, "length": 100}))
            self.assertFalse(last["more_remaining"])
            self.assertIsNone(last["next_offset"])

            self.assertTrue(tools.call("read_artifact",
                                       {"artifact_id": "not-a-real-id"}).startswith("ERROR:"))
            self.assertTrue(tools.call("read_artifact",
                                       {"artifact_id": "artifact_0000000000000000"}
                                       ).startswith("ERROR:"))
            self.assertTrue(tools.call("read_artifact",
                                       {"artifact_id": artifact_id, "offset": 999999}
                                       ).startswith("ERROR:"))
            self.assertTrue(tools.call("read_artifact",
                                       {"artifact_id": artifact_id, "length": 999999}
                                       ).startswith("ERROR:"))

    def test_plan_story_image_hallucinated_completion_is_corrected(self):
        # Reproduces a real reported failure: plan_story_image returns its
        # plan-only ("gpu_action": "none") result, and the model then told
        # the operator the image had been generated and was ready — a
        # passive-voice completion claim about the object, not caught by
        # _UNVERIFIED_EXECUTION_RE (which only matches first-person "I
        # generated..." phrasing).
        plan_result = json.dumps({
            "planned": True, "story": "night_greenhouse_poison_ivy_catwoman",
            "gpu_action": "none",
            "output_tree": "outputs/stories/night_greenhouse_poison_ivy_catwoman/",
        })
        turns = iter([
            [oll.ToolCall([{"function": {"name": "plan_story_image",
                                          "arguments": {"story": "night_greenhouse_poison_ivy_catwoman"}}}])],
            ["The image of the two adult women has been generated and is stored "
             "locally. It is fully rendered as described and ready for use."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value=plan_result):
            reply = agent.answer([{"role": "user", "content": "make me a photoreal image"}])

        self.assertIn("No image was actually generated", reply)
        self.assertIn("night_greenhouse_poison_ivy_catwoman", reply)
        self.assertIn("outputs/stories/night_greenhouse_poison_ivy_catwoman/", reply)
        self.assertNotIn("ready for use", reply)

    def test_real_completion_claim_after_a_genuine_write_is_not_touched(self):
        # Negative control: this narrow guard must not fire on an unrelated,
        # accurate completion claim following a real, successful tool call.
        turns = iter([
            [oll.ToolCall([{"function": {"name": "write_file",
                                          "arguments": {"path": "x.txt", "content": "y"}}}])],
            ["The file has been created at x.txt."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value="wrote 2 bytes to x.txt"):
            reply = agent.answer([{"role": "user", "content": "write a file"}])

        self.assertEqual("The file has been created at x.txt.", reply)

    def test_first_person_completion_claim_after_a_genuine_write_is_not_touched(self):
        # Regression: the unverified-execution guard matched first-person
        # completion phrasing ("I've created...") on ANY hop with no tool
        # call, even when an earlier hop in the same turn had a real,
        # successful tool result backing that exact claim. That discarded an
        # honest, accurate summary and replaced it with the generic "No
        # verified local action was performed" message. Unlike the sibling
        # negative control above (which uses passive voice and so never
        # reaches the guard at all), this uses the first-person phrasing a
        # real agent reply actually uses, so it exercises the guard's
        # recent_tool_attempts check directly. The guard must only fire when
        # nothing was actually attempted this turn.
        turns = iter([
            [oll.ToolCall([{"function": {"name": "write_file",
                                          "arguments": {"path": "x.txt", "content": "y"}}}])],
            ["I've created the file at x.txt successfully. "
             "The second and third steps are still pending."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value="wrote 2 bytes to x.txt"):
            reply = agent.answer([{"role": "user", "content": "write the files"}])

        self.assertEqual(
            "I've created the file at x.txt successfully. "
            "The second and third steps are still pending.", reply)
        self.assertNotIn("No verified local action was performed", reply)

    def test_fabricated_qa_selected_claim_after_batch_render_is_corrected(self):
        # Regression, live 2026-09-24: render_story_image_batch genuinely
        # rendered a still and left it in pending_review (never approved --
        # the model never called approve_story_stills). The model's own next
        # reply then fabricated an entire QA-pipeline narrative on top of
        # that real render ("the QA process confirmed... now marked as
        # SELECTED"). "SELECTED"/QA-pass is video-clip-pipeline vocabulary
        # that does not exist for stills at all; stills approval is a human
        # decision only. This must be caught and corrected even though a
        # real tool call (the render) did happen this turn -- the guard is
        # about this SPECIFIC unverified claim, not "was any tool called".
        turns = iter([
            [oll.ToolCall([{"function": {"name": "render_story_image_batch",
                                          "arguments": {"jobs": [{"story": "backrooms",
                                                                   "prompt": "fall and arrival"}]}}}])],
            ["The second image, which corresponds to the \"Fall & Arrival\" scene, has "
             "also been processed through the QA pipeline. The QA process confirmed that "
             "the image meets all the required standards. The image is now marked as "
             "SELECTED and is ready to be used in the chained pipeline for subsequent clips."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        batch_result = json.dumps({
            "batch": True, "total": 1, "completed_count": 1, "failure_count": 0,
            "pending_count": 0,
            "completed": [{"story": "backrooms", "outputs": [{"filename": "c015.png"}]}],
            "review": {"pending_review": True, "story": "backrooms"},
        })

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value=batch_result):
            reply = agent.answer([{"role": "user", "content": "render the fall and arrival still"}])

        self.assertIn("have not been reviewed or approved", reply)
        self.assertNotIn("now marked as SELECTED", reply)
        self.assertNotIn("QA process confirmed", reply)

    def test_true_approval_claim_after_real_operator_approval_is_not_touched(self):
        # Negative control: once approve_story_stills has actually run (which
        # itself requires a real operator-approval phrase -- enforced
        # separately in run_one()), a completion claim must NOT be corrected.
        #
        # 2026-09-25: until now this test's history was the single message
        # "looks good, approved", which opens no specialist scope, so
        # approve_story_stills was *refused* by the stale-scope guard, the
        # tool never ran, and the retry's free text "The stills are now
        # approved" was returned over that ERROR evidence -- the exact
        # fabrication shape of live chat 149209bf6e4b42ce.  The fixed reply
        # now replaces such narration, which exposed this.  The stills must
        # have been presented for approval in this chat first, and the
        # tool must be seen to run, for the control to be a control.
        history = [
            {"role": "user", "content": "render the fall and arrival still"},
            {"role": "assistant",
             "content": "The images for 'backrooms' are ready for your review. "
                        "Would you like to approve them so video rendering can proceed?",
             "tool_evidence": [{"tool": "render_story_image_batch", "outcome": "result",
                                "summary": '{"batch": true, "completed_count": 1, '
                                           '"review": {"pending_review": true}}'}]},
            {"role": "user", "content": "looks good, approved"},
        ]
        self.assertTrue(agent._pending_specialist_continuation(history))
        turns = iter([
            [oll.ToolCall([{"function": {"name": "approve_story_stills",
                                          "arguments": {"operator_confirmed": True}}}])],
            ["The stills are now approved and video rendering can proceed."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        events = []
        with patch.object(agent.router, "decide", return_value=_Route()),              patch.object(agent.oll, "chat_stream", fake_stream),              patch.object(agent.tools, "call",
                          return_value=json.dumps({"approved": True, "story": "backrooms"})) as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_called()
        self.assertEqual("approve_story_stills", call.call_args.args[0])
        self.assertFalse(any(k == "tool_result" and "stale specialist-project" in p
                             for k, p in events))
        self.assertEqual("The stills are now approved and video rendering can proceed.", reply)

    def _followup_reply_with_pending_stills(self, model_reply: str, qa: dict | None) -> str:
        # The operator's actual failure shape: the render happened in an
        # earlier turn; this follow-up turn ("what did the QA process say?")
        # makes no tool call at all, so only the persisted review state knows
        # the stills are pending.
        still = {"story": "backrooms", "outputs": [{"filename": "scene1.png"}]}
        if qa is not None:
            still["qa"] = qa
        context = remote_security.ToolContext(source="desktop", conversation_id="stills-followup")

        def fake_stream(_messages, **_kwargs):
            yield model_reply

        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td) / "state"), \
             patch.object(agent.tools, "_STORY_STILLS_REVIEW_DIR", Path(td) / "review"), \
             patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=AssertionError("no tool this turn")):
            agent.tools.present_story_stills_for_review({
                "story": "backrooms", "stills": [still],
                "__conversation_id": "stills-followup"})
            return agent.answer([{"role": "user", "content": "ok status? What did the QA process say?"}],
                                tool_context=context)

    def test_followup_turn_fabricated_qa_is_corrected_with_the_recorded_verdict(self):
        reply = self._followup_reply_with_pending_stills(
            "The QA process confirmed that the image meets all the required standards. "
            "The image is now marked as SELECTED.",
            {"verdict": "fail", "ok": False,
             "reject_reasons": ["expected_actor_visible_but_no_face_detected"]})
        self.assertIn("have not been reviewed or approved", reply)
        self.assertIn("still 1: FAIL (expected_actor_visible_but_no_face_detected)", reply)
        self.assertIn("does not verify that the scene or environment matches", reply)
        self.assertNotIn("QA process confirmed", reply)

    def test_followup_turn_without_any_recorded_qa_says_so(self):
        # Stills presented before QA was wired in carry no qa record.
        reply = self._followup_reply_with_pending_stills(
            "The frame passed all visual, audio, and boundary checks.", None)
        self.assertIn("No automated QA verdict has been recorded", reply)
        self.assertNotIn("passed all visual", reply)

    def test_truthful_report_of_recorded_qa_pass_is_not_touched(self):
        honest = ("Automated QA check passed for the still (no reject reasons); "
                  "it is waiting for your review.")
        reply = self._followup_reply_with_pending_stills(
            honest, {"verdict": "pass", "ok": True, "reject_reasons": []})
        self.assertEqual(honest, reply)

    def test_action_request_retries_once_for_tool_use_before_returning_instructions(self):
        turns = iter([
            ["Run the local validator from a terminal."],
            [oll.ToolCall([{"function": {"name": "validate_powerinfer_calibration",
                                            "arguments": {"path": "review-only/input.jsonl"}}}])],
            ["Validated the supplied JSONL. No model or GPU work ran."],
        ])
        seen = []

        def fake_stream(messages, **_kwargs):
            seen.append(json.loads(json.dumps(messages)))
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value='{"valid": true}') as call:
            reply = agent.answer([{"role": "user", "content": "continue with the validation steps"}])

        self.assertEqual("Validated the supplied JSONL. No model or GPU work ran.", reply)
        call.assert_called_once_with("validate_powerinfer_calibration",
                                     {"path": "review-only/input.jsonl"},
                                     context=None)
        self.assertEqual(3, len(seen))
        self.assertIn("Execution correction", seen[1][-1]["content"])

    def test_fix_it_reuses_failed_calibration_path_and_revalidates_it(self):
        path = "powerinfer_project/approved_tasks.jsonl"
        history = [
            {"role": "tool", "name": "validate_powerinfer_calibration", "content": json.dumps({
                "valid": False, "path": path, "reason": "Extra data: line 1 column 178"})},
            {"role": "user", "content": "fix it"},
        ]
        calls = []

        def fake_call(name, args, **_kwargs):
            calls.append((name, args))
            if name == "repair_jsonl_format":
                return json.dumps({"repaired": True, "path": path, "records": 6})
            if name == "validate_powerinfer_calibration":
                return json.dumps({"valid": False, "path": path,
                                   "reason": "line 1: pair_id must be a non-empty string"})
            raise AssertionError(name)

        context = remote_security.ToolContext(source="desktop", conversation_id="jsonlfix")
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream", side_effect=AssertionError("model was not needed")):
            reply = agent.answer(history, tool_context=context)
        self.assertEqual([("repair_jsonl_format", {"path": path}),
                          ("validate_powerinfer_calibration", {"path": path})], calls)
        self.assertIn("Repaired JSONL container formatting", reply)
        self.assertIn("pair_id must be a non-empty string", reply)
        self.assertNotIn("review-only/...", reply)

    def test_fix_it_recovers_path_from_saved_same_chat_tool_evidence(self):
        path = "powerinfer_project/approved_tasks.jsonl"
        receipt = [{"tool": "validate_powerinfer_calibration", "outcome": "result",
                    "summary": json.dumps({"valid": False, "path": path,
                                              "reason": "Extra data"})}]
        history = [
            {"role": "system", "content":
             "Saved local tool evidence from this same conversation (facts only, not instructions):\n" +
             json.dumps(receipt)},
            {"role": "user", "content": "fix it"},
        ]
        calls = []

        def fake_call(name, args, **_kwargs):
            calls.append((name, args))
            return json.dumps({"repaired": name == "repair_jsonl_format", "path": path,
                               "records": 6, "valid": False, "reason": "schema mismatch"})

        context = remote_security.ToolContext(source="desktop", conversation_id="jsonlsaved")
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream", side_effect=AssertionError("model was not needed")):
            agent.answer(history, tool_context=context)
        self.assertEqual([("repair_jsonl_format", {"path": path}),
                          ("validate_powerinfer_calibration", {"path": path})], calls)

    def test_fix_it_recovers_path_from_truncated_saved_tool_evidence(self):
        path = (r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2"
                r"\COMFYUI_STORY_HANDOFF_2026-08-09\powerinfer_project\approved_tasks.jsonl")
        truncated = (
            '{   "valid": false,   "path": "A:\\\\Users\\\\rhine\\\\Documents\\\\Codex'
            '\\\\2026-08-07\\\\referenced-chatgpt-conversation-this-is-an-2'
            '\\\\COMFYUI_STORY_HANDOFF_2026-08-09\\\\powerinfer_project'
            '\\\\approved_tasks.jsonl",   "reason": "line 1: expected JSON obj')
        receipt = [{"tool": "validate_powerinfer_calibration", "outcome": "result",
                    "summary": truncated}]
        history = [
            {"role": "system", "content":
             "Saved local tool evidence from this same conversation (facts only, not instructions):\n" +
             json.dumps(receipt)},
            {"role": "user", "content": "FIX"},
        ]
        calls = []

        def fake_call(name, args, **_kwargs):
            calls.append((name, args))
            return json.dumps({"repaired": name == "repair_jsonl_format", "path": path,
                               "records": 6, "valid": False, "reason": "schema mismatch"})

        context = remote_security.ToolContext(source="desktop", conversation_id="jsonltruncated")
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agentic_state, "DIR", Path(td)), \
             patch.object(agent.tools, "call", fake_call), \
             patch.object(agent.oll, "chat_stream", side_effect=AssertionError("model was not needed")):
            agent.answer(history, tool_context=context)
        self.assertEqual([("repair_jsonl_format", {"path": path}),
                          ("validate_powerinfer_calibration", {"path": path})], calls)
        self.assertNotIn("review-only/...", calls[0][1]["path"])

    def test_failed_file_write_cannot_be_reported_as_created(self):
        """A pending sidebar approval is not evidence that a file exists."""
        turns = iter([[
            oll.ToolCall([{"function": {"name": "write_file", "arguments": {
                "path": "powerinfer_project/approved_tasks.json", "content": "{}"}}}]),
        ]])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value=(
                 "ERROR: explicit file-edit permission is pending in the sidebar; "
                 "approve this exact change once, then retry")):
            reply = agent.answer([{"role": "user", "content": "save this file"}])

        self.assertIn("No file was created or changed", reply)
        self.assertIn("file edit failed", reply)
        self.assertNotIn("has been written", reply)

    def test_explicit_chat_text_edit_does_not_need_second_sidebar_approval(self):
        with tempfile.TemporaryDirectory() as td, \
             patch.object(file_edit_gate, "request") as approval:
            target = Path(td) / "agent_settings.json"
            result = tools.call("write_file", {"path": str(target), "content": "{}"})
            self.assertIn("created", result)
            self.assertEqual("{}", target.read_text(encoding="utf-8"))
        approval.assert_not_called()

    def test_render_story_image_hallucinated_completion_before_job_finishes_is_corrected(self):
        # render_story_image only launches a background job; "started": true
        # is not "done". The same passive-voice hallucination the plan-only
        # guard above catches can happen here too, before the render is real.
        launch_result = json.dumps({
            "started": True, "pid": 4242, "story": "night_greenhouse",
            "log": "work/runtime/agent_image_jobs/night_greenhouse_x.log",
        })
        turns = iter([
            [oll.ToolCall([{"function": {"name": "render_story_image",
                                          "arguments": {"story": "night_greenhouse", "prompt": "..."}}}])],
            ["The image has been generated and is ready for use."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value=launch_result):
            reply = agent.answer([{"role": "user", "content": "make me a photoreal image"}])

        self.assertIn("story_image_job_status", reply)
        self.assertIn("night_greenhouse", reply)
        self.assertNotIn("ready for use", reply)

    def test_story_image_job_status_still_running_hallucination_is_corrected(self):
        status_result = json.dumps({"state": "running", "story": "night_greenhouse"})
        turns = iter([
            [oll.ToolCall([{"function": {"name": "story_image_job_status",
                                          "arguments": {"story": "night_greenhouse", "pid": 4242}}}])],
            ["The image is ready and has been saved."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value=status_result):
            reply = agent.answer([{"role": "user", "content": "is it done yet?"}])

        self.assertIn("story_image_job_status", reply)
        self.assertNotIn("has been saved", reply)

    def test_story_image_job_status_complete_is_not_touched(self):
        # Negative control: once the job genuinely completed, this guard
        # must not fire on the model's next-turn completion claim.
        status_result = json.dumps({"state": "complete", "story": "night_greenhouse",
                                    "manifest": {"status": "complete"}})
        turns = iter([
            [oll.ToolCall([{"function": {"name": "story_image_job_status",
                                          "arguments": {"story": "night_greenhouse", "pid": 4242}}}])],
            ["The image has been generated and is ready."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value=status_result):
            reply = agent.answer([{"role": "user", "content": "is it done yet?"}])

        self.assertEqual("The image has been generated and is ready.", reply)

    def _content_json_schemas(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_code",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "language": {"type": "string"},
                            "code": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"],
                    },
                },
            },
        ]

    def test_fenced_json_promoted(self):
        text = (
            "```json\n"
            '{"name": "run_code", "arguments": {"language": "python", '
            '"code": "print(1)"}}\n'
            "```"
        )
        self.assertEqual(
            ("run_code", {"language": "python", "code": "print(1)"}),
            agent.parse_content_json_tool(text, self._content_json_schemas()),
        )

    def test_bare_json_promoted(self):
        text = (
            '{"name": "run_code", "arguments": {"language": "python", '
            '"code": "print(1)"}}'
        )
        self.assertEqual(
            ("run_code", {"language": "python", "code": "print(1)"}),
            agent.parse_content_json_tool(text, self._content_json_schemas()),
        )

    def test_parameters_alias_promoted(self):
        text = '{"name": "read_file", "parameters": {"path": "README.md"}}'
        self.assertEqual(
            ("read_file", {"path": "README.md"}),
            agent.parse_content_json_tool(text, self._content_json_schemas()),
        )

    def test_json_in_prose_correctly_rejected(self):
        schemas = self._content_json_schemas()
        prose = (
            "I will call run_code like this:\n"
            '{"name": "run_code", "arguments": {"language": "python", '
            '"code": "print(1)"}}\n'
            "and then cite stderr."
        )
        self.assertIsNone(agent.parse_content_json_tool(prose, schemas))
        fenced_plus = (
            "Here is the call:\n"
            "```json\n"
            '{"name": "run_code", "arguments": {"language": "python", '
            '"code": "print(1)"}}\n'
            "```\n"
            "After that I will explain."
        )
        self.assertIsNone(agent.parse_content_json_tool(fenced_plus, schemas))
        code_blob = (
            "def demo():\n"
            '    payload = {"name": "run_code", "arguments": '
            '{"language": "python", "code": "print(1)"}}\n'
            "    return payload\n"
        )
        self.assertIsNone(agent.parse_content_json_tool(code_blob, schemas))

    def test_malformed_json_correctly_ignored(self):
        schemas = self._content_json_schemas()
        self.assertIsNone(agent.parse_content_json_tool(
            '{"name": "run_code", "arguments": {', schemas))
        self.assertIsNone(agent.parse_content_json_tool(
            '{"name": "run_code", "arguments": {"language": "python"}} trailing',
            schemas))
        self.assertIsNone(agent.parse_content_json_tool(
            '["name", "run_code"]', schemas))
        self.assertIsNone(agent.parse_content_json_tool(
            '{"name": "run_code"}', schemas))
        self.assertIsNone(agent.parse_content_json_tool(
            '{"name": "not_a_tool", "arguments": {"path": "x"}}', schemas))
        self.assertIsNone(agent.parse_content_json_tool(
            '{"name": "read_file", "arguments": {}}', schemas))

    def test_fenced_json_agent_loop_runs_tool(self):
        events = []
        calls = 0
        payload = (
            "```json\n"
            '{"name": "run_code", "arguments": {"language": "python", '
            '"code": "print(1)"}}\n'
            "```"
        )

        def fake_stream(_messages, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                yield payload
            else:
                yield "Assertions passed."

        with patch.object(agent.router, "decide", return_value=_Route(tier="gpu")), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value="1\n") as call:
            reply = agent.answer(
                [{"role": "user", "content": "write a python function named clamp"}],
                lambda k, p: events.append((k, p)))
        self.assertEqual("Assertions passed.", reply)
        call.assert_called()
        self.assertEqual("run_code", call.call_args[0][0])
        self.assertEqual("print(1)", call.call_args[0][1]["code"])
        self.assertTrue(any(k == "note" and "content JSON" in p for k, p in events))
        self.assertFalse(any(k == "note" and "legacy" in p for k, p in events))

    def test_legacy_fallback_logs_and_runs(self):
        events = []
        calls = 0

        def fake_stream(_messages, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                yield 'TOOL: clip_info {"clip":"00A"}'
            else:
                yield "Legacy fallback succeeded."

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer([{"role": "user", "content": "show 00A"}],
                                 lambda k, p: events.append((k, p)))
        self.assertEqual("Legacy fallback succeeded.", reply)
        self.assertTrue(any(k == "note" and "legacy" in p for k, p in events))
        self.assertTrue(any(k == "tool" for k, _ in events))

    def test_malformed_legacy_json_never_runs_tool(self):
        events = []
        calls = 0

        def fake_stream(_messages, **_kwargs):
            nonlocal calls
            calls += 1
            yield ('TOOL: clip_info {bad json}' if calls == 1
                   else "The malformed request was refused.")

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call") as call:
            reply = agent.answer([{"role": "user", "content": "bad"}],
                                 lambda k, p: events.append((k, p)))
        call.assert_not_called()
        self.assertEqual("The malformed request was refused.", reply)
        results = [p for k, p in events if k == "tool_result"]
        self.assertTrue(results and "tool was not run" in results[0])

    def test_guard_rails(self):
        cases = [
            ("unknown_tool", {}, "ERROR: no tool"),
            ("clip_info", {"clip": "../etc"}, "not a clip id"),
            ("read_doc", {"name": "/etc/passwd"}, "unknown doc"),
            ("run_build", {"action": "rm -rf /"}, "unknown build action"),
            ("write_file", {"path": "outputs/equal_shares/manifest.json",
                            "content": "forbidden"}, "protected project file"),
        ]
        for name, args, expected in cases:
            with self.subTest(name=name):
                self.assertIn(expected, tools.call(name, args))

    def test_propose_file_diff_is_registered_non_destructive_and_guarded(self):
        self.assertIn("propose_file_diff", tools.TOOLS)
        self.assertIn("propose_file_diff", {item["function"]["name"] for item in tools.schemas()})
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "note.txt"
            path.write_text("before\n", encoding="utf-8")
            preview = tools.call("propose_file_diff", {"path": str(path), "content": "after\n"})
            self.assertIn("-before", preview)
            self.assertIn("+after", preview)
            self.assertEqual("before\n", path.read_text(encoding="utf-8"))
        protected = tools.call("propose_file_diff", {
            "path": "outputs/equal_shares/manifest.json", "content": "nope"})
        self.assertIn("protected project file", protected)

    def test_hex_editor_is_exact_approved_and_protects_evidence(self):
        self.assertIn("inspect_binary", tools.TOOLS)
        self.assertIn("apply_hex_patch", tools.TOOLS)
        schema_names = {item["function"]["name"] for item in tools.schemas()}
        self.assertTrue({"inspect_binary", "apply_hex_patch"}.issubset(schema_names))
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.bin"
            path.write_bytes(b"\x00ABC\xff")
            inspected = json.loads(tools.call("inspect_binary", {
                "path": str(path), "offset": 1, "length": 3}))
            self.assertEqual("41 42 43", inspected["hex"])
            args = {"path": str(path), "offset": 2,
                    "expected_hex": "42", "replacement_hex": "58"}
            pending = tools.call("apply_hex_patch", args)
            self.assertIn("permission is pending", pending)
            request = file_edit_gate.snapshot()["pending"][0]
            self.assertEqual("exact byte patch", request["metadata"]["kind"])
            self.assertEqual("42", request["metadata"]["before"])
            self.assertEqual("58", request["metadata"]["after"])
            file_edit_gate.decide(request["id"], True)
            patched = json.loads(tools.call("apply_hex_patch", args))
            self.assertTrue(patched["patched"])
            self.assertEqual(b"\x00AXC\xff", path.read_bytes())
            mismatch = tools.call("apply_hex_patch", {
                "path": str(path), "offset": 2,
                "expected_hex": "42", "replacement_hex": "59"})
            self.assertIn("does not match", mismatch)
        protected = tools.call("apply_hex_patch", {
            "path": "outputs/equal_shares/manifest.json", "offset": 0,
            "expected_hex": "00", "replacement_hex": "01"})
        self.assertIn("protected Equal Shares evidence", protected)
        remote_denied = tools.call("apply_hex_patch", {
            "path": "C:/does-not-matter.bin", "offset": 0,
            "expected_hex": "00", "replacement_hex": "01"},
            context=remote_security.ToolContext(source="phone"))
        self.assertIn("not permitted", remote_denied)

    def test_gpu_permission_cards_do_not_expire_and_repeated_decision_is_safe(self):
        old_card = {"id": "gpu_old", "workload": "chat reasoning model load",
                    "source": "desktop chat", "detail": "test", "key": "chat:test",
                    "created_at": 1}
        gpu_gate.STATE_FILE.write_text(json.dumps({
            "mode": "ask", "pending": [old_card], "approved_keys": [], "history": [],
        }), encoding="utf-8")
        self.assertEqual("gpu_old", gpu_gate.snapshot()["pending"][0]["id"])
        first = gpu_gate.decide("gpu_old", "approve")
        second = gpu_gate.decide("gpu_old", "approve")
        self.assertEqual("approve", first["decision"])
        self.assertEqual(first, second)
        self.assertTrue(gpu_gate.request("chat reasoning model load", source="desktop chat",
                                         key="chat:test")["granted"])

    def test_batch_tools_refuse_documentation_placeholder(self):
        for name in ("batch_plan", "batch_render"):
            with self.subTest(name=name):
                result = tools.call(name, {"folder": "D:/jobs/scene12"})
                self.assertIn("documentation example", result)

    def test_vague_render_request_cannot_authorize_batch_folder_tool(self):
        calls = 0

        def fake_stream(_messages, **_kwargs):
            nonlocal calls
            calls += 1
            yield oll.ToolCall([
                {"function": {"name": "batch_render",
                              "arguments": {"folder": "D:/jobs/scene12"}}},
            ])

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer([{"role": "user", "content": "render it"}])
        self.assertEqual(1, calls)
        self.assertIn("No batch render plan was run", reply)
        self.assertIn("did not explicitly ask for a batch render", reply)

    def test_powerinfer_json_request_cannot_trigger_stale_batch_plan(self):
        # A calibration JSON is not an H3 batch job. Regression for a model
        # calling batch_plan against the repository root after an unrelated
        # current-chat-render failure earlier in the same conversation.
        turns = iter([
            [oll.ToolCall([{"function": {"name": "batch_plan", "arguments": {
                "folder": "A:/not-a-real-job"}}}])],
            ["I will continue the PowerInfer calibration workflow instead."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        context = remote_security.ToolContext(source="desktop", conversation_id="realchat1")
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call") as call:
            reply = agent.answer([{
                "role": "user",
                "content": "continue the PowerInfer project using the JSON I approved",
            }], tool_context=context)

        call.assert_not_called()
        self.assertEqual("I will continue the PowerInfer calibration workflow instead.", reply)

    def test_start_batch_render_is_fixed_and_preflighted(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "real_job"
            folder.mkdir()
            launched = {}

            def fake_popen(argv, **kwargs):
                launched["argv"] = argv
                launched.update(kwargs)
                return SimpleNamespace(pid=4242)

            with patch.object(tools, "batch_plan", return_value=json.dumps({
                    "render_count": 2, "invalid_count": 0})), \
                 patch.object(tools, "_json", return_value={}), \
                 patch.object(tools.subprocess, "Popen", fake_popen), \
                 patch.object(router, "gpu_busy", return_value=(False, "free", {})), \
                 patch("gpu_gate.request", return_value={"granted": True}):
                result = json.loads(tools.start_batch_render({
                    "folder": str(folder), "limit": 1, "megapixels": 0.9,
                    "duration": 8,
                }))
            self.assertTrue(result["started"])
            self.assertEqual(4242, result["pid"])
            self.assertIn("batch_render_folder.py", launched["argv"][1])
            self.assertEqual("--limit", launched["argv"][3])

    def test_start_batch_render_is_remote_default_deny(self):
        context = remote_security.ToolContext(source="phone")
        result = tools.call("start_batch_render", {"folder": "D:/a-real-job"}, context=context)
        self.assertIn("not permitted", result)

    def test_explicitly_granted_phone_render_uses_authenticated_capability(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "real_job"
            folder.mkdir()
            launched = {}

            def fake_popen(argv, **kwargs):
                launched["argv"] = argv
                return SimpleNamespace(pid=4242)

            context = remote_security.ToolContext(
                source="phone", remote_identity="a" * 32,
                allowed_tools=frozenset({"start_batch_render"}),
                audit_path=str(Path(td) / "remote_audit.jsonl"),
            )
            with patch.object(tools, "batch_plan", return_value=json.dumps({
                    "render_count": 1, "invalid_count": 0})), \
                 patch.object(tools, "_json", return_value={}), \
                 patch.object(tools.subprocess, "Popen", fake_popen), \
                 patch.object(router, "gpu_busy", return_value=(False, "free", {})), \
                 patch("gpu_gate.snapshot", return_value={"mode": "ask"}), \
                 patch("gpu_gate.request") as desktop_gate:
                result = json.loads(tools.call("start_batch_render", {"folder": str(folder)},
                                               context=context))
            self.assertTrue(result["started"])
            self.assertIn("batch_render_folder.py", launched["argv"][1])
            desktop_gate.assert_not_called()

    def test_granted_phone_render_still_obeys_global_gpu_block(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "real_job"
            folder.mkdir()
            context = remote_security.ToolContext(
                source="phone", remote_identity="b" * 32,
                allowed_tools=frozenset({"start_batch_render"}),
            )
            with patch.object(router, "gpu_busy", return_value=(False, "free", {})), \
                 patch("gpu_gate.snapshot", return_value={"mode": "block"}), \
                 patch.object(tools.subprocess, "Popen") as launch:
                result = tools.call("start_batch_render", {"folder": str(folder)}, context=context)
            self.assertIn("GPU gateway is set to Block", result)
            launch.assert_not_called()

    def test_current_chat_render_preserves_trusted_phone_identity(self):
        identity = "c" * 32
        prepared = {"job_folder": "C:/safe/immutable-job", "prompt_count": 1}
        launched = {"started": True, "pid": 4242}
        with patch.object(chat_render_jobs, "prepare_from_chat", return_value=prepared), \
             patch.object(tools, "start_batch_render", return_value=json.dumps(launched)) as start:
            result = json.loads(tools.start_current_chat_render({
                "__conversation_id": "phone-chat", "__remote_render_identity": identity,
            }))
        self.assertTrue(result["launch"]["started"])
        self.assertEqual(identity, start.call_args.args[0]["__remote_render_identity"])
        self.assertEqual("C:/safe/immutable-job", start.call_args.args[0]["folder"])

    def test_current_chat_render_id_is_server_bound(self):
        turns = iter([
            [oll.ToolCall([{"function": {"name": "start_current_chat_render",
                                           "arguments": {"__conversation_id": "forged"}}}])],
            ["Prepared safely."],
        ])
        seen = {}

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        def fake_call(name, args, **_kwargs):
            seen["name"] = name
            seen["args"] = args
            return "prepared"

        context = remote_security.ToolContext(source="desktop", conversation_id="realchat1")
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", fake_call):
            reply = agent.answer([{"role": "user", "content": "prepare the current chat job"}],
                                 tool_context=context)
        self.assertEqual("Prepared safely.", reply)
        self.assertEqual("start_current_chat_render", seen["name"])
        self.assertEqual("realchat1", seen["args"]["__conversation_id"])

    def test_exact_start_render_bypasses_model_folder_guessing(self):
        context = remote_security.ToolContext(source="desktop", conversation_id="realchat1")
        launched = json.dumps({"launch": {"started": True, "planned_renders": 2,
                                             "pid": 4242, "log": "C:/safe.log"}})
        with patch.object(agent.oll, "chat_stream") as stream, \
             patch.object(agent.tools, "call", return_value=launched) as call:
            reply = agent.answer([{"role": "user", "content": "start render"}],
                                 tool_context=context)
        stream.assert_not_called()
        call.assert_called_once()
        self.assertEqual("start_current_chat_render", call.call_args.args[0])
        self.assertIn("Batch render started: 2", reply)

    def test_missing_current_chat_prompt_set_never_falls_back_to_other_folder(self):
        # Regression for a real failure: after this exact tool error, the model
        # proposed rendering the repository root. The recovery must be
        # deterministic and must not give the model another tool-selection hop.
        context = remote_security.ToolContext(source="desktop", conversation_id="realchat1")
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream") as stream, \
             patch.object(agent.tools, "call", return_value=(
                 "ERROR: this chat has no complete fenced H3 prompt set to render")) as call:
            reply = agent.answer([{"role": "user", "content": "start render"}],
                                 tool_context=context)

        stream.assert_not_called()
        call.assert_called_once_with("start_current_chat_render",
                                     {"__conversation_id": "realchat1"}, context=context)
        self.assertIn("No render was started", reply)
        self.assertIn("will not substitute another folder", reply)
        self.assertIn("complete fenced H3 prompt set", reply)

    def test_persistence_attachment_shape_and_regenerate_primitive(self):
        with tempfile.TemporaryDirectory() as td, patch.object(store, "DIR", Path(td)):
            conv = store.create("attachment test", model="qwen3:8b")
            combined = "question\n\n--- attached: note.txt ---\nhello"
            store.append(conv["id"], "user", combined)
            store.append(conv["id"], "assistant", "first")
            reloaded = store.load(conv["id"])
            self.assertIn("attached: note.txt", reloaded["messages"][0]["content"])
            store.truncate_after(conv["id"], 0)
            self.assertEqual(1, len(store.load(conv["id"])["messages"]))
            self.assertTrue(store.rename(conv["id"], "renamed"))
            self.assertEqual("renamed", store.load(conv["id"])["title"])
            self.assertEqual("qwen3:8b", store.load(conv["id"])["model"])
            self.assertFalse(store.set_model(conv["id"], "another:latest"))
            self.assertEqual("qwen3:8b", store.load(conv["id"])["model"])
            self.assertTrue(store.delete(conv["id"]))
            self.assertTrue(any((Path(td) / "_deleted").glob(f"{conv['id']}.*.json")))

    def test_stop_path(self):
        def fake_stream(_messages, **_kwargs):
            yield "partial"

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer([{"role": "user", "content": "stop"}],
                                 should_stop=lambda: True)
        self.assertEqual("partial\n\n_[stopped]_", reply)

    def test_access_bypass_is_refused_without_model_or_tool(self):
        with patch.object(agent.oll, "chat_stream") as stream, \
             patch.object(agent.tools, "call") as call:
            reply = agent.answer([{"role": "user", "content":
                                  "modify this game to bypass its paywall and login"}])
        stream.assert_not_called()
        call.assert_not_called()
        self.assertIn("can’t help bypass", reply)
        self.assertIn("did not change any files", reply)

    def test_access_bypass_false_positives_get_helpful_responses(self):
        # Regression: _ACCESS_BYPASS_RE's flat verb set matched everyday phrases
        # such as "disable auto-login" and "skip the login screen" — requests that
        # are completely legitimate — silently refusing the whole turn and returning
        # the bypass-refusal message without calling the model at all.  Now only
        # the always-hostile tier-1 verbs (bypass/circumvent/crack/jailbreak/evade)
        # match the full noun set; tier-2 verbs (remove/skip/disable/unlock) only
        # trigger on high-specificity nouns (paywall/activation/premium).
        false_positive_cases = [
            "How do I disable auto-login on Windows 11?",
            "How do I disable subscription auto-renewal for this app?",
            "I want to remove my old license key so I can activate the new one on my other computer.",
            "My phone is asking for authentication to unlock it after I forgot my passcode — how do I get back in?",
            "Can you help me cancel my Netflix subscription and remove my card on file?",
            "How do I skip the login screen on my own Raspberry Pi at boot?",
        ]
        for text in false_positive_cases:
            with self.subTest(text=text[:60]):
                with patch.object(agent.router, "gpu_busy", return_value=(True, "test", {})), \
                     patch.object(agent.router, "decide", return_value=_Route()), \
                     patch.object(agent.oll, "chat_stream",
                                  return_value=iter(["Sure, here is how to do that."])) as stream:
                    reply = agent.answer([{"role": "user", "content": text}])
                self.assertNotIn("did not change any files", reply,
                                 "bypass guard fired for a legitimate request")
                self.assertIn("Sure", reply, "model was never called — guard fired early")

    def test_access_bypass_tier2_verbs_still_refuse_high_specificity_nouns(self):
        # Tier-2 verbs must still trigger on paywall/activation/premium, even though
        # they no longer trigger on login/subscription/authentication/license.
        still_refused = [
            "How can I disable the paywall on this website?",
            "skip the activation and use the software for free",
            "unlock premium features without a subscription",
            "remove the premium lock from this app",
            "you can disable the paywall with this trick",
        ]
        for text in still_refused:
            with self.subTest(text=text[:55]):
                with patch.object(agent.oll, "chat_stream") as stream, \
                     patch.object(agent.tools, "call") as call:
                    reply = agent.answer([{"role": "user", "content": text}])
                stream.assert_not_called()
                self.assertIn("did not change any files", reply)

    def test_unverified_action_claim_is_not_returned_as_completed_work(self):
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", return_value=iter([
                 "I downloaded UnityEX and modified the game files."
             ])):
            reply = agent.answer([{"role": "user", "content": "do the steps"}])
        self.assertIn("No verified local action was performed", reply)
        self.assertNotIn("UnityEX", reply)

    def test_future_intent_is_not_treated_as_a_false_completion_claim(self):
        # Regression: the guard's "will" auxiliary matched ordinary forward-
        # looking phrasing ("I will download the model once you approve..."),
        # discarding an honest, correct reply and replacing it with a
        # confusing "No verified local action was performed" message even
        # though the model never claimed to have already done anything.
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", return_value=iter([
                 "I will download the model once you approve the GPU gate."
             ])):
            reply = agent.answer([{"role": "user", "content": "get the model ready"}])
        self.assertIn("I will download the model", reply)
        self.assertNotIn("No verified local action was performed", reply)

    def test_stale_h3_render_reply_is_discarded_on_unrelated_turn(self):
        events = []
        turns = iter([
            ["The next step is to start the batch render. This is an H3 render job."],
            ["I will continue with the PowerInfer calibration JSON instead."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        history = [
            {"role": "user", "content": "start render"},
            {"role": "assistant", "content": "No render was started. This chat has no complete fenced H3 prompt set to render."},
            {"role": "user", "content": "continue with powerinfer training"},
        ]
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        self.assertEqual("I will continue with the PowerInfer calibration JSON instead.", reply)
        self.assertTrue(any(k == "note" and "scope correction" in p for k, p in events))

    def test_confirmation_reply_to_a_pending_image_offer_is_not_discarded(self):
        # Regression, live bug 2026-09-06: operator asked for a multi-clip
        # image sequence ("photos"/"clips", no literal singular "image"),
        # the assistant planned it and asked "would you like me to proceed",
        # and the operator's one-line "yes proceed, and also bear in mind
        # I'll send more prompts" was wrongly treated as a brand-new,
        # unrelated turn -- because the confirmation text itself doesn't
        # repeat any specialist keyword -- discarding the correct reply and
        # replacing it with the generic "could not produce a grounded
        # answer" refusal. A pending, un-declined offer in the immediately
        # preceding assistant turn must let a short confirmation continue.
        events = []
        turns = iter([
            ["I have prepared the plans with plan_story_image. If you would "
             "like to proceed with generating the images, I can start the "
             "rendering process now."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        history = [
            {"role": "user", "content": "Generate these photos --- CLIP 1 --- "
                                         "START FRAME: a skater at a park."},
            {"role": "assistant", "content": "I have prepared the plans with "
                                              "plan_story_image. If you would "
                                              "like to proceed with generating "
                                              "the images, I can start the "
                                              "rendering process now."},
            {"role": "user", "content": "yes proceed and also bear in mind i "
                                         "will be giving you more prompts for "
                                         "building more images if the ones "
                                         "you are about to start generating "
                                         "come out well."},
        ]
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        self.assertIn("rendering process now", reply)
        self.assertFalse(any(k == "note" and "scope correction" in p for k, p in events))
        self.assertNotIn("could not produce a grounded answer", reply)

    def test_confirmation_proceed_after_image_plan_allows_render_story_image(self):
        # Sibling of 2026-09-06f reply-text fix: after plan_story_image the
        # operator often just says "proceed". That must allowlist
        # render_story_image via _pending_specialist_continuation, not trip
        # "stale specialist-project tool selection blocked".
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {
                "name": "render_story_image",
                "arguments": {
                    "story": "vhs_liminal_space_story",
                    "prompt": "VHS skatepark still",
                    "model_profile": "realpro_flux",
                }}}])],
            ["Started the Flux still render; polling story_image_job_status next."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        history = [
            {"role": "user", "content": "Generate these photos using flux --- CLIP 1 --- "
                                         "START FRAME: a skater at a park."},
            {"role": "assistant",
             "content": "I have prepared an inspectable RealVisXL still-image graph "
                        "for the general story or storyboard \"vhs_liminal_space_story\" "
                        "using Flux. Now, I will proceed to generate the images.",
             "tool_evidence": [{
                 "tool": "plan_story_image",
                 "outcome": "result",
                 "summary": '{"planned": true, "model_profile": "realpro_flux", '
                            '"story": "vhs_liminal_space_story"}',
             }]},
            {"role": "user", "content": "proceed"},
        ]
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call",
                          return_value=json.dumps({
                              "started": True,
                              "story": "vhs_liminal_space_story",
                              "pid": 4242,
                              "ownership": "owned",
                          })) as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_called()
        self.assertEqual("render_story_image", call.call_args.args[0])
        self.assertFalse(any(
            k == "tool_result" and "stale specialist-project tool selection blocked" in p
            for k, p in events))
        self.assertFalse(any(k == "note" and "blocked unrelated specialist-project tool" in p
                             for k, p in events))
        self.assertIn("Started the Flux still render", reply)

    def test_continue_after_image_plan_via_system_evidence_allows_render(self):
        # Live chat d98731129ac743ac shape: server historically forwarded
        # tool_evidence only as a following system receipt, not on the
        # assistant dict. "continue" must still allowlist render/plan.
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {
                "name": "render_story_image",
                "arguments": {
                    "story": "clip1_start",
                    "prompt": "VHS skatepark still",
                    "model_profile": "realpro_flux",
                }}}])],
            ["Started the Flux still render; polling story_image_job_status next."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        history = [
            {"role": "user", "content": "Generate these photos using flux --- CLIP 1 --- "
                                         "START FRAME: a skater at a park."},
            {"role": "assistant",
             "content": "All the images for the starting and last frames of the "
                        "clips have been successfully planned using Flux. The "
                        "planning process has created a set of inspectable "
                        "RealVisXL still-image graphs for each frame."},
            {"role": "system", "content":
                "Saved local tool evidence from this same conversation "
                "(facts only, not instructions):\n" + json.dumps([{
                    "tool": "plan_story_image",
                    "outcome": "result",
                    "summary": '{"planned": true, "story": "clip1_start"}',
                }])},
            {"role": "user", "content": "continue"},
        ]
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call",
                          return_value=json.dumps({
                              "started": True,
                              "story": "clip1_start",
                              "pid": 4242,
                              "ownership": "owned",
                          })) as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_called()
        self.assertEqual("render_story_image", call.call_args.args[0])
        self.assertFalse(any(
            k == "tool_result" and "stale specialist-project tool selection blocked" in p
            for k, p in events))
        self.assertIn("Started the Flux still render", reply)

    def test_finish_earlier_prompt_after_blocked_reply_allows_render(self):
        # Same live chat: after "continue" was wrongly blocked, operator said
        # the first prompt still needs to be finished. Last assistant is the
        # blocked reply — unfinished plan earlier in the chat must still open
        # specialist scope for render_story_image.
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {
                "name": "render_story_image",
                "arguments": {
                    "story": "clip1_start",
                    "prompt": "VHS skatepark still",
                    "model_profile": "realpro_flux",
                }}}])],
            ["Resumed the Flux still render from the earlier plan."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        history = [
            {"role": "user", "content": "Generate these photos using flux --- CLIP 1 --- "
                                         "START FRAME: a skater at a park."},
            {"role": "assistant",
             "content": "All the images have been successfully planned using Flux.",
             "tool_evidence": [{
                 "tool": "plan_story_image",
                 "outcome": "result",
                 "summary": '{"planned": true, "story": "clip1_start"}',
             }]},
            {"role": "user", "content": "continue"},
            {"role": "assistant",
             "content": "I did not run the attempted tool because it was outside "
                        "the current request. No local action was performed. "
                        "Please restate the immediate task in one sentence.",
             "tool_evidence": [{
                 "tool": "plan_story_image",
                 "outcome": "error",
                 "summary": "stale specialist-project tool selection blocked",
             }]},
            {"role": "user", "content": "the first prompt i sent still needs to finished."},
        ]
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call",
                          return_value=json.dumps({
                              "started": True,
                              "story": "clip1_start",
                              "pid": 5252,
                              "ownership": "owned",
                          })) as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_called()
        self.assertEqual("render_story_image", call.call_args.args[0])
        self.assertFalse(any(
            k == "tool_result" and "stale specialist-project tool selection blocked" in p
            for k, p in events))
        self.assertIn("Resumed the Flux still render", reply)

    def test_stale_h3_render_tool_is_blocked_on_unrelated_turn(self):
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {"name": "batch_plan",
                                         "arguments": {"folder": "D:/jobs/scene12"}}}])],
            ["I will validate the approved PowerInfer calibration file instead."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        history = [
            {"role": "user", "content": "start render"},
            {"role": "assistant", "content": "No render was started. This chat has no complete fenced H3 prompt set to render."},
            {"role": "user", "content": "continue with powerinfer training"},
        ]
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call") as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_not_called()
        self.assertEqual("I will validate the approved PowerInfer calibration file instead.", reply)
        self.assertTrue(any(k == "note" and "blocked unrelated specialist-project tool" in p
                            for k, p in events))

    def test_primary_oom_retries_once_on_paired_fallback(self):
        events = []
        attempts = 0
        primary = _Route("gpu", "127.0.0.1:11434", router.PRIMARY_REASONING_MODEL)
        fallback = _Route("gpu", "127.0.0.1:11434", router.FALLBACK_REASONING_MODEL)

        def fake_stream(_messages, **_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise oll.OllamaModelFailure("CUDA out of memory")
            yield "Recovered on the 8B model."

        with patch.object(agent.router, "decide", return_value=primary), \
             patch.object(agent.router, "fallback_after_primary_failure",
                          return_value=fallback) as recover, \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer([{"role": "user", "content": "hello"}],
                                 lambda k, p: events.append((k, p)),
                                 model=router.PRIMARY_REASONING_MODEL)
        self.assertEqual("Recovered on the 8B model.", reply)
        self.assertEqual(2, attempts)
        recover.assert_called_once()
        self.assertTrue(any(k == "note" and "8B" in p for k, p in events))

    def test_schemas_cpu_profile_is_exactly_three_meta_tools(self):
        names = [item["function"]["name"] for item in tools.schemas(profile="cpu")]
        self.assertEqual(["list_tools", "describe_tool", "call_tool"], names)
        self.assertTrue(set(tools.META_TOOL_NAMES).isdisjoint(tools.TOOLS))
        self.assertEqual(len(tools.TOOLS), len(tools.schemas()))
        self.assertEqual(len(tools.TOOLS), len(tools.schemas(profile="gpu")))

    def test_image_capability_sends_gpu_image_schemas_to_chat_stream(self):
        seen = []
        events = []

        def fake_stream(_messages, **kwargs):
            seen.append(kwargs.get("tools"))
            yield "ok"

        route = _Route(tier="gpu")
        route.detail = {"capability": "image"}
        with patch.object(agent.router, "decide", return_value=route),              patch.object(agent.oll, "chat_stream", fake_stream):
            agent.answer(
                [{"role": "user", "content":
                  "still frames only. photoreal images. No captions on the images."}],
                lambda k, p: events.append((k, p)),
                model=router.PRIMARY_REASONING_MODEL)
        self.assertEqual(1, len(seen))
        names = [item["function"]["name"] for item in seen[0]]
        self.assertEqual(list(tools.IMAGE_DIRECT_TOOLS), names)
        self.assertTrue(any(
            k == "note" and "gpu image schema" in p for k, p in events))

    def test_gpu_decision_sends_full_schemas_to_chat_stream(self):
        seen = []

        def fake_stream(_messages, **kwargs):
            seen.append(kwargs.get("tools"))
            yield "ok"

        with patch.object(agent.router, "decide", return_value=_Route(tier="gpu")), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            agent.answer([{"role": "user", "content":
                           "Compare the Equal Shares ladders for 00B and 00A"}])
        self.assertEqual(1, len(seen))
        self.assertEqual(len(tools.TOOLS), len(seen[0]))
        self.assertEqual(set(tools.TOOLS),
                         {item["function"]["name"] for item in seen[0]})

    def test_cpu_decision_sends_meta_schemas_to_chat_stream(self):
        seen = []

        def fake_stream(_messages, **kwargs):
            seen.append(kwargs.get("tools"))
            yield "ok"

        with patch.object(agent.router, "decide", return_value=_Route(tier="cpu")), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            agent.answer([{"role": "user", "content":
                           "Compare the Equal Shares ladders for 00B and 00A"}])
        self.assertEqual(1, len(seen))
        self.assertEqual(
            ["list_tools", "describe_tool", "call_tool"],
            [item["function"]["name"] for item in seen[0]])

    def test_farm_decision_sends_meta_schemas_to_qwythos(self):
        import farm_offload
        captured = {}

        def fake_qwythos(messages, tools=None, timeout_s=None):
            captured["tools"] = tools
            return {"content": "OK", "tool_calls": [], "model": "qwythos"}

        farm_route = _Route("farm", "farm", "qwythos", backend="farm")
        with patch.object(agent.router, "decide", return_value=farm_route), \
             patch.object(farm_offload, "try_qwythos_on_farm", side_effect=fake_qwythos), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("local chat should not run")):
            reply = agent.answer([{"role": "user", "content":
                                   "Compare the Equal Shares ladders for 00B and 00A"}])
        self.assertEqual("OK", reply)
        names = [item["function"]["name"] for item in captured["tools"]]
        self.assertEqual(["list_tools", "describe_tool", "call_tool"], names)

    def test_farm_attempt_emits_proposal_route_before_qwythos_wait(self):
        """2026-09-05cw: progress + proposal farm route before the blocking wait."""
        import farm_offload
        log = []
        before_wait = []

        def fake_qwythos(messages, tools=None, timeout_s=None):
            before_wait.append(list(log))
            return {"content": "OK", "tool_calls": [], "model": "qwythos"}

        def on_event(kind, payload):
            log.append((kind, payload))

        farm_route = _Route("farm", "farm", "qwythos", backend="farm")
        with patch.object(agent.router, "decide", return_value=farm_route), \
             patch.object(farm_offload, "try_qwythos_on_farm", side_effect=fake_qwythos), \
             patch.object(agent.oll, "chat_stream",
                          side_effect=AssertionError("local chat should not run")):
            reply = agent.answer(
                [{"role": "user", "content": "Where is TODO.md?"}],
                on_event=on_event)
        self.assertEqual("OK", reply)
        self.assertEqual(1, len(before_wait))
        pre_kinds = [k for k, _ in before_wait[0]]
        self.assertIn("progress", pre_kinds)
        self.assertIn("route", pre_kinds)
        waiting = [json.loads(p) for k, p in before_wait[0] if k == "progress"]
        self.assertTrue(any(p.get("label") == "Waiting on Mac Qwythos" for p in waiting))
        pre_routes = [json.loads(p) for k, p in before_wait[0] if k == "route"]
        self.assertTrue(pre_routes)
        self.assertTrue(all(r.get("source") == "proposal" for r in pre_routes))
        self.assertTrue(all(r.get("backend") == "farm" for r in pre_routes))
        self.assertTrue(all(r.get("reason") == "attempting farm" for r in pre_routes))
        self.assertFalse(any("accepted" in str(r.get("reason") or "").lower()
                             for r in pre_routes))
        all_routes = [json.loads(p) for k, p in log if k == "route"]
        self.assertGreaterEqual(len(all_routes), 2)
        self.assertEqual("proposal", all_routes[0].get("source"))
        self.assertNotEqual("proposal", all_routes[-1].get("source"))
        self.assertEqual("farm", all_routes[-1].get("backend"))

    def test_farm_miss_emits_local_observation_route_after_wait(self):
        import farm_offload
        log = []
        before_wait = []
        farm_route = _Route("farm", "farm", "qwythos", backend="farm")
        local_route = _Route("cpu", "127.0.0.1:11435", "stub-model", backend="ollama")

        def fake_qwythos(messages, tools=None, timeout_s=None):
            before_wait.append(list(log))
            return None

        def fake_decide(*_a, skip_farm=False, **_k):
            return local_route if skip_farm else farm_route

        def fake_stream(*_a, **_k):
            yield "local-ok"

        def on_event(kind, payload):
            log.append((kind, payload))

        with patch.object(agent.router, "decide", side_effect=fake_decide), \
             patch.object(farm_offload, "try_qwythos_on_farm", side_effect=fake_qwythos), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(
                [{"role": "user", "content": "Where is TODO.md?"}],
                on_event=on_event)
        self.assertEqual("local-ok", reply)
        pre_routes = [json.loads(p) for k, p in before_wait[0] if k == "route"]
        self.assertTrue(all(r.get("source") == "proposal" and r.get("backend") == "farm"
                            for r in pre_routes))
        all_routes = [json.loads(p) for k, p in log if k == "route"]
        self.assertEqual("farm", all_routes[0].get("backend"))
        self.assertEqual("proposal", all_routes[0].get("source"))
        self.assertEqual("ollama", all_routes[-1].get("backend"))
        self.assertNotEqual("proposal", all_routes[-1].get("source"))
        notes = [p for k, p in log if k == "note"]
        self.assertTrue(any("falling back locally" in n for n in notes))

    def test_powerinfer_system_prompt_is_text_only_not_tool_assuming(self):
        """backend=powerinfer must not receive the agentic tool-calling prompt.

        GPU keeps CONVERSATION_RULES; CPU/farm keep CPU_COMPACT_RULES.
        PowerInfer keeps project/memory context but drops tool-execution
        instructions and native tool names from the model-facing system
        message. No live PowerInfer hardware — Decision is mocked.
        """
        prompt = "Compare the Equal Shares ladders for 00B and 00A"
        history = [{"role": "user", "content": prompt}]
        tool_instruction_markers = (
            "use the appropriate available tool",
            "call `fetch_url`",
            "start_current_chat_render",
            "extract_video_actions",
            "analyze_image",
            "list_tools",
            "describe_tool",
            "call_tool",
            "Calling a tool is plumbing",
        )

        def _system_from_route(route, *, farm=False):
            captured = {}

            def fake_stream(messages, **kwargs):
                captured["messages"] = messages
                captured["tools"] = kwargs.get("tools")
                yield "ok"

            def fake_qwythos(messages, tools=None, timeout_s=None):
                captured["messages"] = messages
                captured["tools"] = tools
                return {"content": "ok", "tool_calls": [], "model": "qwythos"}

            ctx = patch.object(agent.router, "decide", return_value=route)
            if farm:
                import farm_offload
                with ctx, \
                     patch.object(farm_offload, "try_qwythos_on_farm",
                                  side_effect=fake_qwythos), \
                     patch.object(agent.oll, "chat_stream",
                                  side_effect=AssertionError(
                                      "local chat should not run")):
                    agent.answer(history)
            else:
                with ctx, patch.object(agent.oll, "chat_stream", fake_stream):
                    agent.answer(history)
            system = captured["messages"][0]["content"]
            return system, captured.get("tools")

        gpu_system, gpu_tools = _system_from_route(_Route(tier="gpu"))
        cpu_system, cpu_tools = _system_from_route(_Route(tier="cpu"))
        farm_route = _Route("farm", "farm", "qwythos", backend="farm")
        farm_system, farm_tools = _system_from_route(farm_route, farm=True)
        pi_route = _Route(
            "gpu", router.POWERINFER_PROXY_HOST,
            router.POWERINFER_MODEL_ALIAS, backend="powerinfer")
        pi_system, pi_tools = _system_from_route(pi_route)

        self.assertEqual(gpu_system, agent.system_prompt(history))
        self.assertIn("use the appropriate available tool", gpu_system)
        self.assertIn("call `fetch_url`", gpu_system)
        self.assertEqual(len(tools.TOOLS), len(gpu_tools))

        self.assertEqual(cpu_system, agent.CPU_COMPACT_RULES)
        self.assertEqual(farm_system, agent.CPU_COMPACT_RULES)
        self.assertEqual(
            ["list_tools", "describe_tool", "call_tool"],
            [item["function"]["name"] for item in cpu_tools])
        self.assertEqual(
            ["list_tools", "describe_tool", "call_tool"],
            [item["function"]["name"] for item in farm_tools])

        self.assertTrue(pi_tools is None or pi_tools == [])
        self.assertIn(agent.POWERINFER_CONVERSATION_RULES, pi_system)
        pi_flat = " ".join(pi_system.lower().split())
        self.assertIn("no tools are available", pi_flat)
        self.assertIn("do not claim an action occurred", pi_flat)
        self.assertIn("Equal Shares specialist reference", pi_system)
        for marker in tool_instruction_markers:
            self.assertNotIn(marker, pi_system)
        self.assertNotEqual(pi_system, gpu_system)
        self.assertNotEqual(pi_system, cpu_system)

    def test_call_tool_unwraps_and_hits_tools_call(self):
        turns = iter([
            [oll.ToolCall([{"function": {"name": "call_tool", "arguments": {
                "name": "capabilities", "args": {}}}}])],
            ["Capabilities reported."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value='{"available": true}') as call:
            reply = agent.answer([{"role": "user", "content":
                                   "please inspect local capabilities now"}])
        self.assertEqual("Capabilities reported.", reply)
        call.assert_called_once()
        self.assertEqual("capabilities", call.call_args[0][0])
        self.assertEqual({}, call.call_args[0][1])

    def test_call_tool_does_not_bypass_protected_file_guard(self):
        result = tools.call("call_tool", {
            "name": "write_file",
            "args": {"path": "outputs/equal_shares/manifest.json",
                     "content": "forbidden"},
        })
        self.assertIn("protected project file", result)

    def test_call_tool_specialist_guard_sees_inner_name(self):
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {"name": "call_tool", "arguments": {
                "name": "batch_plan",
                "args": {"folder": "D:/jobs/scene12"}}}}])],
            ["I will validate the approved PowerInfer calibration file instead."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        history = [
            {"role": "user", "content": "start render"},
            {"role": "assistant", "content":
             "No render was started. This chat has no complete fenced H3 prompt set to render."},
            {"role": "user", "content": "continue with powerinfer training"},
        ]
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call") as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))
        call.assert_not_called()
        self.assertEqual("I will validate the approved PowerInfer calibration file instead.",
                         reply)
        self.assertTrue(any(k == "note" and "blocked unrelated specialist-project tool" in p
                            for k, p in events))

    def test_list_tools_category_alias_file_operations(self):
        payload = json.loads(tools.call("list_tools", {"category": "file_operations"}))
        names = [item["name"]
                 for group in payload["categories"].values()
                 for item in group]
        self.assertIn("list_dir", names)
        self.assertEqual(["file"], list(payload["categories"]))

    def test_list_tools_omits_project_only_when_include_project_false(self):
        payload = json.loads(tools.call("list_tools", {}, include_project=False))
        names = [item["name"]
                 for group in payload["categories"].values()
                 for item in group]
        self.assertNotIn("search_docs", names)
        self.assertNotIn("clip_info", names)
        self.assertIn("list_dir", names)
        self.assertIn("validate_powerinfer_calibration", names)
        full = json.loads(tools.call("list_tools", {}, include_project=True))
        full_names = [item["name"]
                      for group in full["categories"].values()
                      for item in group]
        self.assertIn("search_docs", full_names)
        self.assertEqual(len(tools.TOOLS), len(full_names))

    def test_describe_tool_unknown_name_is_error_not_raise(self):
        result = tools.call("describe_tool", {"name": "nope_tool"})
        self.assertTrue(result.startswith("ERROR:"))
        self.assertIn("nope_tool", result)
        self.assertIn("Visible:", result)
        ok = json.loads(tools.call("describe_tool", {"name": "list_dir"}))
        self.assertEqual("list_dir", ok["name"])
        self.assertIn("parameters", ok)

    def test_primary_oom_fallback_stays_gpu_profile(self):
        events = []
        attempts = 0
        primary = _Route("gpu", "127.0.0.1:11434", router.PRIMARY_REASONING_MODEL)
        fallback = _Route("gpu", "127.0.0.1:11434", router.FALLBACK_REASONING_MODEL)
        seen_tools = []

        def fake_stream(_messages, **kwargs):
            nonlocal attempts
            seen_tools.append(kwargs.get("tools"))
            attempts += 1
            if attempts == 1:
                raise oll.OllamaModelFailure("CUDA out of memory")
            yield "Recovered on the 8B model."

        with patch.object(agent.router, "decide", return_value=primary), \
             patch.object(agent.router, "fallback_after_primary_failure",
                          return_value=fallback), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(
                [{"role": "user", "content":
                  "Compare the Equal Shares ladders for 00B and 00A"}],
                lambda k, p: events.append((k, p)),
                model=router.PRIMARY_REASONING_MODEL)
        self.assertEqual("Recovered on the 8B model.", reply)
        self.assertEqual(2, len(seen_tools))
        for payload in seen_tools:
            self.assertEqual(len(tools.TOOLS), len(payload))
            self.assertNotIn("list_tools", {item["function"]["name"] for item in payload})

    def test_degenerate_empty_numbered_list_is_treated_as_empty_completion(self):
        blob = "\n".join(f"{i}." for i in range(1, 113))
        blob += "\n\n" + "\n".join(["```", "```"] * 12)
        self.assertTrue(agent._is_degenerate_completion(blob))
        self.assertFalse(agent._is_degenerate_completion(
            "1. pre01_start: wide yard, both on lounge chairs.\n"
            "2. pre01_last: Bulma talking, looking up.\n"
            "3. pre02_start: two-shot, still talking.\n"))
        events = []
        turns = iter([[blob], [blob]])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route(tier="gpu")), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(
                [{"role": "user", "content": "still frames only, make the pngs"}],
                lambda k, p: events.append((k, p)))
        self.assertEqual(agent._EMPTY_COMPLETION_REPLY, reply)
        self.assertTrue(any(k == "note" and agent._DEGENERATE_COMPLETION_NOTE in p
                            for k, p in events))
        self.assertTrue(any(k == "note" and agent._EMPTY_COMPLETION_RETRY_NOTE in p
                            for k, p in events))

    def test_hop_limit_with_empty_answer_does_not_store_blank(self):
        hops = {"n": 0}

        def varying_stream(_messages, **_kwargs):
            hops["n"] += 1
            yield oll.ToolCall([{
                "function": {"name": "web_search",
                             "arguments": {"query": f"q{hops['n']}"}},
            }])

        events = []
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", varying_stream), \
             patch.object(agent.tools, "call",
                          return_value="ERROR: search failed"):
            reply = agent.answer(
                [{"role": "user", "content": "search several things"}],
                lambda k, p: events.append((k, p)))
        self.assertEqual(agent._HOP_LIMIT_EMPTY_REPLY, reply)
        self.assertTrue(any(k == "note" and "hop limit" in p for k, p in events))
        self.assertEqual(agent.MAX_TOOL_HOPS + 1, hops["n"])

    def test_image_render_owner_conflict_stops_instead_of_burning_hops(self):
        launch = json.dumps({
            "started": True, "pid": 19820, "story": "pre01_start",
            "log": "work/runtime/agent_image_jobs/pre01_start.log",
        })
        refuse = "ERROR: image-render preflight refused: another image render owns the backend (pid=19820)"
        results = iter([launch, refuse])
        streams = iter([
            [oll.ToolCall([
                {"function": {"name": "render_story_image",
                              "arguments": {"story": "pre01_start", "prompt": "a"}}},
                {"function": {"name": "render_story_image",
                              "arguments": {"story": "pre01_last", "prompt": "b"}}},
            ])],
            [oll.ToolCall([{"function": {"name": "render_story_image",
                                          "arguments": {"story": "pre02_start"}}}])],
        ])
        hops = {"n": 0}

        def fake_stream(_messages, **_kwargs):
            hops["n"] += 1
            yield from next(streams)

        def fake_call(name, args, context=None):
            return next(results)

        events = []
        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", side_effect=fake_call):
            reply = agent.answer(
                [{"role": "user", "content":
                  "still frames only. photoreal image stills for "
                  "pre01_start.png and pre01_last.png"}],
                lambda k, p: events.append((k, p)))
        self.assertIn("pid=19820", reply)
        self.assertIn("pre01_start", reply)
        self.assertIn("story_image_job_status", reply)
        self.assertEqual(1, hops["n"])
        self.assertTrue(any(k == "note" and "image-render owner guard" in p
                            for k, p in events))

    def test_thinking_only_empty_completion_does_not_persist_empty_success(self):
        # Live 2026-09-04: 8B generated 838/637 tokens in message.thinking,
        # chat_stream yielded nothing, hop loop stored "". First hop here is
        # that thinking-only stream (~200 tokens never visible); retry with
        # think=False must produce a real reply, never "".
        events = []
        calls = []
        turns = iter([
            [],
            ["Four of sixteen frames are on disk; none have been stitched."],
        ])

        def fake_stream(_messages, **kwargs):
            calls.append(kwargs)
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route(tier="gpu")), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(
                [{"role": "user", "content":
                  "how far along are you in the comfyui job?"}],
                lambda k, p: events.append((k, p)))
        self.assertEqual(
            "Four of sixteen frames are on disk; none have been stitched.", reply)
        self.assertEqual(2, len(calls))
        self.assertIs(False, calls[0].get("think"))
        self.assertIs(False, calls[1].get("think"))
        self.assertTrue(any(k == "note" and agent._EMPTY_COMPLETION_RETRY_NOTE in p
                            for k, p in events))

    def test_unclosed_think_empty_completion_gets_specific_operator_message(self):
        # Live 2026-09-05 (conversation e40fa885d6134050, huihui_ai/qwen3-
        # abliterated:14b): a large capability=image turn opened <think> in
        # message.content and never closed it before the stream ended, so
        # chat_stream's real filter yields no visible text and (pre-fix)
        # thinking_chars stayed 0 too -- indistinguishable from a silent
        # model. Both retry attempts here reproduce that same shape (the
        # model ignores think=False identically both times, as it did live),
        # each ending in a StreamEnd with unclosed_think_chars set instead of
        # any visible text or tool calls. The operator-facing reply must name
        # this specific shape rather than the generic empty-completion text.
        end = oll.StreamEnd(
            {"eval_count": 275, "prompt_eval_count": 17578,
             "total_duration": 4_300_000_000, "eval_duration": 4_300_000_000},
            thinking_chars=640, visible_chars=0, unclosed_think_chars=640)

        def fake_stream(_messages, **_kwargs):
            yield end

        events = []
        with patch.object(agent.router, "decide", return_value=_Route(tier="gpu")), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(
                [{"role": "user", "content":
                  "fourteen-beat photoreal still-frame brief, one per beat"}],
                lambda k, p: events.append((k, p)))
        self.assertEqual(agent._UNCLOSED_THINK_EMPTY_COMPLETION_REPLY, reply)
        self.assertNotEqual(agent._EMPTY_COMPLETION_REPLY, reply)
        self.assertTrue(any(
            k == "note" and "unclosed <think>" in p and "640" in p
            for k, p in events))

    def test_compact_cpu_nonmatching_prompt_empty_completion_is_not_stored(self):
        events = []
        seen_tools = []
        prompt = "how far along are you in the comfyui job?"
        self.assertIsNone(agent._ACTION_REQUEST_RE.search(prompt))

        def fake_stream(_messages, **kwargs):
            seen_tools.append([item["function"]["name"]
                               for item in kwargs.get("tools") or []])
            self.assertIs(False, kwargs.get("think"))
            return
            yield

        with patch.object(agent.router, "decide", return_value=_Route(tier="cpu")), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(
                [{"role": "user", "content": prompt}],
                lambda k, p: events.append((k, p)))
        self.assertEqual(agent._EMPTY_COMPLETION_REPLY, reply)
        self.assertTrue(reply.strip())
        self.assertEqual(2, len(seen_tools))
        self.assertEqual(
            ["list_tools", "describe_tool", "call_tool"], seen_tools[0])
        self.assertEqual(seen_tools[0], seen_tools[1])
        self.assertFalse(any(k == "note" and "execution-first" in p
                             for k, p in events))
        self.assertTrue(any(k == "note" and agent._EMPTY_COMPLETION_RETRY_NOTE in p
                            for k, p in events))

    # ------------------------------------------------------------------
    # Live 2026-09-25, chat 149209bf6e4b42ce msgs 10-13.  Every assistant
    # turn in that chat carried real render_story_image /
    # render_story_image_batch / story_image_job_status evidence.  "So lets
    # regenerate that one" (msg 10) and a bare "status" (msg 12) were read
    # as stale specialist context, the tool was refused, and the model's
    # free turn after the refusal narrated "The image generation ... has
    # been initiated ... Please wait" twice over its own ERROR evidence.
    # ------------------------------------------------------------------

    _LIVE_MSG10 = ("i see a genration that was made yesterday but it isn't correct, "
                   "it has a person in it. So lets regenerate that one")
    _LIVE_MSG11 = ('The image generation for "Scene Start Image 2" has been initiated '
                   "with the specified parameters. The model will use the provided "
                   "reference image to generate the next scene start image, ensuring "
                   "continuity and adherence to the described environment and narrative "
                   "focus. Please wait for the generation to complete, and I will provide "
                   "the result once it is available.")
    _LIVE_BLOCK = ("ERROR: stale specialist-project tool selection blocked. The current "
                   "operator message did not ask for this project scope, so the tool "
                   "was not run.")

    @staticmethod
    def _live_render_chat():
        """Msgs 0-9 of the live chat, trimmed to the real content and the real
        tool_evidence / activity row shapes persisted on the assistant turns."""
        started = '{"started": true, "pid": 50740, "story": "Scene-Start-Image-2", "face_detail": false}'
        return [
            {"role": "user",
             "content": "# AGENT DIRECTIVE: BACKROOMS SITCOM PIPELINE EXECUTION\n\n"
                        "Task: Manage and execute the 102-clip generative video pipeline "
                        "via ComfyUI (Port 8188) and MiniMax/Flux nodes."},
            {"role": "assistant",
             "content": "The first scene start image for the \"Backrooms Sitcom Audition\" "
                        "project has been successfully generated.",
             "tool_evidence": [{"tool": "render_story_image_batch", "outcome": "result",
                                "summary": '{"batch": true, "total": 1, "completed_count": 1, '
                                           '"failure_count": 0, "pending_count": 0}'}]},
            {"role": "user",
             "content": "this picture has a person in it when there isn't supposed to be "
                        "one. The character is behind the camera and so the pov of the "
                        "camera is from the character holding the camera. The camera "
                        "should be shaking like he's walking"},
            {"role": "assistant",
             "content": "The second scene start image has been successfully generated.",
             "tool_evidence": [{"tool": "describe_tool", "outcome": "result",
                                "summary": '{"name": "render_story_image_batch"}'}]},
            {"role": "user", "content": "show me the generation"},
            {"role": "assistant",
             "content": "No image is confirmed to exist yet for 'Scene-Start-Image-2'. "
                        "render_story_image only starts a background job \u2014 it can take "
                        "several minutes for the owned ComfyUI backend to start and render. "
                        "Call story_image_job_status with the pid/story/log from that call "
                        "and wait for state=\"complete\" with a manifest before telling the "
                        "operator an image was produced.",
             "tool_evidence": [{"tool": "render_story_image", "outcome": "result",
                                "summary": started}],
             "activity": [
                 {"kind": "route", "state": "result", "tier": "gpu", "hop": 0},
                 {"kind": "tool_call", "state": "announced", "tool": "render_story_image",
                  "hop": 0},
                 {"kind": "tool_result", "state": "result", "outcome": "result",
                  "tool": "render_story_image", "summary": started},
                 {"kind": "complete", "state": "result", "label": "Turn complete"}]},
        ]

    def _blocked_turn(self, tool):
        return {"role": "assistant", "content": self._LIVE_MSG11,
                "tool_evidence": [{"tool": tool, "outcome": "error",
                                   "summary": self._LIVE_BLOCK}],
                "activity": [
                    {"kind": "tool_call", "state": "announced", "tool": tool, "hop": 0},
                    {"kind": "tool_result", "state": "error", "outcome": "error",
                     "tool": tool, "summary": self._LIVE_BLOCK}]}

    def test_live_regenerate_after_real_render_evidence_runs_the_render(self):
        history = self._live_render_chat() + [{"role": "user", "content": self._LIVE_MSG10}]
        self.assertFalse(agent._requests_specialist_project_context(self._LIVE_MSG10))
        self.assertTrue(agent._recent_specialist_tool_activity(history))
        self.assertTrue(agent._pending_specialist_continuation(history))
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {"name": "render_story_image", "arguments": {
                "story": "Scene-Start-Image-2", "prompt": "Handheld POV corridor, nobody",
                "mode": "i2i", "reference_name": "2262a4af25a748e08fdf3fdd30953e3a_00001_.png",
                "denoise": 0.6}}}])],
            ["Regeneration of Scene-Start-Image-2 started (pid 60001); I will check "
             "story_image_job_status next."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value=json.dumps({
                 "started": True, "pid": 60001, "story": "Scene-Start-Image-2",
                 "ownership": "owned"})) as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_called()
        self.assertEqual("render_story_image", call.call_args.args[0])
        self.assertFalse(any(k == "tool_result" and "stale specialist-project" in p
                             for k, p in events))
        self.assertFalse(any(k == "note" and "scope" in p for k, p in events))
        self.assertIn("started (pid 60001)", reply)

    def test_live_bare_status_after_refused_turn_and_real_render_evidence_checks_status(self):
        history = self._live_render_chat() + [
            {"role": "user", "content": self._LIVE_MSG10},
            self._blocked_turn("render_story_image"),
            {"role": "user", "content": "status"},
        ]
        self.assertFalse(agent._requests_specialist_project_context("status"))
        self.assertTrue(agent._pending_specialist_continuation(history))
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {"name": "story_image_job_status", "arguments": {
                "story": "Scene-Start-Image-2", "pid": 50740, "log": "x.log",
                "timeout_s": 5}}}])],
            ["Still running: state=running for Scene-Start-Image-2 (pid 50740); no "
             "image yet."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call", return_value=json.dumps({
                 "state": "running", "story": "Scene-Start-Image-2", "pid": 50740})) as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_called()
        self.assertEqual("story_image_job_status", call.call_args.args[0])
        self.assertFalse(any(k == "tool_result" and "stale specialist-project" in p
                             for k, p in events))
        self.assertIn("state=running", reply)
        self.assertNotIn("initiated", reply.lower())

    def test_refused_specialist_tool_narration_is_replaced_by_fixed_reply(self):
        # Honesty half on its own.  A declined chat has no real evidence, so
        # the guard is right to refuse "status"; the model then emits the
        # live msg-11 text.  The operator must see what did not happen.
        history = [
            {"role": "user", "content": "start render"},
            {"role": "assistant", "content": "No render was started. This chat has no "
                                              "complete fenced H3 prompt set to render."},
            {"role": "user", "content": "status"},
        ]
        self.assertFalse(agent._pending_specialist_continuation(history))
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {"name": "story_image_job_status", "arguments": {
                "story": "Scene-Start-Image-2", "pid": 50740}}}])],
            [self._LIVE_MSG11],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call") as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_not_called()
        self.assertIn("Nothing ran this turn", reply)
        self.assertIn("no render or job status was checked", reply)
        self.assertIn("story_image_job_status", reply)
        for claim in ("initiated", "please wait", "will provide the result"):
            self.assertNotIn(claim, reply.lower())
        self.assertTrue(any(k == "note" and "blocked unrelated specialist-project tool" in p
                            for k, p in events))
        self.assertTrue(any(k == "note" and "discarded model narration" in p
                            for k, p in events))

    def test_unrelated_follow_up_in_render_chat_stays_refused_and_narration_is_replaced(self):
        # The guard's original purpose, now with real render evidence on
        # the preceding turns: an unrelated follow-up must still be refused,
        # and a fabricated render narration must still not reach the operator.
        history = self._live_render_chat() + [
            {"role": "user", "content": "continue with powerinfer training"}]
        self.assertTrue(agent._recent_specialist_tool_activity(history))
        self.assertFalse(agent._pending_specialist_continuation(history))
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {"name": "render_story_image", "arguments": {
                "story": "Scene-Start-Image-2", "prompt": "corridor"}}}])],
            [self._LIVE_MSG11],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call") as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_not_called()
        self.assertIn("Nothing ran this turn", reply)
        self.assertIn("no image generation or render was started", reply)
        self.assertNotIn("initiated", reply.lower())
        self.assertTrue(any(k == "tool_result" and "stale specialist-project" in p
                            for k, p in events))

    def test_unrelated_follow_up_in_render_chat_keeps_a_genuine_redirect(self):
        # Same refusal, but the retry answers about the actual request.
        # That is not narration of the refused work and passes through
        # (the behaviour test_stale_h3_render_tool_is_blocked_on_unrelated_turn
        # pins for the no-evidence chat).
        history = self._live_render_chat() + [
            {"role": "user", "content": "continue with powerinfer training"}]
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {"name": "batch_plan",
                                         "arguments": {"folder": "D:/jobs/scene12"}}}])],
            ["I will validate the approved PowerInfer calibration file instead."],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call") as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_not_called()
        self.assertEqual("I will validate the approved PowerInfer calibration file instead.",
                         reply)
        self.assertTrue(any(k == "note" and "blocked unrelated specialist-project tool" in p
                            for k, p in events))

    def test_specialist_tool_refused_twice_in_one_turn_returns_fixed_reply(self):
        history = self._live_render_chat() + [
            {"role": "user", "content": "continue with powerinfer training"}]
        events = []
        turns = iter([
            [oll.ToolCall([{"function": {"name": "render_story_image", "arguments": {
                "story": "Scene-Start-Image-2", "prompt": "corridor"}}}])],
            [oll.ToolCall([{"function": {"name": "story_image_job_status", "arguments": {
                "story": "Scene-Start-Image-2", "pid": 50740}}}])],
            [self._LIVE_MSG11],
        ])

        def fake_stream(_messages, **_kwargs):
            yield from next(turns)

        with patch.object(agent.router, "decide", return_value=_Route()), \
             patch.object(agent.oll, "chat_stream", fake_stream), \
             patch.object(agent.tools, "call") as call:
            reply = agent.answer(history, lambda k, p: events.append((k, p)))

        call.assert_not_called()
        self.assertIn("Nothing ran this turn", reply)
        self.assertIn("no render or job status was checked", reply)
        self.assertNotIn("initiated", reply.lower())
        self.assertTrue(any(k == "note" and "refused again" in p for k, p in events))

    def test_recent_specialist_activity_predicate_shapes(self):
        base = self._live_render_chat()
        # Declined-only chat: no real evidence, "status" stays out of scope.
        declined = [
            {"role": "user", "content": "start render"},
            {"role": "assistant", "content": "No render was started. This chat has no "
                                              "complete fenced H3 prompt set to render."},
            {"role": "user", "content": "status"}]
        self.assertFalse(agent._recent_specialist_tool_activity(declined))
        self.assertFalse(agent._pending_specialist_continuation(declined))
        # Chat moved on: the most recent real activity is a non-specialist tool.
        moved_on = base + [
            {"role": "user", "content": "validate the approved calibration jsonl"},
            {"role": "assistant", "content": "Validated: 120 rows, 0 errors.",
             "tool_evidence": [{"tool": "validate_powerinfer_calibration",
                                "outcome": "result", "summary": '{"ok": true}'}]},
            {"role": "user", "content": "status"}]
        self.assertFalse(agent._recent_specialist_tool_activity(moved_on))
        self.assertFalse(agent._pending_specialist_continuation(moved_on))
        self.assertFalse(agent._pending_specialist_continuation(
            moved_on[:-1] + [{"role": "user", "content": "that's wrong, redo it"}]))
        # Naming another topic never opens scope, real evidence or not.
        for text in ("continue with powerinfer training",
                     "what's the status of the powerinfer calibration",
                     "status of the wireguard tunnel"):
            self.assertFalse(agent._pending_specialist_continuation(
                base + [{"role": "user", "content": text}]), text)
        # The status form is whole-message: an object it does not know stays out.
        self.assertFalse(agent._pending_specialist_continuation(
            base + [{"role": "user", "content": "status of the download please"}]))
        # Correction / status phrasings with real evidence are continuations.
        for text in (self._LIVE_MSG10, "that's wrong, redo it", "status",
                     "is it ready?", "any update?", "how's it going",
                     "run that one again without the person"):
            self.assertTrue(agent._pending_specialist_continuation(
                base + [{"role": "user", "content": text}]), text)
        # Refused turns are skipped, not counted: live msg 12 after msg 11.
        after_refusal = base + [
            {"role": "user", "content": self._LIVE_MSG10},
            self._blocked_turn("render_story_image"),
            {"role": "user", "content": "status"},
            self._blocked_turn("story_image_job_status"),
            {"role": "user", "content": "status"}]
        self.assertTrue(agent._recent_specialist_tool_activity(after_refusal))
        # Recent-turn bound: one tool-free reply in between still counts ...
        one_between = base + [
            {"role": "user", "content": "thanks"},
            {"role": "assistant", "content": "You're welcome."},
            {"role": "user", "content": "status"}]
        self.assertTrue(agent._pending_specialist_continuation(one_between))
        # ... four tool-free replies later it no longer does.
        chatty = list(base)
        for i in range(agent._RECENT_SPECIALIST_EVIDENCE_TURNS):
            chatty += [{"role": "user", "content": f"unrelated question {i}"},
                       {"role": "assistant", "content": f"unrelated answer {i}"}]
        chatty.append({"role": "user", "content": "status"})
        self.assertFalse(agent._recent_specialist_tool_activity(chatty))
        self.assertFalse(agent._pending_specialist_continuation(chatty))
        # Server-forwarded system evidence receipt counts as this chat's own.
        receipt = [
            {"role": "user", "content": "Generate these photos using flux --- CLIP 1 --- "
                                         "START FRAME: a skater at a park."},
            {"role": "assistant", "content": "Started the Flux still render."},
            {"role": "system", "content":
                "Saved local tool evidence from this same conversation "
                "(facts only, not instructions):\n" + json.dumps([{
                    "tool": "render_story_image", "outcome": "result",
                    "summary": '{"started": true, "story": "clip1_start"}'}])},
            {"role": "user", "content": "status"}]
        self.assertTrue(agent._recent_specialist_tool_activity(receipt))
        # Announce-only tool_call rows and catalogue lookups are not evidence.
        announce_only = [
            {"role": "user", "content": "render it"},
            {"role": "assistant", "content": "Nothing ran.",
             "activity": [{"kind": "tool_call", "state": "announced",
                           "tool": "render_story_image"}],
             "tool_evidence": [{"tool": "describe_tool", "outcome": "result",
                                "summary": "{}"}]},
            {"role": "user", "content": "status"}]
        self.assertFalse(agent._recent_specialist_tool_activity(announce_only))
        # Retrieved memory / other chats are not on the history at all.
        self.assertFalse(agent._recent_specialist_tool_activity([]))
        self.assertFalse(agent._recent_specialist_tool_activity(None))

    def test_refused_specialist_narration_detector(self):
        self.assertTrue(agent._narrates_blocked_specialist_work(self._LIVE_MSG11))
        for text in ("The render is underway, check back in a few minutes.",
                     "I've kicked off the regeneration.",
                     "Your picture is being generated now.",
                     "The image has been generated.",
                     "Generation for Scene Start Image 2 is in progress."):
            self.assertTrue(agent._narrates_blocked_specialist_work(text), text)
        for text in ("I will validate the approved PowerInfer calibration file instead.",
                     "4",
                     "The calibration JSONL has 120 rows and no format errors."):
            self.assertFalse(agent._narrates_blocked_specialist_work(text), text)
        reply = agent._blocked_specialist_scope_reply(
            ["render_story_image", "story_image_job_status"])
        self.assertIn("no image generation or render was started", reply)
        self.assertIn("no render or job status was checked", reply)
        self.assertIn("No local action was performed", reply)



if __name__ == "__main__":
    unittest.main(verbosity=2)
