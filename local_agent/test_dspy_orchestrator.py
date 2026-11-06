#!/usr/bin/env python3
"""Phase-3 live orchestrator: VRAM flip-flop order and TimeoutError fail-closed.

Does not call ComfyUI, Qwen, or --compile. Hardware callables are injected.
"""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import dspy_orchestrator as orch
from media_accuracy_gate import parse_video_director_scores


def _passing_parsed():
    caption = (
        '{"text_video_alignment":0.82,"temporal_consistency":0.74,'
        '"aesthetic_quality":0.80,'
        '"rationale":{"text_video_alignment":"subjects match",'
        '"temporal_consistency":"identity holds",'
        '"aesthetic_quality":"clean frame"}}'
    )
    return parse_video_director_scores(
        caption, "drone cliffs",
        model=orch.EXACT_VLM_MODEL, runtime=orch.EXACT_VLM_RUNTIME,
    )


class LiveMetricFlipFlopTests(unittest.TestCase):
    def setUp(self):
        self.order = []
        self.example = SimpleNamespace(
            id="GVD-D01",
            category="drone_high_kinematics",
            user_intent="A cinematic drone shot toward Atlantic cliffs.",
        )
        self.pred = SimpleNamespace(
            positive_prompt=(
                "A cinematic drone shot flies in from the open ocean toward "
                "sheer Atlantic cliffs at golden hour. Continuous aerial push-in."
            ),
            negative_prompt="watermark, text, morph",
            cfg_scale="around 12",
            denoise="0.2",
            step_count="steps: 48",
        )

    def _hooks(self, render):
        def prepare_comfy(reason=""):
            self.order.append(("prepare_comfy", reason))

        def release_comfy(reason=""):
            self.order.append(("release_comfy", reason))

        def prepare_vlm(reason=""):
            self.order.append(("prepare_vlm", reason))

        def release_vlm(reason=""):
            self.order.append(("release_vlm", reason))

        def extract(path):
            self.order.append(("extract", str(path)))
            return [Path("frame.png")]

        def vlm(frames, prompt):
            self.order.append(("vlm", len(frames)))
            return _passing_parsed()

        def check(path, prompt="", clip_id=""):
            return {"status": "pass", "reasons": []}

        return dict(
            render_fn=render,
            vlm_fn=vlm,
            extract_fn=extract,
            check_fn=check,
            prepare_comfy=prepare_comfy,
            release_comfy=release_comfy,
            prepare_vlm=prepare_vlm,
            release_vlm=release_vlm,
        )

    def test_success_order_is_prepare_comfy_release_then_vlm_then_vlm_release(self):
        def render(example, pred, hparams):
            self.order.append((
                "render",
                hparams["cfg_scale"],
                hparams["denoise"],
                hparams["step_count"],
            ))
            self.assertEqual(hparams["cfg_scale"], 8.0)
            # FLUX Empty Latent: DENOISE_RANGE pins denoise to 1.0.
            self.assertEqual(hparams["denoise"], 1.0)
            self.assertEqual(hparams["step_count"], 40.0)
            return Path("ok.mp4")

        result = orch.evaluate_live_candidate(self.example, self.pred, **self._hooks(render))
        self.assertEqual(
            [item[0] if isinstance(item, tuple) else item for item in self.order],
            [
                "prepare_comfy", "render", "release_comfy",
                "prepare_vlm", "extract", "vlm", "release_vlm",
            ],
        )
        self.assertEqual(self.order[0][1], "FLUX.1 + MiniMax I2V generation")
        self.assertEqual(self.order[2][1], "FLUX+MiniMax complete; VRAM free for VLM")
        parsed = _passing_parsed()
        self.assertAlmostEqual(parsed["minimum"], 0.74)
        # MIPRO scalar: 0.7 * minimum + 0.3 * mean.
        self.assertAlmostEqual(result["mipro"],
                               0.7 * parsed["minimum"] + 0.3 * parsed["mean"])
        feedback = json.loads(result["feedback"])
        self.assertFalse(feedback["mock"])
        self.assertEqual(feedback["hparams"]["cfg_scale"], 8.0)
        self.assertEqual(feedback["step_count_int"], 40)

    def test_timeout_releases_vram_returns_zero_skips_vlm(self):
        def render(example, pred, hparams):
            self.order.append("render")
            raise TimeoutError("ComfyUI job dropped from queue")

        result = orch.evaluate_live_candidate(self.example, self.pred, **self._hooks(render))
        names = [item[0] if isinstance(item, tuple) else item for item in self.order]
        self.assertEqual(names, ["prepare_comfy", "render", "release_comfy"])
        # _fail_penalty: distinct small scalars per failure mode; timeout = 0.05.
        self.assertEqual(result["mipro"], 0.05)
        self.assertIn("TimeoutError", result["error"])
        self.assertNotIn("vlm", names)

    def test_all_zero_judged_clip_outranks_every_failure_penalty(self):
        # 2026-09-24ad: a rendered, judged clip must rank above a timeout /
        # mechanical / pipeline failure however bad its scores.
        zero = parse_video_director_scores(
            '{"text_video_alignment":0.0,"temporal_consistency":0.0,'
            '"aesthetic_quality":0.0,"rationale":{}}',
            "drone cliffs", model=orch.EXACT_VLM_MODEL, runtime=orch.EXACT_VLM_RUNTIME,
        )
        self.assertEqual(zero["status"], "pass")
        hooks = self._hooks(lambda example, pred, hparams: Path("ok.mp4"))
        hooks["vlm_fn"] = lambda frames, prompt: zero
        result = orch.evaluate_live_candidate(self.example, self.pred, **hooks)
        self.assertEqual(result["mipro"], orch.JUDGED_SCORE_FLOOR)
        for error in ("TimeoutError: queue", "mechanical: instruction echo",
                      "json unparseable", "comfy dispatch failed", "unknown"):
            self.assertGreater(result["mipro"], orch._fail_penalty(error))
        feedback = json.loads(result["feedback"])
        self.assertEqual(feedback["mipro_raw"], 0.0)
        self.assertEqual(feedback["mipro"], orch.JUDGED_SCORE_FLOOR)
        self.assertFalse(feedback["passes_curriculum"])

    def test_judged_scalar_floor_only_lifts_the_bottom(self):
        self.assertGreater(orch.JUDGED_SCORE_FLOOR,
                           max(orch._fail_penalty(e) for e in ("timeout", "json", "comfy", "")))
        self.assertEqual(orch._judged_scalar(0.0, 0.0), orch.JUDGED_SCORE_FLOOR)
        # raw 0.045 sat below the 0.05 timeout penalty before the floor.
        self.assertEqual(orch._judged_scalar(0.0, 0.15), orch.JUDGED_SCORE_FLOOR)
        self.assertAlmostEqual(orch._judged_scalar(0.30, 0.6833), 0.7 * 0.30 + 0.3 * 0.6833)
        self.assertAlmostEqual(orch._judged_scalar(0.74, 0.7867), 0.7 * 0.74 + 0.3 * 0.7867)
        self.assertEqual(orch._judged_scalar(1.0, 1.0), 1.0)

    def test_metric_entrypoint_stores_json_feedback(self):
        def render(example, pred, hparams):
            return Path("ok.mp4")

        hooks = self._hooks(render)
        result = orch.evaluate_live_candidate(self.example, self.pred, **hooks)
        # _store appends to HERE/runtime/dspy_opt/gvd_live_metric_history.jsonl;
        # point HERE at a temp dir so tests stop writing fake rows into it.
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp, patch.object(orch, "HERE", Path(tmp)):
            score = orch._store(result)
            self.assertTrue((Path(tmp) / "runtime" / "dspy_opt"
                             / "gvd_live_metric_history.jsonl").is_file())
        self.assertIsInstance(score, float)
        payload = json.loads(orch.generalized_video_metric.last_feedback)
        self.assertIn("scores", payload)
        self.assertEqual(payload["minimum"], 0.74)

    def test_backrooms_prompt_without_motion_keyword_skips_gpu(self):
        # 2026-09-25j: the mechanical gate reads only the prompts, so it runs
        # before the render. History row 265 (2026-09-25i) spent 757 s of GPU
        # on a Backrooms clip and then scored it 0.02 for a missing motion
        # keyword without judging it.  2026-09-26e: row 265's own wording
        # ("gradually moves ... panning") is accepted now, so this test uses
        # a prompt with no motion at all -- the negated "does not move" is
        # blanked by the floor and must not count.
        example = SimpleNamespace(id="GVD-B01", category="backrooms",
                                  user_intent="Handheld camcorder walk down a yellow hallway.")
        pred = SimpleNamespace(
            start_prompt="1990s VHS camcorder footage of a damp yellow hallway.",
            video_prompt="The handheld camcorder holds on the wallpaper; the camera does not move.",
            cfg_scale="3.5", denoise="1.0", step_count="20")
        result = orch.evaluate_live_candidate(
            example, pred,
            render_fn=lambda *a, **k: self.fail("must not render"),
            prepare_comfy=lambda **k: self.fail("must not take VRAM"))
        self.assertEqual(result["mipro"], 0.02)
        self.assertIn("mechanical video check failed", result["error"])
        self.assertIn("motion keyword", result["error"])
        self.assertIn("skipped GPU", result["error"])
        feedback = json.loads(result["feedback"])
        self.assertIsNone(feedback["video_path"])
        self.assertFalse(feedback["passes_curriculum"])

    def test_backrooms_prompt_with_keywords_still_renders(self):
        example = SimpleNamespace(id="GVD-B01", category="backrooms",
                                  user_intent="Handheld camcorder walk down a yellow hallway.")
        pred = SimpleNamespace(
            start_prompt="1990s VHS camcorder footage of a damp yellow hallway.",
            video_prompt="Handheld first-person camcorder walk forward down the hallway.",
            cfg_scale="3.5", denoise="1.0", step_count="20")
        def render(example, pred, hparams):
            self.order.append(("render",))
            return Path("ok.mp4")

        hooks = self._hooks(render)
        del hooks["check_fn"]  # exercise the built-in gate, not the injected stub
        result = orch.evaluate_live_candidate(example, pred, **hooks)
        names = [item[0] if isinstance(item, tuple) else item for item in self.order]
        self.assertIn("render", names)
        self.assertIn("vlm", names)
        self.assertIsNone(result.get("error"))

    def test_backrooms_row_265_phrasing_now_renders(self):
        # 2026-09-26e (operator decision 26d): the exact video_prompt that
        # history row 265 rejected is admitted and goes to the render.
        example = SimpleNamespace(id="GVD-B01", category="backrooms",
                                  user_intent="Handheld camcorder walk down a yellow hallway.")
        pred = SimpleNamespace(
            start_prompt="1990s VHS camcorder footage of a damp yellow hallway.",
            video_prompt="The handheld camcorder gradually moves along the hallway, panning slowly.",
            cfg_scale="3.5", denoise="1.0", step_count="20")

        def render(example, pred, hparams):
            self.order.append(("render",))
            return Path("ok.mp4")

        hooks = self._hooks(render)
        del hooks["check_fn"]
        result = orch.evaluate_live_candidate(example, pred, **hooks)
        names = [item[0] if isinstance(item, tuple) else item for item in self.order]
        self.assertIn("render", names)
        self.assertIsNone(result.get("error"))

    def test_injected_check_fn_still_runs_after_the_render(self):
        rendered = []

        def render(example, pred, hparams):
            rendered.append(True)
            return Path("ok.mp4")

        hooks = self._hooks(render)
        hooks["check_fn"] = lambda path, prompt="", clip_id="": {"status": "fail",
                                                                 "reasons": ["4:3 frame expected"]}
        result = orch.evaluate_live_candidate(self.example, self.pred, **hooks)
        self.assertEqual(rendered, [True])
        self.assertEqual(result["mipro"], 0.02)
        self.assertIn("4:3 frame expected", result["error"])
        self.assertNotIn("skipped GPU", result["error"])
        self.assertEqual(json.loads(result["feedback"])["video_path"], "ok.mp4")
        names = [item[0] if isinstance(item, tuple) else item for item in self.order]
        self.assertNotIn("vlm", names)

    def test_empty_prompt_skips_gpu(self):
        pred = SimpleNamespace(positive_prompt="", cfg_scale=5, denoise=0.8, step_count=20)
        result = orch.evaluate_live_candidate(
            self.example, pred,
            render_fn=lambda *a, **k: self.fail("must not render"),
            prepare_comfy=lambda **k: self.fail("must not take VRAM"),
        )
        # An empty student prompt is a prompt/format failure (0.02), not generic 0.01.
        self.assertEqual(result["mipro"], 0.02)
        self.assertIn("skipped GPU", result["error"])

    def test_fail_row_records_current_start_and_video_prompts(self):
        pred = SimpleNamespace(
            start_prompt="Atlantic cliffs at golden hour, basalt, white spray.",
            video_prompt="Aerial drone push-in toward the cliffs, steady pace.",
            negative_prompt="watermark",
            cfg_scale=5.5,
            step_count=28,
        )

        def render(example, pred, hparams):
            raise TimeoutError("ComfyUI job dropped from queue")

        result = orch.evaluate_live_candidate(self.example, pred, **self._hooks(render))
        feedback = json.loads(result["feedback"])
        self.assertEqual(feedback["start_prompt"], pred.start_prompt)
        self.assertEqual(feedback["video_prompt"], pred.video_prompt)
        self.assertNotIn("positive_prompt", feedback)

    def test_fail_row_falls_back_to_legacy_positive_prompt(self):
        def render(example, pred, hparams):
            raise TimeoutError("ComfyUI job dropped from queue")

        result = orch.evaluate_live_candidate(self.example, self.pred, **self._hooks(render))
        feedback = json.loads(result["feedback"])
        self.assertEqual(feedback["start_prompt"], self.pred.positive_prompt)
        self.assertEqual(feedback["video_prompt"], self.pred.positive_prompt)

    def test_empty_current_prompts_fail_row_names_fields(self):
        pred = SimpleNamespace(start_prompt="cliffs", video_prompt="", cfg_scale=5, step_count=20)
        result = orch.evaluate_live_candidate(
            self.example, pred,
            render_fn=lambda *a, **k: self.fail("must not render"),
            prepare_comfy=lambda **k: self.fail("must not take VRAM"),
        )
        self.assertEqual(result["mipro"], 0.02)
        feedback = result["feedback_obj"]
        self.assertEqual(feedback["start_prompt"], "cliffs")
        self.assertEqual(feedback["video_prompt"], "")

    def test_success_row_records_current_start_and_video_prompts(self):
        pred = SimpleNamespace(
            start_prompt="Atlantic cliffs at golden hour, basalt, white spray.",
            video_prompt="Aerial drone push-in toward the cliffs, steady pace.",
            negative_prompt="watermark",
            cfg_scale=5.5,
            step_count=28,
        )
        result = orch.evaluate_live_candidate(
            self.example, pred, **self._hooks(lambda *a, **k: Path("ok.mp4"))
        )
        feedback = json.loads(result["feedback"])
        self.assertIsNotNone(feedback["scores"])
        self.assertEqual(feedback["start_prompt"], pred.start_prompt)
        self.assertEqual(feedback["video_prompt"], pred.video_prompt)


