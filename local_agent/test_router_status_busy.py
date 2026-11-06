from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import router


class RouterBusyStatusTests(unittest.TestCase):
    def test_status_never_reads_gpu_catalogue_while_render_is_busy(self):
        def tags(host):
            if host == router.GPU_HOST:
                raise AssertionError("status must not read GPU tags while busy")
            return [router.FALLBACK_REASONING_MODEL]

        with patch.object(router, "gpu_busy", return_value=(True, "ComfyUI active", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags), \
             patch.object(router, "_LAST_VERIFIED_GPU_MODELS", set()), \
             patch.object(router, "_running_models", return_value=[]), \
             patch.object(router, "powerinfer_proxy_listening", return_value=False), \
             patch.object(router, "powerinfer_backend_listening", return_value=False):
            status = router.status()
        self.assertTrue(status["gpu_busy"])
        self.assertEqual(status["gpu_models"], [])
        # The opt-in GPU-only Heretic choice stays visible but disabled; it is
        # never a CPU substitute while ComfyUI owns the GPU.
        # Preserve the operator's 14B picker choice even at a busy startup,
        # but keep it visibly disabled and never classify it as CPU-capable.
        self.assertEqual(len(status["chat_models"]), 4)
        self.assertEqual(status["chat_models"][0]["name"], router.PRIMARY_REASONING_MODEL)
        self.assertFalse(status["chat_models"][0]["available"])
        self.assertFalse(status["chat_models"][0]["cpu"])
        self.assertEqual(status["chat_models"][1]["name"], router.FALLBACK_REASONING_MODEL)
        self.assertTrue(status["chat_models"][1]["cpu"])
        self.assertFalse(status["chat_models"][1]["gpu"])
        self.assertEqual(status["chat_models"][2]["name"], router.GPT_OSS_20B_HERETIC_MODEL)
        self.assertFalse(status["chat_models"][2]["available"])
        self.assertEqual(status["chat_models"][3]["name"], router.POWERINFER_MODEL_ALIAS)
        self.assertFalse(status["chat_models"][3]["available"])
        self.assertEqual(status["chat_models"][3]["backend"], "powerinfer")

    def test_status_includes_routing_reason_field(self):
        def tags(host):
            return [router.FALLBACK_REASONING_MODEL] if host == router.CPU_HOST else []

        with patch.object(router, "gpu_busy", return_value=(False, "GPU idle (74 MB)", {})), \
             patch.object(router, "up", side_effect=lambda h: h == router.CPU_HOST), \
             patch.object(router, "_tags", side_effect=tags), \
             patch.object(router, "_running_models", return_value=None):
            status = router.status()
        self.assertIn("routing_reason", status)
        self.assertIsInstance(status["routing_reason"], str)
        self.assertTrue(len(status["routing_reason"]) > 0)
        self.assertFalse(status["gpu_server_up"])

    def test_busy_picker_uses_verified_gpu_capability_without_reading_gpu_tags(self):
        def tags(host):
            if host == router.GPU_HOST:
                raise AssertionError("busy picker must not read GPU tags")
            return [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]

        with patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags), \
             patch.object(router, "_LAST_VERIFIED_GPU_MODELS",
                          {router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL}), \
             patch.object(router, "powerinfer_proxy_listening", return_value=False), \
             patch.object(router, "powerinfer_backend_listening", return_value=False):
            models = router.chat_models(include_gpu=False)
        self.assertEqual([m["name"] for m in models], [
            router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL,
            router.GPT_OSS_20B_HERETIC_MODEL, router.POWERINFER_MODEL_ALIAS,
        ])
        # The primary 14B is deliberately GPU-only; only the paired 8B is a
        # valid CPU fallback. The cached GPU catalogue must not relabel either.
        self.assertFalse(models[0]["cpu"])
        self.assertTrue(models[0]["gpu"])
        self.assertTrue(models[1]["cpu"])
        self.assertTrue(models[1]["gpu"])
        self.assertFalse(models[2]["cpu"])
        # This cache did not verify Heretic; it remains a disabled setup entry
        # rather than an invented available GPU capability.
        self.assertFalse(models[2]["gpu"])
        self.assertFalse(models[2]["available"])

    def test_status_third_state_from_owners_and_cache_no_queue_network(self):
        router._TIMESHARE_QUEUE_CACHE["idle"] = True
        url_hits = []
        mcp_hits = []

        def boom_url(*_a, **_k):
            url_hits.append(1)
            raise AssertionError("status must not urllib /queue")

        def boom_mcp(*_a, **_k):
            mcp_hits.append(1)
            raise AssertionError("status must not call MCP")

        with patch.object(router, "gpu_busy",
                          return_value=(True, "a ComfyUI backend is listening on port 8188",
                                        {"comfy_port_8188": "listening"})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags",
                          return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "_owners_idle_for_timeshare",
                          return_value=(True, "released")), \
             patch.object(router, "decide",
                          return_value=router.Decision(
                              "cpu", router.CPU_HOST, router.FALLBACK_REASONING_MODEL,
                              True, "busy", {})), \
             patch.object(router.urllib.request, "urlopen", boom_url), \
             patch.object(router, "powerinfer_proxy_listening", return_value=False), \
             patch.object(router, "powerinfer_backend_listening", return_value=False), \
             patch.object(router, "_timeshare_enabled", return_value=True):
            import mcp_client
            with patch.object(mcp_client, "call", boom_mcp):
                status = router.status()
        self.assertTrue(status["gpu_busy"])
        self.assertTrue(status["timeshare_idle"])
        self.assertEqual(router.STATUS_TIMESHARE_IDLE_REASON, status["reason"])
        self.assertEqual([], url_hits)
        self.assertEqual([], mcp_hits)

    def test_status_not_third_state_when_owner_live(self):
        router._TIMESHARE_QUEUE_CACHE["idle"] = True
        with patch.object(router, "gpu_busy",
                          return_value=(True, "render queue claimed",
                                        {"comfy_port_8188": "listening"})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags",
                          return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "_owners_idle_for_timeshare",
                          return_value=(False, "live pid")), \
             patch.object(router, "decide",
                          return_value=router.Decision(
                              "cpu", router.CPU_HOST, router.FALLBACK_REASONING_MODEL,
                              True, "busy", {})), \
             patch.object(router, "powerinfer_proxy_listening", return_value=False), \
             patch.object(router, "powerinfer_backend_listening", return_value=False), \
             patch.object(router, "_timeshare_enabled", return_value=True):
            status = router.status()
        self.assertFalse(status["timeshare_idle"])
        self.assertEqual("render queue claimed", status["reason"])

    def test_status_not_third_state_when_queue_cache_busy(self):
        router._TIMESHARE_QUEUE_CACHE["idle"] = False
        with patch.object(router, "gpu_busy",
                          return_value=(True, "a ComfyUI backend is listening on port 8188",
                                        {"comfy_port_8188": "listening"})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags",
                          return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "_owners_idle_for_timeshare",
                          return_value=(True, "released")), \
             patch.object(router, "decide",
                          return_value=router.Decision(
                              "cpu", router.CPU_HOST, router.FALLBACK_REASONING_MODEL,
                              True, "busy", {})), \
             patch.object(router, "powerinfer_proxy_listening", return_value=False), \
             patch.object(router, "powerinfer_backend_listening", return_value=False), \
             patch.object(router, "_timeshare_enabled", return_value=True):
            status = router.status()
        self.assertFalse(status["timeshare_idle"])
        self.assertIn("8188", status["reason"])


    def test_timeshare_idle_status_keeps_gpu_picker_available_without_cache(self):
        """Idle 8188 must not disable GPU-only picker entries after restart.

        gpu_busy() still reports True while Comfy listens, but timeshare_idle
        means a granted turn may claim. status() must inventory GPU tags so
        14B is selectable instead of "GPU currently unavailable".
        """
        router._TIMESHARE_QUEUE_CACHE["idle"] = True
        router._LAST_VERIFIED_GPU_MODELS = set()
        gpu_hits = []

        def tags(host):
            if host == router.GPU_HOST:
                gpu_hits.append(1)
                return [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
            return [router.FALLBACK_REASONING_MODEL]

        with patch.object(router, "gpu_busy",
                          return_value=(True, "a ComfyUI backend is listening on port 8188",
                                        {"comfy_port_8188": "listening"})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags), \
             patch.object(router, "_owners_idle_for_timeshare",
                          return_value=(True, "released")), \
             patch.object(router, "decide",
                          return_value=router.Decision(
                              "cpu", router.CPU_HOST, router.FALLBACK_REASONING_MODEL,
                              True, "busy", {})), \
             patch.object(router, "powerinfer_proxy_listening", return_value=False), \
             patch.object(router, "powerinfer_backend_listening", return_value=False), \
             patch.object(router, "_timeshare_enabled", return_value=True):
            status = router.status()
        self.assertTrue(status["gpu_busy"])
        self.assertTrue(status["timeshare_idle"])
        self.assertGreaterEqual(len(gpu_hits), 1)
        primary = next(m for m in status["chat_models"]
                       if m["name"] == router.PRIMARY_REASONING_MODEL)
        self.assertTrue(primary["available"])
        self.assertTrue(primary["gpu"])
        self.assertNotIn("unavailable_reason", primary)
        self.assertNotIn("GPU currently unavailable", primary.get("label") or "")

    def test_active_render_busy_still_skips_gpu_catalogue(self):
        """Non-timeshare busy must keep the render-safe catalogue skip."""
        router._TIMESHARE_QUEUE_CACHE["idle"] = False
        def tags(host):
            if host == router.GPU_HOST:
                raise AssertionError("active render must not read GPU tags")
            return [router.FALLBACK_REASONING_MODEL]

        with patch.object(router, "gpu_busy", return_value=(True, "ComfyUI active", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags), \
             patch.object(router, "_LAST_VERIFIED_GPU_MODELS", set()), \
             patch.object(router, "_running_models", return_value=[]), \
             patch.object(router, "powerinfer_proxy_listening", return_value=False), \
             patch.object(router, "powerinfer_backend_listening", return_value=False), \
             patch.object(router, "decide",
                          return_value=router.Decision(
                              "cpu", router.CPU_HOST, router.FALLBACK_REASONING_MODEL,
                              True, "busy", {})):
            status = router.status()
        self.assertTrue(status["gpu_busy"])
        self.assertFalse(status.get("timeshare_idle"))
        primary = next(m for m in status["chat_models"]
                       if m["name"] == router.PRIMARY_REASONING_MODEL)
        self.assertFalse(primary["available"])
        self.assertIn("GPU currently unavailable", primary.get("label") or "")


if __name__ == "__main__":
    unittest.main()
