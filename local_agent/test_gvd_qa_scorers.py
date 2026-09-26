#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from PIL import Image
from gvd_qa.scorers import _center_crop_224, _pil
from gvd_qa.stage_adapters import stage_comfy_gvd_qa


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (40, 20), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


class ScorerHelperTests(unittest.TestCase):
    def test_center_crop_224(self):
        crop = _center_crop_224(_pil(_png()))
        self.assertEqual(crop.size, (224, 224))
        self.assertEqual(crop.mode, "RGB")

    def test_clip_image_self_similarity(self):
        from gvd_qa.scorers import clip_image_score
        png = _png()
        score = clip_image_score(png, png)
        self.assertGreater(score, 0.99)

    def test_stage_copies_adapters_into_package(self):
        tmp = Path(tempfile.mkdtemp())
        report = stage_comfy_gvd_qa(quarantine_dir=tmp, object_info={})
        staged = Path(report["staged"])
        self.assertTrue((staged / "comfy_adapters.py").is_file())
        self.assertTrue((staged / "transformers_compat.py").is_file())
        self.assertTrue((staged / "__init__.py").is_file())
        self.assertFalse(report["installed"])


if __name__ == "__main__":
    unittest.main()
