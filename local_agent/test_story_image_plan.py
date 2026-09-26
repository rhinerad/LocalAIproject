#!/usr/bin/env python3
"""Read-only local-agent storyboard image-plan checks."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import tools


class StoryImagePlanTests(unittest.TestCase):
    def test_text_image_plan_is_read_only_and_uses_verified_model(self):
        payload = json.loads(tools.plan_story_image({
            "story": "my-story",
            "prompt": "cinematic photograph of an adult sailor at sunrise",
            "seed": 42,
        }))
        self.assertTrue(payload["planned"])
        self.assertEqual("RealVisXL_V5.0_fp16.safetensors", payload["model"])
        self.assertFalse(payload["model_load"])
        self.assertEqual("none", payload["gpu_action"])
        self.assertEqual("EmptyLatentImage", payload["graph"]["4"]["class_type"])
        self.assertEqual(42, payload["graph"]["5"]["inputs"]["seed"])

    def test_t2i_ignores_a_caller_supplied_low_denoise(self):
        # Regression for a real reported quality bug: an operator render came
        # back hazy/washed-out because the chat model passed denoise=0.55 on
        # a t2i call. t2i starts from an EmptyLatentImage (pure noise); any
        # denoise below 1.0 tells KSampler to stop partway through removing
        # that noise, which is exactly the haze that was reported. build_graph
        # must ignore a caller-supplied t2i denoise entirely, not just default
        # to 1.0 when one isn't given.
        payload = json.loads(tools.plan_story_image({
            "story": "my-story", "prompt": "a candid photograph",
            "mode": "t2i", "denoise": 0.55,
        }))
        self.assertEqual(1.0, payload["graph"]["5"]["inputs"]["denoise"])

    def test_realpro_flux_plan_uses_its_own_unet_and_flux_components(self):
        payload = json.loads(tools.plan_story_image({
            "story": "realpro-test", "prompt": "a photoreal studio portrait",
            "model_profile": "realpro_flux", "width": 896, "height": 1152,
        }))
        self.assertEqual("realpro_flux", payload["model_profile"])
        self.assertEqual("realProV3_realProV3Unet.safetensors", payload["model"])
        self.assertEqual("UNETLoader", payload["graph"]["1"]["class_type"])
        self.assertEqual("DualCLIPLoader", payload["graph"]["2"]["class_type"])
        self.assertEqual("flux", payload["graph"]["2"]["inputs"]["type"])
        self.assertEqual("ae.safetensors", payload["graph"]["3"]["inputs"]["vae_name"])
        self.assertEqual("CLIPTextEncodeFlux", payload["graph"]["4"]["class_type"])

    def test_alicemix_is_a_separate_sd15_checkpoint_with_its_recipe_defaults(self):
        payload = json.loads(tools.plan_story_image({
            "story": "alice-test", "prompt": "a photoreal portrait",
            "model_profile": "alicemix_sd15",
        }))
        self.assertEqual("realAlicemixV1_v10.safetensors", payload["model"])
        self.assertEqual("CheckpointLoaderSimple", payload["graph"]["1"]["class_type"])
        self.assertEqual(30, payload["graph"]["5"]["inputs"]["steps"])
        self.assertEqual(11.0, payload["graph"]["5"]["inputs"]["cfg"])
        self.assertEqual("dpmpp_2m", payload["graph"]["5"]["inputs"]["sampler_name"])
        self.assertEqual("karras", payload["graph"]["5"]["inputs"]["scheduler"])
        self.assertNotIn("9", payload["graph"])

    def test_i2i_denoise_is_still_respected(self):
        payload = json.loads(tools.plan_story_image({
            "story": "my-story", "prompt": "a candid photograph", "mode": "i2i",
            "reference_name": "ref.png", "denoise": 0.4,
        }))
        self.assertEqual(0.4, payload["graph"]["5"]["inputs"]["denoise"])

    def test_default_negative_and_steps_come_from_image_render(self):
        sys.path.insert(0, str(HERE.parent / "work"))
        import image_render
        payload = json.loads(tools.plan_story_image({
            "story": "my-story", "prompt": "a candid photograph",
        }))
        self.assertEqual(image_render.DEFAULT_NEGATIVE, payload["graph"]["3"]["inputs"]["text"])
        self.assertEqual(image_render.DEFAULT_STEPS, payload["graph"]["5"]["inputs"]["steps"])

    def test_t2i_applies_hires_fix_by_default(self):
        # Two full-body figures at 1024x1024 leaves each face too small for
        # SDXL to reliably resolve (crossed/misaligned eyes reported in
        # production). A second-pass latent-upscale-and-refine is applied
        # automatically unless explicitly disabled.
        payload = json.loads(tools.plan_story_image({
            "story": "my-story", "prompt": "a candid photograph",
        }))
        graph = payload["graph"]
        self.assertEqual("LatentUpscaleBy", graph["9"]["class_type"])
        self.assertEqual(["5", 0], graph["9"]["inputs"]["samples"])
        self.assertEqual("KSampler", graph["10"]["class_type"])
        self.assertEqual(["9", 0], graph["10"]["inputs"]["latent_image"])
        self.assertLess(graph["10"]["inputs"]["denoise"], 1.0)
        # The final decode must read the refined (second-pass) latent, not
        # the first pass — otherwise the hires pass would be built but unused.
        self.assertEqual(["10", 0], graph["6"]["inputs"]["samples"])

    def test_hires_fix_can_be_disabled(self):
        payload = json.loads(tools.plan_story_image({
            "story": "my-story", "prompt": "a candid photograph",
            "hires_fix": False,
        }))
        graph = payload["graph"]
        self.assertNotIn("9", graph)
        self.assertNotIn("10", graph)
        self.assertEqual(["5", 0], graph["6"]["inputs"]["samples"])

    def test_i2i_never_gets_hires_fix(self):
        # i2i is left single-pass for now (its denoise semantics differ);
        # hires_fix=True (the default) must not silently add a second pass.
        payload = json.loads(tools.plan_story_image({
            "story": "my-story", "prompt": "a candid photograph", "mode": "i2i",
            "reference_name": "ref.png",
        }))
        graph = payload["graph"]
        self.assertNotIn("9", graph)
        self.assertNotIn("10", graph)

    def test_negative_prompt_names_the_reported_crossed_eyes_defect(self):
        payload = json.loads(tools.plan_story_image({
            "story": "my-story", "prompt": "a candid photograph",
        }))
        negative = payload["graph"]["3"]["inputs"]["text"]
        self.assertIn("cross-eyed", negative)
        self.assertIn("crossed eyes", negative)

    def test_image_to_image_requires_a_reference_filename(self):
        result = tools.call("plan_story_image", {
            "story": "my-story", "prompt": "warm candid photograph", "mode": "i2i",
        })
        self.assertIn("reference_name is required", result)

    def test_image_to_image_strips_any_directory_component(self):
        payload = json.loads(tools.plan_story_image({
            "story": "my-story", "prompt": "warm candid photograph", "mode": "i2i",
            "reference_name": "C:/untrusted/path/reference.png",
        }))
        self.assertEqual("reference.png", payload["graph"]["8"]["inputs"]["image"])

    def test_schema_exposes_only_supported_modes(self):
        schema = next(item["function"] for item in tools.schemas()
                      if item["function"]["name"] == "plan_story_image")
        self.assertEqual(["t2i", "i2i"],
                         schema["parameters"]["properties"]["mode"]["enum"])

    def test_storyboard_prepare_is_desktop_state_action_and_phone_gated(self):
        context = __import__("remote_security").ToolContext(
            source="phone", remote_identity="0" * 32,
        )
        denied = tools.call("prepare_storyboard_review", {
            "story": "test", "plan": {"characters": [], "shots": []},
        }, context=context)
        self.assertIn("not permitted", denied)

        class FakeStoryboard:
            @staticmethod
            def initialise(story, plan):
                return {"story": story, "plan": plan, "gpu_action": "none"}

        with patch.object(tools, "_storyboard_module", return_value=FakeStoryboard):
            result = json.loads(tools.prepare_storyboard_review({
                "story": "test", "plan": {"characters": [], "shots": []},
            }))
        self.assertEqual("none", result["gpu_action"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
