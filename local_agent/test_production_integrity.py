"""Bounded tests: no model loading, GPU work, or production state writes."""
import hashlib
import json
import os
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
sys.path.insert(0, str(ROOT / "local_agent"))
import image_render as ir
import production_integrity as gate
import prompt_pack_production as prod
import run_prompt_pack_production as worker


class RetryDenoiseTests(unittest.TestCase):
    def test_reference_retries_progress_but_are_bounded(self):
        job = {"reference_path": "reference.png", "denoise": 0.52}
        self.assertEqual(worker.retry_denoise(job, 0), 0.52)
        self.assertEqual(worker.retry_denoise(job, 1), 0.62)
        self.assertEqual(worker.retry_denoise(job, 2), 0.72)
        self.assertEqual(worker.retry_denoise(job, 3), 0.72)

    def test_t2i_keeps_base_value(self):
        self.assertEqual(worker.retry_denoise({"denoise": 0.42}, 3), 0.42)

    def test_c001_repeated_full_body_miss_gets_prompt_recovery(self):
        job = {"clip_id": "C001", "frame": "start", "prompt": "authored prompt", "negative": "base negative"}
        recovered = worker.apply_composition_recovery(job, 3)
        self.assertIn("COMPOSITION RECOVERY", recovered["prompt"])
        self.assertIn("both complete white shoes", recovered["prompt"])
        self.assertIn("cropped feet", recovered["negative"])
        self.assertEqual(recovered["composition_recovery"]["version"], "c001-full-body-v1")
        self.assertEqual(job["prompt"], "authored prompt")

    def test_other_jobs_and_early_attempts_preserve_authored_prompt(self):
        job = {"clip_id": "C002", "prompt": "authored prompt", "negative": "base negative"}
        self.assertEqual(worker.apply_composition_recovery(job, 3), job)
        c001 = {"clip_id": "C001", "prompt": "authored prompt", "negative": "base negative"}
        self.assertEqual(worker.apply_composition_recovery(c001, 2), c001)

    def test_c001_static_recovery_replaces_conflicting_long_prompt(self):
        job = {"clip_id": "C001", "frame": "start", "prompt": "long authored prompt", "negative": "base negative"}
        recovered = worker.apply_composition_recovery(job, 7)
        self.assertEqual(recovered["composition_recovery"]["version"], "c001-static-full-body-v2")
        self.assertTrue(recovered["hires_fix"] is False)
        self.assertIn("standing still", recovered["prompt"])
        self.assertNotIn("long authored prompt", recovered["prompt"])
        self.assertEqual(job["prompt"], "long authored prompt")

    def test_c001_distance_recovery_is_a_distinct_later_experiment(self):
        job = {"clip_id": "C001", "frame": "start", "prompt": "authored", "negative": "base"}
        recovered = worker.apply_composition_recovery(job, 10)
        self.assertEqual(recovered["composition_recovery"]["version"], "c001-distance-long-shot-v3")
        self.assertIn("twelve feet away", recovered["prompt"])
        self.assertIn("Viewer-perspective framing", recovered["prompt"])
        self.assertTrue(recovered["hires_fix"] is False)

    def test_c001_square_recovery_preserves_source_and_requests_derivative(self):
        job = {"clip_id": "C001", "frame": "start", "prompt": "authored", "negative": "base"}
        recovered = worker.apply_composition_recovery(job, 12)
        self.assertEqual(recovered["composition_recovery"]["version"], "c001-square-source-center-crop-v4")
        self.assertEqual((recovered["width"], recovered["height"]), (1024, 1024))
        self.assertTrue(recovered["center_crop_square_to_4_3"])

    def test_c001_square_fit_recovery_is_later_than_center_crop(self):
        job = {"clip_id": "C001", "frame": "start", "prompt": "authored", "negative": "base"}
        recovered = worker.apply_composition_recovery(job, 14)
        self.assertEqual(recovered["composition_recovery"]["version"], "c001-square-fit-sidefill-v5")
        self.assertTrue(recovered["fit_square_to_4_3"])
        self.assertNotIn("center_crop_square_to_4_3", recovered)

    def test_square_recovery_derivative_is_4_by_3_and_source_is_unchanged(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            source, dest = Path(temp) / "square.png", Path(temp) / "still.png"
            Image.new("RGB", (100, 100), "green").save(source)
            original = gate.sha256(source)
            result, transform = worker.materialize_still(source, dest, {"center_crop_square_to_4_3": True})
            self.assertEqual(result, dest)
            with Image.open(dest) as cropped:
                self.assertEqual(cropped.size, (100, 75))
            self.assertEqual(gate.sha256(source), original)
            self.assertEqual(transform["kind"], "center_crop_square_to_4_3")
            self.assertEqual(transform["source_sha256"], original)

    def test_square_fit_derivative_keeps_complete_source_in_4_by_3_canvas(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            source, dest = Path(temp) / "square.png", Path(temp) / "still.png"
            Image.new("RGB", (100, 100), "green").save(source)
            result, transform = worker.materialize_still(source, dest, {"fit_square_to_4_3": True})
            self.assertEqual(result, dest)
            with Image.open(dest) as rendered:
                self.assertEqual(rendered.size, (100, 75))
            self.assertEqual(transform["kind"], "fit_square_to_4_3_with_blurred_sidefill")
            self.assertEqual(transform["foreground_box"], [12, 0, 87, 75])


class BlindEvidenceTests(unittest.TestCase):
    def test_reference_continuity_rejects_c001_false_positive_despite_model_claim(self):
        """Regression for 6d18593c: wave passed, but the actor was replaced."""
        verdict = {"status": "pass", "reasons": []}
        reference = json.dumps({
            "hair": "short straight dark-brown hair",
            "facial_hair": "full beard",
            "clothing": ["long-sleeved olive overshirt", "gray T-shirt"],
        })
        candidate = json.dumps({
            "hair": "medium wavy brown hair",
            "facial_hair": "clean-shaven",
            "clothing": ["short-sleeved olive-green shirt", "blue jeans"],
        })
        # Reproduce the failure mode: the prompt-aware VLM incorrectly says
        # everything is continuous. Independent blind facts must still veto it.
        comparison = json.dumps({
            "same_person": True, "same_hair": True, "same_facial_hair": True,
            "same_clothing": True, "same_room_geometry": True, "differences": [],
        })
        result = worker.enforce_reference_continuity(
            verdict, reference, candidate, comparison)
        self.assertEqual(result["status"], "fail")
        self.assertIn("facial hair", " ".join(result["reasons"]))

    def test_reference_continuity_fails_closed_on_missing_comparison_fields(self):
        result = worker.enforce_reference_continuity(
            {"status": "pass", "reasons": []}, "{}", "{}", "{}")
        self.assertEqual(result["status"], "fail")
        self.assertIn("same_person", " ".join(result["reasons"]))

    def test_reference_continuity_accepts_consistent_structured_evidence(self):
        comparison = json.dumps({
            "same_person": True, "same_hair": True, "same_facial_hair": True,
            "same_clothing": True, "same_room_geometry": True, "differences": [],
        })
        result = worker.enforce_reference_continuity(
            {"status": "pass", "reasons": []},
            json.dumps({"hair": "short dark-brown hair", "facial_hair": "stubble"}),
            json.dumps({"hair": "short dark-brown hair", "facial_hair": "five o'clock shadow"}),
            comparison)
        self.assertEqual(result["status"], "pass", result["reasons"])

    def test_full_body_requires_literal_feet(self):
        verdict = {"status": "pass", "reasons": []}
        blind = json.dumps({"both_feet_visible": False, "camera_or_tripod_visible": False})
        result = worker.enforce_blind_evidence(verdict, blind, "head-to-toe, both feet visible")
        self.assertEqual(result["status"], "fail")

    def test_requested_wave_and_smile_require_literal_evidence(self):
        verdict = {"status": "pass", "reasons": []}
        blind = json.dumps({"left_hand_position": "down", "right_hand_position": "at side",
                            "visible_actions": [], "facial_expression": "neutral",
                            "both_feet_visible": True, "camera_or_tripod_visible": False})
        result = worker.enforce_blind_evidence(verdict, blind, "practiced smile, hand raised in a casual wave")
        self.assertEqual(result["status"], "fail")
        self.assertEqual(len(result["reasons"]), 2)

    def test_visible_wave_smile_and_feet_can_remain_pass(self):
        verdict = {"status": "pass", "reasons": []}
        blind = json.dumps({"left_hand_position": "raised beside shoulder",
                            "right_hand_position": "at side", "visible_actions": ["waving"],
                            "facial_expression": "smiling", "both_feet_visible": True,
                            "camera_or_tripod_visible": False})
        result = worker.enforce_blind_evidence(verdict, blind, "full-body smile, hand raised in a casual wave")
        self.assertEqual(result["status"], "pass")

    def test_explicit_room_type_must_match_blind_setting(self):
        verdict = {"status": "pass", "reasons": []}
        blind = json.dumps({"setting": "indoor hallway", "both_feet_visible": True,
                            "camera_or_tripod_visible": False})
        result = worker.enforce_blind_evidence(verdict, blind, "ordinary apartment living room")
        self.assertEqual(result["status"], "fail")
        self.assertIn("required living room", " ".join(result["reasons"]))

    def test_required_sofa_must_be_in_blind_furniture(self):
        verdict = {"status": "pass", "reasons": []}
        blind = json.dumps({"setting": "living room", "visible_furniture": ["dresser", "lamp"],
                            "both_feet_visible": True, "camera_or_tripod_visible": False})
        result = worker.enforce_blind_evidence(verdict, blind, "living room with a visible sofa or couch")
        self.assertEqual(result["status"], "fail")

    def test_c001_furniture_and_clothing_must_be_literal(self):
        verdict = {"status": "pass", "reasons": []}
        blind = json.dumps({"setting": "living room", "visible_furniture": ["sofa"],
                            "clothing": ["beige shirt", "blue jeans", "white sneakers", "watch"],
                            "both_feet_visible": True, "camera_or_tripod_visible": False})
        prompt = ("living room with a visible sofa or couch, a practical household lamp, and a "
                  "coffee table; olive-green overshirt over a gray T-shirt, jeans, white sneakers, watch")
        result = worker.enforce_blind_evidence(verdict, blind, prompt)
        self.assertEqual(result["status"], "fail")
        joined = " ".join(result["reasons"])
        self.assertIn("olive-green overshirt", joined)

    def test_forbidden_room_names_are_not_treated_as_requirements(self):
        verdict = {"status": "pass", "reasons": []}
        blind = json.dumps({"setting": "living room", "visible_furniture": ["sofa"],
                            "clothing": ["olive shirt", "blue jeans", "white sneakers"],
                            "both_feet_visible": True, "camera_or_tripod_visible": False})
        prompt = ("unmistakably a living room, not a hallway, kitchen, or bedroom; "
                  "visible sofa or couch; olive-green overshirt, jeans, white sneakers")
        result = worker.enforce_blind_evidence(verdict, blind, prompt)
        self.assertEqual(result["status"], "pass", result["reasons"])
import capabilities as caps


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def receipt(self):
        job = {"story": "test_story", "prompt": "ordinary apartment camcorder POV"}
        prefix = "stories/test_story/renders/attempt123"
        png = self.root / "outputs/stories/_comfy_output" / (prefix + "_00001_.png")
        png.parent.mkdir(parents=True)
        png.write_bytes(b"fixture-png")
        receipt = self.root / "receipt.json"
        record = {"status": "complete", "attempt_id": "attempt123", **job,
                  "prompt_id": "p1", "graph": {"7": {"class_type": "SaveImage", "inputs": {"filename_prefix": prefix}}},
                  "verified_outputs": [{"path": str(png), "sha256": gate.sha256(png)}]}
        receipt.write_text(json.dumps(record))
        return job, png, receipt, record

    def test_nested_receipt_ignores_stdout(self):
        job, png, receipt, _ = self.receipt()
        self.assertEqual(gate.read_attempt_receipt(receipt, self.root, job, "attempt123", 0), png.resolve())

    def test_historical_png_rejected(self):
        job, png, receipt, record = self.receipt()
        for modification in ("old_time", "wrong_attempt", "wrong_path", "changed_hash"):
            with self.subTest(modification=modification):
                altered = json.loads(json.dumps(record))
                started = 0
                if modification == "old_time":
                    started = png.stat().st_mtime + 1
                elif modification == "wrong_attempt":
                    altered["attempt_id"] = "old"
                elif modification == "wrong_path":
                    altered["verified_outputs"][0]["path"] = str(self.root / "old.png")
                else:
                    altered["verified_outputs"][0]["sha256"] = "bad"
                receipt.write_text(json.dumps(altered))
                with self.assertRaises(ValueError):
                    gate.read_attempt_receipt(receipt, self.root, job, "attempt123", started)

    def test_missing_receipt_never_scans_old_png(self):
        job, png, receipt, _ = self.receipt()
        receipt.unlink()
        with self.assertRaises(FileNotFoundError):
            gate.read_attempt_receipt(receipt, self.root, job, "attempt123", 0)
        self.assertTrue(png.is_file())

    def fixture_approved(self):
        jobs, stills = [], {}
        review = {"status": "approved", "source_sha256": "revision", "approval_kind": "explicit_operator",
                  "approved_by": "test-operator", "approved_at": 1, "stills": {}}
        for key in ("c1_start", "c1_last", "c2_start", "c2_last"):
            path = self.root / (key + ".png")
            path.write_bytes(key.encode())
            digest = gate.sha256(path)
            prompt_hash = hashlib.sha256(key.encode()).hexdigest()
            jobs.append({"story": key, "prompt": key})
            stills[key] = {"png": str(path), "sha256": digest, "accuracy_gate": {
                "status": "pass", "semantic_check": "pass", "image_sha256": digest,
                "prompt_sha256": prompt_hash, "canonical_prompt_sha256": prompt_hash,
                "qa_prompt_sha256": prompt_hash, "generation_prompt_sha256": prompt_hash,
                "semantic_evidence": {
                    "image_sha256": digest, "prompt_sha256": prompt_hash,
                    "qa_prompt_sha256": prompt_hash, "generation_prompt_sha256": prompt_hash,
                    "model_sha256": caps.QWEN25_VL_WEIGHTS_SHA256,
                    "projector_sha256": caps.QWEN25_VL_MMPROJ_SHA256,
                    "runtime": "llama.cpp", "verdict": "pass"}}}
            review["stills"][key] = {"path": str(path.resolve()), "sha256": digest}
        videos = [{"clip_id": "C001", "story_start": "c1_start", "story_last": "c1_last"},
                  {"clip_id": "C002", "story_start": "c2_start", "story_last": "c2_last"}]
        return jobs, stills, review, videos

    def test_semantic_not_run_is_not_approved(self):
        jobs, stills, review, videos = self.fixture_approved()
        stills["c1_start"]["accuracy_gate"]["semantic_check"] = "not_run"
        with self.assertRaisesRegex(ValueError, "semantic QA"):
            gate.bind_video_jobs(videos, jobs, stills, review, "revision")

    def test_semantic_model_and_prompt_must_match(self):
        jobs, stills, review, videos = self.fixture_approved()
        stills["c1_start"]["accuracy_gate"]["semantic_evidence"]["projector_sha256"] = "substitute"
        with self.assertRaises(ValueError):
            gate.bind_video_jobs(videos, jobs, stills, review, "revision")

    def test_recovery_qa_target_is_traceable_without_replacing_canonical_binding(self):
        jobs, stills, review, _videos = self.fixture_approved()
        evidence = stills["c1_start"]["accuracy_gate"]
        delivery_hash = hashlib.sha256(b"delivery target").hexdigest()
        evidence["qa_prompt_sha256"] = delivery_hash
        evidence["semantic_evidence"]["qa_prompt_sha256"] = delivery_hash
        self.assertTrue(gate.qa_passed(stills["c1_start"], jobs[0]))
        evidence["semantic_evidence"]["qa_prompt_sha256"] = "wrong"
        self.assertFalse(gate.qa_passed(stills["c1_start"], jobs[0]))

    def test_delivery_rubric_recovery_pass_is_not_reopened_on_restart(self):
        jobs, stills, _review, _videos = self.fixture_approved()
        authored = hashlib.sha256(jobs[0]["prompt"].encode()).hexdigest()
        delivery = hashlib.sha256(b"empty floor pov delivery rubric").hexdigest()
        evidence = stills["c1_start"]["accuracy_gate"]
        evidence["prompt_sha256"] = delivery
        evidence["canonical_prompt_sha256"] = delivery
        evidence["qa_prompt_sha256"] = delivery
        evidence["generation_prompt_sha256"] = authored
        evidence["semantic_evidence"]["prompt_sha256"] = delivery
        evidence["semantic_evidence"]["qa_prompt_sha256"] = delivery
        evidence["semantic_evidence"]["generation_prompt_sha256"] = authored
        self.assertTrue(gate.qa_passed(stills["c1_start"], jobs[0]))
        evidence["generation_prompt_sha256"] = delivery
        evidence["semantic_evidence"]["generation_prompt_sha256"] = delivery
        self.assertFalse(gate.qa_passed(stills["c1_start"], jobs[0]))

    def test_c026_scene_reframe_delivery_is_traceable_without_reopening(self):
        jobs, stills, _review, _videos = self.fixture_approved()
        record = stills["c1_start"]
        authored = hashlib.sha256(jobs[0]["prompt"].encode()).hexdigest()
        delivery = hashlib.sha256(b"c026 empty continuation corridor").hexdigest()
        generated = hashlib.sha256(b"c026 recovery generation prompt").hexdigest()
        evidence = record["accuracy_gate"]
        record["canonical_prompt_sha256"] = authored
        evidence["prompt_sha256"] = delivery
        evidence["canonical_prompt_sha256"] = delivery
        evidence["qa_prompt_sha256"] = delivery
        evidence["generation_prompt_sha256"] = generated
        semantic = evidence["semantic_evidence"]
        semantic["prompt_sha256"] = delivery
        semantic["qa_prompt_sha256"] = delivery
        semantic["generation_prompt_sha256"] = generated
        (Path(record["png"]).parent / "identity_control.json").write_text(json.dumps({
            "version": "c026-start-pov-corner-reframe-v2",
            "render_mode": "scene_i2i_reframe",
            "semantic_assertions_prompt": "delivery_qa_prompt",
        }), encoding="utf-8")
        self.assertTrue(gate.qa_passed(record, jobs[0]))
        (Path(record["png"]).parent / "identity_control.json").write_text(json.dumps({
            "version": "other-recovery-v1",
            "render_mode": "scene_i2i_reframe",
            "semantic_assertions_prompt": "delivery_qa_prompt",
        }), encoding="utf-8")
        self.assertFalse(gate.qa_passed(record, jobs[0]))

    def test_authored_pass_allows_distinct_generation_prompt_hash(self):
        jobs, stills, _review, _videos = self.fixture_approved()
        other = hashlib.sha256(b"generation variant").hexdigest()
        evidence = stills["c1_start"]["accuracy_gate"]
        evidence["generation_prompt_sha256"] = other
        evidence["semantic_evidence"]["generation_prompt_sha256"] = other
        self.assertTrue(gate.qa_passed(stills["c1_start"], jobs[0]))

    def test_operator_rejection_overrides_automated_qa_pass(self):
        jobs, stills, _review, _videos = self.fixture_approved()
        record = stills["c1_start"]
        self.assertTrue(gate.qa_passed(record, jobs[0]))
        image = Path(record["png"])
        (image.parent / "operator_review.json").write_text(json.dumps({
            "decision": "reject",
            "reason_codes": ["malformed_hand_anatomy"],
            "image_sha256": record["sha256"],
        }), encoding="utf-8")
        self.assertFalse(gate.qa_passed(record, jobs[0]))

    def test_automatic_approval_is_rejected(self):
        jobs, stills, review, videos = self.fixture_approved()
        review["auto_approved_reason"] = "full production requested"
        with self.assertRaisesRegex(ValueError, "explicit operator"):
            gate.bind_video_jobs(videos, jobs, stills, review, "revision")

    def test_approved_paths_hashes_chain_and_stage(self):
        jobs, stills, review, videos = self.fixture_approved()
        bound = gate.bind_video_jobs(videos, jobs, stills, review, "revision")
        self.assertEqual(bound[0]["references"]["last"], bound[1]["references"]["first"])
        ref = bound[1]["references"]["first"]
        staged = worker.stage_input(self.root / "input", Path(ref["path"]), "C002", ref["sha256"])
        self.assertEqual(gate.sha256(self.root / "input" / staged), ref["sha256"])
        import render_single_pass as h3
        job = {**bound[1], "video_prompt": "camcorder POV", "seed": 1}
        wf = worker.build_video_workflow(h3, job, staged, "last.png", "attempt", "4:3")
        self.assertEqual(wf["137"]["inputs"]["image"], staged)
        self.assertEqual(wf["136"]["inputs"]["first_frame"], ["137", 0])
        self.assertEqual(wf["136"]["inputs"]["last_frame"], ["139", 0])
        self.assertEqual(wf["115"]["inputs"]["aspect_ratio"], "4:3")
        Path(ref["path"]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            gate.bind_video_jobs(videos, jobs, stills, review, "revision")

    def test_versioned_copy_never_overwrites(self):
        src, dst = self.root / "source", self.root / "approved"
        src.write_bytes(b"new")
        dst.write_bytes(b"old")
        with self.assertRaises(FileExistsError):
            gate.copy_evidence(src, dst)
        self.assertEqual(dst.read_bytes(), b"old")

    def test_watchdog_captures_100_lines_and_owner(self):
        ledger, log = self.root / "ledger.json", self.root / "production.log"
        ledger.write_text(json.dumps({"status": "running", "progress_at": 10}))
        log.write_text("\n".join(str(i) for i in range(150)))
        os.utime(log, (10, 10))
        owner = self.root / "work/runtime/image_render_owner.json"
        owner.parent.mkdir(parents=True)
        owner.write_text('{"pid": 123}')
        report = gate.diagnose_stale(self.root, ledger, log, 60, now=100)
        self.assertEqual(len(report["last_100_log_lines"][str(log)]), 100)
        self.assertEqual(json.loads(report["owner_state"])["pid"], 123)
        self.assertEqual(report["ledger"]["progress_at"], 10)
        self.assertIsNone(gate.diagnose_stale(self.root, ledger, log, 60, now=20))

    def test_stale_owner_preserved_and_live_child_blocks(self):
        owner = self.root / "owner.json"
        with mock.patch.object(ir, "IMAGE_OWNER", owner), mock.patch.object(ir, "_pid_alive", side_effect=lambda pid: pid == 99):
            owner.write_text('{"pid": 10, "backend_pid": 99}')
            with self.assertRaises(ir.ImageRenderError):
                ir._write_owner()
            owner.write_text('{"pid": 10, "backend_pid": 0}')
            ir._write_owner()
            self.assertEqual(json.loads(owner.read_text())["pid"], os.getpid())
            self.assertEqual(len(list(self.root.glob("image_render_owner.*.json"))), 1)

    def test_release_cannot_clear_other_owner_or_live_child(self):
        owner = self.root / "owner.json"
        with mock.patch.object(ir, "IMAGE_OWNER", owner), mock.patch.object(ir, "_pid_alive", return_value=True):
            owner.write_text('{"pid": 123}')
            ir._release_owner()
            self.assertEqual(json.loads(owner.read_text())["pid"], 123)
            owner.write_text(json.dumps({"pid": os.getpid(), "backend_pid": 99}))
            with self.assertRaises(ir.ImageRenderError):
                ir._release_owner()

    def test_startup_success_failure_diagnostics(self):
        for ready in (True, False):
            with self.subTest(ready=ready), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                (base / "main.py").touch()
                (base / "python.exe").touch()
                (base / "models.yaml").touch()
                proc = mock.Mock(pid=123)
                proc.poll.return_value = None if ready else 1
                overrides = {"ROOT": base, "COMFY_ROOT": base, "COMFY_PYTHON": base / "python.exe",
                             "MODEL_PATHS": base / "models.yaml", "IMAGE_RUNTIME": base / "runtime",
                             "IMAGE_OWNER": base / "owner", "IMAGE_INPUT": base / "input",
                             "IMAGE_USER": base / "user", "IMAGE_TEMP": base / "temp", "IMAGE_OUTPUT": base / "output"}
                with mock.patch.multiple(ir, **overrides), mock.patch.object(ir, "_port_open", return_value=False), \
                     mock.patch.object(ir.subprocess, "Popen", return_value=proc) as launch, \
                     mock.patch.object(ir, "_get_json", return_value={"SaveImage": {}}), \
                     mock.patch.object(ir.thermal_guard, "check_running_ceiling"), \
                     mock.patch.object(ir, "_stop_owned_backend") as stop:
                    if ready:
                        self.assertIs(ir._start_owned_backend(startup_timeout=.1), proc)
                    else:
                        with self.assertRaises(ir.ImageRenderError):
                            ir._start_owned_backend(startup_timeout=.1)
                        stop.assert_called_once_with(proc)
                    env = launch.call_args.kwargs["env"]
                    self.assertEqual(env["NUMBA_CACHE_DIR"], str(base / "work/runtime/numba_cache"))
                    health = list((base / "runtime/logs").glob("*.health.*.json"))
                    self.assertEqual(json.loads(health[0].read_text())["state"], "server_ready" if ready else "process_exited")

    def test_startup_final_check_at_deadline(self):
        # 2026-09-24: a backend reached "Starting server" just after the 240 s
        # deadline and was torn down.  The probe at the deadline must win that race.
        for ready_at_deadline in (True, False):
            with self.subTest(ready_at_deadline=ready_at_deadline), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                (base / "main.py").touch()
                (base / "python.exe").touch()
                (base / "models.yaml").touch()
                proc = mock.Mock(pid=123)
                proc.poll.return_value = None
                clock = {"now": 1000.0}
                fake_time = mock.Mock()
                fake_time.monotonic.side_effect = lambda: clock["now"]
                fake_time.sleep.side_effect = lambda s: clock.__setitem__("now", clock["now"] + s)
                deadline = 1000.0 + 1.0
                probes = []

                def probe(url, timeout=8):
                    probes.append((clock["now"], timeout))
                    if ready_at_deadline and clock["now"] >= deadline:
                        return {"SaveImage": {}}
                    raise ir.ImageRenderError("connection refused")

                overrides = {"ROOT": base, "COMFY_ROOT": base, "COMFY_PYTHON": base / "python.exe",
                             "MODEL_PATHS": base / "models.yaml", "IMAGE_RUNTIME": base / "runtime",
                             "IMAGE_OWNER": base / "owner", "IMAGE_INPUT": base / "input",
                             "IMAGE_USER": base / "user", "IMAGE_TEMP": base / "temp", "IMAGE_OUTPUT": base / "output"}
                with mock.patch.multiple(ir, **overrides), mock.patch.object(ir, "_port_open", return_value=False), \
                     mock.patch.object(ir, "time", fake_time), \
                     mock.patch.object(ir.subprocess, "Popen", return_value=proc), \
                     mock.patch.object(ir, "_get_json", side_effect=probe), \
                     mock.patch.object(ir.thermal_guard, "check_running_ceiling") as thermal, \
                     mock.patch.object(ir, "_stop_owned_backend") as stop:
                    if ready_at_deadline:
                        self.assertIs(ir._start_owned_backend(startup_timeout=1.0), proc)
                        stop.assert_not_called()
                    else:
                        with self.assertRaisesRegex(ir.ImageRenderError, "startup deadline exceeded"):
                            ir._start_owned_backend(startup_timeout=1.0)
                        stop.assert_called_once_with(proc)
                # Every in-loop probe failed; exactly one extra full-length probe ran at the deadline.
                self.assertTrue(all(at < deadline for at, _ in probes[:-1]))
                self.assertEqual(probes[-1], (deadline, 2))
                self.assertEqual(thermal.call_count, len(probes))
                health = json.loads(next((base / "runtime/logs").glob("*.health.*.json")).read_text())
                if ready_at_deadline:
                    self.assertEqual(health["state"], "server_ready")
                    self.assertTrue(health["ready_on_final_check"])
                else:
                    self.assertEqual(health["state"], "alive_not_listening")
                    self.assertEqual(health["error"], "startup deadline exceeded")

    def test_wait_for_outputs_tolerates_history_timeout(self):
        # 2026-09-24: one 8 s /history read timeout killed a job whose image was
        # written moments later.  A transport failure must be retried.
        image = {"filename": "x_00001_.png", "subfolder": "", "type": "output"}
        done = {"pid": {"status": {"status_str": "success"}, "outputs": {"9": {"images": [image]}}}}
        proc = mock.Mock()
        proc.poll.return_value = None
        with mock.patch.object(ir, "_get_json", side_effect=[ir.ImageRenderError("timed out"), done]) as poll, \
             mock.patch.object(ir.thermal_guard, "check_running_ceiling") as thermal, \
             mock.patch.object(ir.time, "sleep"):
            self.assertEqual(ir._wait_for_outputs("pid", proc, timeout_s=60, output_node_ids={"9"}), [image])
        self.assertEqual(poll.call_count, 2)
        thermal.assert_called_once()

    def test_wait_for_outputs_graph_error_still_raises(self):
        failed = {"pid": {"status": {"status_str": "error"}, "outputs": {}}}
        with mock.patch.object(ir, "_get_json", return_value=failed) as poll, \
             mock.patch.object(ir.thermal_guard, "check_running_ceiling"), \
             mock.patch.object(ir.time, "sleep"):
            with self.assertRaisesRegex(ir.ImageRenderError, "image graph failed"):
                ir._wait_for_outputs("pid", None, timeout_s=60)
        poll.assert_called_once()

    def test_wait_for_outputs_backend_exit_still_raises(self):
        proc = mock.Mock(returncode=1)
        proc.poll.return_value = 1
        with mock.patch.object(ir, "_get_json") as poll, \
             mock.patch.object(ir.thermal_guard, "check_running_ceiling"):
            with self.assertRaisesRegex(ir.ImageRenderError, "owned ComfyUI exited"):
                ir._wait_for_outputs("pid", proc, timeout_s=60)
        poll.assert_not_called()

    def test_busy_port_never_launches(self):
        with mock.patch.object(ir, "_port_open", return_value=True), mock.patch.object(ir.subprocess, "Popen") as launch:
            with self.assertRaises(ir.ImageRenderError):
                ir._start_owned_backend()
            launch.assert_not_called()

    def test_lock_refuses_overlap_and_releases(self):
        path = self.root / "worker.lock"
        with gate.process_lock(path):
            with self.assertRaises(RuntimeError):
                with gate.process_lock(path):
                    pass
        with gate.process_lock(path):
            pass

    def test_watchdog_failure_is_sticky(self):
        ledger = self.root / "production.json"
        with mock.patch.object(prod, "production_path", return_value=ledger):
            prod.save_production("test", {"status": "error", "watchdog_failure": "evidence.json"})
            prod.save_production("test", {"status": "running"})
            current = json.loads(ledger.read_text())
            self.assertEqual(current["status"], "error")
            self.assertEqual(current["watchdog_failure"], "evidence.json")
            self.assertEqual(len(list((self.root / "ledger_history").glob("*.json"))), 1)

    def test_watchdog_allows_supervised_pause_to_update_ledger(self):
        running = {"status": "running", "watchdog_token": "token", "supervisor_pid": 123,
                   "log_path": str(self.root / "production.log")}
        paused = {"status": "paused_for_composition_recovery", "watchdog_token": "token"}
        with mock.patch.object(prod, "load_production", side_effect=[running, paused]), \
             mock.patch.object(prod, "production_path", return_value=self.root / "production.json"), \
             mock.patch.object(prod, "_pid_live", return_value=False), \
             mock.patch.object(worker, "snapshot_stale") as stale, \
             mock.patch.object(worker.time, "sleep"):
            self.assertEqual(worker.watchdog("test", self.root, token="token"), 0)
        stale.assert_not_called()

    def test_semantic_pending_record_cannot_be_operator_approved(self):
        with mock.patch.object(prod, "load_production", return_value={"source_sha256": "rev", "stills": {}}), \
             mock.patch.object(prod, "build_still_jobs", return_value=[{"story": "test", "prompt": "test"}]):
            with self.assertRaisesRegex(ValueError, "semantic QA"):
                prod.record_explicit_approval("test", approved_by="operator")


class WatchdogTerminationTests(unittest.TestCase):
    """Fix 2026-09-23 (readiness-audit finding "other risks", fix-set item
    #10, second half): the watchdog previously only ever *recorded* a
    stale/hung production (status="error" + watchdog_failure) and
    returned -- it never stopped the process it had just diagnosed as
    stuck. A genuinely hung (alive, not already-exited) supervisor kept
    running and holding the GPU indefinitely. These cover both the new
    termination path and that an already-exited supervisor is correctly
    left alone (nothing to terminate)."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_watchdog_terminates_a_genuinely_hung_supervisor_instead_of_only_recording_it(self):
        ledger = self.root / "production.json"
        running = {"status": "running", "watchdog_token": "token", "supervisor_pid": 4321,
                   "log_path": str(self.root / "production.log")}
        with mock.patch.object(prod, "load_production", return_value=running),              mock.patch.object(prod, "production_path", return_value=ledger),              mock.patch.object(prod, "_pid_live", side_effect=[True, False]),              mock.patch.object(worker, "snapshot_stale", return_value="stale evidence path"),              mock.patch.object(
                 worker, "_kill_pid",
                 return_value={"pid": 4321, "attempted": True, "method": "SIGKILL", "error": None},
             ) as kill_mock,              mock.patch.object(worker.time, "sleep"):
            self.assertEqual(worker.watchdog("test", self.root, token="token"), 1)
        kill_mock.assert_called_once_with(4321)
        saved = json.loads(ledger.read_text())
        self.assertEqual(saved["status"], "error")
        self.assertEqual(saved["watchdog_termination"]["method"], "SIGKILL")
        self.assertTrue(saved["watchdog_termination"]["verified_dead"])

    def test_watchdog_does_not_attempt_termination_when_supervisor_already_exited(self):
        """The existing 'already dead' path (a deliberate pause, or a
        process that had already exited on its own) must be unaffected:
        there is nothing to terminate, so _kill_pid must not be called."""
        ledger = self.root / "production.json"
        running = {"status": "running", "watchdog_token": "token", "supervisor_pid": 4321,
                   "log_path": str(self.root / "production.log")}
        with mock.patch.object(prod, "load_production", return_value=running),              mock.patch.object(prod, "production_path", return_value=ledger),              mock.patch.object(prod, "_pid_live", side_effect=[False, False]),              mock.patch.object(worker, "snapshot_stale", return_value="stale evidence path"),              mock.patch.object(worker, "_kill_pid") as kill_mock,              mock.patch.object(worker.time, "sleep"):
            self.assertEqual(worker.watchdog("test", self.root, token="token"), 1)
        kill_mock.assert_not_called()
        saved = json.loads(ledger.read_text())
        self.assertEqual(saved["status"], "error")
        self.assertIsNone(saved["watchdog_termination"])

    def test_kill_pid_posix_sends_sigkill(self):
        # Force the POSIX branch: on Windows the unpatched os.name sent a REAL
        # `taskkill /PID 4321 /T /F`, and signal.SIGKILL does not exist there.
        with mock.patch.object(worker.os, "name", "posix"), \
                mock.patch.object(worker.signal, "SIGKILL", 9, create=True), \
                mock.patch.object(worker.subprocess, "run") as run_mock, \
                mock.patch.object(worker.os, "kill") as kill_mock:
            result = worker._kill_pid(4321)
        run_mock.assert_not_called()
        kill_mock.assert_called_once_with(4321, 9)
        self.assertTrue(result["attempted"])
        self.assertEqual(result["method"], "SIGKILL")
        self.assertIsNone(result["error"])

    def test_kill_pid_windows_uses_forceful_taskkill(self):
        with mock.patch.object(worker.os, "name", "nt"),              mock.patch.object(worker.subprocess, "run") as run_mock:
            result = worker._kill_pid(4321)
        run_mock.assert_called_once()
        args = run_mock.call_args.args[0]
        self.assertEqual(args, ["taskkill", "/PID", "4321", "/T", "/F"])
        self.assertTrue(result["attempted"])
        self.assertEqual(result["method"], "taskkill /T /F")

    def test_kill_pid_rejects_invalid_pid_without_attempting_anything(self):
        for bad in (None, 0, -5, "not-a-pid"):
            with mock.patch.object(worker.os, "kill") as kill_mock, \
                    mock.patch.object(worker.subprocess, "run") as run_mock:
                result = worker._kill_pid(bad)
            kill_mock.assert_not_called()
            run_mock.assert_not_called()
            self.assertFalse(result["attempted"])
            self.assertIsNotNone(result["error"])


class ImageManifestEffectiveSettingsTests(unittest.TestCase):
    """The receipt must describe the graph that ran, not argparse defaults."""

    def _manifest(self, argv):
        args = ir.parse_args(["--story", "s", "--prompt", "a room", "--plan"] + argv)
        graph = ir.build_graph(
            mode=args.mode, prompt=args.prompt, negative=args.negative,
            model=ir.MODEL_PROFILES[args.model_profile]["model"], seed=args.seed,
            width=args.width, height=args.height, steps=args.steps, cfg=args.cfg,
            sampler=args.sampler, scheduler=args.scheduler, denoise=args.denoise,
            prefix="stories/s/renders/a", profile=args.model_profile,
            hires_fix=args.hires_fix, reference_name=args.reference)
        with mock.patch.object(ir, "_now", return_value="t"):
            return ir.manifest("s", args, graph), graph

    def test_realpro_flux_records_graph_values_and_keeps_request(self):
        record, graph = self._manifest(["--model-profile", "realpro_flux"])
        sampler = graph["7"]["inputs"]
        self.assertEqual(record["model"], graph["1"]["inputs"]["unet_name"])
        self.assertEqual(record["model"], ir.REALPRO_FLUX_UNET)
        self.assertEqual(
            (record["sampler"], record["scheduler"], record["cfg"], record["denoise"], record["steps"]),
            (sampler["sampler_name"], sampler["scheduler"], sampler["cfg"], sampler["denoise"], sampler["steps"]))
        self.assertEqual((record["sampler"], record["scheduler"], record["cfg"], record["denoise"]),
                         ("euler", "simple", 1.0, 1.0))
        self.assertEqual(record["requested"], {
            "model": ir.DEFAULT_MODEL, "steps": ir.DEFAULT_STEPS, "cfg": 6.0,
            "sampler": "dpmpp_2m_sde", "scheduler": "karras", "denoise": 0.55,
            "hires_fix": True, "width": 1024, "height": 1024})
        # Flux never builds the hi-res pass, whatever the flag says.
        self.assertIs(record["hires_fix"], False)
        self.assertEqual((record["width"], record["height"]), (1024, 1024))
        self.assertIs(record["graph"], graph)

    def test_hires_fix_records_whether_the_graph_has_the_pass(self):
        record, graph = self._manifest([])
        self.assertEqual(graph["10"]["inputs"]["latent_image"], ["9", 0])
        self.assertIs(record["hires_fix"], True)
        record, graph = self._manifest(["--no-hires-fix"])
        self.assertNotIn("9", graph)
        self.assertIs(record["hires_fix"], False)
        self.assertIs(record["requested"]["hires_fix"], False)
        for argv in (["--model-profile", "alicemix_sd15"], ["--mode", "i2i", "--reference", "r.png"]):
            record, graph = self._manifest(argv)
            self.assertIs(record["hires_fix"], False, argv)
            self.assertIs(record["requested"]["hires_fix"], True, argv)

    def test_primary_pass_wins_over_hires_and_profile_model_wins_over_flag(self):
        record, graph = self._manifest(
            ["--model-profile", "alicemix_sd15", "--model", "ignored.safetensors"])
        self.assertEqual(record["model"], ir.ALICEMIX_SD15_CHECKPOINT)
        self.assertEqual(record["requested"]["model"], "ignored.safetensors")
        # t2i pins the first pass to denoise 1.0 regardless of --denoise.
        self.assertEqual(record["denoise"], 1.0)
        record, graph = self._manifest([])
        self.assertIn("10", graph)  # hi-res second pass exists at a lower denoise
        self.assertEqual(record["denoise"], graph["5"]["inputs"]["denoise"])
        self.assertNotEqual(record["denoise"], graph["10"]["inputs"]["denoise"])

    def test_graph_without_loader_or_sampler_records_none(self):
        self.assertEqual(ir.effective_settings({"9": {"class_type": "SaveImage", "inputs": {}}}),
                         dict(dict.fromkeys(("model", "steps", "cfg", "sampler", "scheduler", "denoise",
                                             "width", "height")),
                              hires_fix=False))

    def test_width_height_predict_the_saved_image(self):
        record, graph = self._manifest([])
        self.assertEqual((record["width"], record["height"]), (1536, 1536))
        self.assertEqual((record["requested"]["width"], record["requested"]["height"]), (1024, 1024))
        record, graph = self._manifest(["--no-hires-fix", "--width", "832", "--height", "1216"])
        self.assertEqual((record["width"], record["height"]), (832, 1216))
        # 1000/8=125 -> round(187.5)=188 -> 1504; 776/8=97 -> round(145.5)=146 -> 1168,
        # the same Python round() ComfyUI's LatentUpscaleBy applies to latent pixels.
        record, graph = self._manifest(["--width", "1000", "--height", "776"])
        self.assertEqual((record["width"], record["height"]), (1504, 1168))
        # i2i takes the reference image's size; the graph cannot know it.
        record, graph = self._manifest(["--mode", "i2i", "--reference", "r.png"])
        self.assertEqual((record["width"], record["height"]), (None, None))
        self.assertEqual((record["requested"]["width"], record["requested"]["height"]), (1024, 1024))

    def test_measured_png_size_replaces_prediction(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            png, other, text = Path(temp) / "a.png", Path(temp) / "b.png", Path(temp) / "c.txt"
            Image.new("RGB", (768, 1152)).save(png)
            Image.new("RGB", (512, 512)).save(other)
            text.write_text("not a png", encoding="utf-8")
            self.assertEqual(ir.png_size(png), (768, 1152))
            self.assertIsNone(ir.png_size(text))
            record = {"width": None, "height": None}
            ir.apply_measured_size(record, [{"width": 768, "height": 1152}])
            self.assertEqual((record["width"], record["height"]), (768, 1152))
            record = {"width": 1536, "height": 1536}
            ir.apply_measured_size(record, [{"width": 768, "height": 1152}, {"width": 512, "height": 512}])
            self.assertEqual((record["width"], record["height"]), (1536, 1536))
            ir.apply_measured_size(record, [{"width": None, "height": None}])
            self.assertEqual((record["width"], record["height"]), (1536, 1536))


if __name__ == "__main__":
    unittest.main()
