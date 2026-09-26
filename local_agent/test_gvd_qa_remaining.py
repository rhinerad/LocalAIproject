#!/usr/bin/env python3
"""Remaining blueprint items: resume, best-of-K, ablation, faults, staging."""
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

_SPEC = importlib.util.spec_from_file_location("gvd_qa_ref", ROOT / "gvd_qa.py")
gvd_qa = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["gvd_qa_ref"] = gvd_qa
_SPEC.loader.exec_module(gvd_qa)

from PIL import Image
from gvd_qa.evidence import connect_evidence, insert_evidence, insert_experiment, read_evidence
from gvd_qa.stage_adapters import stage_comfy_gvd_qa
from gvd_qa.validate import qa_activation_report
from gvd_qa.wd14_cpu import cpu_ort_settings, write_qa_worker_wd14_settings, assert_cpu_providers


def _png(size=(8, 8)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (12, 34, 56)).save(buf, format="PNG")
    return buf.getvalue()


PNG = _png()
DIGEST = gvd_qa.sha256(PNG)
REQ = json.dumps([{"id": "cast_count", "criterion": "Exactly two adults are visibly present."}])
RUBRIC = gvd_qa.sha256(REQ.encode())


def _policy(**kwargs):
    values = dict(
        policy_id="unit", metrics_profile="m1", qwen_profile="q1",
        reward_profile="r1", clip_text_min=50.0, required_ids=("cast_count",),
        max_attempts=4,
    )
    values.update(kwargs)
    return gvd_qa.Policy(**values)


def _metrics(attempt, digest, clip):
    return {"outputs": {"90": {"gvd_metrics": [{
        "schema_version": 1, "attempt_id": attempt, "image_sha256": digest,
        "profile_id": "m1", "clip_text": clip,
        "clip_text_unit": "torchmetrics_clipscore_0_100",
    }]}, "30": {"tags": ["glasses"]}}}


def _qwen(attempt, digest, verdict="pass"):
    checks = [{"id": "cast_count", "verdict": verdict, "evidence": "x"}]
    return {"outputs": {"91": {"gvd_qa": [{
        "schema_version": 1, "attempt_id": attempt, "image_sha256": digest,
        "profile_id": "q1", "requirements_sha256": RUBRIC, "checks": checks,
        "qwen_pass": verdict == "pass",
    }]}}}


def _reward(attempt, digest, value):
    return {"outputs": {"92": {"gvd_reward": [{
        "schema_version": 1, "attempt_id": attempt, "image_sha256": digest,
        "profile_id": "r1", "image_reward": value, "unit": "imagereward_raw",
    }]}}}


