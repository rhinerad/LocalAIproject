"""Mockable regression coverage for UPGRADE 15's one-source VRAM plan."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import router


TIERS = [{"label": "caption", "model": "qwen25-vl-nsfw-caption:v4-q4_k_m",
          "vram_need_mb": 8000}]


class VramPlanTests(unittest.TestCase):
    def common(self):
        return patch.multiple(router, queue_owner=lambda: (False, "released"),
                              comfy_listening=lambda: False, chat_busy=lambda: False)

    def test_coexists_when_a_tier_fits(self):
        with self.common(), patch.object(router, "gpu_free_mb", return_value=10000):
            tier, action = router.plan_vision_vram(TIERS)
        self.assertEqual("none", action)
        self.assertEqual("caption", tier["label"])

    def test_primary_resident_requests_downgrade(self):
        with self.common(), patch.object(router, "gpu_free_mb", return_value=100), \
             patch.object(router, "_running_models",
                          return_value=[router.PRIMARY_REASONING_MODEL]):
            tier, action = router.plan_vision_vram(TIERS)
        self.assertEqual("downgrade", action)
        self.assertEqual("caption", tier["label"])

    def test_secondary_resident_requests_eviction(self):
        with self.common(), patch.object(router, "gpu_free_mb", return_value=100), \
             patch.object(router, "_running_models",
                          return_value=[router.FALLBACK_REASONING_MODEL]):
            _tier, action = router.plan_vision_vram(TIERS)
        self.assertEqual("evict", action)

    def test_render_or_streaming_chat_never_evicts(self):
        with patch.object(router, "queue_owner", return_value=(True, "render")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "chat_busy", return_value=False):
            tier, action = router.plan_vision_vram(TIERS)
        self.assertIsNone(tier)
        self.assertEqual("none", action)

    def test_gpu_free_mb_reads_nvidia_telemetry(self):
        with patch.object(router.shutil, "which", return_value="nvidia-smi"), \
             patch.object(router.subprocess, "run",
                          return_value=SimpleNamespace(stdout="15830\n", returncode=0)):
            self.assertEqual(15830, router.gpu_free_mb())


if __name__ == "__main__":
    unittest.main(verbosity=2)
