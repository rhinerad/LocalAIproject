#!/usr/bin/env python3
"""Static safety checks for the opt-in live Qwen2.5-VL diagnostic."""
from __future__ import annotations

import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class VerifyExactQwenScriptTests(unittest.TestCase):
    def test_live_check_refuses_render_ownership_and_releases_runtime(self):
        source = (HERE / "verify_qwen25_vl_caption.py").read_text(encoding="utf-8")
        self.assertIn("router.comfy_listening()", source)
        self.assertIn("caps.QWEN25_VL_MODEL", source)
        self.assertIn("caps.release_qwen25_vl_runtime()", source)
        self.assertIn("--report", source)
        self.assertNotIn("oll.chat", source)


if __name__ == "__main__":
    unittest.main()
