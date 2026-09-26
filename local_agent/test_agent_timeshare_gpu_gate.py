#!/usr/bin/env python3
"""Sidebar gpu_gate before an idle-8188 timeshare claim. No live ComfyUI."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent  # noqa: E402
import router  # noqa: E402


class _Route:
    tier = "cpu"
    host = router.CPU_HOST
    model = router.FALLBACK_REASONING_MODEL
    gpu_busy = True
    reason = "pending gate"
    detail = {}
    backend = "ollama"

    def options(self):
        return {"num_gpu": 0}

    def as_dict(self):
        return {"tier": self.tier, "host": self.host, "model": self.model,
                "backend": self.backend, "gpu_busy": self.gpu_busy,
                "reason": self.reason}


class TimeshareSidebarGateTests(unittest.TestCase):
    def test_predicate_true_for_idle_8188_host_gpu(self):
        with patch.object(router, "_timeshare_enabled", return_value=True), \
             patch.object(router, "_owners_idle_for_timeshare",
                          return_value=(True, "released")):
            self.assertTrue(agent.timeshare_claim_needs_sidebar_gate(
                "auto", None, "hello there",
                gpu_busy=True,
                gpu_detail={"comfy_port_8188": "listening"}))

    def test_predicate_false_live_owner(self):
        with patch.object(router, "_timeshare_enabled", return_value=True), \
             patch.object(router, "_owners_idle_for_timeshare",
                          return_value=(False, "live pid")):
            self.assertFalse(agent.timeshare_claim_needs_sidebar_gate(
                "auto", None, "hello there",
                gpu_busy=True,
                gpu_detail={"comfy_port_8188": "listening"}))

    def test_predicate_false_qwythos_and_cpu_only(self):
        with patch.object(router, "_timeshare_enabled", return_value=True), \
             patch.object(router, "_owners_idle_for_timeshare",
                          return_value=(True, "released")):
            self.assertFalse(agent.timeshare_claim_needs_sidebar_gate(
                "auto", router.QWYTHOS_MODEL, "hello",
                gpu_busy=True,
                gpu_detail={"comfy_port_8188": "listening"}))
            self.assertFalse(agent.timeshare_claim_needs_sidebar_gate(
                "auto", "equal-shares-cpu", "hello",
                gpu_busy=True,
                gpu_detail={"comfy_port_8188": "listening"}))

    def test_predicate_false_farm_tool_turn(self):
        with patch.object(router, "_timeshare_enabled", return_value=True), \
             patch.object(router, "_owners_idle_for_timeshare",
                          return_value=(True, "released")):
            self.assertFalse(agent.timeshare_claim_needs_sidebar_gate(
                "auto", None, "list the files in the current folder",
                gpu_busy=True,
                gpu_detail={"comfy_port_8188": "listening"},
                farm_tool_turn=True))

    def test_answer_requests_sidebar_before_hop0_decide(self):
        notes = []
        gate = MagicMock(return_value={
            "granted": False, "mode": "ask",
            "request": {"workload": "chat reasoning model load", "id": "gpu_test"},
        })
        decide = MagicMock(return_value=_Route())

        def on_event(kind, payload):
            if kind == "note":
                notes.append(payload)

        with patch.object(agent.router, "gpu_busy",
                          return_value=(True, "8188",
                                        {"comfy_port_8188": "listening"})), \
             patch.object(agent.router, "_timeshare_enabled", return_value=True), \
             patch.object(agent.router, "_owners_idle_for_timeshare",
                          return_value=(True, "released")), \
             patch.object(agent.router, "up", return_value=True), \
             patch.object(agent.router, "decide", decide), \
             patch.object(agent.router, "_running_models", return_value=[]), \
             patch.object(agent.router, "_tags",
                          return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch("gpu_gate.request", gate), \
             patch.object(agent.action_resolver, "classify", return_value=None), \
             patch.object(agent.oll, "chat_stream",
                          return_value=iter(["cpu reply"])):
            reply = agent.answer(
                [{"role": "user", "content":
                  "Please architect a refactor of the repository and compare "
                  "the end-to-end workflow against the current implementation."}],
                on_event=on_event, prefer="auto",
                model=router.PRIMARY_REASONING_MODEL)
        self.assertEqual("cpu reply", reply)
        self.assertTrue(gate.called)
        self.assertTrue(decide.called)
        self.assertEqual("cpu", decide.call_args[0][0])
        self.assertTrue(any("sidebar" in n.lower() for n in notes))


if __name__ == "__main__":
    unittest.main()
