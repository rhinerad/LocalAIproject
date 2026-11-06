#!/usr/bin/env python3
"""Capability routing: mocked Ollama only. No live model load."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import router  # noqa: E402
import farm_offload  # noqa: E402


def _gpu_idle():
    return False, "GPU idle (70 MB used, no foreign compute process)", {
        "queue_owner": "queue owner released",
        "comfy_port_8188": "closed",
        "vram_used_mb": 70,
    }


def _gpu_busy_render():
    return True, "render queue claimed by live pid 1234 (audio)", {
        "queue_owner": "render queue claimed by live pid 1234 (audio)",
    }


class ClassifyCapabilityTests(unittest.TestCase):
    def test_coding_prompt(self):
        self.assertEqual(
            router.CAP_CODE,
            router.classify_capability("write a python function that parses JSON"),
        )

    def test_logic_prompt_uses_difficulty_signals(self):
        text = ("Please architect a refactor of the repository and compare "
                "the end-to-end workflow against the current implementation.")
        self.assertEqual(router.CAP_LOGIC, router.classify_capability(text))

    def test_tool_prompt(self):
        self.assertEqual(
            router.CAP_TOOL,
            router.classify_capability("list the files in the current folder"),
        )

    def test_empty_prompt_is_no_override(self):
        self.assertEqual("", router.classify_capability(None))
        self.assertEqual("", router.classify_capability(""))

    def test_pin_wins(self):
        self.assertEqual(
            router.CAP_CODE,
            router.classify_capability("hello", model=router.JOSIEFIED_CODER_MODEL),
        )
        self.assertEqual(
            router.CAP_LOGIC,
            router.classify_capability("hello", model=router.DEEPSEEK_MODEL),
        )

    def test_non_capability_pin_still_classifies_by_text(self):
        """Huihui 14B is not one of the three capability pins, so the
        ``if model:`` block in classify_capability falls through to
        _CODE_SIGNAL. Classification still happens; decide() is what
        must refuse to apply it as a model override (see
        test_explicit_huihui_pin_not_overridden_by_code_signal)."""
        self.assertEqual(
            router.CAP_CODE,
            router.classify_capability(
                "write a python function that parses JSON",
                model=router.PRIMARY_REASONING_MODEL,
            ),
        )

    def test_long_still_frame_script_is_image_not_logic(self):
        text = (
            "AGENT TASK: still frames only. Photoreal live-action. "
            "Two adult women from my reference sheets.\n"
            "No captions on the images. No extra people in the foreground.\n"
            "MAKE START + LAST FOR EACH BEAT\n"
            "PRE01 START: wide yard, both on lounge chairs.\n"
            "PRE01 LAST: Bulma talking, looking up.\n"
            "OUTPUT pre01_start.png pre01_last.png through pre14_last.png.\n"
            "One short visual prompt under each file. Stop after stills.\n"
        )
        text = text + ("Keep the same faces every frame. Photoreal, not cartoon. "
                       "If a face changes, redo that frame. ") * 20
        self.assertGreaterEqual(len(text), 700)
        self.assertTrue(router.image_generation_intent(text))
        self.assertEqual(router.CAP_IMAGE, router.classify_capability(text))
        self.assertEqual(
            router.CAP_IMAGE,
            router.classify_capability(text, model=router.PRIMARY_REASONING_MODEL),
        )

    def test_short_generate_image_is_image_not_farm_tool(self):
        self.assertEqual(
            router.CAP_IMAGE,
            router.classify_capability("make me a photoreal image of a greenhouse"),
        )

    def test_analyze_attached_image_is_not_image_generation(self):
        text = ("Call analyze_image on this path now. Do not describe the "
                "image from memory. --- attached image: sheet.png ---")
        self.assertFalse(router.image_generation_intent(text))
        self.assertEqual(router.CAP_TOOL, router.classify_capability(text))

    def test_enqueue_txt2img_workflow_path_is_not_image_generation(self):
        """A graph filename containing txt2img is still a tool/enqueue turn."""
        text = (
            "Start an automatic ComfyUI workflow now. Load the API-format "
            "graph at artifacts/benchmarks/2026-09-05_task_completion/"
            "txt2img_mcp_test.json and enqueue it via comfy_workflow with "
            "tool enqueue_workflow and action enqueue. Do not use "
            "comfy_generate. After enqueue, report the prompt_id. "
            "Do not restart ComfyUI."
        )
        self.assertFalse(router.image_generation_intent(text))
        self.assertEqual(router.CAP_TOOL, router.classify_capability(text))

    def test_generate_photos_using_flux_is_image(self):
        text = "Generate these photos using flux"
        self.assertTrue(router.image_generation_intent(text))
        self.assertEqual(router.CAP_IMAGE, router.classify_capability(text))

    def test_generate_these_photos_is_image(self):
        text = "generate these photos"
        self.assertTrue(router.image_generation_intent(text))
        self.assertEqual(router.CAP_IMAGE, router.classify_capability(text))

    def test_start_end_frame_sheet_is_image(self):
        text = (
            "START FRAME: wide yard, both on lounge chairs.\n"
            "END FRAME: close-up talking, looking up.\n"
            "Photoreal stills only."
        )
        self.assertTrue(router.image_generation_intent(text))
        self.assertEqual(router.CAP_IMAGE, router.classify_capability(text))

    def test_using_flux_with_generate_photos_is_image(self):
        text = "Please generate these photos with flux model"
        self.assertTrue(router.image_generation_intent(text))
        self.assertEqual(router.CAP_IMAGE, router.classify_capability(text))

    def test_plan_story_image_signal_still_image(self):
        text = "Call plan_story_image then render_story_image for the stills"
        self.assertTrue(router.image_generation_intent(text))
        self.assertEqual(router.CAP_IMAGE, router.classify_capability(text))

    def test_coding_pin_wins_over_logic_text(self):
        """A Coding-mode pin is one of the three capability pins, so the
        classifier returns CAP_CODE even when the prompt looks like DeepSeek
        work. Text-based CAP_LOGIC cannot leak through the way it does for
        Huihui 14B."""
        text = ("Please architect a refactor of the repository and compare "
                "the end-to-end workflow against the current implementation.")
        self.assertEqual(
            router.CAP_CODE,
            router.classify_capability(text, model=router.JOSIEFIED_CODER_MODEL),
        )
        self.assertEqual(
            router.CAP_CODE,
            router.classify_capability(text, model=router.CODING_MODEL),
        )


class CapabilityDecideTests(unittest.TestCase):
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

    def test_tool_routes_to_farm_qwythos_when_reachable(self):
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.PRIMARY_REASONING_MODEL]), \
             patch.object(router, "_farm_reachable", return_value=True), \
             patch.object(router, "prepare_gpu_model") as swap:
            d = router.decide("auto", prompt="list the files in the current folder")
        self.assertEqual("farm", d.tier)
        self.assertEqual("farm", d.backend)
        self.assertEqual(router.QWYTHOS_MODEL, d.model)
        swap.assert_not_called()

    def test_unpinned_still_frame_script_does_not_go_to_farm(self):
        text = (
            "AGENT TASK: still frames only. Photoreal live-action.\n"
            "MAKE START + LAST FOR EACH BEAT. Output pre01_start.png "
            "through pre14_last.png. Stop after stills. "
        ) * 15
        self.assertGreaterEqual(len(text), 700)
        gpu_have = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=True), \
             patch.object(router, "media_pressure", return_value=False), \
             patch.object(router, "prepare_gpu_model") as swap:
            d = router.decide(
                "auto", prompt=text,
                prompt_tokens=router.PRIMARY_SAFE_PROMPT_TOKENS + 5000)
        self.assertNotEqual("farm", d.tier)
        self.assertNotEqual("farm", d.backend)
        self.assertEqual(router.CAP_IMAGE, d.detail.get("capability"))
        self.assertEqual(router.PRIMARY_REASONING_MODEL, d.model)
        self.assertNotEqual(router.FALLBACK_REASONING_MODEL, d.model)
        self.assertNotIn("predictive context-length protection", d.reason)
        self.assertEqual(
            "image-generation intent keeps primary",
            (d.detail.get("adaptive_fallback_skipped") or {}).get("reason"),
        )
        swap.assert_not_called()

    def test_coding_routes_to_josiefied_and_flushes_deepseek(self):
        resident = [router.DEEPSEEK_MODEL]

        def _running(host):
            return list(resident)

        def _unload(host, model):
            if model in resident:
                resident.remove(model)
            return True

        gpu_have = [router.DEEPSEEK_MODEL, router.JOSIEFIED_CODER_MODEL,
                    router.PRIMARY_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "thermal_blocks_gpu", return_value=None), \
             patch.object(router, "_running_models", side_effect=_running), \
             patch.object(router, "unload", side_effect=_unload) as unload:
            d = router.decide(
                "auto",
                prompt="write a python function that parses JSON",
            )
        self.assertEqual("gpu", d.tier)
        self.assertEqual(router.JOSIEFIED_CODER_MODEL, d.model)
        self.assertEqual(28371, d.options()["num_ctx"])
        unload.assert_called()
        sent = d.detail["host_model_swap"]["keep_alive_sent"]
        self.assertEqual([router.DEEPSEEK_MODEL], sent)
        self.assertTrue(d.detail["host_model_swap"]["verified"])

    def test_logic_routes_to_deepseek(self):
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
             }) as swap:
            d = router.decide(
                "auto",
                prompt=("Please architect a refactor of the repository and compare "
                        "the end-to-end workflow against the current implementation."),
            )
        self.assertEqual(router.DEEPSEEK_MODEL, d.model)
        swap.assert_called_once_with(router.DEEPSEEK_MODEL)

    def test_queue_owner_refuses_capability_gpu(self):
        with patch.object(router, "gpu_busy", return_value=_gpu_busy_render()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags",
                          return_value=[router.FALLBACK_REASONING_MODEL,
                                        router.JOSIEFIED_CODER_MODEL]), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "queue_owner",
                          return_value=(True, "render queue claimed by live pid 1234")), \
             patch.object(router, "evict_gpu_residents", return_value={
                 "verified": True, "attempted": [], "remaining": [],
             }), \
             patch.object(router, "prepare_gpu_model") as swap:
            d = router.decide(
                "auto",
                prompt="write a python function that parses JSON",
            )
        swap.assert_not_called()
        self.assertEqual("cpu", d.tier)
        self.assertIn("capability_gpu_refused", d.detail)

    def test_thermal_guard_refuses_capability_gpu(self):
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags",
                          return_value=[router.FALLBACK_REASONING_MODEL,
                                        router.DEEPSEEK_MODEL]), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "thermal_blocks_gpu",
                          return_value="GPU 81 C reached thermal_guard emergency ceiling 82 C"), \
             patch.object(router, "prepare_gpu_model") as swap:
            d = router.decide(
                "auto",
                prompt=("Please architect a refactor of the repository and compare "
                        "the end-to-end workflow against the current implementation."),
            )
        swap.assert_not_called()
        self.assertNotEqual(router.DEEPSEEK_MODEL, d.model)
        self.assertEqual("cpu", d.tier)
        self.assertIn("capability_gpu_refused", d.detail)

    def test_forced_gpu_thermal_returns_no_model(self):
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.DEEPSEEK_MODEL]), \
             patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "thermal_blocks_gpu",
                          return_value="GPU 75 C exceeds thermal_guard start ceiling 70 C"):
            d = router.decide(
                "gpu",
                prompt=("Please architect a refactor of the repository and compare "
                        "the end-to-end workflow against the current implementation."),
            )
        self.assertIsNone(d.model)
        self.assertIn("refused", d.reason)

    def test_unverified_keep_alive_flush_refuses(self):
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags",
                          return_value=[router.DEEPSEEK_MODEL, router.JOSIEFIED_CODER_MODEL]), \
             patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "thermal_blocks_gpu", return_value=None), \
             patch.object(router, "prepare_gpu_model", return_value={
                 "attempted": [router.DEEPSEEK_MODEL],
                 "keep_alive_sent": [router.DEEPSEEK_MODEL],
                 "remaining": [router.DEEPSEEK_MODEL],
                 "verified": False,
                 "reason": "keep_alive:0 swap timed out",
             }):
            d = router.decide(
                "auto",
                prompt="write a python function that parses JSON",
            )
        self.assertIsNone(d.model)
        self.assertIn("keep_alive:0", d.reason)

    def test_explicit_huihui_pin_not_overridden_by_code_signal(self):
        """Operator pin of the general-reasoning 14B must beat _CODE_SIGNAL.

        classify_capability still returns CAP_CODE (see the classifier test);
        decide() must keep huihui_ai/qwen3-abliterated:14b anyway, not swap
        to Coder-14B or farm Qwythos.
        """
        code_prompt = "write a python function that parses JSON"
        gpu_have = [
            router.PRIMARY_REASONING_MODEL,
            router.FALLBACK_REASONING_MODEL,
            router.JOSIEFIED_CODER_MODEL,
            router.DEEPSEEK_MODEL,
        ]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=True), \
             patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "thermal_blocks_gpu", return_value=None), \
             patch.object(router, "media_pressure", return_value=False), \
             patch.object(router, "prepare_gpu_model") as swap:
            d = router.decide(
                "auto",
                model=router.PRIMARY_REASONING_MODEL,
                prompt=code_prompt,
            )
        self.assertEqual("gpu", d.tier)
        self.assertNotEqual("farm", d.backend)
        self.assertEqual(router.PRIMARY_REASONING_MODEL, d.model)
        self.assertNotEqual(router.JOSIEFIED_CODER_MODEL, d.model)
        self.assertEqual(router.CAP_CODE, d.detail.get("capability"))
        swap.assert_not_called()

    def test_explicit_coder_pin_not_overridden_by_logic_signal(self):
        """Desktop Coding mode pins JOSIEFIED_CODER_MODEL (see index.html
        picker value=m.name and /api/send store.create(model=...)).

        Unlike a Huihui pin, want_capability_gpu is True because the pin *is*
        a coding model — but target_cfg is still Coder, not DeepSeek, because
        classify_capability short-circuits to CAP_CODE. Farm requires
        model is None, so Qwythos is skipped.
        """
        logic_prompt = (
            "Please architect a refactor of the repository and compare "
            "the end-to-end workflow against the current implementation."
        )
        gpu_have = [
            router.PRIMARY_REASONING_MODEL,
            router.JOSIEFIED_CODER_MODEL,
            router.DEEPSEEK_MODEL,
        ]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=True), \
             patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "thermal_blocks_gpu", return_value=None), \
             patch.object(router, "media_pressure", return_value=False), \
             patch.object(router, "prepare_gpu_model", return_value={
                 "attempted": [], "keep_alive_sent": [], "remaining": [],
                 "verified": True, "reason": "empty",
             }) as swap:
            d = router.decide(
                "auto",
                model=router.JOSIEFIED_CODER_MODEL,
                prompt=logic_prompt,
            )
        self.assertEqual("gpu", d.tier)
        self.assertNotEqual("farm", d.backend)
        self.assertEqual(router.JOSIEFIED_CODER_MODEL, d.model)
        self.assertNotEqual(router.DEEPSEEK_MODEL, d.model)
        self.assertEqual(router.CAP_CODE, d.detail.get("capability"))
        swap.assert_called_once_with(router.JOSIEFIED_CODER_MODEL)
        self.assertTrue(
            router._timeshare_would_load_host_gpu(
                "auto", router.JOSIEFIED_CODER_MODEL, router.CAP_CODE),
        )

    def test_legacy_auto_without_prompt_does_not_farm(self):
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags",
                          return_value=[router.PRIMARY_REASONING_MODEL]), \
             patch.object(router, "_farm_reachable", return_value=True):
            d = router.decide("auto")
        self.assertEqual("gpu", d.tier)
        self.assertNotEqual("farm", d.backend)


class PrepareGpuModelTests(unittest.TestCase):
    def test_sends_keep_alive_zero_via_unload(self):
        resident = [router.DEEPSEEK_MODEL]

        def _running(host):
            return list(resident)

        def _unload(host, model):
            self.assertEqual(router.GPU_HOST, host)
            if model in resident:
                resident.remove(model)
            return True

        with patch.object(router, "up", return_value=True), \
             patch.object(router, "_running_models", side_effect=_running), \
             patch.object(router, "unload", side_effect=_unload) as unload:
            result = router.prepare_gpu_model(router.JOSIEFIED_CODER_MODEL)
        self.assertTrue(result["verified"])
        unload.assert_called_once_with(router.GPU_HOST, router.DEEPSEEK_MODEL)
        self.assertEqual([router.DEEPSEEK_MODEL], result["keep_alive_sent"])


class FarmOffloadQwythosTests(unittest.TestCase):
    def test_should_route_qwythos_when_farm_reachable(self):
        with patch.object(farm_offload, "farm_reachable", return_value=True):
            self.assertTrue(farm_offload.should_route(farm_offload.KIND_QWYTHOS,
                                                      blocking=True))
        with patch.object(farm_offload, "farm_reachable", return_value=False):
            self.assertFalse(farm_offload.should_route(farm_offload.KIND_QWYTHOS,
                                                       blocking=True))

    def test_try_qwythos_returns_none_when_unreachable(self):
        with patch.object(farm_offload, "farm_reachable", return_value=False):
            self.assertIsNone(farm_offload.try_qwythos_on_farm(
                [{"role": "user", "content": "hi"}]))


class GpuToolFallbackSchemaTests(unittest.TestCase):
    def test_farm_up_unpinned_tool_stays_qwythos_compact(self):
        gpu_have = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=True):
            d = router.decide("auto", prompt="list the files in the current folder")
        self.assertEqual("farm", d.backend)
        self.assertEqual(router.QWYTHOS_MODEL, d.model)
        self.assertFalse(d.detail.get("gpu_tool_fallback"))
        import tools
        self.assertEqual("cpu", tools.profile_for(d))
        names = {item["function"]["name"] for item in tools.schemas(profile="cpu")}
        self.assertEqual({"list_tools", "describe_tool", "call_tool"}, names)

    def test_farm_down_unpinned_tool_is_gpu_core_not_full_catalog(self):
        gpu_have = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "media_pressure", return_value=False):
            d = router.decide("auto", prompt="list the files in the current folder")
        self.assertEqual("gpu", d.tier)
        self.assertNotEqual("farm", d.backend)
        self.assertTrue(d.detail.get("gpu_tool_fallback"))
        self.assertEqual(router.PRIMARY_REASONING_MODEL, d.model)
        import tools
        self.assertEqual("gpu_core", tools.profile_for(d))
        names = [item["function"]["name"] for item in tools.schemas(
            profile="gpu_core", prompt="list the files in the current folder")]
        self.assertEqual(set(tools.CORE_DIRECT_TOOLS), set(names))
        self.assertNotIn("see_image", names)
        self.assertNotIn("comfy_workflow", names)

    def test_skip_farm_unpinned_tool_is_gpu_core_even_if_farm_up(self):
        gpu_have = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=True), \
             patch.object(router, "media_pressure", return_value=False):
            d = router.decide(
                "auto", prompt="list the files in the current folder",
                skip_farm=True)
        self.assertEqual("gpu", d.tier)
        self.assertTrue(d.detail.get("gpu_tool_fallback"))
        import tools
        self.assertEqual("gpu_core", tools.profile_for(d))

    def test_gpu_core_adds_comfy_on_workflow_prompt(self):
        import tools
        prompt = (
            "Start an automatic ComfyUI workflow now and enqueue it via "
            "comfy_workflow with tool enqueue_workflow."
        )
        names = set(item["function"]["name"] for item in tools.schemas(
            profile="gpu_core", prompt=prompt))
        self.assertTrue(set(tools.CORE_DIRECT_TOOLS).issubset(names))
        self.assertTrue(set(tools.COMFY_CORE_TOOLS).issubset(names))
        self.assertIn("comfy_workflow", names)
        self.assertNotIn("see_image", names)
        self.assertNotIn("comfy_process", names)

    def test_pinned_huihui_keeps_full_gpu_schema(self):
        gpu_have = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "media_pressure", return_value=False):
            d = router.decide(
                "auto",
                model=router.PRIMARY_REASONING_MODEL,
                prompt="list the files in the current folder",
            )
        self.assertFalse(d.detail.get("gpu_tool_fallback"))
        import tools
        self.assertEqual("gpu", tools.profile_for(d))
        names = {item["function"]["name"] for item in tools.schemas(profile="gpu")}
        self.assertIn("see_image", names)
        self.assertGreater(len(names), 20)

    def test_cap_code_farm_down_is_not_gpu_core(self):
        gpu_have = [
            router.PRIMARY_REASONING_MODEL,
            router.JOSIEFIED_CODER_MODEL,
            router.DEEPSEEK_MODEL,
        ]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "thermal_blocks_gpu", return_value=None), \
             patch.object(router, "media_pressure", return_value=False), \
             patch.object(router, "prepare_gpu_model", return_value={
                 "attempted": [], "keep_alive_sent": [], "remaining": [],
                 "verified": True, "reason": "empty",
             }):
            d = router.decide(
                "auto", prompt="write a python function that parses JSON")
        self.assertFalse(d.detail.get("gpu_tool_fallback"))
        import tools
        self.assertEqual("gpu", tools.profile_for(d))
        self.assertEqual(router.JOSIEFIED_CODER_MODEL, d.model)


class GpuImageProfileTests(unittest.TestCase):
    def test_schemas_gpu_image_is_exactly_image_direct_tools(self):
        import tools
        names = [item["function"]["name"] for item in tools.schemas(profile="gpu_image")]
        self.assertEqual(list(tools.IMAGE_DIRECT_TOOLS), names)
        self.assertEqual(set(tools.IMAGE_DIRECT_TOOLS), set(names))
        self.assertNotIn("see_image", names)
        self.assertNotIn("web_search", names)
        self.assertLess(len(names), 10)

    def test_image_capability_profile_for_is_gpu_image(self):
        import tools
        d = type("D", (), {
            "backend": "ollama", "tier": "gpu",
            "detail": {"capability": router.CAP_IMAGE},
        })()
        self.assertEqual("gpu_image", tools.profile_for(d))

    def test_image_capability_on_cpu_tier_still_gpu_image(self):
        """Busy-GPU Huihui-8B fallback must not collapse to meta-tools."""
        import tools
        d = type("D", (), {
            "backend": "ollama", "tier": "cpu",
            "detail": {"capability": router.CAP_IMAGE},
        })()
        self.assertEqual("gpu_image", tools.profile_for(d))

    def test_pinned_image_prompt_decide_uses_gpu_image_profile(self):
        import tools
        gpu_have = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        prompt = (
            "still frames only. photoreal live-action images of two adult "
            "women from my reference sheets. No captions on the images."
        )
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "media_pressure", return_value=False):
            d = router.decide(
                "auto",
                model=router.PRIMARY_REASONING_MODEL,
                prompt=prompt,
            )
        self.assertEqual(router.CAP_IMAGE, d.detail.get("capability"))
        self.assertEqual("gpu_image", tools.profile_for(d))
        names = {item["function"]["name"] for item in tools.schemas(
            profile=tools.profile_for(d), prompt=prompt)}
        self.assertEqual(set(tools.IMAGE_DIRECT_TOOLS), names)

    def test_non_image_pinned_huihui_still_full_gpu(self):
        import tools
        gpu_have = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "media_pressure", return_value=False):
            d = router.decide(
                "auto",
                model=router.PRIMARY_REASONING_MODEL,
                prompt="list the files in the current folder",
            )
        self.assertEqual("gpu", tools.profile_for(d))


class TokenEstimateTests(unittest.TestCase):
    def _case4_messages(self):
        import agent
        prompt = (
            "Start an automatic ComfyUI workflow now. Load the API-format "
            "graph at artifacts/benchmarks/2026-09-05_task_completion/"
            "txt2img_mcp_test.json and enqueue it via comfy_workflow with "
            "tool enqueue_workflow and action enqueue. Do not use "
            "comfy_generate. After enqueue, report the prompt_id. "
            "Do not restart ComfyUI."
        )
        history = [{"role": "user", "content": prompt}]
        system = agent.system_prompt(history, include_project=True)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ], prompt

    def test_measured_schema_constant_keeps_case4_under_14b_threshold(self):
        """Fix 2 alone: full 68-tool GPU catalog must not trip 16k demotion."""
        import tools
        msgs, _prompt = self._case4_messages()
        full = tools.schemas(include_project=True, profile="gpu")
        est = router.estimate_context_tokens(msgs, full)
        old = max(1, int(len(json.dumps(
            {"messages": msgs, "tools": full},
            ensure_ascii=False, separators=(",", ":"),
        )) / 3.4))
        self.assertGreater(len(full), 50)
        self.assertGreater(old, router.PRIMARY_SAFE_PROMPT_TOKENS)
        self.assertLessEqual(est, router.PRIMARY_SAFE_PROMPT_TOKENS)

    def test_gpu_core_schema_under_threshold_even_with_old_char_heuristic(self):
        """Fix 1 alone: curated catalog would not have overflowed 16k."""
        import tools
        msgs, prompt = self._case4_messages()
        core = tools.schemas(
            include_project=True, profile="gpu_core", prompt=prompt)
        old = max(1, int(len(json.dumps(
            {"messages": msgs, "tools": core},
            ensure_ascii=False, separators=(",", ":"),
        )) / 3.4))
        self.assertIn("read_file", {s["function"]["name"] for s in core})
        self.assertIn("comfy_workflow", {s["function"]["name"] for s in core})
        self.assertNotIn("see_image", {s["function"]["name"] for s in core})
        self.assertLessEqual(old, router.PRIMARY_SAFE_PROMPT_TOKENS)
        self.assertLessEqual(
            router.estimate_context_tokens(msgs, core),
            router.PRIMARY_SAFE_PROMPT_TOKENS,
        )

    def test_farm_down_case4_stays_on_huihui_14b(self):
        import tools
        msgs, prompt = self._case4_messages()
        full = tools.schemas(include_project=True, profile="gpu")
        tokens = router.estimate_context_tokens(msgs, full)
        gpu_have = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=_gpu_idle()), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=gpu_have), \
             patch.object(router, "_farm_reachable", return_value=False), \
             patch.object(router, "media_pressure", return_value=False):
            d = router.decide(
                "auto", prompt=prompt, prompt_tokens=tokens)
        self.assertEqual(router.PRIMARY_REASONING_MODEL, d.model)
        self.assertNotEqual(router.FALLBACK_REASONING_MODEL, d.model)
        self.assertNotIn("predictive context-length protection", d.reason)
        self.assertTrue(d.detail.get("gpu_tool_fallback"))


if __name__ == "__main__":
    unittest.main()
