from __future__ import annotations

import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


class Qwen25SetupScriptTests(unittest.TestCase):
    def test_projector_minimum_matches_the_runtime_capability_guard(self):
        script = (HERE / "setup_qwen25_vl_caption.ps1").read_text(encoding="utf-8")
        import capabilities
        self.assertIn(f"$ProjectorBytes = {capabilities.QWEN25_VL_MMPROJ_BYTES}", script)
        self.assertIn(f"$ModelBytes = {capabilities.QWEN25_VL_WEIGHTS_BYTES}", script)
        self.assertIn(capabilities.QWEN25_VL_WEIGHTS_SHA256, script)
        self.assertIn(capabilities.QWEN25_VL_MMPROJ_SHA256, script)
        self.assertIn(f"$ProjectorPath $ProjectorBytes", script)


if __name__ == "__main__":
    unittest.main()
