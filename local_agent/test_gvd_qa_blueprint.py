#!/usr/bin/env python3
"""Blueprint section 10: seven mocked tests. Synthetic scores; no GPU."""
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

_SPEC = importlib.util.spec_from_file_location("gvd_qa_ref", ROOT / "gvd_qa.py")
gvd_qa = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["gvd_qa_ref"] = gvd_qa
_SPEC.loader.exec_module(gvd_qa)

from PIL import Image


def _png(size=(8, 8)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (12, 34, 56)).save(buf, format="PNG")
    return buf.getvalue()


def _policy(**kwargs) -> gvd_qa.Policy:
    values = dict(
        policy_id="unit",
        metrics_profile="m1",
        qwen_profile="q1",
        reward_profile="r1",
        clip_text_min=50.0,
        required_ids=("cast_count",),
        max_attempts=4,
    )
    values.update(kwargs)
    return gvd_qa.Policy(**values)


def _metrics(attempt, digest, clip, unit="torchmetrics_clipscore_0_100", dino=None, clip_image=None):
    report = {
        "schema_version": 1,
        "attempt_id": attempt,
        "image_sha256": digest,
        "profile_id": "m1",
        "clip_text": clip,
        "clip_text_unit": unit,
        "dino": dino,
        "clip_image": clip_image,
    }
    return {"outputs": {"90": {"gvd_metrics": [report]}, "30": {"tags": ["glasses, red hair"]}}}


def _qwen(attempt, digest, rubric_sha, verdicts, qwen_pass=None):
    checks = [{"id": "cast_count", "verdict": verdicts[0], "evidence": "x"}]
    computed = all(c["verdict"] == "pass" for c in checks)
    if qwen_pass is None:
        qwen_pass = computed
    return {"outputs": {"91": {"gvd_qa": [{
        "schema_version": 1,
        "attempt_id": attempt,
        "image_sha256": digest,
        "profile_id": "q1",
        "requirements_sha256": rubric_sha,
        "checks": checks,
        "qwen_pass": qwen_pass,
    }]}}}


def _reward(attempt, digest, value):
    return {"outputs": {"92": {"gvd_reward": [{
        "schema_version": 1,
        "attempt_id": attempt,
        "image_sha256": digest,
        "profile_id": "r1",
        "image_reward": value,
        "unit": "imagereward_raw",
    }]}}}


PNG = _png()
DIGEST = gvd_qa.sha256(PNG)
REQ = json.dumps([{"id": "cast_count", "criterion": "Exactly two adults are visibly present."}])
RUBRIC = gvd_qa.sha256(REQ.encode())


