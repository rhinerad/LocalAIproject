#!/usr/bin/env python3
"""Tests for reusable media bucket and prompt routing helpers."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["DSPY_DISABLE_OLLAMA"] = "1"

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from local_agent.comfy_graph_builder import (  # noqa: E402
    ComfyGraphBuilder,
    prompt_requests_human_subject,
)
from local_agent.dispatcher import PipelineOrchestrator  # noqa: E402
import evaluate_dspy_pipeline as dspy_eval  # noqa: E402
import optimize_dspy_pipeline as dspy_opt  # noqa: E402
from local_agent.media_buckets import resolve_latent_bucket  # noqa: E402
from local_agent.prompt_router import format_prompt_for_target  # noqa: E402
from local_agent.temporal_physics import (  # noqa: E402
    inject_temporal_physics,
    load_compiled_temporal_physics,
    ping_ollama,
    runtime_inject_temporal_physics,
)


class TestMediaBuckets(unittest.TestCase):
    def test_square_bucket_hits_sdxl_budget(self) -> None:
        self.assertEqual(resolve_latent_bucket("1:1"), (1024, 1024))

    def test_widescreen_bucket_is_16_by_9_aligned(self) -> None:
        width, height = resolve_latent_bucket("16:9")
        self.assertEqual((width, height), (1344, 768))
        self.assertEqual(width % 64, 0)
        self.assertEqual(height % 64, 0)
        self.assertLess(abs((width / height) - (16 / 9)), 0.04)

    def test_portrait_bucket_is_9_by_16_aligned(self) -> None:
        width, height = resolve_latent_bucket("9:16")
        self.assertEqual((width, height), (768, 1344))
        self.assertEqual(width % 64, 0)
        self.assertEqual(height % 64, 0)
        self.assertLess(abs((width / height) - (9 / 16)), 0.04)

    def test_custom_float_ratio(self) -> None:
        width, height = resolve_latent_bucket(1.5)
        self.assertEqual(width % 64, 0)
        self.assertEqual(height % 64, 0)
        self.assertLess(abs((width / height) - 1.5), 0.05)


class TestPromptRouter(unittest.TestCase):
    def test_sdxl_adds_quality_negative_and_tags(self) -> None:
        result = format_prompt_for_target(
            "adult actor in yellow hallway, handheld analog look",
            "sdxl",
            base_negative="visible camera",
        )
        self.assertEqual(result["dialect"], "comma_tags")
        self.assertIn("adult actor in yellow hallway", result["prompt"])
        self.assertIn("photorealistic", result["prompt"])
        self.assertIn("visible camera", result["negative_prompt"])
        self.assertIn("mutated hands", result["negative_prompt"])
        self.assertIn("bad anatomy", result["negative_prompt"])

    def test_flux_removes_quality_tag_soup_and_ignores_negative(self) -> None:
        result = format_prompt_for_target(
            "masterpiece, best quality, quiet yellow corridor, damp carpet",
            "flux",
            base_negative="bad anatomy",
        )
        self.assertEqual(result["dialect"], "natural_language")
        self.assertNotIn("masterpiece", result["prompt"].lower())
        self.assertNotIn("best quality", result["prompt"].lower())
        self.assertIn("Quiet yellow corridor", result["prompt"])
        self.assertEqual(result["negative_prompt"], "")
        self.assertEqual(result["metadata"]["negative_handling"], "ignored_by_target")

    def test_video_adds_temporal_cues(self) -> None:
        result = format_prompt_for_target("actor walks down a hallway", "minimax")
        self.assertEqual(result["dialect"], "temporal_video")
        self.assertIn("Camera motion:", result["prompt"])
        self.assertIn("Temporal stability:", result["prompt"])
        self.assertIn("single continuous physical take", result["prompt"])


class TestComfyGraphRewire(unittest.TestCase):
    def setUp(self) -> None:
        self.builder = ComfyGraphBuilder.from_txt2img(
            prompt="a lamp in a hallway",
            negative_prompt="visible camera",
        )
        self.original_ids = set(self.builder.graph)
        self.original_types = {
            nid: node["class_type"] for nid, node in self.builder.graph.items()
        }
        self.original_sampler_keys = set(
            self.builder.graph[self.builder.require_one("KSampler")]["inputs"]
        )
        self.original_pos = list(
            self.builder.graph["5"]["inputs"]["positive"]
        )
        self.original_neg = list(
            self.builder.graph["5"]["inputs"]["negative"]
        )

    def test_conditioning_inject_rewires_without_dropping_keys(self) -> None:
        sampler_before = dict(self.builder.graph["5"]["inputs"])
        new_id = self.builder.inject_conditioning_node(
            "MockControlNetApply",
            extra_inputs={"strength": 0.8, "image": ["99", 0]},
        )
        graph = self.builder.to_prompt()
        self.assertTrue(self.original_ids.issubset(graph))
        for node_id in self.original_ids:
            self.assertEqual(graph[node_id]["class_type"], self.original_types[node_id])
            self.assertIn("inputs", graph[node_id])
        sampler = graph["5"]["inputs"]
        self.assertEqual(self.original_sampler_keys, set(sampler))
        for key in self.original_sampler_keys - {"positive", "negative"}:
            self.assertEqual(sampler[key], sampler_before[key])
        self.assertEqual(graph[new_id]["class_type"], "MockControlNetApply")
        self.assertEqual(graph[new_id]["inputs"]["positive"], self.original_pos)
        self.assertEqual(graph[new_id]["inputs"]["negative"], self.original_neg)
        self.assertEqual(graph[new_id]["inputs"]["strength"], 0.8)
        self.assertEqual(sampler["positive"], [new_id, 0])
        self.assertEqual(sampler["negative"], [new_id, 1])
        self.assertNotEqual(sampler["positive"], self.original_pos)
        self.assertEqual(graph["2"]["inputs"]["text"], "a lamp in a hallway")
        self.assertEqual(graph["3"]["inputs"]["text"], "visible camera")

    def test_second_inject_reads_live_links_not_assumed_ids(self) -> None:
        first = self.builder.inject_conditioning_node("MockControlNetApply")
        second = self.builder.inject_conditioning_node("MockSecondConditioner")
        graph = self.builder.to_prompt()
        self.assertEqual(graph[second]["inputs"]["positive"], [first, 0])
        self.assertEqual(graph[second]["inputs"]["negative"], [first, 1])
        self.assertEqual(graph["5"]["inputs"]["positive"], [second, 0])
        self.assertIn(first, graph)
        self.assertIn("2", graph)
        self.assertIn("3", graph)


class TestFaceDetailerDetection(unittest.TestCase):
    def test_human_keywords_trigger(self) -> None:
        self.assertTrue(prompt_requests_human_subject(
            "One fictional adult man stands in an ordinary apartment"
        ))
        self.assertTrue(prompt_requests_human_subject("portrait of a woman"))
        self.assertTrue(prompt_requests_human_subject("a girl's face, close crop"))
        self.assertTrue(prompt_requests_human_subject("two people in a hallway"))

    def test_empty_scene_and_prohibitions_do_not_trigger(self) -> None:
        self.assertFalse(prompt_requests_human_subject(
            "Empty Level 0 Backrooms corridor, sickly yellow wallpaper, damp carpet"
        ))
        self.assertFalse(prompt_requests_human_subject(
            "Do not depict the actor's face or torso. The actor is entirely "
            "outside the frame. Absence of a person is correct."
        ))
        self.assertFalse(prompt_requests_human_subject("manager of a warehouse"))
        self.assertFalse(prompt_requests_human_subject("the wall surface is yellow"))
        self.assertFalse(prompt_requests_human_subject(
            "first-person camcorder tracking, heavy VHS artifacting"
        ))

    def test_face_detailer_injected_and_save_rewired(self) -> None:
        prompt = "One fictional adult man stands in an ordinary apartment living room"
        builder = ComfyGraphBuilder.from_txt2img(prompt=prompt, seed=1016)
        original_keys = set(builder.graph)
        decode_id = builder.require_one("VAEDecode")
        ckpt_id = builder.require_one("CheckpointLoaderSimple")
        save_id = builder.require_one("SaveImageWebsocket")
        self.assertEqual(builder.graph[save_id]["inputs"]["images"], [decode_id, 0])
        detailer_id = builder.inject_face_detailer(prompt=prompt, seed=1016)
        self.assertIsNotNone(detailer_id)
        graph = builder.to_prompt()
        self.assertTrue(original_keys.issubset(graph))
        self.assertEqual(graph[detailer_id]["class_type"], "FaceDetailer")
        detailer = graph[detailer_id]["inputs"]
        self.assertEqual(detailer["image"], [decode_id, 0])
        self.assertEqual(detailer["model"], [ckpt_id, 0])
        self.assertEqual(detailer["clip"], [ckpt_id, 1])
        self.assertEqual(detailer["vae"], [ckpt_id, 2])
        self.assertEqual(
            graph[decode_id]["inputs"]["vae"],
            detailer["vae"],
        )
        self.assertEqual(graph[save_id]["inputs"]["images"], [detailer_id, 0])
        self.assertTrue(builder.node_ids_of("UltralyticsDetectorProvider"))
        self.assertEqual(
            graph["5"]["inputs"]["model"],
            [ckpt_id, 0],
        )

    def test_empty_prompt_skips_face_detailer(self) -> None:
        prompt = "Static empty yellow Backrooms corridor, damp carpet, fluorescent lights"
        builder = ComfyGraphBuilder.from_txt2img(prompt=prompt)
        self.assertIsNone(builder.inject_face_detailer(prompt=prompt))
        self.assertFalse(builder.node_ids_of("FaceDetailer"))
        save_id = builder.require_one("SaveImageWebsocket")
        decode_id = builder.require_one("VAEDecode")
        self.assertEqual(builder.graph[save_id]["inputs"]["images"], [decode_id, 0])


_BACKROOMS_DEFAULTS = (
    "first-person camcorder tracking",
    "heavy VHS artifacting",
    "handheld walking momentum",
    "continuous unbroken shot",
    "realistic camera shake",
    "1990s home video aesthetic",
)


class TestTemporalPhysics(unittest.TestCase):
    def test_basic_hallway_gets_full_backrooms_injection(self) -> None:
        out = inject_temporal_physics("A yellow hallway", style="backrooms")
        lowered = out.lower()
        self.assertTrue(out.startswith("A yellow hallway"))
        for term in _BACKROOMS_DEFAULTS:
            self.assertIn(term.lower(), lowered)
        self.assertTrue(out.endswith("."))
        self.assertNotIn(",,", out)

    def test_empty_prompt_still_emits_physics_paragraph(self) -> None:
        out = inject_temporal_physics("", style="backrooms")
        lowered = out.lower()
        for term in _BACKROOMS_DEFAULTS:
            self.assertIn(term.lower(), lowered)
        self.assertTrue(out.endswith("."))

    def test_compiled_style_drop_is_repaired_with_handheld_momentum(self) -> None:
        from local_agent.temporal_physics import enforce_physics_terms
        repaired = enforce_physics_terms(
            "A yellow hallway with flickering fluorescent lights",
            "A yellow hallway. Heavy VHS artifacting, continuous unbroken shot, and 1990s home video aesthetic.",
        )
        self.assertIn("handheld walking momentum", repaired.lower())
        self.assertIn("vhs", repaired.lower())

    def test_static_security_camera_suppresses_handheld_momentum(self) -> None:
        out = inject_temporal_physics(
            "A yellow hallway, static security camera footage",
            style="backrooms",
        )
        lowered = out.lower()
        self.assertIn("A yellow hallway, static security camera footage", out)
        self.assertNotIn("handheld walking momentum", lowered)
        self.assertNotIn("first-person camcorder tracking", lowered)
        self.assertNotIn("realistic camera shake", lowered)
        self.assertIn("heavy vhs artifacting", lowered)
        self.assertIn("continuous unbroken shot", lowered)
        self.assertIn("1990s home video aesthetic", lowered)

    def test_specified_dolly_suppresses_handheld_momentum(self) -> None:
        out = inject_temporal_physics(
            "A yellow hallway, dolly in toward the far door",
            style="backrooms",
        )
        self.assertIn("dolly in", out)
        self.assertNotIn("handheld walking momentum", out)

    def test_existing_phrase_is_not_duplicated(self) -> None:
        out = inject_temporal_physics(
            "A yellow hallway with heavy VHS artifacting",
            style="backrooms",
        )
        self.assertEqual(out.lower().count("heavy vhs artifacting"), 1)

    def test_unknown_style_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            inject_temporal_physics("A yellow hallway", style="anime")


class TestPipelineOrchestrator(unittest.TestCase):
    def test_woman_hallway_sdxl_backrooms_wires_all_layers(self) -> None:
        orchestrator = PipelineOrchestrator()
        graph = orchestrator.build_and_dispatch_payload(
            "A woman in a yellow hallway",
            "16:9",
            "sdxl",
            "backrooms",
        )
        width, height = resolve_latent_bucket("16:9")
        latent = next(
            node for node in graph.values()
            if node.get("class_type") == "EmptyLatentImage"
        )
        self.assertEqual(latent["inputs"]["width"], width)
        self.assertEqual(latent["inputs"]["height"], height)
        self.assertEqual((width, height), (1344, 768))
        self.assertTrue(
            any(node.get("class_type") == "FaceDetailer" for node in graph.values()),
            "woman must trigger FaceDetailer",
        )
        texts = " ".join(
            str((node.get("inputs") or {}).get("text") or "")
            for node in graph.values()
        ).lower()
        self.assertIn("woman", texts)
        self.assertIn("handheld walking momentum", texts)
        self.assertIn("1990s home video aesthetic", texts)
        self.assertIn("heavy vhs artifacting", texts)

    def test_submit_posts_prompt_id_and_websocket_url(self) -> None:
        import json
        from unittest.mock import patch

        orchestrator = PipelineOrchestrator(client_id="media-pipeline-test")
        graph = orchestrator.build_and_dispatch_payload(
            "A lamp", "1:1", "sdxl", "default",
        )
        captured = {}

        class _Resp:
            def read(self):
                return json.dumps({"prompt_id": "abc-12345", "number": 1}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            return _Resp()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            queued = orchestrator.submit_prompt(graph)
        self.assertTrue(captured["url"].endswith("/prompt"))
        self.assertEqual(captured["body"]["client_id"], "media-pipeline-test")
        self.assertEqual(captured["body"]["prompt"], graph)
        self.assertEqual(queued["prompt_id"], "abc-12345")
        self.assertIn("clientId=media-pipeline-test", queued["websocket_url"])
        self.assertTrue(queued["websocket_url"].startswith("ws://"))

    def test_track_prompt_id_uses_websocket_executed(self) -> None:
        orchestrator = PipelineOrchestrator(client_id="media-pipeline-ws")

        class FakeSession:
            def __init__(self):
                self.closed = False
                self.frames = [
                    json.dumps({
                        "type": "executing",
                        "data": {"prompt_id": "abc-12345", "node": "5"},
                    }),
                    json.dumps({
                        "type": "execution_success",
                        "data": {"prompt_id": "abc-12345"},
                    }),
                ]

            def recv_text(self, timeout=5.0):
                return self.frames.pop(0) if self.frames else None

            def close(self):
                self.closed = True

        session = FakeSession()
        result = orchestrator.track_prompt_id(
            "abc-12345",
            websocket_connect=lambda url, timeout=10.0: session,
        )
        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["source"], "websocket")
        self.assertTrue(session.closed)

    def test_live_case_payloads_route_without_comfy(self) -> None:
        orchestrator = PipelineOrchestrator()
        image_graph = orchestrator.build_and_dispatch_payload(
            "A tired woman in a corporate office, looking at the camera",
            "16:9",
            "sdxl",
            "default",
        )
        self.assertTrue(any(
            node.get("class_type") == "FaceDetailer" for node in image_graph.values()
        ))
        video_graph = orchestrator.build_and_dispatch_payload(
            "A yellow hallway with flickering fluorescent lights",
            "16:9",
            "video",
            "backrooms",
        )
        text = " ".join(
            str((node.get("inputs") or {}).get("text") or "")
            for node in video_graph.values()
        ).lower()
        self.assertIn("handheld walking momentum", text)
        self.assertFalse(any(
            node.get("class_type") == "FaceDetailer" for node in video_graph.values()
        ))


class TestDspyTemporalEvalHelpers(unittest.TestCase):
    def test_extract_injected_prompt_from_trace_envelope(self) -> None:
        graph = PipelineOrchestrator().build_and_dispatch_payload(
            "A yellow hallway with flickering fluorescent lights",
            "16:9",
            "video",
            "backrooms",
        )
        envelope = {
            "case_id": "case_b_video_temporal_physics",
            "request": {
                "base_prompt": "A yellow hallway with flickering fluorescent lights",
                "model_type": "video",
                "style": "backrooms",
            },
            "prompt": graph,
        }
        injected = dspy_eval.extract_injected_prompt(envelope)
        self.assertIn("handheld walking momentum", injected.lower())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case_b_video_temporal_physics.json"
            path.write_text(json.dumps(envelope), encoding="utf-8")
            rows = dspy_eval.load_trace_examples(Path(tmp))
        matching = [row for row in rows if row["case_id"] == "case_b_video_temporal_physics"]
        self.assertTrue(matching)
        self.assertIn("hallway", matching[0]["base_prompt"].lower())

    def test_gold_static_camera_fails_if_handheld_leaks(self) -> None:
        example = type("Ex", (), {
            "base_prompt": "A yellow hallway, static security camera footage",
            "injected_prompt": (
                "A yellow hallway, static security camera footage. "
                "Handheld walking momentum, realistic camera shake."
            ),
        })()
        pred = type("Pred", (), {"score": True})()
        self.assertFalse(dspy_eval.temporal_physics_metric(example, pred))

    def test_gold_open_hallway_passes_with_full_physics(self) -> None:
        gold = dspy_eval.gold_examples()[0]
        example = type("Ex", (), gold)()
        pred = type("Pred", (), {"score": True, "injected_prompt": gold["injected_prompt"]})()
        self.assertTrue(dspy_eval.temporal_physics_metric(example, pred))
        self.assertTrue(dspy_eval.evaluate_temporal_physics(example, pred))

    def test_evaluate_temporal_physics_does_not_require_judge_score(self) -> None:
        gold = dspy_eval.gold_examples()[0]
        example = type("Ex", (), gold)()
        pred = type("Pred", (), {"injected_prompt": gold["injected_prompt"]})()
        self.assertTrue(dspy_eval.evaluate_temporal_physics(example, pred))

    def test_training_rows_include_gold_and_style(self) -> None:
        rows = dspy_opt.load_training_rows()
        ids = {row["case_id"] for row in rows}
        self.assertIn("gold_open_hallway", ids)
        self.assertIn("gold_static_security", ids)
        self.assertIn("gold_tripod", ids)
        for row in rows:
            self.assertEqual(row["style"], "backrooms")
            self.assertTrue(row["base_prompt"])
            self.assertTrue(row["injected_prompt"])
        tripod = next(row for row in rows if row["case_id"] == "gold_tripod")
        text = tripod["injected_prompt"].lower()
        self.assertIn("vhs", text)
        self.assertIn("1990s", text)
        self.assertNotIn("handheld walking momentum", text)
        self.assertNotIn("realistic camera shake", text)

    def test_synthesized_artifact_schema_and_four_demos(self) -> None:
        artifact = Path(self.id().replace(".", "_") + "_synth.json")
        artifact = Path(dspy_opt.write_synthesized_artifact(artifact))
        self.addCleanup(lambda: artifact.unlink(missing_ok=True))
        state = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertIn("prog.predict", state)
        predict = state["prog.predict"]
        self.assertEqual(predict["traces"], [])
        self.assertEqual(predict["train"], [])
        self.assertIsNone(predict["lm"])
        prefixes = [field["prefix"] for field in predict["signature"]["fields"]]
        self.assertEqual(
            prefixes,
            ["Base Prompt:", "Style:", "Reasoning:", "Injected Prompt:"],
        )
        demos = predict["demos"]
        self.assertEqual(len(demos), 4)
        kinds = []
        for demo in demos:
            self.assertEqual(demo["style"], "backrooms")
            self.assertTrue(demo["reasoning"])
            example = type("Ex", (), {"base_prompt": demo["base_prompt"]})()
            pred = type("Pred", (), {"injected_prompt": demo["injected_prompt"]})()
            self.assertTrue(dspy_eval.evaluate_temporal_physics(example, pred))
            text = demo["injected_prompt"].lower()
            if "handheld walking momentum" in text:
                kinds.append("dynamic")
            else:
                kinds.append("locked")
                self.assertIn("vhs", text)
                self.assertIn("1990s", text)
        self.assertEqual(kinds.count("dynamic"), 2)
        self.assertEqual(kinds.count("locked"), 2)


class TestCompiledRuntimeInjection(unittest.TestCase):
    def test_load_compiled_deserializes_baked_artifact(self) -> None:
        state = load_compiled_temporal_physics(
            "models/dspy_compiled/temporal_physics_v1.json"
        )
        predict = state["prog.predict"]
        self.assertGreaterEqual(len(predict["demos"]), 1)
        self.assertEqual(
            [field["prefix"] for field in predict["signature"]["fields"]],
            ["Base Prompt:", "Style:", "Reasoning:", "Injected Prompt:"],
        )
        complete = [d for d in predict["demos"] if d.get("injected_prompt")]
        self.assertTrue(complete)
        instructions = predict["signature"]["instructions"]
        lore = (
            "Must maintain a first-person camcorder perspective.",
            "Mandate 8-second generation lengths.",
        )
        for sentence in lore:
            self.assertIn(sentence, instructions)
            self.assertTrue(any(sentence in d["injected_prompt"] for d in complete))

    def test_preferred_ollama_models_are_tiny_first(self) -> None:
        from local_agent import temporal_physics as tp_mod
        self.assertEqual(tp_mod.PREFERRED_OLLAMA_MODELS[0], "qwen2.5:1.5b")
        self.assertIn("llama3.2:1b", tp_mod.PREFERRED_OLLAMA_MODELS)
        src = Path(tp_mod.__file__).read_text(encoding="utf-8")
        self.assertIn("keep_alive=0", src)

    def test_ping_ollama_returns_list(self) -> None:
        names = ping_ollama(timeout=1.0)
        self.assertIsInstance(names, list)

    def test_runtime_falls_back_when_artifact_missing(self) -> None:
        prompt = "A yellow hallway with flickering fluorescent lights"
        expected = inject_temporal_physics(prompt, style="backrooms")
        got = runtime_inject_temporal_physics(
            prompt, style="backrooms", artifact_path="models/dspy_compiled/no_such.json",
        )
        self.assertEqual(got, expected)
        missing = Path(tempfile.mkdtemp()) / "absent.json"
        got_abs = runtime_inject_temporal_physics(
            prompt, style="backrooms", artifact_path=missing,
        )
        self.assertEqual(got_abs, expected)

    def test_video_payload_clip_contains_temporal_cues(self) -> None:
        graph = PipelineOrchestrator().build_and_dispatch_payload(
            "A yellow hallway with flickering fluorescent lights",
            "16:9",
            "video",
            "backrooms",
        )
        encode = graph["2"]
        self.assertEqual(encode["class_type"], "CLIPTextEncode")
        text = str(encode["inputs"]["text"]).lower()
        self.assertIn("handheld walking momentum", text)
        self.assertIn("vhs", text)
        self.assertIn("1990s", text)
        locked = PipelineOrchestrator().build_and_dispatch_payload(
            "A static tripod shot of a yellow hallway",
            "16:9",
            "video",
            "backrooms",
        )
        locked_text = str(locked["2"]["inputs"]["text"]).lower()
        action = locked_text.split("action:", 1)[-1]
        self.assertIn("vhs", action)
        self.assertNotIn("handheld walking momentum", action)
        self.assertNotIn("realistic camera shake", action)


if __name__ == "__main__":
    unittest.main()
