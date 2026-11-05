#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_equal_shares_completion as audit


CLIP_IDS = [f"C{i:03d}" for i in range(123)] + ["01B"]
FL2VA = "01B"


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _touch(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return str(path)


def _story_config() -> dict:
    clips = [{"id": cid, "duration": 10, "sequence_order": i} for i, cid in enumerate(CLIP_IDS[:-1])]
    clips.append({"id": FL2VA, "duration": 36, "sequence_order": 123})
    return {"clips": clips}


def _voice_requirements() -> dict:
    recurring = ["Narrator"]
    one_off = ["Wealthy commuter", "Unhoused man"]
    clips = []
    for cid in CLIP_IDS:
        if cid == FL2VA:
            clips.append({
                "id": cid,
                "speakers": ["Wealthy commuter", "Unhoused man"],
                "audio_reference_speakers": [],
                "no_audio_reference_speakers": ["Wealthy commuter", "Unhoused man"],
                "path": "fl2va",
                "node": "MiniMaxH3ImageToVideo",
            })
        else:
            clips.append({
                "id": cid,
                "speakers": ["Narrator"],
                "audio_reference_speakers": ["Narrator"],
                "no_audio_reference_speakers": [],
                "path": "ref2va",
                "node": "MiniMaxH3ReferenceToVideo",
            })
    return {
        "one_off": one_off,
        "recurring": recurring,
        "summary": {"fl2va_clips": [FL2VA]},
        "clips": clips,
    }


def _accepted_audio(root: Path, cid: str, *, refs=None, status="accepted", extra=None) -> dict:
    rec = {
        "status": status,
        "accepted_attempt": 1,
        "accepted_full_wav": _touch(root / "audio" / "h3_dialogue" / f"{cid}_a01_full.wav"),
        "source_video": _touch(root / "raw" / f"{cid}.mp4"),
        "validation_report": _touch(root / "audio_validation" / f"{cid}_a01.json"),
        "attempts": [{
            "attempt": 1,
            "audio_references": refs if refs is not None else (
                [] if cid == FL2VA else [f"voices/narrator/{cid}.wav"]
            ),
            "voice_ref_characters": (
                [] if cid == FL2VA else ["Narrator"]
            ) if refs is None else [],
        }],
    }
    if extra:
        rec.update(extra)
        if "attempts" in extra:
            rec["attempts"] = extra["attempts"]
    return rec


def _accepted_picture(root: Path, cid: str, shared: Path, status="visually_accepted") -> dict:
    return {
        "status": status,
        "selected_picture_raw": _touch(shared / cid / "take.mp4"),
        "visual_validation_report": _touch(root / "visual_validation" / f"{cid}.json"),
        "assembly_input": _touch(root / "assembly" / f"{cid}.mp4"),
        "selected_exact_audio_wav": _touch(root / "assembly_wav" / f"{cid}.wav"),
    }


def _synced_probe(duration=1266.0) -> dict:
    return {
        "format": {"duration": str(duration)},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1344, "height": 768,
             "duration": str(duration)},
            {"codec_type": "audio", "codec_name": "aac", "duration": str(duration)},
        ],
    }


def _passing_project(root: Path, shared: Path) -> None:
    _write(root / "story_config.json", _story_config())
    _write(root / "voice_requirements.json", _voice_requirements())
    audio_clips = {cid: _accepted_audio(root, cid) for cid in CLIP_IDS}
    picture_clips = {cid: _accepted_picture(root, cid, shared) for cid in CLIP_IDS}
    _write(root / "audio_pass_manifest.json", {"clips": audio_clips})
    _write(root / "picture_pass_manifest.json", {"clips": picture_clips})
    _write(root / "manifest.json", {"clips": {cid: {"status": "valid"} for cid in CLIP_IDS}})
    _write(root / "visual_audit.json", {
        "accepted_count_at_review": 43,
        "reviewed_pass": CLIP_IDS[:43],
        "audio_audit": {"h3_generated_audio": "discarded from final assembly"},
    })
    _touch(root / "EQUAL_SHARES_FINAL_1344x768.mp4")


class CompletionAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "equal_shares"
        self.shared = Path(self.temp.name) / "shared"
        self.root.mkdir()
        self.shared.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, probe_payload=None):
        payload = probe_payload if probe_payload is not None else _synced_probe()
        with patch.object(audit, "probe", return_value=payload):
            return audit.run_audit(self.root, shared_raw_root=self.shared)

    def test_legacy_valid_and_visual_audit_43_are_not_audio_acceptance(self):
        _write(self.root / "story_config.json", _story_config())
        _write(self.root / "voice_requirements.json", _voice_requirements())
        _write(self.root / "audio_pass_manifest.json", {"clips": {}})
        _write(self.root / "manifest.json", {
            "clips": {cid: {"status": "valid"} for cid in CLIP_IDS}
        })
        _write(self.root / "visual_audit.json", {
            "accepted_count_at_review": 43,
            "reviewed_pass": CLIP_IDS[:43],
        })
        report = self._run()
        self.assertFalse(report["complete"])
        self.assertFalse(report["checks"]["audio_gate_124_accepted"])
        self.assertEqual(0, report["audio_accepted_count"])
        self.assertEqual(124, report["legacy_manifest_valid_count_informational"])
        self.assertEqual(43, report["visual_audit_accepted_count_informational"])
        self.assertTrue(report["visual_audit_is_not_stage1_audio_acceptance"])
        self.assertTrue(report["legacy_manifest_valid_is_not_stage1_audio_acceptance"])
        self.assertTrue(report["checks"]["zero_pending_ear_review"])
        self.assertTrue(report["checks"]["zero_human_review_needed"])
        self.assertTrue(report["checks"]["no_one_off_or_vox_refs_on_accepted_clips"])

    def test_pending_ear_review_and_human_review_block(self):
        _passing_project(self.root, self.shared)
        audio = json.loads((self.root / "audio_pass_manifest.json").read_text(encoding="utf-8"))
        audio["clips"]["C000"]["status"] = "pending_ear_review"
        _write(self.root / "audio_pass_manifest.json", audio)
        picture = json.loads((self.root / "picture_pass_manifest.json").read_text(encoding="utf-8"))
        picture["clips"]["C001"]["status"] = "human_review_needed"
        _write(self.root / "picture_pass_manifest.json", picture)
        report = self._run()
        self.assertFalse(report["complete"])
        self.assertFalse(report["checks"]["audio_gate_124_accepted"])
        self.assertFalse(report["checks"]["zero_pending_ear_review"])
        self.assertFalse(report["checks"]["zero_human_review_needed"])
        self.assertIn("C000", report["pending_ear_review"])
        self.assertIn("C001", report["human_review_needed"])

    def test_needs_ear_review_counts_as_pending(self):
        _passing_project(self.root, self.shared)
        audio = json.loads((self.root / "audio_pass_manifest.json").read_text(encoding="utf-8"))
        audio["clips"]["C002"]["status"] = "needs_ear_review"
        _write(self.root / "audio_pass_manifest.json", audio)
        report = self._run()
        self.assertFalse(report["checks"]["zero_pending_ear_review"])
        self.assertIn("C002", report["pending_ear_review"])

    def test_one_off_speaker_on_accepted_clip_fails(self):
        _passing_project(self.root, self.shared)
        audio = json.loads((self.root / "audio_pass_manifest.json").read_text(encoding="utf-8"))
        audio["clips"]["C000"]["voice_ref_characters"] = ["Wealthy commuter"]
        audio["clips"]["C000"]["attempts"][0]["voice_ref_characters"] = ["Wealthy commuter"]
        audio["clips"]["C000"]["attempts"][0]["audio_references"] = [
            "voices/wealthy_commuter/omni_master_v1.wav"
        ]
        _write(self.root / "audio_pass_manifest.json", audio)
        report = self._run()
        self.assertFalse(report["checks"]["no_one_off_or_vox_refs_on_accepted_clips"])
        self.assertTrue(any("one-off" in row["reason"] for row in report["illicit_voice_references"]))

    def test_vox_path_on_accepted_clip_fails(self):
        _passing_project(self.root, self.shared)
        audio = json.loads((self.root / "audio_pass_manifest.json").read_text(encoding="utf-8"))
        audio["clips"]["C000"]["attempts"][0]["audio_references"] = [
            "voices/vox_narrator/VOX_NARRATOR_REF.wav"
        ]
        audio["clips"]["C000"]["attempts"][0]["voice_ref_characters"] = []
        _write(self.root / "audio_pass_manifest.json", audio)
        report = self._run()
        self.assertFalse(report["checks"]["no_one_off_or_vox_refs_on_accepted_clips"])
        self.assertTrue(any("VOX" in row["reason"] for row in report["illicit_voice_references"]))

    def test_fl2va_accepted_with_audio_refs_fails(self):
        _passing_project(self.root, self.shared)
        audio = json.loads((self.root / "audio_pass_manifest.json").read_text(encoding="utf-8"))
        audio["clips"][FL2VA]["attempts"][0]["audio_references"] = [
            "voices/narrator/omni_master_v2.wav"
        ]
        audio["clips"][FL2VA]["attempts"][0]["voice_ref_characters"] = ["Narrator"]
        _write(self.root / "audio_pass_manifest.json", audio)
        report = self._run()
        self.assertFalse(report["checks"]["no_one_off_or_vox_refs_on_accepted_clips"])
        self.assertTrue(any("fl2va" in row["reason"] for row in report["illicit_voice_references"]))

    def test_prompt_audio_tag_for_one_off_fails(self):
        prompt = (
            "<Subject 1> is Wealthy commuter in <Picture 1>.\n"
            "<Audio 1> is the voice-timbre reference for <Subject 1> (S1), containing a single dry spoken English vocal layer.\n"
        )
        self.assertEqual(
            ["Wealthy commuter"],
            audit.prompt_audio_reference_characters(prompt),
        )
        _passing_project(self.root, self.shared)
        (self.root / "prompts_native_r2v").mkdir()
        (self.root / "prompts_native_r2v" / f"{FL2VA}.txt").write_text(prompt, encoding="utf-8")
        report = self._run()
        self.assertFalse(report["checks"]["no_one_off_or_vox_refs_on_accepted_clips"])

    def test_missing_voice_requirements_fails_closed(self):
        _write(self.root / "story_config.json", _story_config())
        report = self._run()
        self.assertFalse(report["checks"]["voice_requirements_present"])
        self.assertFalse(report["checks"]["no_one_off_or_vox_refs_on_accepted_clips"])

    def test_master_duration_and_sync_gates(self):
        _passing_project(self.root, self.shared)
        unsynced = _synced_probe(1266.0)
        unsynced["streams"][1]["duration"] = "1200.0"
        report = self._run(unsynced)
        self.assertFalse(report["checks"]["final_aac_synced"])
        self.assertTrue(report["checks"]["final_duration_within_2s_of_1266"])

        too_long = _synced_probe(1300.0)
        report = self._run(too_long)
        self.assertFalse(report["checks"]["final_duration_within_2s_of_1266"])
        self.assertFalse(report["checks"]["final_duration_matches_edit"])

        missing_stream_duration = {
            "format": {"duration": "1266.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1344, "height": 768},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
        report = self._run(missing_stream_duration)
        self.assertFalse(report["checks"]["final_aac_synced"])

    def test_full_audio_first_pass(self):
        _passing_project(self.root, self.shared)
        report = self._run()
        self.assertTrue(report["complete"], json.dumps(report["checks"], indent=2))
        self.assertEqual(124, report["audio_accepted_count"])
        self.assertEqual(124, report["picture_accepted_count"])
        self.assertTrue(report["checks"]["final_aac_synced"])
        self.assertTrue(report["checks"]["final_duration_within_2s_of_1266"])
        self.assertTrue(report["checks"]["no_one_off_or_vox_refs_on_accepted_clips"])
        self.assertTrue(report["checks"]["zero_pending_ear_review"])
        self.assertEqual(43, report["visual_audit_accepted_count_informational"])
        self.assertEqual(0, len(report["illicit_voice_references"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
