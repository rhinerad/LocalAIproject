#!/usr/bin/env python3
"""Isolated CPU WD14 tagger. No live ONNX download."""
from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

_SPEC = importlib.util.spec_from_file_location("gvd_qa_ref", ROOT / "gvd_qa.py")
gvd_qa = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["gvd_qa_ref"] = gvd_qa
_SPEC.loader.exec_module(gvd_qa)

from gvd_qa.local_client import LocalQaClient
from gvd_qa.wd14_cpu import (
    cpu_ort_settings,
    cpu_wd14_fn,
    ensure_model,
    model_urls,
    tag_image,
)


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (16, 12), (40, 80, 120)).save(buf, format="PNG")
    return buf.getvalue()


def _vocab(path: Path) -> None:
    rows = [
        ("tag_id", "name", "category", "count"),
        ("0", "rating:general", "9", "1"),
        ("1", "rating:sensitive", "9", "1"),
        ("2", "rating:questionable", "9", "1"),
        ("3", "rating:explicit", "9", "1"),
        ("4", "1girl", "0", "10"),
        ("5", "glasses", "0", "10"),
        ("6", "red_hair", "0", "10"),
        ("7", "some_character", "4", "3"),
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(rows)


class FakeSession:
    def get_inputs(self):
        class I:
            name = "input"
            shape = [1, 8, 8, 3]
        return [I()]

    def get_outputs(self):
        class O:
            name = "output"
        return [O()]

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def run(self, outputs, feeds):
        probs = np.zeros((1, 8), dtype=np.float32)
        probs[0, 5] = 0.91
        probs[0, 6] = 0.12
        probs[0, 7] = 0.99
        return [probs]


class Wd14CpuTests(unittest.TestCase):
    def test_urls_and_cpu_only(self):
        urls = model_urls()
        self.assertIn("SmilingWolf/wd-v1-4-moat-tagger-v2", urls["onnx"])
        self.assertTrue(urls["onnx"].endswith("model.onnx"))
        self.assertTrue(urls["csv"].endswith("selected_tags.csv"))
        self.assertEqual(cpu_ort_settings()["ortProviders"], ["CPUExecutionProvider"])
        with self.assertRaises(Exception):
            tag_image(_png(), providers=["CUDAExecutionProvider"], session=FakeSession(),
                      csv_path=Path(tempfile.mkdtemp()) / "x.csv")

    def test_fake_session_tags_and_local_client(self):
        tmp = Path(tempfile.mkdtemp())
        csv_path = tmp / "wd-v1-4-moat-tagger-v2.csv"
        _vocab(csv_path)
        png = _png()
        result = tag_image(png, session=FakeSession(), csv_path=csv_path)
        self.assertEqual(result["providers"], ["CPUExecutionProvider"])
        self.assertIn("glasses", result["tags"])
        self.assertIn("some character", result["tags"])
        self.assertNotIn("red hair", result["tags"])
        traits = gvd_qa.wd14_traits(
            {"outputs": {"30": {"tags": [result["tags"]]}}},
            {"glasses": ("glasses", "eyewear"), "red_hair": ("red hair", "redhead")},
        )
        self.assertEqual(traits["glasses"]["status"], "tag_supported")
        self.assertEqual(traits["red_hair"]["status"], "not_detected")
        digest = gvd_qa.sha256(png)
        qa = LocalQaClient(
            clip_score_fn=lambda b, t: 70.0,
            wd14_fn=cpu_wd14_fn(session=FakeSession(), csv_path=csv_path),
        )
        qa.upload(png, digest)
        history = qa.run(
            {"90": {"class_type": "GVDMetricReport", "inputs": {
                "attempt_id": "a", "image_sha256": digest, "profile_id": "m1",
                "clip_text_unit": "torchmetrics_clipscore_0_100"}}},
            "a",
            tmp / "fast.json",
        )
        self.assertEqual(history["outputs"]["30"]["tags"][0], result["tags"])

    def test_ensure_model_skips_when_present(self):
        tmp = Path(tempfile.mkdtemp())
        onnx = tmp / "wd-v1-4-moat-tagger-v2.onnx"
        csv_path = tmp / "wd-v1-4-moat-tagger-v2.csv"
        onnx.write_bytes(b"onnx")
        csv_path.write_text("x", encoding="utf-8")
        got_onnx, got_csv = ensure_model(tmp, download=False)
        self.assertEqual(got_onnx, onnx)
        self.assertEqual(got_csv, csv_path)
        missing = Path(tempfile.mkdtemp())
        with self.assertRaises(Exception) as ctx:
            ensure_model(missing, download=False)
        self.assertIn("missing", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
