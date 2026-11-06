#!/usr/bin/env python3
"""DSPy visual-QA metric: fail-closed, cached, no live ComfyUI or VLM."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import dspy_optimizer


def _gradient_png(path: Path, size=(1024, 768)) -> None:
    im = Image.new("RGB", size)
    px = im.load()
    w, h = size
    for y in range(h):
        for x in range(w):
            px[x, y] = ((x * 255) // max(w - 1, 1), (y * 255) // max(h - 1, 1), 90)
    im.save(path)


C016_LAST = (
    "Static low, slightly tilted 4:3 consumer-camcorder POV lying on the floor "
    "of an empty Level 0 Backrooms interior. Damp brown-beige carpet dominates "
    "the foreground under sickly yellow fluorescent light. Patterned yellow "
    "wallpaper, low acoustic ceiling tiles, rectangular fluorescent fixtures, "
    "and repetitive empty office openings are visible beyond the carpet. Do not "
    "depict the actor's face or torso. The actor is entirely outside the frame: "
    "no person, no hand, no sleeve, no body. No visible camera body, lens, "
    "tripod, operator, crew, apartment furniture, text, blood, or gore. The "
    "requested subject is the empty floor-level Backrooms environment itself; "
    "absence of a person or pose is correct."
)

PASSING_VLM = {
    "status": "pass",
    "model": "qwen25-vl-nsfw-caption:v4-q4_k_m",
    "runtime": "llama.cpp",
    "reasons": [],
    "verdict": {
        "pass": True,
        "rationale": "Empty Level 0 plate, no camera, no actor.",
        "observed": {"subjects": [], "setting": "backrooms", "camera_visible": False},
        "checks": {
            "requested_subjects_present": True,
            "requested_pose_or_action_visible": True,
            "requested_composition_visible": True,
            "setting_matches": True,
            "identity_continuity": True,
            "no_forbidden_equipment": True,
            "blind_observation_consistent": True,
        },
    },
}

FAILING_VLM = {
    "status": "fail",
    "model": "qwen25-vl-nsfw-caption:v4-q4_k_m",
    "runtime": "llama.cpp",
    "reasons": ["semantic check failed: no_forbidden_equipment"],
    "verdict": {
        "pass": False,
        "rationale": "Visible camera body in the lower left.",
        "observed": {"subjects": [], "setting": "backrooms", "camera_visible": True},
        "checks": {
            "requested_subjects_present": True,
            "requested_pose_or_action_visible": True,
            "requested_composition_visible": True,
            "setting_matches": True,
            "identity_continuity": True,
            "no_forbidden_equipment": False,
            "blind_observation_consistent": True,
        },
    },
}


class DspyOptimizerMetricTests(unittest.TestCase):
    def setUp(self):
        dspy_optimizer._RENDER_CACHE.clear()
        dspy_optimizer._VIDEO_RENDER_CACHE.clear()
        os.environ.pop("DSPY_OPT_DRY_RUN", None)
        os.environ["DSPY_OPT_TARGET"] = "still"
        self.example = SimpleNamespace(
            scene_spec="empty Level 0 floor plate",
            clip_id="C016",
            frame="last",
            constraints="no actor face or torso",
            seed=1016,
        )
        self.pred = SimpleNamespace(positive_prompt=C016_LAST, negative_prompt="")

    def test_locked_sampler_constants_are_not_read_from_pred(self):
        self.assertEqual(dspy_optimizer.LOCKED_CFG, 7.0)
        self.assertEqual(dspy_optimizer.LOCKED_STEPS, 30)
        self.assertEqual(dspy_optimizer.LOCKED_SAMPLER, "euler")
        self.assertEqual(dspy_optimizer.RENDER_TIMEOUT_S, 60)
        self.assertFalse(hasattr(dspy_optimizer, "clamp_params"))

    def test_prompt_assertion_failure_skips_gpu(self):
        pred = SimpleNamespace(
            positive_prompt="actor walks through the backrooms",
            negative_prompt="",
        )
        renders = []
        result = dspy_optimizer.evaluate_candidate(
            self.example, pred,
            render_fn=lambda *a, **k: renders.append(a) or Path("nope.png"),
            vlm_fn=lambda *a, **k: self.fail("VLM must not run"),
        )
        self.assertEqual(result["gepa"], 0.0)
        self.assertEqual(result["mipro"], 0.0)
        self.assertTrue(result["skipped_gpu"])
        self.assertFalse(renders)
        self.assertIn("Prompt Assertion Failed", result["feedback"])
        metric = dspy_optimizer.gepa_metric(self.example, pred)
        self.assertEqual(metric.score, 0.0)

    def test_dry_run_passes_assertions_without_gpu(self):
        result = dspy_optimizer.evaluate_candidate(self.example, self.pred, dry_run=True)
        self.assertTrue(result["prompt_ok"])
        self.assertEqual(result["gepa"], 0.5)
        self.assertEqual(result["mipro"], 0.2)
        self.assertTrue(result["skipped_gpu"])

    def test_render_timeout_does_not_load_vlm(self):
        def boom(prompt, negative, example):
            raise TimeoutError("dropped")

        result = dspy_optimizer.evaluate_candidate(
            self.example, self.pred,
            render_fn=boom,
            vlm_fn=lambda *a, **k: self.fail("VLM must not run"),
        )
        self.assertEqual(result["gepa"], 0.0)
        self.assertIn("Timed Out", result["feedback"])

    def test_mechanical_fail_does_not_load_vlm(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "still.png"
            _gradient_png(png, size=(64, 64))
            vlm_calls = []
            offload_calls = []
            result = dspy_optimizer.evaluate_candidate(
                self.example, self.pred,
                render_fn=lambda prompt, negative, example: png,
                vlm_fn=lambda *a, **k: vlm_calls.append(1),
                free_vram_fn=lambda: self.fail("must not free/load VLM on mechanical fail"),
                offload_vlm_fn=lambda: offload_calls.append(1),
            )
        self.assertEqual(result["gepa"], 0.0)
        self.assertEqual(result["mipro"], 0.1)
        self.assertFalse(vlm_calls)
        self.assertFalse(offload_calls)
        self.assertIn("Mechanical check failed", result["feedback"])

    def test_semantic_fail_offloads_vlm_and_uses_check_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "still.png"
            _gradient_png(png)
            offloads = []
            result = dspy_optimizer.evaluate_candidate(
                self.example, self.pred,
                render_fn=lambda prompt, negative, example: png,
                vlm_fn=lambda image, prompt: FAILING_VLM,
                free_vram_fn=lambda: None,
                offload_vlm_fn=lambda: offloads.append(1),
            )
        self.assertEqual(result["gepa"], 0.0)
        self.assertGreater(result["mipro"], 0.4)
        self.assertLess(result["mipro"], 1.0)
        self.assertIn("no_forbidden_equipment", result["feedback"])
        self.assertIn("Visible camera body", result["feedback"])
        self.assertEqual(len(offloads), 1)

    def test_full_pass_is_one_cached_and_offloads_vlm(self):
        with tempfile.TemporaryDirectory() as tmp:
            png = Path(tmp) / "still.png"
            _gradient_png(png)
            calls = {"render": 0, "vlm": 0, "offload": 0}

            def render(prompt, negative, example):
                calls["render"] += 1
                return png

            def vlm(image, prompt):
                calls["vlm"] += 1
                return PASSING_VLM

            first = dspy_optimizer.evaluate_candidate(
                self.example, self.pred,
                render_fn=render, vlm_fn=vlm,
                free_vram_fn=lambda: None,
                offload_vlm_fn=lambda: calls.__setitem__("offload", calls["offload"] + 1),
            )
            second = dspy_optimizer.evaluate_candidate(
                self.example, self.pred,
                render_fn=render, vlm_fn=vlm,
                free_vram_fn=lambda: None,
                offload_vlm_fn=lambda: calls.__setitem__("offload", calls["offload"] + 1),
            )
        self.assertEqual(first["gepa"], 1.0)
        self.assertEqual(first["mipro"], 1.0)
        self.assertEqual(second["gepa"], 1.0)
        self.assertEqual(calls["render"], 1)
        self.assertEqual(calls["vlm"], 1)
        self.assertEqual(calls["offload"], 1)
        metric = dspy_optimizer.gepa_metric(self.example, self.pred)
        self.assertEqual(metric.score, 1.0)

    def test_compile_refuses_without_flag(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = dspy_optimizer.main([])
        self.assertEqual(code, 2)
        self.assertIn("Refusing to start GPU work", buf.getvalue())

    def test_wrong_vlm_identity_cannot_pass_parser(self):
        from media_accuracy_gate import semantic_verdict_from_caption
        caption = (
            '{"pass":true,"rationale":"x","observed":{"subjects":[],"setting":"backrooms"},'
            '"checks":{"requested_subjects_present":true,'
            '"requested_pose_or_action_visible":true,"requested_composition_visible":true,'
            '"setting_matches":true,"identity_continuity":true,'
            '"no_forbidden_equipment":true,"blind_observation_consistent":true}}'
        )
        bad = semantic_verdict_from_caption(
            caption, C016_LAST, model="stub", runtime="ollama",
        )
        self.assertEqual(bad["status"], "fail")
        good = semantic_verdict_from_caption(
            caption, C016_LAST,
            model="qwen25-vl-nsfw-caption:v4-q4_k_m", runtime="llama.cpp",
        )
        self.assertEqual(good["status"], "pass")


PASSING_VIDEO_PROMPT = (
    "[Handheld POV] Walk down a damp yellow Level 0 hallway. "
    "First-person camcorder tracking, heavy VHS artifacting, handheld walking "
    "momentum, continuous unbroken shot, realistic camera shake, and 1990s "
    "home video aesthetic."
)


class DspyVideoOptimizerMetricTests(unittest.TestCase):
    def setUp(self):
        dspy_optimizer._VIDEO_RENDER_CACHE.clear()
        os.environ.pop("DSPY_OPT_DRY_RUN", None)
        os.environ["DSPY_OPT_TARGET"] = "video"
        self.example = SimpleNamespace(
            scene_spec="damp yellow carpet hallway, Level 0 Backrooms",
            clip_id="OPT01",
            base_prompt="[Handheld POV] Walk down a damp yellow hallway.",
            start_prompt="carpet",
            end_prompt="wall",
            style="backrooms",
            camera_locked=False,
            seed=1601,
        )
        self.pred = SimpleNamespace(injected_prompt=PASSING_VIDEO_PROMPT)

    def tearDown(self):
        os.environ["DSPY_OPT_TARGET"] = "still"

    def test_missing_physics_skips_gpu(self):
        pred = SimpleNamespace(injected_prompt="walk down a hallway")
        renders = []
        result = dspy_optimizer.evaluate_video_candidate(
            self.example, pred,
            render_fn=lambda *a, **k: renders.append(a) or Path("nope.mp4"),
            vlm_fn=lambda *a, **k: self.fail("VLM must not run"),
        )
        self.assertEqual(result["gepa"], 0.0)
        self.assertEqual(result["mipro"], 0.0)
        self.assertTrue(result["skipped_gpu"])
        self.assertFalse(renders)
        self.assertIn("Video Prompt Assertion Failed", result["feedback"])
        self.assertIn("handheld walking momentum", result["feedback"])

    def test_dry_run_passes_assertions_without_gpu(self):
        result = dspy_optimizer.evaluate_video_candidate(
            self.example, self.pred, dry_run=True,
        )
        self.assertTrue(result["prompt_ok"])
        self.assertEqual(result["gepa"], 0.5)
        self.assertEqual(result["mipro"], 0.2)
        self.assertTrue(result["skipped_gpu"])

    def test_mechanical_fail_does_not_load_vlm(self):
        vlm_calls = []
        result = dspy_optimizer.evaluate_video_candidate(
            self.example, self.pred,
            render_fn=lambda prompt, example: Path("fake.mp4"),
            check_video_fn=lambda *a, **k: {"status": "fail", "reasons": ["no video stream"]},
            vlm_fn=lambda *a, **k: vlm_calls.append(1),
        )
        self.assertEqual(result["gepa"], 0.0)
        self.assertEqual(result["mipro"], 0.1)
        self.assertFalse(vlm_calls)
        self.assertIn("Mechanical video check failed", result["feedback"])

    def test_full_pass_is_cached_and_offloads_vlm(self):
        calls = {"render": 0, "vlm": 0, "offload": 0}

        def render(prompt, example):
            calls["render"] += 1
            return Path("ok.mp4")

        def vlm(video, prompt):
            calls["vlm"] += 1
            return PASSING_VLM

        first = dspy_optimizer.evaluate_video_candidate(
            self.example, self.pred,
            render_fn=render, vlm_fn=vlm,
            check_video_fn=lambda *a, **k: {"status": "pass", "reasons": []},
            free_vram_fn=lambda: None,
            offload_vlm_fn=lambda: calls.__setitem__("offload", calls["offload"] + 1),
        )
        second = dspy_optimizer.evaluate_video_candidate(
            self.example, self.pred,
            render_fn=render, vlm_fn=vlm,
            check_video_fn=lambda *a, **k: {"status": "pass", "reasons": []},
            free_vram_fn=lambda: None,
            offload_vlm_fn=lambda: calls.__setitem__("offload", calls["offload"] + 1),
        )
        self.assertEqual(first["gepa"], 1.0)
        self.assertEqual(first["mipro"], 1.0)
        self.assertEqual(second["gepa"], 1.0)
        self.assertEqual(calls["render"], 1)
        self.assertEqual(calls["vlm"], 1)
        self.assertEqual(calls["offload"], 1)
        metric = dspy_optimizer.gepa_metric(self.example, self.pred)
        self.assertEqual(metric.score, 1.0)

    def test_default_video_trainset_has_three_to_five_scenarios(self):
        rows = dspy_optimizer.default_video_trainset()
        self.assertGreaterEqual(len(rows), 3)
        self.assertLessEqual(len(rows), 5)
        self.assertTrue(all(ex.base_prompt for ex in rows))


if __name__ == "__main__":
    unittest.main()
