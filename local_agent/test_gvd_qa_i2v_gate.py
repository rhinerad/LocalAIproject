#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from PIL import Image
from gvd_qa.i2v_gate import apply_qa_gate


def _png() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


class I2VGateTests(unittest.TestCase):
    def test_missing_receipt_blocks(self):
        args = SimpleNamespace(
            allow_ungated_i2v=False,
            require_qa_receipt=True,
            qa_receipt=None,
            qa_candidate=None,
            qa_job_dir=None,
            qa_policy_json=None,
            qa_requirements_json=None,
            qa_generation_graph=None,
            qa_policy_id=None,
        )
        code, still = apply_qa_gate(args, root=ROOT, local_agent=HERE)
        self.assertEqual(code, 4)
        self.assertIsNone(still)

    def test_ungated_skips(self):
        args = SimpleNamespace(allow_ungated_i2v=True, require_qa_receipt=True)
        code, still = apply_qa_gate(args, root=ROOT, local_agent=HERE)
        self.assertIsNone(code)
        self.assertIsNone(still)

    def test_accepted_receipt_binds_still(self):
        import hashlib
        tmp = Path(tempfile.mkdtemp())
        png = _png()
        image_path = tmp / "candidate.png"
        image_path.write_bytes(png)
        rubric = tmp / "rubric.json"
        rubric.write_text('[{"id":"corridor","criterion":"hallway"}]', encoding="utf-8")
        digest = hashlib.sha256(png).hexdigest()
        rubric_sha = hashlib.sha256(rubric.read_bytes()).hexdigest()
        receipt = tmp / "accepted.json"
        receipt.write_text(json.dumps({
            "accepted": True,
            "reasons": [],
            "policy_id": "observed_5080_c017_end_v1",
            "requirements_sha256": rubric_sha,
            "image_sha256": digest,
            "image_path": str(image_path),
        }), encoding="utf-8")
        args = SimpleNamespace(
            allow_ungated_i2v=False,
            require_qa_receipt=True,
            qa_receipt=str(receipt),
            qa_candidate=None,
            qa_job_dir=None,
            qa_policy_json=None,
            qa_requirements_json=str(rubric),
            qa_generation_graph=None,
            qa_policy_id="observed_5080_c017_end_v1",
        )
        code, still = apply_qa_gate(args, root=ROOT, local_agent=HERE)
        self.assertIsNone(code)
        self.assertEqual(still.resolve(), image_path.resolve())

    def test_blocked_receipt_refuses(self):
        tmp = Path(tempfile.mkdtemp())
        blocked = tmp / "blocked.json"
        blocked.write_text(json.dumps({
            "accepted": False, "reasons": ["qwen:yellow_walls"],
            "policy_id": "x", "requirements_sha256": "0" * 64,
            "image_sha256": "0" * 64, "image_path": str(tmp / "nope.png"),
        }), encoding="utf-8")
        args = SimpleNamespace(
            allow_ungated_i2v=False,
            require_qa_receipt=True,
            qa_receipt=str(blocked),
            qa_candidate=None,
            qa_job_dir=None,
            qa_policy_json=None,
            qa_requirements_json=str(tmp / "missing.json"),
            qa_generation_graph=None,
            qa_policy_id="x",
        )
        (tmp / "missing.json").write_text("[]", encoding="utf-8")
        code, still = apply_qa_gate(args, root=ROOT, local_agent=HERE)
        self.assertEqual(code, 4)
        self.assertIsNone(still)


class WanReceiptGraphTests(unittest.TestCase):
    def test_bind_start_image(self):
        from gvd_qa.smoke_i2v_from_receipt import bind_start_image
        graph = json.loads((ROOT / "local_agent" / "gvd_tool_router" / "fixtures" / "wan_i2v_smoke.api.json").read_text(encoding="utf-8"))
        bound = bind_start_image(graph, "gvd_qa_c017_end_accepted.png", prefix="gvd_qa/i2v_gen_accepted")
        self.assertEqual(bound["5"]["inputs"]["image"], "gvd_qa_c017_end_accepted.png")
        self.assertEqual(bound["9"]["inputs"]["filename_prefix"], "gvd_qa/i2v_gen_accepted")
        self.assertEqual(graph["5"]["inputs"]["image"], "gvd_identity_ref.png")


class BatchQaLoopFlags(unittest.TestCase):
    def test_parser_accepts_receipt_and_candidate(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "master_batch_runner_mod", ROOT / "master_batch_runner.py")
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        args = mod.build_argparser().parse_args([
            "--task-dir", str(Path(tempfile.mkdtemp())),
            "--qa-loop",
            "--qa-receipt", "accepted.json",
            "--qa-candidate", "still.png",
            "--qa-local",
            "--qa-policy-json", "p.json",
            "--qa-requirements-json", "r.json",
        ])
        self.assertTrue(args.qa_loop)
        self.assertEqual(str(args.qa_receipt), "accepted.json")
        self.assertEqual(str(args.qa_candidate), "still.png")
        self.assertTrue(args.qa_local)


if __name__ == "__main__":
    unittest.main()
