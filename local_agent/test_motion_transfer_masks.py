#!/usr/bin/env python3
"""Per-frame character selection, tracking, masks and face rule from DWPose
keypoints (stdlib + PIL; no GPU)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PIL import Image

import motion_transfer_masks as mm

CW, CH = 512, 288


def _person(cx: float, cy: float, h: float, *, normalised: bool = False) -> dict:
    """A body-18 skeleton standing at (cx, cy) with height h (pixels)."""
    nose = (cx, cy - 0.45 * h)
    neck = (cx, cy - 0.35 * h)
    pts = [None] * 18
    pts[mm.NOSE] = nose
    pts[mm.NECK] = neck
    pts[mm.R_SHOULDER] = (cx - 0.12 * h, cy - 0.33 * h)
    pts[mm.L_SHOULDER] = (cx + 0.12 * h, cy - 0.33 * h)
    pts[8] = (cx - 0.08 * h, cy)             # r hip
    pts[11] = (cx + 0.08 * h, cy)            # l hip
    pts[10] = (cx - 0.08 * h, cy + 0.5 * h)  # r ankle
    pts[13] = (cx + 0.08 * h, cy + 0.5 * h)  # l ankle
    pts[mm.R_EYE] = (cx - 0.03 * h, cy - 0.47 * h)
    pts[mm.L_EYE] = (cx + 0.03 * h, cy - 0.47 * h)
    flat: list[float] = []
    for p in pts:
        if p is None:
            flat += [0.0, 0.0, 0.0]
        elif normalised:
            flat += [p[0] / CW, p[1] / CH, 1.0]
        else:
            flat += [p[0], p[1], 1.0]
    return {"pose_keypoints_2d": flat, "face_keypoints_2d": None,
            "hand_left_keypoints_2d": None, "hand_right_keypoints_2d": None}


def _frame(*people: dict) -> dict:
    return {"people": list(people), "canvas_width": CW, "canvas_height": CH}


def _clip(n: int = 4) -> list[dict]:
    """A (left, walking right slowly), B (right, static), and a tiny photo
    skeleton at far right."""
    frames = []
    for i in range(n):
        a = _person(120 + 6 * i, 150, 200)
        b = _person(380, 150, 200)
        tiny = _person(490, 60, 20)
        frames.append(_frame(b, a, tiny))   # A is index 1 on purpose
    return frames


class PeopleTests(unittest.TestCase):

    def test_tiny_skeleton_is_dropped_by_size_floor(self):
        people = mm.frame_people(_clip()[0])
        self.assertEqual([0, 1], sorted(p.index for p in people))

    def test_normalised_coordinates_are_scaled_to_the_canvas(self):
        fr = _frame(_person(120, 150, 200, normalised=True))
        p = mm.frame_people(fr)[0]
        self.assertAlmostEqual(120, p.centre[0], delta=1.0)
        self.assertGreater(p.height, 150)

    def test_selectors(self):
        people = mm.frame_people(_clip()[0])
        self.assertEqual(1, mm.select_person(people, {"by": "leftmost"}).index)
        self.assertEqual(0, mm.select_person(people, {"by": "rightmost"}).index)
        self.assertEqual(1, mm.select_person(people, {"by": "index", "index": 1}).index)
        self.assertEqual(0, mm.select_person(people, {"by": "nearest", "point": [0.75, 0.5]}).index)
        self.assertIsNone(mm.select_person(people, {"by": "index", "index": 7}))
        with self.assertRaises(mm.MaskError):
            mm.select_person(people, {"by": "biggest"})

    def test_largest_prefers_the_taller_person(self):
        fr = _frame(_person(120, 150, 120), _person(380, 150, 220))
        self.assertEqual(1, mm.select_person(mm.frame_people(fr), {"by": "largest"}).index)


class TrackTests(unittest.TestCase):

    def test_follows_the_moving_person_by_body_centre(self):
        track, per_frame = mm.track_person(_clip(6), {"by": "leftmost"})
        self.assertEqual(6, len(track))
        self.assertTrue(all(ft.person is not None and not ft.carried for ft in track))
        xs = [ft.person.centre[0] for ft in track]
        self.assertTrue(all(b > a for a, b in zip(xs, xs[1:])), xs)
        self.assertTrue(all(x < 250 for x in xs), xs)

    def test_missing_frame_carries_the_previous_person(self):
        frames = _clip(3)
        frames[1] = _frame(_person(380, 150, 200))     # only B this frame
        track, _ = mm.track_person(frames, {"by": "leftmost"})
        self.assertTrue(track[1].carried)
        self.assertAlmostEqual(track[0].person.centre[0], track[1].person.centre[0])
        self.assertFalse(track[2].carried)

    def test_no_match_at_all_is_an_error_in_prepare(self):
        frames = [_frame(_person(490, 60, 20))] * 2    # only the tiny photo skeleton
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(mm.MaskError):
                mm.prepare(frames, tmp, size=(768, 448))


class MaskTests(unittest.TestCase):

    def test_body_mask_covers_body_and_head_and_scales_to_render_size(self):
        p = mm.frame_people(_clip()[0])[1]           # A, centre x 120 of 512
        img = mm.body_mask(p, (768, 448))
        self.assertEqual((768, 448), img.size)
        sx, sy = 768 / CW, 448 / CH
        self.assertEqual(255, img.getpixel((int(120 * sx), int(150 * sy))))     # hips
        self.assertEqual(255, img.getpixel((int(120 * sx), int(60 * sy))))      # head (nose y=60)
        self.assertEqual(0, img.getpixel((int(380 * sx), int(150 * sy))))       # B's body
        self.assertEqual(0, img.getpixel((760, 440)))

    def test_prepare_writes_one_mask_per_frame_and_a_union(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = mm.prepare(_clip(4), tmp, size=(768, 448), selector={"by": "leftmost"})
            self.assertEqual(4, rec.frames)
            self.assertEqual(4, rec.found)
            self.assertEqual(0, rec.carried)
            self.assertEqual(1, rec.selected_index)
            self.assertEqual(4, len(rec.mask_paths))
            self.assertEqual(sorted(rec.mask_paths), rec.mask_paths)
            for path, sha in zip(rec.mask_paths, rec.mask_sha256):
                self.assertTrue(Path(path).is_file())
                self.assertEqual(64, len(sha))
            self.assertEqual("mask_00001.png", Path(rec.mask_paths[0]).name)
            with Image.open(rec.union_mask_path) as union:
                self.assertEqual((768, 448), union.size)
            self.assertEqual("union", Path(rec.union_mask_path).parent.name)
            # only the frame masks sit directly in out_dir (VHS_LoadImagesPath loads a folder)
            self.assertEqual(4, len([p for p in Path(tmp).iterdir() if p.is_file()]))
            self.assertEqual([2, 2, 2, 2], rec.people_per_frame)
            self.assertEqual("ordered", rec.face_rule["mode"])
            self.assertEqual(("x1", False, 1), (rec.face_rule["target"], rec.face_rule["order"],
                                                rec.face_rule["take_count"]))
            as_dict = rec.as_dict()
            self.assertEqual(json.loads(json.dumps(as_dict)), as_dict)

    def test_pose_json_file_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "pose_kps_00001.json"
            src.write_text(json.dumps(_clip(2)), encoding="utf-8")
            rec = mm.prepare(src, Path(tmp) / "masks", size=(768, 448), selector={"by": "index", "index": 0})
            self.assertEqual(0, rec.selected_index)
            self.assertEqual("x1", rec.face_rule["target"])
            self.assertTrue(rec.face_rule["order"])       # B is rightmost


class FaceRuleTests(unittest.TestCase):

    def test_alone_means_largest_face(self):
        frames = [_frame(_person(200, 150, 200)) for _ in range(3)]
        track, per_frame = mm.track_person(frames, None)
        rule = mm.face_rule(track, per_frame)
        self.assertEqual(("ordered", "area", True), (rule["mode"], rule["target"], rule["order"]))

    def test_topmost_when_heads_differ_vertically_only(self):
        frames = [_frame(_person(250, 100, 120), _person(250, 220, 120)) for _ in range(3)]
        track, per_frame = mm.track_person(frames, {"by": "index", "index": 0})
        rule = mm.face_rule(track, per_frame)
        self.assertEqual(("y1", False), (rule["target"], rule["order"]))

    def test_crossing_paths_fall_back_to_the_union_mask(self):
        frames = []
        for i in range(5):
            a = _person(100 + 70 * i, 150, 200)    # walks right across B
            b = _person(240, 150, 200)
            frames.append(_frame(a, b))
        track, per_frame = mm.track_person(frames, {"by": "index", "index": 0}, max_jump_frac=0.5)
        rule = mm.face_rule(track, per_frame)
        self.assertEqual("union_mask", rule["mode"])


if __name__ == "__main__":
    unittest.main()
