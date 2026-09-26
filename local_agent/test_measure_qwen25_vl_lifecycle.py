#!/usr/bin/env python3
"""Static safeguards for the opt-in Qwen2.5-VL lifecycle benchmark."""
from __future__ import annotations

import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class LifecycleBenchmarkSafetyTests(unittest.TestCase):
    def test_requires_explicit_execution_and_releases_exact_runtime(self):
        source = (HERE / "measure_qwen25_vl_lifecycle.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--execute", action="store_true"', source)
        self.assertIn("router.comfy_listening()", source)
        self.assertIn("caps.QWEN25_VL_MODEL", source)
        self.assertIn("caps.release_qwen25_vl_runtime()", source)
        self.assertIn("analysis_sha256", source)
        self.assertNotIn("oll.chat", source)


if __name__ == "__main__":
    unittest.main()
