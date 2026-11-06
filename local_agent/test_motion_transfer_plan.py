#!/usr/bin/env python3
"""2026-09-25q Part 2: reference-video motion transfer is planned honestly.

Covers the GVD ``motion_reference`` capability (manifest field, required
capabilities, blocked-route report with named candidates, discovery
allowlist), the read-only planner module (inventory against a fake ComfyUI
tree, frame plan, whole plan), and the whitelisted tool wrapper. No ComfyUI,
no GPU, no network, no downloads.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import motion_transfer as mt  # noqa: E402
import remote_security  # noqa: E402
import tools  # noqa: E402
from gvd_tool_router import discovery  # noqa: E402
from gvd_tool_router.catalog_seed import seed_implementations  # noqa: E402
from gvd_tool_router.paths import GvdLayout  # noqa: E402
from gvd_tool_router.router import required_capabilities  # noqa: E402
from gvd_tool_router.schema import (  # noqa: E402
    CAPABILITY_IDENTITY, CAPABILITY_MOTION_REFERENCE, shot_from_dict)
from gvd_tool_router.service import route_shot  # noqa: E402

SHA = "0" * 63 + "1"
MOTION_IDS = {"wan22_animate_14b_unvalidated", "wan21_vace_1_3b_unvalidated",
              "animatediff_sdxl_pose_ipadapter_unvalidated"}


def _manifest(*, with_character: bool = True, with_motion: bool = True) -> dict:
    m = {
        "shot_id": "MT01", "script_intent": "reference motion, new character",
        "camera_motion": "as reference", "continuity_mode": "identity" if with_character else "independent",
        "character_state": [], "duration_s": 70.8, "width": 1920, "height": 1080,
        "fps_num": 24, "fps_den": 1, "hard_requirements": [], "priorities": {},
    }
    if with_character:
        m["character_state"] = [{
            "character_id": "c1", "revision": "v1",
            "face_refs": [{"asset_id": "face.png", "sha256": SHA, "media_type": "image/png"}],
            "wardrobe_refs": [], "wardrobe_description": "", "props": [],
            "screen_position": "", "pose": "", "expression": ""}]
    if with_motion:
        m["motion_reference_video"] = {"asset_id": "ref.mp4", "sha256": SHA,
                                       "media_type": "video/mp4"}
    return m


class GvdMotionReferenceTests(unittest.TestCase):
    def test_manifest_field_parses_and_requires_capability(self):
        shot = shot_from_dict(_manifest())
        self.assertIsNotNone(shot.motion_reference_video)
        self.assertEqual("ref.mp4", shot.motion_reference_video.asset_id)
        required = required_capabilities(shot)
        self.assertIn(CAPABILITY_MOTION_REFERENCE, required)
        self.assertIn(CAPABILITY_IDENTITY, required)
        plain = shot_from_dict(_manifest(with_motion=False))
        self.assertIsNone(plain.motion_reference_video)
        self.assertNotIn(CAPABILITY_MOTION_REFERENCE, required_capabilities(plain))

    def test_motion_without_named_character_needs_no_identity(self):
        shot = shot_from_dict(_manifest(with_character=False))
        required = required_capabilities(shot)
        self.assertIn(CAPABILITY_MOTION_REFERENCE, required)
        self.assertNotIn(CAPABILITY_IDENTITY, required)

    def test_route_is_blocked_with_named_missing_capability_and_candidates(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            out = route_shot(_manifest(), GvdLayout(tmp))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual("blocked", out["status"])
        self.assertIn("UNAVAILABLE_CAPABILITY", out["reason_codes"])
        self.assertIn(CAPABILITY_MOTION_REFERENCE, out["missing_capabilities"])
        by_id = {c["implementation_id"]: c for c in out["blocked_candidates"]}
        self.assertTrue(MOTION_IDS <= set(by_id))
        for impl_id in MOTION_IDS:
            row = by_id[impl_id]
            self.assertEqual("disabled", row["status"])
            self.assertIn(CAPABILITY_MOTION_REFERENCE, row["covers"])
            self.assertTrue(row["disabled_reason"])
            self.assertTrue(row["provenance_urls"])
        # The weights-complete path names its one missing node pack; the two
        # others name a weight size.
        self.assertIn("ComfyUI-Advanced-ControlNet",
                      by_id["animatediff_sdxl_pose_ipadapter_unvalidated"]["disabled_reason"])
        self.assertIn("~17 GB", by_id["wan22_animate_14b_unvalidated"]["disabled_reason"])
        self.assertIn("~1.2 GB", by_id["wan21_vace_1_3b_unvalidated"]["disabled_reason"])

    def test_selected_route_carries_no_blocked_report(self):
        # A still request with the seeded known-good SDXL implementation
        # should still route exactly as before: no blocked_* keys on success.
        tmp = Path(tempfile.mkdtemp())
        try:
            from gvd_tool_router.service import ensure_control_plane
            layout = ensure_control_plane(GvdLayout(tmp))
            from gvd_tool_router.registry import Registry
            reg = Registry(layout)
            still = next(i for i in reg.implementations()
                         if i.implementation_id == "known_good_sdxl_txt2img_v1")
            from dataclasses import replace
            reg.promote([replace(still, status="active")], allow_unvalidated=True)
            out = route_shot({
                "shot_id": "S01", "script_intent": "still", "camera_motion": "static",
                "character_state": [], "continuity_mode": "independent",
                "duration_s": 1, "width": 512, "height": 512, "fps_num": 24, "fps_den": 1,
                "hard_requirements": ["still_generation"], "priorities": {}}, layout)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if out["status"] == "selected":
            self.assertNotIn("blocked_candidates", out)
        else:
            # Promotion may be refused by policy in this environment; the
            # blocked report must then still be well-formed.
            self.assertIn("missing_capabilities", out)

    def test_seed_rows_are_disabled_narrative_scene_with_motion_capability(self):
        rows = {i.implementation_id: i for i in seed_implementations()}
        self.assertTrue(MOTION_IDS <= set(rows))
        for impl_id in MOTION_IDS:
            impl = rows[impl_id]
            self.assertEqual("execute_narrative_scene", impl.tool_name)
            self.assertEqual("disabled", impl.status)
            self.assertIn(CAPABILITY_MOTION_REFERENCE, impl.capabilities)
            self.assertIn(CAPABILITY_IDENTITY, impl.capabilities)
            self.assertEqual((), impl.profiles)

    def test_discovery_allows_the_capability(self):
        self.assertIn("motion_reference", discovery.ALLOWED_CAPABILITIES)


class _FakeTree:
    """A ComfyUI checkout + model tree the planner can inventory."""

    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.custom_nodes = self.tmp / "ComfyUI" / "custom_nodes"
        self.models = self.tmp / "models"
        self.config = self.tmp / "paths.yaml"
        folders = ("checkpoints", "loras", "controlnet", "clip_vision", "ipadapter",
                   "text_encoders", "vae", "animatediff_models", "diffusion_models")
        for f in folders:
            (self.models / f).mkdir(parents=True, exist_ok=True)
        self.config.write_text(
            "fake:\n  base_path: '%s'\n" % str(self.models).replace("\\", "\\\\")
            + "".join(f"  {f}: '{f}/'\n" for f in folders if f != "diffusion_models")
            + "  unet: 'diffusion_models/'\n", encoding="utf-8")

    def node(self, name: str) -> None:
        (self.custom_nodes / name).mkdir(parents=True, exist_ok=True)

    def aux(self, rel: str) -> None:
        p = self.custom_nodes / "comfyui_controlnet_aux" / "ckpts" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")

    def weight(self, folder: str, name: str) -> None:
        (self.models / folder / name).write_bytes(b"x")

    def install_animatediff_stack(self) -> None:
        for n in ("ComfyUI-AnimateDiff-Evolved", "comfyui_controlnet_aux",
                  "comfyui_ipadapter_plus", "ComfyUI-VideoHelperSuite",
                  "ComfyUI-Advanced-ControlNet"):
            self.node(n)
        for rel in mt.DWPOSE_CKPTS:
            self.aux(rel)
        self.weight("checkpoints", "sd_xl_base_1.0_0.9vae.safetensors")
        self.weight("animatediff_models", "mm_sdxl_v10_beta.ckpt")
        self.weight("controlnet", "controlnet-union-sdxl-1.0-promax.safetensors")
        self.weight("ipadapter", "ip-adapter-plus-face_sdxl_vit-h.safetensors")
        self.weight("clip_vision", "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors")

    def install_wan_common(self) -> None:
        self.node("ComfyUI-WanVideoWrapper")
        self.weight("text_encoders", "umt5_xxl_fp8_e4m3fn_scaled.safetensors")
        self.weight("vae", "wan_2.1_vae.safetensors")
        self.weight("clip_vision", "clip_vision_h.safetensors")
        self.weight("diffusion_models", "wan2.1_t2v_1.3B_fp16.safetensors")

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)


class PlannerInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tree = _FakeTree()

    def tearDown(self):
        self.tree.close()

    def _inv(self) -> dict[str, dict]:
        rows = mt.inventory(custom_nodes=self.tree.custom_nodes, config_path=self.tree.config)
        return {r["id"]: r for r in rows}

    def test_empty_tree_reports_everything_missing(self):
        inv = self._inv()
        self.assertEqual({"wan22_animate_14b", "wan21_vace_1_3b", "animatediff_sdxl_pose_ipadapter"},
                         set(inv))
        for row in inv.values():
            self.assertFalse(row["feasible_now"])
            self.assertTrue(row["missing"])
            self.assertEqual([], row["installed"])
        self.assertGreaterEqual(inv["wan22_animate_14b"]["download_gb_to_enable"], 17.0)

    def test_full_animatediff_stack_is_feasible_now(self):
        self.tree.install_animatediff_stack()
        inv = self._inv()
        row = inv["animatediff_sdxl_pose_ipadapter"]
        self.assertTrue(row["feasible_now"], row["missing"])
        self.assertEqual([], row["missing"])
        self.assertEqual(0, row["download_gb_to_enable"])
        kinds = {m["kind"] for m in row["installed"]}
        self.assertEqual({"custom_node", "preprocessor_weight", "model_weight"}, kinds)
        self.assertFalse(inv["wan22_animate_14b"]["feasible_now"])
        # Without the Advanced-ControlNet pack the weights alone are not enough
        # (live 2026-09-25: sliding context window refused core ControlNet nodes).
        shutil.rmtree(self.tree.custom_nodes / "ComfyUI-Advanced-ControlNet")
        row = self._inv()["animatediff_sdxl_pose_ipadapter"]
        self.assertFalse(row["feasible_now"])
        self.assertEqual([{"kind": "custom_node", "name": "ComfyUI-Advanced-ControlNet"}], row["missing"])
        self.assertEqual(0, row["download_gb_to_enable"])

    def test_wan_paths_need_exactly_the_named_weight(self):
        self.tree.install_wan_common()
        self.tree.node("comfyui_controlnet_aux")
        self.tree.node("ComfyUI-VideoHelperSuite")
        for rel in mt.DWPOSE_CKPTS:
            self.tree.aux(rel)
        inv = self._inv()
        animate = inv["wan22_animate_14b"]
        self.assertFalse(animate["feasible_now"])
        required_missing = [m for m in animate["missing"] if not m.get("optional")]
        self.assertEqual(1, len(required_missing))
        self.assertEqual("diffusion_models", required_missing[0]["folder"])
        self.assertEqual(17.0, required_missing[0]["approx_gb"])
        self.assertIn("Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors",
                      required_missing[0]["accepted_names"])
        optional_missing = [m for m in animate["missing"] if m.get("optional")]
        self.assertEqual(1, len(optional_missing))  # the relight LoRA
        self.assertEqual(17.0, animate["download_gb_to_enable"])  # optional not counted
        vace = inv["wan21_vace_1_3b"]
        self.assertFalse(vace["feasible_now"])
        self.assertEqual(1.2, vace["download_gb_to_enable"])
        # Drop the missing weights in -> feasible, nothing else changes.
        self.tree.weight("diffusion_models", "Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors")
        self.tree.weight("diffusion_models", "Wan2_1-VACE_module_1_3B_bf16.safetensors")
        inv = self._inv()
        self.assertTrue(inv["wan22_animate_14b"]["feasible_now"])
        self.assertTrue(inv["wan21_vace_1_3b"]["feasible_now"])

    def test_frame_plan_covers_the_whole_clip(self):
        plan = mt.frame_plan(70.767, {"target_fps": 16, "window_frames": 81, "overlap_frames": 5})
        self.assertEqual(1133, plan["output_frames"])   # ceil(70.767 * 16)
        self.assertEqual(15, plan["windows"])           # 1 + ceil((1133-81)/76)
        short = mt.frame_plan(3.0, {"target_fps": 8, "window_frames": 16, "overlap_frames": 4})
        self.assertEqual(24, short["output_frames"])
        self.assertEqual(2, short["windows"])
        one = mt.frame_plan(1.0, {"target_fps": 8, "window_frames": 16, "overlap_frames": 4})
        self.assertEqual(1, one["windows"])
        custom = mt.frame_plan(10.0, {"target_fps": 16, "window_frames": 81, "overlap_frames": 5},
                               target_fps=24)
        self.assertEqual(24.0, custom["target_fps"])
        self.assertEqual(240, custom["output_frames"])


class PlannerPlanTests(unittest.TestCase):
    def setUp(self):
        self.tree = _FakeTree()
        self.tree.install_animatediff_stack()
        self.video = self.tree.tmp / "ref.mp4"
        self.video.write_bytes(b"\x00" * 128)
        self.image = self.tree.tmp / "char.png"
        from PIL import Image
        Image.new("RGB", (64, 32), (200, 100, 50)).save(self.image)
        self.gvd_root = Path(tempfile.mkdtemp())
        self.probe = patch.object(mt, "probe_video", return_value={
            "path": str(self.video), "duration_s": 70.767, "fps": 60.0, "width": 1920,
            "height": 1080, "source_frames": 4246, "size_bytes": 128,
            "sha256": SHA, "audio_streams": 1})
        self.probe.start()

    def tearDown(self):
        self.probe.stop()
        self.tree.close()
        shutil.rmtree(self.gvd_root, ignore_errors=True)

    def _plan(self, **kw):
        return mt.plan(self.video, self.image, custom_nodes=self.tree.custom_nodes,
                       config_path=self.tree.config, gvd_layout=GvdLayout(self.gvd_root), **kw)

    def test_plan_reports_feasible_now_missing_and_gvd_route(self):
        out = self._plan()
        self.assertTrue(out["planned"])
        self.assertFalse(out["rendered"])
        self.assertEqual(70.767, out["reference_video"]["duration_s"])
        self.assertEqual(64, out["character_image"]["width"])
        self.assertEqual(64, len(out["character_image"]["sha256"]))
        self.assertEqual("animatediff_sdxl_pose_ipadapter", out["recommended_now"])
        self.assertEqual("wan22_animate_14b", out["best_with_download"])
        self.assertEqual(2, len(out["operator_decisions_needed"]))
        self.assertTrue(any("~17.0 GB" in d for d in out["operator_decisions_needed"]))
        self.assertTrue(any("~1.2 GB" in d for d in out["operator_decisions_needed"]))
        by_id = {a["id"]: a for a in out["approaches"]}
        self.assertEqual(567, by_id["animatediff_sdxl_pose_ipadapter"]["frame_plan"]["output_frames"])
        self.assertEqual(1133, by_id["wan22_animate_14b"]["frame_plan"]["output_frames"])
        self.assertEqual("blocked", out["gvd_route"]["status"])
        self.assertIn("motion_reference", out["gvd_route"]["missing_capabilities"])
        self.assertTrue(MOTION_IDS <= {c["implementation_id"]
                                       for c in out["gvd_route"]["blocked_candidates"]})
        self.assertIn("nothing was rendered", out["note"].lower())

    def test_target_fps_override_flows_into_every_frame_plan(self):
        out = self._plan(target_fps=12)
        for row in out["approaches"]:
            self.assertEqual(12.0, row["frame_plan"]["target_fps"])
            self.assertEqual(850, row["frame_plan"]["output_frames"])

    def test_bad_inputs_are_plan_errors(self):
        with self.assertRaises(mt.PlanError):
            mt.plan("", self.image, custom_nodes=self.tree.custom_nodes,
                    config_path=self.tree.config, gvd_layout=GvdLayout(self.gvd_root))
        with self.assertRaises(mt.PlanError):
            mt.plan(self.video, self.tree.tmp / "missing.png",
                    custom_nodes=self.tree.custom_nodes, config_path=self.tree.config,
                    gvd_layout=GvdLayout(self.gvd_root))
        wrong = self.tree.tmp / "notes.txt"
        wrong.write_text("x")
        with self.assertRaises(mt.PlanError):
            mt.plan(wrong, self.image, custom_nodes=self.tree.custom_nodes,
                    config_path=self.tree.config, gvd_layout=GvdLayout(self.gvd_root))

    def test_gvd_manifest_is_identity_mode_with_motion_reference(self):
        m = mt.gvd_manifest(
            {"path": str(self.video), "duration_s": 70.767, "width": 1920, "height": 1080,
             "sha256": SHA},
            {"path": str(self.image), "sha256": SHA})
        shot = shot_from_dict(m)
        self.assertEqual("identity", shot.continuity_mode)
        self.assertEqual(1, len(shot.character_state))
        self.assertIsNotNone(shot.motion_reference_video)
        self.assertIn(CAPABILITY_MOTION_REFERENCE, required_capabilities(shot))


class ToolWrapperTests(unittest.TestCase):
    def test_registered_read_only_and_phone_visible(self):
        self.assertIn("plan_video_from_reference", tools.TOOLS)
        self.assertIn("plan_video_from_reference", tools.CONCURRENCY_SAFE_TOOLS)
        self.assertIn("plan_video_from_reference", remote_security.REMOTE_DEFAULT_TOOLS)
        names = {s["function"]["name"] for s in tools.schemas()}
        self.assertIn("plan_video_from_reference", names)
        desc = tools.TOOLS["plan_video_from_reference"][1]
        self.assertIn("never renders", desc)

    def test_missing_arguments_are_errors_not_exceptions(self):
        self.assertTrue(tools.call("plan_video_from_reference", {}).startswith("ERROR:"))
        self.assertTrue(tools.call("plan_video_from_reference",
                                   {"reference_video": "nope.mp4"}).startswith("ERROR:"))
        out = tools.call("plan_video_from_reference",
                         {"reference_video": "nope.mp4", "character_image": "nope.png"})
        self.assertTrue(out.startswith("ERROR:"))
        self.assertIn("not found", out)

    def test_wrapper_returns_plan_json(self):
        fake = {"planned": True, "rendered": False, "approaches": []}
        with patch.object(mt, "plan", return_value=fake) as planned:
            out = json.loads(tools.call("plan_video_from_reference",
                                        {"reference_video": "a.mp4", "character_image": "b.png",
                                         "target_fps": "12"}))
        self.assertEqual(fake, out)
        self.assertEqual(12.0, planned.call_args.kwargs["target_fps"])


class LiveInventorySmokeTests(unittest.TestCase):
    """This machine, read-only: what the 2026-09-25q investigation found."""

    def test_this_install_state(self):
        import mcp_client
        nodes = Path(mcp_client.COMFYUI_CODE_PATH) / "custom_nodes"
        if not nodes.is_dir():
            self.skipTest(f"no ComfyUI checkout at {nodes}")
        inv = {r["id"]: r for r in mt.inventory()}
        ad = inv["animatediff_sdxl_pose_ipadapter"]
        # Every weight is on disk; the only thing that may be missing is the
        # Advanced-ControlNet node pack (live finding 2026-09-25, 24-frame run).
        self.assertFalse([m for m in ad["missing"] if m["kind"] == "model_weight"], ad["missing"])
        self.assertTrue(set(m["name"] for m in ad["missing"] if m["kind"] == "custom_node")
                        <= {"ComfyUI-Advanced-ControlNet"}, ad["missing"])
        for wan in ("wan22_animate_14b", "wan21_vace_1_3b"):
            row = inv[wan]
            if row["feasible_now"]:
                continue  # weights were downloaded after this test was written
            missing_folders = {m["folder"] for m in row["missing"]
                               if m["kind"] == "model_weight" and not m.get("optional")}
            self.assertEqual({"diffusion_models"}, missing_folders)


if __name__ == "__main__":
    unittest.main()