class FakeClient:
    def __init__(self, png, script):
        self.png = png
        self.script = list(script)

    def run(self, graph, attempt, journal: Path):
        if journal.exists():
            raise gvd_qa.QAError("Existing submission journal: reconcile before retry")
        gvd_qa.atomic_json(journal, {"state": "completed", "attempt_id": attempt})
        if journal.name.startswith("generation"):
            return {"outputs": {"9": {"images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}}}
        return self.script.pop(0)(attempt)

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
        self.entered.append(phase)
        return self.client

    def idle(self):
        self.idled = True


def _run(tmp, script, policy=None, resume=False):
    client = FakeClient(PNG, script)
    return gvd_qa.generate_until_accepted(
        generation_graph={
            "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
            "8": {"class_type": "VAEDecode", "inputs": {}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "x"}},
        },
        seed_bindings=(("3", "seed"),),
        generation_save_node="9",
        base_seed=1,
        expected_size=(8, 8),
        policy=policy or _policy(),
        requirements_json=REQ,
        make_fast_graph=lambda n, a, d: {"1": {"inputs": {"image": n}}},
        make_qwen_graph=lambda n, a, d: {"1": {"inputs": {"image": n}}},
        make_reward_graph=lambda n, a, d: {"1": {"inputs": {"image": n}}},
        phases=FakePhases(client),
        job_dir=tmp,
        resume=resume,
    ), client


class RemainingTests(unittest.TestCase):
    def test_resume_returns_existing_receipt(self):
        tmp = Path(tempfile.mkdtemp()) / "job"
        script = [
            lambda a: _metrics(a, DIGEST, 80.0),
            lambda a: _qwen(a, DIGEST),
            lambda a: _reward(a, DIGEST, 0.4),
        ]
        receipt, _ = _run(tmp, script)
        again, _ = _run(tmp, [], resume=True)
        self.assertEqual(receipt, again)

    def test_queued_journal_blocks_resume(self):
        tmp = Path(tempfile.mkdtemp()) / "job"
        tmp.mkdir()
        folder = tmp / "abc"
        folder.mkdir()
        gvd_qa.atomic_json(folder / "generation.json", {"state": "queued", "prompt_id": "p"})
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.reconcile_job_dir(tmp)

    def test_best_of_k_picks_higher_reward(self):
        tmp = Path(tempfile.mkdtemp()) / "job"
        script = [
            lambda a: _metrics(a, DIGEST, 80.0),
            lambda a: _qwen(a, DIGEST),
            lambda a: _reward(a, DIGEST, 0.1),
            lambda a: _metrics(a, DIGEST, 80.0),
            lambda a: _qwen(a, DIGEST),
            lambda a: _reward(a, DIGEST, 0.9),
        ]
        receipt, _ = _run(tmp, script, policy=_policy(max_attempts=2, best_of_k=2))
        data = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(data["scores"]["image_reward"], 0.9)
        self.assertEqual(data["selection"], "best_of_k")

    def test_ablation_jobs_max_attempts_one(self):
        history = {"outputs": {"61": {"gvd_variants": [
            {"index": 0, "prompt": "a | b", "label": "baseline"},
            {"index": 1, "prompt": "a", "label": "drop b"},
        ]}}}
        jobs = list(gvd_qa.ablation_jobs(history, [1, 2], "flux", "abc"))
        self.assertEqual(len(jobs), 4)
        self.assertTrue(all(j["max_attempts"] == 1 for j in jobs))
        self.assertTrue(all(j["purpose"] == "ablation_measurement" for j in jobs))

    def test_clip_overlong_and_unknown_class(self):
        audit = gvd_qa.clip_token_audit(" ".join(["token"] * 80))
        self.assertTrue(audit["overlong"])
        graph = {"20": {"class_type": "Clip_Score-missing"}}
        missing = gvd_qa.missing_graph_classes(graph, {"LoadImage": {}})
        self.assertEqual(missing, ["Clip_Score-missing"])
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.missing_graph_classes(graph, None)

    def test_onnx_cuda_forbidden_and_cpu_ok(self):
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.onnx_must_be_cpu(["CUDAExecutionProvider", "CPUExecutionProvider"])
        gvd_qa.onnx_must_be_cpu(["CPUExecutionProvider"])
        path = write_qa_worker_wd14_settings(Path(tempfile.mkdtemp()) / "pysssss.json")
        assert_cpu_providers(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(cpu_ort_settings()["ortProviders"], ["CPUExecutionProvider"])

    def test_free_busy_and_zero_headroom(self):
        class Sess:
            def __init__(self):
                self.n = 0
            def get(self, url, timeout=None):
                self.n += 1
                class R:
                    def raise_for_status(self):
                        return None
                    def json(self):
                        return {"queue_running": [1], "queue_pending": []}
                return R()
            def post(self, *a, **k):
                raise AssertionError("must not /free while busy")
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.free_idle_comfy(Sess(), "http://127.0.0.1:8188")
        from gvd_qa.phases import LeasePhaseController
        from gvd_tool_router.paths import GvdLayout
        layout = GvdLayout(Path(tempfile.mkdtemp()))
        layout.ensure()
        ctl = LeasePhaseController(layout=layout, skip_live_free=True, free_vram_mib=100)
        with self.assertRaises(Exception) as ctx:
            ctl.enter("fast_qa")
        self.assertIn("RESOURCE_BLOCKED", str(ctx.exception))

    def test_journal_exists_is_reconcile_not_reroll(self):
        client = gvd_qa.ComfyClient.__new__(gvd_qa.ComfyClient)
        journal = Path(tempfile.mkdtemp()) / "generation.json"
        journal.write_text("{}", encoding="utf-8")
        with self.assertRaises(gvd_qa.QAError) as ctx:
            client.run({}, "a", journal)
        self.assertIn("reconcile", str(ctx.exception))

    def test_i2v_bypass_rejected(self):
        tmp = Path(tempfile.mkdtemp())
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.accepted_i2v_image(tmp / "missing.json", "unit", RUBRIC)
        receipt = tmp / "accepted.json"
        gvd_qa.atomic_json(receipt, {"accepted": False, "reasons": ["x"],
                                     "policy_id": "unit", "requirements_sha256": RUBRIC,
                                     "image_sha256": DIGEST, "image_path": str(tmp / "c.png")})
        with self.assertRaises(gvd_qa.QAError):
            gvd_qa.accepted_i2v_image(receipt, "unit", RUBRIC)

    def test_redirect_drops_i2v_and_evidence_insert_only(self):
        graph = {
            "8": {"class_type": "VAEDecode", "inputs": {}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "pub"}},
            "12": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {}},
        }
        out = gvd_qa.redirect_generation_save(graph, "8", "9")
        self.assertNotIn("12", out)
        self.assertTrue(out["9"]["inputs"]["filename_prefix"].startswith("gvd_candidates/"))
        db = connect_evidence(Path(tempfile.mkdtemp()) / "qa.sqlite")
        eid = insert_evidence(db, job_id="j", verdict={
            "attempt_id": "a", "image_sha256": DIGEST, "policy_id": "unit",
            "scores": {"clip_text": 80}, "wd14_traits": {}, "accepted": True,
            "reasons": [], "seed": 1,
        }, rubric_sha256=RUBRIC)
        self.assertTrue(eid)
        self.assertEqual(len(read_evidence(db, "a")), 1)
        insert_experiment(db, {"variant_index": 0, "variant_hash": "h", "seed": 1,
                               "label": "no_detectable_effect"})

    def test_stage_adapters_without_install(self):
        report = stage_comfy_gvd_qa(
            quarantine_dir=Path(tempfile.mkdtemp()),
            object_info={},
            install=False,
        )
        self.assertFalse(report["installed"])
        self.assertTrue(Path(report["staged"]).is_dir())
        self.assertTrue((Path(report["staged"]) / "comfy_adapters.py").is_file())
        act = qa_activation_report({})
        self.assertFalse(act["activable"])
        with self.assertRaises(ValueError):
            stage_comfy_gvd_qa(
                quarantine_dir=Path(tempfile.mkdtemp()),
                object_info={},
                install=True,
                trust_receipt=None,
            )


if __name__ == "__main__":
    unittest.main()
