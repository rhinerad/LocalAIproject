#!/usr/bin/env python3
"""Offline regression checks for media schemas and deterministic analyzers."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import tools  # noqa: E402
import media_tools  # noqa: E402
import capabilities as caps  # noqa: E402


class MediaAnalysisTests(unittest.TestCase):
    def test_custom_vision_instruction_keeps_operator_request(self):
        rendered = media_tools._build_prompt(
            "The actor points toward the empty space beside him.",
            "Return a strict JSON verdict.")
        self.assertIn("Return a strict JSON verdict.", rendered)
        self.assertIn("OPERATOR REQUEST / EXPECTED CONTENT", rendered)
        self.assertIn("actor points", rendered)

    def test_sensory_schemas_are_registered(self):
        names = {s["function"]["name"] for s in tools.schemas()}
        self.assertTrue({"capabilities", "see_image", "video_frames",
                         "analyze_video", "read_video_metadata", "audio_measure",
                         "transcribe", "compare_voice"} <= names)
        self.assertEqual(len(tools.TOOLS), len(tools.schemas()))
        video = next(s for s in tools.schemas()
                     if s["function"]["name"] == "analyze_video")
        self.assertEqual(["per_second", "half_second", "overview"],
                         video["function"]["parameters"]["properties"]["detail"]["enum"])

    def test_short_video_timeline_covers_each_second_and_the_end_state(self):
        self.assertEqual([0.0, 1.0, 2.0, 3.0, 4.0, 4.75],
                         media_tools._timeline_times(5.0, {}))
        self.assertEqual([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5,
                          4.0, 4.5, 4.75],
                         media_tools._timeline_times(5.0, {"detail": "half_second"}))

    def test_action_windows_cover_each_requested_second_without_inventing_tail_time(self):
        self.assertEqual([
            {"frame": 1, "start": 0.0, "end": 1.0},
            {"frame": 2, "start": 1.0, "end": 2.0},
            {"frame": 3, "start": 2.0, "end": 3.0},
            {"frame": 4, "start": 3.0, "end": 3.25},
        ], media_tools._action_windows(4, 1.0, 3.25))

    def test_action_instruction_requires_exact_frame_labels_and_no_legacy_h3_timing_blocks(self):
        windows = media_tools._action_windows(2, 1.0, 2.0)
        instruction = media_tools._action_frame_instruction(windows, "Avery", True)
        self.assertIn("Frame 1: t=00:00.000–00:01.000", instruction)
        self.assertIn("Frame 2: t=00:01.000–00:02.000", instruction)
        self.assertIn("Return exactly one labelled line for every Frame N", instruction)
        self.assertIn("Do not emit bracketed timing blocks", instruction)
        # 2026-09-25b: camera motion is a mandatory cam= slot on every line.
        self.assertIn("| cam=<camera motion> |", instruction)
        self.assertIn("mandatory even when the camera is still", instruction)
        plain = media_tools._action_frame_instruction(windows, None, False)
        self.assertIn("| cam=<camera motion> |", plain)
        # 2026-09-25d: measured camera motion rides in the frame table only when given.
        self.assertNotIn("measured camera", plain)
        fed = media_tools._action_frame_instruction(windows, None, False,
                                                    measured_camera={1: "push-in", 2: "uncertain"})
        self.assertIn("Measured camera motion per frame", fed)
        self.assertIn("Frame 1: push-in, Frame 2: uncertain", fed)
        self.assertIn("write that exact word for that frame", fed)
        self.assertIn("The measurement says nothing about the subject", fed)

    def test_action_coverage_reports_camera_slot_without_inferring_one(self):
        windows = media_tools._action_windows(4, 1.0, 4.0)
        coverage = media_tools._action_coverage(
            windows, "Frame 1 | t=00:00.000–00:01.000 | cam=static | standing still\n"
                     "Frame 2 | t=00:01.000–00:02.000 | cam=Pan-Left | turns frame-left\n"
                     "Frame 3 | t=00:02.000–00:03.000 | cam=zoom | no visible change\n"
                     "Frame 4 | t=00:03.000–00:04.000 | no visible change")
        self.assertEqual({"1": "static", "2": "pan-left"}, coverage["camera_labels"])
        self.assertEqual({"3": "zoom"}, coverage["invalid_camera_labels"])
        self.assertEqual([3, 4], coverage["missing_camera_labels"])
        self.assertFalse(coverage["camera_complete"])
        self.assertTrue(coverage["complete"])          # frame labels are all there
        self.assertIn("Camera motion is unknown", coverage["warning"])
        full = media_tools._action_coverage(
            windows[:1], "Frame 1 | t=00:00.000–00:01.000 | cam=uncertain | no visible change")
        self.assertTrue(full["camera_complete"])
        self.assertIsNone(full["warning"])

    def test_action_coverage_reports_missing_seconds_without_fabricating_an_action(self):
        windows = media_tools._action_windows(3, 1.0, 3.0)
        coverage = media_tools._action_coverage(
            windows, "Frame 1 | t=00:00.000–00:01.000 | standing still\n"
                     "Frame 3 | t=00:02.000–00:03.000 | turns frame-left")
        self.assertEqual([1, 3], coverage["returned_frame_labels"])
        self.assertEqual([2], coverage["missing_frame_labels"])
        self.assertFalse(coverage["complete"])

    def test_video_analysis_returns_individual_states_and_motion_beats(self):
        source = ROOT / "local_agent" / "uploads" / "timeline_test.mp4"
        frames = [ROOT / "local_agent" / "uploads" / f"timeline_{n}.jpg"
                  for n in range(4)]
        calls = []

        def fake_vision(images, _question, **_kwargs):
            calls.append(images)
            return json.dumps({"available": True, "analysis": f"evidence-{len(calls)}"})

        fake_tier = [{"label": "primary", "model": "stub",
                      "vram_need_mb": 11500, "task_strengths": ""}]

        with patch.object(media_tools, "_path", return_value=source), \
             patch.object(media_tools, "_duration", return_value=3.0), \
             patch.object(media_tools, "_extract_frames", return_value=frames), \
             patch.object(media_tools, "_vision_direct", side_effect=fake_vision), \
             patch.object(media_tools.router, "gpu_free_mb", return_value=14000), \
             patch.object(media_tools.caps, "qwen25_vl_runtime_available", return_value=True), \
             patch.object(media_tools.caps, "vision_tiers", return_value=fake_tier), \
             patch.object(Path, "read_bytes", side_effect=[b"a", b"b", b"b", b"c", b"c", b"d"]), \
             patch.object(media_tools, "audio_measure", return_value=json.dumps({"duration": 3.0})):
            result = json.loads(media_tools.analyze_video({"path": str(source)}))

        self.assertEqual([0.0, 1.0, 2.0, 2.75], result["sample_times"])
        self.assertEqual(4, len(result["frame_by_frame"]))
        self.assertEqual(3, len(result["action_timeline"]))
        self.assertEqual("evidence-1", result["frame_by_frame"][0]["visible_state"])
        self.assertEqual("evidence-5", result["action_timeline"][0]["visible_change"])
        self.assertEqual(7, len(calls))
        self.assertTrue(all(len(images) == 1 for images in calls[:4]))
        self.assertTrue(all(len(images) == 2 for images in calls[4:]))

    def test_identical_adjacent_frames_never_claim_motion(self):
        source = ROOT / "local_agent" / "uploads" / "timeline_test.mp4"
        frame = ROOT / "local_agent" / "uploads" / "45c8387e32cc5578_boundary_00_v2.png"
        if not frame.is_file():
            self.skipTest(f"missing uploaded image {frame}")
        fake_tier = [{"label": "primary", "model": "stub",
                      "vram_need_mb": 11500, "task_strengths": ""}]
        with patch.object(media_tools, "_path", return_value=source), \
             patch.object(media_tools, "_duration", return_value=1.0), \
             patch.object(media_tools, "_extract_frames", return_value=[frame, frame]), \
             patch.object(media_tools, "_vision_direct",
                          return_value=json.dumps({"available": True, "analysis": "frame"})), \
             patch.object(media_tools.router, "gpu_free_mb", return_value=14000), \
             patch.object(media_tools.caps, "qwen25_vl_runtime_available", return_value=True), \
             patch.object(media_tools.caps, "vision_tiers", return_value=fake_tier), \
             patch.object(media_tools, "audio_measure", return_value=json.dumps({"duration": 1.0})):
            result = json.loads(media_tools.analyze_video({"path": str(source)}))
        self.assertEqual("No confirmed change: the extracted frames are identical.",
                         result["action_timeline"][0]["visible_change"])

    def test_capability_registry_is_explicit(self):
        data = json.loads(tools.call("capabilities", {}))
        self.assertTrue({"vision", "video_frames", "audio_measure",
                         "transcription", "voice_compare", "action_extraction",
                         "qwen_image_diffusion"} <= set(data))
        for value in data.values():
            self.assertIn("available", value)
            self.assertIn("reason", value)

    def test_qwen25_vl_is_the_primary_and_action_model(self):
        self.assertEqual("qwen25-vl-nsfw-caption:v4-q4_k_m",
                         caps._TIER_DEFS[0]["models"][0])
        self.assertEqual(8000, caps._TIER_DEFS[0]["vram_need_mb"])
        with patch.object(caps, "_models", return_value=[caps.QWEN25_VL_MODEL]), \
             patch.object(caps, "_model_capabilities", return_value=["vision"]):
            self.assertEqual((caps.QWEN25_VL_MODEL, caps.QWEN25_VL_VRAM_MB),
                             caps.action_model("127.0.0.1:11434"))

    def test_action_model_accepts_complete_lazy_gguf_pair(self):
        files = {"weights": {"size_ok": True, "large_enough": True},
                 "mmproj": {"size_ok": True, "large_enough": True}}
        with patch.object(caps, "qwen25_vl_files", return_value=files), \
             patch.object(caps, "qwen25_vl_runtime_available", return_value=False), \
             patch.object(caps, "_models", return_value=[]):
            self.assertEqual((caps.QWEN25_VL_MODEL, caps.QWEN25_VL_VRAM_MB),
                             caps.action_model())

    def test_action_job_uses_watcher_owned_runtime_after_it_consumes_vram(self):
        """Do not re-queue after the VLM itself has reduced free VRAM."""
        source = ROOT / "local_agent/uploads/45c8387e32cc5578_boundary_00_v2.png"
        # The path check happens before the runtime decision; a temporary MP4
        # name is sufficient because the direct body is patched out below.
        video = ROOT / "local_agent/uploads/test_action_runtime.mp4"
        video.touch(exist_ok=True)
        def fake_ffmpeg(command, **_kwargs):
            frame = Path(command[-1].replace("%04d", "0001"))
            media_tools.Image.new("RGB", (8, 8), "black").save(frame)
            return SimpleNamespace(returncode=0, stderr="")
        seen_vision = {}

        def fake_vision(*args, **kwargs):
            seen_vision.update(kwargs)
            return json.dumps({"available": True,
                               "analysis": "Frame 1 | t=00:00.000–00:01.000 | cam=static | still"})
        import camera_motion

        def fake_camera(video, windows, fps=None):
            return [{"frame": w["frame"], "start": w["start"], "end": w["end"], "camera": "pan-left",
                     "dx_frac": 0.05, "dy_frac": 0.0, "scale": 0.0, "response": 0.6,
                     "pairs": 24, "low_response_pairs": 0} for w in windows]
        try:
            with patch.object(media_tools.caps, "action_model",
                              return_value=(caps.QWEN25_VL_MODEL, 8000)), \
                 patch.object(media_tools.caps, "qwen25_vl_runtime_available", return_value=True), \
                 patch.object(media_tools.router, "gpu_free_mb", return_value=9032), \
                 patch.object(media_tools.router, "queue_owner", return_value=(False, "released")), \
                 patch.object(media_tools.router, "comfy_listening", return_value=False), \
                 patch.object(media_tools, "_duration", return_value=0.0), \
                 patch.object(media_tools.subprocess, "run", side_effect=fake_ffmpeg), \
                 patch.object(media_tools, "_run_vision_gpu", side_effect=fake_vision), \
                 patch.object(camera_motion, "estimate_camera_motion", side_effect=fake_camera):
                result = json.loads(media_tools.extract_video_actions({"video_path": str(video)}))
            self.assertNotIn("queued", result)
            # 2026-09-25c: measured camera motion travels with the result and is
            # compared against the model's cam= claim, never merged into it.
            self.assertEqual("pan-left", result["camera_motion"][0]["camera"])
            # 2026-09-25d: the measurement reached the VLM's frame table.
            self.assertIn("Frame 1: pan-left", seen_vision["instruction"])
            self.assertEqual({"1": "static"}, result["coverage"]["camera_labels"])
            self.assertEqual(0, result["camera_motion_vs_model"]["agree"])
            self.assertEqual([{"frame": 1, "claimed": "static", "measured": "pan-left"}],
                             result["camera_motion_vs_model"]["disagree"])
            self.assertIsNone(result["camera_motion_error"])
            # 2026-09-25a: the per-line action log keeps the repeat penalty off.
            self.assertEqual(seen_vision["repeat_penalty"], 1.0)
            self.assertEqual(seen_vision["num_ctx"], 32768)
            self.assertIn("cam=static | still", result["action_log"])
            self.assertEqual([{"frame": 1, "start": 0.0, "end": 1.0}],
                             result["observation_windows"])
            self.assertTrue(result["coverage"]["complete"])
        finally:
            video.unlink(missing_ok=True)

    def test_release_keeps_ownership_record_when_windows_refuses_to_stop_vlm(self):
        state = caps.QWEN25_VL_RUNTIME_STATE
        state.parent.mkdir(parents=True, exist_ok=True)
        original = state.read_text(encoding="utf-8") if state.exists() else None
        state.write_text(json.dumps({"pid": 99999}), encoding="utf-8")
        try:
            with patch.object(caps.os, "name", "nt"), \
                 patch.object(caps.subprocess, "run",
                              return_value=SimpleNamespace(returncode=1)), \
                 patch.object(caps, "_runtime_pid_alive", return_value=True):
                self.assertFalse(caps.release_qwen25_vl_runtime())
            self.assertTrue(state.exists())
        finally:
            if original is None:
                state.unlink(missing_ok=True)
            else:
                state.write_text(original, encoding="utf-8")

    def test_release_removes_stale_record_when_windows_reports_already_gone(self):
        state = caps.QWEN25_VL_RUNTIME_STATE
        state.parent.mkdir(parents=True, exist_ok=True)
        original = state.read_text(encoding="utf-8") if state.exists() else None
        state.write_text(json.dumps({"pid": 99998}), encoding="utf-8")
        try:
            with patch.object(caps.os, "name", "nt"), \
                 patch.object(caps.subprocess, "run",
                              return_value=SimpleNamespace(returncode=1)), \
                 patch.object(caps, "_runtime_pid_alive", return_value=False):
                self.assertTrue(caps.release_qwen25_vl_runtime())
            self.assertFalse(state.exists())
        finally:
            if original is not None:
                state.write_text(original, encoding="utf-8")

    def test_qwen25_modelfile_pairs_base_and_matching_projector(self):
        text = (HERE / "Modelfile.qwen25-vl-nsfw-caption").read_text(encoding="utf-8")
        self.assertIn(str(caps.QWEN25_VL_GGUF), text)
        self.assertIn(str(caps.QWEN25_VL_MMPROJ), text)
        self.assertEqual(2, sum(1 for line in text.splitlines()
                                if line.startswith("FROM ")))

    def test_lazy_qwen_runtime_uses_32k_context_for_action_batches(self):
        source = (HERE / "capabilities.py").read_text(encoding="utf-8")
        self.assertIn('"--ctx-size", "32768"', source)

    def test_llama_vision_turn_uses_structured_images_and_qwen_system_user_roles(self):
        sample = ROOT / "local_agent/uploads/45c8387e32cc5578_boundary_00_v2.png"
        if not sample.is_file():
            self.skipTest(f"missing uploaded image {sample}")
        captured = {}

        def fake_chat(messages, **kwargs):
            captured["messages"] = messages
            captured["kwargs"] = kwargs
            return "grounded description", {}

        with patch.object(media_tools.caps, "qwen25_vl_runtime_available", return_value=True), \
             patch.object(media_tools.llama_cpp_client, "chat", side_effect=fake_chat):
            result = json.loads(media_tools._run_vision_gpu(
                [sample], "describe", caps.QWEN25_VL_MODEL, "127.0.0.1:11434"))

        self.assertTrue(result["available"])
        self.assertEqual(["system", "user"], [m["role"] for m in captured["messages"]])
        self.assertEqual(1, len(captured["messages"][1]["images"]))
        self.assertNotIn("<|vision_start|>", captured["messages"][1]["content"])
        self.assertEqual(99, captured["kwargs"]["options"]["num_gpu"])

    def test_llama_vision_turn_accepts_bounded_predict_override(self):
        sample = ROOT / "local_agent/uploads/45c8387e32cc5578_boundary_00_v2.png"
        if not sample.is_file():
            self.skipTest(f"missing uploaded image {sample}")
        captured = {}

        def fake_chat(messages, **kwargs):
            captured.update(kwargs)
            return '{"pass":true}', {}

        with patch.object(media_tools.caps, "qwen25_vl_runtime_available", return_value=True), \
             patch.object(media_tools.llama_cpp_client, "chat", side_effect=fake_chat):
            media_tools._run_vision_gpu(
                [sample], "inspect", caps.QWEN25_VL_MODEL, "127.0.0.1:11434",
                num_ctx=32768, num_predict=512)
        self.assertEqual(512, captured["options"]["num_predict"])
        self.assertEqual(1.08, captured["options"]["repeat_penalty"])
        # 2026-09-25o: cache_prompt reaches the body only when a caller decided.
        self.assertNotIn("cache_prompt", captured["options"])
        with patch.object(media_tools.caps, "qwen25_vl_runtime_available", return_value=True), \
             patch.object(media_tools.llama_cpp_client, "chat", side_effect=fake_chat):
            media_tools._run_vision_gpu(
                [sample], "inspect", caps.QWEN25_VL_MODEL, "127.0.0.1:11434",
                num_ctx=32768, num_predict=512, cache_prompt=False)
        self.assertIs(captured["options"]["cache_prompt"], False)
        self.assertEqual(1.08, captured["options"]["repeat_penalty"])

    def test_existing_whisper_capability_routes_transcription_without_loading_a_model(self):
        caps = json.loads(tools.call("capabilities", {}))["transcription"]
        self.assertTrue(caps["available"])
        self.assertEqual("comfy_whisper_tiny", caps["engine"])
        self.assertTrue(Path(caps["model"]).is_dir())
        sample = ROOT / "outputs/equal_shares/audio/_hybrid_parts/00C.wav"
        if not sample.is_file():
            self.skipTest(f"missing project sample {sample}")
        fake = json.dumps({"available": True, "engine": "Whisper tiny (mock)",
                           "transcript": "deterministic offline transcription routing check is working"})
        with patch.object(media_tools.router, "queue_owner", return_value=(False, "released")), \
             patch.object(media_tools.router, "comfy_listening", return_value=False), \
             patch.object(media_tools, "_do_transcribe", return_value=fake):
            result = json.loads(tools.call("transcribe", {"path": str(sample)}))
        self.assertTrue(result["available"])
        self.assertIn("Whisper tiny", result["engine"])
        self.assertGreater(len(result["transcript"].split()), 5)

    def test_vision_queues_when_vram_insufficient(self):
        sample = ROOT / "local_agent/uploads/45c8387e32cc5578_boundary_00_v2.png"
        if not sample.is_file():
            self.skipTest(f"missing uploaded image {sample}")

        import types
        fake_tier = [{"label": "primary", "model": "qwen3-vl-abliterated:8b-q8_0",
                      "vram_need_mb": 11500, "task_strengths": "OCR"}]
        mock_mq = types.SimpleNamespace(
            enqueue=lambda kind, args, **kwargs: {"id": "queued-abc123", "kind": kind})

        with patch.dict(sys.modules, {"media_queue": mock_mq}), \
             patch.object(media_tools.router, "gpu_free_mb", return_value=0), \
             patch.object(media_tools.caps, "vision_tiers", return_value=fake_tier):
            result = json.loads(media_tools.see_image({"path": str(sample), "question": "test"}))

        self.assertTrue(result["queued"])
        self.assertEqual("queued-abc123", result["job_id"])

    def test_real_audio_measurement_has_limitations(self):
        sample = ROOT / "outputs/equal_shares/audio/_hybrid_parts/00C.wav"
        if not sample.is_file():
            self.skipTest(f"missing project sample {sample}")
        data = json.loads(tools.call("audio_measure", {"path": str(sample)}))
        self.assertEqual(8.0, data["duration"])
        self.assertGreater(data["speech_seconds"], 0)
        self.assertIn("cannot determine", data["limitations"])

    def test_inline_video_prompt_is_found(self):
        sample = Path(r"A:\Users\rhine\ComfyUI-Shared\output\video\good audio\17.mp4")
        if not sample.is_file():
            self.skipTest(f"missing proven-good sample {sample}")
        data = json.loads(tools.call("read_video_metadata", {"path": str(sample)}))
        self.assertEqual("fl2va", data["node_path"])
        self.assertTrue(data["prompt"].startswith("subject_definitions:"))
        self.assertEqual(2, len(data["dialogue"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