class FakeClient:
    def __init__(self, png: bytes, script):
        self.png = png
        self.script = list(script)
        self.calls = []

    def run(self, graph, attempt, journal: Path):
        self.calls.append((graph, attempt, journal.name))
        if journal.exists():
            raise gvd_qa.QAError("Existing submission journal: reconcile before retry")
        gvd_qa.atomic_json(journal, {"state": "completed", "attempt_id": attempt})
        kind = journal.name
        if kind.startswith("generation"):
            return {"outputs": {"9": {"images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}}}
        row = self.script.pop(0)
        return row(attempt)

    def image_bytes(self, history, save_node):
        return self.png

    def upload(self, image, digest):
        return digest + ".png"


class FakePhases:
    def __init__(self, client):
        self.client = client
        self.entered = []
        self.idled = False

    def enter(self, phase):
        if not phase:
            raise gvd_qa.QAError("empty phase")
        self.entered.append(phase)
        return self.client

    def idle(self):
        self.idled = True


def _run(tmp: Path, script, policy=None, png=None):
    png = png or PNG
    client = FakeClient(png, script)
    phases = FakePhases(client)
    graph = {
        "8": {"class_type": "VAEDecode", "inputs": {}},
        "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "x"}},
    }
    receipt = gvd_qa.generate_until_accepted(
        generation_graph=graph,
        seed_bindings=(("3", "seed"),),
        generation_save_node="9",
        base_seed=1,
        expected_size=(8, 8),
        policy=policy or _policy(),
        requirements_json=REQ,
        make_fast_graph=lambda n, a, d: {"1": {"inputs": {"image": n}}},
        make_qwen_graph=lambda n, a, d: {"1": {"inputs": {"image": n}}},
        make_reward_graph=lambda n, a, d: {"1": {"inputs": {"image": n}}},
        phases=phases,
        job_dir=tmp,
        wd14_aliases={"glasses": ("glasses", "eyewear")},
    )
    return receipt, phases, client


class BlueprintGateTests(unittest.TestCase):
    def test_low_clip_rerolls_then_accepts(self):
        tmp = Path(tempfile.mkdtemp()) / "job"
        script = [
            lambda attempt: _metrics(attempt, DIGEST, 10.0),
            lambda attempt: _metrics(attempt, DIGEST, 80.0),
            lambda attempt: _qwen(attempt, DIGEST, RUBRIC, ["pass"]),
            lambda attempt: _reward(attempt, DIGEST, 0.5),
        ]
        receipt, phases, _ = _run(tmp, script)
        self.assertTrue(receipt.is_file())
        data = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertTrue(data["accepted"])
        self.assertEqual(data["reasons"], [])
        self.assertIn("generate", phases.entered)
        self.assertTrue(phases.idled)
        path = gvd_qa.accepted_i2v_image(receipt, "unit", RUBRIC)
        self.assertEqual(path.read_bytes(), PNG)

    def test_qwen_rejection_rerolls(self):
        tmp = Path(tempfile.mkdtemp()) / "job"
        script = [
            lambda attempt: _metrics(attempt, DIGEST, 80.0),
            lambda attempt: _qwen(attempt, DIGEST, RUBRIC, ["fail"]),
            lambda attempt: _metrics(attempt, DIGEST, 80.0),
            lambda attempt: _qwen(attempt, DIGEST, RUBRIC, ["pass"]),
            lambda attempt: _reward(attempt, DIGEST, 0.2),
        ]
        receipt, _, _ = _run(tmp, script)
        data = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertTrue(data["accepted"])

    def test_uncertainty_blocks_without_reroll(self):
        tmp = Path(tempfile.mkdtemp()) / "job"
        script = [
            lambda attempt: _metrics(attempt, DIGEST, 80.0),
            lambda attempt: _qwen(attempt, DIGEST, RUBRIC, ["unknown"]),
        ]
        with self.assertRaises(gvd_qa.QAError) as ctx:
            _run(tmp, script)
        self.assertIn("Uncertain", str(ctx.exception))
        self.assertFalse((tmp / "accepted.json").exists())

    def test_attempt_budget_exhaustion(self):
        tmp = Path(tempfile.mkdtemp()) / "job"
        script = [
            lambda attempt: _metrics(attempt, DIGEST, 1.0),
            lambda attempt: _metrics(attempt, DIGEST, 2.0),
        ]
        with self.assertRaises(gvd_qa.Rejected):
            _run(tmp, script, policy=_policy(max_attempts=2))
        blocked = json.loads((tmp / "blocked.json").read_text(encoding="utf-8"))
        self.assertEqual(blocked["reason"], "quality_budget_exhausted")

    def test_malformed_nonfinite_score(self):
        policy = _policy()
        history = _metrics("a", DIGEST, "nan")
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.evaluate_fast(history, "a", DIGEST, policy)
        history = _metrics("a", DIGEST, "inf")
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.evaluate_fast(history, "a", DIGEST, policy)
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.finite_number(True)

    def test_stale_and_boolean_invalid_reports(self):
        policy = _policy()
        history = _metrics("other", DIGEST, 80.0)
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.evaluate_fast(history, "a", DIGEST, policy)
        bad = _qwen("a", DIGEST, RUBRIC, ["pass"], qwen_pass=False)
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.evaluate_qwen(bad, "a", DIGEST, policy, RUBRIC)

    def test_changed_image_rejection(self):
        tmp = Path(tempfile.mkdtemp())
        image = tmp / "candidate.png"
        image.write_bytes(PNG)
        receipt = tmp / "accepted.json"
        gvd_qa.atomic_json(receipt, {
            "accepted": True,
            "reasons": [],
            "policy_id": "unit",
            "requirements_sha256": RUBRIC,
            "image_sha256": DIGEST,
            "image_path": str(image),
        })
        image.write_bytes(_png((16, 16)))
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.accepted_i2v_image(receipt, "unit", RUBRIC)


class AdapterSmokeTests(unittest.TestCase):
    def test_metric_report_ui(self):
        spec = importlib.util.spec_from_file_location(
            "gvd_qa_adapters", HERE / "gvd_qa" / "comfy_adapters.py")
        adapters = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(adapters)
        out = adapters.GVDMetricReport().report(
            "12.5", "att", "abc", "m1", "torchmetrics_clipscore_0_100")
        self.assertEqual(out["ui"]["gvd_metrics"][0]["clip_text"], 12.5)
        with self.assertRaises(ValueError):
            adapters.GVDMetricReport().report("nan", "att", "abc", "m1", "raw_cosine")


if __name__ == "__main__":
    unittest.main()
