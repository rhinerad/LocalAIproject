from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import image_render as ir


INFO = {name: {"input": {"required": {key: ["X", {}] for key in keys}}}
        for name, keys in {**ir.REQUIRED_T2I, **ir.REQUIRED_I2I}.items()}


class ImageGraphTests(unittest.TestCase):
    def test_sdxl_lora_routes_model_and_clip_but_preserves_vae(self):
        args = dict(mode='t2i', prompt='room', negative='bad hands', model='model.safetensors',
                    seed=42, width=1024, height=768, steps=28, cfg=6,
                    sampler='dpmpp_2m_sde', scheduler='karras', denoise=1, prefix='test')
        graph = ir.build_graph(**args, lora_name='background.safetensors', lora_strength=0.5)
        self.assertEqual(graph['5']['inputs']['model'], ['15', 0])
        self.assertEqual(graph['10']['inputs']['model'], ['15', 0])
        self.assertEqual(graph['2']['inputs']['clip'], ['15', 1])
        self.assertEqual(graph['6']['inputs']['vae'], ['1', 2])
        with self.assertRaises(ir.ImageRenderError):
            ir.build_graph(**args, lora_name='../escape.safetensors')
        with self.assertRaises(ir.ImageRenderError):
            ir.build_graph(**args, profile='realpro_flux', lora_name='background.safetensors')

    def test_t2i_graph_uses_core_nodes_and_seed(self):
        ir.validate_nodes(INFO, "t2i")
        graph = ir.build_graph(mode="t2i", prompt="studio portrait", negative="bad hands",
                               model="model.safetensors", seed=42, width=1024, height=1024,
                               steps=28, cfg=6, sampler="dpmpp_2m_sde", scheduler="karras",
                               denoise=1, prefix="stories/test/renders/a")
        self.assertEqual("CheckpointLoaderSimple", graph["1"]["class_type"])
        self.assertEqual(42, graph["5"]["inputs"]["seed"])
        self.assertEqual("EmptyLatentImage", graph["4"]["class_type"])

    def test_face_detail_graph_repairs_only_detected_faces(self):
        info = dict(INFO)
        info.update({name: {"input": {"required": {key: ["X", {}] for key in keys}}}
                     for name, keys in ir.REQUIRED_FACE_DETAIL.items()})
        ir.validate_nodes(info, "t2i", face_detail=True)
        graph = ir.build_graph(mode="t2i", prompt="two adults", negative="bad face",
                               model="model.safetensors", seed=42, width=896, height=1152,
                               steps=35, cfg=6, sampler="dpmpp_2m_sde", scheduler="karras",
                               denoise=1, prefix="stories/test/renders/a", face_detail=True)
        self.assertEqual("UltralyticsDetectorProvider", graph["11"]["class_type"])
        self.assertEqual(ir.FACE_DETAIL_MODEL, graph["11"]["inputs"]["model_name"])
        self.assertEqual("FaceDetailer", graph["12"]["class_type"])
        self.assertEqual(["12", 0], graph["7"]["inputs"]["images"])
        self.assertEqual(0.30, graph["12"]["inputs"]["denoise"])

    def test_realpro_flux_is_a_separate_unet_graph(self):
        info = {name: {"input": {"required": {key: ["X", {}] for key in keys}}}
                for name, keys in ir.REQUIRED_FLUX_T2I.items()}
        ir.validate_nodes(info, "t2i", profile="realpro_flux")
        graph = ir.build_graph(mode="t2i", prompt="photoreal portrait", negative="ignored",
                               model=ir.REALPRO_FLUX_UNET, seed=42, width=896, height=1152,
                               steps=28, cfg=6, sampler="dpmpp_2m_sde", scheduler="karras",
                               denoise=1, prefix="stories/test/renders/a", profile="realpro_flux")
        self.assertEqual("UNETLoader", graph["1"]["class_type"])
        self.assertEqual("DualCLIPLoader", graph["2"]["class_type"])
        self.assertEqual("flux", graph["2"]["inputs"]["type"])
        self.assertEqual("ae.safetensors", graph["3"]["inputs"]["vae_name"])
        self.assertEqual("CLIPTextEncodeFlux", graph["4"]["class_type"])
        self.assertEqual(1.0, graph["7"]["inputs"]["cfg"])

    def test_i2i_uses_vae_encode_and_requires_reference(self):
        graph = ir.build_graph(mode="i2i", prompt="portrait", negative="", model="m",
                               seed=1, width=1024, height=1024, steps=20, cfg=6,
                               sampler="euler", scheduler="normal", denoise=.55,
                               prefix="stories/test/renders/a", reference_name="photo.png")
        self.assertEqual("VAEEncode", graph["4"]["class_type"])
        self.assertEqual("photo.png", graph["8"]["inputs"]["image"])
        with self.assertRaises(ir.ImageRenderError):
            ir.build_graph(mode="i2i", prompt="portrait", negative="", model="m", seed=1,
                           width=1024, height=1024, steps=20, cfg=6, sampler="euler",
                           scheduler="normal", denoise=.5, prefix="x")

    def test_i2i_identity_routes_sampler_through_ipadapter(self):
        info = dict(INFO)
        info.update({name: {"input": {"required": {key: ["X", {}] for key in keys}}}
                     for name, keys in ir.REQUIRED_IDENTITY_I2I.items()})
        ir.validate_nodes(info, "i2i_identity")
        graph = ir.build_graph(
            mode="i2i_identity", prompt="same actor resets", negative="different actor",
            model="m", seed=1, width=1024, height=768, steps=20, cfg=6,
            sampler="euler", scheduler="normal", denoise=.50,
            prefix="stories/test/renders/identity", reference_name="previous.png",
            identity_name="face.png", identity_weight=.90,
        )
        self.assertEqual(graph["4"]["class_type"], "VAEEncode")
        self.assertEqual(graph["8"]["inputs"]["image"], "previous.png")
        self.assertEqual(graph["18"]["inputs"]["image"], "face.png")
        self.assertEqual(graph["17"]["class_type"], "IPAdapterAdvanced")
        self.assertEqual(graph["17"]["inputs"]["weight"], .90)
        self.assertEqual(graph["17"]["inputs"]["ipadapter"], ["15", 1])
        self.assertEqual(graph["5"]["inputs"]["model"], ["17", 0])

    def test_missing_live_input_is_a_safe_refusal(self):
        broken = dict(INFO)
        broken["KSampler"] = {"input": {"required": {}}}
        with self.assertRaises(ir.ImageRenderError):
            ir.validate_nodes(broken, "t2i")

    def test_plan_is_read_only_and_validates_live_catalogue(self):
        args = ["--story", "demo", "--prompt", "a studio portrait", "--plan"]
        with patch.object(ir, "object_info", return_value=INFO), patch("builtins.print") as output:
            self.assertEqual(0, ir.main(args))
        self.assertIn('"status": "planned"', output.call_args.args[0])

    def test_execute_requires_explicit_model_load_flag_before_any_backend_action(self):
        with self.assertRaises(ir.ImageRenderError) as caught:
            ir.main(["--story", "demo", "--prompt", "portrait", "--execute"])
        self.assertIn("--allow-model-load", str(caught.exception))


    def test_extra_model_paths_empty_segment_is_a_noop(self):
        """ComfyUI skips empty path segments; '' must not mean base_path."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models = root / "models"
            models.mkdir()
            cfg = root / "paths.yaml"
            cfg.write_text(
                "broken:\n"
                f"  base_path: {str(models)!r}\n"
                "  diffusion_models: ''\n",
                encoding="utf-8",
            )
            self.assertEqual([], ir.iter_extra_model_folder_paths("diffusion_models", config_path=cfg))

    def test_extra_model_paths_dot_registers_base_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models = root / "models"
            models.mkdir()
            target = models / "realProV3_realProV3Unet.safetensors"
            target.write_bytes(b"fake")
            cfg = root / "paths.yaml"
            cfg.write_text(
                "realpro:\n"
                f"  base_path: {str(models)!r}\n"
                "  diffusion_models: '.'\n",
                encoding="utf-8",
            )
            dirs = ir.iter_extra_model_folder_paths("diffusion_models", config_path=cfg)
            self.assertEqual([models.resolve()], dirs)
            hit = ir.assert_configured_model_visible(
                "realProV3_realProV3Unet.safetensors", "diffusion_models", config_path=cfg
            )
            self.assertEqual(target.resolve(), hit)

    def test_configured_model_lookup_preserves_safe_nested_catalogue_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            models = root / "models"
            target = models / "bbox" / "hand_yolov8s.pt"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"fake")
            cfg = root / "paths.yaml"
            cfg.write_text(
                "ultralytics_test:\n"
                f"  base_path: {str(models)!r}\n"
                "  ultralytics: '.'\n",
                encoding="utf-8",
            )
            hit = ir.assert_configured_model_visible(
                "bbox/hand_yolov8s.pt", "ultralytics", config_path=cfg
            )
            self.assertEqual(target.resolve(), hit)

    def test_live_realpro_yaml_sees_operator_unet(self):
        """Regression: RealPro lives under Downloads subfolder, not Downloads root."""
        if not ir.MODEL_PATHS.is_file():
            self.skipTest("image_render_model_paths.yaml missing")
        dirs = ir.iter_extra_model_folder_paths("diffusion_models")
        self.assertTrue(dirs, "expected at least one diffusion_models search dir")
        hit = ir.model_file_on_configured_paths(ir.REALPRO_FLUX_UNET, "diffusion_models")
        self.assertIsNotNone(
            hit,
            f"{ir.REALPRO_FLUX_UNET} not found on configured paths: "
            + ", ".join(str(d) for d in dirs),
        )
        self.assertTrue(hit.is_file())
        self.assertTrue(
            any("minimax and realprovisualXL" in str(d) for d in dirs),
            f"operator RealPro folder missing from search dirs: {dirs}",
        )

    def test_live_model_paths_register_impact_bbox_catalogue(self):
        dirs = ir.iter_extra_model_folder_paths("ultralytics_bbox")
        self.assertTrue(dirs, "Impact bbox registry must be explicitly configured")
        self.assertTrue(any(str(d).endswith("ultralytics\\bbox") for d in dirs))
        hit = ir.model_file_on_configured_paths(
            "hand_yolov8s.pt", "ultralytics_bbox"
        )
        self.assertIsNotNone(hit, "installed hand detector is absent from bbox registry")

    def test_live_model_paths_register_hand_refiner_controlnet(self):
        hit = ir.model_file_on_configured_paths(
            ir.HAND_REFINER_CONTROLNET, "controlnet"
        )
        self.assertIsNotNone(hit, "hand-refiner ControlNet is not configured")


    def test_existing_backend_is_never_reused_for_image_execution(self):
        with patch.object(ir, "_live_owner", return_value=False), \
             patch.object(ir, "_port_open", return_value=True):
            with self.assertRaises(ir.ImageRenderError) as caught:
                ir.preflight_execute()
        self.assertIn("already listening", str(caught.exception))



    def test_identity_inpaint_latent_noise_mask_uses_vaeencode_and_set_mask(self):
        """use_latent_noise_mask=True must preserve prefill via VAEEncode+mask."""
        graph = ir.build_graph(
            mode="inpaint_identity", prompt="erase hand", negative="blob",
            model="model.safetensors", seed=7, width=1024, height=768,
            steps=28, cfg=6, sampler="dpmpp_2m_sde", scheduler="karras",
            denoise=0.52, prefix="stories/test/renders/b",
            reference_name="ref.png", mask_name="mask.png",
            identity_name="id.png", identity_weight=1.0, grow_mask_by=0,
            use_latent_noise_mask=True,
        )
        self.assertEqual(graph["4"]["class_type"], "VAEEncode")
        self.assertEqual(graph["23"]["class_type"], "SetLatentNoiseMask")
        self.assertEqual(graph["23"]["inputs"]["samples"], ["4", 0])
        self.assertEqual(graph["23"]["inputs"]["mask"], ["9", 1])
        self.assertEqual(graph["5"]["inputs"]["latent_image"], ["23", 0])
        self.assertEqual(graph["8"]["class_type"], "LoadImage")
        self.assertEqual(graph["9"]["class_type"], "LoadImage")
        self.assertEqual(graph["10"]["class_type"], "ImageCompositeMasked")
        # Default path remains VAEEncodeForInpaint
        default = ir.build_graph(
            mode="inpaint_identity", prompt="erase hand", negative="blob",
            model="model.safetensors", seed=7, width=1024, height=768,
            steps=28, cfg=6, sampler="dpmpp_2m_sde", scheduler="karras",
            denoise=0.52, prefix="stories/test/renders/c",
            reference_name="ref.png", mask_name="mask.png",
            identity_name="id.png", identity_weight=1.0, grow_mask_by=0,
        )
        self.assertEqual(default["4"]["class_type"], "VAEEncodeForInpaint")
        self.assertNotIn("23", default)


if __name__ == "__main__":
    unittest.main(verbosity=2)
