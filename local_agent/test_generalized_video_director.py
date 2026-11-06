#!/usr/bin/env python3
"""Phase-2 Generalized Video Director: dataset, metric, mock MIPROv2."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import generalized_video_director as gvd


class BetaSetTests(unittest.TestCase):
    def test_sixteen_rows_three_generalized_plus_one_backrooms(self):
        rows = gvd.beta_set_rows()
        self.assertEqual(len(rows), 16)
        grouped = gvd.beta_set_by_category()
        self.assertEqual(set(grouped), set(gvd.CATEGORIES))
        self.assertEqual(len(grouped["drone_high_kinematics"]), 5)
        self.assertEqual(len(grouped["macro_nature"]), 5)
        self.assertEqual(len(grouped["stylized_2d"]), 5)
        self.assertEqual(len(grouped["backrooms"]), 1)
        self.assertEqual(grouped["backrooms"][0]["id"], "GVD-B01")

    def test_ids_and_intents_are_unique(self):
        rows = gvd.BETA_SET
        ids = [row["id"] for row in rows]
        intents = [row["user_intent"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(intents), len(set(intents)))

    def test_motion_class_unique_inside_each_category(self):
        grouped = gvd.beta_set_by_category()
        for category, rows in grouped.items():
            motions = [row["motion_class"] for row in rows]
            self.assertEqual(len(motions), len(set(motions)), category)

    def test_required_fields_and_vbench_focus(self):
        required = {
            "id", "category", "vbench_focus", "motion_class",
            "duration_seconds", "user_intent", "constraints",
        }
        for row in gvd.BETA_SET:
            self.assertTrue(required <= set(row), row.get("id"))
            self.assertGreaterEqual(len(row["user_intent"].split()), 12)
            self.assertIn(row["category"], gvd.CATEGORIES)
            self.assertGreaterEqual(row["duration_seconds"], 4.0)
            self.assertLessEqual(row["duration_seconds"], 8.0)
            self.assertIn(",", row["vbench_focus"])

    def test_beta_set_keeps_exactly_one_backrooms_retention_row(self):
        backrooms = [row for row in gvd.BETA_SET if row["category"] == "backrooms"]
        self.assertEqual(len(backrooms), 1)
        self.assertIn("level 0", backrooms[0]["user_intent"].lower())
        others = " ".join(
            row["user_intent"].lower()
            for row in gvd.BETA_SET
            if row["category"] != "backrooms"
        )
        self.assertNotIn("backrooms", others)
        self.assertNotIn("level 0", others)


class SignatureTests(unittest.TestCase):
    def test_outputs_include_prompts_and_hparam_floats(self):
        signature = gvd.director_signature_class()
        inputs = set(signature.input_fields)
        outputs = set(signature.output_fields)
        self.assertEqual(
            inputs,
            {"user_intent", "category", "vbench_focus", "duration_seconds", "constraints"},
        )
        # FLUX.1 start frame + MiniMax I2V: no positive_prompt/end_prompt, and
        # no denoise (FLUX Empty Latent always runs denoise=1.0).
        self.assertEqual(
            outputs,
            {"start_prompt", "video_prompt", "negative_prompt", "cfg_scale", "step_count"},
        )
        for name in ("cfg_scale", "step_count"):
            self.assertIs(signature.output_fields[name].annotation, float)
        self.assertIn("JSON numbers", signature.instructions)
        # The 1.5B student copied "start_prompt (FLUX.1 T2I):" as a prefix.
        self.assertNotIn("(FLUX.1 T2I):", signature.instructions)
        self.assertNotIn("(MiniMax I2V):", signature.instructions)
        self.assertIn("Never begin it", signature.instructions)

    def test_program_wires_chain_of_thought(self):
        program = gvd.build_director_program()
        self.assertEqual(type(program.director).__name__, "ChainOfThought")
        outputs = set(program.director.predict.signature.output_fields)
        self.assertTrue(
            {"start_prompt", "video_prompt", "negative_prompt", "cfg_scale", "step_count"}
            <= outputs
        )


class HparamClampTests(unittest.TestCase):
    def test_clamps_and_parses_gepa_strings(self):
        raw = SimpleNamespace(
            cfg_scale="around 12",
            denoise="0.2",
            step_count="steps: 48",
        )
        clamped = gvd.clamp_director_hparams(raw)
        self.assertEqual(clamped["cfg_scale"], gvd.CFG_SCALE_RANGE[1])
        self.assertEqual(clamped["denoise"], gvd.DENOISE_RANGE[0])
        self.assertEqual(clamped["step_count"], gvd.STEP_COUNT_RANGE[1])

    def test_defaults_on_garbage(self):
        clamped = gvd.clamp_director_hparams({"cfg_scale": "nope", "denoise": None})
        self.assertEqual(clamped["cfg_scale"], gvd.DEFAULT_HPARAMS["cfg_scale"])
        lo, hi = gvd.DENOISE_RANGE
        self.assertEqual(clamped["denoise"],
                         max(lo, min(hi, gvd.DEFAULT_HPARAMS["denoise"])))
        self.assertEqual(clamped["step_count"], gvd.DEFAULT_HPARAMS["step_count"])


class MetricTests(unittest.TestCase):
    def setUp(self):
        os.environ["GVD_CURRICULUM_ITERATION"] = "0"
        self.example = SimpleNamespace(
            id="GVD-D01",
            user_intent=(
                "A cinematic drone shot flies in from the open ocean toward "
                "sheer Atlantic cliffs at golden hour."
            ),
            category="drone_high_kinematics",
            vbench_focus="dynamic_degree, scene, motion_smoothness",
            duration_seconds=8.0,
            constraints="no text",
        )
        self.pred = SimpleNamespace(
            positive_prompt=(
                "A cinematic drone shot flies in from the open ocean toward "
                "sheer Atlantic cliffs at golden hour. Continuous aerial push-in, "
                "white spray against black basalt, nested seabirds, consistent lighting."
            ),
            negative_prompt="watermark, readable text, still photograph, morph",
            cfg_scale="around 12",
            denoise="0.2",
            step_count="steps: 48",
        )

    def test_metric_returns_float_and_json_feedback(self):
        score = gvd.generalized_video_metric(self.example, self.pred)
        self.assertIsInstance(score, float)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        feedback = json.loads(gvd.generalized_video_metric.last_feedback)
        self.assertTrue(feedback["mock"])
        self.assertEqual(feedback["hparams"]["cfg_scale"], gvd.CFG_SCALE_RANGE[1])
        self.assertEqual(feedback["hparams"]["denoise"], gvd.DENOISE_RANGE[0])
        self.assertEqual(feedback["hparams"]["step_count"], gvd.STEP_COUNT_RANGE[1])
        self.assertEqual(feedback["step_count_int"], int(gvd.STEP_COUNT_RANGE[1]))
        for key in gvd.VIDEO_DIRECTOR_SCORE_KEYS:
            self.assertIn(key, feedback["scores"])
        self.assertEqual(score, feedback["minimum"])
        self.assertEqual(feedback["threshold"], 0.60)

    def test_empty_prompt_scores_near_floor(self):
        pred = SimpleNamespace(
            positive_prompt="",
            negative_prompt="",
            cfg_scale=5.5,
            denoise=0.85,
            step_count=28,
        )
        score = gvd.generalized_video_metric(self.example, pred)
        self.assertLess(score, 0.40)

    def test_backrooms_row_rewards_physics_tokens(self):
        example = SimpleNamespace(
            id="GVD-B01",
            user_intent=(
                "Handheld first-person camcorder walk down a damp yellow "
                "Level 0 Backrooms hallway."
            ),
            category="backrooms",
        )
        weak = SimpleNamespace(
            positive_prompt="walk down a hallway with yellow walls and fluorescent lights.",
            negative_prompt="watermark",
            cfg_scale=5.5,
            denoise=0.9,
            step_count=28,
        )
        strong = SimpleNamespace(
            positive_prompt=(
                "Handheld first-person camcorder walk down a damp yellow Level 0 "
                "Backrooms hallway. First-person camcorder tracking, heavy VHS "
                "artifacting, handheld walking momentum, continuous unbroken shot, "
                "realistic camera shake, 1990s home video aesthetic."
            ),
            negative_prompt="watermark, text, apartment",
            cfg_scale=5.5,
            denoise=0.9,
            step_count=28,
        )
        weak_score = gvd.generalized_video_metric(example, weak)
        strong_score = gvd.generalized_video_metric(example, strong)
        self.assertGreater(strong_score, weak_score)

    def _hparams(self):
        return {"cfg_scale": 5.5, "denoise": 1.0, "step_count": 28.0}

    def test_current_signature_fields_are_scored(self):
        # 2026-09-16 signature: no positive_prompt at all.
        pred = SimpleNamespace(
            start_prompt=(
                "Sheer Atlantic cliffs at golden hour seen from the open ocean, "
                "black basalt, white spray."
            ),
            video_prompt="Cinematic drone flies in toward the cliffs, continuous aerial push-in.",
            negative_prompt="watermark, readable text",
        )
        scores = gvd.mock_vlm_scores(self.example, pred, self._hparams())
        self.assertGreater(scores["text_video_alignment"], 0.35)
        self.assertEqual(scores["temporal_consistency"], 0.72)
        empty = SimpleNamespace(start_prompt="", video_prompt="", negative_prompt="")
        self.assertEqual(
            gvd.mock_vlm_scores(self.example, empty, self._hparams())["text_video_alignment"],
            0.05,
        )

    def test_current_signature_candidates_are_distinguishable(self):
        weak = SimpleNamespace(
            start_prompt="A seascape.",
            video_prompt="The camera is still.",
            negative_prompt="watermark",
        )
        strong = SimpleNamespace(
            start_prompt="Sheer Atlantic cliffs at golden hour above the open ocean.",
            video_prompt="Cinematic drone flies in toward the cliffs, aerial push-in.",
            negative_prompt="watermark",
        )
        weak_scores = gvd.mock_vlm_scores(self.example, weak, self._hparams())
        strong_scores = gvd.mock_vlm_scores(self.example, strong, self._hparams())
        self.assertGreater(
            strong_scores["text_video_alignment"], weak_scores["text_video_alignment"]
        )
        self.assertGreater(
            strong_scores["temporal_consistency"], weak_scores["temporal_consistency"]
        )
        self.assertGreater(
            gvd.generalized_video_metric(self.example, strong),
            gvd.generalized_video_metric(self.example, weak),
        )

    def test_motion_cues_come_from_video_prompt_not_start_prompt(self):
        in_start = SimpleNamespace(
            start_prompt="A drone orbit shot of Atlantic cliffs.",
            video_prompt="Static composition, nothing changes.",
            negative_prompt="watermark",
        )
        in_video = SimpleNamespace(
            start_prompt="Atlantic cliffs.",
            video_prompt="Drone orbit around the cliffs.",
            negative_prompt="watermark",
        )
        self.assertEqual(
            gvd.mock_vlm_scores(self.example, in_start, self._hparams())["temporal_consistency"],
            0.42,
        )
        self.assertEqual(
            gvd.mock_vlm_scores(self.example, in_video, self._hparams())["temporal_consistency"],
            0.72,
        )

    def test_backrooms_physics_phrase_read_from_video_prompt(self):
        example = SimpleNamespace(
            id="GVD-B01",
            user_intent="Handheld camcorder walk down a yellow Backrooms hallway.",
            category="backrooms",
        )
        look = "1990s VHS still of a damp yellow Backrooms hallway, fluorescent lights."
        weak = SimpleNamespace(start_prompt=look, video_prompt="Walk forward.", negative_prompt="text")
        strong = SimpleNamespace(
            start_prompt=look,
            video_prompt="First-person camcorder tracking, handheld walking momentum.",
            negative_prompt="text",
        )
        weak_scores = gvd.mock_vlm_scores(example, weak, self._hparams())
        strong_scores = gvd.mock_vlm_scores(example, strong, self._hparams())
        self.assertLessEqual(weak_scores["temporal_consistency"], 0.48)
        self.assertGreater(
            strong_scores["temporal_consistency"], weak_scores["temporal_consistency"]
        )


class MockCompileTests(unittest.TestCase):
    def test_mock_lm_emits_float_hparams(self):
        gvd.configure_mock_lms()
        program = gvd.build_director_program()
        pred = program(
            user_intent="A drone flies toward Atlantic cliffs at golden hour.",
            category="drone_high_kinematics",
            vbench_focus="dynamic_degree, scene",
            duration_seconds=8.0,
            constraints="no text",
        )
        self.assertTrue(str(pred.start_prompt).strip())
        self.assertTrue(str(pred.video_prompt).strip())
        self.assertNotEqual("mock", str(pred.start_prompt).strip())
        self.assertNotEqual("mock", str(pred.video_prompt).strip())
        self.assertTrue(str(pred.negative_prompt).strip())
        hparams = gvd.clamp_director_hparams(pred)
        self.assertIsInstance(hparams["cfg_scale"], float)
        self.assertIsInstance(hparams["denoise"], float)
        self.assertIsInstance(hparams["step_count"], float)

    def test_mock_video_prompt_carries_motion_and_backrooms_physics(self):
        gvd.configure_mock_lms()
        program = gvd.build_director_program()
        cases = {
            "drone_high_kinematics": "A drone flies toward Atlantic cliffs at golden hour.",
            "backrooms": "Handheld camcorder walk down a yellow Backrooms hallway.",
        }
        for category, intent in cases.items():
            with self.subTest(category=category):
                pred = program(
                    user_intent=intent,
                    category=category,
                    vbench_focus="dynamic_degree",
                    duration_seconds=8.0,
                    constraints="no text",
                )
                example = SimpleNamespace(user_intent=intent, category=category)
                scores = gvd.mock_vlm_scores(
                    example, pred, gvd.clamp_director_hparams(pred)
                )
                # 0.72 is the motion-cue floor; without a cue the mock caps near 0.50.
                self.assertGreaterEqual(scores["temporal_consistency"], 0.72)
                if category == "backrooms":
                    video = str(pred.video_prompt).lower()
                    start = str(pred.start_prompt).lower()
                    self.assertIn("handheld walking momentum", video)
                    self.assertIn("yellow", start)
                    self.assertIn("vhs", start)
                    self.assertNotIn("yellow", video)

    def test_mipro_mock_compile_runs(self):
        rows = gvd.BETA_SET[:3]
        trainset = gvd.load_beta_trainset(rows)
        with tempfile.TemporaryDirectory() as tmp:
            save_path = Path(tmp) / "gvd_mock.json"
            compiled, path = gvd.compile_director(
                mock=True,
                auto=None,
                trainset=trainset,
                valset=trainset,
                save_path=save_path,
                log_dir=Path(tmp) / "logs",
                num_candidates=1,
                num_trials=1,
                max_bootstrapped_demos=0,
                max_labeled_demos=0,
            )
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 32)
            self.assertIsNotNone(compiled)
            score = gvd.generalized_video_metric(
                trainset[0],
                compiled(
                    user_intent=trainset[0].user_intent,
                    category=trainset[0].category,
                    vbench_focus=trainset[0].vbench_focus,
                    duration_seconds=trainset[0].duration_seconds,
                    constraints=trainset[0].constraints,
                ),
            )
            self.assertIsInstance(score, float)

    def test_live_compile_is_refused(self):
        with self.assertRaises(RuntimeError):
            gvd.compile_director(mock=False)


if __name__ == "__main__":
    unittest.main()
