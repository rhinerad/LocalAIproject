#!/usr/bin/env python3
"""Offline GVD QA loop tests. Stdlib only; no GPU."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gvd_qa.ablation import ignored_keywords, tokenize_prompt
from gvd_qa.evaluate import evaluate_artifact
from gvd_qa.graph import attach_wd14_tagger, find_image_output_nodes
from gvd_qa.loop import next_seed, run_qa_loop
from gvd_qa.parse import parse_verifier_outputs
from gvd_qa.tools import gvd_qa_evaluate
from gvd_qa.vram_phases import PHASE_FLUSH, PHASE_GENERATE, run_phase


def _fake_vlm_parser(caption, prompt, *, model, runtime):
    if model != "qwen25-vl-nsfw-caption:v4-q4_k_m" or runtime != "llama.cpp":
        return {"status": "fail", "scores": None, "reasons": ["wrong runtime"]}
    return {
        "status": "pass",
        "scores": {
            "text_video_alignment": float(caption),
            "temporal_consistency": 0.8,
            "aesthetic_quality": 0.8,
        },
        "reasons": [],
    }


class ParseTests(unittest.TestCase):
    def test_parses_yrikka_and_wd14(self):
        graph = {
            "8": {"class_type": "VAEDecode", "inputs": {}},
            "9": {"class_type": "WD14Tagger|pysssss", "inputs": {"image": ["8", 0]}},
            "10": {"class_type": "CLIPScoreVerifier", "inputs": {}},
            "11": {"class_type": "QwenVLMVerifier", "inputs": {}},
            "12": {"class_type": "ImageRewardVerifier", "inputs": {}},
        }
        history = {
            "outputs": {
                "9": {"text": ["yellow wallpaper, fluorescent, hallway"]},
                "10": {"text": ["0.18"]},
                "11": {"text": ["False"]},
                "12": {"result": [0.4]},
            }
        }
        parsed = parse_verifier_outputs(history, graph=graph)
        self.assertEqual(parsed["qwen_vl"], False)
        self.assertAlmostEqual(parsed["clip_score"], 0.18)
        self.assertAlmostEqual(parsed["image_reward"], 0.4)
        self.assertIn("yellow wallpaper", parsed["wd14_tags"])


class FailClosedEvaluateTests(unittest.TestCase):
    """Fix 2026-09-23 (readiness-audit finding 1.2): evaluate_artifact() was
    fail-open -- a nonexistent artifact with no other evidence returned
    passed=True/action="accept". These lock in the fail-closed behavior."""

    def test_nonexistent_artifact_with_no_evidence_does_not_pass(self):
        """Exact bug reproduced by the audit: a nonexistent MP4 path with no
        other evidence must never pass."""
        report = evaluate_artifact(
            prompt="empty yellow corridor",
            artifact_path="/tmp/definitely-does-not-exist-gvd-qa-probe.mp4",
        )
        self.assertFalse(report["passed"])
        self.assertNotEqual(report["action"], "accept")
        self.assertIn("artifact_missing_or_unreadable", report["reasons"])

    def test_no_evidence_at_all_does_not_pass(self):
        """No artifact_path, no history/graph scores, no vlm_caption: this
        must not silently accept just because nothing failed."""
        report = evaluate_artifact(prompt="empty yellow corridor")
        self.assertFalse(report["passed"])
        self.assertIn("no_qa_evidence", report["reasons"])

    def test_existing_real_artifact_with_real_evidence_still_passes(self):
        """The fix must not regress the legitimate accept path: a real file
        on disk plus a genuine passing verifier score."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            fh.write(b"not a real png but a real, non-empty file")
            path = fh.name
        try:
            graph = {"11": {"class_type": "QwenVLMVerifier", "inputs": {}}}
            report = evaluate_artifact(
                prompt="empty yellow corridor",
                artifact_path=path,
                graph=graph,
                history={"outputs": {"11": {"text": ["True"]}}},
            )
            self.assertTrue(report["passed"])
            self.assertEqual(report["action"], "accept")
            self.assertNotIn("artifact_missing_or_unreadable", report["reasons"])
            self.assertNotIn("no_qa_evidence", report["reasons"])
        finally:
            import os
            os.unlink(path)

    def test_empty_file_counts_as_missing(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as fh:
            path = fh.name  # zero bytes
        try:
            report = evaluate_artifact(prompt="x", artifact_path=path)
            self.assertFalse(report["passed"])
            self.assertIn("artifact_missing_or_unreadable", report["reasons"])
        finally:
            import os
            os.unlink(path)


class GraphTests(unittest.TestCase):
    def test_attach_wd14_keeps_save_image(self):
        graph = {
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0]}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "gvd"}},
        }
        out = attach_wd14_tagger(graph, image_node_id="8")
        self.assertEqual(out["9"]["class_type"], "SaveImage")
        self.assertEqual(out["9"]["inputs"]["images"], ["8", 0])
        self.assertEqual(out["10"]["class_type"], "WD14Tagger|pysssss")
        self.assertEqual(out["10"]["inputs"]["image"], ["8", 0])
        self.assertEqual(find_image_output_nodes(graph)[0][0], "8")


