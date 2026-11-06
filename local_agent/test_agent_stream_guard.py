#!/usr/bin/env python3
"""Audit 2026-11-02 findings 10/15/18: mid-stream render guard, context trim
headroom, chat_busy refcount, and the knowledge-pack RuntimeError."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent  # noqa: E402
import router  # noqa: E402

GPU_MODEL = router.PRIMARY_REASONING_MODEL
CPU_MODEL = "equal-shares-cpu"


class _Route:
    def __init__(self, tier, host, model, backend="ollama", gpu_busy=False):
        self.tier, self.host, self.model, self.backend = tier, host, model, backend
        self.gpu_busy, self.reason, self.detail = gpu_busy, f"{tier} test route", {}

    def options(self):
        return {"num_gpu": 99 if self.tier == "gpu" else 0, "num_ctx": 8192}

    def as_dict(self):
        return {"tier": self.tier, "host": self.host, "model": self.model,
                "backend": self.backend, "gpu_busy": self.gpu_busy, "reason": self.reason}


class RenderClaimedGpuSignalTests(unittest.TestCase):
    def test_owner_file_wins_without_touching_comfy(self) -> None:
        with patch.object(agent.router, "queue_owner", return_value=(True, "live pid 7")), \
             patch.object(agent.router, "comfy_listening", side_effect=AssertionError("probed")), \
             patch.object(agent.router, "gpu_busy", side_effect=AssertionError("nvidia-smi")):
            self.assertEqual((True, "live pid 7"), agent.render_claimed_gpu())

    def test_queue_is_consulted_only_when_comfy_listens(self) -> None:
        with patch.object(agent.router, "queue_owner", return_value=(False, "released")), \
             patch.object(agent.router, "comfy_listening", return_value=False), \
             patch.object(agent.router, "_comfy_queue_idle", side_effect=AssertionError("probed")), \
             patch.object(agent.router, "gpu_busy", side_effect=AssertionError("nvidia-smi")):
            self.assertEqual((False, ""), agent.render_claimed_gpu())
        with patch.object(agent.router, "queue_owner", return_value=(False, "released")), \
             patch.object(agent.router, "comfy_listening", return_value=True), \
             patch.object(agent.router, "_comfy_queue_idle", return_value=(False, '{"running": 1}')), \
             patch.object(agent.router, "gpu_busy", side_effect=AssertionError("nvidia-smi")):
            claimed, why = agent.render_claimed_gpu()
        self.assertTrue(claimed)
        self.assertIn("not idle", why)
        with patch.object(agent.router, "queue_owner", return_value=(False, "released")), \
             patch.object(agent.router, "comfy_listening", return_value=True), \
             patch.object(agent.router, "_comfy_queue_idle", return_value=(True, "{}")):
            self.assertEqual((False, ""), agent.render_claimed_gpu())


class StreamRenderGuardTests(unittest.TestCase):
    def _run(self, *, first_route, owner, check_seconds=0):
        gpu_route = _Route("gpu", router.GPU_HOST, GPU_MODEL)
        cpu_route = _Route("cpu", router.CPU_HOST, CPU_MODEL)
        streams: list[str] = []
        events: list[tuple[str, str]] = []

        def fake_decide(prefer, *_a, **_k):
            return cpu_route if prefer == "cpu" else first_route

        def fake_stream(_msgs, model=None, **_k):
            streams.append(str(model))
            if model == GPU_MODEL:
                yield "gpu "
                yield "partial"
            else:
                yield "cpu reply"

        evict = MagicMock(return_value={"verified": True})
        with patch.object(agent, "STREAM_RENDER_CHECK_SECONDS", check_seconds), \
             patch.object(agent.router, "queue_owner", owner), \
             patch.object(agent.router, "comfy_listening", return_value=False), \
             patch.object(agent.router, "gpu_busy", return_value=(False, "free", {})), \
             patch.object(agent.router, "up", return_value=True), \
             patch.object(agent.router, "decide", side_effect=fake_decide), \
             patch.object(agent.router, "_running_models", return_value=[GPU_MODEL]), \
             patch.object(agent.router, "_tags", return_value=[GPU_MODEL, CPU_MODEL]), \
             patch.object(agent.router, "evict_gpu_residents", evict), \
             patch("gpu_gate.request", return_value={"granted": True, "mode": "allow"}), \
             patch.object(agent.action_resolver, "classify", return_value=None), \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer([{"role": "user", "content": "Where is TODO.md?"}],
                                 on_event=lambda k, p: events.append((k, p)),
                                 prefer="auto", model=GPU_MODEL)
        return reply, streams, events, evict

    def test_render_claim_mid_stream_switches_the_hop_to_cpu(self) -> None:
        owner = MagicMock(return_value=(True, "render queue claimed by live pid 42 (batch)"))
        reply, streams, events, evict = self._run(
            first_route=_Route("gpu", router.GPU_HOST, GPU_MODEL), owner=owner)
        self.assertEqual("cpu reply", reply)
        self.assertEqual([GPU_MODEL, CPU_MODEL], streams)
        evict.assert_called_once()
        self.assertTrue(owner.called)
        notes = [p for k, p in events if k == "note"]
        self.assertTrue(any("render claimed the GPU" in n for n in notes), notes)
        routes = [json.loads(p) for k, p in events if k == "route"]
        self.assertEqual("cpu", routes[-1]["tier"])
        # The abandoned GPU tokens never reached the operator's reply.
        self.assertNotIn("partial", reply)

    def test_guard_is_silent_when_no_render_claims_the_gpu(self) -> None:
        owner = MagicMock(return_value=(False, "queue owner released"))
        reply, streams, _events, evict = self._run(
            first_route=_Route("gpu", router.GPU_HOST, GPU_MODEL), owner=owner)
        self.assertEqual("gpu partial", reply)
        self.assertEqual([GPU_MODEL], streams)
        evict.assert_not_called()
        self.assertTrue(owner.called)

    def test_guard_does_not_run_on_the_cpu_route(self) -> None:
        owner = MagicMock(side_effect=AssertionError("owner file probed on CPU route"))
        reply, streams, _events, evict = self._run(
            first_route=_Route("cpu", router.CPU_HOST, CPU_MODEL), owner=owner)
        self.assertEqual("cpu reply", reply)
        self.assertEqual([CPU_MODEL], streams)
        evict.assert_not_called()

    def test_guard_can_be_disabled(self) -> None:
        owner = MagicMock(return_value=(True, "live pid 42"))
        reply, streams, _events, evict = self._run(
            first_route=_Route("gpu", router.GPU_HOST, GPU_MODEL), owner=owner,
            check_seconds=None)
        self.assertEqual("gpu partial", reply)
        self.assertEqual([GPU_MODEL], streams)
        owner.assert_not_called()


class ChatBusyRefcountTests(unittest.TestCase):
    def setUp(self) -> None:
        agent._chat_busy_depth = 0

    def test_marker_set_on_first_enter_and_cleared_on_last_exit(self) -> None:
        with patch.object(agent.router, "set_chat_busy") as busy:
            self.assertEqual(1, agent._chat_busy_enter())
            self.assertEqual(2, agent._chat_busy_enter())
            self.assertEqual(1, agent._chat_busy_exit())
            self.assertEqual([call(True)], busy.call_args_list)
            self.assertEqual(0, agent._chat_busy_exit())
            self.assertEqual([call(True), call(False)], busy.call_args_list)
            # An unbalanced extra exit never goes negative or re-signals.
            self.assertEqual(0, agent._chat_busy_exit())
            self.assertEqual([call(True), call(False)], busy.call_args_list)

    def test_guard_keeps_the_marker_while_an_inner_turn_still_runs(self) -> None:
        order: list = []

        @agent._chat_busy_guard
        def inner():
            order.append("inner")

        @agent._chat_busy_guard
        def outer():
            inner()
            order.append("outer")

        with patch.object(agent.router, "set_chat_busy", side_effect=lambda v: order.append(v)):
            outer()
        self.assertEqual([True, "inner", "outer", False], order)

    def test_failed_marker_write_does_not_strand_the_refcount(self) -> None:
        with patch.object(agent.router, "set_chat_busy", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                agent._chat_busy_enter()
        self.assertEqual(0, agent._chat_busy_depth)


class KnowledgePackTests(unittest.TestCase):
    def test_missing_pack_is_a_runtime_error_not_system_exit(self) -> None:
        with tempfile.TemporaryDirectory() as td, \
             patch.object(agent, "KNOWLEDGE", Path(td) / "missing_pack.md"):
            with self.assertRaises(RuntimeError):
                agent.system_prompt([{"role": "user", "content": "hi"}])


class ContextFitTests(unittest.TestCase):
    def setUp(self) -> None:
        p1 = patch.object(agent.context_compactor, "summarize_old_messages",
                          return_value={"goal": "keep going", "decisions": [], "open_questions": [],
                                        "tool_state": [], "hard_constraints": [], "notable_files": []})
        p2 = patch.object(agent.compaction_prefetch, "consume", return_value=None)
        p1.start(); p2.start()
        self.addCleanup(p1.stop); self.addCleanup(p2.stop)

    def test_budget_reserves_room_for_the_reply(self) -> None:
        self.assertEqual(8192 - 2048, agent._context_budget(8192))
        self.assertEqual(4096 - 1024, agent._context_budget(4096))
        self.assertEqual(32768 - 2048, agent._context_budget(32768))
        self.assertEqual(1, agent._context_budget(1))

    def _history(self) -> list[dict]:
        return [{"role": "system", "content": "policy " * 20},
                {"role": "user", "content": "A" * 4000},
                {"role": "assistant", "content": "B" * 4000},
                {"role": "user", "content": "C" * 4000},
                {"role": "assistant", "content": "D" * 4000},
                {"role": "user", "content": "E" * 4000},
                {"role": "assistant", "content": "F" * 4000},
                {"role": "user", "content": "what model is active now?"}]

    def test_fit_loops_until_the_prompt_fits_the_budget(self) -> None:
        notes: list[str] = []
        num_ctx = 1200
        out = agent._fit_context(self._history(), num_ctx, [], lambda k, t: notes.append(t))
        budget = agent._context_budget(num_ctx)
        self.assertLessEqual(router.estimate_context_tokens(out, []), budget)
        self.assertEqual("system", out[0]["role"])
        self.assertEqual("what model is active now?", out[-1]["content"])
        self.assertTrue(any("context compacted" in n for n in notes), notes)
        self.assertTrue(any("trimmed further" in n for n in notes), notes)
        self.assertFalse(any("still exceeds" in n for n in notes), notes)

    def test_fit_stops_at_system_plus_last_user_and_says_so(self) -> None:
        notes: list[str] = []
        out = agent._fit_context(self._history(), 8, [], lambda k, t: notes.append(t))
        self.assertEqual(["system", "user"], [m["role"] for m in out])
        self.assertEqual("what model is active now?", out[-1]["content"])
        self.assertTrue(any("still exceeds" in n for n in notes), notes)

    def test_fit_is_a_no_op_when_the_prompt_already_fits(self) -> None:
        history = self._history()
        notes: list[str] = []
        out = agent._fit_context(history, 200_000, [], lambda k, t: notes.append(t))
        self.assertIs(history, out)
        self.assertEqual([], notes)

    def test_drop_oldest_keeps_tool_call_and_results_together(self) -> None:
        msgs = [{"role": "system", "content": "s"},
                {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "x"}}]},
                {"role": "tool", "content": "r1"},
                {"role": "tool", "content": "r2"},
                {"role": "assistant", "content": "done"},
                {"role": "user", "content": "next"}]
        out = agent._drop_oldest_body_message(msgs)
        self.assertEqual(["system", "assistant", "user"], [m["role"] for m in out])
        out = agent._drop_oldest_body_message(out)
        self.assertEqual(["system", "user"], [m["role"] for m in out])
        self.assertIsNone(agent._drop_oldest_body_message(out))

    def test_answer_trims_when_over_budget_but_under_num_ctx(self) -> None:
        """The old code trimmed only above num_ctx; now the reserve triggers it."""
        seen: dict = {}
        cpu_route = _Route("cpu", router.CPU_HOST, CPU_MODEL)

        def fake_stream(msgs, **_k):
            seen["tokens"] = router.estimate_context_tokens(msgs, [])
            yield "ok"

        history = [{"role": "user", "content": "x" * 3000}, {"role": "assistant", "content": "y" * 3000},
                   {"role": "user", "content": "z" * 3000}, {"role": "assistant", "content": "w" * 3000},
                   {"role": "user", "content": "what next?"}]
        with patch.object(agent.router, "decide", return_value=cpu_route), \
             patch.object(agent.router, "gpu_busy", return_value=(True, "render", {})), \
             patch.object(agent.router, "up", return_value=True), \
             patch.object(agent.action_resolver, "classify", return_value=None), \
             patch.object(agent, "_fit_context", wraps=agent._fit_context) as fit, \
             patch.object(agent.oll, "chat_stream", fake_stream):
            reply = agent.answer(history, on_event=lambda k, p: None, prefer="cpu",
                                 model=CPU_MODEL, ctx_ceiling=4096)
        self.assertEqual("ok", reply)
        self.assertTrue(fit.called)
        self.assertLessEqual(seen["tokens"], agent._context_budget(4096))


if __name__ == "__main__":
    unittest.main()
