#!/usr/bin/env python3
"""Blueprint local fault tests. No live GPU."""
from __future__ import annotations

import importlib.util
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
from gvd_qa.local_client import LocalQaClient, checklist_from_mapping
from gvd_qa.local_phases import HybridPhaseController
from gvd_qa.pipeline import bind_fast, bind_qwen, bind_reward, load_policy
from gvd_qa.prompt_ablation import expand_prompt_variants, plan_history, record_ablation_from_plan
from gvd_qa.evidence import connect_evidence
from gvd_qa.phases import LeasePhaseController

_SPEC = importlib.util.spec_from_file_location("gvd_qa_ref", ROOT / "gvd_qa.py")
gvd_qa = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules["gvd_qa_ref"] = gvd_qa
_SPEC.loader.exec_module(gvd_qa)


def _png(size=(16, 16), color=(20, 40, 60)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


POLICY = HERE / "gvd_qa" / "profiles" / "observed_5080_c017_end_reroll.json"
RUBRIC = HERE / "gvd_qa" / "profiles" / "br24_c017_end_rubric.json"
GRAPH = ROOT / "local_agent" / "gvd_tool_router" / "fixtures" / "known_good_still.api.json"


class FakeGen:
    def __init__(self, png: bytes, fail_run: bool = False):
        self.png = png
        self.fail_run = fail_run
        self.runs = 0

    def run(self, graph, attempt, journal):
        self.runs += 1
        if self.fail_run:
            raise gvd_qa.QAError("worker crashed after queue")
        Path(journal).write_text("{}", encoding="utf-8")
        return {"outputs": {"7": {"images": [{"filename": "x.png", "subfolder": "", "type": "output"}]}}}

    def image_bytes(self, history, save_node):
        return self.png


class CrashAfterSavePhases:
    def __init__(self, qa, comfy):
        self.qa = qa
        self.comfy = comfy
        self.idled = False
        self.seen = []

    def enter(self, phase):
        self.seen.append(phase)
        if phase == "generate":
            return self.comfy
        if phase == "fast_qa" and "fast_qa" not in self.seen[:-1]:
            raise RuntimeError("QA worker crashed after candidate save")
        return self.qa

    def idle(self):
        self.idled = True


class FaultTests(unittest.TestCase):
    def _policy(self):
        return load_policy(POLICY)

    def _req(self):
        return RUBRIC.read_text(encoding="utf-8")

    def _qa(self, reward=0.1):
        return LocalQaClient(
            clip_score_fn=lambda b, t: 20.0,
            checklist_fn=checklist_from_mapping({"yellow_surfaces": "pass", "corridor": "pass"}),
            reward_fn=lambda b, t: reward,
        )

    def test_headroom_blocks(self):
        ctl = LeasePhaseController(skip_live_free=True, free_vram_mib=100, min_headroom_mib=2048)
        with self.assertRaises(Exception) as ctx:
            ctl.enter("generate")
        self.assertIn("RESOURCE_BLOCKED", str(ctx.exception))

    def test_onnx_cuda_forbidden(self):
        with self.assertRaises(Exception):
            gvd_qa.onnx_must_be_cpu(["CUDAExecutionProvider", "CPUExecutionProvider"])

    def test_unknown_node_class(self):
        missing = gvd_qa.missing_graph_classes(
            {"1": {"class_type": "NotARealNode"}}, {"LoadImage": {}})
        self.assertEqual(missing, ["NotARealNode"])

    def test_missing_checkpoint_name_is_not_a_class_gap(self):
        graph = json.loads(GRAPH.read_text(encoding="utf-8"))
        graph["1"]["inputs"]["ckpt_name"] = "does_not_exist.safetensors"
        missing = gvd_qa.missing_graph_classes(graph, {
            "CheckpointLoaderSimple": {}, "CLIPTextEncode": {}, "EmptyLatentImage": {},
            "KSampler": {}, "VAEDecode": {}, "SaveImage": {},
        })
        self.assertEqual(missing, [])

    def test_overlong_clip_caption(self):
        qa = LocalQaClient(clip_score_fn=lambda b, t: 1.0, audit_caption="word " * 80)
        png = _png()
        digest = gvd_qa.sha256(png)
        qa.upload(png, digest)
        tmp = Path(tempfile.mkdtemp()) / "fast.json"
        with self.assertRaises(Exception) as ctx:
            qa.run({"90": {"class_type": "GVDMetricReport", "inputs": {
                "attempt_id": "a", "image_sha256": digest, "profile_id": "m",
                "clip_text_unit": "torchmetrics_clipscore_0_100"}}}, "a", tmp)
        self.assertIn("token", str(ctx.exception).lower())

    def test_queued_journal_blocks_retry(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "attempt").mkdir()
        journal = tmp / "attempt" / "generation.json"
        gvd_qa.atomic_json(journal, {"state": "queued", "prompt_id": "x"})
        with self.assertRaises(Exception) as ctx:
            gvd_qa.reconcile_job_dir(tmp)
        self.assertIn("reconcile", str(ctx.exception).lower())

    def test_crash_after_save_resume_scores_orphan(self):
        png = _png(size=(512, 512))
        job = Path(tempfile.mkdtemp()) / "job"
        job.mkdir()
        orphan = job / "deadbeef"
        orphan.mkdir()
        (orphan / "candidate.png").write_bytes(png)
        qa = self._qa()
        gen = FakeGen(png)
        dest = gvd_qa.generate_until_accepted(
            generation_graph=json.loads(GRAPH.read_text(encoding="utf-8")),
            seed_bindings=(("5", "seed"),),
            generation_save_node="7",
            base_seed=1,
            expected_size=(512, 512),
            policy=self._policy(),
            requirements_json=self._req(),
            make_fast_graph=lambda n, a, d: bind_fast(n, a, d, self._policy(), None, local=True),
            make_qwen_graph=lambda n, a, d: bind_qwen(n, a, d, self._policy(), self._req(), local=True),
            make_reward_graph=lambda n, a, d: bind_reward(n, a, d, self._policy(), "x", local=True),
            phases=HybridPhaseController(qa, start_vlm=False, comfy=gen),
            job_dir=job,
            resume=True,
        )
        self.assertEqual(dest.name, "accepted.json")
        self.assertEqual(gen.runs, 0)
        self.assertTrue(json.loads(dest.read_text(encoding="utf-8")).get("resumed_orphan"))

    def test_best_of_k_picks_higher_reward(self):
        png = _png(size=(512, 512))
        rewards = iter([0.1, 1.7])
        qa = LocalQaClient(
            clip_score_fn=lambda b, t: 20.0,
            checklist_fn=checklist_from_mapping({"yellow_surfaces": "pass", "corridor": "pass"}),
            reward_fn=lambda b, t: next(rewards),
        )
        data = json.loads(POLICY.read_text(encoding="utf-8"))
        data["best_of_k"] = 2
        data["max_attempts"] = 2
        policy = gvd_qa.policy_from_mapping(data)
        policy.validate()
        tmp = Path(tempfile.mkdtemp()) / "bok"
        dest = gvd_qa.generate_until_accepted(
            generation_graph=json.loads(GRAPH.read_text(encoding="utf-8")),
            seed_bindings=(("5", "seed"),),
            generation_save_node="7",
            base_seed=3,
            expected_size=(512, 512),
            policy=policy,
            requirements_json=self._req(),
            make_fast_graph=lambda n, a, d: bind_fast(n, a, d, policy, None, local=True),
            make_qwen_graph=lambda n, a, d: bind_qwen(n, a, d, policy, self._req(), local=True),
            make_reward_graph=lambda n, a, d: bind_reward(n, a, d, policy, "x", local=True),
            phases=HybridPhaseController(qa, start_vlm=False, comfy=FakeGen(png)),
            job_dir=tmp,
        )
        receipt = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(receipt["selection"], "best_of_k")
        self.assertEqual(receipt["scores"]["image_reward"], 1.7)

    def test_wave_generates_then_scores(self):
        png = _png(size=(512, 512))
        gen = FakeGen(png)
        qa = self._qa()
        tmp = Path(tempfile.mkdtemp()) / "wave"
        dest = gvd_qa.generate_wave_then_score(
            generation_graph=json.loads(GRAPH.read_text(encoding="utf-8")),
            seed_bindings=(("5", "seed"),),
            generation_save_node="7",
            base_seed=4,
            expected_size=(512, 512),
            policy=self._policy(),
            requirements_json=self._req(),
            make_fast_graph=lambda n, a, d: bind_fast(n, a, d, self._policy(), None, local=True),
            make_qwen_graph=lambda n, a, d: bind_qwen(n, a, d, self._policy(), self._req(), local=True),
            make_reward_graph=lambda n, a, d: bind_reward(n, a, d, self._policy(), "x", local=True),
            phases=HybridPhaseController(qa, start_vlm=False, comfy=gen),
            job_dir=tmp,
            wave_n=2,
        )
        self.assertEqual(dest.name, "accepted.json")
        self.assertEqual(gen.runs, 2)
        self.assertEqual(json.loads(dest.read_text(encoding="utf-8")).get("mode"), "wave")

    def test_dino_logged_when_fn_present(self):
        png = _png()
        digest = gvd_qa.sha256(png)
        qa = LocalQaClient(
            clip_score_fn=lambda b, t: 12.0,
            dino_fn=lambda b: 0.91,
            audit_caption="yellow hallway",
        )
        qa.upload(png, digest)
        hist = qa.run({"90": {"class_type": "GVDMetricReport", "inputs": {
            "attempt_id": "a", "image_sha256": digest, "profile_id": "unmeasured_clip",
            "clip_text_unit": "torchmetrics_clipscore_0_100"}}}, "a",
            Path(tempfile.mkdtemp()) / "fast.json")
        self.assertEqual(hist["outputs"]["90"]["gvd_metrics"][0]["dino"], 0.91)

    def test_provisional_clip_floor_splits_labeled_stills(self):
        policy = load_policy(HERE / "gvd_qa" / "profiles" / "provisional_loop_labels_v1.json")
        self.assertEqual(policy.clip_text_min, 28.0)
        hist_lo = {"outputs": {"90": {"gvd_metrics": [{
            "schema_version": 1, "attempt_id": "a", "image_sha256": "0" * 64,
            "profile_id": "unmeasured_clip", "clip_text": 26.16,
            "clip_text_unit": "torchmetrics_clipscore_0_100"}]}}}
        hist_hi = {"outputs": {"90": {"gvd_metrics": [{
            "schema_version": 1, "attempt_id": "a", "image_sha256": "0" * 64,
            "profile_id": "unmeasured_clip", "clip_text": 33.49,
            "clip_text_unit": "torchmetrics_clipscore_0_100"}]}}}
        _, lo = gvd_qa.evaluate_fast(hist_lo, "a", "0" * 64, policy)
        _, hi = gvd_qa.evaluate_fast(hist_hi, "a", "0" * 64, policy)
        self.assertIn("clip_text_below_threshold", lo)
        self.assertEqual(hi, [])

    def test_prompt_ablation_max_attempts_one(self):
        prompt = "yellow carpet, empty hallway, fluorescent lights"
        variants = expand_prompt_variants(prompt)
        self.assertEqual(variants[0]["label"], "Baseline Full Prompt")
        self.assertEqual(len(variants), 4)
        plan = plan_history(variants)
        db = connect_evidence(Path(tempfile.mkdtemp()) / "e.sqlite")
        jobs = record_ablation_from_plan(db, plan, [1], prompt, "m", "r" * 64)
        self.assertTrue(all(j["max_attempts"] == 1 for j in jobs))
        n = db.execute("select count(*) from qa_experiments").fetchone()[0]
        self.assertEqual(n, len(jobs))


if __name__ == "__main__":
    unittest.main()