class EvaluateLoopTests(unittest.TestCase):
    def _mkdtemp(self) -> str:
        import shutil
        import tempfile
        path = tempfile.mkdtemp(prefix="gvd_qa_loop_test_")
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def test_qwen_false_or_low_clip_rerolls(self):
        graph = {
            "8": {"class_type": "VAEDecode", "inputs": {}},
            "10": {"class_type": "CLIPScoreVerifier", "inputs": {}},
            "11": {"class_type": "QwenVLMVerifier", "inputs": {}},
        }
        bad = evaluate_artifact(
            prompt="yellow wallpaper hallway fluorescent camcorder",
            history={"outputs": {"10": {"text": ["0.10"]}, "11": {"text": ["False"]}}},
            graph=graph,
            expected_tags=["yellow wallpaper"],
        )
        self.assertFalse(bad["passed"])
        self.assertEqual(bad["action"], "reroll")
        self.assertIn("qwen_vl_verifier_false", bad["reasons"])
        self.assertIn("clip_score_below_threshold", bad["reasons"])

    def test_wd14_required_tags_and_ablation(self):
        graph = {
            "9": {"class_type": "WD14Tagger|pysssss", "inputs": {}},
        }
        report = evaluate_artifact(
            prompt="yellow wallpaper fluorescent hallway camcorder walk",
            history={"outputs": {"9": {"text": ["indoor, hallway"]}}},
            graph=graph,
            expected_tags=["yellow wallpaper"],
            installed_nodes=["comfyui-wd14-tagger"],
        )
        self.assertIn("wd14_missing_required_tags", report["reasons"])
        self.assertIn("yellow", report["ignored_keywords"] or report["missing_required_tags"])
        self.assertEqual(report["adapters"]["comfyui-wd14-tagger"], "installed")
        self.assertEqual(report["adapters"]["comfyui-inference-time-scaling"], "adapter_required")

    def test_caption_v4_alignment_gate(self):
        report = evaluate_artifact(
            prompt="apartment living room",
            vlm_caption="0.20",
            vlm_parser=_fake_vlm_parser,
            require_vlm=True,
        )
        self.assertFalse(report["passed"])
        self.assertIn("caption_v4_alignment_below_threshold", report["reasons"])

    def test_loop_accepts_on_second_seed(self):
        graph = {
            "10": {"class_type": "CLIPScoreVerifier", "inputs": {}},
            "11": {"class_type": "QwenVLMVerifier", "inputs": {}},
        }

        # Fix 2026-09-23 (readiness-audit finding 1.2): evaluate_artifact()
        # now fails closed on a missing/unreadable artifact_path, so this
        # fixture must point at real files, the same as a real render would
        # produce, rather than the bare placeholder strings "a.png"/"b.png".
        tmpdir = Path(self._mkdtemp())
        (tmpdir / "a.png").write_bytes(b"a")
        (tmpdir / "b.png").write_bytes(b"b")

        def render(seed: int):
            if seed == 1:
                return {
                    "artifact_path": str(tmpdir / "a.png"),
                    "graph": graph,
                    "history": {"outputs": {"10": {"text": ["0.1"]}, "11": {"text": ["False"]}}},
                }
            return {
                "artifact_path": str(tmpdir / "b.png"),
                "graph": graph,
                "history": {"outputs": {"10": {"text": ["0.9"]}, "11": {"text": ["True"]}}},
            }

        phases: list[str] = []
        result = run_qa_loop(
            prompt="test",
            seed=1,
            render=render,
            attempt_budget=3,
            prepare_comfy=lambda reason: phases.append("comfy"),
            release_comfy=lambda reason: phases.append("flush"),
            comfy_free=lambda: phases.append("free"),
        )
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["seed"], next_seed(1, 0))
        self.assertEqual(len(result["attempts"]), 2)
        self.assertIn("comfy", phases)
        self.assertIn("flush", phases)
        self.assertIn("free", phases)

    def test_prior_artifacts_is_forwarded_and_flags_duplicate(self):
        """Fix 2026-09-23 (readiness-audit finding 1.2): run_qa_loop() never
        forwarded prior_artifacts/artifact_bytes to evaluate_fn, so
        duplicate detection (evaluate_artifact only runs it `if
        prior_artifacts:`) was silently dead for every caller of this
        generic loop. This proves it now actually reaches evaluate_fn."""
        received_kwargs = []

        def fake_evaluate(**kwargs):
            received_kwargs.append(kwargs)
            return {"passed": True, "action": "accept", "reasons": []}

        prior = [("empty yellow corridor", b"prior-image-bytes")]

        def render(seed: int):
            return {"artifact_path": None, "artifact_bytes": b"candidate-bytes"}

        run_qa_loop(
            prompt="empty yellow corridor",
            seed=1,
            render=render,
            evaluate=fake_evaluate,
            prior_artifacts=prior,
        )
        self.assertEqual(len(received_kwargs), 1)
        self.assertEqual(received_kwargs[0]["prior_artifacts"], prior)
        self.assertEqual(received_kwargs[0]["artifact_bytes"], b"candidate-bytes")

    def test_vlm_released_even_when_render_raises(self):
        """Fix 2026-09-23 (readiness-audit finding 1.2): a render()/evaluate
        exception must not skip finish_validate(release_vlm) and leak a
        loaded VLM on the GPU."""
        released = []

        def boom(seed: int):
            raise RuntimeError("render exploded")

        with self.assertRaises(RuntimeError):
            run_qa_loop(
                prompt="x",
                seed=1,
                render=boom,
                release_vlm=lambda reason: released.append(reason),
            )
        self.assertEqual(len(released), 1, "release_vlm must run despite the exception")

    def test_vram_generate_never_prepares_vlm(self):
        called = []
        run_phase(
            PHASE_GENERATE,
            prepare_comfy=lambda r: called.append("comfy"),
            prepare_vlm=lambda r: called.append("vlm"),
        )
        self.assertEqual(called, ["comfy"])
        run_phase(PHASE_FLUSH, comfy_free=lambda: called.append("free"), release_comfy=lambda r: called.append("rel"))
        self.assertIn("free", called)

    def test_tool_json(self):
        payload = gvd_qa_evaluate({
            "prompt": "yellow hallway",
            "history": {"outputs": {}},
            "seed": 7,
        })
        data = json.loads(payload)
        self.assertIn("passed", data)
        self.assertEqual(data["next_seed"], 8)


class AblationTests(unittest.TestCase):
    def test_tokenize_skips_stopwords(self):
        tokens = tokenize_prompt("A yellow wallpaper hallway with the camcorder")
        self.assertIn("yellow", tokens)
        self.assertNotIn("the", tokens)
        ignored = ignored_keywords("yellow wallpaper camcorder", ["hallway"])
        self.assertIn("yellow", ignored)


if __name__ == "__main__":
    unittest.main()
