#!/usr/bin/env python3
"""VRAM-derived GPU num_ctx: ceilings change, routing tags do not."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import router  # noqa: E402


def _gpu_idle():
    return False, "GPU idle (70 MB used, no foreign compute process)", {
        "queue_owner": "queue owner released",
        "comfy_port_8188": "closed",
        "vram_used_mb": 70,
    }


class GpuVramNumCtxTests(unittest.TestCase):
    def test_table_matches_model_vram_budget_addendum(self) -> None:
        self.assertEqual(33976, router.GPU_VRAM_NUM_CTX[router.PRIMARY_REASONING_MODEL])
        self.assertEqual(40960, router.GPU_VRAM_NUM_CTX[router.FALLBACK_REASONING_MODEL])
        self.assertEqual(28371, router.GPU_VRAM_NUM_CTX[router.DEEPSEEK_MODEL])
        self.assertEqual(28371, router.GPU_VRAM_NUM_CTX[router.JOSIEFIED_CODER_MODEL])
        self.assertEqual(1742, router.GPU_VRAM_NUM_CTX[router.GPT_OSS_20B_HERETIC_MODEL])

    def test_lookup_follows_configured_variants_and_coder_pins(self) -> None:
        self.assertEqual(33976, router.gpu_vram_num_ctx(router.PRIMARY_REASONING_MODEL))
        self.assertEqual(
            33976,
            router.gpu_vram_num_ctx(router.PRIMARY_REASONING_MODEL + "-v2"),
        )
        self.assertEqual(1742, router.gpu_vram_num_ctx("gpt-oss-20b-heretic:latest"))
        self.assertEqual(
            28371,
            router.gpu_vram_num_ctx("josiefied-qwen2.5-coder-14b:official-tools"),
        )
        self.assertEqual(
            28371,
            router.gpu_vram_num_ctx("deepseek-r1-abliterated-14b:r1-tools"),
        )
        self.assertEqual(28371, router.gpu_vram_num_ctx("qwen2.5-coder:14b"))
        self.assertIsNone(router.gpu_vram_num_ctx("equal-shares-gpu"))

    def test_farm_path_still_uses_capability_constant_not_vram_table(self) -> None:
        d = router.Decision(
            "farm", "farm", router.QWYTHOS_MODEL, False, "farm", {}, "farm",
        )
        self.assertEqual(router.CAPABILITY_GPU_NUM_CTX, d.options()["num_ctx"])
        self.assertEqual(8192, d.options()["num_ctx"])


class GpuVramRoutingUnchangedTests(unittest.TestCase):
    def setUp(self):
        self._owned_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._owned_tmp.cleanup)
        owned = Path(self._owned_tmp.name) / "gpu_owned_residents.json"
        pressure = Path(self._owned_tmp.name) / "media_vram_pressure.json"
        for name, path in (("GPU_OWNED_FILE", owned),
                           ("MEDIA_PRESSURE_FILE", pressure)):
            p = patch.object(router, name, path)
            p.start()
            self.addCleanup(p.stop)

    def test_coding_still_selects_josiefied(self) -> None:
        gpu_have = [router.DEEPSEEK_MODEL, router.JOSIEFIED_CODER_MODEL,
                    router.PRIMARY_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "thermal_blocks_gpu", return_value=None), \
             patch.object(router, "prepare_gpu_model", return_value={
                 "attempted": [], "keep_alive_sent": [], "remaining": [],
                 "verified": True, "reason": "empty",
             }):
            d = router.decide(
                "auto",
                prompt="write a python function that parses JSON",
            )
        self.assertEqual("gpu", d.tier)
        self.assertEqual(router.JOSIEFIED_CODER_MODEL, d.model)
        self.assertEqual(28371, d.options()["num_ctx"])

    def test_logic_still_selects_deepseek(self) -> None:
        gpu_have = [router.DEEPSEEK_MODEL, router.JOSIEFIED_CODER_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "thermal_blocks_gpu", return_value=None), \
             patch.object(router, "prepare_gpu_model", return_value={
                 "attempted": [], "keep_alive_sent": [], "remaining": [],
                 "verified": True, "reason": "empty",
             }):
            d = router.decide(
                "auto",
                prompt=("Please architect a refactor of the repository and compare "
                        "the end-to-end workflow against the current implementation."),
            )
        self.assertEqual(router.DEEPSEEK_MODEL, d.model)
        self.assertEqual("gpu", d.tier)
        self.assertEqual(28371, d.options()["num_ctx"])

    def test_short_primary_pin_still_stays_on_primary(self) -> None:
        pair = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=pair):
            d = router.decide("auto", model=router.PRIMARY_REASONING_MODEL,
                              prompt_tokens=1000)
        self.assertEqual(router.PRIMARY_REASONING_MODEL, d.model)
        self.assertEqual("gpu", d.tier)
        self.assertEqual(33976, d.options()["num_ctx"])

    def test_long_primary_still_routes_to_fallback(self) -> None:
        pair = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=pair):
            d = router.decide(
                "auto", model=router.PRIMARY_REASONING_MODEL,
                prompt_tokens=router.PRIMARY_SAFE_PROMPT_TOKENS + 1)
        self.assertEqual(router.FALLBACK_REASONING_MODEL, d.model)
        self.assertEqual("gpu", d.tier)
        self.assertEqual(40960, d.options()["num_ctx"])
        self.assertEqual("predictive context-length protection",
                         d.detail["adaptive_fallback"]["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
