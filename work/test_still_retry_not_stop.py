import json
import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import image_render
import run_prompt_pack_production as w


class StillRetryNotStop(unittest.TestCase):
    def test_blind_subject_fields_are_losslessly_normalized(self):
        raw = json.dumps({"subjects": [{
            "facial_expression": "pained", "left_hand_position": "floor",
            "right_hand_position": "floor", "visible_actions": ["crouching"],
        }]})
        normalized = w._json_object(w.normalize_blind_subject_fields(raw))
        self.assertEqual(normalized["facial_expression"], "pained")
        self.assertEqual(normalized["left_hand_position"], "floor")
        self.assertEqual(normalized["right_hand_position"], "floor")
        self.assertEqual(normalized["visible_actions"], ["crouching"])

    def test_c014_last_switches_to_bounded_ipadapter_identity_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("ordinary-one", "ordinary-two"):
                attempt = root / name
                attempt.mkdir()
                (attempt / "failure.json").write_text(
                    json.dumps({"error": "semantic still QA failed"}),
                    encoding="utf-8",
                )
                (attempt / "qa.json").write_text(
                    json.dumps({"semantic_check": "fail"}), encoding="utf-8"
                )
            base = {
                "clip_id": "C014", "frame": "last",
                "reference_path": str(root / "c014-start.png"),
                "prompt": "same actor holds a backward brace",
                "negative": "low quality", "denoise": 0.52,
            }
            recovered = w.apply_c014_last_identity_recovery(base, 8, root)
            control = recovered["identity_control"]
            self.assertEqual(control["version"], "c014-last-fullframe-ipadapter-v1")
            self.assertEqual(control["render_mode"], "i2i_identity")
            self.assertEqual(control["max_attempts"], 2)
            self.assertEqual(recovered["denoise"], 0.48)
            self.assertIn("unseen support", recovered["prompt"])
            self.assertIn("visible camera", recovered["negative"])

            second = root / "conditioned-one"
            second.mkdir()
            (second / "identity_control.json").write_text(json.dumps({
                "version": "c014-last-fullframe-ipadapter-v1",
                "policy_revision": "same-actor-backward-brace-v1",
            }), encoding="utf-8")
            (second / "failure.json").write_text(
                json.dumps({"error": "semantic still QA failed"}), encoding="utf-8"
            )
            final_try = w.apply_c014_last_identity_recovery(base, 9, root)
            self.assertEqual(final_try["denoise"], 0.36)
            self.assertEqual(final_try["identity_control"]["identity_weight"], 1.08)
            self.assertNotIn("tripod-mounted", final_try["qa_prompt"])

    def test_c014_last_endpoint_donor_uses_canonical_brief_after_pose_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            failed = root / "localized-pose"
            failed.mkdir()
            (failed / "identity_control.json").write_text(json.dumps({
                "version": "c014-last-localized-openpose-v2",
                "policy_revision": "lower-body-backward-brace-v1",
            }), encoding="utf-8")
            (failed / "failure.json").write_text(
                json.dumps({"error": "semantic still QA failed"}), encoding="utf-8"
            )
            base = {"clip_id": "C014", "frame": "last", "reference_path": "start.png"}
            recovered = w.apply_c014_last_endpoint_recovery(base, 13, root)
            control = recovered["identity_control"]
            self.assertEqual(control["version"], "c014-last-hash-pinned-endpoint-v3")
            self.assertEqual(control["render_mode"], "c014_last_endpoint_donor")
            self.assertEqual(control["endpoint_donor_path"], str(w.C014_LAST_DONOR_PATH))
            self.assertEqual(control["endpoint_donor_sha256"], w.C014_LAST_DONOR_SHA256)
            self.assertIn("body is leaned backward", recovered["qa_prompt"])
            self.assertNotIn("below the lower frame", recovered["qa_prompt"])
            self.assertEqual(control["pose_qa_crop_fraction"], [0.25, 0.24, 0.76, 0.99])

            v1 = root / "endpoint-v1"
            v1.mkdir()
            (v1 / "identity_control.json").write_text(json.dumps({
                "version": "c014-last-hash-pinned-endpoint-v3",
                "policy_revision": "canonical-backward-lean-brief-v1",
            }), encoding="utf-8")
            (v1 / "failure.json").write_text(
                json.dumps({"error": "semantic still QA failed"}), encoding="utf-8"
            )
            refined = w.apply_c014_last_endpoint_recovery(base, 14, root)
            self.assertEqual(refined["identity_control"]["version"],
                             "c014-last-hash-pinned-endpoint-v4")
            self.assertEqual(refined["identity_control"]["endpoint_donor_path"],
                             str(w.C014_LAST_DONOR_V2_PATH))

            v2 = root / "endpoint-v2"
            v2.mkdir()
            (v2 / "identity_control.json").write_text(json.dumps({
                "version": "c014-last-hash-pinned-endpoint-v4",
                "policy_revision": "canonical-backward-lean-brief-v2",
            }), encoding="utf-8")
            (v2 / "failure.json").write_text(
                json.dumps({"error": "semantic still QA failed"}), encoding="utf-8"
            )
            final = w.apply_c014_last_endpoint_recovery(base, 15, root)
            self.assertEqual(final["identity_control"]["version"],
                             "c014-last-hash-pinned-endpoint-v5")
            self.assertEqual(final["identity_control"]["endpoint_donor_path"],
                             str(w.C014_LAST_DONOR_V3_PATH))

            v3 = root / "endpoint-v3"
            v3.mkdir()
            (v3 / "identity_control.json").write_text(json.dumps({
                "version": "c014-last-hash-pinned-endpoint-v5",
                "policy_revision": "canonical-backward-lean-brief-v3",
            }), encoding="utf-8")
            (v3 / "failure.json").write_text(
                json.dumps({"error": "semantic still QA failed"}), encoding="utf-8"
            )
            rechecked = w.apply_c014_last_endpoint_recovery(base, 16, root)
            self.assertEqual(rechecked["identity_control"]["version"],
                             "c014-last-hash-pinned-endpoint-v6")
            self.assertEqual(rechecked["identity_control"]["endpoint_donor_path"],
                             str(w.C014_LAST_DONOR_V3_PATH))

            v4 = root / "endpoint-v4"
            v4.mkdir()
            (v4 / "identity_control.json").write_text(json.dumps({
                "version": "c014-last-hash-pinned-endpoint-v6",
                "policy_revision": "pose-crop-recheck-v4",
            }), encoding="utf-8")
            (v4 / "failure.json").write_text(
                json.dumps({"error": "semantic still QA failed"}), encoding="utf-8"
            )
            repaired = w.apply_c014_last_endpoint_recovery(base, 17, root)
            self.assertEqual(repaired["identity_control"]["version"],
                             "c014-last-hash-pinned-endpoint-v7")

            v5 = root / "endpoint-v5"
            v5.mkdir()
            (v5 / "identity_control.json").write_text(json.dumps({
                "version": "c014-last-hash-pinned-endpoint-v7",
                "policy_revision": "pose-and-fullframe-evidence-recheck-v5",
            }), encoding="utf-8")
            (v5 / "failure.json").write_text(
                json.dumps({"error": "semantic still QA failed"}), encoding="utf-8"
            )
            normalized = w.apply_c014_last_endpoint_recovery(base, 18, root)
            self.assertEqual(normalized["identity_control"]["version"],
                             "c014-last-hash-pinned-endpoint-v8")

    def test_c001_last_switches_to_localized_identity_recovery_after_bounded_evidence(self):
        base = {"clip_id": "C001", "frame": "last", "reference_path": "start.png",
                "prompt": "wave", "denoise": 0.72}
        self.assertIsNone(w.apply_identity_pose_recovery(base, 95).get("identity_control"))
        recovered = w.apply_identity_pose_recovery(base, 96)
        self.assertEqual(recovered["denoise"], 1.0)
        self.assertEqual(recovered["identity_control"]["version"],
                         "c001-localized-wave-openpose-ipadapter-v3")
        self.assertIn("raised open-palm", recovered["prompt"])
        self.assertIn("identity replacement", recovered["negative"])

    def test_identity_recovery_is_c001_last_only(self):
        for job in (
            {"clip_id": "C001", "frame": "start", "reference_path": "x"},
            {"clip_id": "C002", "frame": "last", "reference_path": "x"},
            {"clip_id": "C001", "frame": "last"},
        ):
            self.assertIsNone(w.apply_identity_pose_recovery(job, 999).get("identity_control"))

    def test_c002_start_switches_to_one_bounded_arm_down_identity_recovery(self):
        base = {"clip_id": "C002", "frame": "start", "reference_path": "c001-last.png",
                "prompt": "same actor relaxed", "negative": "camera", "denoise": 0.42}
        self.assertIsNone(w.apply_c002_identity_recovery(base, 4).get("identity_control"))
        recovered = w.apply_c002_identity_recovery(base, 5)
        control = recovered["identity_control"]
        self.assertEqual(control["version"], "c002-localized-arm-down-ipadapter-v1")
        self.assertEqual(control["render_mode"], "inpaint_identity")
        self.assertEqual(control["max_attempts"], 1)
        self.assertFalse(control["use_openpose"])
        self.assertIn("lower the currently raised arm", recovered["prompt"])
        self.assertIn("different actor", recovered["negative"])



    def test_c002_v1_v2_failures_switch_to_union_mask_v3(self):
        """After v1+v2 teal failures, unlock shoulder-inclusive union-mask v3."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            v1 = root / 'v1'; v1.mkdir()
            (v1 / 'identity_control.json').write_text(json.dumps({
                'version': 'c002-localized-arm-down-ipadapter-v1',
                'policy_revision': 'c001-last-anchor-arm-down-v1',
            }), encoding='utf-8')
            (v1 / 'operator_review.json').write_text(json.dumps({
                'decision': 'reject',
            }), encoding='utf-8')
            v2 = root / 'v2'; v2.mkdir()
            (v2 / 'identity_control.json').write_text(json.dumps({
                'version': 'c002-localized-arm-down-openpose-v2',
                'policy_revision': 'openpose-arm-down-grow2-v1',
            }), encoding='utf-8')
            (v2 / 'failure.json').write_text(json.dumps({
                'error': 'semantic still QA failed',
            }), encoding='utf-8')
            base = {'clip_id': 'C002', 'frame': 'start', 'reference_path': 'c001-last.png',
                    'prompt': 'same actor relaxed', 'negative': 'camera', 'denoise': 0.42}
            recovered = w.apply_c002_identity_recovery(base, 30, root)
            control = recovered['identity_control']
            self.assertEqual(control['version'], 'c002-localized-arm-down-union-mask-v3')
            self.assertEqual(control['policy_revision'], 'shoulder-inclusive-union-grow0-v1')
            self.assertEqual(control['grow_mask_by'], 0)
            self.assertTrue(control['use_openpose'])
            self.assertEqual(recovered['denoise'], 0.58)
            self.assertEqual(control['mask_feather_pixels'], 2)
            shoulder = control['pose_points_fraction']['left_shoulder']
            self.assertEqual(shoulder, [0.575, 0.300])
            self.assertIn('sofa cushions', recovered['prompt'])

    def test_c002_v4b_failure_switches_to_v5a_bgnoise_prefill(self):
        """After v4b fail, unlock bgnoise-prefill SD erase v5a."""
        from PIL import Image
        import numpy as np
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = [
                ("v1", "c002-localized-arm-down-ipadapter-v1", "c001-last-anchor-arm-down-v1"),
                ("v2", "c002-localized-arm-down-openpose-v2", "openpose-arm-down-grow2-v1"),
                ("v3", "c002-localized-arm-down-union-mask-v3", "shoulder-inclusive-union-grow0-v1"),
                ("v4a", "c002-raised-hand-erase-v4a", "background-fill-raised-hand-v1"),
                ("v4b", "c002-hanging-arm-openpose-v4b", "hang-corridor-on-erase-plate-v1"),
            ]
            for name, version, policy in specs:
                attempt = root / name
                attempt.mkdir()
                (attempt / "identity_control.json").write_text(json.dumps({
                    "version": version,
                    "policy_revision": policy,
                }), encoding="utf-8")
                (attempt / "failure.json").write_text(json.dumps({
                    "error": "semantic still QA failed",
                }), encoding="utf-8")
            ref = root / "c001-last.png"
            arr = np.zeros((768, 1024, 3), dtype=np.uint8)
            for y in range(768):
                for x in range(1024):
                    arr[y, x] = (40 + (x % 50), 80 + (y % 40), 60)
            Image.fromarray(arr, mode="RGB").save(ref)
            base = {
                "clip_id": "C002", "frame": "start",
                "reference_path": str(ref),
                "prompt": "same actor relaxed", "negative": "camera",
                "denoise": 0.42,
            }
            recovered = w.apply_c002_identity_recovery(base, 40, root)
            control = recovered["identity_control"]
            self.assertEqual(control["version"], "c002-raised-hand-erase-v5a")
            self.assertEqual(control["policy_revision"], "bgnoise-prefill-sd-erase-v1")
            self.assertEqual(control["render_mode"], "inpaint_identity")
            self.assertFalse(control["use_openpose"])
            self.assertEqual(control["grow_mask_by"], 0)
            self.assertEqual(recovered["denoise"], 0.50)
            self.assertIn("prefilled", recovered["prompt"].lower())
            self.assertTrue(Path(recovered["reference_path"]).is_file())
            self.assertNotEqual(recovered["reference_path"], str(ref))

    def test_c002_v5a_failure_switches_to_v5a2_latent_mask(self):
        """After v5a fail, unlock bgnoise-prefill latent-mask erase v5a2."""
        from PIL import Image
        import numpy as np
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = [
                ("v1", "c002-localized-arm-down-ipadapter-v1", "c001-last-anchor-arm-down-v1"),
                ("v2", "c002-localized-arm-down-openpose-v2", "openpose-arm-down-grow2-v1"),
                ("v3", "c002-localized-arm-down-union-mask-v3", "shoulder-inclusive-union-grow0-v1"),
                ("v4a", "c002-raised-hand-erase-v4a", "background-fill-raised-hand-v1"),
                ("v4b", "c002-hanging-arm-openpose-v4b", "hang-corridor-on-erase-plate-v1"),
                ("v5a", "c002-raised-hand-erase-v5a", "bgnoise-prefill-sd-erase-v1"),
            ]
            for name, version, policy in specs:
                attempt = root / name
                attempt.mkdir()
                (attempt / "identity_control.json").write_text(json.dumps({
                    "version": version,
                    "policy_revision": policy,
                }), encoding="utf-8")
                (attempt / "failure.json").write_text(json.dumps({
                    "error": "semantic still QA failed",
                }), encoding="utf-8")
                still = attempt / "still.png"
                Image.new("RGB", (64, 48), "gray").save(still)
            ref = root / "c001-last.png"
            arr = np.zeros((768, 1024, 3), dtype=np.uint8)
            for y in range(768):
                for x in range(1024):
                    arr[y, x] = (40 + (x % 50), 80 + (y % 40), 60)
            Image.fromarray(arr, mode="RGB").save(ref)
            base = {
                "clip_id": "C002", "frame": "start",
                "reference_path": str(ref),
                "prompt": "same actor relaxed", "negative": "camera",
                "denoise": 0.42,
            }
            recovered = w.apply_c002_identity_recovery(base, 50, root)
            control = recovered["identity_control"]
            self.assertEqual(control["version"], "c002-raised-hand-erase-v5a2")
            self.assertEqual(control["policy_revision"], "bgnoise-prefill-latentmask-v1")
            self.assertEqual(control["render_mode"], "inpaint_identity")
            self.assertTrue(control["use_latent_noise_mask"])
            self.assertFalse(control["use_openpose"])
            self.assertEqual(control["grow_mask_by"], 0)
            self.assertEqual(recovered["denoise"], 0.52)
            self.assertTrue(Path(recovered["reference_path"]).is_file())
            self.assertIn("v5a2_bgnoise_prefill.png", recovered["reference_path"].replace("\\", "/"))

    def test_c002_v5a2_failure_switches_to_v5b_hanging_arm(self):
        """After v5a2 fail, unlock hanging-arm OpenPose v5b on v5a2 plate."""
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            specs = [
                ("v1", "c002-localized-arm-down-ipadapter-v1", "c001-last-anchor-arm-down-v1"),
                ("v2", "c002-localized-arm-down-openpose-v2", "openpose-arm-down-grow2-v1"),
                ("v3", "c002-localized-arm-down-union-mask-v3", "shoulder-inclusive-union-grow0-v1"),
                ("v4a", "c002-raised-hand-erase-v4a", "background-fill-raised-hand-v1"),
                ("v4b", "c002-hanging-arm-openpose-v4b", "hang-corridor-on-erase-plate-v1"),
                ("v5a", "c002-raised-hand-erase-v5a", "bgnoise-prefill-sd-erase-v1"),
                ("v5a2", "c002-raised-hand-erase-v5a2", "bgnoise-prefill-latentmask-v1"),
            ]
            v5a2_still = None
            for name, version, policy in specs:
                attempt = root / name
                attempt.mkdir()
                (attempt / "identity_control.json").write_text(json.dumps({
                    "version": version,
                    "policy_revision": policy,
                }), encoding="utf-8")
                (attempt / "failure.json").write_text(json.dumps({
                    "error": "semantic still QA failed",
                }), encoding="utf-8")
                still = attempt / "still.png"
                Image.new("RGB", (64, 48), "blue" if name == "v5a2" else "gray").save(still)
                if name == "v5a2":
                    v5a2_still = still
            base = {
                "clip_id": "C002", "frame": "start",
                "reference_path": "c001-last.png",
                "prompt": "same actor relaxed", "negative": "camera",
                "denoise": 0.42,
            }
            with patch.object(w, "C002_ARM_DONOR_PATH", root / "missing-donor.png"):
                recovered = w.apply_c002_identity_recovery(base, 60, root)
            control = recovered["identity_control"]
            self.assertEqual(control["version"], "c002-hanging-arm-openpose-v5b")
            self.assertEqual(control["policy_revision"], "hang-corridor-on-v5a2-plate-v1")
            self.assertEqual(control["render_mode"], "inpaint_identity_pose")
            self.assertTrue(control["use_openpose"])
            self.assertEqual(control["grow_mask_by"], 0)
            self.assertEqual(recovered["denoise"], 0.55)
            self.assertEqual(Path(recovered["reference_path"]), v5a2_still)
            self.assertIn("v5a2 plate", recovered["prompt"])

    def test_c002_v5a2_failure_prefers_hash_pinned_v6_arm_donor(self):
        from PIL import Image, ImageChops
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            attempts = root / "attempts"
            attempts.mkdir()
            specs = [
                ("v1", "c002-localized-arm-down-ipadapter-v1", "c001-last-anchor-arm-down-v1"),
                ("v2", "c002-localized-arm-down-openpose-v2", "openpose-arm-down-grow2-v1"),
                ("v3", "c002-localized-arm-down-union-mask-v3", "shoulder-inclusive-union-grow0-v1"),
                ("v4a", "c002-raised-hand-erase-v4a", "background-fill-raised-hand-v1"),
                ("v4b", "c002-hanging-arm-openpose-v4b", "hang-corridor-on-erase-plate-v1"),
                ("v5a", "c002-raised-hand-erase-v5a", "bgnoise-prefill-sd-erase-v1"),
                ("v5a2", "c002-raised-hand-erase-v5a2", "bgnoise-prefill-latentmask-v1"),
            ]
            for name, version, policy in specs:
                attempt = attempts / name
                attempt.mkdir()
                (attempt / "identity_control.json").write_text(json.dumps({
                    "version": version, "policy_revision": policy,
                }), encoding="utf-8")
                (attempt / "failure.json").write_text("{}", encoding="utf-8")
            source = root / "source.png"
            donor = root / "donor.png"
            Image.new("RGB", (320, 240), "gray").save(source)
            Image.new("RGB", (320, 240), "olive").save(donor)
            donor_hash = w.sha256(donor)
            base = {
                "clip_id": "C002", "frame": "start",
                "reference_path": str(source), "prompt": "same actor relaxed",
                "negative": "camera", "denoise": 0.42,
            }
            with patch.object(w, "C002_ARM_DONOR_PATH", donor), \
                    patch.object(w, "C002_ARM_DONOR_SHA256", donor_hash):
                recovered = w.apply_c002_identity_recovery(base, 70, attempts)
            control = recovered["identity_control"]
            self.assertEqual(control["version"], "c002-arm-down-donor-composite-v6")
            self.assertEqual(
                control["policy_revision"],
                "imagegen-donor-two-corridor-v2-at-side-qa",
            )
            self.assertEqual(control["render_mode"], "arm_donor_composite")
            self.assertEqual(control["max_attempts"], 1)
            self.assertNotIn("hand_qa_crop_fraction", control)
            self.assertIn("apartment living room", recovered["qa_prompt"])
            self.assertNotIn("raised hand", recovered["qa_prompt"].lower())
            self.assertEqual(recovered["reference_path"], str(source))
            out_dir = root / "composite"
            out_dir.mkdir()
            output = w.stage_arm_donor_composite(source, recovered, out_dir)
            result = Image.open(output).convert("RGB")
            original = Image.open(source).convert("RGB")
            mask = Image.open(out_dir / "arm_donor_mask.png").convert("L")
            outside = ImageChops.difference(result, original)
            # Feathered pixels are intentionally partial edits. Remove every
            # nonzero-mask pixel from the comparison; zero-mask pixels must be
            # byte-identical to the accepted source.
            edited = mask.point(lambda value: 255 if value else 0)
            outside.paste((0, 0, 0), mask=edited)
            self.assertIsNone(outside.getbbox())
            evidence = json.loads((out_dir / "identity_control.json").read_text())
            self.assertLessEqual(evidence["arm_donor_mask_coverage_fraction"], 0.10)

    def test_write_bgnoise_prefill_keeps_outside_mask_exact(self):
        """Outside-mask pixels must remain byte-identical to the source."""
        import cv2
        import numpy as np
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "src.png"
            arr = np.zeros((96, 128, 3), dtype=np.uint8)
            for y in range(96):
                for x in range(128):
                    arr[y, x] = (x % 200, y % 180, (x + y) % 160)
            cv2.imwrite(str(src), arr)
            out = root / "prefill.png"
            poly = [[0.40, 0.20], [0.70, 0.20], [0.70, 0.60], [0.40, 0.60]]
            face = [0.10, 0.10, 0.30, 0.35]
            path = w.write_bgnoise_prefill_plate(
                src, poly, out, protected_face_box_fraction=face, dilate=2, seed=7,
            )
            self.assertEqual(Path(path), out)
            before = cv2.imread(str(src), cv2.IMREAD_COLOR)
            after = cv2.imread(str(out), cv2.IMREAD_COLOR)
            h, ww = before.shape[:2]
            mask = np.zeros((h, ww), dtype=np.uint8)
            pts = np.array(
                [
                    [int(round(0.40 * ww)), int(round(0.20 * h))],
                    [int(round(0.70 * ww)), int(round(0.20 * h))],
                    [int(round(0.70 * ww)), int(round(0.60 * h))],
                    [int(round(0.40 * ww)), int(round(0.60 * h))],
                ],
                np.int32,
            )
            cv2.fillPoly(mask, [pts], 255)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask = cv2.dilate(mask, kernel)
            mask[int(0.10 * h):int(0.35 * h), int(0.10 * ww):int(0.30 * ww)] = 0
            self.assertTrue(np.array_equal(before[mask == 0], after[mask == 0]))
            self.assertGreater(int((mask > 0).sum()), 0)
            self.assertFalse(np.array_equal(before[mask > 0], after[mask > 0]))
            # Corner must be untouched.
            self.assertTrue(np.array_equal(before[0, 0], after[0, 0]))


    def test_c002_v1_reject_switches_to_openpose_v2(self):
        """Operator-rejected v1 must unlock exactly one OpenPose arm-down retry."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            attempt = root / '2c0ad89da8334a75b8e6285ec1a16904'
            attempt.mkdir()
            (attempt / 'identity_control.json').write_text(json.dumps({
                'version': 'c002-localized-arm-down-ipadapter-v1',
                'policy_revision': 'c001-last-anchor-arm-down-v1',
            }), encoding='utf-8')
            (attempt / 'operator_review.json').write_text(json.dumps({
                'decision': 'reject',
                'image_sha256': 'f11ab6ba99b6398f23c743a7a2436d562ddfcfcca90589295a1a880c04245f29',
            }), encoding='utf-8')
            base = {'clip_id': 'C002', 'frame': 'start', 'reference_path': 'c001-last.png',
                    'prompt': 'same actor relaxed', 'negative': 'camera', 'denoise': 0.42}
            recovered = w.apply_c002_identity_recovery(base, 20, root)
            control = recovered['identity_control']
            self.assertEqual(control['version'], 'c002-localized-arm-down-openpose-v2')
            self.assertEqual(control['policy_revision'], 'openpose-arm-down-grow2-v1')
            self.assertEqual(control['render_mode'], 'inpaint_identity_pose')
            self.assertTrue(control['use_openpose'])
            self.assertEqual(control['grow_mask_by'], 2)
            self.assertEqual(control['max_attempts'], 1)
            self.assertEqual(recovered['denoise'], 0.55)
            self.assertIn('left_wrist', control['pose_points_fraction'])
            self.assertIn('teal glow', recovered['negative'])
            self.assertEqual(
                w.policy_failure_count(
                    root,
                    'c002-localized-arm-down-ipadapter-v1',
                    'c001-last-anchor-arm-down-v1',
                ),
                1,
            )

    def test_inpaint_graph_honors_grow_mask_by_override(self):
        graph = image_render.build_graph(
            mode='inpaint_identity', prompt='same actor', negative='camera',
            model='RealVisXL_V5.0_fp16.safetensors', seed=7, width=1024, height=768,
            steps=35, cfg=6.0, sampler='dpmpp_2m_sde', scheduler='karras',
            denoise=0.55, prefix='stories/test/renders/a', reference_name='ref.png',
            mask_name='mask.png', identity_name='face.png', identity_weight=1.0,
            grow_mask_by=2,
        )
        self.assertEqual(graph['4']['inputs']['grow_mask_by'], 2)

    def test_c002_arm_mask_hard_excludes_the_protected_face_after_feathering(self):
        """The arm can border the face, but must never edit it."""
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reference = root / "c001-last.png"
            attempt = root / "attempt"
            inputs = root / "inputs"
            Image.new("RGB", (1024, 768), "gray").save(reference)
            attempt.mkdir()
            job = w.apply_c002_identity_recovery({
                "clip_id": "C002", "frame": "start",
                "reference_path": str(reference), "prompt": "same actor relaxed",
                "negative": "camera", "denoise": 0.42,
            }, 5)
            with patch.object(image_render, "IMAGE_INPUT", inputs):
                w.stage_identity_pose_inputs(reference, job, attempt)
            evidence = json.loads((attempt / "identity_control.json").read_text())
            self.assertEqual(evidence["protected_face_overlap_max"], 0)

    def test_identity_inpaint_graph_preserves_reference_outside_mask(self):
        graph = image_render.build_graph(
            mode="inpaint_identity", prompt="same actor waving", negative="camera",
            model="RealVisXL_V5.0_fp16.safetensors", seed=7, width=1024, height=768,
            steps=35, cfg=6.0, sampler="dpmpp_2m_sde", scheduler="karras",
            denoise=1.0, prefix="stories/test/renders/a", reference_name="ref.png",
            mask_name="mask.png", identity_name="face.png", identity_weight=0.85,
        )
        self.assertEqual(graph["4"]["class_type"], "VAEEncodeForInpaint")
        self.assertEqual(graph["5"]["inputs"]["model"], ["17", 0])
        self.assertEqual(graph["7"]["inputs"]["images"], ["10", 0])
        self.assertEqual(graph["10"]["inputs"]["destination"], ["8", 0])
        self.assertEqual(graph["10"]["inputs"]["mask"], ["9", 1])

    def test_identity_pose_graph_applies_explicit_openpose_control(self):
        graph = image_render.build_graph(
            mode="inpaint_identity_pose", prompt="same actor waving", negative="camera",
            model="RealVisXL_V5.0_fp16.safetensors", seed=7, width=1024, height=768,
            steps=35, cfg=6.0, sampler="dpmpp_2m_sde", scheduler="karras",
            denoise=1.0, prefix="stories/test/renders/a", reference_name="ref.png",
            mask_name="mask.png", identity_name="face.png", identity_weight=0.85,
            pose_name="pose.png", pose_strength=1.0,
        )
        self.assertEqual(graph["19"]["class_type"], "ControlNetLoader")
        self.assertEqual(graph["20"]["inputs"]["type"], "openpose")
        self.assertEqual(graph["21"]["class_type"], "ControlNetApplyAdvanced")
        self.assertEqual(graph["5"]["inputs"]["positive"], ["21", 0])
        self.assertEqual(graph["5"]["inputs"]["negative"], ["21", 1])

    def test_face_refine_graph_samples_detector_crop_and_keeps_source_image(self):
        graph = image_render.build_graph(
            mode="face_refine_identity", prompt="same actor, gentle smile",
            negative="different person, object over mouth",
            model="RealVisXL_V5.0_fp16.safetensors", seed=7, width=1024,
            height=768, steps=24, cfg=5.5, sampler="dpmpp_2m_sde",
            scheduler="karras", denoise=0.32,
            prefix="stories/test/renders/face", reference_name="wave.png",
            identity_name="original-face.png", identity_weight=0.90,
        )
        self.assertEqual(graph["12"]["class_type"], "FaceDetailer")
        self.assertEqual(graph["12"]["inputs"]["image"], ["8", 0])
        self.assertEqual(graph["12"]["inputs"]["model"], ["17", 0])
        self.assertEqual(graph["12"]["inputs"]["denoise"], 0.32)
        self.assertEqual(graph["7"]["inputs"]["images"], ["12", 0])
        self.assertNotIn("VAEEncodeForInpaint", {
            node["class_type"] for node in graph.values()
        })

    def test_liveportrait_graph_retargets_source_without_diffusion_nodes(self):
        graph = image_render.build_graph(
            mode="liveportrait_expression", prompt="smile", negative="",
            model="RealVisXL_V5.0_fp16.safetensors", seed=7, width=1024,
            height=768, steps=1, cfg=1.0, sampler="euler",
            scheduler="normal", denoise=0.0,
            prefix="stories/test/renders/liveportrait",
            reference_name="wave.png", smile_strength=1.15,
            mouth_open=8.0, liveportrait_crop_factor=2.2,
        )
        self.assertEqual(graph["1"]["class_type"], "LoadImage")
        self.assertEqual(graph["2"]["class_type"], "ExpressionEditor")
        self.assertEqual(graph["2"]["inputs"]["src_image"], ["1", 0])
        self.assertEqual(graph["2"]["inputs"]["smile"], 1.15)
        self.assertEqual(graph["2"]["inputs"]["aaa"], 8.0)
        self.assertEqual(graph["3"]["inputs"]["images"], ["2", 0])
        node_types = {node["class_type"] for node in graph.values()}
        self.assertNotIn("CheckpointLoaderSimple", node_types)
        self.assertNotIn("KSampler", node_types)

    def test_hand_crop_graph_samples_enlarged_crop_then_stitches_source(self):
        graph = image_render.build_graph(
            mode="hand_crop_inpaint", prompt="anatomically correct waving hand",
            negative="extra fingers, fused fingers",
            model="RealVisXL_V5.0_fp16.safetensors", seed=9, width=1024,
            height=768, steps=35, cfg=6.0, sampler="dpmpp_2m_sde",
            scheduler="karras", denoise=0.52,
            prefix="stories/test/renders/hand", reference_name="smile.png",
            mask_name="hand-mask.png",
        )
        self.assertEqual(graph["10"]["class_type"], "InpaintCropImproved")
        self.assertEqual(graph["10"]["inputs"]["output_target_width"], 768)
        self.assertEqual(graph["4"]["class_type"], "VAEEncode")
        self.assertEqual(graph["4"]["inputs"]["pixels"], ["10", 1])
        self.assertEqual(graph["12"]["class_type"], "SetLatentNoiseMask")
        self.assertEqual(graph["12"]["inputs"]["mask"], ["10", 2])
        self.assertEqual(graph["5"]["inputs"]["latent_image"], ["12", 0])
        self.assertEqual(graph["11"]["class_type"], "InpaintStitchImproved")
        self.assertEqual(graph["7"]["inputs"]["images"], ["11", 0])

    def test_hand_detailer_uses_hand_detector_not_face_detector(self):
        graph = image_render.build_graph(
            mode="hand_detailer", prompt="correct open waving hand",
            negative="face, extra fingers",
            model="RealVisXL_V5.0_fp16.safetensors", seed=10, width=1024,
            height=768, steps=35, cfg=6.0, sampler="dpmpp_2m_sde",
            scheduler="karras", denoise=0.48,
            prefix="stories/test/renders/hand-detail", reference_name="smile.png",
        )
        self.assertEqual(graph["11"]["inputs"]["model_name"],
                         "bbox/hand_yolov8s.pt")
        self.assertEqual(graph["13"]["inputs"]["bbox_detector"], ["11", 0])
        self.assertEqual(graph["14"]["inputs"]["segs"], ["13", 0])
        self.assertEqual(graph["14"]["inputs"]["target"], "y1")
        self.assertFalse(graph["14"]["inputs"]["order"])
        self.assertEqual(graph["14"]["inputs"]["take_count"], 1)
        self.assertEqual(graph["12"]["inputs"]["segs"], ["14", 0])
        self.assertEqual(graph["12"]["inputs"]["image"], ["8", 0])
        self.assertEqual(graph["7"]["inputs"]["images"], ["12", 0])

    def test_hand_refiner_uses_depth_control_inside_bounded_crop(self):
        graph = image_render.build_graph(
            mode="hand_refiner_sd15", prompt="five digit hand",
            negative="claw, missing digits",
            model="realisticVisionV60B1_v51HyperVAE.safetensors",
            seed=11, width=1024, height=768, steps=30, cfg=7.0,
            sampler="dpmpp_2m_sde", scheduler="karras", denoise=0.72,
            prefix="stories/test/renders/mesh-hand", reference_name="smile.png",
            mask_name="raised-hand-mask.png", profile="realisticvision_sd15",
        )
        self.assertEqual(graph["15"]["class_type"],
                         "MeshGraphormer-DepthMapPreprocessor")
        self.assertEqual(graph["15"]["inputs"]["image"], ["10", 1])
        self.assertEqual(graph["10"]["inputs"]["preresize_mode"],
                         "ensure minimum resolution")
        self.assertEqual(graph["16"]["inputs"]["mask"], ["15", 1])
        self.assertEqual(graph["17"]["inputs"]["control_net_name"],
                         image_render.HAND_REFINER_CONTROLNET)
        self.assertEqual(graph["18"]["inputs"]["image"], ["15", 0])
        self.assertEqual(graph["5"]["inputs"]["positive"], ["18", 0])
        self.assertEqual(graph["11"]["inputs"]["stitcher"], ["10", 0])

    def test_hand_openpose_uses_explicit_pose_on_same_bounded_crop(self):
        graph = image_render.build_graph(
            mode="hand_openpose_sdxl", prompt="open palm wave",
            negative="claw, missing digits",
            model="RealVisXL_V5.0_fp16.safetensors", seed=12,
            width=1024, height=768, steps=35, cfg=6.0,
            sampler="dpmpp_2m_sde", scheduler="karras", denoise=0.72,
            prefix="stories/test/renders/openpose-hand",
            reference_name="smile.png", mask_name="raised-hand-mask.png",
            pose_name="target-hand-pose.png", pose_strength=1.0,
            pose_end_percent=0.65,
        )
        self.assertEqual(graph["10"]["inputs"]["mask"], ["9", 1])
        self.assertEqual(graph["20"]["inputs"]["mask"], ["9", 1])
        self.assertEqual(graph["20"]["inputs"]["image"], ["19", 0])
        self.assertEqual(graph["17"]["inputs"]["control_net_name"],
                         image_render.CONTROLNET_UNION_SDXL)
        self.assertEqual(graph["21"]["inputs"]["type"], "openpose")
        self.assertEqual(graph["18"]["inputs"]["image"], ["20", 1])
        self.assertEqual(graph["18"]["inputs"]["strength"], 1.0)
        self.assertEqual(graph["18"]["inputs"]["end_percent"], 0.65)
        self.assertEqual(graph["5"]["inputs"]["latent_image"], ["12", 0])
        self.assertEqual(graph["11"]["inputs"]["stitcher"], ["10", 0])

    def test_output_wait_ignores_custom_node_temporary_preview(self):
        history = {
            "pid": {
                "status": {"status_str": "success"},
                "outputs": {
                    "2": {"images": [{
                        "filename": "fe_edit_preview.png", "type": "temp",
                    }]},
                    "3": {"images": [{
                        "filename": "attempt_00001_.png", "type": "output",
                    }]},
                },
            }
        }
        with patch.object(image_render, "_get_json", return_value=history), \
                patch.object(image_render.thermal_guard,
                             "check_running_ceiling", return_value=None):
            images = image_render._wait_for_outputs(
                "pid", timeout_s=1, output_node_ids={"3"}
            )
        self.assertEqual(images, [{
            "filename": "attempt_00001_.png", "type": "output",
        }])

    def test_identity_control_artifacts_are_immutable_and_hash_recorded(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reference = root / "reference.png"
            attempt = root / "attempt"
            inputs = root / "inputs"
            attempt.mkdir()
            Image.new("RGB", (400, 300), "gray").save(reference)
            job = w.apply_identity_pose_recovery(
                {"clip_id": "C001", "frame": "last",
                 "reference_path": str(reference)}, 96)
            with patch.object(image_render, "IMAGE_INPUT", inputs):
                face_name, mask_name, pose_name = w.stage_identity_pose_inputs(
                    reference, job, attempt
                )
            self.assertTrue((inputs / face_name).is_file())
            self.assertTrue((inputs / mask_name).is_file())
            self.assertTrue((inputs / pose_name).is_file())
            evidence = json.loads((attempt / "identity_control.json").read_text())
            self.assertEqual(evidence["reference_sha256"], w.sha256(reference))
            self.assertEqual(evidence["identity_reference_sha256"],
                             w.sha256(attempt / "identity_reference.png"))
            self.assertLessEqual(evidence["protected_face_overlap_max"], 64)
            alpha = Image.open(attempt / "inpaint_mask.png").getchannel("A")
            # The ComfyUI mask is 1-alpha. Corners therefore stay fully
            # opaque/unmasked while the two local edit islands are transparent.
            self.assertEqual(alpha.getpixel((0, 0)), 255)
            self.assertLess(alpha.getpixel((260, 75)), 255)
            self.assertEqual(
                evidence["target_openpose_sha256"],
                w.sha256(attempt / "target_openpose.png"),
            )

    def test_smile_refinement_selects_only_qa_proven_wave_and_uses_original_anchor(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original.png"
            Image.new("RGB", (400, 300), "gray").save(original)
            candidate_dir = root / "candidate"
            candidate_dir.mkdir()
            Image.new("RGB", (400, 300), "gray").save(candidate_dir / "still.png")
            (candidate_dir / "qa.json").write_text(json.dumps({
                "semantic_review": {
                    "reasons": ["blind evidence does not show the required smile or grin"],
                    "continuity_evidence": {
                        "same_person": True, "same_hair": True,
                        "same_facial_hair": True, "same_clothing": True,
                        "same_room_geometry": True,
                    },
                    "verdict": {"checks": {
                        "requested_subjects_present": True,
                        "requested_pose_or_action_visible": True,
                        "requested_composition_visible": True,
                        "setting_matches": True, "identity_continuity": True,
                        "no_forbidden_equipment": True,
                        "blind_observation_consistent": True,
                    }},
                }
            }))
            (candidate_dir / "identity_control.json").write_text(json.dumps({
                "version": "c001-localized-wave-openpose-ipadapter-v3"
            }))
            job = w.apply_identity_pose_recovery({
                "clip_id": "C001", "frame": "last", "reference_path": str(original),
                "prompt": "wave and smile", "negative": "camera",
            }, 110)
            refined = w.apply_smile_refinement(job, root, 110)
            self.assertEqual(refined["reference_path"], str(candidate_dir / "still.png"))
            self.assertEqual(refined["qa_reference_path"], str(original))
            self.assertEqual(refined["identity_control"]["version"],
                             "c001-smile-refine-ipadapter-v4")
            self.assertEqual(refined["identity_control"]["policy_revision"],
                             "lower-face-clamped-v2")
            self.assertEqual(refined["identity_control"]["max_attempts"], 1)
            attempt = root / "refine"
            inputs = root / "inputs"
            attempt.mkdir()
            with patch.object(image_render, "IMAGE_INPUT", inputs):
                _, _, pose_name = w.stage_identity_pose_inputs(
                    candidate_dir / "still.png", refined, attempt
                )
            self.assertIsNone(pose_name)
            evidence = json.loads((attempt / "identity_control.json").read_text())
            self.assertIsNone(evidence["target_openpose"])
            self.assertEqual(evidence["identity_anchor_sha256"], w.sha256(original))
            self.assertLessEqual(evidence["protected_face_overlap_max"], 64)
            alpha = Image.open(attempt / "inpaint_mask.png").getchannel("A")
            clamp_y = evidence["smile_upper_clamp_y"]
            self.assertEqual(alpha.getpixel((210, clamp_y - 1)), 255)
            self.assertLess(alpha.getpixel((210, clamp_y + 8)), 255)

    def test_identity_policy_failure_counter_is_bounded_by_exact_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(5):
                attempt = root / str(index)
                attempt.mkdir()
                (attempt / "failure.json").write_text("{}")
                version = "v4" if index < 4 else "other"
                (attempt / "identity_control.json").write_text(
                    json.dumps({"version": version})
                )
            self.assertEqual(w.policy_failure_count(root, "v4"), 4)
            self.assertEqual(w.policy_failure_count(root, "other"), 1)
            self.assertEqual(w.policy_failure_count(root, "v4", "new-mask"), 0)

    def test_failed_v4_promotes_one_bounded_face_crop_refinement(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original.png"
            Image.new("RGB", (400, 300), "gray").save(original)
            candidate = root / "candidate"
            candidate.mkdir()
            Image.new("RGB", (400, 300), "gray").save(candidate / "still.png")
            (candidate / "qa.json").write_text(json.dumps({
                "semantic_review": {
                    "reasons": ["required smile is not visible"],
                    "continuity_evidence": {
                        "same_person": True, "same_hair": True,
                        "same_facial_hair": True, "same_clothing": True,
                        "same_room_geometry": True,
                    },
                    "verdict": {"checks": {
                        "requested_subjects_present": True,
                        "requested_pose_or_action_visible": True,
                        "requested_composition_visible": True,
                        "setting_matches": True, "identity_continuity": True,
                        "no_forbidden_equipment": True,
                        "blind_observation_consistent": True,
                    }},
                }
            }))
            (candidate / "identity_control.json").write_text(json.dumps({
                "version": "c001-localized-wave-openpose-ipadapter-v3"
            }))
            failed = root / "failed-v4"
            failed.mkdir()
            (failed / "failure.json").write_text("{}")
            (failed / "identity_control.json").write_text(json.dumps({
                "version": "c001-smile-refine-ipadapter-v4",
                "policy_revision": "lower-face-clamped-v2",
            }))
            refined = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 111)
            control = refined["identity_control"]
            self.assertEqual(control["version"],
                             "c001-smile-facedetailer-ipadapter-v5")
            self.assertEqual(control["render_mode"], "face_refine_identity")
            self.assertEqual(control["max_attempts"], 1)
            self.assertEqual(refined["denoise"], 0.32)
            attempt = root / "face-refine"
            inputs = root / "inputs"
            attempt.mkdir()
            with patch.object(image_render, "IMAGE_INPUT", inputs):
                staged = w.stage_identity_face_input(
                    candidate / "still.png", refined, attempt
                )
            self.assertTrue((inputs / staged).is_file())
            evidence = json.loads((attempt / "identity_control.json").read_text())
            self.assertEqual(evidence["identity_anchor_sha256"], w.sha256(original))
            self.assertEqual(evidence["mask_mode"],
                             "impact-pack-face-detector-crop")
            self.assertFalse((attempt / "inpaint_mask.png").exists())

    def test_exhausted_diffusion_smile_trials_promote_one_liveportrait_attempt(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original.png"
            Image.new("RGB", (400, 300), "gray").save(original)
            wave = root / "wave"
            wave.mkdir()
            Image.new("RGB", (400, 300), "gray").save(wave / "still.png")
            (wave / "identity_control.json").write_text(json.dumps({
                "version": "c001-localized-wave-openpose-ipadapter-v3",
            }), encoding="utf-8")
            (wave / "qa.json").write_text(json.dumps({
                "semantic_review": {
                    "reasons": ["blind evidence does not show the required smile"],
                    "continuity_evidence": {
                        "same_person": True, "same_hair": True,
                        "same_facial_hair": True, "same_clothing": True,
                        "same_room_geometry": True,
                    },
                    "verdict": {"checks": {
                        "requested_subjects_present": True,
                        "requested_pose_or_action_visible": True,
                        "requested_composition_visible": True,
                        "setting_matches": True, "identity_continuity": True,
                        "no_forbidden_equipment": True,
                        "blind_observation_consistent": True,
                    }},
                }
            }), encoding="utf-8")
            failures = (
                ("c001-smile-refine-ipadapter-v4", "lower-face-clamped-v2"),
                ("c001-smile-facedetailer-ipadapter-v5", "face-crop-tooth-bearing-smile-push-v7"),
                ("c001-smile-lowerface-inpaint-v8", "larger-mouth-inpaint-identity-v1"),
                ("c001-smile-tiny-lip-inpaint-v9", "tiny-lip-inpaint-low-denoise-v1"),
                ("c001-smile-medium-mouth-inpaint-v10", "medium-mouth-ultra-low-denoise-v1"),
                ("c001-smile-facedetailer-midip-v11", "face-crop-tooth-bearing-mid-ip-v1"),
                ("c001-smile-facedetailer-stageb-v12", "face-crop-stage-b-visible-smile-v1"),
            )
            for index, (version, revision) in enumerate(failures):
                attempt = root / f"failed-{index}"
                attempt.mkdir()
                (attempt / "identity_control.json").write_text(json.dumps({
                    "version": version, "policy_revision": revision,
                }), encoding="utf-8")
                (attempt / "failure.json").write_text("{}", encoding="utf-8")
            refined = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 130)
            control = refined["identity_control"]
            self.assertEqual(control["version"], "c001-smile-liveportrait-v13")
            self.assertEqual(control["policy_revision"],
                             "non-diffusion-expression-retarget-v1")
            self.assertEqual(control["render_mode"], "liveportrait_expression")
            self.assertEqual(control["max_attempts"], 1)
            self.assertEqual(refined["reference_path"], str(wave / "still.png"))
            attempt = root / "liveportrait-evidence"
            attempt.mkdir()
            w.stage_liveportrait_smile_input(wave / "still.png", refined, attempt)
            evidence = json.loads((attempt / "identity_control.json").read_text())
            self.assertFalse(evidence["diffusion_checkpoint_used"])
            self.assertEqual(evidence["reference_sha256"], w.sha256(wave / "still.png"))
            self.assertEqual(evidence["identity_anchor_sha256"], w.sha256(original))
            failed_v13 = root / "failed-liveportrait-v13"
            failed_v13.mkdir()
            (failed_v13 / "identity_control.json").write_text(json.dumps({
                "version": "c001-smile-liveportrait-v13",
                "policy_revision": "non-diffusion-expression-retarget-v1",
            }), encoding="utf-8")
            (failed_v13 / "failure.json").write_text("{}", encoding="utf-8")
            retried = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 131)
            self.assertEqual(retried["identity_control"]["version"],
                             "c001-smile-liveportrait-v14")
            self.assertEqual(retried["identity_control"]["policy_revision"],
                             "saveimage-only-evidence-filter-v2")
            failed_v14 = root / "failed-liveportrait-v14"
            failed_v14.mkdir()
            (failed_v14 / "identity_control.json").write_text(json.dumps({
                "version": "c001-smile-liveportrait-v14",
                "policy_revision": "saveimage-only-evidence-filter-v2",
            }), encoding="utf-8")
            (failed_v14 / "failure.json").write_text("{}", encoding="utf-8")
            crop_checked = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 132)
            crop_control = crop_checked["identity_control"]
            self.assertEqual(crop_control["version"],
                             "c001-smile-liveportrait-v15")
            self.assertEqual(crop_control["policy_revision"],
                             "blind-face-crop-expression-gate-v3")
            self.assertEqual(crop_control["expression_qa_crop_fraction"],
                             [0.42, 0.05, 0.63, 0.40])
            failed_v15 = root / "failed-liveportrait-v15"
            failed_v15.mkdir()
            (failed_v15 / "identity_control.json").write_text(json.dumps({
                "version": "c001-smile-liveportrait-v15",
                "policy_revision": "blind-face-crop-expression-gate-v3",
            }), encoding="utf-8")
            (failed_v15 / "failure.json").write_text("{}", encoding="utf-8")
            strengthened = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 133)
            strong_control = strengthened["identity_control"]
            self.assertEqual(strong_control["version"],
                             "c001-smile-liveportrait-v16")
            self.assertEqual(strong_control["policy_revision"],
                             "maximum-smile-expression-retarget-v4")
            self.assertEqual(strong_control["smile_strength"], 1.30)
            self.assertEqual(strong_control["mouth_open"], 16.0)
            failed_v16 = root / "failed-liveportrait-v16"
            failed_v16.mkdir()
            (failed_v16 / "identity_control.json").write_text(json.dumps({
                "version": "c001-smile-liveportrait-v16",
                "policy_revision": "maximum-smile-expression-retarget-v4",
            }), encoding="utf-8")
            (failed_v16 / "failure.json").write_text("{}", encoding="utf-8")
            compared = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 134)
            self.assertEqual(compared["identity_control"]["version"],
                             "c001-smile-liveportrait-v17")
            self.assertEqual(compared["identity_control"]["policy_revision"],
                             "blind-contrastive-expression-gate-v5")
            rejected_v17 = root / "operator-rejected-liveportrait-v17"
            rejected_v17.mkdir()
            Image.new("RGB", (400, 300), "gray").save(rejected_v17 / "still.png")
            (rejected_v17 / "identity_control.json").write_text(json.dumps({
                "version": "c001-smile-liveportrait-v17",
                "policy_revision": "blind-contrastive-expression-gate-v5",
            }), encoding="utf-8")
            (rejected_v17 / "operator_review.json").write_text(json.dumps({
                "decision": "reject",
                "image_sha256": w.sha256(rejected_v17 / "still.png"),
                "reason_codes": ["malformed_hand_anatomy"],
            }), encoding="utf-8")
            hand_fixed = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 135)
            hand_control = hand_fixed["identity_control"]
            self.assertEqual(hand_control["version"], "c001-hand-crop-inpaint-v18")
            self.assertEqual(hand_control["render_mode"], "hand_crop_inpaint")
            self.assertEqual(hand_fixed["reference_path"],
                             str(rejected_v17 / "still.png"))
            self.assertIn("exactly five", hand_fixed["prompt"])
            attempt = root / "hand-evidence"
            inputs = root / "hand-inputs"
            attempt.mkdir()
            with patch.object(image_render, "IMAGE_INPUT", inputs):
                mask_name = w.stage_hand_refine_input(
                    rejected_v17 / "still.png", hand_fixed, attempt
                )
            self.assertTrue((inputs / mask_name).is_file())
            evidence = json.loads((attempt / "identity_control.json").read_text())
            self.assertLess(evidence["hand_mask_area_fraction"], 0.015)
            self.assertEqual(evidence["mask_mode"], "crop-and-stitch-hand-only")
            for version, revision in (
                ("c001-hand-crop-inpaint-v18", "operator-rejected-hand-anatomy-v1"),
                ("c001-hand-crop-inpaint-v19", "masked-latent-hand-repair-v2"),
            ):
                failed = root / ("failed-" + version)
                failed.mkdir()
                (failed / "identity_control.json").write_text(json.dumps({
                    "version": version, "policy_revision": revision,
                }), encoding="utf-8")
                (failed / "failure.json").write_text("{}", encoding="utf-8")
            detected = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 136)
            self.assertEqual(detected["identity_control"]["version"],
                             "c001-hand-yolo-detailer-v20")
            self.assertEqual(detected["identity_control"]["render_mode"],
                             "hand_detailer")
            self.assertIn("face", detected["negative"])
            failed_v20 = root / "failed-c001-hand-yolo-detailer-v20"
            failed_v20.mkdir()
            (failed_v20 / "identity_control.json").write_text(json.dumps({
                "version": "c001-hand-yolo-detailer-v20",
                "policy_revision": "detected-hand-silhouette-v3",
            }), encoding="utf-8")
            (failed_v20 / "failure.json").write_text("{}", encoding="utf-8")
            reconstructed = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 137)
            self.assertEqual(reconstructed["identity_control"]["version"],
                             "c001-hand-yolo-detailer-v21")
            self.assertEqual(reconstructed["denoise"], 0.72)
            self.assertIn("all five digits", reconstructed["prompt"])
            failed_v21 = root / "failed-c001-hand-yolo-detailer-v21"
            failed_v21.mkdir()
            (failed_v21 / "identity_control.json").write_text(json.dumps({
                "version": "c001-hand-yolo-detailer-v21",
                "policy_revision": "five-visible-digits-v1",
            }), encoding="utf-8")
            (failed_v21 / "failure.json").write_text("{}", encoding="utf-8")
            topmost_only = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 138)
            self.assertEqual(topmost_only["identity_control"]["version"],
                             "c001-hand-yolo-detailer-v22")
            self.assertEqual(topmost_only["denoise"], 0.80)
            self.assertIn("topmost", topmost_only["identity_control"]["reason"])
            failed_v22 = root / "failed-c001-hand-yolo-detailer-v22"
            failed_v22.mkdir()
            (failed_v22 / "identity_control.json").write_text(json.dumps({
                "version": "c001-hand-yolo-detailer-v22",
                "policy_revision": "topmost-hand-only-v1",
            }), encoding="utf-8")
            (failed_v22 / "failure.json").write_text("{}", encoding="utf-8")
            depth_controlled = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 139)
            self.assertEqual(depth_controlled["identity_control"]["version"],
                             "c001-hand-meshgraphormer-v23")
            self.assertEqual(depth_controlled["identity_control"]["render_mode"],
                             "hand_refiner_sd15")
            self.assertEqual(depth_controlled["model_profile"],
                             "realisticvision_sd15")
            failed_v23 = root / "failed-c001-hand-meshgraphormer-v23"
            failed_v23.mkdir()
            (failed_v23 / "identity_control.json").write_text(json.dumps({
                "version": "c001-hand-meshgraphormer-v23",
                "policy_revision": "depth-controlled-raised-hand-v3",
            }), encoding="utf-8")
            (failed_v23 / "failure.json").write_text("{}", encoding="utf-8")
            pose_controlled = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 140)
            pose_control = pose_controlled["identity_control"]
            self.assertEqual(pose_control["version"],
                             "c001-hand-openpose-sdxl-v24")
            self.assertEqual(pose_control["render_mode"],
                             "hand_openpose_sdxl")
            self.assertEqual(len(pose_control["hand_pose_points_fraction"]), 21)
            self.assertEqual(pose_controlled["model_profile"], "realvisxl")
            attempt = root / "openpose-hand-evidence"
            inputs = root / "openpose-hand-inputs"
            attempt.mkdir()
            with patch.object(image_render, "IMAGE_INPUT", inputs):
                mask_name, pose_name = w.stage_hand_refine_input(
                    rejected_v17 / "still.png", pose_controlled, attempt
                )
            self.assertTrue((inputs / mask_name).is_file())
            self.assertTrue((inputs / pose_name).is_file())
            evidence = json.loads((attempt / "identity_control.json").read_text())
            self.assertEqual(evidence["target_hand_pose_edge_count"], 20)
            self.assertEqual(len(evidence["target_hand_pose_points_pixels"]), 21)
            self.assertTrue(Path(evidence["target_hand_openpose"]).is_file())
            failed_v24 = root / "failed-c001-hand-openpose-sdxl-v24"
            failed_v24.mkdir()
            (failed_v24 / "identity_control.json").write_text(json.dumps({
                "version": "c001-hand-openpose-sdxl-v24",
                "policy_revision": "explicit-21-joint-open-palm-v1",
            }), encoding="utf-8")
            (failed_v24 / "failure.json").write_text("{}", encoding="utf-8")
            weakened = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 141)
            weak_control = weakened["identity_control"]
            self.assertEqual(weak_control["version"],
                             "c001-hand-openpose-sdxl-v25")
            self.assertEqual(weak_control["pose_strength"], 0.35)
            self.assertEqual(weak_control["pose_end_percent"], 0.65)
            failed_v25 = root / "failed-c001-hand-openpose-sdxl-v25"
            failed_v25.mkdir()
            (failed_v25 / "identity_control.json").write_text(json.dumps({
                "version": "c001-hand-openpose-sdxl-v25",
                "policy_revision": "low-strength-shape-guidance-v1",
            }), encoding="utf-8")
            (failed_v25 / "failure.json").write_text("{}", encoding="utf-8")
            thumb_separated = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 142)
            thumb_control = thumb_separated["identity_control"]
            self.assertEqual(thumb_control["version"],
                             "c001-hand-openpose-sdxl-v26")
            self.assertEqual(thumb_control["pose_strength"], 0.48)
            self.assertEqual(thumb_control["pose_end_percent"], 0.72)
            self.assertGreater(
                thumb_control["hand_pose_points_fraction"][1][0],
                thumb_control["hand_pose_points_fraction"][4][0],
            )
            failed_v26 = root / "failed-c001-hand-openpose-sdxl-v26"
            failed_v26.mkdir()
            (failed_v26 / "identity_control.json").write_text(json.dumps({
                "version": "c001-hand-openpose-sdxl-v26",
                "policy_revision": "lateral-thumb-five-digit-v1",
            }), encoding="utf-8")
            (failed_v26 / "failure.json").write_text("{}", encoding="utf-8")
            donor_composite = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last", "story": "c001-last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 143)
            donor_control = donor_composite["identity_control"]
            self.assertEqual(donor_control["version"],
                             "c001-hand-donor-composite-v27")
            self.assertEqual(donor_control["render_mode"],
                             "hand_donor_composite")
            self.assertTrue(Path(donor_control["hand_donor_path"]).is_file())
            attempt = root / "donor-composite-evidence"
            attempt.mkdir()
            output, receipt = w.render_still(
                w.ROOT, donor_composite, attempt
            )
            self.assertTrue(output.is_file())
            self.assertTrue(receipt.is_file())
            receipt_data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertFalse(receipt_data["gpu_used"])
            evidence = json.loads((attempt / "identity_control.json").read_text())
            self.assertEqual(evidence["mask_mode"],
                             "bounded-pixel-donor-composite")
            self.assertLess(evidence["hand_donor_bbox_area_fraction"], 0.022)
            failed_v27 = root / "failed-c001-hand-donor-composite-v27"
            failed_v27.mkdir()
            (failed_v27 / "identity_control.json").write_text(json.dumps({
                "version": "c001-hand-donor-composite-v27",
                "policy_revision": "bounded-five-digit-donor-v1",
            }), encoding="utf-8")
            (failed_v27 / "failure.json").write_text("{}", encoding="utf-8")
            schema_recheck = w.apply_smile_refinement({
                "clip_id": "C001", "frame": "last", "story": "c001-last",
                "reference_path": str(original), "prompt": "wave and smile",
            }, root, 144)
            schema_control = schema_recheck["identity_control"]
            self.assertEqual(schema_control["version"],
                             "c001-hand-donor-composite-v28")
            self.assertEqual(schema_control["policy_revision"],
                             "five-digit-schema-v12-recheck-v1")

    def test_v5_delivery_target_is_4_by_3_and_keeps_required_visible_facts(self):
        recovered = w.apply_composition_recovery(
            {"clip_id": "C001", "frame": "start", "prompt": "canonical", "negative": "base"}, 14)
        target = w.delivery_qa_prompt(recovered).lower()
        self.assertIn("4:3", target)
        self.assertNotIn("square", target)
        for required in ("head-to-toe", "white sneakers", "living room", "olive-green", "no visible recording camera"):
            self.assertIn(required, target)

    def test_v5c_qa_prompt_disambiguates_layered_clothing_and_drops_unassessable_details(self):
        # v5c: accept white/gray/off-white T-shirts, remove wristwatch (too small
        # to reliably detect in a still), and accept ceiling light fixtures.
        recovered = w.apply_composition_recovery(
            {"clip_id": "C001", "frame": "start", "prompt": "canonical", "negative": "base"}, 14)
        qa = w.delivery_qa_prompt(recovered).lower()
        self.assertIn("olive-green", qa)
        self.assertIn("outer layer", qa)
        self.assertIn("underneath", qa)
        self.assertIn("white, gray, or off-white", qa)
        self.assertIn("ceiling light", qa)
        # Removed: straight-leg, worn, cheap digital, wristwatch.
        self.assertNotIn("straight-leg", qa)
        self.assertNotIn("worn white", qa)
        self.assertNotIn("cheap dark digital", qa)
        self.assertNotIn("wristwatch", qa)

    def test_jeans_check_accepts_vlm_pants_terminology(self):
        # The exact VLM labels denim trousers as "pants" in its structured output.
        # enforce_blind_evidence must accept "pant" (covers "pants") alongside "jean".
        verdict = {"status": "pass", "reasons": []}
        blind = json.dumps({
            "setting": "living room", "visible_furniture": ["sofa"],
            "clothing": [{"type": "button-up shirt", "color": "olive green"},
                         {"type": "t-shirt", "color": "white"},
                         {"type": "pants", "color": "dark blue"},
                         {"type": "shoes", "color": "white"}],
            "both_feet_visible": True, "camera_or_tripod_visible": False,
        })
        prompt = ("living room with a visible sofa or couch; "
                  "olive-green overshirt over a lighter T-shirt; dark jeans; white sneakers")
        result = w.enforce_blind_evidence(verdict, blind, prompt)
        self.assertEqual(result["status"], "pass", result.get("reasons"))

    def test_hand_only_pov_does_not_require_hidden_jeans_or_shoes(self):
        verdict = {"status": "pass", "reasons": []}
        blind = json.dumps({
            "setting": "office corridor",
            "clothing": [{"item": "sleeve", "color": "olive green"}],
            "both_feet_visible": False,
            "camera_or_tripod_visible": False,
        })
        prompt = (
            "Exactly one adult hand with a small olive-green overshirt cuff enters "
            "only from the extreme lower edge. The actor is otherwise entirely "
            "outside the frame: do not depict the actor's face or torso."
        )
        result = w.enforce_blind_evidence(verdict, blind, prompt)
        self.assertEqual(result["status"], "pass", result.get("reasons"))

    def test_prompt_free_face_crop_can_resolve_small_fullframe_smile(self):
        verdict = {"status": "pass", "reasons": []}
        full_frame = json.dumps({"facial_expression": "neutral"})
        face_crop = json.dumps({
            "facial_expression": "smiling",
            "mouth_corners": "upturned",
            "teeth_visible": True,
            "confidence": "high",
        })
        result = w.enforce_blind_evidence(
            verdict, full_frame, "actor has a clear smile", face_crop
        )
        self.assertEqual(result["status"], "pass", result.get("reasons"))
        self.assertEqual(
            result["expression_blind_evidence"]["mouth_corners"], "upturned"
        )

    def test_prompt_free_contrastive_expression_can_resolve_absolute_label(self):
        verdict = {"status": "pass", "reasons": []}
        result = w.enforce_blind_evidence(
            verdict,
            json.dumps({"facial_expression": "neutral"}),
            "actor has a clear smile",
            json.dumps({"facial_expression": "serious"}),
            json.dumps({
                "same_identity": True,
                "reference_expression": "serious",
                "candidate_expression": "smiling",
                "candidate_more_smiling": True,
                "candidate_smile_cues": [
                    "visible teeth", "upturned mouth corners",
                ],
            }),
        )
        self.assertEqual(result["status"], "pass", result.get("reasons"))

    def test_raised_hand_requires_prompt_free_anatomy_pass_when_crop_is_present(self):
        verdict = {"status": "pass", "reasons": []}
        blind = json.dumps({
            "right_hand_position": "raised in a wave",
            "visible_actions": ["waving"],
        })
        malformed = json.dumps({
            "hand_visible": True, "finger_count_visible": 3,
            "extra_digits": False, "missing_digits": True,
            "fused_digits": True, "wrist_plausible": True,
            "anatomically_plausible": False, "confidence": "high",
        })
        result = w.enforce_blind_evidence(
            verdict, blind, "one hand raised in a casual wave",
            hand_blind_analysis=malformed,
        )
        self.assertEqual(result["status"], "fail")
        self.assertTrue(any("hand" in reason for reason in result["reasons"]))

    def test_hand_gate_counts_four_fingers_plus_thumb_as_five_digits(self):
        verdict = {"status": "pass", "reasons": []}
        result = w.enforce_blind_evidence(
            verdict,
            json.dumps({
                "right_hand_position": "raised, palm facing forward",
                "visible_actions": ["waving"],
            }),
            "one hand raised in a casual wave",
            hand_blind_analysis=json.dumps({
                "hand_visible": True, "upright_fingers_visible": 4,
                "thumb_visible": True, "total_digits_visible": 5,
                "extra_digits": False, "missing_digits": False,
                "fused_digits": False, "wrist_plausible": True,
                "anatomically_plausible": True, "defects": [],
                "confidence": "high",
            }),
        )
        self.assertEqual(result["status"], "pass", result.get("reasons"))
        self.assertEqual(
            result["hand_blind_evidence"]["total_digits_visible_derived"], 5
        )

    def test_prompt_role_hashes_do_not_collapse_retry_into_source(self):
        self.assertNotEqual(w.prompt_sha256("canonical"), w.prompt_sha256("recovery"))

    def test_composition_recovery_is_complete_noop_for_last_frame(self):
        # ec999d11 had a smile and no recovery, but later side-by-side review
        # proved it was not the same actor. The no-op remains correct because
        # additive recovery caused even worse drift; identity needs a separate
        # generation/QA mechanism rather than prompt-weight escalation.
        # The v1 additive directive's extreme weights (2.0, 1.8) overwhelm the
        # i2i anchor and generate completely wrong actors even at denoise 0.60.
        # Non-start frames must be returned completely unmodified at any index.
        last_job = {"clip_id": "C001", "frame": "last",
                    "prompt": "actor smiles and waves", "negative": "base"}
        result = w.apply_composition_recovery(last_job, 7)
        # Prompt and negative returned verbatim — no directive prepended
        self.assertEqual(result["prompt"], "actor smiles and waves",
                         "non-start frames must be returned unchanged")
        self.assertEqual(result["negative"], "base",
                         "non-start frame negative must not be modified")
        # No composition_recovery record attached
        self.assertIsNone(result.get("composition_recovery"),
                          "no composition_recovery record for non-start frames")
        # "waving" must not appear in the negative
        self.assertNotIn("waving", result.get("negative", ""),
                         "wave must not appear in the negative for an endpoint frame")

    def test_composition_recovery_v2_still_applies_to_start_frame(self):
        start_job = {"clip_id": "C001", "frame": "start",
                     "prompt": "canonical", "negative": "base"}
        result = w.apply_composition_recovery(start_job, 7)
        self.assertEqual(result.get("composition_recovery", {}).get("version"),
                         "c001-static-full-body-v2",
                         "v2 static recovery must still apply to start-frame jobs")
        self.assertIn("waving", result.get("negative", ""),
                      "start-frame v2 negative must prohibit waving to lock neutral pose")

    def test_c002_last_switches_to_hash_pinned_endpoint_after_two_base_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        donor = root / "donor.png"
        donor.write_bytes(b"immutable endpoint")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for index in range(2):
            attempt = attempts / str(index)
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "identity drift"}))
        job = {
            "clip_id": "C002", "frame": "last", "prompt": "lean and smile",
            "reference_path": str(root / "accepted-start.png"),
        }
        with patch.object(w, "C002_LAST_DONOR_PATH", donor), \
                patch.object(w, "C002_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c002_last_endpoint_recovery(job, 9, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["version"], "c002-last-hash-pinned-endpoint-v1")
        self.assertEqual(control["render_mode"], "c002_last_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c002_last_endpoint_policy_waits_for_two_completed_base_failures(self):
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        donor = root / "donor.png"
        donor.write_bytes(b"immutable endpoint")
        attempt = root / "attempts" / "one"
        attempt.mkdir(parents=True)
        (attempt / "failure.json").write_text(json.dumps({"error": "identity drift"}))
        job = {
            "clip_id": "C002", "frame": "last", "prompt": "lean and smile",
            "reference_path": str(root / "accepted-start.png"),
        }
        with patch.object(w, "C002_LAST_DONOR_PATH", donor):
            recovered = w.apply_c002_last_endpoint_recovery(job, 1, root / "attempts")
        self.assertNotIn("identity_control", recovered)

    def test_vision_envelope_format_failure_retries_same_review_once(self):
        class FakeMediaTools:
            def __init__(self):
                self.calls = 0

            def _run_vision_gpu(self, *args, **kwargs):
                self.calls += 1
                return "{broken" if self.calls == 1 else '{"analysis":"ok"}'

        media = FakeMediaTools()
        result = w._vision_response_json(media, ["same-image"], "same-review")
        self.assertEqual(result, {"analysis": "ok"})
        self.assertEqual(media.calls, 2)

    def test_vision_envelope_format_failure_is_bounded_at_two(self):
        class BrokenMediaTools:
            def __init__(self):
                self.calls = 0

            def _run_vision_gpu(self, *args, **kwargs):
                self.calls += 1
                return "{still broken"

        media = BrokenMediaTools()
        with self.assertRaisesRegex(ValueError, "malformed twice"):
            w._vision_response_json(media, ["same-image"], "same-review")
        self.assertEqual(media.calls, 2)

    def test_c003_start_uses_fullframe_identity_after_two_base_failures(self):
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c002-last.png"
        reference.write_bytes(b"reference")
        attempts = root / "attempts"
        for index in range(2):
            attempt = attempts / str(index)
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "identity drift"}))
        recovered = w.apply_c003_start_identity_recovery({
            "clip_id": "C003", "frame": "start", "prompt": "reset",
            "negative": "camera", "reference_path": str(reference),
        }, 4, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "i2i_identity")
        self.assertEqual(control["max_attempts"], 2)
        self.assertEqual(control["identity_anchor_path"], str(reference.resolve()))
        self.assertIn("exact same", recovered["prompt"])

    def test_c003_start_switches_to_hash_pinned_endpoint_after_two_ip_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c002-last.png"
        reference.write_bytes(b"reference")
        donor = root / "c003-reset.png"
        donor.write_bytes(b"immutable c003 reset")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for index in range(2):
            attempt = attempts / str(index)
            attempt.mkdir(parents=True)
            (attempt / "identity_control.json").write_text(json.dumps({
                "version": "c003-start-fullframe-ipadapter-v1",
                "policy_revision": "same-actor-reset-pose-v1",
            }))
            (attempt / "failure.json").write_text(json.dumps({
                "error": "continuity drift",
            }))
        job = {
            "clip_id": "C003", "frame": "start", "prompt": "reset",
            "reference_path": str(reference),
        }
        with patch.object(w, "C003_START_DONOR_PATH", donor), \
                patch.object(w, "C003_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c003_start_endpoint_recovery(
                job, 6, attempts
            )
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c003_start_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c003_start_endpoint_waits_for_two_ip_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c002-last.png"
        reference.write_bytes(b"reference")
        donor = root / "c003-reset.png"
        donor.write_bytes(b"immutable c003 reset")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempt = root / "attempts" / "one"
        attempt.mkdir(parents=True)
        (attempt / "identity_control.json").write_text(json.dumps({
            "version": "c003-start-fullframe-ipadapter-v1",
            "policy_revision": "same-actor-reset-pose-v1",
        }))
        (attempt / "failure.json").write_text("{}")
        with patch.object(w, "C003_START_DONOR_PATH", donor), \
                patch.object(w, "C003_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c003_start_endpoint_recovery({
                "clip_id": "C003", "frame": "start", "prompt": "reset",
                "reference_path": str(reference),
            }, 5, root / "attempts")
        self.assertNotIn("identity_control", recovered)

    def test_c003_last_base_failure_guard_counts_only_completed_base_qa(self):
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        for name in ("first", "second"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text(json.dumps({"error": "drift"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        interrupted = root / "third-unreviewed"
        interrupted.mkdir()
        (interrupted / "still.png").write_bytes(b"preserved")
        controlled = root / "controlled"
        controlled.mkdir()
        (controlled / "failure.json").write_text("{}")
        (controlled / "qa.json").write_text("{}")
        (controlled / "identity_control.json").write_text("{}")
        self.assertEqual(w.c003_last_base_failure_count(root), 2)

    def test_c003_last_switches_to_hash_pinned_gesture_after_two_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c003-start.png"
        reference.write_bytes(b"accepted start")
        donor = root / "c003-last.png"
        donor.write_bytes(b"immutable gesture")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("first", "second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "identity"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        with patch.object(w, "C003_LAST_DONOR_PATH", donor), \
                patch.object(w, "C003_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c003_last_endpoint_recovery({
                "clip_id": "C003", "frame": "last", "story": "c003-last",
                "prompt": "gesture toward roommate", "reference_path": str(reference),
            }, 7, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c003_last_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)
        self.assertEqual(control["hand_qa_crop_fraction"], [0.62, 0.24, 0.86, 0.48])

    def test_c004_start_switches_to_hash_pinned_profile_after_two_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c003-last.png"
        reference.write_bytes(b"accepted c003 endpoint")
        donor = root / "c004-start.png"
        donor.write_bytes(b"immutable profile and exposure dip")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("first", "second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "identity"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        with patch.object(w, "C004_START_DONOR_PATH", donor), \
                patch.object(w, "C004_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c004_start_endpoint_recovery({
                "clip_id": "C004", "frame": "start", "story": "c004-start",
                "prompt": "profile and exposure dip", "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c004_start_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c004_start_promotes_once_to_camcorder_texture_after_v1_failure(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c003-last.png"
        reference.write_bytes(b"accepted c003 endpoint")
        donor_v1 = root / "c004-v1.png"
        donor_v1.write_bytes(b"profile v1")
        donor_v2 = root / "c004-v2.png"
        donor_v2.write_bytes(b"profile with camcorder texture")
        hash_v1 = hashlib.sha256(donor_v1.read_bytes()).hexdigest()
        hash_v2 = hashlib.sha256(donor_v2.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("base-first", "base-second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text("{}")
            (attempt / "qa.json").write_text("{}")
        failed_v1 = attempts / "failed-v1"
        failed_v1.mkdir()
        (failed_v1 / "failure.json").write_text("{}")
        (failed_v1 / "identity_control.json").write_text(json.dumps({
            "version": "c004-start-hash-pinned-endpoint-v1",
            "policy_revision": "profile-exposure-dip-v1",
        }))
        with patch.object(w, "C004_START_DONOR_PATH", donor_v1), \
                patch.object(w, "C004_START_DONOR_SHA256", hash_v1), \
                patch.object(w, "C004_START_DONOR_V2_PATH", donor_v2), \
                patch.object(w, "C004_START_DONOR_V2_SHA256", hash_v2):
            recovered = w.apply_c004_start_endpoint_recovery({
                "clip_id": "C004", "frame": "start", "story": "c004-start",
                "prompt": "profile and exposure dip", "reference_path": str(reference),
            }, 4, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["version"], "c004-start-hash-pinned-endpoint-v2")
        self.assertEqual(control["policy_revision"],
                         "consumer-camcorder-profile-exposure-v2")
        self.assertEqual(control["endpoint_donor_sha256"], hash_v2)
        self.assertEqual(control["max_attempts"], 1)

    def test_c004_start_retries_same_v2_pixels_once_after_grader_loop(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c003-last.png"
        reference.write_bytes(b"accepted c003 endpoint")
        donor_v2 = root / "c004-v2.png"
        donor_v2.write_bytes(b"profile with camcorder texture")
        hash_v2 = hashlib.sha256(donor_v2.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("base-first", "base-second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text("{}")
            (attempt / "qa.json").write_text("{}")
        failed_v2 = attempts / "failed-v2"
        failed_v2.mkdir()
        (failed_v2 / "failure.json").write_text("{}")
        (failed_v2 / "identity_control.json").write_text(json.dumps({
            "version": "c004-start-hash-pinned-endpoint-v2",
            "policy_revision": "consumer-camcorder-profile-exposure-v2",
        }))
        with patch.object(w, "C004_START_DONOR_V2_PATH", donor_v2), \
                patch.object(w, "C004_START_DONOR_V2_SHA256", hash_v2):
            recovered = w.apply_c004_start_endpoint_recovery({
                "clip_id": "C004", "frame": "start", "story": "c004-start",
                "prompt": "profile and exposure dip", "reference_path": str(reference),
            }, 5, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["version"], "c004-start-hash-pinned-endpoint-v3")
        self.assertEqual(control["policy_revision"], "qa-contract-retry-v1")
        self.assertEqual(control["endpoint_donor_sha256"], hash_v2)
        self.assertEqual(control["max_attempts"], 1)

    def test_c004_last_switches_to_hash_pinned_direct_look_after_two_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c004-start.png"
        reference.write_bytes(b"accepted c004 start")
        donor = root / "c004-last.png"
        donor.write_bytes(b"immutable direct look")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("first", "second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "identity"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        with patch.object(w, "C004_LAST_DONOR_PATH", donor), \
                patch.object(w, "C004_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c004_last_endpoint_recovery({
                "clip_id": "C004", "frame": "last", "story": "c004-last",
                "prompt": "look directly into the lens", "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c004_last_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c005_start_switches_to_hash_pinned_script_after_two_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c004-last.png"
        reference.write_bytes(b"accepted c004 endpoint")
        donor = root / "c005-start.png"
        donor.write_bytes(b"immutable script prop")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("first", "second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "identity"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        with patch.object(w, "C005_START_DONOR_PATH", donor), \
                patch.object(w, "C005_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c005_start_endpoint_recovery({
                "clip_id": "C005", "frame": "start", "story": "c005-start",
                "prompt": "hold a script", "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c005_start_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c005_last_switches_to_hash_pinned_page_drop_after_two_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c005-start.png"
        reference.write_bytes(b"accepted c005 start")
        donor = root / "c005-last.png"
        donor.write_bytes(b"immutable page drop")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("first", "second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "identity"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        with patch.object(w, "C005_LAST_DONOR_PATH", donor), \
                patch.object(w, "C005_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c005_last_endpoint_recovery({
                "clip_id": "C005", "frame": "last", "story": "c005-last",
                "prompt": "drops page", "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c005_last_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c005_last_retries_same_donor_once_for_a_positive_schema_omission(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c005-start.png"
        reference.write_bytes(b"accepted c005 start")
        donor = root / "c005-last.png"
        donor.write_bytes(b"immutable page drop")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("base-first", "base-second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text("{}")
            (attempt / "qa.json").write_text("{}")
        failed_v1 = attempts / "failed-v1"
        failed_v1.mkdir()
        (failed_v1 / "failure.json").write_text("{}")
        (failed_v1 / "identity_control.json").write_text(json.dumps({
            "version": "c005-last-hash-pinned-endpoint-v1",
            "policy_revision": "dropped-page-embarrassed-look-v1",
        }))
        with patch.object(w, "C005_LAST_DONOR_PATH", donor), \
                patch.object(w, "C005_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c005_last_endpoint_recovery({
                "clip_id": "C005", "frame": "last", "story": "c005-last",
                "prompt": "drops page", "reference_path": str(reference),
            }, 4, attempts)
        self.assertEqual(recovered["identity_control"]["version"],
                         "c005-last-hash-pinned-endpoint-v2")

    def test_c006_start_switches_to_hash_pinned_page_pickup_after_two_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c005-last.png"
        reference.write_bytes(b"accepted c005 endpoint")
        donor = root / "c006-start.png"
        donor.write_bytes(b"immutable page pickup")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("first", "second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "identity"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        with patch.object(w, "C006_START_DONOR_PATH", donor), \
                patch.object(w, "C006_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c006_start_endpoint_recovery({
                "clip_id": "C006", "frame": "start", "story": "c006-start",
                "prompt": "crouch to pick up page",
                "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c006_start_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c006_last_switches_to_hash_pinned_standing_endpoint_after_two_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c006-start.png"
        reference.write_bytes(b"accepted c006 start")
        donor = root / "c006-last.png"
        donor.write_bytes(b"immutable standing endpoint")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("first", "second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "pose"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        with patch.object(w, "C006_LAST_DONOR_PATH", donor), \
                patch.object(w, "C006_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c006_last_endpoint_recovery({
                "clip_id": "C006", "frame": "last", "story": "c006-last",
                "prompt": "stand and notice recording light",
                "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c006_last_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c006_last_retries_same_donor_once_after_positive_incomplete_qa(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c006-start.png"
        reference.write_bytes(b"accepted c006 start")
        donor = root / "c006-last.png"
        donor.write_bytes(b"immutable standing endpoint")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("base-first", "base-second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text("{}")
            (attempt / "qa.json").write_text("{}")
        failed_v1 = attempts / "failed-v1"
        failed_v1.mkdir()
        (failed_v1 / "failure.json").write_text(json.dumps({
            "error": "blind clothing fields omitted from positive verdict"
        }))
        (failed_v1 / "identity_control.json").write_text(json.dumps({
            "version": "c006-last-hash-pinned-endpoint-v1",
            "policy_revision": "standing-recording-light-notice-v1",
        }))
        with patch.object(w, "C006_LAST_DONOR_PATH", donor), \
                patch.object(w, "C006_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c006_last_endpoint_recovery({
                "clip_id": "C006", "frame": "last", "story": "c006-last",
                "prompt": "stand and notice recording light",
                "reference_path": str(reference),
            }, 4, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["version"],
                         "c006-last-hash-pinned-endpoint-v2")
        self.assertEqual(control["policy_revision"], "qa-contract-retry-v1")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)

    def test_c006_last_uses_clothing_supplement_after_two_incomplete_reviews(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c006-start.png"
        reference.write_bytes(b"accepted c006 start")
        donor = root / "c006-last.png"
        donor.write_bytes(b"immutable standing endpoint")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("base-first", "base-second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text("{}")
            (attempt / "qa.json").write_text("{}")
        for name, version, revision in (
            ("failed-v1", "c006-last-hash-pinned-endpoint-v1",
             "standing-recording-light-notice-v1"),
            ("failed-v2", "c006-last-hash-pinned-endpoint-v2",
             "qa-contract-retry-v1"),
        ):
            attempt = attempts / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}")
            (attempt / "identity_control.json").write_text(json.dumps({
                "version": version, "policy_revision": revision,
            }))
        with patch.object(w, "C006_LAST_DONOR_PATH", donor), \
                patch.object(w, "C006_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c006_last_endpoint_recovery({
                "clip_id": "C006", "frame": "last", "story": "c006-last",
                "prompt": "stand and notice recording light",
                "reference_path": str(reference),
            }, 5, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["version"],
                         "c006-last-hash-pinned-endpoint-v3")
        self.assertEqual(control["policy_revision"],
                         "blind-clothing-supplement-v1")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)

    def test_c007_start_switches_to_hash_pinned_natural_mark_after_two_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c006-last.png"
        reference.write_bytes(b"accepted c006 endpoint")
        donor = root / "c007-start.png"
        donor.write_bytes(b"immutable natural mark stance")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("first", "second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "identity"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        with patch.object(w, "C007_START_DONOR_PATH", donor), \
                patch.object(w, "C007_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c007_start_endpoint_recovery({
                "clip_id": "C007", "frame": "start", "story": "c007-start",
                "prompt": "return to the mark naturally",
                "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c007_start_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c007_last_switches_to_hash_pinned_grin_point_after_two_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c007-start.png"
        reference.write_bytes(b"accepted c007 start")
        donor = root / "c007-last.png"
        donor.write_bytes(b"immutable grin point")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("first", "second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "identity"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        with patch.object(w, "C007_LAST_DONOR_PATH", donor), \
                patch.object(w, "C007_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c007_last_endpoint_recovery({
                "clip_id": "C007", "frame": "last", "story": "c007-last",
                "prompt": "grin and point", "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c007_last_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c008_start_switches_to_hash_pinned_frozen_exchange_after_two_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        reference = root / "c007-last.png"
        reference.write_bytes(b"accepted c007 endpoint")
        donor = root / "c008-start.png"
        donor.write_bytes(b"immutable frozen exchange")
        donor_hash = hashlib.sha256(donor.read_bytes()).hexdigest()
        attempts = root / "attempts"
        for name in ("first", "second"):
            attempt = attempts / name
            attempt.mkdir(parents=True)
            (attempt / "failure.json").write_text(json.dumps({"error": "qa"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        with patch.object(w, "C008_START_DONOR_PATH", donor), \
                patch.object(w, "C008_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c008_start_endpoint_recovery({
                "clip_id": "C008", "frame": "start", "story": "c008-start",
                "prompt": "freeze mid exchange", "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c008_start_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_completed_base_failure_guard_ignores_interrupted_and_controlled(self):
        import json
        import tempfile
        from pathlib import Path
        root = Path(tempfile.mkdtemp())
        for name in ("first", "second"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text(json.dumps({"error": "drift"}))
            (attempt / "qa.json").write_text(json.dumps({"semantic_check": "fail"}))
        interrupted = root / "third-unreviewed"
        interrupted.mkdir()
        (interrupted / "failure.json").write_text(json.dumps({
            "status": "interrupted_unreviewed", "eligible_for_acceptance": False,
        }))
        controlled = root / "controlled"
        controlled.mkdir()
        (controlled / "failure.json").write_text("{}")
        (controlled / "qa.json").write_text("{}")
        (controlled / "identity_control.json").write_text("{}")
        self.assertEqual(w.completed_base_failure_count(root), 2)

    def test_missing_blind_clothing_gets_candidate_only_supplement(self):
        import json

        class Media:
            def __init__(self):
                self.calls = []

            def _run_vision_gpu(self, *args, **kwargs):
                self.calls.append((args, kwargs))
                return json.dumps({
                    "analysis": json.dumps({"clothing": [
                        {"type": "overshirt", "color": "olive green"},
                        {"type": "jeans", "color": "dark blue"},
                        {"type": "sneakers", "color": "white"},
                    ]})
                })

        media = Media()
        original = json.dumps({
            "subjects": [{"description": "one adult man"}],
            "setting": "living room",
            "clothing": [],
        })
        merged, supplement = w.supplement_missing_blind_clothing(
            media, "candidate.png", original, "exact-vlm", "127.0.0.1:8091"
        )
        parsed = json.loads(merged)
        self.assertEqual(len(parsed["clothing"]), 3)
        self.assertIn("olive green", supplement)
        self.assertEqual(len(media.calls), 1)
        args, kwargs = media.calls[0]
        self.assertEqual(args[0], ["candidate.png"])
        self.assertNotIn("reference", kwargs.get("instruction", "").lower())

    def test_existing_blind_clothing_is_not_requeried(self):
        class Media:
            def _run_vision_gpu(self, *args, **kwargs):
                raise AssertionError("supplemental VLM call must not run")

        original = json.dumps({
            "subjects": [{"description": "one adult man"}],
            "clothing": [{"type": "overshirt", "color": "olive"}],
        })
        merged, supplement = w.supplement_missing_blind_clothing(
            Media(), "candidate.png", original, "exact-vlm", "127.0.0.1:8091"
        )
        self.assertEqual(merged, original)
        self.assertEqual(supplement, "")

    def test_structured_verdict_retries_only_malformed_inner_json(self):
        import json

        class Media:
            def __init__(self):
                self.calls = 0

            def _run_vision_gpu(self, *args, **kwargs):
                self.calls += 1
                analysis = "{bad inner json" if self.calls == 1 else json.dumps({
                    "pass": True, "rationale": "literal evidence",
                    "observed": {}, "checks": {},
                })
                return json.dumps({
                    "analysis": analysis, "model": "exact", "runtime": "llama.cpp",
                })

        def parser(raw, prompt, *, model, runtime):
            if raw.startswith("{bad"):
                return {"status": "fail", "reasons": [
                    "VLM did not return structured JSON"
                ]}
            return {"status": "pass", "reasons": []}

        media = Media()
        wrapped, raw, verdict, retried = w.structured_verdict_with_format_retry(
            media, ["candidate.png"], "prompt", "exact", "host", "rubric", 8192, parser
        )
        self.assertTrue(retried)
        self.assertEqual(media.calls, 2)
        self.assertEqual(verdict["status"], "pass")
        self.assertIn('"pass": true', raw)
        self.assertEqual(wrapped["runtime"], "llama.cpp")

    def test_content_pause_is_not_infra(self):
        msg = "pause at safe checkpoint: v6 C001 misses olive overshirt"
        self.assertTrue(w.is_content_quality_pause(msg))
        self.assertFalse(w.is_infrastructure_watchdog(msg))

    def test_qa_failure_is_content(self):
        msg = "semantic still QA failed; evidence preserved"
        self.assertTrue(w.is_content_quality_pause(msg))
        self.assertFalse(w.is_infrastructure_watchdog(msg))

    def test_stale_progress_is_infra(self):
        msg = "stale progress/logs; inspect evidence before retry"
        self.assertFalse(w.is_content_quality_pause(msg))
        self.assertTrue(w.is_infrastructure_watchdog(msg))



    def test_failed_strong_smile_promotes_tooth_bearing_face_crop(self):
        import tempfile
        from pathlib import Path
        import json
        root = Path(tempfile.mkdtemp())
        wave = root / 'wave'
        wave.mkdir()
        (wave / 'still.png').write_bytes(b'x')
        (wave / 'qa.json').write_text(json.dumps({
            'semantic_review': {
                'status': 'fail',
                'reasons': ['blind evidence does not show the required smile or grin'],
                'continuity_evidence': {
                    'same_person': True, 'same_hair': True, 'same_facial_hair': True,
                    'same_clothing': True, 'same_room_geometry': True,
                },
                'verdict': {'checks': {
                    'requested_subjects_present': True,
                    'requested_pose_or_action_visible': True,
                    'requested_composition_visible': True,
                    'setting_matches': True,
                    'identity_continuity': True,
                    'no_forbidden_equipment': True,
                    'blind_observation_consistent': True,
                }},
            }
        }), encoding='utf-8')
        (wave / 'identity_control.json').write_text(json.dumps({
            'version': 'c001-localized-wave-openpose-ipadapter-v3',
        }), encoding='utf-8')
        for rev in (
            'lower-face-clamped-v2',
            'face-crop-low-denoise-v1',
            'face-crop-dependencies-repaired-v2',
            'face-crop-full-dependencies-repaired-v3',
            'face-crop-strong-smile-guidance-v4',
        ):
            d = root / ('fail_' + rev)
            d.mkdir()
            ver = (
                'c001-smile-refine-ipadapter-v4'
                if rev == 'lower-face-clamped-v2'
                else 'c001-smile-facedetailer-ipadapter-v5'
            )
            (d / 'identity_control.json').write_text(json.dumps({
                'version': ver, 'policy_revision': rev,
            }), encoding='utf-8')
            (d / 'failure.json').write_text('{}', encoding='utf-8')
        original = root / 'anchor.png'
        original.write_bytes(b'y')
        refined = w.apply_smile_refinement({
            'clip_id': 'C001', 'frame': 'last',
            'reference_path': str(original),
            'prompt': 'wave and smile', 'negative': 'camera',
        }, root, 120)
        control = refined['identity_control']
        self.assertEqual(control['version'], 'c001-smile-facedetailer-ipadapter-v5')
        self.assertEqual(control['policy_revision'], 'face-crop-tooth-bearing-smile-v5')
        self.assertEqual(control['max_attempts'], 1)
        self.assertEqual(control['identity_weight'], 0.58)
        self.assertEqual(control['face_detail_denoise'], 0.50)
        self.assertEqual(refined['denoise'], 0.50)
        self.assertIn('tooth-bearing', refined['prompt'])
        self.assertNotIn('open mouth', refined['negative'])
        self.assertIn('closed mouth', refined['negative'])
        self.assertIn('oversized teeth', refined['negative'])

    def test_c009_last_uses_hash_pinned_shrug_after_two_base_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        attempts = root / "attempts"
        attempts.mkdir()
        reference = root / "accepted-start.png"
        reference.write_bytes(b"accepted")
        donor = root / "shrug.png"
        donor.write_bytes(b"shrug")
        donor_hash = hashlib.sha256(b"shrug").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = attempts / name
            attempt.mkdir()
            (attempt / "failure.json").write_text(
                json.dumps({"error": "pose"}), encoding="utf-8"
            )
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C009_LAST_DONOR_PATH", donor), \
                patch.object(w, "C009_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c009_last_endpoint_recovery({
                "clip_id": "C009", "frame": "last", "story": "c009-last",
                "prompt": "turn back with a dismissive shrug",
                "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c009_last_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

    def test_c010_start_reuses_neutral_endpoint_after_two_base_failures(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        attempts = root / "attempts"
        attempts.mkdir()
        reference = root / "c009-last.png"
        reference.write_bytes(b"shrug")
        donor = root / "neutral.png"
        donor.write_bytes(b"neutral")
        donor_hash = hashlib.sha256(b"neutral").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = attempts / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C007_START_DONOR_PATH", donor), \
                patch.object(w, "C007_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c010_start_endpoint_recovery({
                "clip_id": "C010", "frame": "start", "story": "c010-start",
                "prompt": "perform another take more subdued",
                "reference_path": str(reference),
            }, 3, attempts)
        control = recovered["identity_control"]
        self.assertEqual(control["render_mode"], "c010_start_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)

class AppearanceCategoryTests(unittest.TestCase):
    def test_beard_with_mustache_remains_beard_for_continuity(self):
        self.assertEqual(w._appearance_category("beard, mustache"), "beard")

    def test_c016_hand_only_pov_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "floor_hand.png"
        donor.write_bytes(b"floor-hand")
        donor_hash = hashlib.sha256(b"floor-hand").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C016_START_DONOR_PATH", donor), \
                patch.object(w, "C016_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c016_start_endpoint_recovery({
                "clip_id": "C016", "frame": "start", "story": "c016-start",
                "prompt": "camera points at blurred carpet and the actor hand",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c016_start_endpoint_donor")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["semantic_assertions_prompt"], "delivery_qa_prompt")
        self.assertEqual(control["max_attempts"], 1)
        self.assertIn("do not depict the actor's face", recovered["qa_prompt"].lower())

    def test_c016_last_floor_pov_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "floor_empty.png"
        donor.write_bytes(b"floor-empty")
        donor_hash = hashlib.sha256(b"floor-empty").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C016_LAST_DONOR_PATH", donor), \
                patch.object(w, "C016_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c016_last_endpoint_recovery({
                "clip_id": "C016", "frame": "last", "story": "c016-last",
                "prompt": "the carpet becomes damp brown-beige under sickly yellow light",
            }, 3, root)
            skipped = w.apply_c016_last_endpoint_recovery({
                "clip_id": "C016", "frame": "start", "story": "c016-start",
                "prompt": "camera points at blurred carpet and the actor hand",
            }, 3, root)
            too_early = w.apply_c016_last_endpoint_recovery({
                "clip_id": "C016", "frame": "last", "story": "c016-last",
                "prompt": "the carpet becomes damp brown-beige under sickly yellow light",
            }, 1, root / "missing")
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c016_last_endpoint_donor")
        self.assertEqual(control["version"], "c016-last-hash-pinned-floor-pov-v1")
        self.assertEqual(control["policy_revision"], "floor-pov-environment-lock-v1")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["semantic_assertions_prompt"], "delivery_qa_prompt")
        self.assertEqual(control["max_attempts"], 1)
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("damp brown-beige carpet", qa)
        self.assertIn("no hand", qa)
        self.assertIn("absence of a person or pose is correct", qa)
        self.assertNotIn("identity_control", skipped)
        self.assertNotIn("identity_control", too_early)

        failed = root / "v1-fail"
        failed.mkdir()
        (failed / "failure.json").write_text("{}", encoding="utf-8")
        (failed / "identity_control.json").write_text(json.dumps({
            "version": "c016-last-hash-pinned-floor-pov-v1",
            "policy_revision": "floor-pov-environment-lock-v1",
        }), encoding="utf-8")
        with patch.object(w, "C016_LAST_DONOR_PATH", donor), \
                patch.object(w, "C016_LAST_DONOR_SHA256", donor_hash):
            v2 = w.apply_c016_last_endpoint_recovery({
                "clip_id": "C016", "frame": "last", "story": "c016-last",
                "prompt": "the carpet becomes damp brown-beige under sickly yellow light",
            }, 4, root)
        self.assertEqual(
            v2["identity_control"]["version"],
            "c016-last-hash-pinned-floor-pov-v2",
        )
        self.assertEqual(
            v2["identity_control"]["policy_revision"],
            "empty-plate-subject-pose-scope-fix-v1",
        )
        self.assertEqual(v2["identity_control"]["endpoint_donor_sha256"], donor_hash)
        self.assertTrue(v2["skip_reference_continuity"])

    def test_empty_plate_subject_pose_false_positive_is_narrow(self):
        rubric = (
            "Do not depict the actor's face or torso. The actor is entirely outside "
            "the frame: no person, no hand, no sleeve, no body."
        )
        raw = {
            "pass": True,
            "rationale": "Empty floor-level environment matches request.",
            "observed": {
                "subjects": [], "setting": "office corridor",
                "camera_visible": False, "composition": "low-angle carpet",
            },
            "checks": {
                "requested_subjects_present": False,
                "requested_pose_or_action_visible": False,
                "requested_composition_visible": True,
                "setting_matches": True,
                "identity_continuity": True,
                "no_forbidden_equipment": True,
                "blind_observation_consistent": True,
            },
        }
        verdict = {
            "status": "fail",
            "reasons": [
                "semantic check failed: requested_subjects_present",
                "semantic check failed: requested_pose_or_action_visible",
            ],
        }
        blind = {
            "subjects": [], "setting": "office corridor",
            "camera_or_tripod_visible": False,
            "composition": "low-angle shot of carpeted floor",
        }
        self.assertTrue(w.empty_plate_subject_pose_false_positive(
            verdict, json.dumps(blind), raw, rubric
        ))
        actor_prompt = "one fictional adult man stands in an apartment living room"
        self.assertFalse(w.empty_plate_subject_pose_false_positive(
            verdict, json.dumps(blind), raw, actor_prompt
        ))
        camera_blind = dict(blind, camera_or_tripod_visible=True)
        self.assertFalse(w.empty_plate_subject_pose_false_positive(
            verdict, json.dumps(camera_blind), raw, rubric
        ))
        person_blind = dict(blind, subjects=[{"hand": "left"}])
        self.assertFalse(w.empty_plate_subject_pose_false_positive(
            verdict, json.dumps(person_blind), raw, rubric
        ))
        setting_fail = dict(raw)
        setting_fail["checks"] = dict(raw["checks"], setting_matches=False)
        self.assertFalse(w.empty_plate_subject_pose_false_positive(
            verdict, json.dumps(blind), setting_fail, rubric
        ))

    def test_c016_last_donor_hash_is_pinned(self):
        self.assertTrue(w.C016_LAST_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C016_LAST_DONOR_PATH), w.C016_LAST_DONOR_SHA256
        )
        self.assertEqual(
            w.C016_LAST_DONOR_SHA256,
            "088e854fb176577c58d05d43837e697c1eb6639124d2fbd34b7b625e30b31f75",
        )

    def test_c017_start_hand_press_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "hand_press.png"
        donor.write_bytes(b"hand-press")
        donor_hash = hashlib.sha256(b"hand-press").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C017_START_DONOR_PATH", donor), \
                patch.object(w, "C017_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c017_start_endpoint_recovery({
                "clip_id": "C017", "frame": "start", "story": "c017-start",
                "prompt": "a hand presses into unfamiliar damp carpet",
            }, 3, root)
            skipped = w.apply_c017_start_endpoint_recovery({
                "clip_id": "C017", "frame": "last", "story": "c017-last",
                "prompt": "a hand presses into unfamiliar damp carpet",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c017_start_endpoint_donor")
        self.assertEqual(control["version"], "c017-start-hash-pinned-hand-press-pov-v1")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("presses into the damp carpet", qa)
        self.assertIn("exactly one adult hand", qa)
        self.assertNotIn("identity_control", skipped)

    def test_c017_start_donor_hash_is_pinned(self):
        self.assertTrue(w.C017_START_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C017_START_DONOR_PATH), w.C017_START_DONOR_SHA256
        )

    def test_c017_last_wallpaper_wall_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "wallpaper.png"
        donor.write_bytes(b"wallpaper-wall")
        donor_hash = hashlib.sha256(b"wallpaper-wall").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C017_LAST_DONOR_PATH", donor), \
                patch.object(w, "C017_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c017_last_endpoint_recovery({
                "clip_id": "C017", "frame": "last", "story": "c017-last",
                "prompt": "the view turns toward a wall of yellow wallpaper",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c017_last_endpoint_donor")
        self.assertEqual(control["version"], "c017-last-hash-pinned-wallpaper-wall-v1")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        self.assertEqual(control["max_attempts"], 1)
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("yellow patterned wallpaper", qa)
        self.assertIn("no hand", qa)

    def test_c017_last_donor_hash_is_pinned(self):
        self.assertTrue(w.C017_LAST_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C017_LAST_DONOR_PATH), w.C017_LAST_DONOR_SHA256
        )

    def test_c018_start_hand_wallpaper_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "hand_wall.png"
        donor.write_bytes(b"hand-wall")
        donor_hash = hashlib.sha256(b"hand-wall").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C018_START_DONOR_PATH", donor), \
                patch.object(w, "C018_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c018_start_endpoint_recovery({
                "clip_id": "C018", "frame": "start", "story": "c018-start",
                "prompt": "close view of actor hand pressing into yellow wallpaper",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c018_start_endpoint_donor")
        self.assertEqual(control["version"], "c018-start-hash-pinned-hand-wallpaper-v1")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("presses into the yellow wallpaper", qa)
        self.assertIn("exactly one adult hand", qa)

    def test_c018_start_donor_hash_is_pinned(self):
        self.assertTrue(w.C018_START_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C018_START_DONOR_PATH), w.C018_START_DONOR_SHA256
        )

    def test_c018_last_hand_pullback_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "pullback.png"
        donor.write_bytes(b"hand-pullback")
        donor_hash = hashlib.sha256(b"hand-pullback").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C018_LAST_DONOR_PATH", donor), \
                patch.object(w, "C018_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c018_last_endpoint_recovery({
                "clip_id": "C018", "frame": "last", "story": "c018-last",
                "prompt": "a hand pulls back with moisture on the fingers",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c018_last_endpoint_donor")
        self.assertEqual(control["version"], "c018-last-hash-pinned-hand-pullback-v1")
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("moisture on the fingers", qa)
        self.assertIn("pulls back", qa)

    def test_c018_last_donor_hash_is_pinned(self):
        self.assertTrue(w.C018_LAST_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C018_LAST_DONOR_PATH), w.C018_LAST_DONOR_SHA256
        )

    def test_c019_start_chest_cuff_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "cuff.png"
        donor.write_bytes(b"chest-cuff")
        donor_hash = hashlib.sha256(b"chest-cuff").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C019_START_DONOR_PATH", donor), \
                patch.object(w, "C019_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c019_start_endpoint_recovery({
                "clip_id": "C019", "frame": "start", "story": "c019-start",
                "prompt": "chest height empty yellow room sleeve cuff",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c019_start_endpoint_donor")
        self.assertEqual(control["version"], "c019-start-hash-pinned-chest-cuff-v1")
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("sleeve cuff", qa)
        self.assertIn("chest-height", qa)

        failed = root / "v1-fail"
        failed.mkdir()
        (failed / "failure.json").write_text("{}", encoding="utf-8")
        (failed / "identity_control.json").write_text(json.dumps({
            "version": "c019-start-hash-pinned-chest-cuff-v1",
            "policy_revision": "chest-height-empty-room-cuff-v1",
        }), encoding="utf-8")
        with patch.object(w, "C019_START_DONOR_PATH", donor), \
                patch.object(w, "C019_START_DONOR_SHA256", donor_hash):
            v2 = w.apply_c019_start_endpoint_recovery({
                "clip_id": "C019", "frame": "start", "story": "c019-start",
                "prompt": "chest height empty yellow room sleeve cuff",
            }, 4, root)
        self.assertEqual(
            v2["identity_control"]["version"],
            "c019-start-hash-pinned-chest-cuff-v2",
        )
        self.assertIn("requested subject is a small olive-green sleeve cuff",
                      v2["qa_prompt"].lower())

    def test_c019_start_donor_hash_is_pinned(self):
        self.assertTrue(w.C019_START_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C019_START_DONOR_PATH), w.C019_START_DONOR_SHA256
        )

    def test_c019_last_three_openings_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "openings.png"
        donor.write_bytes(b"three-openings")
        donor_hash = hashlib.sha256(b"three-openings").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C019_LAST_DONOR_PATH", donor), \
                patch.object(w, "C019_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c019_last_endpoint_recovery({
                "clip_id": "C019", "frame": "last", "story": "c019-last",
                "prompt": "pans toward three identical openings",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c019_last_endpoint_donor")
        self.assertEqual(control["version"], "c019-last-hash-pinned-three-openings-v1")
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("three identical empty rectangular openings", qa)

    def test_c019_last_donor_hash_is_pinned(self):
        self.assertTrue(w.C019_LAST_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C019_LAST_DONOR_PATH), w.C019_LAST_DONOR_SHA256
        )

    def test_c020_start_three_openings_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "c020.png"
        donor.write_bytes(b"c020-openings")
        donor_hash = hashlib.sha256(b"c020-openings").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C020_START_DONOR_PATH", donor), \
                patch.object(w, "C020_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c020_start_endpoint_recovery({
                "clip_id": "C020", "frame": "start", "story": "c020-start",
                "prompt": "three identical yellow doorless openings",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c020_start_endpoint_donor")
        self.assertEqual(control["version"], "c020-start-hash-pinned-three-openings-v1")
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("fluorescent fixtures repeating overhead", qa)

        failed = root / "v1-fail"
        failed.mkdir()
        (failed / "failure.json").write_text("{}", encoding="utf-8")
        (failed / "identity_control.json").write_text(json.dumps({
            "version": "c020-start-hash-pinned-three-openings-v1",
            "policy_revision": "three-openings-repeating-fluorescents-v1",
        }), encoding="utf-8")
        with patch.object(w, "C020_START_DONOR_PATH", donor), \
                patch.object(w, "C020_START_DONOR_SHA256", donor_hash):
            v2 = w.apply_c020_start_endpoint_recovery({
                "clip_id": "C020", "frame": "start", "story": "c020-start",
                "prompt": "three identical yellow doorless openings",
            }, 4, root)
        self.assertEqual(
            v2["identity_control"]["version"],
            "c020-start-hash-pinned-three-openings-v2",
        )
        failed2 = root / "v2-fail"
        failed2.mkdir()
        (failed2 / "failure.json").write_text("{}", encoding="utf-8")
        (failed2 / "identity_control.json").write_text(json.dumps({
            "version": "c020-start-hash-pinned-three-openings-v2",
            "policy_revision": "static-environment-pose-scope-v1",
        }), encoding="utf-8")
        with patch.object(w, "C020_START_DONOR_PATH", donor), \
                patch.object(w, "C020_START_DONOR_SHA256", donor_hash):
            v3 = w.apply_c020_start_endpoint_recovery({
                "clip_id": "C020", "frame": "start", "story": "c020-start",
                "prompt": "three identical yellow doorless openings",
            }, 5, root)
        self.assertEqual(
            v3["identity_control"]["version"],
            "c020-start-hash-pinned-three-openings-v3",
        )
        self.assertIn("is not a face or torso", v3["qa_prompt"].lower())

    def test_c020_start_donor_hash_is_pinned(self):
        self.assertTrue(w.C020_START_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C020_START_DONOR_PATH), w.C020_START_DONOR_SHA256
        )

    def test_c020_last_center_opening_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "center.png"
        donor.write_bytes(b"center-opening")
        donor_hash = hashlib.sha256(b"center-opening").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C020_LAST_DONOR_PATH", donor), \
                patch.object(w, "C020_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c020_last_endpoint_recovery({
                "clip_id": "C020", "frame": "last", "story": "c020-last",
                "prompt": "advances into the center opening walls closing in",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c020_last_endpoint_donor")
        self.assertEqual(control["version"], "c020-last-hash-pinned-center-opening-v1")
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("center", qa)
        self.assertIn("closing", qa)

    def test_c020_last_donor_hash_is_pinned(self):
        self.assertTrue(w.C020_LAST_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C020_LAST_DONOR_PATH), w.C020_LAST_DONOR_SHA256
        )

    def test_c021_start_narrow_corridor_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "narrow.png"
        donor.write_bytes(b"narrow-corridor")
        donor_hash = hashlib.sha256(b"narrow-corridor").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C021_START_DONOR_PATH", donor), \
                patch.object(w, "C021_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c021_start_endpoint_recovery({
                "clip_id": "C021", "frame": "start", "story": "c021-start",
                "prompt": "low through a narrow yellow corridor",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c021_start_endpoint_donor")
        self.assertEqual(control["version"], "c021-start-hash-pinned-narrow-corridor-v1")
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("narrow", qa)
        self.assertIn("carpet fills the lower frame", qa)

    def test_c021_start_donor_hash_is_pinned(self):
        self.assertTrue(w.C021_START_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C021_START_DONOR_PATH), w.C021_START_DONOR_SHA256
        )

    def test_c021_last_look_back_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "lookback.png"
        donor.write_bytes(b"look-back")
        donor_hash = hashlib.sha256(b"look-back").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C021_LAST_DONOR_PATH", donor), \
                patch.object(w, "C021_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c021_last_endpoint_recovery({
                "clip_id": "C021", "frame": "last", "story": "c021-last",
                "prompt": "swings back over the shoulder toward the corridor behind",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c021_last_endpoint_donor")
        self.assertEqual(control["version"], "c021-last-hash-pinned-look-back-v1")
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("corridor behind", qa)

    def test_c021_last_donor_hash_is_pinned(self):
        self.assertTrue(w.C021_LAST_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C021_LAST_DONOR_PATH), w.C021_LAST_DONOR_SHA256
        )

    def test_c022_start_empty_corridor_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "empty.png"
        donor.write_bytes(b"empty-corridor")
        donor_hash = hashlib.sha256(b"empty-corridor").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C022_START_DONOR_PATH", donor), \
                patch.object(w, "C022_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c022_start_endpoint_recovery({
                "clip_id": "C022", "frame": "start", "story": "c022-start",
                "prompt": "the corridor ahead appears empty and ordinary",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c022_start_endpoint_donor")
        self.assertEqual(control["version"], "c022-start-hash-pinned-empty-corridor-v1")
        self.assertIn("empty corridor", recovered["qa_prompt"].lower())

    def test_c022_start_donor_hash_is_pinned(self):
        self.assertTrue(w.C022_START_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C022_START_DONOR_PATH), w.C022_START_DONOR_SHA256
        )

    def test_c022_last_longer_corridor_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "longer.png"
        donor.write_bytes(b"longer-corridor")
        donor_hash = hashlib.sha256(b"longer-corridor").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C022_LAST_DONOR_PATH", donor), \
                patch.object(w, "C022_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c022_last_endpoint_recovery({
                "clip_id": "C022", "frame": "last", "story": "c022-last",
                "prompt": "the same corridor appears subtly longer and more distant",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c022_last_endpoint_donor")
        self.assertEqual(control["version"], "c022-last-hash-pinned-longer-corridor-v1")
        self.assertIn("longer", recovered["qa_prompt"].lower())

    def test_c022_last_donor_hash_is_pinned(self):
        self.assertTrue(w.C022_LAST_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C022_LAST_DONOR_PATH), w.C022_LAST_DONOR_SHA256
        )

    def test_c023_start_gesturing_hand_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "gesture.png"
        donor.write_bytes(b"gesturing-hand")
        donor_hash = hashlib.sha256(b"gesturing-hand").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C023_START_DONOR_PATH", donor), \
                patch.object(w, "C023_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c023_start_endpoint_recovery({
                "clip_id": "C023", "frame": "start", "story": "c023-start",
                "prompt": "looking back with a hand gesturing into frame",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c023_start_endpoint_donor")
        self.assertEqual(control["version"], "c023-start-hash-pinned-gesturing-hand-v1")
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("gestures into the lower frame", qa)
        self.assertIn("exactly one adult hand", qa)

    def test_c023_start_donor_hash_is_pinned(self):
        self.assertTrue(w.C023_START_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C023_START_DONOR_PATH), w.C023_START_DONOR_SHA256
        )

    def test_c023_last_hand_slap_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "slap.png"
        donor.write_bytes(b"hand-slap")
        donor_hash = hashlib.sha256(b"hand-slap").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C023_LAST_DONOR_PATH", donor), \
                patch.object(w, "C023_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c023_last_endpoint_recovery({
                "clip_id": "C023", "frame": "last", "story": "c023-last",
                "prompt": "a hand slaps against the wall for balance",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c023_last_endpoint_donor")
        self.assertEqual(control["version"], "c023-last-hash-pinned-hand-slap-v1")
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("slaps against the yellow patterned wallpaper", qa)

    def test_c023_last_donor_hash_is_pinned(self):
        self.assertTrue(w.C023_LAST_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C023_LAST_DONOR_PATH), w.C023_LAST_DONOR_SHA256
        )

    def test_c024_start_branching_corridor_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "branch.png"
        donor.write_bytes(b"branching")
        donor_hash = hashlib.sha256(b"branching").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C024_START_DONOR_PATH", donor), \
                patch.object(w, "C024_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c024_start_endpoint_recovery({
                "clip_id": "C024", "frame": "start", "story": "c024-start",
                "prompt": "looks down a branching corridor",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c024_start_endpoint_donor")
        self.assertEqual(control["version"], "c024-start-hash-pinned-branching-corridor-v1")
        self.assertIn("branching", recovered["qa_prompt"].lower())

    def test_c024_start_donor_hash_is_pinned(self):
        self.assertTrue(w.C024_START_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C024_START_DONOR_PATH), w.C024_START_DONOR_SHA256
        )

    def test_c024_last_flickering_passage_uses_specific_hash_pinned_candidate(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "flicker.png"
        donor.write_bytes(b"flickering")
        donor_hash = hashlib.sha256(b"flickering").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C024_LAST_DONOR_PATH", donor), \
                patch.object(w, "C024_LAST_DONOR_SHA256", donor_hash):
            recovered = w.apply_c024_last_endpoint_recovery({
                "clip_id": "C024", "frame": "last", "story": "c024-last",
                "prompt": "turns toward a passage with one flickering fluorescent",
            }, 3, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c024_last_endpoint_donor")
        self.assertEqual(control["version"], "c024-last-hash-pinned-flickering-passage-v1")
        self.assertIn("flickering", recovered["qa_prompt"].lower())

    def test_c024_last_donor_hash_is_pinned(self):
        self.assertTrue(w.C024_LAST_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C024_LAST_DONOR_PATH), w.C024_LAST_DONOR_SHA256
        )

    def test_c025_corridor_donors_are_pinned(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        self.assertTrue(w.C025_START_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C025_START_DONOR_PATH), w.C025_START_DONOR_SHA256
        )
        self.assertTrue(w.C025_LAST_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C025_LAST_DONOR_PATH), w.C025_LAST_DONOR_SHA256
        )
        root = Path(tempfile.mkdtemp())
        donor = root / "c025.png"
        donor.write_bytes(b"c025")
        donor_hash = hashlib.sha256(b"c025").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        with patch.object(w, "C025_START_DONOR_PATH", donor), \
                patch.object(w, "C025_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c025_start_endpoint_recovery({
                "clip_id": "C025", "frame": "start", "story": "c025-start",
                "prompt": "long yellow corridor",
            }, 3, root)
        self.assertEqual(
            recovered["identity_control"]["version"],
            "c025-start-hash-pinned-long-corridor-v1",
        )

    def test_c027_start_switches_to_mode_b_wall_after_ipadapter_v3(self):
        import hashlib
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        root = Path(tempfile.mkdtemp())
        donor = root / "wall.png"
        donor.write_bytes(b"close-wall")
        donor_hash = hashlib.sha256(b"close-wall").hexdigest()
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        for name in ("v3-one", "v3-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "identity_control.json").write_text(json.dumps({
                "version": "c027-start-close-face-ipadapter-v3-output-index-fix",
                "policy_revision": "ipadapter-second-output-v1",
            }), encoding="utf-8")
        with patch.object(w, "C027_START_DONOR_PATH", donor), \
                patch.object(w, "C027_START_DONOR_SHA256", donor_hash):
            recovered = w.apply_c027_start_identity_recovery({
                "clip_id": "C027", "frame": "start", "story": "c027-start",
                "prompt": "close handheld view of a yellow-lit wall",
            }, 8, root)
        control = recovered["identity_control"]
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertEqual(control["render_mode"], "c027_start_endpoint_donor")
        self.assertEqual(control["version"], "c027-start-hash-pinned-close-wall-v4")
        self.assertEqual(control["endpoint_donor_sha256"], donor_hash)
        qa = recovered["qa_prompt"].lower()
        self.assertIn("do not depict the actor's face", qa)
        self.assertIn("yellow-lit wall", qa)
        self.assertIn("flickering", qa)

    def test_c027_start_donor_hash_is_pinned(self):
        self.assertTrue(w.C027_START_DONOR_PATH.is_file())
        self.assertEqual(
            w.sha256(w.C027_START_DONOR_PATH), w.C027_START_DONOR_SHA256
        )

    def test_c026_start_recovers_as_bounded_handheld_pov_after_two_failures(self):
        import json
        import tempfile
        from pathlib import Path

        root = Path(tempfile.mkdtemp())
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        recovered = w.apply_c026_start_pov_recovery({
            "clip_id": "C026", "frame": "start", "story": "c026-start",
            "prompt": "actor near a corner", "reference_path": "c025-last.png",
        }, 3, root)
        control = recovered["identity_control"]
        self.assertEqual(control["version"], "c026-start-pov-corner-reframe-v2")
        self.assertEqual(control["render_mode"], "scene_i2i_reframe")
        self.assertEqual(control["max_attempts"], 2)
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertIn("do not depict a face", recovered["qa_prompt"].lower())
        self.assertIn("corner", recovered["qa_prompt"].lower())

    def test_c026_last_recovers_as_bounded_continuation_pov_after_two_failures(self):
        import json
        import tempfile
        from pathlib import Path

        root = Path(tempfile.mkdtemp())
        for name in ("base-one", "base-two"):
            attempt = root / name
            attempt.mkdir()
            (attempt / "failure.json").write_text("{}", encoding="utf-8")
            (attempt / "qa.json").write_text(
                json.dumps({"semantic_check": "fail"}), encoding="utf-8"
            )
        recovered = w.apply_c026_last_pov_recovery({
            "clip_id": "C026", "frame": "last", "story": "c026-last",
            "prompt": "actor leans around a corner", "reference_path": "c026-start.png",
        }, 3, root)
        control = recovered["identity_control"]
        self.assertEqual(control["version"], "c026-last-pov-corridor-reframe-v1")
        self.assertEqual(control["render_mode"], "scene_i2i_reframe")
        self.assertEqual(control["max_attempts"], 2)
        self.assertTrue(recovered["skip_reference_continuity"])
        self.assertIn("no pose or action is requested", recovered["qa_prompt"].lower())
        self.assertIn("continuation corridor", recovered["qa_prompt"].lower())

    def test_scene_plate_wording_allows_empty_no_action_semantic_repair(self):
        verdict = {"reasons": ["semantic check failed: requested_pose_or_action_visible"]}
        blind = '{"subjects":[],"camera_or_tripod_visible":false}'
        raw = {
            "pass": True,
            "checks": {
                "setting_matches": True,
                "requested_composition_visible": True,
                "no_forbidden_equipment": True,
            },
        }
        prompt = (
            "Do not depict a face, torso, full body, or visible camera. "
            "No pose or action is requested; absence of a person is correct."
        )
        self.assertTrue(w.static_environment_pose_false_positive(
            verdict, blind, raw, prompt
        ))


class StillRetryHardCapTests(unittest.TestCase):
    """Fix 2026-09-23 (readiness-audit finding "other risks", fix-set item
    #10): the `while not accepted:` still-generation retry loop had no
    explicit, always-enforced upper bound -- only recovery-path-specific
    counters (e.g. apply_identity_pose_recovery's own "recovery_index < 96"
    behavior change) bounded it, which is soft and behavior-dependent, not
    an enforced ceiling. These test the extracted, directly-callable
    still_retry_cap_reached()/max_still_retry_attempts() helpers the fix
    added, since run() itself is a large orchestration function (spawns a
    watchdog subprocess, writes production state, renders) not otherwise
    unit-tested in this suite."""

    def setUp(self):
        os.environ.pop("PROMPT_PACK_MAX_STILL_RETRIES", None)
        self.addCleanup(os.environ.pop, "PROMPT_PACK_MAX_STILL_RETRIES", None)

    def test_default_cap_is_two_hundred(self):
        self.assertEqual(w.max_still_retry_attempts(), 200)

    def test_default_cap_is_comfortably_above_every_named_recovery_ceiling(self):
        """apply_identity_pose_recovery alone deliberately retries up to
        recovery_index 96 -- the safety-net cap must never fire before a
        legitimate, already-bounded recovery path finishes its own run."""
        self.assertGreater(w.max_still_retry_attempts(), 96)

    def test_cap_not_reached_below_threshold(self):
        self.assertFalse(w.still_retry_cap_reached(0))
        self.assertFalse(w.still_retry_cap_reached(199))

    def test_cap_reached_at_and_beyond_threshold(self):
        self.assertTrue(w.still_retry_cap_reached(200))
        self.assertTrue(w.still_retry_cap_reached(201))
        self.assertTrue(w.still_retry_cap_reached(10_000))

    def test_cap_is_overridable_via_environment_variable(self):
        os.environ["PROMPT_PACK_MAX_STILL_RETRIES"] = "5"
        self.assertEqual(w.max_still_retry_attempts(), 5)
        self.assertTrue(w.still_retry_cap_reached(5))
        self.assertFalse(w.still_retry_cap_reached(4))


if __name__ == "__main__":
    unittest.main()
