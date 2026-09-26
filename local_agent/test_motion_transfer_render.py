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

    def test_long_clip_refused_with_section_hint(self):
        with self.assertRaises(mtr.RenderRequestError) as ctx:
            self.prepare(video=_video(duration=70.767, width=1920, height=1080, path=str(self.video)))
        self.assertIn("max_seconds", str(ctx.exception))
        self.assertIn("64 frames", str(ctx.exception))

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

    def _gates(self, busy=False, gate=None, owner=None):
        import router
        import gpu_gate
        sys.path.insert(0, str(HERE.parent / "work"))
        import image_render
        return [patch.object(router, "gpu_busy", return_value=(busy, "busy for test", {})),
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

    def test_status_tool_is_read_only_and_concurrency_safe(self):
        self.assertIn("video_reference_job_status", self.tools.CONCURRENCY_SAFE_TOOLS)
        self.assertNotIn("render_video_from_reference", self.tools.CONCURRENCY_SAFE_TOOLS)
        self.assertIn("render_video_from_reference", self.tools._REMOTE_GPU_TOOLS)


if __name__ == "__main__":
    unittest.main()
