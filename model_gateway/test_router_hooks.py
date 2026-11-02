"""Tests for the minimal hooks in local_agent/router.py and ollama_client.py.

Same stubbing style as local_agent/test_router_switching.py: patch the GPU
probes and Ollama catalogue, never touch the network. The VRAM invariant is
asserted directly: a cloud Decision is produced without ``prepare_gpu_model``
or any ``/api/chat`` request.
"""
from __future__ import annotations

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
        p = patch.object(router, "_farm_reachable", return_value=False)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(router, "thermal_blocks_gpu", return_value=None)
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
    def test_logic_turn_routes_to_cloud_heavy_without_local_load(self):
        self.env(CLOUD_ENV)
        with self.idle():
            d = router.decide("auto", prompt=LOGIC_PROMPT)
        self.assertEqual(("cloud", "anthropic"), (d.tier, d.backend))
        self.assertEqual("claude-opus-5-5", d.model)
        self.assertEqual("anthropic://api.anthropic.com", d.host)
        self.assertEqual("logic", d.detail["capability"])
        self.assertEqual({"effort": "high", "max_tokens": 16000}, d.options())
        self.prepare.assert_not_called()
        self.evict.assert_not_called()

    def test_tool_turn_idle_gpu_stays_local(self):
        self.env(CLOUD_ENV)
        with self.idle():
            d = router.decide("auto", prompt=TOOL_PROMPT)
        self.assertNotEqual("anthropic", d.backend)
        self.assertEqual("gpu", d.tier)

    def test_busy_gpu_tool_turn_goes_cloud_fast_and_yields_vram(self):
        self.env(CLOUD_ENV)
        with self.busy():
            d = router.decide("auto", prompt=TOOL_PROMPT)
        self.assertEqual(("cloud", "claude-sonnet-5-5"), (d.tier, d.model))
        self.assertTrue(d.gpu_busy)
        self.assertIn("8188", d.reason)
        self.evict.assert_called_once()          # same yield-to-render rule as CPU
        self.prepare.assert_not_called()
        self.assertIn("gpu_eviction", d.detail)

    def test_status_poll_does_not_evict(self):
        self.env(CLOUD_ENV)
        with self.busy():
            d = router.decide("auto", prompt=TOOL_PROMPT, ensure_gpu_evicted=False)
        self.assertEqual("anthropic", d.backend)
        self.evict.assert_not_called()

    def test_cloud_disabled_keeps_legacy_routing(self):
        self.env(LOCAL_ENV)
        with self.idle():
            d = router.decide("auto", prompt=LOGIC_PROMPT)
        self.assertNotEqual("anthropic", d.backend)
        self.assertNotIn("gateway", d.detail)

    def test_prefer_cpu_stays_local(self):
        self.env(CLOUD_ENV)
        with self.busy():
            d = router.decide("cpu", prompt=LOGIC_PROMPT)
        self.assertEqual("cpu", d.tier)

    def test_no_prompt_callers_stay_local(self):
        self.env(CLOUD_ENV)
        with self.busy():
            d = router.decide("auto")
        self.assertNotEqual("anthropic", d.backend)

    def test_cloud_pin_and_refusal(self):
        self.env(CLOUD_ENV)
        with self.idle():
            d = router.decide("auto", model="cloud-fast", prompt="hi")
        self.assertEqual(("anthropic", "claude-sonnet-5-5"), (d.backend, d.model))
        self.env(LOCAL_ENV)
        with self.idle():
            d = router.decide("auto", model="cloud-heavy", prompt="hi")
        self.assertEqual("anthropic", d.backend)
        self.assertIsNone(d.model)
        self.assertIn("cannot run", d.reason)

    def test_allow_cloud_false_routes_cloud_pin_locally(self):
        self.env(CLOUD_ENV)
        with self.idle():
            d = router.decide("auto", model="cloud-heavy", prompt=LOGIC_PROMPT, allow_cloud=False)
        self.assertNotEqual("anthropic", d.backend)
        self.assertEqual("cloud-heavy", d.detail.get("cloud_pin_ignored"))
        self.assertIsNotNone(d.model)

    def test_planner_passes_allow_cloud_false(self):
        self.env(CLOUD_ENV)
        with self.idle(), patch.object(router, "decide", wraps=router.decide) as decide, \
                patch.object(oll, "chat", side_effect=oll.OllamaUnavailable("stub")):
            planner.propose(LOGIC_PROMPT, prefer="auto", model="cloud-heavy")
        self.assertFalse(decide.call_args.kwargs["allow_cloud"])


