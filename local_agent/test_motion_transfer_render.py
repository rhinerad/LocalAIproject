"""Tests for render_video_from_reference (motion_transfer_render.py + tools wrappers).

No GPU, no ComfyUI, no InsightFace: probes, the GPU gate, the backend checks and the
subprocess are patched. The graph is pinned by TEMPLATE_SHA256 so any structural change
to the template has to be made deliberately here too.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import motion_transfer as mt  # noqa: E402
import motion_transfer_render as mtr  # noqa: E402

TEMPLATE_SHA256 = "d2943a9ddabc9c4f1308461ca2a93921e1c73fed0c5e134d48e188620a1ffc8d"
# A segment after the first of a chained job (held frames + latent noise mask), 2026-09-26l.
CHAINED_TEMPLATE_SHA256 = "00bd278d3562cbdc1fb254cac0836fc245294cf6805629ce5846aa3d794ba2cf"


def _video(duration=8.0, width=736, height=416, path="C:/clip.mp4"):
    return {"path": path, "duration_s": duration, "fps": 24.0, "width": width, "height": height,
            "source_frames": int(duration * 24), "size_bytes": 1, "sha256": "ab" * 32, "audio_streams": 1}


def _still(path="C:/still.png"):
    return {"path": path, "width": 1672, "height": 941, "size_bytes": 1, "sha256": "cd" * 32}


class _Inputs(unittest.TestCase):
    """Real (empty) files with the right suffixes, so path validation runs for real."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.video = self.tmp / "clip.mp4"
        self.still = self.tmp / "still.png"
        self.video.write_bytes(b"x")
        self.still.write_bytes(b"x")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def args(self, **kw):
        a = {"reference_video": str(self.video), "character_image": str(self.still),
             "prompt": "a man in a teal cardigan leans over a bed", "likeness_attestation": True}
        a.update(kw)
        return a

    def prepare(self, video=None, **kw):
        with patch.object(mt, "probe_video", return_value=video or _video(path=str(self.video))), \
                patch.object(mt, "probe_image", return_value=_still(str(self.still))):
            return mtr.prepare_request(self.args(**kw))