class MechanicalGateTests(unittest.TestCase):
    def test_generalized_clip_skips_backrooms_tokens(self):
        example = SimpleNamespace(
            id="GVD-D01",
            category="drone_high_kinematics",
            duration_seconds=8.0,
        )
        pred = SimpleNamespace(
            positive_prompt="A cinematic drone shot of Atlantic cliffs at golden hour.",
        )
        result = orch.mechanical_director_gate(example, pred)
        self.assertEqual(result["status"], "pass", result["reasons"])

    def test_backrooms_accepts_relaxed_keywords(self):
        example = SimpleNamespace(id="GVD-B01", category="backrooms", duration_seconds=8.0)
        pred = SimpleNamespace(
            positive_prompt=(
                "A handheld first-person camcorder walk down a damp yellow hallway "
                "with fluorescent rectangles."
            ),
        )
        result = orch.mechanical_director_gate(example, pred)
        self.assertEqual(result["status"], "pass", result["reasons"])

    def test_backrooms_rejects_without_camera_or_motion(self):
        example = SimpleNamespace(id="GVD-B01", category="backrooms", duration_seconds=8.0)
        pred = SimpleNamespace(positive_prompt="A still photograph of yellow wallpaper.")
        result = orch.mechanical_director_gate(example, pred)
        self.assertEqual(result["status"], "fail")
        blob = " ".join(result["reasons"])
        self.assertIn("camera keyword", blob)
        self.assertIn("motion keyword", blob)

    def test_current_fields_pass_without_positive_prompt(self):
        example = SimpleNamespace(id="GVD-D01", category="drone_high_kinematics", duration_seconds=8.0)
        pred = SimpleNamespace(
            start_prompt="Atlantic cliffs at golden hour.",
            video_prompt="Aerial drone push-in toward the cliffs.",
        )
        result = orch.mechanical_director_gate(example, pred)
        self.assertEqual(result["status"], "pass", result["reasons"])

    def test_missing_video_prompt_is_named(self):
        example = SimpleNamespace(id="GVD-D01", category="drone_high_kinematics", duration_seconds=8.0)
        pred = SimpleNamespace(start_prompt="Atlantic cliffs at golden hour.", video_prompt="")
        result = orch.mechanical_director_gate(example, pred)
        self.assertEqual(result["status"], "fail")
        self.assertIn("video_prompt is empty", result["reasons"])
        self.assertNotIn("positive_prompt is empty", " ".join(result["reasons"]))

    def test_backrooms_reads_camera_and_motion_from_video_prompt(self):
        example = SimpleNamespace(id="GVD-B01", category="backrooms", duration_seconds=8.0)
        pred = SimpleNamespace(
            start_prompt="1990s VHS still of a damp yellow wallpapered hallway.",
            video_prompt="Handheld camcorder walk forward down the hallway.",
        )
        result = orch.mechanical_director_gate(example, pred)
        self.assertEqual(result["status"], "pass", result["reasons"])


