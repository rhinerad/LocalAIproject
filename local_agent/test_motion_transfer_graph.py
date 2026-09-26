#!/usr/bin/env python3
"""Pinned motion-transfer templates and their builder (no GPU, no ComfyUI).

Offline validation uses the live node schemas dumped on 2026-09-25
(runtime/motion_transfer_20260925/node_schemas_pass2.json) for every class
that dump contains; the classes it lacks are validated live by the runner.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import motion_transfer_graph as mg

SCHEMAS = HERE / "runtime" / "motion_transfer_20260925" / "node_schemas_pass2.json"


def _stage2(**over):
    base = dict(reference_video=r"A:\clip.mp4", frame_cap=24, skip_first=0, force_fps=8,
                width=768, height=448, character_face_image="face.png",
                masks_dir=r"A:\masks", positive="a man in a cardigan", negative=None,
                seed=7, prefix="mcp_test/job1",
                face_rule={"mode": "ordered", "target": "x1", "order": False, "take_count": 1})
    base.update(over)
    return mg.build_stage2(**base)


class TemplateTests(unittest.TestCase):

    def test_templates_are_pinned_by_sha256(self):
        for name, want in mg.TEMPLATE_SHA256.items():
            self.assertEqual(want, mg.template_sha256(name), name)

    def test_placeholders_are_the_documented_set(self):
        self.assertEqual({"REFERENCE_VIDEO", "FORCE_FPS", "FRAME_CAP", "SKIP_FIRST", "PREFIX"},
                         mg.placeholders(mg.STAGE1))
        self.assertEqual({"REFERENCE_VIDEO", "FORCE_FPS", "FRAME_CAP", "SKIP_FIRST", "PREFIX",
                          "WIDTH", "HEIGHT", "CHARACTER_FACE_IMAGE", "MASKS_DIR", "POSITIVE",
                          "NEGATIVE", "SEED", "STEPS", "CFG", "FD_POSITIVE", "FD_NEGATIVE",
                          "FD_DENOISE", "FACE_TARGET", "FACE_ORDER", "FACE_TAKE"},
                         mg.placeholders(mg.STAGE2))

    def test_pinned_settings_match_the_template(self):
        g = _stage2()
        self.assertEqual(mg.PINNED["checkpoint"], g["10"]["inputs"]["ckpt_name"])
        self.assertEqual(mg.PINNED["motion_module"], g["11"]["inputs"]["model_name"])
        self.assertEqual(mg.PINNED["beta_schedule"], g["11"]["inputs"]["beta_schedule"])
        self.assertEqual(16, g["12"]["inputs"]["context_length"])
        self.assertEqual(4, g["12"]["inputs"]["context_overlap"])
        self.assertEqual("disable", g["2"]["inputs"]["detect_face"])      # 25t root cause
        self.assertEqual("enable", g["2"]["inputs"]["scale_stick_for_xinsr_cn"])
        self.assertEqual("openpose", g["19"]["inputs"]["type"])
        self.assertEqual(0.8, g["20"]["inputs"]["strength"])
        self.assertEqual("PLUS FACE (portraits)", g["13"]["inputs"]["preset"])
        self.assertEqual(["27", 0], g["15"]["inputs"]["attn_mask"])
        self.assertEqual("FACEID PLUS V2", g["50"]["inputs"]["preset"])
        self.assertEqual(["50", 0], g["43"]["inputs"]["model"])
        self.assertEqual("IPAdapterFaceID", g["43"]["class_type"])
        self.assertEqual(0.5, g["47"]["inputs"]["denoise"])
        self.assertEqual("bbox/face_yolov8m.pt", g["40"]["inputs"]["model_name"])


class BuilderTests(unittest.TestCase):

    def test_stage1_fills_every_token_with_typed_values(self):
        g = mg.build_stage1(reference_video=r"A:\clip.mp4", frame_cap=24, skip_first=48,
                            force_fps=8, prefix="mcp_test/job1")
        self.assertEqual(r"A:\clip.mp4", g["1"]["inputs"]["video"])
        self.assertEqual(24, g["1"]["inputs"]["frame_load_cap"])
        self.assertEqual(48, g["1"]["inputs"]["skip_first_frames"])
        self.assertEqual(8, g["1"]["inputs"]["force_rate"])
        self.assertEqual("mcp_test/job1/pose_kps", g["5"]["inputs"]["filename_prefix"])
        self.assertEqual(["2", 1], g["5"]["inputs"]["pose_kps"])
        self.assertNotIn("{{", json.dumps(g))

    def test_stage2_fills_every_token_with_typed_values(self):
        g = _stage2(seed=123, steps=12, cfg=5.5, fd_denoise=0.35)
        self.assertNotIn("{{", json.dumps(g))
        self.assertEqual(24, g["21"]["inputs"]["batch_size"])
        self.assertEqual(768, g["21"]["inputs"]["width"])
        self.assertEqual(123, g["22"]["inputs"]["seed"])
        self.assertEqual(12, g["22"]["inputs"]["steps"])
        self.assertEqual(5.5, g["22"]["inputs"]["cfg"])
        self.assertEqual(0.35, g["47"]["inputs"]["denoise"])
        self.assertEqual(r"A:\masks", g["26"]["inputs"]["directory"])
        self.assertEqual(24, g["26"]["inputs"]["image_load_cap"])
        self.assertEqual("face.png", g["14"]["inputs"]["image"])
        self.assertEqual(mg.DEFAULTS["negative"], g["17"]["inputs"]["text"])
        self.assertEqual(mg.DEFAULTS["fd_positive"], g["44"]["inputs"]["text"])
        self.assertEqual("x1", g["42"]["inputs"]["target"])
        self.assertIs(False, g["42"]["inputs"]["order"])
        self.assertEqual(1, g["42"]["inputs"]["take_count"])
        self.assertEqual("ImpactSEGSOrderedFilter", g["42"]["class_type"])
        self.assertNotIn("28", g)

    def test_area_rule_uses_impacts_target_name(self):
        g = _stage2(face_rule={"mode": "ordered", "target": "area", "order": True, "take_count": 1})
        self.assertEqual("area(=w*h)", g["42"]["inputs"]["target"])
        self.assertIs(True, g["42"]["inputs"]["order"])

    def test_union_rule_swaps_the_filter_for_a_mask_intersection(self):
        g = _stage2(face_rule={"mode": "union_mask"}, union_mask_dir=r"A:\masks\union")
        self.assertEqual("ImpactSegsAndMask", g["42"]["class_type"])
        self.assertEqual(["41", 0], g["42"]["inputs"]["segs"])
        self.assertEqual(["29", 0], g["42"]["inputs"]["mask"])
        self.assertEqual(r"A:\masks\union", g["28"]["inputs"]["directory"])
        self.assertEqual(["42", 0], g["47"]["inputs"]["segs"])
        with self.assertRaises(mg.TemplateError):
            _stage2(face_rule={"mode": "union_mask"})

    def test_bad_inputs_are_template_errors(self):
        for over in (dict(frame_cap=0), dict(frame_cap=65), dict(force_fps=0), dict(width=770),
                     dict(character_face_image=r"A:\face.png"), dict(positive=""), dict(seed=0),
                     dict(prefix="noslash"), dict(prefix="../x/y"),
                     dict(face_rule={"mode": "ordered", "target": "z1"}),
                     dict(face_rule={"mode": "nope"}), dict(steps=0), dict(fd_denoise=1.5)):
            with self.assertRaises(mg.TemplateError, msg=str(over)):
                _stage2(**over)

    def test_unfilled_placeholder_is_refused(self):
        with self.assertRaises(mg.TemplateError):
            mg._fill(mg.STAGE1, {"REFERENCE_VIDEO": "x"})


class OfflineSchemaValidationTests(unittest.TestCase):
    """Every node class present in the 2026-09-25 live schema dump validates;
    classes absent from that dump are listed so the live check knows what
    it still has to cover."""

    @classmethod
    def setUpClass(cls):
        cls.info = json.loads(SCHEMAS.read_text(encoding="utf-8")) if SCHEMAS.is_file() else {}

    def _check(self, graph):
        if not self.info:
            self.skipTest("no schema dump")
        # LoadImage's "image" combo is the input-directory listing at dump
        # time, not a schema; the runner checks the file live.
        known = {k: v for k, v in graph.items()
                 if v["class_type"] in self.info and v["class_type"] != "LoadImage"}
        problems = mg.validate_graph(known, self.info)
        self.assertEqual([], problems)
        return sorted({v["class_type"] for v in graph.values()} - set(self.info))

    def test_stage1_known_classes_validate(self):
        g = mg.build_stage1(reference_video=r"A:\clip.mp4", frame_cap=24, skip_first=0,
                            force_fps=8, prefix="mcp_test/job1")
        unknown = self._check(g)
        self.assertEqual(["SavePoseKpsAsJsonFile"], unknown)

    def test_stage2_known_classes_validate(self):
        unknown = self._check(_stage2())
        # Classes outside the 2026-09-25 dump: validated live by the runner.
        self.assertEqual(sorted({
            "DetailerForEachPipeForAnimateDiff", "ImageToMask", "ImpactSEGSOrderedFilter",
            "ImpactSimpleDetectorSEGS_for_AD", "ToBasicPipe", "UltralyticsDetectorProvider",
            "VHS_LoadImagesPath"}), unknown)


if __name__ == "__main__":
    unittest.main()