class PrepareRequestTests(_Inputs):
    def test_attestation_is_required_and_must_be_true(self):
        for value in (None, False, "true", 1):
            with self.assertRaises(mtr.RenderRequestError):
                self.prepare(likeness_attestation=value)

    def test_whole_short_clip(self):
        spec = self.prepare()
        self.assertEqual(63, spec["frames"])          # 8 s at 8 fps, quarter-frame end margin
        self.assertEqual(5, spec["windows"])
        self.assertEqual((768, 448), (spec["width"], spec["height"]))
        self.assertTrue(spec["size_measured"])
        self.assertEqual("auto", spec["target"])
        self.assertTrue(spec["face_detail"])

    def test_long_clip_refused_with_section_hint_unless_chaining_is_asked_for(self):
        long = _video(duration=70.767, width=1920, height=1080, path=str(self.video))
        for kw in ({}, {"chain": False}):
            with self.subTest(kw=kw), self.assertRaises(mtr.RenderRequestError) as ctx:
                self.prepare(video=long, **kw)
            self.assertIn("max_seconds", str(ctx.exception))
            self.assertIn("180 frames", str(ctx.exception))
            self.assertIn("chain=true", str(ctx.exception))

    def test_long_clip_chains_when_asked(self):
        spec = self.prepare(video=_video(duration=70.767, width=1920, height=1080, path=str(self.video)),
                            chain=True)
        self.assertTrue(spec["chained"])
        self.assertEqual(565, spec["frames"])                        # delivered frames, unchanged meaning
        self.assertEqual((64, 4, "held"), (spec["segment_frames"], spec["held_frames"], spec["init_mode"]))
        segs = spec["segments"]
        self.assertEqual(9, len(segs))
        self.assertEqual(565, sum(s["new"] for s in segs))
        self.assertTrue(all(s["frames"] <= mtr.MAX_FRAMES for s in segs))
        self.assertEqual(0, segs[0]["held"])
        self.assertTrue(all(s["held"] == 4 for s in segs[1:]))
        self.assertEqual(67, mtr.ram_frames(spec))                    # RAM is bounded by one segment
        self.assertEqual(565 + 8 * 4, mtr.rendered_frames(spec))
        self.assertEqual(sum(s["windows"] for s in segs), spec["windows"])

    def test_short_clip_keeps_the_single_job_path(self):
        spec = self.prepare()
        self.assertFalse(spec["chained"])
        self.assertIsNone(spec["segments"])
        self.assertEqual((None, 0, None), (spec["segment_frames"], spec["held_frames"], spec["init_mode"]))
        # chain=true on a clip that fits one segment is still one job (no seam to make)
        self.assertFalse(self.prepare(chain=True)["chained"])

    def test_segment_seconds_forces_chaining(self):
        spec = self.prepare(segment_seconds=4)
        self.assertTrue(spec["chained"])
        self.assertEqual(32, spec["segment_frames"])
        self.assertEqual([(0, 32, 32), (4, 31, 35)],
                         [(s["held"], s["new"], s["frames"]) for s in spec["segments"]])
        self.assertEqual([0, 28], [s["source_offset"] for s in spec["segments"]])

    def test_segment_and_chain_validation(self):
        long = _video(duration=70.767, width=1920, height=1080, path=str(self.video))
        for kw in ({"segment_seconds": 0.5}, {"segment_seconds": 30}, {"segment_seconds": -1},
                   {"chain": "yes"}, {"segment_seconds": "x"}):
            with self.subTest(kw=kw), self.assertRaises(mtr.RenderRequestError):
                self.prepare(video=long, **kw)
        with self.assertRaises(mtr.RenderRequestError) as ctx:
            self.prepare(video=_video(duration=80.0, width=1920, height=1080, path=str(self.video)), chain=True)
        self.assertIn("600 frames", str(ctx.exception))
        # 600 delivered frames exactly is allowed
        spec = self.prepare(video=_video(duration=75.1, width=1920, height=1080, path=str(self.video)),
                            chain=True)
        self.assertEqual(600, spec["frames"])
        self.assertTrue(spec["chained"])

    def test_measured_longest_run_is_allowed(self):
        spec = self.prepare(video=_video(duration=15.08, path=str(self.video)), target_fps=12)
        self.assertEqual((180, 15), (spec["frames"], spec["windows"]))

    def test_ram_need_scales_with_length(self):
        self.assertEqual(15.9, mtr.ram_needed_gb(180))
        self.assertEqual(6.5, mtr.ram_needed_gb(63))
        with patch.dict(sys.modules, {"psutil": MagicMock(virtual_memory=lambda: MagicMock(available=8 * 2**30))}):
            self.assertEqual((False, 8.0), (mtr.ram_check(180)["ok"], mtr.ram_check(180)["available_gb"]))
            self.assertTrue(mtr.ram_check(63)["ok"])

    def test_section_of_long_clip(self):
        spec = self.prepare(video=_video(duration=70.767, width=1920, height=1080, path=str(self.video)),
                            start_seconds=12, max_seconds=4)
        self.assertEqual(32, spec["frames"])
        self.assertEqual(96, spec["skip_frames"])

    def test_portrait_is_unmeasured(self):
        spec = self.prepare(video=_video(width=1080, height=1920, path=str(self.video)))
        self.assertEqual((448, 768), (spec["width"], spec["height"]))
        self.assertFalse(spec["size_measured"])

    def test_bad_values(self):
        for kw in ({"target_fps": 30}, {"target": "everyone"}, {"start_seconds": 9}, {"prompt": "short"},
                   {"seed": 0}, {"max_seconds": 0.5}):
            with self.subTest(kw=kw), self.assertRaises(mtr.RenderRequestError):
                self.prepare(**kw)

    def test_equal_shares_tree_refused(self):
        with patch.object(mtr, "FORBIDDEN_TREE", self.tmp.resolve()):
            with self.assertRaises(mtr.RenderRequestError) as ctx:
                self.prepare()
        self.assertIn("equal_shares", str(ctx.exception))

    def test_missing_file(self):
        with self.assertRaises(mtr.RenderRequestError):
            mtr.prepare_request(self.args(reference_video=str(self.tmp / "nope.mp4")))


class SegmentPlanTests(unittest.TestCase):
    def test_balanced_segments_cover_the_clip_once(self):
        segs = mtr.plan_segments(180, 60)
        self.assertEqual([(0, 0, 60, 60), (56, 4, 60, 64), (116, 4, 60, 64)],
                         [(s["source_offset"], s["held"], s["new"], s["frames"]) for s in segs])
        # every delivered frame comes from exactly one segment's new frames, in order
        delivered = []
        for s in segs:
            delivered.extend(range(s["source_offset"] + s["held"], s["source_offset"] + s["frames"]))
        self.assertEqual(list(range(180)), delivered)
        # and the held frames of segment i are the last frames delivered by segment i-1
        for prev, cur in zip(segs, segs[1:]):
            prev_end = prev["source_offset"] + prev["frames"]
            self.assertEqual(list(range(prev_end - cur["held"], prev_end)),
                             list(range(cur["source_offset"], cur["source_offset"] + cur["held"])))

    def test_uneven_split_and_small_clips(self):
        segs = mtr.plan_segments(565, 64)
        self.assertEqual(9, len(segs))
        self.assertEqual(565, sum(s["new"] for s in segs))
        self.assertTrue(all(62 <= s["new"] <= 64 for s in segs))
        self.assertTrue(all(s["frames"] <= 68 for s in segs))
        self.assertEqual(1, len(mtr.plan_segments(40, 64)))
        self.assertEqual([(0, 5), (4, 4)], [(s["held"], s["new"]) for s in mtr.plan_segments(9, 8)])
        for bad in ((0, 8), (8, 0), (8, 8, -1)):
            with self.assertRaises(ValueError):
                mtr.plan_segments(*bad)

    def test_windows_helper(self):
        self.assertEqual([1, 1, 2, 5, 15], [mtr._windows(n) for n in (8, 16, 24, 63, 180)])