class RelaxedMotionTableTests(unittest.TestCase):
    """2026-09-26e: broadened Backrooms motion vocabulary with a real floor."""

    def _gate(self, video_prompt):
        example = SimpleNamespace(id="GVD-B01", category="backrooms", duration_seconds=8.0)
        pred = SimpleNamespace(
            start_prompt="1990s VHS still of a damp yellow wallpapered hallway.",
            video_prompt=video_prompt)
        return orch.mechanical_director_gate(example, pred)

    def test_row_265_wording_passes(self):
        result = self._gate(
            "The handheld camcorder gradually moves along the hallway, panning slowly.")
        self.assertEqual(result["status"], "pass", result["reasons"])

    def test_pan_tilt_turn_count_as_motion(self):
        for text in (
            "Handheld camcorder pans across the yellow wall.",
            "POV camcorder tilts up to the fluorescent panels.",
            "First-person camcorder turns the corner into the next room.",
            "Handheld camcorder drifting down the corridor.",
        ):
            result = self._gate(text)
            self.assertEqual(result["status"], "pass", (text, result["reasons"]))

    def test_negated_motion_does_not_count(self):
        for text in (
            "Handheld camcorder locked off on the wallpaper; the camera does not move.",
            "POV camcorder with no panning, static on the doorway.",
            "Handheld camcorder, never moving, fixed on the carpet.",
        ):
            result = self._gate(text)
            self.assertEqual(result["status"], "fail", text)
            self.assertIn("motion keyword", " ".join(result["reasons"]))

    def test_substrings_do_not_count(self):
        # "remove" / "improvement" contain "move"; "span" contains "pan".
        result = self._gate("Handheld camcorder; remove the improvement across the span.")
        self.assertEqual(result["status"], "fail")
        self.assertIn("motion keyword", " ".join(result["reasons"]))

    def test_camera_keyword_still_required(self):
        result = self._gate("The camera gradually moves along the hallway, panning slowly.")
        self.assertEqual(result["status"], "fail")
        blob = " ".join(result["reasons"])
        self.assertIn("camera keyword", blob)
        self.assertNotIn("motion keyword", blob)

    def test_instruction_echo_floor_still_applies(self):
        result = self._gate("Describe how the camera and subject move over this clip")
        self.assertEqual(result["status"], "fail")
        self.assertIn("video_prompt repeats the director instructions", result["reasons"])