class FallbackTests(_Base):
    def test_cloud_failure_falls_back_locally_with_note(self):
        self.env(CLOUD_ENV)
        with self.idle():
            cloud = router.decide("auto", prompt=LOGIC_PROMPT)
            err = oll.OllamaModelFailure("cloud tier unavailable (offline): refused")
            err.gateway_kind = "offline"
            local = router.fallback_after_primary_failure(cloud, err)
        self.assertIsNotNone(local)
        self.assertNotEqual("anthropic", local.backend)
        self.assertIsNotNone(local.model)
        self.assertIn("offline", local.detail["fallback_note"])
        self.assertEqual("claude-opus-5-5", local.detail["gateway_fallback"]["from_model"])
        self.assertTrue(local.reason.startswith("cloud tier unavailable"))

    def test_local_primary_failure_path_unchanged(self):
        self.env(CLOUD_ENV)
        with self.idle(), patch.object(router, "unload", return_value=True):
            previous = router.Decision("gpu", router.GPU_HOST, router.PRIMARY_REASONING_MODEL,
                                       False, "x", {})
            d = router.fallback_after_primary_failure(previous, RuntimeError("oom"))
        self.assertEqual(router.FALLBACK_REASONING_MODEL, d.model)


class PickerAndStatusTests(_Base):
    def test_picker_rows_only_when_enabled(self):
        self.env(CLOUD_ENV)
        with self.idle():
            names = {m["name"] for m in router.chat_models()}
        self.assertIn("cloud-heavy", names)
        self.assertIn("cloud-fast", names)
        self.env(LOCAL_ENV)
        with self.idle():
            names = {m["name"] for m in router.chat_models()}
        self.assertNotIn("cloud-heavy", names)

    def test_status_has_gateway_block_without_key_leak(self):
        self.env(CLOUD_ENV)
        with self.idle():
            s = router.status()
        self.assertTrue(s["model_gateway"]["cloud_enabled"])
        self.assertTrue(s["model_gateway"]["credential_present"])
        self.assertNotIn("sk-test", str(s))


class OllamaClientDispatchTests(_Base):
    def test_cloud_host_streams_through_gateway(self):
        def fake_stream(host, **kw):
            yield gw.TextDelta("hel")
            yield gw.TextDelta("lo")
            yield gw.ToolCalls([{"id": "toolu_1", "function": {"name": "a", "arguments": {}}}])
            yield gw.Done(model="m", stop_reason="tool_use",
                          telemetry={"eval_count": 3, "gateway": {"model": "m"}})
        with patch.object(gw, "stream_for_host", side_effect=fake_stream), \
                patch.object(oll.urllib.request, "urlopen",
                             side_effect=AssertionError("no local HTTP for a cloud route")):
            pieces = list(oll.chat_stream([{"role": "user", "content": "x"}], model="m",
                                          host="anthropic://api.anthropic.com"))
            text, calls = oll.chat([{"role": "user", "content": "x"}], model="m",
                                   host="anthropic://api.anthropic.com")
        self.assertEqual(["hel", "lo"], [p for p in pieces if isinstance(p, str)])
        self.assertIsInstance(pieces[2], oll.ToolCall)
        self.assertIsInstance(pieces[3], oll.StreamEnd)
        self.assertEqual(5, pieces[3].visible_chars)
        self.assertEqual("hello", text)
        self.assertEqual("a", calls[0]["function"]["name"])

    def test_gateway_failure_becomes_model_failure_with_kind(self):
        def failing(host, **kw):
            raise gw.CloudUnavailable("rate_limit", "429")
            yield  # pragma: no cover
        with patch.object(gw, "stream_for_host", side_effect=failing):
            with self.assertRaises(oll.OllamaModelFailure) as ctx:
                list(oll.chat_stream([{"role": "user", "content": "x"}], model="m",
                                     host="anthropic://api.anthropic.com"))
        self.assertEqual("rate_limit", ctx.exception.gateway_kind)
        self.assertIn("rate_limit", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
