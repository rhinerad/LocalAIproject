#!/usr/bin/env python3
"""mcp_test_output graph isolation. No live ComfyUI."""
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

import mcp_test_output
import tools


class McpTestOutputTests(unittest.TestCase):
    def test_save_prefix_is_subdir(self):
        self.assertEqual(mcp_test_output.save_prefix("vram_phase_probe_20260904"),
                         "mcp_test/vram_phase_probe_20260904")
        self.assertTrue(mcp_test_output.save_prefix("../etc/passwd").startswith("mcp_test/"))
        self.assertNotIn("..", mcp_test_output.save_prefix("../etc/passwd"))

    def test_graph_saveimage_uses_mcp_test_prefix(self):
        graph = mcp_test_output.build_txt2img_graph(
            prompt="a lamp",
            checkpoint="v1-5-pruned-emaonly-fp16.safetensors",
            filename_prefix="unit_test_probe",
        )
        self.assertEqual(graph["7"]["class_type"], "SaveImage")
        self.assertEqual(graph["7"]["inputs"]["filename_prefix"], "mcp_test/unit_test_probe")
        self.assertNotEqual(graph["7"]["inputs"]["filename_prefix"], "ComfyUI")

    def test_enqueue_posts_graph_and_audits(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        audit = Path(tmp.name) / "audit.jsonl"
        captured = {}

        class _Resp:
            def read(self):
                return json.dumps({"prompt_id": "abc-123", "number": 1}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            return _Resp()

        with patch.object(tools, "_COMFY_AUDIT_PATH", audit), \
             patch("urllib.request.urlopen", side_effect=fake_urlopen):
            queued = mcp_test_output.enqueue_txt2img(
                prompt="a lamp",
                checkpoint="v1-5-pruned-emaonly-fp16.safetensors",
                filename_prefix="unit_test_probe",
            )
        self.assertEqual(queued["prompt_id"], "abc-123")
        self.assertEqual(queued["filename_prefix"], "mcp_test/unit_test_probe")
        self.assertTrue(captured["url"].endswith("/prompt"))
        self.assertEqual(
            captured["body"]["prompt"]["7"]["inputs"]["filename_prefix"],
            "mcp_test/unit_test_probe",
        )
        record = json.loads(audit.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(record["local_tool"], "mcp_test_enqueue")
        self.assertEqual(record["prompt_id"], "abc-123")
        self.assertEqual(record["output_prefix"], "mcp_test/unit_test_probe")
        self.assertEqual(record["risk"], "generate")


if __name__ == "__main__":
    unittest.main()