class HparamFallbackTests(unittest.TestCase):
    def test_missing_hparams_use_safe_fallbacks(self):
        pred = SimpleNamespace(positive_prompt="enough text here")
        parsed, notes = orch.parse_director_hparams(pred)
        self.assertEqual(parsed["cfg_scale"], 5.5)
        self.assertEqual(parsed["denoise"], 1.0)  # fallback clamped to DENOISE_RANGE
        self.assertEqual(parsed["step_count"], 28.0)
        # denoise is not in the current signature, so its absence is not noted.
        self.assertEqual(len(notes), 2)
        self.assertFalse(any("denoise" in note for note in notes))

    def test_current_signature_prediction_does_not_warn_about_denoise(self):
        import warnings

        pred = SimpleNamespace(
            start_prompt="Atlantic cliffs at golden hour.",
            video_prompt="Drone push-in toward the cliffs.",
            cfg_scale=5.5,
            step_count=28,
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            parsed, notes = orch.parse_director_hparams(pred)
        self.assertEqual(notes, [])
        self.assertEqual([str(w.message) for w in caught], [])
        self.assertEqual(set(parsed), {"cfg_scale", "denoise", "step_count"})
        self.assertEqual(parsed["denoise"], 1.0)

    def test_legacy_garbage_denoise_still_noted(self):
        pred = SimpleNamespace(cfg_scale=5.5, denoise="nope", step_count=28)
        parsed, notes = orch.parse_director_hparams(pred)
        self.assertEqual(parsed["denoise"], 1.0)
        self.assertEqual(len(notes), 1)
        self.assertIn("denoise", notes[0])

    def test_garbage_hparams_use_safe_fallbacks(self):
        pred = SimpleNamespace(cfg_scale="nope", denoise="", step_count=None)
        parsed, notes = orch.parse_director_hparams(pred)
        self.assertEqual(parsed["cfg_scale"], 5.5)
        self.assertEqual(parsed["denoise"], 1.0)  # fallback clamped to DENOISE_RANGE
        self.assertEqual(parsed["step_count"], 28.0)
        self.assertTrue(notes)

    def test_json_adapter_defaults_missing_prompts_to_empty(self):
        import json as _json
        import warnings

        adapter = orch.director_json_adapter()
        signature = orch.gvd.director_signature_class()
        completion = _json.dumps({
            "start_prompt": "Atlantic cliffs at golden hour.",
            "negative_prompt": "blur",
            "cfg_scale": 5.5,
            "step_count": 28,
        })
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fields = adapter.parse(signature, completion)
        self.assertEqual(fields["video_prompt"], "")
        self.assertEqual(fields["start_prompt"], "Atlantic cliffs at golden hour.")
        self.assertNotIn("denoise", fields)
        self.assertEqual([str(w.message) for w in caught], [])
        example = SimpleNamespace(category="drone_high_kinematics", duration_seconds=8.0)
        result = orch.mechanical_director_gate(example, SimpleNamespace(**fields))
        self.assertIn("video_prompt is empty", result["reasons"])

    def test_student_token_budget_is_raised(self):
        self.assertGreaterEqual(orch.STUDENT_MAX_TOKENS, 4096)

    def test_compile_refuses_without_flag(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = orch.main([])
        self.assertEqual(code, 2)
        self.assertIn("Refusing to start GPU work", buf.getvalue())
        self.assertNotIn("--mock", buf.getvalue())


class MiniMaxGraphHparamTests(unittest.TestCase):
    def test_build_wan_graph_is_retired(self):
        with self.assertRaisesRegex(RuntimeError, "build_minimax_graph"):
            orch.build_wan_graph(
                "start.png", "end.png", "prompt", "watermark, morph",
                "gvd", cfg_scale=6.25, denoise=0.85, step_count=27.4,
            )

    def test_build_minimax_graph_patches_flux_sampler_hparams(self):
        graph = orch.build_minimax_graph(
            "A still of Atlantic cliffs at golden hour.",
            "Slow aerial push-in toward the cliffs.",
            {"cfg_scale": 6.25, "denoise": 0.2, "step_count": 27.4},
            negative="watermark, morph",
            enable_f5_voice=False,
        )
        sampler = graph["3"]
        self.assertEqual(sampler["class_type"], "KSampler")
        self.assertEqual(sampler["inputs"]["cfg"], 6.25)
        self.assertEqual(sampler["inputs"]["steps"], 27)
        self.assertEqual(sampler["inputs"]["denoise"], 1.0)
        self.assertEqual(graph["6"]["inputs"]["text"],
                         "A still of Atlantic cliffs at golden hour.")

    def test_flux_hparams_do_not_reach_the_minimax_scheduler(self):
        # Node 35 (MiniMax BasicScheduler) ran at the FLUX step_count on 143 of
        # 144 renders through 2026-09-23. It now takes the fixed H3 step count.
        graph = orch.build_minimax_graph(
            "A still.", "Slow push-in.",
            {"cfg_scale": 6.25, "denoise": 1.0, "step_count": 27.4},
            enable_f5_voice=False,
        )
        self.assertEqual(graph["35"]["class_type"], "BasicScheduler")
        self.assertEqual(graph["35"]["inputs"]["steps"], orch.MINIMAX_H3_STEPS)
        self.assertEqual(orch.MINIMAX_H3_STEPS, 20)
        self.assertEqual(graph["3"]["inputs"]["steps"], 27)

    def test_minimax_step_count_is_an_explicit_override(self):
        graph = orch.build_minimax_graph(
            "A still.", "Slow push-in.",
            {"cfg_scale": 5.5, "step_count": 20, "minimax_step_count": 24},
            enable_f5_voice=False,
        )
        self.assertEqual(graph["35"]["inputs"]["steps"], 24)
        self.assertEqual(graph["3"]["inputs"]["steps"], 20)


class PromptLabelEchoTests(unittest.TestCase):
    def test_strips_labels_seen_on_the_2026_09_24_verify_render(self):
        self.assertEqual(
            orch.strip_prompt_label("FLUX.1 T2I: Cinematic drone flight over the ocean."),
            "Cinematic drone flight over the ocean.")
        self.assertEqual(
            orch.strip_prompt_label("MiniMax I2V: Drone captures an aerial view."),
            "Drone captures an aerial view.")

    def test_strips_field_names_and_stacked_labels(self):
        for raw in ("start_prompt: A basalt cliff.",
                    "Start Prompt (FLUX.1 T2I): A basalt cliff.",
                    "video_prompt: FLUX: A basalt cliff."):
            self.assertIn(orch.strip_prompt_label(raw),
                          {"A basalt cliff."}, raw)

    def test_leaves_real_prompts_alone(self):
        for raw in ("Flux capacitor glowing on a workbench.",
                    "MiniMax-style slow push-in toward the cliffs.",
                    "A sign reading: EXIT above the door."):
            self.assertEqual(orch.strip_prompt_label(raw), raw)

    def test_resolvers_strip_before_render(self):
        pred = SimpleNamespace(start_prompt="FLUX.1 T2I: Cliffs.",
                               video_prompt="MiniMax I2V: Push in.")
        self.assertEqual(orch._director_start_prompt(SimpleNamespace(), pred), "Cliffs.")
        self.assertEqual(orch._director_motion_prompt(pred), "Push in.")


class DirectorAdapterTests(unittest.TestCase):
    def test_dict_and_range_hparams_are_coerced_not_crashed(self):
        # 2026-09-24: the student emitted {"cfg_scale": {"value": "4.0"}};
        # the adapter validated the raw dict as float and raised.
        import generalized_video_director as gvd
        adapter = orch.director_json_adapter()
        signature = gvd.director_signature_class()
        out = adapter.parse(signature, json.dumps({
            "start_prompt": "Cliffs.", "video_prompt": "Push in.",
            "negative_prompt": "text",
            "cfg_scale": {"value": "4.0"}, "step_count": "24-32",
        }))
        self.assertEqual(out["cfg_scale"], 4.0)
        self.assertEqual(out["step_count"], 28.0)


class InstructionEchoTests(unittest.TestCase):
    def test_regurgitated_description_is_flagged_real_prompts_are_not(self):
        self.assertTrue(orch.instruction_echo(
            "Describe the opening still of this clip in your own words."))
        self.assertFalse(orch.instruction_echo(
            "Cinematic drone flight over the ocean toward black basalt cliffs."))

    def test_echo_skips_gpu_with_prompt_format_penalty(self):
        example = SimpleNamespace(id="GVD-D01", category="drone_high_kinematics",
                                  user_intent="cliffs")
        pred = SimpleNamespace(
            start_prompt="Describe the opening still of this clip in your own words",
            video_prompt="Slow aerial push-in toward the cliffs.",
            cfg_scale=4.0, step_count=24.0)
        result = orch.evaluate_live_candidate(
            example, pred,
            render_fn=lambda *a, **k: self.fail("must not render"),
            prepare_comfy=lambda **k: self.fail("must not take VRAM"),
        )
        self.assertIn("instruction echo in start_prompt", result["error"])
        self.assertEqual(result["mipro"], 0.02)

    def test_mechanical_gate_names_the_echoed_field(self):
        example = SimpleNamespace(id="GVD-D01", category="drone_high_kinematics",
                                  duration_seconds=8.0)
        pred = SimpleNamespace(
            start_prompt="Cliffs at golden hour.",
            video_prompt="Describe how the camera and subject move over this clip")
        result = orch.mechanical_director_gate(example, pred)
        self.assertEqual(result["status"], "fail")
        self.assertIn("video_prompt repeats the director instructions", result["reasons"])

    def test_bare_versioned_model_tokens_and_frame_labels_are_stripped(self):
        for raw, want in (("FLUX.1 handheld camcorder walk.", "handheld camcorder walk."),
                          ("MiniMax I2V handheld walk.", "handheld walk."),
                          ("Start frame: A honeybee.", "A honeybee."),
                          ("Video prompt: Follows the bee.", "Follows the bee."),
                          ("FLUX.1 still prompt: A cliff.", "A cliff.")):
            self.assertEqual(orch.strip_prompt_label(raw), want, raw)

    def test_adapter_unwraps_object_valued_prompts(self):
        import generalized_video_director as gvd
        out = orch.director_json_adapter().parse(
            gvd.director_signature_class(), json.dumps({
                "start_prompt": {"description": "A damp yellow hallway."},
                "video_prompt": {"text": "Handheld walk forward."},
                "negative_prompt": "text", "cfg_scale": 5.0, "step_count": 24,
            }))
        self.assertEqual(out["start_prompt"], "A damp yellow hallway.")
        self.assertEqual(out["video_prompt"], "Handheld walk forward.")


class StillArchiveTests(unittest.TestCase):
    def test_archive_flf_stills_copies_start_and_end(self):
        import tempfile
        from dispatcher import archive_flf_stills

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            dest = Path(tmp) / "debug"
            src.mkdir()
            start = src / "start.png"
            end = src / "end.png"
            start.write_bytes(b"\x89PNG\r\nstart")
            end.write_bytes(b"\x89PNG\r\nend")
            copied = archive_flf_stills(
                start, end, clip_id="GVD-D01", key="abc123", dest_dir=dest,
            )
            self.assertTrue(Path(copied["start"]).is_file())
            self.assertTrue(Path(copied["end"]).is_file())
            self.assertEqual(Path(copied["start"]).read_bytes(), start.read_bytes())
            self.assertTrue((dest / "stills.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
