#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import three_d_discovery


class ThreeDDiscoveryTests(unittest.TestCase):
    def test_inventory_detects_assets_but_never_claims_routing_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "models" / "checkpoints" / "TRELLIS-image-large").mkdir(parents=True)
            (root / "models" / "checkpoints" / "TRELLIS-image-large" / "model.safetensors").write_bytes(b"x")
            (root / "models" / "diffusion_models").mkdir(parents=True)
            (root / "models" / "diffusion_models" / "hunyuan3d-dit-v2.safetensors").write_bytes(b"x")
            (root / "models" / "checkpoints" / "TRELLIS-image-large" / ".cache").mkdir()
            (root / "models" / "checkpoints" / "TRELLIS-image-large" / ".cache" / "ignored.safetensors").write_bytes(b"x")
            report = three_d_discovery.inspect(root)
            self.assertTrue(report["models"]["trellis"])
            self.assertTrue(report["models"]["hunyuan3d"])
            self.assertNotIn(".cache", " ".join(item["path"] for item in report["models"]["trellis"]))
            self.assertFalse(report["routing_ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