class FramePlanTests(unittest.TestCase):
    def test_plan_frames(self):
        self.assertEqual(63, mtr.plan_frames(8.0, 0, 8, None))
        self.assertEqual(32, mtr.plan_frames(8.0, 0, 8, 4))
        self.assertEqual(15, mtr.plan_frames(8.0, 6.0, 8, None))
        self.assertEqual(63, mtr.plan_frames(8.0, 0, 8, 7.95))  # a cut at the end keeps the margin


class TargetTests(unittest.TestCase):
    TWO = [[0.30, 0.10, 0.42, 0.30, 0.9], [0.60, 0.30, 0.70, 0.45, 0.9]]

    def test_two_people_auto_takes_largest_left(self):
        t = mtr.choose_target([self.TWO] * 8, "auto")
        self.assertEqual((2, 0), (t["people"], t["rank"]))
        self.assertEqual([0.0, 0.505], t["band"])

    def test_right_target(self):
        t = mtr.choose_target([self.TWO] * 8, "right")
        self.assertEqual(1, t["rank"])
        self.assertEqual([0.505, 1.0], t["band"])

    def test_one_person_has_no_band(self):
        t = mtr.choose_target([[[0.4, 0.1, 0.5, 0.3, 0.9]]] * 8, "auto")
        self.assertEqual((1, None), (t["people"], t["band"]))

    def test_no_faces(self):
        t = mtr.choose_target([[], []], "auto")
        self.assertEqual(0, t["people"])
        self.assertIsNone(t["band"])

    def test_tracks_a_moving_target_by_nearest_centre(self):
        frames = [[[0.20 + i * 0.02, 0.1, 0.30 + i * 0.02, 0.3, 0.9], [0.70, 0.1, 0.80, 0.3, 0.9]]
                  for i in range(8)]
        t = mtr.choose_target(frames, "left")
        self.assertEqual(0, t["rank"])
        self.assertAlmostEqual(0.25, t["track"][0], places=3)
        self.assertAlmostEqual(0.39, t["track"][-1], places=3)

    def test_crowded_band_is_widened(self):
        faces = [[0.40, 0.1, 0.44, 0.2, 0.9], [0.46, 0.1, 0.50, 0.2, 0.9], [0.52, 0.1, 0.56, 0.2, 0.9]]
        t = mtr.choose_target([faces] * 4, "center")
        self.assertGreaterEqual(t["band"][1] - t["band"][0], 0.25 - 1e-9)

    def test_prev_centre_continues_the_tracked_person(self):
        # a segment after the first: the person nearest the previous track wins, whatever `target` says
        t = mtr.choose_target([self.TWO] * 4, "left", prev_centre=0.66)
        self.assertEqual(1, t["rank"])
        self.assertEqual([0.505, 1.0], t["band"])
        self.assertEqual(0, mtr.choose_target([self.TWO] * 4, "right", prev_centre=0.3)["rank"])

    def test_map_x_centre_crop(self):
        self.assertAlmostEqual(0.5, mtr.map_x(0.5, 1920, 1080, 768, 448))
        self.assertLess(mtr.map_x(0.0, 1920, 1080, 768, 448), 0.0)
        self.assertEqual(0.3, mtr.map_x(0.3, 1080, 1920, 448, 768))

    def test_band_to_pixels_matches_the_measured_manual_mask(self):
        spec = {"reference_video": _video(), "width": 768, "height": 448}
        # 736x416 source centre-cropped to 768x448: source x 0.52 lands on pixel 400 (25v's mask)
        self.assertEqual([0, 400], mtr.band_to_pixels([0.0, 0.52], spec))
        self.assertEqual([0, 388], mtr.band_to_pixels([0.0, 0.505], spec))
        self.assertIsNone(mtr.band_to_pixels(None, spec))


