#!/usr/bin/env python3
"""Deterministic CPU/GPU handoff tests. No model is loaded by this suite."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import router  # noqa: E402


class RouterSwitchingTests(unittest.TestCase):
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

    @staticmethod
    def _tier_tags(host):
        if host == router.CPU_HOST:
            return [router.FALLBACK_REASONING_MODEL, "cpu-only:latest"]
        return [router.FALLBACK_REASONING_MODEL, "gpu-only:latest"]

    def test_chat_busy_cleanup_ignores_transient_windows_file_lock(self):
        with patch.object(router, "CHAT_BUSY_FILE", Path("locked-chat-busy.json")), \
             patch.object(Path, "unlink", side_effect=PermissionError("locked")) as unlink, \
             patch.object(router.time, "sleep") as pause:
            router.set_chat_busy(False)
        self.assertEqual(3, unlink.call_count)
        self.assertEqual(2, pause.call_count)

    def test_auto_moves_gpu_cpu_gpu_across_turns(self):
        installed = ["qwen3:8b", "qwen2.5-coder:14b", "qwen3vl-abl:latest"]
        states = [
            (False, "idle", {"state": "idle"}),
            (True, "render claimed", {"state": "busy"}),
            (False, "idle again", {"state": "idle"}),
        ]
        with patch.object(router, "gpu_busy", side_effect=states), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=installed), \
             patch.object(router, "_running_models",
                          side_effect=[["qwen3vl-abl:latest"], []]), \
             patch.object(router, "unload") as unload:
            first = router.decide("auto")
            second = router.decide("auto")
            third = router.decide("auto")

        self.assertEqual((first.tier, first.host), ("gpu", router.GPU_HOST))
        self.assertEqual((second.tier, second.host), ("cpu", router.CPU_HOST))
        self.assertEqual((third.tier, third.host), ("gpu", router.GPU_HOST))
        self.assertEqual(second.options()["num_gpu"], 0)
        self.assertEqual(second.options()["num_thread"], 4)
        self.assertGreater(first.options()["num_gpu"], 0)
        unload.assert_called_once_with(router.GPU_HOST, "qwen3vl-abl:latest")
        self.assertTrue(second.detail["gpu_eviction"]["verified"])
        self.assertEqual(second.detail["gpu_eviction"]["attempted"],
                         ["qwen3vl-abl:latest"])

    def test_empty_gpu_server_does_not_issue_pointless_unload(self):
        with patch.object(router, "gpu_busy",
                          return_value=(True, "busy", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=["qwen3:8b"]), \
             patch.object(router, "_running_models", return_value=[]), \
             patch.object(router, "unload") as unload:
            decision = router.decide("auto")
        self.assertEqual(decision.tier, "cpu")
        unload.assert_not_called()
        self.assertTrue(decision.detail["gpu_eviction"]["verified"])

    def test_unverified_gpu_eviction_refuses_cpu_handoff(self):
        with patch.object(router, "gpu_busy", return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "evict_gpu_residents", return_value={
                 "verified": False, "reason": "GPU Ollama model eviction timed out",
             }):
            decision = router.decide("auto", model=router.PRIMARY_REASONING_MODEL)
        self.assertIsNone(decision.model)
        self.assertIn("eviction could not be verified", decision.reason)

    def test_salad_xmrig_does_not_force_cpu_num_gpu_zero(self):
        xmrig = r"C:\ProgramData\Salad\workloads\XMRig-6.18.0\xmrig.exe"
        brave = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
        with patch.object(router, "queue_owner", return_value=(False, "no queue")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "gpu_memory", return_value=(1745, [brave, xmrig])), \
             patch.object(router, "_running_models", return_value=[]):
            busy, why, detail = router.gpu_busy()
        self.assertFalse(busy, why)
        self.assertTrue(any("xmrig" in p.lower() for p in detail["background_gpu_compute"]))

        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags",
                          return_value=[router.FALLBACK_REASONING_MODEL,
                                        router.PRIMARY_REASONING_MODEL]), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("auto")
        self.assertEqual(decision.tier, "gpu")
        self.assertEqual(decision.host, router.GPU_HOST)
        self.assertGreater(decision.options()["num_gpu"], 0)

    def test_codex_desktop_display_context_does_not_claim_the_gpu(self):
        codex = (r"C:\Program Files\WindowsApps\OpenAI.Codex_26.825.3734.0_"
                 r"x64__2p2nqsd0c76g0\app\ChatGPT.exe")
        with patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "gpu_memory", return_value=(81, [codex])), \
             patch.object(router, "_running_models", return_value=[]):
            busy, why, _detail = router.gpu_busy()
        self.assertFalse(busy, why)
        self.assertIn("GPU idle", why)

    def test_idle_steam_client_display_context_does_not_claim_the_gpu(self):
        steam = r"C:\Program Files (x86)\Steam\steam.exe"
        with patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "gpu_memory", return_value=(121, [steam])), \
             patch.object(router, "_running_models", return_value=[]):
            busy, why, _detail = router.gpu_busy()
        self.assertFalse(busy, why)
        self.assertIn("GPU idle", why)

    def test_real_foreign_compute_process_still_claims_the_gpu(self):
        with patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "gpu_memory", return_value=(81, [r"C:\Python\python.exe"])), \
             patch.object(router, "_running_models", return_value=[]):
            busy, _why, _detail = router.gpu_busy()
        self.assertTrue(busy)

    def test_status_never_evicts_gpu_models(self):
        with patch.object(router, "gpu_busy", return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "evict_gpu_residents") as evict:
            router.status()
        evict.assert_not_called()

    def test_forced_gpu_is_refused_while_busy(self):
        with patch.object(router, "gpu_busy",
                          return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=["qwen3:8b"]), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("gpu")
        self.assertEqual(decision.tier, "cpu")
        self.assertIn("GPU requested but unavailable", decision.reason)

    def test_pinned_model_moves_tiers_without_substitution(self):
        states = [(False, "idle", {}), (True, "busy", {})]
        with patch.object(router, "gpu_busy", side_effect=states), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=self._tier_tags), \
             patch.object(router, "_running_models", return_value=[]):
            gpu = router.decide("auto", model=router.FALLBACK_REASONING_MODEL)
            cpu = router.decide("auto", model=router.FALLBACK_REASONING_MODEL)
        self.assertEqual((gpu.tier, gpu.model), ("gpu", router.FALLBACK_REASONING_MODEL))
        self.assertEqual((cpu.tier, cpu.model), ("cpu", router.FALLBACK_REASONING_MODEL))

    def test_cpu_pinned_fallback_model_not_falsely_refused(self):
        # Regression, live bug 2026-09-06: a chat pinned directly to the
        # plain 8B fallback model, explicitly requesting the CPU tier, while
        # that model is only installed in the GPU Ollama store (not the
        # dedicated CPU store) and the GPU is idle. `_paired_cpu_fallback`
        # resolves this correctly (reuse the GPU-store copy with num_gpu=0)
        # and a valid `selected` is set -- but the final not-installed
        # refusal at the end of the CPU branch used to check only
        # `paired_cpu_fallback` (scoped to the primary-14B-pairing and
        # coding-model cases), not whether `selected` was already resolved,
        # so it discarded the correct answer and produced a
        # self-contradictory "cannot run ... GPU tier is unavailable"
        # message immediately followed by "using Huihui 8B on CPU ... GPU
        # idle" in the same sentence.
        def tags(host):
            if host == router.CPU_HOST:
                return ["cpu-only:latest"]
            return [router.FALLBACK_REASONING_MODEL, "gpu-only:latest"]

        with patch.object(router, "gpu_busy", return_value=(False, "GPU idle (84 MB used, no foreign compute process)", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("cpu", model=router.FALLBACK_REASONING_MODEL)
        self.assertEqual("cpu", decision.tier)
        self.assertEqual(router.FALLBACK_REASONING_MODEL, decision.model)
        self.assertNotIn("cannot run now", decision.reason)
        self.assertIn("using Huihui 8B on CPU", decision.reason)

    def test_gpu_only_pin_refuses_instead_of_substituting_when_busy(self):
        gpu_models = router.GPU_MODELS + ["gpu-only:latest"]
        with patch.object(router, "GPU_MODELS", gpu_models), \
             patch.object(router, "gpu_busy", return_value=(True, "busy", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=self._tier_tags), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("auto", model="gpu-only:latest")
        self.assertIsNone(decision.model)
        self.assertIn("cannot run now", decision.reason)

    def test_heretic_pin_refuses_while_busy_without_cpu_substitution(self):
        with patch.object(router, "gpu_busy", return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]):
            decision = router.decide("auto", model=router.GPT_OSS_20B_HERETIC_MODEL)
        self.assertEqual("gpu", decision.tier)
        self.assertIsNone(decision.model)
        self.assertIn("will not fall back to CPU", decision.reason)

    def test_gpu_only_opt_in_pin_refuses_when_busy_even_if_eviction_unverified(self):
        # Regression: eviction-verification used to return a CPU Decision
        # *before* the GPU-only opt-in busy refusal, silently becoming Huihui.
        with patch.object(router, "gpu_busy", return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "evict_gpu_residents", return_value={
                 "verified": False, "reason": "GPU Ollama model eviction timed out",
             }) as evict:
            decision = router.decide("auto", model=router.GPT_OSS_20B_HERETIC_MODEL)
        self.assertEqual("gpu", decision.tier)
        self.assertEqual(router.GPU_HOST, decision.host)
        self.assertIsNone(decision.model)
        self.assertIn("will not fall back to CPU", decision.reason)
        self.assertNotIn("eviction could not be verified", decision.reason)
        evict.assert_not_called()

    def test_powerinfer_pin_refuses_when_busy_even_if_eviction_unverified(self):
        with patch.object(router, "gpu_busy",
                          return_value=(True, "a ComfyUI backend is listening on port 8188",
                                        {"comfy_port_8188": "listening"})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "powerinfer_proxy_listening", return_value=True), \
             patch.object(router, "powerinfer_backend_listening", return_value=True), \
             patch.object(router, "evict_gpu_residents", return_value={
                 "verified": False, "reason": "GPU Ollama model eviction timed out",
             }) as evict, \
             patch.object(router, "try_idle_comfy_timeshare",
                          return_value=(False, "test: render intent")):
            decision = router.decide("auto", model=router.POWERINFER_MODEL_ALIAS)
        self.assertEqual("gpu", decision.tier)
        self.assertEqual("powerinfer", decision.backend)
        self.assertIsNone(decision.model)
        self.assertIn("will not fall back to Ollama or CPU", decision.reason)
        self.assertNotIn("eviction could not be verified", decision.reason)
        evict.assert_not_called()

    def test_heretic_pin_uses_gpu_with_vram_ceiling_when_available(self):
        def tags(host):
            return ([router.FALLBACK_REASONING_MODEL] if host == router.CPU_HOST
                    else [router.GPT_OSS_20B_HERETIC_MODEL])
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags):
            decision = router.decide("auto", model=router.GPT_OSS_20B_HERETIC_MODEL)
        self.assertEqual(("gpu", router.GPT_OSS_20B_HERETIC_MODEL),
                         (decision.tier, decision.model))
        self.assertEqual(1742, decision.options()["num_ctx"])
        self.assertGreater(decision.options()["num_gpu"], 0)

    def test_heretic_stays_visible_as_disabled_setup_option(self):
        def tags(host):
            return [router.FALLBACK_REASONING_MODEL] if host == router.CPU_HOST else []
        with patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags):
            models = router.chat_models()
        heretic = next(m for m in models if m["name"] == router.GPT_OSS_20B_HERETIC_MODEL)
        self.assertFalse(heretic["available"])
        self.assertTrue(heretic["gpu_only"])

    def test_heretic_picker_emits_ollama_latest_tag_when_catalogue_has_it(self):
        tagged = router.GPT_OSS_20B_HERETIC_MODEL + ":latest"
        def tags(host):
            return [router.FALLBACK_REASONING_MODEL] if host == router.CPU_HOST else [tagged]
        with patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags):
            models = router.chat_models()
        heretic = next(m for m in models if m["name"] == tagged)
        self.assertTrue(heretic["available"])
        self.assertTrue(heretic["gpu_only"])

    def test_heretic_latest_suffix_gets_same_gpu_only_busy_refusal(self):
        tagged = router.GPT_OSS_20B_HERETIC_MODEL + ":latest"
        with patch.object(router, "gpu_busy", return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "evict_gpu_residents") as evict:
            decision = router.decide("auto", model=tagged)
        self.assertEqual("gpu", decision.tier)
        self.assertIsNone(decision.model)
        self.assertIn("will not fall back to CPU", decision.reason)
        evict.assert_not_called()

    def test_powerinfer_latest_suffix_gets_same_gpu_only_busy_refusal(self):
        tagged = router.POWERINFER_MODEL_ALIAS + ":latest"
        with patch.object(router, "gpu_busy",
                          return_value=(True, "a ComfyUI backend is listening on port 8188",
                                        {"comfy_port_8188": "listening"})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "powerinfer_proxy_listening", return_value=True), \
             patch.object(router, "powerinfer_backend_listening", return_value=True), \
             patch.object(router, "evict_gpu_residents") as evict, \
             patch.object(router, "try_idle_comfy_timeshare",
                          return_value=(False, "test: render intent")):
            decision = router.decide("auto", model=tagged)
        self.assertEqual("gpu", decision.tier)
        self.assertEqual("powerinfer", decision.backend)
        self.assertIsNone(decision.model)
        self.assertIn("will not fall back to Ollama or CPU", decision.reason)
        evict.assert_not_called()

    def test_cpu_only_pin_uses_cpu_even_while_gpu_is_free(self):
        cpu_models = router.CPU_MODELS + ["cpu-only:latest"]
        def only_cpu(host):
            return ["cpu-only:latest"] if host == router.CPU_HOST else ["gpu-only:latest"]
        with patch.object(router, "CPU_MODELS", cpu_models), \
             patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=only_cpu), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("auto", model="cpu-only:latest")
        self.assertEqual((decision.tier, decision.model),
                         ("cpu", "cpu-only:latest"))

    def test_long_image_intent_keeps_primary_instead_of_8b_fallback(self):
        pair = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        prompt = (
            "AGENT TASK: still frames only. Photoreal live-action. "
            "MAKE START + LAST FOR EACH BEAT. Output pre01_start.png "
            "through pre14_last.png. Stop after stills."
        )
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=pair), \
             patch.object(router, "media_pressure", return_value=False):
            decision = router.decide(
                "auto", model=router.PRIMARY_REASONING_MODEL, prompt=prompt,
                prompt_tokens=router.PRIMARY_SAFE_PROMPT_TOKENS + 1)
        self.assertEqual((decision.tier, decision.model),
                         ("gpu", router.PRIMARY_REASONING_MODEL))
        self.assertEqual(router.CAP_IMAGE, decision.detail.get("capability"))
        self.assertNotIn("adaptive_fallback", decision.detail)
        self.assertIn("adaptive_fallback_skipped", decision.detail)

    def test_long_primary_context_routes_to_paired_gpu_fallback(self):
        pair = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=pair):
            decision = router.decide("auto", model=router.PRIMARY_REASONING_MODEL,
                                     prompt_tokens=router.PRIMARY_SAFE_PROMPT_TOKENS + 1)
        self.assertEqual((decision.tier, decision.model),
                         ("gpu", router.FALLBACK_REASONING_MODEL))
        self.assertEqual("predictive context-length protection",
                         decision.detail["adaptive_fallback"]["reason"])
        self.assertEqual(40960, decision.options()["num_ctx"])
        self.assertGreater(decision.options()["num_gpu"], 0)

    def test_short_primary_context_stays_on_full_gpu_primary(self):
        pair = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=pair):
            decision = router.decide("auto", model=router.PRIMARY_REASONING_MODEL,
                                     prompt_tokens=1000)
        self.assertEqual((decision.tier, decision.model),
                         ("gpu", router.PRIMARY_REASONING_MODEL))
        self.assertEqual(33976, decision.options()["num_ctx"])

    def test_primary_failure_unloads_then_retries_on_gpu_fallback(self):
        pair = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        previous = router.Decision("gpu", router.GPU_HOST,
                                   router.PRIMARY_REASONING_MODEL, False, "primary", {})
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=pair), \
             patch.object(router, "unload") as unload:
            fallback = router.fallback_after_primary_failure(
                previous, RuntimeError("CUDA out of memory"))
        self.assertIsNotNone(fallback)
        self.assertEqual((fallback.tier, fallback.model),
                         ("gpu", router.FALLBACK_REASONING_MODEL))
        unload.assert_called_once_with(router.GPU_HOST, router.PRIMARY_REASONING_MODEL)

    def test_own_resident_ollama_model_is_not_mistaken_for_a_render(self):
        router.note_gpu_owned(router.PRIMARY_REASONING_MODEL)
        with patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "gpu_memory", return_value=(11954, ["[Insufficient Permissions]"])), \
             patch.object(router, "_running_models",
                          return_value=[router.PRIMARY_REASONING_MODEL]):
            busy, why, detail = router.gpu_busy()
        self.assertFalse(busy)
        self.assertIn("resident Ollama", why)
        self.assertEqual([router.PRIMARY_REASONING_MODEL],
                         detail["gpu_resident_ollama_models"])
        self.assertEqual([router.PRIMARY_REASONING_MODEL],
                         detail["gpu_owned_ollama_models"])

    def test_third_party_gpu_host_resident_is_busy_not_ours(self):
        """comfy-pilot 2026-09-05df: Huihui 8B on :11434 that we never selected."""
        with patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "gpu_memory", return_value=(7623, ["ollama.exe"])), \
             patch.object(router, "chat_busy", return_value=False), \
             patch.object(router, "_running_models",
                          return_value=[router.FALLBACK_REASONING_MODEL]):
            busy, why, detail = router.gpu_busy()
        self.assertTrue(busy)
        self.assertIn("not loaded by this agent", why)
        self.assertEqual([router.FALLBACK_REASONING_MODEL],
                         detail["gpu_unexplained_ollama_models"])
        self.assertEqual([], detail["gpu_owned_ollama_models"])

    def test_cpu_chat_busy_does_not_waive_third_party_resident(self):
        with patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "gpu_memory", return_value=(7623, ["ollama.exe"])), \
             patch.object(router, "chat_busy", return_value=True), \
             patch.object(router, "_running_models",
                          return_value=[router.FALLBACK_REASONING_MODEL]):
            busy, why, _detail = router.gpu_busy()
        self.assertTrue(busy)
        self.assertIn("not loaded by this agent", why)

    def test_in_flight_owned_load_waives_empty_api_ps(self):
        router.note_gpu_owned(router.PRIMARY_REASONING_MODEL)
        with patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "gpu_memory", return_value=(7623, ["ollama.exe"])), \
             patch.object(router, "chat_busy", return_value=True), \
             patch.object(router, "_running_models", return_value=[]):
            busy, why, _detail = router.gpu_busy()
        self.assertFalse(busy)
        self.assertIn("loading", why)

    def test_pruned_owned_tag_does_not_claim_later_third_party_reload(self):
        router.note_gpu_owned(router.FALLBACK_REASONING_MODEL)
        with patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "chat_busy", return_value=False), \
             patch.object(router, "gpu_memory", return_value=(70, [])), \
             patch.object(router, "_running_models", return_value=[]):
            busy, _why, _detail = router.gpu_busy()
        self.assertFalse(busy)
        with patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "chat_busy", return_value=False), \
             patch.object(router, "gpu_memory", return_value=(7623, ["ollama.exe"])), \
             patch.object(router, "_running_models",
                          return_value=[router.FALLBACK_REASONING_MODEL]):
            busy, why, detail = router.gpu_busy()
        self.assertTrue(busy)
        self.assertIn("not loaded by this agent", why)
        self.assertEqual([], detail["gpu_owned_ollama_models"])

    def test_busy_gpu_moves_primary_huihui_chat_to_cpu_8b_not_dolphin(self):
        def tier_tags(host):
            if host == router.CPU_HOST:
                return [router.FALLBACK_REASONING_MODEL, "dolphin3:latest"]
            return [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]

        with patch.object(router, "gpu_busy", return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tier_tags), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("auto", model=router.PRIMARY_REASONING_MODEL)
        self.assertEqual((decision.tier, decision.model),
                         ("cpu", router.FALLBACK_REASONING_MODEL))
        self.assertEqual(0, decision.options()["num_gpu"])
        self.assertIn("paired CPU fallback", decision.reason)

    def test_busy_gpu_with_cpu_8b_does_not_probe_gpu_inventory(self):
        calls = []

        def tier_tags(host):
            calls.append(host)
            if host == router.CPU_HOST:
                return [router.FALLBACK_REASONING_MODEL]
            raise AssertionError("GPU inventory must not be probed while render is busy")

        with patch.object(router, "gpu_busy", return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tier_tags), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("auto", model=router.PRIMARY_REASONING_MODEL)
        self.assertEqual((decision.tier, decision.model),
                         ("cpu", router.FALLBACK_REASONING_MODEL))
        self.assertEqual(calls, [router.CPU_HOST, router.CPU_HOST])
        self.assertIn("gpu_inventory_skipped", decision.detail)

    def test_uninstalled_legacy_primary_pin_continues_on_cpu_8b(self):
        legacy_primary = "huihui_ai/qwen3-abliterated:14b-v2"
        def tier_tags(host):
            return [router.FALLBACK_REASONING_MODEL] if host == router.CPU_HOST else []
        with patch.object(router, "gpu_busy", return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tier_tags), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("auto", model=legacy_primary)
        self.assertEqual(("cpu", router.CPU_HOST, router.FALLBACK_REASONING_MODEL),
                         (decision.tier, decision.host, decision.model))
        self.assertIn("unavailable_primary_chat", decision.detail)

    def test_busy_gpu_reuses_gpu_store_8b_with_cpu_only_options(self):
        def tier_tags(host):
            if host == router.CPU_HOST:
                return ["dolphin3:latest"]
            return [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]

        with patch.object(router, "gpu_busy", return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tier_tags), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("auto", model=router.PRIMARY_REASONING_MODEL)
        self.assertEqual((decision.tier, decision.host, decision.model),
                         ("cpu", router.GPU_HOST, router.FALLBACK_REASONING_MODEL))
        self.assertEqual(0, decision.options()["num_gpu"])
        self.assertEqual(4, decision.options()["num_thread"])

    def test_gpu_server_down_routes_to_cpu_when_gpu_not_busy(self):
        """Case B: GPU idle and GPU not busy, but Ollama server :11434 is not running."""
        def server_up(host):
            return host == router.CPU_HOST

        def tier_tags(host):
            return [router.FALLBACK_REASONING_MODEL] if host == router.CPU_HOST else []

        with patch.object(router, "gpu_busy",
                          return_value=(False, "GPU idle (74 MB used)", {})), \
             patch.object(router, "up", side_effect=server_up), \
             patch.object(router, "_tags", side_effect=tier_tags), \
             patch.object(router, "_running_models", return_value=None):
            decision = router.decide("auto")
        self.assertEqual(decision.tier, "cpu")
        self.assertEqual(decision.model, router.FALLBACK_REASONING_MODEL)
        self.assertFalse(decision.gpu_busy)

    def test_coding_mode_selects_coding_model_when_gpu_idle(self):
        have = [router.PRIMARY_REASONING_MODEL, router.CODING_MODEL,
                router.FALLBACK_REASONING_MODEL]
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=have):
            decision = router.decide("auto", model=router.CODING_MODEL)
        self.assertEqual((decision.tier, decision.model),
                         ("gpu", router.CODING_MODEL))
        self.assertGreater(decision.options()["num_gpu"], 0)

    def test_unknown_coding_model_falls_back_cleanly(self):
        have = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        missing = "huihui_ai/qwen2.5-coder-abliterate:99b"
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=have):
            decision = router.decide("auto", model=missing)
        self.assertIsNotNone(decision.model)
        self.assertNotEqual(missing, decision.model)
        self.assertEqual(router.PRIMARY_REASONING_MODEL, decision.model)
        self.assertEqual("gpu", decision.tier)
        self.assertIn("unavailable_coding_model", decision.detail)

    def test_coding_mode_uses_cpu_when_gpu_busy(self):
        def tier_tags(host):
            if host == router.CPU_HOST:
                return [router.FALLBACK_REASONING_MODEL]
            return [router.CODING_MODEL, router.PRIMARY_REASONING_MODEL]

        with patch.object(router, "gpu_busy", return_value=(True, "render owns GPU", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tier_tags), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("auto", model=router.CODING_MODEL)
        self.assertEqual(decision.tier, "cpu")
        self.assertEqual(decision.model, router.FALLBACK_REASONING_MODEL)
        self.assertEqual(0, decision.options()["num_gpu"])
        self.assertIn("coding mode on CPU", decision.reason)
        self.assertIn("14B coder on CPU is slow", decision.reason)

    def test_chat_models_mark_coder_as_coding_kind(self):
        def tags(host):
            if host == router.CPU_HOST:
                return [router.FALLBACK_REASONING_MODEL]
            return [router.CODING_MODEL, router.PRIMARY_REASONING_MODEL]
        with patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags):
            models = router.chat_models()
        by_name = {m["name"]: m for m in models}
        self.assertEqual("coding", by_name[router.CODING_MODEL]["kind"])
        self.assertEqual("chat", by_name[router.PRIMARY_REASONING_MODEL]["kind"])

    def test_primary_stays_visible_when_busy_start_has_no_gpu_catalogue(self):
        def tags(host):
            return [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL] \
                if host == router.CPU_HOST else []
        with patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags), \
             patch.object(router, "_LAST_VERIFIED_GPU_MODELS", set()):
            by_name = {item["name"]: item for item in router.chat_models(include_gpu=False)}
        primary = by_name[router.PRIMARY_REASONING_MODEL]
        self.assertFalse(primary["available"])
        self.assertTrue(primary["gpu_only"])
        self.assertIn("currently unavailable", primary["label"])

    def test_powerinfer_stays_visible_as_disabled_when_down(self):
        def tags(host):
            return [router.FALLBACK_REASONING_MODEL] if host == router.CPU_HOST else []
        with patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags), \
             patch.object(router, "powerinfer_proxy_listening", return_value=False), \
             patch.object(router, "powerinfer_backend_listening", return_value=False):
            models = router.chat_models()
        entry = next(m for m in models if m["name"] == router.POWERINFER_MODEL_ALIAS)
        self.assertFalse(entry["available"])
        self.assertTrue(entry["gpu_only"])
        self.assertEqual("powerinfer", entry["backend"])
        self.assertIn("does not start", entry["setup_hint"])

    def test_powerinfer_becomes_selectable_when_proxy_and_backend_listen(self):
        def tags(host):
            return [router.FALLBACK_REASONING_MODEL] if host == router.CPU_HOST else []
        with patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", side_effect=tags), \
             patch.object(router, "powerinfer_proxy_listening", return_value=True), \
             patch.object(router, "powerinfer_backend_listening", return_value=True):
            models = router.chat_models()
        entry = next(m for m in models if m["name"] == router.POWERINFER_MODEL_ALIAS)
        self.assertTrue(entry["available"])
        self.assertTrue(entry["gpu"])

    def test_powerinfer_pin_refuses_while_comfy_busy_without_ollama_substitution(self):
        with patch.object(router, "gpu_busy",
                          return_value=(True, "a ComfyUI backend is listening on port 8188",
                                        {"comfy_port_8188": "listening"})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "powerinfer_proxy_listening", return_value=True), \
             patch.object(router, "powerinfer_backend_listening", return_value=True), \
             patch.object(router, "_running_models", return_value=[]), \
             patch.object(router, "try_idle_comfy_timeshare",
                          return_value=(False, "test: render intent")):
            decision = router.decide("auto", model=router.POWERINFER_MODEL_ALIAS)
        self.assertEqual("powerinfer", decision.backend)
        self.assertIsNone(decision.model)
        self.assertIn("will not fall back to Ollama or CPU", decision.reason)

    def test_powerinfer_pin_selects_when_idle_8188_timeshare_claims(self):
        with patch.object(router, "gpu_busy",
                          return_value=(True, "a ComfyUI backend is listening on port 8188",
                                        {"comfy_port_8188": "listening"})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "powerinfer_proxy_listening", return_value=True), \
             patch.object(router, "powerinfer_backend_listening", return_value=True), \
             patch.object(router, "_running_models", return_value=[]), \
             patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "thermal_blocks_gpu", return_value=None), \
             patch.object(router, "try_idle_comfy_timeshare",
                          return_value=(True, "cleared idle ComfyUI")):
            decision = router.decide("auto", model=router.POWERINFER_MODEL_ALIAS)
        self.assertEqual("powerinfer", decision.backend)
        self.assertEqual(router.POWERINFER_MODEL_ALIAS, decision.model)
        self.assertFalse(decision.gpu_busy)
        self.assertEqual("gpu", decision.tier)

    def test_powerinfer_pin_refuses_clearly_when_proxy_is_down(self):
        with patch.object(router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "powerinfer_proxy_listening", return_value=False), \
             patch.object(router, "powerinfer_backend_listening", return_value=True):
            decision = router.decide("auto", model=router.POWERINFER_MODEL_ALIAS)
        self.assertEqual("powerinfer", decision.backend)
        self.assertEqual(router.POWERINFER_PROXY_HOST, decision.host)
        self.assertIsNone(decision.model)
        self.assertIn("proxy is not listening", decision.reason)
        self.assertIn("does not start", decision.reason)

    def test_powerinfer_pin_uses_proxy_when_it_already_owns_the_gpu(self):
        with patch.object(router, "gpu_busy",
                          return_value=(True, "PowerInfer is using the GPU",
                                        {"powerinfer_backend": "listening"})), \
             patch.object(router, "up", return_value=True), \
             patch.object(router, "_tags", return_value=[router.FALLBACK_REASONING_MODEL]), \
             patch.object(router, "powerinfer_proxy_listening", return_value=True), \
             patch.object(router, "powerinfer_backend_listening", return_value=True), \
             patch.object(router, "_running_models", return_value=[]):
            decision = router.decide("auto", model=router.POWERINFER_MODEL_ALIAS)
        self.assertEqual(
            ("gpu", router.POWERINFER_PROXY_HOST, router.POWERINFER_MODEL_ALIAS, "powerinfer"),
            (decision.tier, decision.host, decision.model, decision.backend),
        )
        self.assertEqual(512, decision.options()["num_predict"])
        self.assertNotIn("num_gpu", decision.options())

    def test_powerinfer_on_gpu_forces_ollama_auto_chat_to_cpu(self):
        with patch.object(router, "queue_owner", return_value=(False, "released")), \
             patch.object(router, "comfy_listening", return_value=False), \
             patch.object(router, "gpu_memory",
                          return_value=(9000, [router.POWERINFER_SERVER_EXE])), \
             patch.object(router, "powerinfer_backend_listening", return_value=True), \
             patch.object(router, "_running_models", return_value=[]):
            busy, why, detail = router.gpu_busy()
        self.assertTrue(busy)
        self.assertEqual("PowerInfer is using the GPU", why)
        self.assertIn(router.POWERINFER_SERVER_EXE, detail["powerinfer_compute"])

    def test_unload_resolves_configured_tag_to_resident_v2(self):
        sent = {}

        class _Response:
            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def fake_open(request, timeout):
            sent["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response()

        with patch.object(router, "_running_models",
                          return_value=["huihui_ai/qwen3-abliterated:14b-v2"]), \
             patch.object(router.urllib.request, "urlopen", fake_open):
            router.unload(router.GPU_HOST, router.PRIMARY_REASONING_MODEL)
        self.assertEqual("huihui_ai/qwen3-abliterated:14b-v2", sent["payload"]["model"])

    def test_media_pressure_expires_after_ttl_and_unlinks(self):
        router.set_media_pressure(True)
        self.assertTrue(router.MEDIA_PRESSURE_FILE.is_file())
        self.assertTrue(router.media_pressure())
        written = json.loads(router.MEDIA_PRESSURE_FILE.read_text(encoding="utf-8"))
        expired = float(written["at"]) + router.MEDIA_PRESSURE_TTL_S + 1
        with patch.object(router.time, "time", return_value=expired):
            self.assertFalse(router.media_pressure())
        self.assertFalse(router.MEDIA_PRESSURE_FILE.is_file())

    def test_stale_pressure_file_without_ttl_field_expires(self):
        """Live leak shape from 2026-09-05dw: ``{"at": <old>}`` and no ttl_s."""
        router.MEDIA_PRESSURE_FILE.write_text(
            json.dumps({"at": 1.0}), encoding="utf-8")
        self.assertFalse(router.media_pressure())
        self.assertFalse(router.MEDIA_PRESSURE_FILE.is_file())

    def test_refresh_media_pressure_extends_in_flight_stamp(self):
        router.set_media_pressure(True)
        first = json.loads(router.MEDIA_PRESSURE_FILE.read_text(encoding="utf-8"))["at"]
        later = first + 10
        with patch.object(router.time, "time", return_value=later):
            self.assertTrue(router.refresh_media_pressure())
        second = json.loads(router.MEDIA_PRESSURE_FILE.read_text(encoding="utf-8"))["at"]
        self.assertEqual(later, second)
        self.assertTrue(router.media_pressure())

    def _pinned_14b_gpu(self):
        gpu_have = [router.PRIMARY_REASONING_MODEL, router.FALLBACK_REASONING_MODEL]
        stack = ExitStack()
        stack.enter_context(patch.object(
            router, "gpu_busy",
            return_value=(False, "GPU idle", {"vram_used_mb": 70})))
        stack.enter_context(patch.object(router, "up", return_value=True))
        stack.enter_context(patch.object(router, "_tags", return_value=gpu_have))
        stack.enter_context(patch.object(router, "_farm_reachable", return_value=False))
        stack.enter_context(patch.object(
            router, "queue_owner", return_value=(False, "released")))
        stack.enter_context(patch.object(router, "thermal_blocks_gpu", return_value=None))
        stack.enter_context(patch.object(router, "prepare_gpu_model", return_value={
            "attempted": [], "keep_alive_sent": [], "remaining": [],
            "verified": True, "reason": "empty",
        }))
        return stack

    def test_fresh_media_pressure_demotes_pinned_14b_to_8b(self):
        router.set_media_pressure(True)
        with self._pinned_14b_gpu():
            decision = router.decide(
                "auto",
                model=router.PRIMARY_REASONING_MODEL,
                prompt="hello",
            )
        self.assertEqual("gpu", decision.tier)
        self.assertEqual(router.FALLBACK_REASONING_MODEL, decision.model)
        self.assertIn("media VRAM pressure", decision.reason)

    def test_expired_leaked_pressure_does_not_demote_pinned_14b(self):
        router.MEDIA_PRESSURE_FILE.write_text(
            json.dumps({"at": 1.0}), encoding="utf-8")
        with self._pinned_14b_gpu():
            decision = router.decide(
                "auto",
                model=router.PRIMARY_REASONING_MODEL,
                prompt="hello",
            )
        self.assertEqual("gpu", decision.tier)
        self.assertEqual(router.PRIMARY_REASONING_MODEL, decision.model)
        self.assertNotIn("media VRAM pressure", decision.reason)
        self.assertFalse(router.MEDIA_PRESSURE_FILE.is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
