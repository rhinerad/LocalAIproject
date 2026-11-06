#!/usr/bin/env python3
"""camera_motion: synthetic pans, tilts, zooms, statics, cuts and blanks.

No ffmpeg, no video files: frames are crops of one textured plate.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import camera_motion as cm  # noqa: E402

PLATE = 1024, 576   # (width, height) of the textured plate the "camera" looks at


def _plate(seed: int = 7) -> np.ndarray:
    """Smooth random texture with structure at several scales."""
    rng = np.random.default_rng(seed)
    w, h = PLATE
    img = np.zeros((h, w), np.float32)
    for cell in (2, 8, 24, 64):   # 2: fine grain so unrelated plates decorrelate
        small = rng.uniform(0, 255, size=(h // cell + 2, w // cell + 2)).astype(np.float32)
        ys = (np.arange(h) / cell)
        xs = (np.arange(w) / cell)
        y0, x0 = ys.astype(int), xs.astype(int)
        fy, fx = (ys - y0)[:, None], (xs - x0)[None, :]
        top = small[y0][:, x0] * (1 - fx) + small[y0][:, x0 + 1] * fx
        bot = small[y0 + 1][:, x0] * (1 - fx) + small[y0 + 1][:, x0 + 1] * fx
        img += top * (1 - fy) + bot * fy
    img -= img.min()
    return (img / img.max() * 200 + 30).astype(np.float32)


def _view(plate: np.ndarray, cx: float, cy: float, zoom: float = 1.0) -> np.ndarray:
    """Camera view: a cm.W x cm.H window centred at (cx, cy) on the plate,
    seeing a plate region of size (cm.W / zoom, cm.H / zoom). zoom > 1 = closer."""
    h, w = plate.shape
    xs = cx + (np.arange(cm.W) - cm.W / 2 + 0.5) / zoom
    ys = cy + (np.arange(cm.H) - cm.H / 2 + 0.5) / zoom
    xi = np.clip(np.round(xs).astype(int), 0, w - 1)
    yi = np.clip(np.round(ys).astype(int), 0, h - 1)
    return plate[yi][:, xi]


def _windows(n: int) -> list[dict]:
    return [{"frame": i + 1, "start": float(i), "end": float(i + 1)} for i in range(n)]


class PhaseShiftTests(unittest.TestCase):
    def test_pure_roll_recovers_signed_shift(self):
        plate = _plate()
        a = _view(plate, 512, 288)
        b = np.roll(a, shift=(3, 5), axis=(0, 1))   # content moves down 3, right 5
        dx, dy, resp = cm.phase_shift(a, b)
        self.assertAlmostEqual(dx, 5.0, delta=0.3)
        self.assertAlmostEqual(dy, 3.0, delta=0.3)
        self.assertGreater(resp, 0.5)

    def test_unrelated_pictures_have_low_response(self):
        a = _view(_plate(1), 512, 288)
        b = _view(_plate(2), 512, 288)
        _dx, _dy, resp = cm.phase_shift(a, b)
        self.assertLess(resp, cm.MIN_RESPONSE)


class PairMotionTests(unittest.TestCase):
    def setUp(self):
        self.plate = _plate()

    def test_camera_pan_left_reads_as_content_moving_right(self):
        # camera window slides LEFT over the plate by 4 px: content moves right
        a = _view(self.plate, 512, 288)
        b = _view(self.plate, 508, 288)
        m = cm.pair_motion(a, b)
        self.assertAlmostEqual(m["dx"], 4.0, delta=0.5)
        self.assertAlmostEqual(m["dy"], 0.0, delta=0.5)
        self.assertLess(abs(m["scale"]), 0.005)
        self.assertGreater(m["response"], 0.3)

    def test_push_in_reads_as_positive_scale(self):
        a = _view(self.plate, 512, 288, zoom=1.00)
        b = _view(self.plate, 512, 288, zoom=1.03)
        m = cm.pair_motion(a, b)
        self.assertGreater(m["scale"], 0.015)
        self.assertLess(abs(m["dx"]), 1.0)
        self.assertLess(abs(m["dy"]), 1.0)

    def test_pull_back_reads_as_negative_scale(self):
        a = _view(self.plate, 512, 288, zoom=1.03)
        b = _view(self.plate, 512, 288, zoom=1.00)
        self.assertLess(cm.pair_motion(a, b)["scale"], -0.015)

    def test_blank_frame_is_flagged_not_measured(self):
        a = _view(self.plate, 512, 288)
        m = cm.pair_motion(a, np.zeros_like(a))
        self.assertTrue(m["blank"])
        self.assertEqual(m["response"], 0.0)


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.plate = _plate()

    def _clip(self, path):
        """path: list of (cx, cy, zoom) per frame."""
        return np.stack([_view(self.plate, cx, cy, z) for cx, cy, z in path])

    def test_static_then_pan_then_tilt_then_zoom_then_cut(self):
        fps = 4.0   # 4 frames per one-second window
        path = []
        path += [(512, 288, 1.0)] * 5                                   # window 1: static
        path += [(512 - 3 * k, 288, 1.0) for k in range(1, 5)]          # window 2: camera pans left 12 px
        path += [(500, 288 - 2 * k, 1.0) for k in range(1, 5)]          # window 3: camera moves up, content moves down -> tilt-up
        path += [(500, 280, 1.0 + 0.012 * k) for k in range(1, 5)]      # window 4: push-in ~4.8%
        frames = self._clip(path)
        other = np.stack([_view(_plate(3), 512, 288)] * 4)              # window 5: hard cut to another picture
        frames = np.concatenate([frames, other])
        est = cm.estimate_from_frames(frames, fps, _windows(5))
        labels = [e["camera"] for e in est]
        self.assertEqual(labels[0], "static")
        self.assertEqual(labels[1], "pan-left")
        self.assertEqual(labels[2], "tilt-up")
        self.assertEqual(labels[3], "push-in")
        # window 5: the first pair is the cut (low response, excluded); the rest are static
        self.assertEqual(est[4]["low_response_pairs"], 1)
        self.assertIn(labels[4], ("static", "uncertain"))
        self.assertAlmostEqual(est[1]["dx_frac"], 12 / cm.W, delta=0.01)

    def test_window_with_mostly_cuts_is_uncertain(self):
        # five unrelated pictures in a row (white-noise plates: nothing to align)
        rng = np.random.default_rng(11)
        frames = np.stack([rng.uniform(30, 230, size=(cm.H, cm.W)).astype(np.float32) for _ in range(5)])
        est = cm.estimate_from_frames(frames, 4.0, _windows(1))
        self.assertEqual(est[0]["camera"], "uncertain")
        self.assertEqual(est[0]["low_response_pairs"], 4)

    def test_black_clip_is_uncertain(self):
        frames = np.zeros((9, cm.H, cm.W), np.float32)
        est = cm.estimate_from_frames(frames, 4.0, _windows(2))
        self.assertEqual([e["camera"] for e in est], ["uncertain", "uncertain"])


class BorderAndCoherenceTests(unittest.TestCase):
    """2026-09-25e: border-ring fit, subject motion in the centre, incoherent flow."""

    def setUp(self):
        self.plate = _plate()

    def _with_subject(self, offset: int) -> np.ndarray:
        """Static camera view with a textured square subject in the centre,
        displaced by ``offset`` px to the right."""
        view = _view(self.plate, 512, 288).copy()
        patch = _view(_plate(5), 400, 300)[20:76, 40:120]      # 56 x 80 textured patch
        y0, x0 = cm.H // 2 - 28, cm.W // 2 - 40 + offset
        view[y0:y0 + 56, x0:x0 + 80] = patch
        return view

    def test_moving_subject_over_still_background_is_static_with_subject_motion(self):
        frames = np.stack([self._with_subject(3 * k) for k in range(5)])
        est = cm.estimate_from_frames(frames, 4.0, _windows(1))[0]
        self.assertEqual(est["camera"], "static")
        self.assertTrue(est["subject_motion"])
        self.assertGreaterEqual(est["subject_excess_px"], cm.SUBJECT_EXCESS_PX)

    def test_incoherent_block_motion_lowers_coherence_but_is_not_relabelled(self):
        a = _view(self.plate, 512, 288)
        rng = np.random.default_rng(3)
        bh, bw = cm.H // cm.GRID, cm.W // cm.GRID
        frames = [a]
        cur = a
        for _ in range(4):
            nxt = cur.copy()
            for gy in range(cm.GRID):
                for gx in range(cm.GRID):
                    ys, xs = slice(gy * bh, (gy + 1) * bh), slice(gx * bw, (gx + 1) * bw)
                    # every block slides by its own amount, all rightwards: the sum is
                    # a big "pan-left" but the field is not a camera move
                    nxt[ys, xs] = np.roll(cur[ys, xs], int(rng.integers(1, 7)), axis=1)
            frames.append(nxt)
            cur = nxt
        est = cm.estimate_from_frames(np.stack(frames), 4.0, _windows(1))[0]
        pan = cm.estimate_from_frames(
            np.stack([_view(self.plate, 512 - 3 * k, 288) for k in range(5)]), 4.0, _windows(1))[0]
        # Coherence is a diagnostic: lower than a clean pan's, but the label
        # is still the summed motion (parallax makes real camera moves
        # incoherent too, so no gate; CHANGELOG 2026-09-25e).
        self.assertLess(est["coherence"], pan["coherence"])
        self.assertEqual(est["camera"], "pan-left")
        self.assertNotIn("incoherent", est)

    def test_coherent_pan_keeps_high_coherence_and_matches_full_frame(self):
        frames = np.stack([_view(self.plate, 512 - 3 * k, 288) for k in range(5)])
        est = cm.estimate_from_frames(frames, 4.0, _windows(1))[0]
        self.assertEqual(est["camera"], "pan-left")
        self.assertEqual(est["full_frame_camera"], "pan-left")
        self.assertGreaterEqual(est["coherence"], 0.9)
        self.assertFalse(est["subject_motion"])


class ClassifyTests(unittest.TestCase):
    def test_thresholds_and_vocabulary(self):
        self.assertEqual(cm.classify(0.0, 0.0, 0.0, 0.9), "static")
        self.assertEqual(cm.classify(0.019, 0.0, 0.0, 0.9), "static")
        self.assertEqual(cm.classify(0.03, 0.0, 0.0, 0.9), "pan-left")
        self.assertEqual(cm.classify(-0.03, 0.0, 0.0, 0.9), "pan-right")
        self.assertEqual(cm.classify(0.0, 0.03, 0.0, 0.9), "tilt-up")
        self.assertEqual(cm.classify(0.0, -0.03, 0.0, 0.9), "tilt-down")
        self.assertEqual(cm.classify(0.0, 0.0, 0.05, 0.9), "push-in")
        self.assertEqual(cm.classify(0.0, 0.0, -0.05, 0.9), "pull-back")
        self.assertEqual(cm.classify(0.5, 0.5, 0.5, 0.05), "uncertain")
        for value in ("static", "push-in", "pan-left", "uncertain"):
            self.assertIn(value, cm.CAMERA_VALUES)

    def test_compare_with_claims_skips_uncertain_and_unclaimed(self):
        est = [{"frame": 1, "camera": "static"}, {"frame": 2, "camera": "pan-left"},
               {"frame": 3, "camera": "uncertain"}, {"frame": 4, "camera": "push-in"}]
        out = cm.compare_with_claims(est, {"1": "static", "2": "static", "3": "static"})
        self.assertEqual(out["agree"], 1)
        self.assertEqual(out["disagree"], [{"frame": 2, "claimed": "static", "measured": "pan-left"}])
        self.assertEqual(out["measured_values"]["4"], "push-in")


if __name__ == "__main__":
    unittest.main()