class GraphTests(unittest.TestCase):
    SPEC = {"reference_video": {"path": "C:/clip.mp4", "width": 736, "height": 416},
            "prompt": "p", "negative": "n", "face_prompt": "f", "seed": 7, "target_fps": 8,
            "skip_frames": 3, "frames": 24, "width": 768, "height": 448, "face_detail": True}
    INPUTS = {"face_image": "face.png", "mask_image": "mask.png", "face_found": True, "faceid": True,
              "people": 2, "rank": 1}

    def test_template_is_pinned(self):
        self.assertEqual(TEMPLATE_SHA256, mtr.template_sha256())

    def test_measured_rules_are_in_the_graph(self):
        g, done = mtr.build_graph(self.SPEC, self.INPUTS, "motion_transfer/j")
        self.assertEqual("48", done)
        self.assertEqual("disable", g["2"]["inputs"]["detect_face"])      # 25t: no face keypoints
        self.assertEqual("enable", g["2"]["inputs"]["scale_stick_for_xinsr_cn"])
        self.assertEqual("openpose", g["19"]["inputs"]["type"])
        self.assertEqual("ACN_AdvancedControlNetApply_v2", g["20"]["class_type"])  # 25u multi-window
        self.assertEqual((24, 3), (g["1"]["inputs"]["frame_load_cap"], g["1"]["inputs"]["skip_first_frames"]))
        self.assertEqual(24, g["21"]["inputs"]["batch_size"])
        self.assertEqual(["26", 0], g["15"]["inputs"]["attn_mask"])       # 25v mask on the main adapter
        self.assertEqual("IPAdapterFaceID", g["43"]["class_type"])        # 26g FaceID in detail only
        self.assertEqual(["50", 0], g["43"]["inputs"]["model"])
        self.assertEqual("IPAdapterUnifiedLoader", g["13"]["class_type"])
        self.assertNotIn("attn_mask", g["43"]["inputs"])
        self.assertEqual({"target": "x1", "order": False, "take_start": 1, "take_count": 1, "segs": ["41", 0]},
                         g["42"]["inputs"])
        self.assertEqual(0.5, g["47"]["inputs"]["denoise"])

    def test_chained_template_is_pinned(self):
        self.assertEqual(CHAINED_TEMPLATE_SHA256, mtr.template_sha256(chained=True))
        self.assertEqual(TEMPLATE_SHA256, mtr.template_sha256())  # the single-job graph did not move

    def test_first_segment_is_the_single_graph_with_a_narrower_loader(self):
        spec = dict(self.SPEC, chained=True, init_mode="held", frames=48)
        seg0 = {"index": 0, "source_offset": 0, "held": 0, "new": 24, "frames": 24, "windows": 2}
        g0, done = mtr.build_graph(spec, self.INPUTS, "motion_transfer/j/seg01", seg0)
        g_single, _ = mtr.build_graph(self.SPEC, self.INPUTS, "motion_transfer/j/seg01")
        self.assertEqual(g_single, g0)                                 # held 0 -> no init nodes at all
        self.assertEqual((24, 3), (g0["1"]["inputs"]["frame_load_cap"], g0["1"]["inputs"]["skip_first_frames"]))

    def test_held_segment_graph(self):
        spec = dict(self.SPEC, chained=True, init_mode="held", frames=48)
        seg1 = {"index": 1, "source_offset": 20, "held": 4, "new": 24, "frames": 28, "windows": 2}
        inputs = dict(self.INPUTS, init_dir="C:/job/seg02/init", noise_mask_dir="C:/job/seg02/noise_mask")
        g, done = mtr.build_graph(spec, inputs, "motion_transfer/j/seg02", seg1)
        self.assertEqual("48", done)
        # loader walks the reference: skip_frames 3 + offset 20, 28 frames (4 held + 24 new)
        self.assertEqual((28, 23), (g["1"]["inputs"]["frame_load_cap"], g["1"]["inputs"]["skip_first_frames"]))
        # the 4 held frames are encoded and batched ahead of 24 empty latents
        self.assertEqual({"directory": "C:/job/seg02/init", "image_load_cap": 4, "skip_first_images": 0,
                          "select_every_nth": 1}, g["30"]["inputs"])
        self.assertEqual({"pixels": ["30", 0], "vae": ["10", 2]}, g["31"]["inputs"])
        self.assertEqual(24, g["21"]["inputs"]["batch_size"])
        self.assertEqual({"samples1": ["31", 0], "samples2": ["21", 0]}, g["32"]["inputs"])
        # one mask per frame pins the held ones; the sampler starts from the masked batch at full denoise
        self.assertEqual(28, g["33"]["inputs"]["image_load_cap"])
        self.assertEqual("C:/job/seg02/noise_mask", g["33"]["inputs"]["directory"])
        self.assertEqual({"image": ["33", 0], "channel": "red"}, g["34"]["inputs"])
        self.assertEqual({"samples": ["32", 0], "mask": ["34", 0]}, g["35"]["inputs"])
        self.assertEqual((["35", 0], 1.0), (g["22"]["inputs"]["latent_image"], g["22"]["inputs"]["denoise"]))
        # everything measured before is untouched
        self.assertEqual("disable", g["2"]["inputs"]["detect_face"])
        self.assertEqual(["26", 0], g["15"]["inputs"]["attn_mask"])
        self.assertEqual("IPAdapterFaceID", g["43"]["class_type"])
        self.assertNotIn("36", g)

    def test_img2img_segment_graph_is_the_investigation_alternative(self):
        spec = dict(self.SPEC, chained=True, init_mode="img2img", init_denoise=0.65, frames=48)
        seg1 = {"index": 1, "source_offset": 20, "held": 4, "new": 24, "frames": 28, "windows": 2}
        inputs = dict(self.INPUTS, init_dir="C:/job/seg02/init", noise_mask_dir="C:/job/seg02/noise_mask")
        g, _ = mtr.build_graph(spec, inputs, "x", seg1)
        self.assertEqual((1, 3), (g["30"]["inputs"]["image_load_cap"], g["30"]["inputs"]["skip_first_images"]))
        self.assertEqual({"image": ["30", 0], "amount": 28}, g["36"]["inputs"])
        self.assertEqual((["31", 0], 0.65), (g["22"]["inputs"]["latent_image"], g["22"]["inputs"]["denoise"]))
        self.assertFalse({"32", "33", "34", "35"} & set(g))
        with self.assertRaises(ValueError):
            mtr.build_graph(dict(spec, init_mode="magic"), inputs, "x", seg1)

    def test_single_person_no_mask(self):
        g, _ = mtr.build_graph(self.SPEC, dict(self.INPUTS, mask_image=None, people=1, rank=0), "x")
        self.assertNotIn("26", g)
        self.assertNotIn("attn_mask", g["15"]["inputs"])
        self.assertEqual("area(=w*h)", g["42"]["inputs"]["target"])

    def test_plus_face_fallbacks(self):
        for inputs in (dict(self.INPUTS, face_found=False), dict(self.INPUTS, faceid=False)):
            g, _ = mtr.build_graph(self.SPEC, inputs, "x")
            self.assertEqual("IPAdapterAdvanced", g["43"]["class_type"])
            self.assertNotIn("50", g)

    def test_without_face_detail(self):
        g, done = mtr.build_graph(dict(self.SPEC, face_detail=False), self.INPUTS, "x")
        self.assertEqual("24", done)
        self.assertFalse({"40", "41", "42", "43", "47", "48", "49", "50"} & set(g))

    def test_validate_graph(self):
        info = {"SaveImage": {"input": {"required": {"images": ["IMAGE"], "filename_prefix": ["STRING", {}]}}},
                "SetUnionControlNetType": {"input": {"required": {
                    "control_net": ["CONTROL_NET", {}],
                    "type": ["COMBO", {"options": ["auto", "openpose", "depth"]}]}}}}
        ok = {"1": {"class_type": "SaveImage", "inputs": {"images": ["0", 0], "filename_prefix": "a"}},
              "2": {"class_type": "SetUnionControlNetType", "inputs": {"control_net": ["0", 0], "type": "openpose"}}}
        self.assertEqual([], mtr.validate_graph(ok, info))
        bad = {"1": {"class_type": "Nope", "inputs": {}},
               "2": {"class_type": "SaveImage", "inputs": {"images": ["0", 0], "extra": 1}},
               "3": {"class_type": "SetUnionControlNetType", "inputs": {"control_net": ["0", 0], "type": "canny"}}}
        problems = " | ".join(mtr.validate_graph(bad, info))
        self.assertIn("Nope not in object_info", problems)
        self.assertIn("unknown input 'extra'", problems)
        self.assertIn("type='canny' not offered", problems)


