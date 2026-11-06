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
from gvd_qa.evidence import connect_evidence, insert_evidence, read_evidence
from gvd_qa.local_client import LocalQaClient, checklist_from_mapping
from gvd_qa.pipeline import run_persisted_still_qa

_SPEC = importlib.util.spec_from_file_location("gvd_qa_ref", ROOT / "gvd_qa.py")
gvd_qa = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["gvd_qa_ref"] = gvd_qa
_SPEC.loader.exec_module(gvd_qa)


def _png(size=(16, 8)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (20, 40, 60)).save(buf, format="PNG")
    return buf.getvalue()


class PersistPhases:
    def __init__(self, qa):
        self.qa = qa
        self.idled = False
        self.seen = []

    def enter(self, phase):
        self.seen.append(phase)
        if phase == "generate":
            raise AssertionError("persisted candidate must not generate")
        return self.qa

    def idle(self):
        self.idled = True


class PersistedStillTests(unittest.TestCase):
    def test_qwen_fail_writes_blocked_not_accepted(self):
        png = _png()
        qa = LocalQaClient(
            clip_score_fn=lambda b, t: 12.0,
            checklist_fn=checklist_from_mapping({"yellow_walls": "fail", "person_visible": "pass"}),
            reward_fn=lambda b, t: 9.9,
            wd14_fn=lambda b: "camera, 1boy",
        )
        tmp = Path(tempfile.mkdtemp()) / "job"
        db = connect_evidence(tmp.parent / "qa.sqlite")

        def record(**kwargs):
            insert_evidence(db, job_id="job", verdict=kwargs["verdict"],
                            rubric_sha256=kwargs["rubric_sha256"])

        phases = PersistPhases(qa)
        dest = run_persisted_still_qa(
            image=png,
            policy_path=HERE / "gvd_qa" / "profiles" / "observed_5080_finite_clip.json",
            requirements_path=HERE / "gvd_qa" / "profiles" / "br24_c017_rubric.json",
            phases=phases,
            job_dir=tmp,
            expected_size=(16, 8),
            wd14_aliases={"camera": ("camera",), "boy": ("1boy", "boy")},
            record_evidence=record,
            audit_caption="a person holding a camera",
            local=True,
        )
        self.assertEqual(dest.name, "blocked.json")
        self.assertFalse((tmp / "accepted.json").exists())
        data = json.loads(dest.read_text(encoding="utf-8"))
        self.assertFalse(data["accepted"])
        self.assertIn("qwen:yellow_walls", data["reasons"])
        self.assertEqual(data["scores"]["clip_text"], 12.0)
        self.assertNotIn("image_reward", data["scores"])
        self.assertEqual(data["wd14_traits"]["camera"]["status"], "tag_supported")
        self.assertTrue(phases.idled)
        self.assertEqual(phases.seen, ["fast_qa", "qwen_qa"])
        rows = read_evidence(db, data["attempt_id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "rejected")
        with self.assertRaises(Exception):
            gvd_qa.accepted_i2v_image(dest, data["policy_id"], data["requirements_sha256"])

    def test_all_pass_writes_accepted(self):
        png = _png()
        qa = LocalQaClient(
            clip_score_fn=lambda b, t: 12.0,
            checklist_fn=checklist_from_mapping({"yellow_walls": "pass", "person_visible": "pass"}),
            reward_fn=lambda b, t: 0.4,
            wd14_fn=lambda b: "camera",
        )
        tmp = Path(tempfile.mkdtemp()) / "ok"
        dest = run_persisted_still_qa(
            image=png,
            policy_path=HERE / "gvd_qa" / "profiles" / "observed_5080_finite_clip.json",
            requirements_path=HERE / "gvd_qa" / "profiles" / "br24_c017_rubric.json",
            phases=PersistPhases(qa),
            job_dir=tmp,
            expected_size=(16, 8),
            audit_caption="x",
            local=True,
        )
        self.assertEqual(dest.name, "accepted.json")
        data = json.loads(dest.read_text(encoding="utf-8"))
        self.assertTrue(data["accepted"])
        self.assertEqual(data["scores"]["image_reward"], 0.4)
        path = gvd_qa.accepted_i2v_image(dest, data["policy_id"], data["requirements_sha256"])
        self.assertEqual(path.read_bytes(), png)

    def test_c017_end_shot_contract_accepts(self):
        png = _png()
        qa = LocalQaClient(
            clip_score_fn=lambda b, t: 18.0,
            checklist_fn=checklist_from_mapping({"yellow_surfaces": "pass", "corridor": "pass"}),
            reward_fn=lambda b, t: -0.5,
        )
        tmp = Path(tempfile.mkdtemp()) / "end"
        dest = run_persisted_still_qa(
            image=png,
            policy_path=HERE / "gvd_qa" / "profiles" / "observed_5080_c017_end.json",
            requirements_path=HERE / "gvd_qa" / "profiles" / "br24_c017_end_rubric.json",
            phases=PersistPhases(qa),
            job_dir=tmp,
            audit_caption="yellow hallway",
            local=True,
        )
        self.assertEqual(dest.name, "accepted.json")
        data = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(data["scores"]["image_reward"], -0.5)
        gvd_qa.accepted_i2v_image(dest, data["policy_id"], data["requirements_sha256"])


class GenerateVideoFlagTests(unittest.TestCase):
    def test_qa_candidate_flags(self):
        spec = importlib.util.spec_from_file_location(
            "generate_video_mod", ROOT / "generate_video.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        args = mod.build_argparser().parse_args([
            "--intent", "backrooms hallway",
            "--category", "backrooms",
            "--qa-candidate", "still.png",
            "--qa-local",
            "--qa-job-dir", "jobs/x",
            "--qa-policy-json", "p.json",
            "--qa-requirements-json", "r.json",
            "--qa-audit-caption", "yellow hallway",
        ])
        self.assertTrue(args.qa_local)
        self.assertEqual(args.qa_candidate, "still.png")
        self.assertEqual(args.qa_audit_caption, "yellow hallway")


if __name__ == "__main__":
    unittest.main()
