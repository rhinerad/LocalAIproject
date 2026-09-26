#!/usr/bin/env python3
"""Regression coverage for lazy, exact-Qwen media watcher ownership.

These checks are deliberately mocked: they prove the watcher decisions without
starting llama.cpp, touching Ollama, or loading a vision model.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import capabilities as caps
import media_watcher


class ExactQwenWatcherTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pressure = Path(self._tmp.name) / "media_vram_pressure.json"
        p = patch.object(media_watcher.router, "MEDIA_PRESSURE_FILE", self.pressure)
        p.start()
        self.addCleanup(p.stop)

    def test_no_safe_tier_never_starts_the_vlm(self):
        with patch.object(media_watcher.router, "plan_vision_vram",
                          return_value=(None, "wait")), \
             patch.object(media_watcher.caps, "ensure_qwen25_vl_runtime") as ensure:
            self.assertIsNone(media_watcher._prepare_vision_batch())
        ensure.assert_not_called()

    def test_render_ownership_blocks_vision_before_vram_or_runtime_checks(self):
        with patch.object(media_watcher.router, "queue_owner", return_value=(True, "active render")), \
             patch.object(media_watcher.router, "comfy_listening", return_value=False), \
             patch.object(media_watcher.router, "gpu_free_mb") as free_mb, \
             patch.object(media_watcher.caps, "ensure_qwen25_vl_runtime") as ensure:
            self.assertFalse(media_watcher._action_model_ready())
        free_mb.assert_not_called()
        ensure.assert_not_called()

    def test_safe_qwen_tier_starts_only_the_exact_runtime(self):
        tier = {"label": "exact-qwen", "model": caps.QWEN25_VL_MODEL,
                "vram_need_mb": caps.QWEN25_VL_VRAM_MB}
        with patch.object(media_watcher.router, "plan_vision_vram",
                          return_value=(tier, "coexist")), \
             patch.object(media_watcher.router, "gpu_free_mb",
                          return_value=caps.QWEN25_VL_VRAM_MB + caps.VRAM_SAFETY_MB), \
             patch.object(media_watcher.caps, "ensure_qwen25_vl_runtime",
                          return_value=True) as ensure:
            result = media_watcher._prepare_vision_batch()
        self.assertEqual(caps.QWEN25_VL_MODEL, result["model"])
        self.assertEqual("llama.cpp", result["runtime"])
        ensure.assert_called_once_with()

    def test_empty_queue_never_plans_or_starts_the_vlm(self):
        with patch.object(media_watcher.mq, "list_queue",
                          return_value={"pending": []}), \
             patch.object(media_watcher, "_render_active", return_value=True), \
             patch.object(media_watcher, "_prepare_vision_batch") as prepare:
            self.assertEqual(0, media_watcher.run_once())
        prepare.assert_not_called()

    def test_non_exact_model_is_refused_before_any_runtime_call(self):
        with patch.object(media_watcher.caps, "qwen25_vl_runtime_available",
                          return_value=True):
            result = media_watcher.media_tools._run_vision_gpu(
                [], "test", "qwen3vl-abl:latest", media_watcher.router.GPU_HOST)
        self.assertIn("only the exact Qwen2.5-VL Caption V4", result)

    def test_unowned_runtime_is_reported_as_resident_not_released(self):
        with patch.object(media_watcher.caps, "release_qwen25_vl_runtime",
                          return_value=False), \
             patch.object(media_watcher.router, "set_media_pressure") as pressure, \
             patch("builtins.print") as printed:
            self.assertFalse(media_watcher._release_vision_batch())
        pressure.assert_called_once_with(False)
        self.assertIn("remains resident", printed.call_args.args[0])

    def test_owned_runtime_release_is_reported_accurately(self):
        with patch.object(media_watcher.caps, "release_qwen25_vl_runtime",
                          return_value=True), \
             patch.object(media_watcher.router, "set_media_pressure") as pressure, \
             patch("builtins.print") as printed:
            self.assertTrue(media_watcher._release_vision_batch())
        pressure.assert_called_once_with(False)
        self.assertIn("released owned", printed.call_args.args[0])

    def _qwen_tier(self):
        return {"label": "exact-qwen", "model": caps.QWEN25_VL_MODEL,
                "vram_need_mb": caps.QWEN25_VL_VRAM_MB}

    def test_failed_vlm_start_after_downgrade_clears_media_pressure(self):
        """Simulated failed vision start must not leave the demotion latch."""
        with patch.object(media_watcher.router, "plan_vision_vram",
                          return_value=(self._qwen_tier(), "downgrade")), \
             patch.object(media_watcher.router, "unload"), \
             patch.object(media_watcher.router, "gpu_free_mb",
                          return_value=caps.QWEN25_VL_VRAM_MB + caps.VRAM_SAFETY_MB), \
             patch.object(media_watcher.caps, "ensure_qwen25_vl_runtime",
                          return_value=False):
            self.assertIsNone(media_watcher._prepare_vision_batch())
        self.assertFalse(self.pressure.is_file())
        self.assertFalse(media_watcher.router.media_pressure())

    def test_insufficient_vram_after_evict_clears_media_pressure(self):
        with patch.object(media_watcher.router, "plan_vision_vram",
                          return_value=(self._qwen_tier(), "evict")), \
             patch.object(media_watcher.router, "_running_models",
                          return_value=[media_watcher.router.FALLBACK_REASONING_MODEL]), \
             patch.object(media_watcher.router, "unload"), \
             patch.object(media_watcher.router, "gpu_free_mb", return_value=100), \
             patch.object(media_watcher.caps, "ensure_qwen25_vl_runtime") as ensure:
            self.assertIsNone(media_watcher._prepare_vision_batch())
        ensure.assert_not_called()
        self.assertFalse(self.pressure.is_file())
        self.assertFalse(media_watcher.router.media_pressure())

    def test_successful_prepare_keeps_media_pressure_while_in_flight(self):
        with patch.object(media_watcher.router, "plan_vision_vram",
                          return_value=(self._qwen_tier(), "downgrade")), \
             patch.object(media_watcher.router, "unload"), \
             patch.object(media_watcher.router, "gpu_free_mb",
                          return_value=caps.QWEN25_VL_VRAM_MB + caps.VRAM_SAFETY_MB), \
             patch.object(media_watcher.caps, "ensure_qwen25_vl_runtime",
                          return_value=True):
            result = media_watcher._prepare_vision_batch()
        self.assertEqual(caps.QWEN25_VL_MODEL, result["model"])
        self.assertTrue(self.pressure.is_file())
        self.assertTrue(media_watcher.router.media_pressure())

    def test_prepare_none_clears_a_leaked_pressure_flag(self):
        media_watcher.router.set_media_pressure(True)
        self.assertTrue(self.pressure.is_file())
        with patch.object(media_watcher.router, "plan_vision_vram",
                          return_value=(None, "wait")):
            self.assertIsNone(media_watcher._prepare_vision_batch())
        self.assertFalse(self.pressure.is_file())
        self.assertFalse(media_watcher.router.media_pressure())

    def test_run_once_releases_pressure_after_successful_prepare_even_if_queue_empty(self):
        media_watcher.router.set_media_pressure(True)
        pending = [{"id": "gone", "kind": "vision"}]
        with patch.object(media_watcher.mq, "list_queue",
                          return_value={"pending": pending}), \
             patch.object(media_watcher, "_prepare_vision_batch",
                          return_value=self._qwen_tier()), \
             patch.object(media_watcher.mq, "claim_next", return_value=None), \
             patch.object(media_watcher, "_render_active", return_value=False), \
             patch.object(media_watcher, "_release_vision_batch") as release:
            self.assertEqual(0, media_watcher.run_once())
        release.assert_called_once_with()


if __name__ == "__main__":
    unittest.main(verbosity=2)
