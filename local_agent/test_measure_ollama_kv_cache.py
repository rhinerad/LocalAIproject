from __future__ import annotations

import unittest
import sys
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import measure_ollama_kv_cache as bench


class KvCacheBenchmarkTests(unittest.TestCase):
    def test_preflight_requires_idle_gpu_and_installed_model(self):
        with patch.object(bench.router, "gpu_busy", return_value=(False, "idle", {})), \
             patch.object(bench, "_installed", return_value=["huihui_ai/qwen3-abliterated:14b"]):
            facts = bench.preflight("127.0.0.1:11434", "huihui_ai/qwen3-abliterated:14b")
        self.assertEqual(facts["model"], "huihui_ai/qwen3-abliterated:14b")

    def test_preflight_refuses_render_or_unknown_gpu(self):
        with patch.object(bench.router, "gpu_busy", return_value=(True, "ComfyUI active", {})):
            with self.assertRaisesRegex(RuntimeError, "not available"):
                bench.preflight("127.0.0.1:11434", "anything")

    def test_probe_is_deterministic_and_requests_exact_reply(self):
        first = bench.probe_prompt(1_024)
        self.assertEqual(first, bench.probe_prompt(1_024))
        self.assertIn("KV_CACHE_OK", first)
        with self.assertRaises(ValueError):
            bench.probe_prompt(1_023)
        with self.assertRaises(ValueError):
            bench.probe_prompt(1_024, chars_per_token=0)

    def test_probe_scales_with_chars_per_token_not_router_3_4(self):
        sparse = bench.probe_prompt(2_048, chars_per_token=3.4)
        dense = bench.probe_prompt(2_048, chars_per_token=6.5)
        self.assertGreater(len(dense), len(sparse))
        # 3.4 was the silent under-fill: a 6.5 tokenizer needs ~1.9× the chars.
        self.assertAlmostEqual(len(dense) / len(sparse), 6.5 / 3.4, delta=0.15)
        self.assertAlmostEqual(
            len(dense) / 2_048, 6.5, delta=0.4)

    def test_chars_per_token_from_eval_rejects_missing_count(self):
        with self.assertRaises(ValueError):
            bench.chars_per_token_from_eval("hello", 0)
        self.assertEqual(bench.chars_per_token_from_eval("x" * 6500, 1_000), 6.5)

    def test_run_records_quality_speed_and_vram(self):
        response = {
            "message": {"content": "KV_CACHE_OK\n"}, "prompt_eval_count": 100,
            "eval_count": 4, "eval_duration": 2_000_000_000, "load_duration": 3,
        }
        with patch.object(bench.router, "gpu_memory", side_effect=[(100, []), (200, [])]), \
             patch.object(bench, "_post", return_value=response):
            report = bench.run_once(
                "127.0.0.1:11434", "model", 1_024, chars_per_token=6.5)
        self.assertEqual(report["vram_before_mb"], 100)
        self.assertEqual(report["vram_after_mb"], 200)
        self.assertTrue(report["reply_exact"])
        self.assertTrue(report["reply_expected_token_seen"])
        self.assertEqual(report["decode_tokens_per_second"], 2.0)
        self.assertFalse(report["fill_calibrated"])
        self.assertEqual(report["fill_chars_per_token"], 6.5)

    def test_run_once_calibrates_when_chars_per_token_omitted(self):
        sample = bench.probe_prompt(
            bench.CALIBRATE_SAMPLE_TOKENS,
            chars_per_token=bench.FALLBACK_FILL_CHARS_PER_TOKEN)
        calibrate_resp = {
            "message": {"content": "K"},
            "prompt_eval_count": len(sample) // 6,  # 6.0 chars/token
        }
        timed_resp = {
            "message": {"content": "KV_CACHE_OK"},
            "prompt_eval_count": 1_024,
            "eval_count": 4, "eval_duration": 1_000_000_000, "load_duration": 1,
        }
        with patch.object(bench.router, "gpu_memory", side_effect=[(10, []), (20, [])]), \
             patch.object(bench, "_post", side_effect=[calibrate_resp, timed_resp]) as post:
            report = bench.run_once("127.0.0.1:11434", "model", 1_024)
        self.assertTrue(report["fill_calibrated"])
        self.assertAlmostEqual(report["fill_chars_per_token"], 6.0, places=1)
        self.assertEqual(post.call_count, 2)
        timed_prompt = post.call_args_list[1].args[2]["messages"][0]["content"]
        # Calibrated 6.0, not the old 3.4 estimator.
        self.assertGreater(len(timed_prompt), int(1_024 * 5.0))

    def test_run_disables_optional_thinking_and_keeps_a_nonexact_signal(self):
        response = {"message": {"content": "Answer: KV_CACHE_OK"}}
        with patch.object(bench.router, "gpu_memory", side_effect=[(100, []), (200, [])]), \
             patch.object(bench, "_post", return_value=response) as post:
            report = bench.run_once(
                "127.0.0.1:11434", "model", 1_024, chars_per_token=6.5)
        self.assertFalse(report["reply_exact"])
        self.assertTrue(report["reply_expected_token_seen"])
        self.assertIs(post.call_args.args[2]["think"], False)


if __name__ == "__main__":
    unittest.main()
