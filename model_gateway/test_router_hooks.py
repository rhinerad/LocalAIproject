"""Tests for the plan-only hooks in local_agent/router.py, planner.py and agent.py.

Same stubbing style as local_agent/test_router_switching.py: patch the GPU
probes and Ollama catalogue, never touch the network. The core guarantee is
asserted directly: no Decision ever carries a cloud backend, the local
routing is unchanged, and a heavy-logic turn merely gets a
``needs_cloud_plan`` flag that the agent turns into a system message.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local_agent"))

import router  # noqa: E402
import ollama_client as oll  # noqa: E402
import model_gateway as gw  # noqa: E402
import planner  # noqa: E402
import agent  # noqa: E402

LOGIC_PROMPT = ("Please architect and refactor the retrieval pipeline end-to-end, "
                "then debug the orchestration plan and compare approaches.")
TOOL_PROMPT = "list the files in the project folder"
INSTALLED = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL,
             router.DEEPSEEK_MODEL, "qwen2.5-coder:14b"]

CLOUD_ENV = {"MODEL_GATEWAY_CLOUD": "1", "ANTHROPIC_API_KEY": "sk-test",
             "MODEL_GATEWAY_ENV_FILE": os.devnull}
LOCAL_ENV = {"MODEL_GATEWAY_CLOUD": "0", "ANTHROPIC_API_KEY": "",
             "MODEL_GATEWAY_ENV_FILE": os.devnull}


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        for name in ("GPU_OWNED_FILE", "MEDIA_PRESSURE_FILE", "CHAT_BUSY_FILE"):
            p = patch.object(router, name, Path(self._tmp.name) / f"{name}.json")
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(router, "prepare_gpu_model",
                         return_value={"verified": True, "reason": "stub"})
        self.prepare = p.start()
        self.addCleanup(p.stop)
        p = patch.object(router, "evict_gpu_residents",
                         return_value={"verified": True, "attempted": [], "remaining": []})
        self.evict = p.start()
        self.addCleanup(p.stop)
        for name, value in (("_farm_reachable", False), ("thermal_blocks_gpu", None)):
            p = patch.object(router, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def env(self, values):
        p = patch.dict(os.environ, values, clear=False)
        p.start()
        self.addCleanup(p.stop)

    def idle(self):
        return patch.multiple(router,
                              gpu_busy=lambda: (False, "GPU idle", {"state": "idle"}),
                              up=lambda host: True,
                              _tags=lambda host: list(INSTALLED),
                              _running_models=lambda host: [])

    def busy(self):
        return patch.multiple(router,
                              gpu_busy=lambda: (True, "a ComfyUI backend is listening on port 8188",
                                                {"comfy_port_8188": "listening"}),
                              up=lambda host: True,
                              _tags=lambda host: list(INSTALLED),
                              _running_models=lambda host: [])


class DecideTests(_Base):
    def test_logic_turn_is_flagged_but_routed_locally(self):
        self.env(CLOUD_ENV)
        with self.idle():
            d = router.decide("auto", prompt=LOGIC_PROMPT)
        self.assertEqual("ollama", d.backend)
        self.assertEqual("gpu", d.tier)
        self.assertEqual(router.DEEPSEEK_MODEL, d.model)      # unchanged local routing
        self.assertTrue(d.detail["needs_cloud_plan"])
        self.assertEqual("claude-opus-5-5", d.detail["cloud_plan"]["model"])
        self.assertNotIn("anthropic", (d.host, d.backend))

    def test_no_decision_ever_has_a_cloud_backend(self):
        self.env(CLOUD_ENV)
        for prompt in (LOGIC_PROMPT, TOOL_PROMPT, None):
            for state in (self.idle, self.busy):
                with state():
                    d = router.decide("auto", prompt=prompt)
                self.assertIn(d.backend, {"ollama", "powerinfer", "farm"})
                self.assertIn(d.tier, {"gpu", "cpu", "farm"})

    def test_tool_turn_not_flagged(self):
        self.env(CLOUD_ENV)
        with self.idle():
            d = router.decide("auto", prompt=TOOL_PROMPT)
        self.assertNotIn("needs_cloud_plan", d.detail)

    def test_busy_gpu_logic_turn_routes_cpu_and_is_flagged(self):
        self.env(CLOUD_ENV)
        with self.busy():
            d = router.decide("auto", prompt=LOGIC_PROMPT)
        self.assertEqual("cpu", d.tier)
        self.assertTrue(d.detail.get("needs_cloud_plan"))
        self.evict.assert_called_once()   # the normal yield-to-render rule, unchanged

    def test_cloud_disabled_keeps_legacy_routing(self):
        self.env(LOCAL_ENV)
        with self.idle():
            d = router.decide("auto", prompt=LOGIC_PROMPT)
        self.assertNotIn("needs_cloud_plan", d.detail)
        self.assertEqual(router.DEEPSEEK_MODEL, d.model)

    def test_prefer_cpu_not_flagged(self):
        self.env(CLOUD_ENV)
        with self.idle():
            d = router.decide("cpu", prompt=LOGIC_PROMPT)
        self.assertEqual("cpu", d.tier)
        self.assertNotIn("needs_cloud_plan", d.detail)

    def test_no_prompt_callers_not_flagged(self):
        self.env(CLOUD_ENV)
        with self.idle():
            d = router.decide("auto")
        self.assertNotIn("needs_cloud_plan", d.detail)

    def test_allow_cloud_false_not_flagged(self):
        self.env(CLOUD_ENV)
        with self.idle():
            d = router.decide("auto", prompt=LOGIC_PROMPT, allow_cloud=False)
        self.assertNotIn("needs_cloud_plan", d.detail)

    def test_planner_passes_allow_cloud_false_and_includes_guidance(self):
        self.env(CLOUD_ENV)
        seen = {}

        def fake_chat(messages, **kw):
            seen["messages"] = messages
            raise oll.OllamaUnavailable("stub")
        with self.idle(), patch.object(router, "decide", wraps=router.decide) as decide, \
                patch.object(oll, "chat", side_effect=fake_chat):
            planner.propose(LOGIC_PROMPT, prefer="auto", guidance="1. read\n2. edit")
        self.assertFalse(decide.call_args.kwargs["allow_cloud"])
        self.assertIn("Guidance from the planning model", seen["messages"][1]["content"])
        self.assertIn("1. read", seen["messages"][1]["content"])


class PickerAndStatusTests(_Base):
    def test_picker_has_no_cloud_rows(self):
        self.env(CLOUD_ENV)
        with self.idle():
            names = {m["name"] for m in router.chat_models()}
        self.assertFalse(any(n.startswith("cloud-") or n.startswith("claude-") for n in names))

    def test_status_has_gateway_block_without_key_leak(self):
        self.env(CLOUD_ENV)
        with self.idle():
            s = router.status()
        self.assertEqual("plan-only", s["model_gateway"]["mode"])
        self.assertTrue(s["model_gateway"]["planning_available"])
        self.assertNotIn("sk-test", str(s))

    def test_fallback_after_primary_failure_unchanged(self):
        self.env(CLOUD_ENV)
        with self.idle(), patch.object(router, "unload", return_value=True):
            previous = router.Decision("gpu", router.GPU_HOST, router.PRIMARY_REASONING_MODEL,
                                       False, "x", {})
            d = router.fallback_after_primary_failure(previous, RuntimeError("oom"))
        self.assertEqual(router.FALLBACK_REASONING_MODEL, d.model)


class OllamaClientTests(_Base):
    def test_cloud_dispatch_removed(self):
        self.assertFalse(hasattr(oll, "_is_cloud_host"))
        self.assertFalse(hasattr(oll, "_cloud_chat_stream"))
        with patch.object(oll.urllib.request, "urlopen", side_effect=AssertionError("stub")):
            with self.assertRaises(AssertionError):
                list(oll.chat_stream([{"role": "user", "content": "x"}], model="m",
                                     host="anthropic://api.anthropic.com"))


class AgentHookTests(_Base):
    def _run(self, plan_result):
        events: list[tuple[str, str]] = []
        msgs = [{"role": "system", "content": "sys"},
                {"role": "user", "content": "earlier question with <file contents>"},
                {"role": "assistant", "content": "earlier answer"},
                {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "a"}}]},
                {"role": "tool", "name": "a", "content": "secret tool output"},
                {"role": "user", "content": LOGIC_PROMPT}]
        route = router.Decision("gpu", router.GPU_HOST, router.DEEPSEEK_MODEL, False, "x",
                                {"needs_cloud_plan": True})
        schemas = [{"type": "function", "function": {"name": "read_file", "parameters": {}}},
                   {"type": "function", "function": {"name": "list_dir", "parameters": {}}}]
        captured = {}

        def fake_request_plan(prompt, context_summary="", tool_names=()):
            captured.update(prompt=prompt, context=context_summary, tools=list(tool_names))
            return plan_result
        with patch.object(gw, "request_plan", side_effect=fake_request_plan):
            agent._request_cloud_plan(LOGIC_PROMPT, msgs, schemas, route,
                                      lambda kind, payload: events.append((kind, payload)))
        return msgs, route, events, captured

    def test_plan_injected_as_system_message(self):
        msgs, route, events, captured = self._run("1. Read router.py\n2. Edit")
        self.assertEqual("system", msgs[1]["role"])
        self.assertIn("Plan from planning model", msgs[1]["content"])
        self.assertIn("1. Read router.py", msgs[1]["content"])
        self.assertEqual("cloud", route.detail["plan_source"])
        self.assertIn(("note", "cloud plan received"), events)
        self.assertEqual(["read_file", "list_dir"], captured["tools"])
        self.assertEqual(LOGIC_PROMPT, captured["prompt"])

    def test_context_summary_excludes_user_tool_and_system_text(self):
        _, _, _, captured = self._run("plan")
        self.assertIn("earlier answer", captured["context"])
        self.assertNotIn("file contents", captured["context"])
        self.assertNotIn("secret tool output", captured["context"])
        self.assertNotIn("sys", captured["context"].split("assistant:")[0])

    def test_no_plan_continues_locally(self):
        msgs, route, events, _ = self._run(None)
        self.assertEqual("user", msgs[1]["role"])          # nothing inserted
        self.assertEqual("none", route.detail["plan_source"])
        self.assertIn(("note", "cloud plan unavailable; continuing locally"), events)

    def test_request_plan_exception_never_escapes(self):
        events = []
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": LOGIC_PROMPT}]
        route = router.Decision("gpu", router.GPU_HOST, "m", False, "x", {"needs_cloud_plan": True})
        with patch.object(gw, "request_plan", side_effect=RuntimeError("boom")):
            agent._request_cloud_plan(LOGIC_PROMPT, msgs, [], route,
                                      lambda k, p: events.append((k, p)))
        self.assertEqual("none", route.detail["plan_source"])
        self.assertEqual(2, len(msgs))

    def test_route_event_carries_plan_source(self):
        route = router.Decision("gpu", router.GPU_HOST, "m", False, "x",
                                {"needs_cloud_plan": True, "plan_source": "cloud"})
        self.assertEqual("cloud", json.loads(json.dumps(route.as_dict()))["detail"]["plan_source"])


if __name__ == "__main__":
    unittest.main()