class FacesHelperArgsTests(unittest.TestCase):
    """The helper accepts a frame-list file: 180 inline paths overflowed the Windows command line."""

    def test_frames_file(self):
        import io
        import motion_transfer_faces as mf
        tmp = Path(tempfile.mkdtemp())
        try:
            listing = tmp / "frames.txt"
            listing.write_text("a.png\n\nb.png\n", encoding="utf-8")
            seen = {}
            with patch.object(mf, "cmd_score", side_effect=lambda a: seen.update(frames=a.frames) or {}), \
                    patch("sys.stdout", new=io.StringIO()):
                mf.main(["score", "--ref", "r.png", "--frames-file", str(listing)])
            self.assertEqual(["a.png", "b.png"], seen["frames"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_frames_and_file_are_exclusive(self):
        import motion_transfer_faces as mf
        with self.assertRaises(SystemExit), patch("sys.stderr"):
            mf.main(["score", "--ref", "r.png", "--frames", "a.png", "--frames-file", "x.txt"])


class ChainFilesTests(unittest.TestCase):
    """Held-frame inputs, stitching order and the seam measurement, on real (tiny) PNGs."""

    W, H = 16, 8

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _png(self, name: str, value: int) -> str:
        from PIL import Image
        path = self.tmp / name
        Image.new("RGB", (self.W, self.H), (value, value // 2, 255 - value)).save(path)
        return str(path)

    def test_write_segment_inputs_copies_the_previous_tail_bytewise(self):
        tail = [self._png(f"seg01_f{i:02d}.png", 10 * i) for i in range(1, 9)]
        seg = {"index": 1, "source_offset": 4, "held": 4, "new": 6, "frames": 10, "windows": 1}
        out = mtr.write_segment_inputs(self.tmp / "job", seg, tail, (self.W, self.H))
        inits = out["init_frames"]
        self.assertEqual(4, len(inits))
        for src, row in zip(tail[-4:], inits):
            self.assertEqual(src, row["from"])
            self.assertEqual(mtr._sha(Path(src)), row["sha256"])
            self.assertEqual(Path(src).read_bytes(), Path(row["path"]).read_bytes())
        self.assertEqual(sorted(p.name for p in Path(out["init_dir"]).iterdir()),
                         [f"init_{i:05d}.png" for i in range(1, 5)])
        from PIL import Image
        masks = sorted(Path(out["noise_mask_dir"]).iterdir())
        self.assertEqual(10, len(masks))
        values = [Image.open(m).convert("L").getpixel((0, 0)) for m in masks]
        self.assertEqual([0] * 4 + [255] * 6, values)  # black = keep, white = generate
        with self.assertRaises(RuntimeError):
            mtr.write_segment_inputs(self.tmp / "job2", seg, tail[:3], (self.W, self.H))

    def test_stitch_links_delivered_frames_in_order_and_calls_ffmpeg(self):
        frames = [self._png(f"a{i}.png", i) for i in range(6)]
        with patch.object(mtr.subprocess, "run") as run, patch.object(mtr, "_probe", return_value={}):
            out = mtr.stitch_frames(frames, self.tmp / "job", 8)
        linked = sorted(Path(out["frames_dir"]).iterdir())
        self.assertEqual([f"f_{i:05d}.png" for i in range(1, 7)], [p.name for p in linked])
        for src, dst in zip(frames, linked):
            self.assertEqual(Path(src).read_bytes(), dst.read_bytes())
        cmd = run.call_args[0][0]
        self.assertEqual(["ffmpeg", "-v", "error", "-y", "-framerate", "8", "-i"], cmd[:7])
        self.assertTrue(cmd[7].endswith("f_%05d.png"))
        self.assertEqual(6, out["frames_linked"])

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg not installed")
    def test_stitch_with_real_ffmpeg_has_the_frame_count(self):
        frames = [self._png(f"b{i}.png", 20 * i) for i in range(12)]
        out = mtr.stitch_frames(frames, self.tmp / "job", 6)
        self.assertTrue(out["exists"])
        self.assertEqual("12", str(out["ffprobe"]["streams"][0]["nb_frames"]))
        self.assertEqual(64, len(out["sha256"]))

    def test_sequence_metrics_flags_the_seam(self):
        # 8 frames drifting by 4 levels each, except a jump of 40 into frame 4 (the seam)
        values = [0, 4, 8, 12, 52, 56, 60, 64]
        frames = [self._png(f"s{i}.png", v) for i, v in enumerate(values)]
        m = mtr.sequence_metrics(frames, seams=[4], roundtrips=[(frames[3], frames[4])])
        self.assertEqual(8, m["frames"])
        self.assertEqual(7, len(m["f2f"]))
        self.assertAlmostEqual(3.333, m["f2f_median"], places=2)  # R +4, G +2, B -4 -> mean |diff| 10/3
        self.assertEqual(1, len(m["seams"]))
        seam = m["seams"][0]
        self.assertEqual(4, seam["index"])
        self.assertAlmostEqual(33.333, seam["f2f"], places=2)   # R +40, G +20, B -40
        self.assertAlmostEqual(10.0, seam["ratio_to_median"], places=1)
        self.assertAlmostEqual(33.333, m["roundtrip"][0]["mean_abs_diff"], places=2)
        self.assertEqual(8, len(m["mean_rgb"]))
        # a seam index outside the sequence is ignored, an identical pair round-trips to 0
        m2 = mtr.sequence_metrics(frames[:3], seams=[9], roundtrips=[(frames[0], frames[0])])
        self.assertEqual(([], 0.0), (m2["seams"], m2["roundtrip"][0]["mean_abs_diff"]))


class GpuSamplerTests(unittest.TestCase):
    def test_summary_without_and_with_samples(self):
        s = mtr._GpuSampler()
        self.assertEqual((0, None, None), (s.summary()["samples"], s.summary()["peak_mib"], s.summary()["peak_temp_c"]))
        s.mem, s.temp = [100, 15902, 400], [40, 67, 50]
        self.assertEqual((15902, 67), (s.summary()["peak_mib"], s.summary()["peak_temp_c"]))

    def test_sampler_survives_nvidia_smi_failure(self):
        with patch.object(mtr.subprocess, "run", side_effect=OSError("no nvidia-smi")):
            with mtr._GpuSampler() as s:
                pass
        self.assertEqual(0, s.summary()["samples"])


class JobStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.patch = patch.object(mtr, "JOBS_ROOT", self.tmp)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_new_job_and_launch_record(self):
        job_id, job_dir = mtr.new_job({"frames": 8})
        self.assertTrue(job_id.startswith("mtr_"))
        mtr.record_launch(job_dir, 4242)
        status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(("queued", 4242), (status["state"], status["pid"]))

    def test_dead_process_without_manifest(self):
        job_id, job_dir = mtr.new_job({"frames": 8})
        mtr.record_launch(job_dir, 4242)
        with patch.object(mtr, "_pid_alive", return_value=False):
            self.assertEqual("finished_or_crashed", mtr.job_status(job_id)["state"])
        with patch.object(mtr, "_pid_alive", return_value=True):
            self.assertEqual("queued", mtr.job_status(job_id)["state"])

    def test_complete_manifest(self):
        job_id, job_dir = mtr.new_job({"frames": 8})
        (job_dir / "manifest.json").write_text(json.dumps({
            "status": "complete", "verified_outputs": True, "final_video": {"path": "v.mp4", "sha256": "e" * 64},
            "frame_counts": {"planned": 8, "generated": 8}, "identity_check": {"available": True, "mean": 0.17},
            "acceptance": "not accepted"}), encoding="utf-8")
        out = mtr.job_status(job_id)
        self.assertEqual(("complete", True, "v.mp4"), (out["state"], out["verified_outputs"], out["final_video"]["path"]))
        self.assertEqual(0.17, out["identity_check"]["mean"])

    def test_bad_ids(self):
        for bad in ("", "../x", "job_1", "mtr_missing"):
            with self.assertRaises(mtr.RenderRequestError):
                mtr.job_status(bad)

    def test_chained_job_progress_and_completion(self):
        job_id, job_dir = mtr.new_job({"frames": 120, "chained": True, "segments": [{}, {}, {}]})
        seg = {"index": 0, "frames": 40, "held": 0, "new": 40, "verified": True, "render_seconds": 300.0,
               "prompt_id": "p1", "gpu_during_render": {"peak_mib": 15000, "ram_used_gb_peak": 20.5}}
        # in progress: one segment rendered, manifest rewritten, status.json says rendering segment 2
        (job_dir / "manifest.json").write_text(json.dumps({
            "status": "failed", "chained": True, "segments": [seg],
            "settings": {"segments": [{}, {}, {}]}}), encoding="utf-8")
        (job_dir / "status.json").write_text(json.dumps({"job_id": job_id, "state": "rendering", "pid": 1,
                                                          "segment": 2, "segments": 3}), encoding="utf-8")
        with patch.object(mtr, "_pid_alive", return_value=True):
            out = mtr.job_status(job_id)
        self.assertEqual(("rendering", 1, 3, 2), (out["state"], out["segments_done"], out["segments_total"],
                                                  out["segment"]))
        self.assertEqual(20.5, out["segments"][0]["ram_used_gb_peak"])
        self.assertIn("in progress", out["note"])
        # complete: stitched video, seams reported
        (job_dir / "manifest.json").write_text(json.dumps({
            "status": "complete", "chained": True, "verified_outputs": True, "finished_at": "t",
            "final_video": {"path": "final_chained.mp4", "sha256": "e" * 64},
            "frame_counts": {"planned": 120, "delivered": 120, "rendered": 128},
            "segments": [seg, dict(seg, index=1, held=4, frames=44, render_seconds=330.0),
                         dict(seg, index=2, held=4, frames=44, render_seconds=331.0)],
            "settings": {"segments": [{}, {}, {}]},
            "sequence": {"f2f_median": 3.1, "seams": [{"index": 40, "f2f": 3.4, "ratio_to_median": 1.1}]},
            "acceptance": "not accepted"}), encoding="utf-8")
        out = mtr.job_status(job_id)
        self.assertEqual(("complete", True, 3, 3), (out["state"], out["verified_outputs"], out["segments_done"],
                                                   out["segments_total"]))
        self.assertEqual(961.0, out["render_seconds"])
        self.assertEqual(40, out["seams"][0]["index"])


class ToolWrapperTests(_Inputs):
    def setUp(self):
        super().setUp()
        import tools
        self.tools = tools
        self.jobs = self.tmp / "jobs"
        self.patches = [patch.object(mtr, "JOBS_ROOT", self.jobs),
                        patch.object(mt, "probe_video", return_value=_video(path=str(self.video))),
                        patch.object(mt, "probe_image", return_value=_still(str(self.still)))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def _gates(self, busy=False, gate=None, owner=None, ram=None):
        import router
        import gpu_gate
        sys.path.insert(0, str(HERE.parent / "work"))
        import image_render
        # The real free-RAM probe must not decide these tests (a live render beside the suite
        # left 2.6 GB free on 2026-09-26 and three of them failed on RAM instead of the gate).
        ram_probe = ram if callable(ram) else MagicMock(return_value=ram or {"ok": True, "available_gb": 16.0,
                                                                              "needed_gb": 6.5})
        return [patch.object(mtr, "ram_check", ram_probe),
                patch.object(router, "gpu_busy", return_value=(busy, "busy for test", {})),
                patch.object(image_render, "_live_owner", return_value=False),
                patch.object(image_render, "_port_open", return_value=False),
                patch.object(self.tools, "_image_owner_snapshot", return_value=owner or {}),
                patch.object(gpu_gate, "request", return_value=gate or {"granted": True})]

    def _run(self, args, **gates):
        ps = self._gates(**gates)
        for p in ps:
            p.start()
        try:
            return self.tools.call("render_video_from_reference", args)
        finally:
            for p in ps:
                p.stop()

    def test_remote_identity_refused(self):
        with self.assertRaises(self.tools.ToolError):
            self.tools.render_video_from_reference(dict(self.args(), __remote_render_identity="phone-1"))

    def test_busy_gpu_refused(self):
        self.assertIn("preflight refused", self._run(self.args(), busy=True))

    def test_short_ram_refuses_before_anything_starts(self):
        with patch.object(self.tools.subprocess, "Popen") as popen:
            out = self._run(self.args(), ram={"ok": False, "available_gb": 4.0, "needed_gb": 6.5})
        self.assertIn("not enough free system RAM", out)
        popen.assert_not_called()
        self.assertFalse(self.jobs.exists() and any(self.jobs.iterdir()))

    def test_pending_gate_starts_nothing(self):
        out = self._run(self.args(), gate={"granted": False})
        self.assertIn("GPU permission pending", out)
        self.assertFalse(self.jobs.exists() and any(self.jobs.iterdir()))

    def test_launch(self):
        fake = MagicMock(pid=31337)
        with patch.object(self.tools.subprocess, "Popen", return_value=fake) as popen:
            out = json.loads(self._run(self.args()))
        self.assertTrue(out["started"])
        self.assertEqual((63, "768x448"), (out["frames"], out["size"]))
        argv = popen.call_args[0][0]
        self.assertTrue(argv[1].endswith("motion_transfer_render.py"))
        self.assertEqual("--job-dir", argv[2])
        status = json.loads((Path(out["job_dir"]) / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(31337, status["pid"])
        job = json.loads((Path(out["job_dir"]) / "job.json").read_text(encoding="utf-8"))
        self.assertTrue(job["likeness_attestation"])

    def test_long_request_launches_a_chained_job_with_per_segment_ram(self):
        fake = MagicMock(pid=4242)
        seen = {}

        def ram_check(frames):
            seen["frames"] = frames
            return {"ok": True, "available_gb": 16.0, "needed_gb": mtr.ram_needed_gb(frames)}

        long = _video(duration=70.767, width=1920, height=1080, path=str(self.video))
        with patch.object(mt, "probe_video", return_value=long), \
                patch.object(self.tools.subprocess, "Popen", return_value=fake):
            out = json.loads(self._run(self.args(chain=True), ram=ram_check))
        self.assertTrue(out["started"] and out["chained"])
        self.assertEqual((565, 9, 64, 4, 597), (out["frames"], out["segments"], out["segment_frames"],
                                                out["held_frames"], out["rendered_frames"]))
        self.assertEqual(67, seen["frames"])                          # RAM checked for one segment, not 565
        self.assertIn("chained job", out["note"])
        job = json.loads((Path(out["job_dir"]) / "job.json").read_text(encoding="utf-8"))
        self.assertEqual(9, len(job["segments"]))

    def test_status_tool_is_read_only_and_concurrency_safe(self):
        self.assertIn("video_reference_job_status", self.tools.CONCURRENCY_SAFE_TOOLS)
        self.assertNotIn("render_video_from_reference", self.tools.CONCURRENCY_SAFE_TOOLS)
        self.assertIn("render_video_from_reference", self.tools._REMOTE_GPU_TOOLS)


if __name__ == "__main__":
    unittest.main()
