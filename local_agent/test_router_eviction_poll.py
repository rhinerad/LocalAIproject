"""Router fixes from AUDIT_2026-11-02 area C (finding 10 + P2 subprocess storm).

Covers what router.py already does after the 2026-11-06 WIP commit:
- maybe_evict_for_render() from the 2-second status() poll (finding 10)
- _CACHE_TTL memoisation of gpu_memory()/gpu_free_mb()/_pid_alive() (P2)
- CAP_SWITCH_HYSTERESIS on the 14B capability class switch
- thermal_blocks_gpu() refusing, never raising, when thermal_guard is missing
- set_media_pressure() writing through atomic_io
- _pick(cpu_tier=True) skipping the family fallback (pass 2)

No GPU, no Ollama, no nvidia-smi: every probe is patched.
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import router  # noqa: E402


class _EvictBase(unittest.TestCase):
    def setUp(self) -> None:
        router.reset_render_eviction_state()
        self.addCleanup(router.reset_render_eviction_state)
        self.evicted = threading.Event()

        def fake_evict(**_kw):
            self.evicted.set()
            return {"attempted": ["m"], "remaining": [], "verified": True}

        for target, kw in (
            ("chat_busy", {"return_value": False}),
            ("_load_gpu_owned", {"return_value": [router.PRIMARY_REASONING_MODEL]}),
            ("evict_gpu_residents", {"side_effect": fake_evict}),
        ):
            p = patch.object(router, target, **kw)
            p.start()
            self.addCleanup(p.stop)

    def _join(self) -> None:
        thread = router._RENDER_EVICT_STATE.get("thread")
        if thread is not None:
            thread.join(timeout=5)

    def _detail(self, resident=None) -> dict:
        return {"gpu_resident_ollama_models":
                [router.PRIMARY_REASONING_MODEL] if resident is None else resident}


class MaybeEvictForRenderTests(_EvictBase):
    def test_idle_gpu_never_evicts(self):
        out = router.maybe_evict_for_render(False, {}, now=100.0)
        self.assertFalse(out["triggered"])
        self.assertFalse(self.evicted.is_set())

    def test_busy_gpu_with_our_resident_starts_one_eviction_thread(self):
        out = router.maybe_evict_for_render(True, self._detail(), now=100.0)
        self._join()
        self.assertTrue(out["triggered"], out)
        self.assertTrue(self.evicted.is_set())
        self.assertFalse(router._RENDER_EVICT_STATE["in_flight"])
        self.assertTrue(router._RENDER_EVICT_STATE["last_result"]["verified"])

    def test_streaming_chat_turn_is_not_evicted(self):
        with patch.object(router, "chat_busy", return_value=True):
            out = router.maybe_evict_for_render(True, self._detail(), now=100.0)
        self.assertFalse(out["triggered"])
        self.assertIn("streaming", out["reason"])

    def test_no_owned_residents_means_no_api_ps_read(self):
        with patch.object(router, "_load_gpu_owned", return_value=[]), \
             patch.object(router, "_running_models",
                          side_effect=AssertionError("no /api/ps read")):
            out = router.maybe_evict_for_render(True, {}, now=100.0)
        self.assertFalse(out["triggered"])

    def test_foreign_resident_is_left_alone(self):
        out = router.maybe_evict_for_render(True, self._detail(["someone-else:7b"]), now=100.0)
        self.assertFalse(out["triggered"])
        self.assertFalse(self.evicted.is_set())

    def test_cooldown_stops_the_poll_stacking_evictions(self):
        first = router.maybe_evict_for_render(True, self._detail(), now=100.0)
        self._join()
        self.assertTrue(first["triggered"])
        again = router.maybe_evict_for_render(
            True, self._detail(), now=100.0 + router.RENDER_EVICT_COOLDOWN_S - 1)
        self.assertFalse(again["triggered"])
        self.assertEqual("eviction cooldown", again["reason"])
        later = router.maybe_evict_for_render(
            True, self._detail(), now=100.0 + router.RENDER_EVICT_COOLDOWN_S + 1)
        self._join()
        self.assertTrue(later["triggered"], later)

    def test_in_flight_eviction_is_not_duplicated(self):
        with router._RENDER_EVICT_LOCK:
            router._RENDER_EVICT_STATE["in_flight"] = True
        out = router.maybe_evict_for_render(True, self._detail(), now=100.0)
        self.assertFalse(out["triggered"])
        self.assertIn("in flight", out["reason"])

    def test_probe_interval_rate_limits_api_ps(self):
        calls = []
        with patch.object(router, "_running_models",
                          side_effect=lambda host: calls.append(host) or []):
            router.maybe_evict_for_render(True, {}, now=100.0)
            router.maybe_evict_for_render(True, {}, now=101.0)
            router.maybe_evict_for_render(
                True, {}, now=100.0 + router.RENDER_EVICT_PROBE_INTERVAL_S + 0.1)
        self.assertEqual(2, len(calls))

    def test_status_poll_calls_eviction_with_its_own_snapshot(self):
        seen = []
        snapshot = (True, "render owns the GPU", {"x": 1})
        with patch.object(router, "gpu_busy", return_value=snapshot), \
             patch.object(router, "maybe_evict_for_render",
                          side_effect=lambda b, d: seen.append((b, d)) or {"triggered": False}), \
             patch.object(router, "decide",
                          return_value=router.Decision("cpu", router.CPU_HOST, "m", True,
                                                       "busy", {}, "ollama")), \
             patch.object(router, "up", return_value=False), \
             patch.object(router, "chat_models", return_value=[]), \
             patch.object(router, "_status_timeshare_idle", return_value=False):
            out = router.status()
        self.assertEqual([(True, {"x": 1})], seen)
        self.assertIn("render_eviction", out)


class ProbeMemoTests(unittest.TestCase):
    def setUp(self) -> None:
        router.clear_probe_cache()
        self.addCleanup(router.clear_probe_cache)
        p = patch.object(router, "_CACHE_TTL", 60.0)
        p.start()
        self.addCleanup(p.stop)

    def test_gpu_memory_spawns_once_per_ttl(self):
        calls = []
        with patch.object(router, "_gpu_memory_uncached",
                          side_effect=lambda: calls.append(1) or (1234, ["comfy.exe"])):
            first = router.gpu_memory()
            second = router.gpu_memory()
        self.assertEqual((1234, ["comfy.exe"]), first)
        self.assertEqual(first, second)
        self.assertEqual(1, len(calls))
        second[1].append("mutated")
        self.assertEqual(["comfy.exe"], router.gpu_memory()[1], "callers get a copy")

    def test_unavailable_nvidia_smi_is_never_cached(self):
        calls = []
        with patch.object(router, "_gpu_memory_uncached",
                          side_effect=lambda: calls.append(1) or (None, [])):
            router.gpu_memory()
            router.gpu_memory()
        self.assertEqual(2, len(calls), "unknown must be re-probed every time")
        with patch.object(router, "_gpu_free_mb_uncached",
                          side_effect=lambda: calls.append(2) or None):
            self.assertIsNone(router.gpu_free_mb())
            self.assertIsNone(router.gpu_free_mb())
        self.assertEqual(4, len(calls))

    def test_pid_alive_is_memoised_per_pid(self):
        calls = []
        with patch.object(router, "_pid_alive_uncached",
                          side_effect=lambda pid: calls.append(pid) or True):
            self.assertTrue(router._pid_alive(42))
            self.assertTrue(router._pid_alive(42))
            self.assertTrue(router._pid_alive(43))
        self.assertEqual([42, 43], calls)

    def test_ttl_zero_disables_the_cache(self):
        calls = []
        with patch.object(router, "_CACHE_TTL", 0), \
             patch.object(router, "_gpu_free_mb_uncached",
                          side_effect=lambda: calls.append(1) or 5000):
            router.gpu_free_mb()
            router.gpu_free_mb()
        self.assertEqual(2, len(calls))


class CapabilityHysteresisTests(unittest.TestCase):
    def setUp(self) -> None:
        router.reset_capability_hysteresis()
        self.addCleanup(router.reset_capability_hysteresis)

    def _detail(self) -> dict:
        return {"gpu_owned_ollama_models": [router.PRIMARY_REASONING_MODEL]}

    def test_one_code_turn_keeps_the_resident_primary(self):
        if router._capability_class_of(router.PRIMARY_REASONING_MODEL) != router._CAP_CLASS_CHAT:
            self.skipTest("PRIMARY_REASONING_MODEL overridden to a non-chat class")
        detail = self._detail()
        held = router._capability_hysteresis_hold(router.CAP_CODE, detail)
        self.assertEqual(router.PRIMARY_REASONING_MODEL, held)
        self.assertEqual("hold", detail["capability_hysteresis"]["action"])

    def test_switch_after_threshold_consecutive_turns(self):
        if router._capability_class_of(router.PRIMARY_REASONING_MODEL) != router._CAP_CLASS_CHAT:
            self.skipTest("PRIMARY_REASONING_MODEL overridden to a non-chat class")
        results = []
        for _ in range(router.CAP_SWITCH_HYSTERESIS):
            detail = self._detail()
            results.append(router._capability_hysteresis_hold(router.CAP_CODE, detail))
        self.assertIsNone(results[-1], "switch on the threshold turn")
        self.assertTrue(all(r is not None for r in results[:-1]))
        self.assertEqual("switch", detail["capability_hysteresis"]["action"])

    def test_agreeing_turn_resets_the_streak(self):
        router._capability_hysteresis_hold(router.CAP_CODE, self._detail())
        self.assertIsNone(router._capability_hysteresis_hold("chat", self._detail()))
        self.assertEqual(0, router._CAP_SWITCH_STATE["streak"])

    def test_no_resident_routes_normally(self):
        detail = {"gpu_owned_ollama_models": []}
        with patch.object(router, "_load_gpu_owned", return_value=[]):
            self.assertIsNone(router._capability_hysteresis_hold(router.CAP_CODE, detail))


class ThermalGuardImportTests(unittest.TestCase):
    def test_missing_thermal_guard_refuses_instead_of_raising(self):
        with patch.dict(sys.modules, {"thermal_guard": None}):
            reason = router.thermal_blocks_gpu()
        self.assertIsNotNone(reason)
        self.assertIn("unavailable", reason)


class MediaPressureAtomicTests(unittest.TestCase):
    def test_flag_written_through_atomic_io(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        flag = Path(tmp.name) / "media_vram_pressure.json"
        writes = []
        real = router.atomic_write_text

        def spy(path, text, *a, **kw):
            writes.append(Path(path))
            return real(path, text, *a, **kw)

        with patch.object(router, "RUNTIME", Path(tmp.name)), \
             patch.object(router, "MEDIA_PRESSURE_FILE", flag), \
             patch.object(router, "atomic_write_text", side_effect=spy):
            router.set_media_pressure(True)
            self.assertEqual([flag], writes)
            data = json.loads(flag.read_text(encoding="utf-8"))
            self.assertIn("at", data)
            router.set_media_pressure(False)
            self.assertFalse(flag.exists())
            router.set_media_pressure(False)  # idempotent


class PickCpuTierTests(unittest.TestCase):
    def test_family_fallback_would_pick_a_14b(self):
        have = ["qwen2.5-coder:14b", "qwen2.5:7b"]
        self.assertEqual("qwen2.5-coder:14b", router._pick(have, ["qwen2.5-coder:7b"]))

    def test_cpu_tier_skips_pass_two_and_takes_a_small_model(self):
        have = ["qwen2.5-coder:14b", "qwen2.5:7b"]
        self.assertEqual("qwen2.5:7b",
                         router._pick(have, ["qwen2.5-coder:7b"], cpu_tier=True))

    def test_cpu_tier_with_only_large_models_returns_none(self):
        have = ["qwen2.5-coder:14b", "llama3.1:70b"]
        self.assertIsNone(router._pick(have, ["qwen2.5-coder:7b"], cpu_tier=True))

    def test_exact_match_still_wins_on_cpu_tier(self):
        have = ["qwen2.5:7b", "qwen2.5-coder:7b"]
        self.assertEqual("qwen2.5-coder:7b",
                         router._pick(have, ["qwen2.5-coder:7b"], cpu_tier=True))


if __name__ == "__main__":
    unittest.main()
