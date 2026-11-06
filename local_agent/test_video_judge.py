"""Fault-checked GVD judge: CPU detector, check parsing, caps, orchestrator wiring."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import dspy_orchestrator as orch
import gvd_judge_eval
import video_judge as vj
from media_accuracy_gate import parse_video_director_scores


def _scene(seed: int, n: int, level: float = 120.0) -> np.ndarray:
    """n frames of one textured 'shot' drifting slowly (camera pan)."""
    rng = np.random.default_rng(seed)
    tint = rng.uniform(0.2, 1.0, size=3).astype(np.float32)   # each shot has its own palette
    base = rng.uniform(0, 255, size=(36, 64 + n, 3)).astype(np.float32) * tint
    base = base * (level / base.mean())
    return np.stack([np.clip(base[:, t:t + 64], 0, 255) for t in range(n)])


def _checks(**overrides) -> dict:
    checks = {
        "requested_subject_visible": "yes",
        "same_place_in_all_frames": "yes",
        "abrupt_cut_between_frames": "no",
        "same_time_of_day_in_all_frames": "yes",
        "subject_count_matches_brief": "yes",
        "visual_medium_matches_brief": "yes",
        "text_or_logo_visible": "no",
        "camera_or_operator_visible": "no",
        "constraint_broken": "none",
    }
    checks.update(overrides)
    return checks


def _vlm_json(checks: dict, scores=(0.85, 0.95, 0.90)) -> str:
    return json.dumps({
        "frames": ["F1: a", "F2: b"],
        "checks": checks,
        "text_video_alignment": scores[0],
        "temporal_consistency": scores[1],
        "aesthetic_quality": scores[2],
        "rationale": {"text_video_alignment": "x", "temporal_consistency": "y", "aesthetic_quality": "z"},
    })


def _parsed(checks: dict, scores=(0.85, 0.95, 0.90)) -> dict:
    return parse_video_director_scores(_vlm_json(checks, scores), "p",
                                       model=orch.EXACT_VLM_MODEL, runtime=orch.EXACT_VLM_RUNTIME)


class FrameSignalTests(unittest.TestCase):
    def test_hard_cut_between_two_shots_is_detected(self):
        frames = np.concatenate([_scene(1, 48), _scene(2, 48)])
        signals = vj.frame_signals(frames, fps=24.0)
        self.assertEqual(signals["hard_cuts_s"], [2.0])
        self.assertEqual(signals["blank_fraction"], 0.0)

    def test_continuous_pan_has_no_cut(self):
        self.assertEqual(vj.frame_signals(_scene(3, 96))["hard_cuts_s"], [])

    def test_first_two_steps_are_ignored(self):
        # MiniMax I2V pops from the conditioning still on frame 0 -> 1.
        frames = np.concatenate([_scene(4, 1), _scene(5, 95)])
        self.assertEqual(vj.frame_signals(frames)["hard_cuts_s"], [])

    def test_brief_flash_that_returns_is_not_a_cut(self):
        shot = _scene(6, 96)
        shot[40:43] = _scene(7, 3)  # three foreign frames, then the shot resumes
        self.assertEqual(vj.frame_signals(shot)["hard_cuts_s"], [])

    def test_lights_off_then_on_is_not_a_cut(self):
        shot = _scene(8, 96)
        shot[30:60] *= 0.08       # ~1.2 s near-black, like c017's fluorescent flicker
        signals = vj.frame_signals(shot)
        self.assertEqual(signals["hard_cuts_s"], [])
        self.assertAlmostEqual(signals["blank_fraction"], 30 / 96, places=2)

    def test_change_times_pick_largest_steps_away_from_uniform_frames(self):
        frames = np.concatenate([_scene(10, 48), _scene(11, 48), _scene(12, 48)])
        times = vj.change_times(frames, 24.0, k=2, avoid_s=[0.0])
        self.assertEqual(times, [2.0, 4.0])
        # A uniform frame already at the cut: the next-largest step is used instead.
        self.assertNotIn(2.0, vj.change_times(frames, 24.0, k=1, avoid_s=[2.1]))
        self.assertEqual(vj.change_times(frames[:3], 24.0), [])

    def test_mostly_black_clip_reports_blank_fraction(self):
        frames = _scene(9, 96, level=6.0)
        self.assertEqual(vj.frame_signals(frames)["blank_fraction"], 1.0)


def _static(seed: int, n: int, level: float = 120.0) -> np.ndarray:
    """n identical frames of one textured picture (a locked-off shot)."""
    return np.repeat(_scene(seed, 1, level=level), n, axis=0).copy()


class LightingDipTests(unittest.TestCase):
    """2026-09-25 (CHANGELOG 2026-09-25h). c018 (good, held-out): lights out
    at 1.0 s, back dim (~20 luma) at 1.5 s, full at 1.83 s. That last step is
    dim -> lit on the same hallway: not near-black, histogram never returns,
    adjacent-frame correlation 0.63 (the panels were off), so every flash rule
    missed it and the detector called a cut. The lit picture on the far side
    of the dip matched the lit side at 0.82-0.91; every labeled real cut is
    <= 0.56 on the same comparison."""

    @staticmethod
    def _dip_clip(dark_frames: int, start: int = 40) -> np.ndarray:
        shot = _static(20, 96)
        # Panels off: the picture is dim (~50 luma, not near-black) and lit by
        # a different pattern, so it does not correlate with the lit frames.
        other = _static(21, 96, level=40.0)
        shot[start:start + dark_frames] = 0.12 * shot[start:start + dark_frames] + 0.88 * other[start:start + dark_frames]
        return shot

    def test_dim_stretch_on_the_same_picture_is_not_a_cut(self):
        clip = self._dip_clip(21)
        luma = clip.mean(-1).reshape(len(clip), -1).mean(1)
        self.assertGreater(luma[45], vj.BLANK_MEAN_LUMA)          # the near-black rule does not apply
        self.assertLess(luma[45], vj.CUT_DIP_FRACTION * luma[10])  # but it is a dip
        self.assertEqual(vj.frame_signals(clip)["hard_cuts_s"], [])
        # Without the dip rule both edges of the stretch read as cuts (the
        # flash rules look 12 frames for a histogram return; the dip is 21).
        with patch.object(vj, "CUT_DIP_MAX_FRAMES", 10):
            self.assertEqual(len(vj.frame_signals(clip)["hard_cuts_s"]), 2)

    def test_cut_into_a_dark_scene_that_brightens_is_still_a_cut(self):
        # M03 371a: a real cut lands on a 17-luma frame that brightens over
        # the next half second. The far side of that "dip" is a different
        # picture, so the dip rule does not rescue it.
        a = _static(1, 48)   # the two shots of test_hard_cut_between_two_shots_is_detected
        b = _static(2, 48)
        ramp = np.linspace(0.15, 1.0, 12)
        b[:12] *= ramp[:, None, None, None]
        clip = np.concatenate([a, b])
        self.assertEqual(vj.frame_signals(clip, fps=24.0)["hard_cuts_s"], [2.0])

    def test_dip_rule_needs_a_real_dip(self):
        # Plain cut between two lit shots: no dark side, nothing to walk over.
        gray = np.concatenate([_static(32, 48), _static(33, 48)]).mean(-1)
        luma = gray.reshape(96, -1).mean(1)
        self.assertFalse(vj._dip_returns_same_picture(gray, luma, 47))

    def test_dark_spans_mark_near_black_and_dim_runs(self):
        # c018's shape: lit ~80, lights out (3), back dim (20), lit again.
        luma = np.array([80.0] * 10 + [3.0] * 5 + [20.0] * 6 + [80.0] * 10)
        spans = vj.dark_spans(luma, 24.0)
        self.assertEqual(spans, [[round(11 / 24, 2), round(15 / 24, 2), "near-black"],
                                 [round(16 / 24, 2), round(21 / 24, 2), "dim"]])
        self.assertEqual(vj.dark_spans(np.array([80.0] * 8), 24.0), [])
        self.assertEqual(vj.frame_signals(self._dip_clip(21))["dark_spans_s"],
                         [[round(41 / 24, 2), round(61 / 24, 2), "dim"]])

    def test_user_prompt_marks_sampled_frames_inside_a_dip(self):
        signals = {"hard_cuts_s": [], "blank_fraction": 0.13,
                   "dark_spans_s": [[0.46, 1.75, "near-black"], [1.79, 1.96, "dim"]]}
        prompt = vj.build_judge_user_prompt(brief="hallway, fluorescent flicker", constraints="",
                                            frame_times=[0.2, 1.59, 1.9, 2.98], signals=signals)
        self.assertIn("F2=1.6s (near-black: lights down in this frame, measured)", prompt)
        self.assertIn("F3=1.9s (dim: lights down in this frame, measured)", prompt)
        self.assertIn("F1=0.2s, ", prompt)
        self.assertIn("judge place, cuts and the subject from the lit frames", prompt)
        # No dip, or no signals: the old prompt, byte for byte.
        plain = "BRIEF: b\nCONSTRAINTS: c\nFRAMES (1, in time order): F1=0.2s"
        self.assertEqual(vj.build_judge_user_prompt(brief="b", constraints="c", frame_times=[0.2]), plain)
        self.assertEqual(vj.build_judge_user_prompt(brief="b", constraints="c", frame_times=[0.2],
                                                    signals={"dark_spans_s": []}), plain)

    def test_orchestrator_passes_dark_spans_to_the_user_prompt(self):
        seen = {}

        def judge(frames, prompt, system_prompt=None):
            seen["prompt"] = prompt
            return _parsed(_checks())

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"x")
            orch.judge_rendered_clip(
                {"id": "c004", "user_intent": "hallway, fluorescent flicker"}, video,
                start_prompt="s", motion_prompt="m",
                extract=lambda p: [Path("x_00_0.200s.png"), Path("x_01_1.590s.png")], judge=judge,
                signals_fn=lambda p: {"hard_cuts_s": [], "blank_fraction": 0.13,
                                      "dark_spans_s": [[0.46, 1.75, "near-black"]]})
        self.assertIn("F2=1.6s (near-black", seen["prompt"])
        self.assertNotIn("F1=0.2s (", seen["prompt"])

    def test_prompt_tells_vlm_a_requested_flicker_or_turn_is_not_a_cut(self):
        # c004: a requested fluorescent flicker read as "a different dark
        # hallway"; c038: a requested turn to the wall read as a cut.
        self.assertIn("Lighting and camera moves:", vj.VIDEO_JUDGE_SYSTEM_PROMPT)
        self.assertIn("never for the light level or the framing alone", vj.VIDEO_JUDGE_SYSTEM_PROMPT)


class CameraTurnTests(unittest.TestCase):
    """2026-09-25l. c038 (good, held-out): the brief's walk turns to face the
    wall; since 25g the VLM described F4-F8 as "close-up of wallpaper, no
    hallway" and answered cut / different place / subject absent. The measured
    estimator (camera_motion.py, 25c/e) reads that turn as pan-left at 0.46
    and 0.32 frame widths over the F3-F4 and F4-F5 gaps, so the user prompt
    now says so, the way dark_spans_s marks a lighting dip."""

    @staticmethod
    def _move(frame, camera, dx=0.0, dy=0.0, subject=False):
        return {"frame": frame, "start": float(frame - 2), "end": float(frame - 1), "camera": camera,
                "dx_frac": dx, "dy_frac": dy, "scale": 0.0, "response": 0.4, "pairs": 24,
                "low_response_pairs": 0, "subject_motion": subject}

    def test_measured_camera_moves_uses_the_gaps_between_sampled_frames(self):
        import camera_motion
        seen = {}

        def fake(video, windows, fps=None):
            seen["video"], seen["windows"] = video, windows
            return [{"frame": w["frame"], "start": w["start"], "end": w["end"], "camera": "pan-left",
                     "dx_frac": 0.3, "dy_frac": 0.0, "scale": 0.01, "response": 0.4, "coherence": 0.9,
                     "subject_excess_px": 0.1, "subject_motion": False, "pairs": 30,
                     "low_response_pairs": 0, "full_frame_camera": "pan-left"} for w in windows]

        with patch.object(camera_motion, "estimate_camera_motion", side_effect=fake) as est:
            moves = vj.measured_camera_moves(Path("clip.mp4"), [0.2, 1.6, 3.0])
            self.assertEqual(est.call_count, 1)
            self.assertEqual(vj.measured_camera_moves(Path("clip.mp4"), [0.2]), [])
            self.assertEqual(vj.measured_camera_moves(Path("clip.mp4"), None), [])
            self.assertEqual(est.call_count, 1)   # nothing to measure with one frame
        self.assertEqual(seen["windows"], [{"frame": 2, "start": 0.2, "end": 1.6},
                                           {"frame": 3, "start": 1.6, "end": 3.0}])
        self.assertEqual([m["frame"] for m in moves], [2, 3])
        self.assertEqual(moves[0]["camera"], "pan-left")
        self.assertNotIn("coherence", moves[0])   # compact record for the feedback row

    def test_only_a_rigid_turn_of_at_least_turn_min_frac_is_a_turn(self):
        moves = [self._move(2, "push-in", dx=0.5), self._move(3, "pan-left", dx=0.10),
                 self._move(4, "pan-left", dx=0.46), self._move(5, "pan-left", dx=0.32),
                 self._move(6, "pan-right", dx=-0.27, subject=True), self._move(7, "tilt-up", dy=0.24),
                 self._move(8, "uncertain", dx=0.9)]
        self.assertEqual(vj.measured_turns(moves), {4: "turned left", 5: "turned left", 7: "tilted up"})
        self.assertEqual(vj.measured_turns(None), {})
        self.assertEqual(vj.measured_turns([]), {})
        # c038's turn (0.46, 0.32) is inside the gate; the 25c creek confounder
        # (water flowing down the frame, tilt-up at 0.13-0.15 per gap) is not.
        self.assertGreaterEqual(0.32, vj.TURN_MIN_FRAC)
        self.assertLess(0.15, vj.TURN_MIN_FRAC)

    def test_user_prompt_marks_the_later_frame_of_a_measured_turn(self):
        signals = {"hard_cuts_s": [], "blank_fraction": 0.0, "dark_spans_s": [],
                   "camera_moves": [self._move(2, "static"), self._move(3, "pan-left", dx=0.10),
                                    self._move(4, "pan-left", dx=0.46), self._move(5, "pan-left", dx=0.32),
                                    self._move(6, "push-in"), self._move(7, "push-in"), self._move(8, "push-in")]}
        times = [0.2, 1.59, 2.98, 4.37, 5.76, 7.14, 8.53, 9.92]
        prompt = vj.build_judge_user_prompt(brief="hallway walk, turns to the wall", constraints="",
                                            frame_times=times, signals=signals)
        self.assertIn("F4=4.4s (camera turned left between F3 and F4, measured)", prompt)
        self.assertIn("F5=5.8s (camera turned left between F4 and F5, measured)", prompt)
        self.assertIn("F2=1.6s, F3=3.0s, F4=", prompt)        # the 0.10 gap is below the gate
        self.assertIn("F6=7.1s, F7=8.5s, F8=9.9s", prompt)
        self.assertIn(vj.TURN_RULE, prompt)
        self.assertIn("only if the setting itself is somewhere else", vj.TURN_RULE)
        self.assertNotIn("lights down", prompt)
        # No rigid turn, or no measurement at all: the 25h prompt byte for byte.
        plain = vj.build_judge_user_prompt(brief="b", constraints="c", frame_times=[0.2, 1.6])
        self.assertEqual(plain, "BRIEF: b\nCONSTRAINTS: c\nFRAMES (2, in time order): F1=0.2s, F2=1.6s")
        for moves in ([], [self._move(2, "push-in", dx=0.9)], [self._move(2, "pan-left", dx=0.5, subject=True)],
                      [self._move(2, "uncertain")]):
            self.assertEqual(vj.build_judge_user_prompt(brief="b", constraints="c", frame_times=[0.2, 1.6],
                                                        signals={"camera_moves": moves}), plain)
        self.assertNotIn(vj.TURN_RULE, plain)

    def test_turn_and_dip_marks_share_a_frame(self):
        signals = {"dark_spans_s": [[4.3, 4.5, "dim"]], "camera_moves": [self._move(2, "pan-right", dx=-0.3)]}
        prompt = vj.build_judge_user_prompt(brief="b", constraints="", frame_times=[3.0, 4.4], signals=signals)
        self.assertIn("F2=4.4s (dim: lights down in this frame, measured; "
                      "camera turned right between F1 and F2, measured)", prompt)
        self.assertIn("judge place, cuts and the subject from the lit frames", prompt)
        self.assertIn(vj.TURN_RULE, prompt)

    def test_orchestrator_measures_turns_on_the_production_path_only(self):
        seen = {}

        def judge(frames, prompt, system_prompt=None):
            seen["prompt"] = prompt
            return _parsed(_checks())

        def extract(_p):
            return [Path("x_00_0.200s.png"), Path("x_01_1.590s.png"), Path("x_02_2.980s.png")]

        move = self._move(3, "pan-left", dx=0.46)
        example = {"id": "c038", "user_intent": "hallway walk, turns to the wall"}
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"x")
            # Production path: no injected signals, the detector and the estimator both run.
            with patch.object(vj, "detect_frame_faults",
                              return_value={"hard_cuts_s": [], "blank_fraction": 0.0, "dark_spans_s": []}), \
                    patch.object(vj, "measured_camera_moves", return_value=[move]) as measured:
                out = orch.judge_rendered_clip(example, video, start_prompt="s", motion_prompt="m",
                                               extract=extract, judge=judge)
            measured.assert_called_once_with(video, [0.2, 1.59, 2.98])
            self.assertIn("F3=3.0s (camera turned left between F2 and F3, measured)", seen["prompt"])
            self.assertIn(vj.TURN_RULE, seen["prompt"])
            self.assertEqual(out["signals"]["camera_moves"], [move])
            self.assertEqual(out["status"], "pass")
            # Canned CPU signals (the test hook): no measurement unless camera_fn is injected too.
            with patch.object(vj, "measured_camera_moves", return_value=[move]) as measured:
                out = orch.judge_rendered_clip(example, video, start_prompt="s", motion_prompt="m",
                                               extract=extract, judge=judge,
                                               signals_fn=lambda p: {"hard_cuts_s": [], "blank_fraction": 0.0})
            measured.assert_not_called()
            self.assertNotIn("camera turned", seen["prompt"])
            self.assertNotIn("camera_moves", out["signals"])
            out = orch.judge_rendered_clip(example, video, start_prompt="s", motion_prompt="m",
                                           extract=extract, judge=judge,
                                           signals_fn=lambda p: {"hard_cuts_s": [], "blank_fraction": 0.0},
                                           camera_fn=lambda p, t: [move])
            self.assertIn("camera turned left between F2 and F3", seen["prompt"])
            self.assertEqual(out["signals"]["camera_moves"], [move])
            # A failing estimator is skipped, never a failed judgement, and the prompt is the plain one.
            with patch.object(vj, "detect_frame_faults", return_value={"hard_cuts_s": [], "blank_fraction": 0.0}), \
                    patch.object(vj, "measured_camera_moves", side_effect=ValueError("ffmpeg decoded no frames")):
                out = orch.judge_rendered_clip(example, video, start_prompt="s", motion_prompt="m",
                                               extract=extract, judge=judge)
            self.assertEqual(out["status"], "pass")
            self.assertNotIn("camera_moves", out["signals"])
            self.assertNotIn("measured", seen["prompt"])

    def test_live_metric_feedback_row_carries_the_measured_moves(self):
        move = self._move(2, "pan-left", dx=0.46)
        example = {"id": "GVD-M03", "category": "macro_nature", "user_intent": "creek"}
        pred = {"start_prompt": "a creek over mossy stones", "video_prompt": "slow drift over the water",
                "cfg_scale": "4", "denoise": "1.0", "step_count": "24"}
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "ok.mp4"
            video.write_bytes(b"x")
            result = orch.evaluate_live_candidate(
                example, pred, render_fn=lambda example, pred, hparams: video,
                vlm_fn=lambda f, p, system_prompt=None: _parsed(_checks()),
                extract_fn=lambda p: [Path("x_00_0.200s.png"), Path("x_01_1.590s.png")],
                check_fn=lambda *a: {"status": "pass", "reasons": []},
                prepare_comfy=lambda **k: None, release_comfy=lambda **k: None,
                prepare_vlm=lambda **k: None, release_vlm=lambda **k: None,
                signals_fn=lambda p: {"hard_cuts_s": [], "blank_fraction": 0.0, "dark_spans_s": []},
                camera_fn=lambda p, t: [move])
        feedback = json.loads(result["feedback"])
        self.assertEqual(feedback["signals"]["camera_moves"], [move])
        self.assertEqual(feedback["scores"]["temporal_consistency"], 0.95)   # a turn caps nothing


class CheckAndCapTests(unittest.TestCase):
    def test_normalize_checks_accepts_yes_no_variants_and_none(self):
        checks = vj.normalize_checks({"checks": {
            "requested_subject_visible": "No.", "abrupt_cut_between_frames": "YES - at F5",
            "same_place_in_all_frames": True, "constraint_broken": "None"}})
        self.assertEqual(checks["requested_subject_visible"], "no")
        self.assertEqual(checks["abrupt_cut_between_frames"], "yes")
        self.assertEqual(checks["same_place_in_all_frames"], "yes")
        self.assertIsNone(checks["constraint_broken"])
        self.assertIsNone(checks["text_or_logo_visible"])

    def test_clean_checks_leave_scores_alone(self):
        out = vj.apply_fault_caps(_parsed(_checks()), {"hard_cuts_s": [], "blank_fraction": 0.0})
        self.assertEqual(out["scores"], {"text_video_alignment": 0.85, "temporal_consistency": 0.95,
                                         "aesthetic_quality": 0.9})
        self.assertEqual(out["caps"], {})
        self.assertEqual(out["status"], "pass")

    def test_missing_subject_caps_alignment_and_recomputes_min_mean(self):
        out = vj.apply_fault_caps(_parsed(_checks(requested_subject_visible="no")), None)
        self.assertEqual(out["scores"]["text_video_alignment"], 0.20)
        self.assertEqual(out["minimum"], 0.20)
        self.assertAlmostEqual(out["mean"], round((0.20 + 0.95 + 0.90) / 3, 4))
        self.assertEqual(out["scores_vlm"]["text_video_alignment"], 0.85)

    def test_temporal_faults_cap_temporal(self):
        for key, value, cap in (("same_place_in_all_frames", "no", 0.30),
                                ("abrupt_cut_between_frames", "yes", 0.30),
                                ("same_time_of_day_in_all_frames", "no", 0.40)):
            out = vj.apply_fault_caps(_parsed(_checks(**{key: value})), None)
            self.assertEqual(out["scores"]["temporal_consistency"], cap, key)

    def test_detected_hard_cut_caps_temporal_even_if_vlm_says_no_cut(self):
        out = vj.apply_fault_caps(_parsed(_checks()), {"hard_cuts_s": [4.71], "blank_fraction": 0.0})
        self.assertEqual(out["scores"]["temporal_consistency"], 0.25)
        self.assertIn("4.71", out["caps"]["temporal_consistency"]["why"])

    def test_blank_frames_cap_aesthetic_only(self):
        out = vj.apply_fault_caps(_parsed(_checks()), {"hard_cuts_s": [], "blank_fraction": 0.5})
        self.assertEqual(out["scores"]["aesthetic_quality"], 0.20)
        self.assertEqual(out["scores"]["text_video_alignment"], 0.85)

    def test_text_cap_skipped_when_brief_asks_for_signage(self):
        parsed = _parsed(_checks(text_or_logo_visible="yes"))
        self.assertIn("text_video_alignment",
                      vj.apply_fault_caps(parsed, None, "a honeybee on a flower")["caps"])
        self.assertEqual(vj.apply_fault_caps(parsed, None, "neon kanji reflections")["caps"], {})

    def test_medium_cap_only_for_stylized_briefs(self):
        parsed = _parsed(_checks(visual_medium_matches_brief="no"))
        # Photoreal brief: the VLM called clean Backrooms hallways "3D renders".
        self.assertEqual(vj.apply_fault_caps(parsed, None, "yellow hallway, analog camcorder")["caps"], {})
        out = vj.apply_fault_caps(parsed, None, "A 16-bit pixel-art dungeon corridor")
        self.assertEqual(out["scores"]["text_video_alignment"], 0.30)
        out = vj.apply_fault_caps(parsed, None, "a wave", "Stay 2D woodblock for every frame")
        self.assertEqual(out["scores"]["text_video_alignment"], 0.30)

    def test_constraint_quote_needs_constraints_and_must_not_be_check_dump(self):
        dump = "requested_subject_visible: no, same_place_in_all_frames: no"
        for quote, constraints, capped in (
                ("no crowd", "Single skater, no crowd.", True),
                ("no crowd", "", False),                       # invented: brief has none
                (dump, "Single skater, no crowd.", False)):     # check answers dumped
            out = vj.apply_fault_caps(_parsed(_checks(constraint_broken=quote)), None, "skater", constraints)
            self.assertEqual("text_video_alignment" in out["caps"], capped, quote)

    def test_lowest_cap_wins(self):
        out = vj.apply_fault_caps(_parsed(_checks(requested_subject_visible="no",
                                                  subject_count_matches_brief="no")), None)
        self.assertEqual(out["scores"]["text_video_alignment"], 0.20)

    def test_unanswered_checks_are_reported_not_failed(self):
        parsed = parse_video_director_scores(
            json.dumps({"text_video_alignment": 0.8, "temporal_consistency": 0.8, "aesthetic_quality": 0.8}),
            "p", model=orch.EXACT_VLM_MODEL, runtime=orch.EXACT_VLM_RUNTIME)
        out = vj.apply_fault_caps(parsed, None)
        self.assertEqual(out["status"], "pass")
        self.assertTrue(any("unanswered" in r for r in out["reasons"]))

    def test_unparsed_verdict_passes_through(self):
        out = vj.apply_fault_caps({"status": "fail", "scores": None, "reasons": ["no json"]}, None)
        self.assertEqual(out["status"], "fail")
        self.assertIsNone(out["scores"])

    def test_frame_times_from_extract_eval_frames_names(self):
        names = [Path("clip_abc_00_0.160s.png"), Path("clip_abc_01_7.840s.png")]
        self.assertEqual(vj.frame_times_from_names(names), [0.16, 7.84])
        self.assertIsNone(vj.frame_times_from_names([Path("frame.png")]))


class CameraRigCheckTests(unittest.TestCase):
    """2026-09-25 (CHANGELOG 2026-09-25g): eighth check, the rig / drone /
    operator physically in the picture. 24q's wrong_viewpoint false passes
    (D02 614e, D01 3032, c036) all answered the seven older checks clean."""

    def test_check_key_is_asked_and_parsed(self):
        self.assertIn("camera_or_operator_visible", vj.CHECK_KEYS)
        self.assertIn('"camera_or_operator_visible": "yes" or "no"', vj.VIDEO_JUDGE_SYSTEM_PROMPT)
        # The question must separate "rig in the picture" from "static shot",
        # and answer from the pictures, not the brief's camera words (v3).
        self.assertIn("THROUGH a camera or drone", vj.VIDEO_JUDGE_SYSTEM_PROMPT)
        self.assertIn("not the shot being static", vj.VIDEO_JUDGE_SYSTEM_PROMPT)
        self.assertIn("answer from the pictures only, not from the BRIEF", vj.VIDEO_JUDGE_SYSTEM_PROMPT)
        checks = vj.normalize_checks({"checks": {"camera_or_operator_visible": "Yes - quadcopter in F1-F4"}})
        self.assertEqual(checks["camera_or_operator_visible"], "yes")
        self.assertIsNone(vj.normalize_checks({"checks": {}})["camera_or_operator_visible"])

    def test_rig_visible_caps_alignment_at_025(self):
        brief = "First-person FPV drone threads a dense pine canopy at high speed"
        out = vj.apply_fault_caps(_parsed(_checks(camera_or_operator_visible="yes")), None, brief,
                                  "Unbroken FPV take, no crash cut, no HUD")
        self.assertEqual(out["scores"]["text_video_alignment"], 0.25)
        self.assertEqual(out["minimum"], 0.25)
        self.assertAlmostEqual(out["mean"], round((0.25 + 0.95 + 0.90) / 3, 4))
        self.assertEqual(out["scores_vlm"]["text_video_alignment"], 0.85)
        self.assertIn("operator", out["caps"]["text_video_alignment"]["why"])
        self.assertEqual(out["scores"]["temporal_consistency"], 0.95)  # alignment only

    def test_rig_not_visible_leaves_scores_alone(self):
        out = vj.apply_fault_caps(_parsed(_checks(camera_or_operator_visible="no")), None,
                                  "handheld first-person camcorder walk", "Unlocked handheld camera")
        self.assertEqual(out["caps"], {})
        self.assertEqual(out["scores"]["text_video_alignment"], 0.85)

    def test_rig_cap_skipped_when_brief_asks_to_show_the_gear(self):
        # c013 (good): the actor inspects a tripod that is meant to be in shot.
        brief = ("The camera stands still in front of the tripod, looking at the legs. "
                 "He checks everything on the tripod (tripod legs, cable)")
        parsed = _parsed(_checks(camera_or_operator_visible="yes"))
        self.assertEqual(vj.apply_fault_caps(parsed, None, brief)["caps"], {})
        self.assertEqual(vj.apply_fault_caps(parsed, None, "He grips the camera body and looks confused")["caps"], {})
        # Mentions that describe the viewpoint or forbid the gear still bind.
        for brief, constraints in (
                ("Diegetic camcorder on a locked tripod, Mode A. Actor faces camera.", ""),
                ("actor looking through the camcorder lens, no visible camera body in frame", ""),
                ("A cinematic drone shot flies toward sheer cliffs", "Continuous aerial move, no tripod lock"),
                ("the actor steps in front of the camera and says hi", "")):
            out = vj.apply_fault_caps(parsed, None, brief, constraints)
            self.assertEqual(out["scores"]["text_video_alignment"], 0.25, brief)

    def test_rig_cap_loses_to_missing_subject(self):
        out = vj.apply_fault_caps(_parsed(_checks(camera_or_operator_visible="yes",
                                                  requested_subject_visible="no")), None, "a bee")
        self.assertEqual(out["scores"]["text_video_alignment"], 0.20)
        self.assertIn("subject", out["caps"]["text_video_alignment"]["why"])

    def test_unanswered_rig_check_is_reported(self):
        checks = _checks()
        del checks["camera_or_operator_visible"]
        out = vj.apply_fault_caps(_parsed(checks), None)
        self.assertEqual(out["status"], "pass")
        self.assertEqual(out["caps"], {})
        self.assertTrue(any("camera_or_operator_visible" in r for r in out["reasons"]))


class OrchestratorWiringTests(unittest.TestCase):
    def test_judge_sees_brief_and_constraints_not_student_prompts(self):
        seen = {}

        def judge(frames, prompt, system_prompt=None):
            seen.update(prompt=prompt, system=system_prompt)
            return _parsed(_checks(requested_subject_visible="no"))

        example = {"id": "GVD-M03", "user_intent": "A clear creek over mossy stones.",
                   "constraints": "no animals larger than an insect"}
        out = orch.judge_rendered_clip(
            example, Path("missing.mp4"), start_prompt="STUDENT START", motion_prompt="STUDENT MOTION",
            extract=lambda p: [Path("x_00_0.160s.png"), Path("x_01_4.000s.png")], judge=judge)
        self.assertIn("BRIEF: A clear creek over mossy stones.", seen["prompt"])
        self.assertIn("CONSTRAINTS: no animals larger than an insect", seen["prompt"])
        self.assertIn("F2=4.0s", seen["prompt"])
        self.assertNotIn("STUDENT", seen["prompt"])
        self.assertIn('"checks"', seen["system"])
        self.assertEqual(out["scores"]["text_video_alignment"], 0.20)
        self.assertIsNone(out["signals"])  # file missing: detector skipped, no crash

    def test_literal_mode_appends_override_to_new_system_prompt(self):
        seen = {}

        def judge(frames, prompt, system_prompt=None):
            seen["system"] = system_prompt
            return _parsed(_checks())

        orch.judge_rendered_clip({"id": "x", "user_intent": "bedroom", "literal_prompt": True},
                                 Path("missing.mp4"), start_prompt="s", motion_prompt="m",
                                 extract=lambda p: [], judge=judge)
        self.assertIn("CLIP-SPECIFIC OVERRIDE", seen["system"])
        self.assertTrue(seen["system"].startswith(vj.VIDEO_JUDGE_SYSTEM_PROMPT))

    def test_brief_falls_back_to_prompts_when_example_has_no_intent(self):
        seen = {}

        def judge(frames, prompt):  # legacy two-arg fake: TypeError fallback
            seen["prompt"] = prompt
            return _parsed(_checks())

        orch.judge_rendered_clip({"id": "c005"}, Path("missing.mp4"), start_prompt="yellow hallway",
                                 motion_prompt="slow walk", extract=lambda p: [], judge=judge)
        self.assertIn("BRIEF: yellow hallway slow walk", seen["prompt"])

    def test_signals_fn_runs_for_existing_file_and_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "clip.mp4"
            video.write_bytes(b"x")
            out = orch.judge_rendered_clip(
                {"id": "x", "user_intent": "y"}, video, start_prompt="s", motion_prompt="m",
                extract=lambda p: [], judge=lambda f, p, system_prompt=None: _parsed(_checks()),
                signals_fn=lambda p: {"hard_cuts_s": [1.0], "blank_fraction": 0.0})
        self.assertEqual(out["scores"]["temporal_consistency"], 0.25)

    def test_judge_vlm_call_sends_repeat_penalty_off(self):
        # 2026-09-24ae: llama_cpp_client now forwards repeat_penalty; the yes/no
        # checklist judge must run with it disabled (measured, results_v2c).
        import capabilities
        import media_tools
        seen = {}

        def fake_vision(frames, prompt, model, host, **kwargs):
            seen.update(kwargs)
            return json.dumps({"available": True, "model": model, "runtime": "llama.cpp",
                               "analysis": _vlm_json(_checks())})

        with patch.object(capabilities, "qwen25_vl_runtime_available", return_value=True),              patch.object(media_tools, "_run_vision_gpu", side_effect=fake_vision):
            parsed = orch.run_qwen_director_scores([Path("f.png")], "BRIEF: x", system_prompt="s")
        self.assertEqual(seen["repeat_penalty"], 1.0)
        self.assertTrue(seen["json_mode"])
        self.assertEqual(seen["num_predict"], 1536)
        self.assertEqual(parsed["status"], "pass")
        # 2026-09-25o: every judgement is a cold prefill (CHANGELOG 2026-09-25n:
        # the warm and cold answers differ on ~90% of clips and 4/79 verdicts).
        self.assertIs(vj.JUDGE_CACHE_PROMPT, False)
        self.assertIs(seen["cache_prompt"], False)

    def test_live_metric_feedback_records_checks_and_caps(self):
        def render(example, pred, hparams):
            return Path("ok.mp4")

        example = {"id": "GVD-M03", "category": "macro_nature", "user_intent": "creek"}
        pred = {"start_prompt": "a creek over mossy stones", "video_prompt": "slow drift over the water",
                "cfg_scale": "4", "denoise": "1.0", "step_count": "24"}
        result = orch.evaluate_live_candidate(
            example, pred, render_fn=render,
            vlm_fn=lambda f, p, system_prompt=None: _parsed(_checks(same_place_in_all_frames="no")),
            extract_fn=lambda p: [], check_fn=lambda *a: {"status": "pass", "reasons": []},
            prepare_comfy=lambda **k: None, release_comfy=lambda **k: None,
            prepare_vlm=lambda **k: None, release_vlm=lambda **k: None)
        feedback = json.loads(result["feedback"])
        self.assertEqual(feedback["checks"]["same_place_in_all_frames"], "no")
        self.assertEqual(feedback["scores"]["temporal_consistency"], 0.30)
        self.assertEqual(feedback["scores_vlm"]["temporal_consistency"], 0.95)
        self.assertAlmostEqual(result["mipro"], 0.7 * 0.30 + 0.3 * round((0.85 + 0.30 + 0.90) / 3, 4))


class JudgeRetryTests(unittest.TestCase):
    """2026-09-25k: one retry when the judge's answer has no scores."""

    def _run(self, answers, runtime="llama.cpp"):
        import capabilities
        import media_tools
        calls = []

        def fake_vision(frames, prompt, model, host, **kwargs):
            calls.append({"prompt": prompt, **kwargs})
            self.assertLessEqual(len(calls), len(answers), "more VLM calls than answers")
            return json.dumps({"available": True, "model": model, "runtime": runtime,
                               "analysis": answers[len(calls) - 1]})

        # HERE is patched so the debug dump (runtime/dspy_opt/gvd_vlm_raw.jsonl)
        # does not collect synthetic rows from every test run.
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(orch, "HERE", Path(tmp)), \
                patch.object(capabilities, "qwen25_vl_runtime_available", return_value=True), \
                patch.object(media_tools, "_run_vision_gpu", side_effect=fake_vision):
            parsed = orch.run_qwen_director_scores([Path("f.png")], "BRIEF: x", system_prompt="s")
            dumped = (Path(tmp) / "runtime" / "dspy_opt" / "gvd_vlm_raw.jsonl").read_text(encoding="utf-8")
        self.assertEqual(len(dumped.splitlines()), len(calls))
        return parsed, calls

    def test_retry_keeps_the_judge_sampler_and_says_nothing_about_repetition(self):
        # Measured 2026-09-25k (judge_eval_20260925/retry_arms*.jsonl): a
        # "never repeat a phrase" note or repeat_penalty 1.05 / 1.08 on the
        # retry flips a good continuous clip to a cut; 1.08 closes the JSON
        # early again. The retry changes the prompt, not the sampler.
        self.assertEqual(vj.JUDGE_RETRY_REPEAT_PENALTY, 1.0)
        self.assertGreater(vj.JUDGE_RETRY_NUM_PREDICT, 1536)
        self.assertNotIn("repeat", vj.JUDGE_RETRY_NOTE.lower())
        self.assertIn("under 15 words", vj.JUDGE_RETRY_NOTE)
        self.assertIn("aesthetic_quality and rationale", vj.JUDGE_RETRY_NOTE)
        self.assertEqual(vj.retry_user_prompt("BRIEF: x\n"), "BRIEF: x\n" + vj.JUDGE_RETRY_NOTE)

    def test_runaway_first_answer_is_retried_with_room_and_the_note(self):
        runaway = '{"frames": ["F1: pine canopy", "F2: ' + "more motion blur, slight upward tilt, " * 60
        parsed, calls = self._run([runaway, _vlm_json(_checks())])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["prompt"], "BRIEF: x")
        self.assertEqual(calls[0]["repeat_penalty"], 1.0)
        self.assertEqual(calls[0]["num_predict"], 1536)
        self.assertEqual(calls[1]["repeat_penalty"], vj.JUDGE_RETRY_REPEAT_PENALTY)
        self.assertEqual(calls[1]["num_predict"], vj.JUDGE_RETRY_NUM_PREDICT)
        self.assertTrue(calls[1]["json_mode"])
        # The retry is a cold prefill too (2026-09-25o).
        self.assertIs(calls[0]["cache_prompt"], False)
        self.assertIs(calls[1]["cache_prompt"], False)
        self.assertTrue(calls[1]["prompt"].startswith("BRIEF: x\n"))
        self.assertIn("RETRY", calls[1]["prompt"])
        self.assertIn("under 15 words", calls[1]["prompt"])
        self.assertEqual(parsed["status"], "pass")
        self.assertEqual(parsed["scores"]["text_video_alignment"], 0.85)
        self.assertTrue(parsed["retry"]["recovered"])
        self.assertEqual(parsed["retry"]["attempt"], 2)
        self.assertIn("VLM did not return a JSON object with float scores", parsed["retry"]["first_reasons"])
        self.assertEqual(parsed["retry"]["first_raw_chars"], len(runaway))
        self.assertTrue(runaway.endswith(parsed["retry"]["first_raw_tail"]))

    def test_json_closed_before_the_scores_is_retried(self):
        early = json.dumps({"frames": ["F1: a"], "checks": _checks(), "constraint_broken": "none"})
        parsed, calls = self._run([early, _vlm_json(_checks())])
        self.assertEqual(len(calls), 2)
        self.assertEqual(parsed["status"], "pass")
        self.assertTrue(parsed["retry"]["recovered"])
        self.assertTrue(any("missing or invalid float score" in r for r in parsed["retry"]["first_reasons"]))

    def test_parsed_first_answer_is_not_retried(self):
        parsed, calls = self._run([_vlm_json(_checks()), "MUST NOT BE ASKED"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(parsed["status"], "pass")
        self.assertNotIn("retry", parsed)

    def test_second_failure_is_final(self):
        runaway = '{"frames": ["F1: ' + "again, " * 50
        parsed, calls = self._run([runaway, runaway, _vlm_json(_checks())])
        self.assertEqual(len(calls), 2)
        self.assertEqual(parsed["status"], "fail")
        self.assertIsNone(parsed["scores"])
        self.assertFalse(parsed["retry"]["recovered"])

    def test_wrong_runtime_verdict_is_not_retried(self):
        parsed, calls = self._run([_vlm_json(_checks()), _vlm_json(_checks())], runtime="ollama")
        self.assertEqual(len(calls), 1)
        self.assertEqual(parsed["status"], "fail")
        self.assertNotIn("retry", parsed)

    def test_scores_missing_helper(self):
        self.assertFalse(vj.scores_missing(None))
        self.assertFalse(vj.scores_missing(_parsed(_checks())))
        self.assertTrue(vj.scores_missing({"status": "fail", "reasons": ["missing or invalid float score: aesthetic_quality"]}))
        self.assertTrue(vj.scores_missing({"status": "fail", "reasons": ["VLM did not return a JSON object with float scores"]}))
        self.assertFalse(vj.scores_missing({"status": "fail", "reasons": [
            "video-director verdict is not from the exact Qwen2.5-VL Caption V4 llama.cpp runtime",
            "missing or invalid float score: aesthetic_quality"]}))
        self.assertFalse(vj.scores_missing({"status": "fail", "reasons": ["rationale must be a string or object"]}))

    def test_retry_survives_fault_caps_and_reaches_the_feedback_row(self):
        judged = _parsed(_checks())
        judged["retry"] = {"attempt": 2, "recovered": True, "first_reasons": ["x"]}
        example = {"id": "GVD-D02", "category": "drone", "user_intent": "fpv through pines"}
        pred = {"start_prompt": "pines", "video_prompt": "fpv weaving between trunks",
                "cfg_scale": "4", "denoise": "1.0", "step_count": "24"}
        result = orch.evaluate_live_candidate(
            example, pred, render_fn=lambda e, p, h: Path("ok.mp4"),
            vlm_fn=lambda f, p, system_prompt=None: judged,
            extract_fn=lambda p: [], check_fn=lambda *a: {"status": "pass", "reasons": []},
            prepare_comfy=lambda **k: None, release_comfy=lambda **k: None,
            prepare_vlm=lambda **k: None, release_vlm=lambda **k: None)
        feedback = json.loads(result["feedback"])
        self.assertEqual(feedback["judge_retry"]["attempt"], 2)
        self.assertEqual(feedback["scores"]["text_video_alignment"], 0.85)
        self.assertIsNone(result.get("error"))

    def test_failed_retry_is_named_in_the_live_metric_error(self):
        judged = {"status": "fail", "scores": None, "minimum": None, "mean": None, "verdict": None,
                  "reasons": ["VLM did not return a JSON object with float scores"],
                  "retry": {"attempt": 2, "recovered": False}}
        example = {"id": "GVD-D03", "category": "drone", "user_intent": "motorcycle on a mountain road"}
        pred = {"start_prompt": "road", "video_prompt": "tracking the rider through the bends",
                "cfg_scale": "4", "denoise": "1.0", "step_count": "24"}
        result = orch.evaluate_live_candidate(
            example, pred, render_fn=lambda e, p, h: Path("ok.mp4"),
            vlm_fn=lambda f, p, system_prompt=None: judged,
            extract_fn=lambda p: [], check_fn=lambda *a: {"status": "pass", "reasons": []},
            prepare_comfy=lambda **k: None, release_comfy=lambda **k: None,
            prepare_vlm=lambda **k: None, release_vlm=lambda **k: None)
        self.assertTrue(result["error"].startswith("VLM scores rejected: "))
        self.assertIn("after one retry", result["error"])
        self.assertEqual(result["mipro"], orch._fail_penalty(result["error"]))
        self.assertLess(result["mipro"], orch.JUDGED_SCORE_FLOOR)


class EvalReportTests(unittest.TestCase):
    def test_summary_counts_false_pass_fail_and_collapse(self):
        labels = {"items": [
            {"clip": "a", "faults": ["hard_cut"]}, {"clip": "b", "faults": []},
            {"clip": "c", "faults": []}, {"clip": "d", "faults": []}]}

        def rec(clip, label, minimum, triple):
            return {"clip": clip, "label": label, "confidence": "high", "status": "pass",
                    "minimum": minimum, "mean": minimum,
                    "scores": dict(zip(gvd_judge_eval.AXES, triple))}

        rep = gvd_judge_eval.summarize([
            rec("a", "reject", 0.85, (0.85, 0.95, 0.9)),
            rec("b", "good", 0.85, (0.85, 0.95, 0.9)),
            rec("c", "good", 0.2, (0.2, 0.9, 0.9)),
            rec("d", "partial", 0.7, (0.7, 0.9, 0.9)),
        ], labels)
        self.assertEqual(rep["distinct_triples"], 3)
        self.assertEqual(rep["@0.60_all"]["false_pass"], "1/1")
        self.assertEqual(rep["@0.60_all"]["false_fail"], "1/2")
        self.assertEqual(rep["@0.60_all"]["partial_pass"], "1/1")
        self.assertEqual(rep["reject_faults_passed@0.60"], {"hard_cut": "1/1"})
        self.assertEqual(rep["auc_good_vs_reject"], 0.25)
        self.assertEqual(rep["retried"], [])
        self.assertEqual(rep["retry_recovered"], [])

    def test_summary_lists_retried_clips(self):
        labels = {"items": [{"clip": "a", "faults": []}, {"clip": "b", "faults": []}, {"clip": "c", "faults": []}]}
        base = {"label": "good", "confidence": "high", "status": "pass", "minimum": 0.8, "mean": 0.8,
                "scores": dict(zip(gvd_judge_eval.AXES, (0.8, 0.8, 0.8)))}
        rep = gvd_judge_eval.summarize([
            {"clip": "a", **base, "retry": {"attempt": 2, "recovered": True}},
            {"clip": "b", **base},
            {"clip": "c", "label": "reject", "confidence": "high", "status": "fail", "minimum": None,
             "mean": None, "scores": None, "retry": {"attempt": 2, "recovered": False}},
        ], labels)
        self.assertEqual(rep["retried"], ["a", "c"])
        self.assertEqual(rep["retry_recovered"], ["a"])
        self.assertEqual(rep["errors"], ["c"])


if __name__ == "__main__":
    unittest.main()
