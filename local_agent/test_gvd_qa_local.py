#!/usr/bin/env python3
"""LocalQaClient still-QA without Comfy/YRIKKA."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from PIL import Image
from gvd_qa.local_client import LocalQaClient, checklist_from_mapping
from gvd_qa.pipeline import load_policy, run_still_qa

_SPEC = importlib.util.spec_from_file_location("gvd_qa_ref", ROOT / "gvd_qa.py")
gvd_qa = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["gvd_qa_ref"] = gvd_qa
_SPEC.loader.exec_module(gvd_qa)


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buf, format="PNG")
    return buf.getvalue()


PNG = _png()
DIGEST = gvd_qa.sha256(PNG)


class GenClient:
    def run(self, graph, attempt, journal):
        gvd_qa.atomic_json(journal, {"state": "completed"})
        return {"outputs": {"9": {"images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}}}

    def image_bytes(self, history, node):
        return PNG

    def upload(self, image, digest):
        raise AssertionError("generation phase does not upload")


class HybridPhases:
    def __init__(self, qa: LocalQaClient):
        self.qa = qa
        self.gen = GenClient()
        self.idled = False

    def enter(self, phase):
        return self.gen if phase == "generate" else self.qa

    def idle(self):
        self.idled = True


class LocalClientTests(unittest.TestCase):
    def test_local_accepts(self):
        qa = LocalQaClient(
            clip_score_fn=lambda b, t: 80.0,
            checklist_fn=checklist_from_mapping({"cast_count": "pass"}),
            reward_fn=lambda b, t: 0.3,
            wd14_fn=lambda b: "glasses",
        )
        tmp = Path(tempfile.mkdtemp()) / "job"
        receipt = run_still_qa(
            generation_graph={
                "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
                "8": {"class_type": "VAEDecode", "inputs": {}},
                "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "x"}},
            },
            seed_bindings=(("3", "seed"),),
            generation_save_node="9",
            base_seed=1,
            expected_size=(8, 8),
            policy_path=HERE / "gvd_qa" / "profiles" / "local_unmeasured.json",
            requirements_path=HERE / "gvd_qa" / "profiles" / "example_rubric.json",
            phases=HybridPhases(qa),
            job_dir=tmp,
            local=True,
        )
        data = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertTrue(data["accepted"])
        path = gvd_qa.accepted_i2v_image(
            receipt, "local_unmeasured_v1",
            gvd_qa.sha256((HERE / "gvd_qa" / "profiles" / "example_rubric.json").read_bytes()),
        )
        self.assertEqual(path.read_bytes(), PNG)

    def test_missing_clip_scorer_is_infra(self):
        qa = LocalQaClient(checklist_fn=checklist_from_mapping({"cast_count": "pass"}))
        qa.upload(PNG, DIGEST)
        graph = {
            "90": {"class_type": "GVDMetricReport", "inputs": {
                "attempt_id": "a", "image_sha256": DIGEST, "profile_id": "unmeasured_clip",
                "clip_text_unit": "torchmetrics_clipscore_0_100"}},
        }
        with self.assertRaises(Exception) as ctx:
            qa.run(graph, "a", Path(tempfile.mkdtemp()) / "fast.json")
        self.assertIn("adapter_required", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
