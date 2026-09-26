#!/usr/bin/env python3
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
from gvd_qa.assemble_mp4 import assemble_png_sequence
from gvd_qa.local_client import LocalQaClient, checklist_from_mapping
from gvd_qa.local_phases import HybridPhaseController
from gvd_qa.pipeline import bind_fast, bind_qwen, bind_reward, load_policy

_SPEC = importlib.util.spec_from_file_location("gvd_qa_ref", ROOT / "gvd_qa.py")
gvd_qa = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["gvd_qa_ref"] = gvd_qa
_SPEC.loader.exec_module(gvd_qa)


def _png(size=(512, 512)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (180, 160, 40)).save(buf, format="PNG")
    return buf.getvalue()


class FakeGen:
    def __init__(self, png: bytes):
        self.png = png
        self.ran = []

    def run(self, graph, attempt, journal):
        self.ran.append(("gen", graph["5"]["inputs"]["seed"]))
        Path(journal).write_text("{}", encoding="utf-8")
        return {"outputs": {"7": {"images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}}}

    def image_bytes(self, history, save_node):
        return self.png


class HybridGenerateTests(unittest.TestCase):
    def test_generate_then_local_qa_accepts(self):
        png = _png()
        qa = LocalQaClient(
            clip_score_fn=lambda b, t: 20.0,
            checklist_fn=checklist_from_mapping({"yellow_surfaces": "pass", "corridor": "pass"}),
            reward_fn=lambda b, t: 0.2,
        )
        phases = HybridPhaseController(qa, start_vlm=False, comfy=FakeGen(png))
        policy = load_policy(HERE / "gvd_qa" / "profiles" / "observed_5080_c017_end_reroll.json")
        req = (HERE / "gvd_qa" / "profiles" / "br24_c017_end_rubric.json").read_text(encoding="utf-8")
        graph = json.loads((ROOT / "local_agent" / "gvd_tool_router" / "fixtures" / "known_good_still.api.json").read_text(encoding="utf-8"))
        tmp = Path(tempfile.mkdtemp()) / "job"
        dest = gvd_qa.generate_until_accepted(
            generation_graph=graph,
            seed_bindings=(("5", "seed"),),
            generation_save_node="7",
            base_seed=1,
            expected_size=(512, 512),
            policy=policy,
            requirements_json=req,
            make_fast_graph=lambda n, a, d: bind_fast(n, a, d, policy, None, local=True),
            make_qwen_graph=lambda n, a, d: bind_qwen(n, a, d, policy, req, local=True),
            make_reward_graph=lambda n, a, d: bind_reward(n, a, d, policy, "yellow hallway", local=True),
            phases=phases,
            job_dir=tmp,
        )
        self.assertEqual(dest.name, "accepted.json")
        self.assertEqual(phases.comfy.ran[0][0], "gen")

    def test_assemble_mp4(self):
        tmp = Path(tempfile.mkdtemp())
        for i in range(1, 4):
            Image.new("RGB", (16, 16), (i * 40, 80, 20)).save(tmp / f"i2v_from_receipt_{i:05d}_.png")
        dest = tmp / "out.mp4"
        assemble_png_sequence(tmp, "i2v_from_receipt_%05d_.png", dest, fps=6)
        self.assertGreater(dest.stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
