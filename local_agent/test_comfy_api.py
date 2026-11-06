#!/usr/bin/env python3
"""comfy_api graph isolation and history parsing. No live ComfyUI."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import comfy_api


class ComfyAPITests(unittest.TestCase):
    def test_save_prefix_is_isolated_subdir(self):
        self.assertEqual(comfy_api.save_prefix("C016_last"), "dspy_opt/C016_last")
        self.assertTrue(comfy_api.save_prefix("../etc/passwd").startswith("dspy_opt/"))
        self.assertNotIn("..", comfy_api.save_prefix("../etc/passwd"))

    def test_graph_is_4_3_and_isolated(self):
        graph = comfy_api.build_txt2img_graph(
            prompt="sickly yellow wallpaper, damp carpet",
            filename_prefix="C016_last",
        )
        self.assertEqual(graph["7"]["class_type"], "SaveImage")
        self.assertEqual(graph["7"]["inputs"]["filename_prefix"], "dspy_opt/C016_last")
        self.assertNotEqual(graph["7"]["inputs"]["filename_prefix"], "ComfyUI")
        self.assertEqual(graph["4"]["inputs"]["width"], 1024)
        self.assertEqual(graph["4"]["inputs"]["height"], 768)
        self.assertNotIn("8", graph)

    def test_lora_node_only_when_named(self):
        graph = comfy_api.build_txt2img_graph(
            prompt="backrooms",
            filename_prefix="x",
            lora_name="some_backrooms.safetensors",
        )
        self.assertEqual(graph["8"]["class_type"], "LoraLoader")
        self.assertEqual(graph["8"]["inputs"]["lora_name"], "some_backrooms.safetensors")
        self.assertEqual(graph["2"]["inputs"]["clip"], ["8", 1])

    def test_rejects_non_4_3_small_latent(self):
        with self.assertRaises(comfy_api.ComfyAPIError):
            comfy_api.build_txt2img_graph(prompt="x", width=64, height=64)

    def test_enqueue_posts_graph(self):
        captured = {}

        class _Resp:
            def read(self):
                return json.dumps({"prompt_id": "abc-12345", "number": 1}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            return _Resp()

        graph = comfy_api.build_txt2img_graph(prompt="a lamp", filename_prefix="unit")
        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            queued = comfy_api.enqueue_graph(graph)
        self.assertEqual(queued["prompt_id"], "abc-12345")
        self.assertTrue(captured["url"].endswith("/prompt"))
        self.assertEqual(
            captured["body"]["prompt"]["7"]["inputs"]["filename_prefix"],
            "dspy_opt/unit",
        )
        self.assertEqual(captured["body"]["client_id"], "local_agent-dspy-opt")

    def test_parse_history_complete_and_error(self):
        prompt_id = "abc-12345"
        complete = {
            prompt_id: {
                "status": {"status_str": "success", "completed": True},
                "outputs": {
                    "7": {"images": [{
                        "filename": "dspy_opt_unit_00001.png",
                        "subfolder": "dspy_opt",
                        "type": "output",
                    }]},
                },
            }
        }
        parsed = comfy_api.parse_history(complete, prompt_id)
        self.assertEqual(parsed["state"], "complete")
        self.assertEqual(parsed["outputs"][0]["filename"], "dspy_opt_unit_00001.png")
        failed = {
            prompt_id: {
                "status": {"status_str": "error", "completed": True},
                "outputs": {},
            }
        }
        self.assertEqual(comfy_api.parse_history(failed, prompt_id)["state"], "error")
        self.assertEqual(comfy_api.parse_history({}, prompt_id)["state"], "pending")

    def test_dropped_history_raises_timeout_error_in_60s_budget(self):
        clock = {"t": 0.0}

        def monotonic():
            return clock["t"]

        def sleep(seconds):
            clock["t"] += float(seconds)

        with patch.object(comfy_api.time, "monotonic", side_effect=monotonic), \
             patch.object(comfy_api.time, "sleep", side_effect=sleep), \
             patch.object(comfy_api, "_fetch_history", return_value={}):
            with self.assertRaises(TimeoutError) as ctx:
                comfy_api.wait_for_image("abc-12345", timeout_s=60)
        self.assertIn("60", str(ctx.exception))
        self.assertGreaterEqual(clock["t"], 60.0)
        self.assertEqual(comfy_api.wait_for_image.__kwdefaults__["timeout_s"], 60.0)
        self.assertEqual(comfy_api.RENDER_TIMEOUT_S, 60.0)
        self.assertEqual(comfy_api.DEFAULT_CFG, 7.0)
        self.assertEqual(comfy_api.DEFAULT_STEPS, 30)
        self.assertEqual(comfy_api.DEFAULT_SAMPLER, "euler")

    def test_graph_locks_euler_30_cfg7(self):
        graph = comfy_api.build_txt2img_graph(prompt="x", filename_prefix="unit")
        ks = graph["5"]["inputs"]
        self.assertEqual(ks["cfg"], 7.0)
        self.assertEqual(ks["steps"], 30)
        self.assertEqual(ks["sampler_name"], "euler")

    def test_resolve_output_prefers_on_disk_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "output" / "dspy_opt"
            root.mkdir(parents=True)
            png = root / "still.png"
            png.write_bytes(b"png")
            with patch.object(comfy_api, "comfy_output_root", return_value=Path(tmp) / "output"):
                got = comfy_api.resolve_output_path({
                    "filename": "still.png",
                    "subfolder": "dspy_opt",
                })
            self.assertEqual(got, png)


if __name__ == "__main__":
    unittest.main()
