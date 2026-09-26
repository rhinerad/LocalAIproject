#!/usr/bin/env python3
"""Offline tests: native per-character MiniMax voice continuity."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import native_voice_continuity as nvc
import gvd_graph_builder as ggb


def _wav(path: Path, payload: bytes = b"RIFF....WAVEfmt ") -> Path:
    path.write_bytes(payload + b"\x00" * 64)
    return path


def test_per_character_bootstrap_not_global_c001():
    dialogue = {
        "S001": [{"speaker_id": "ALICE", "text": "Hello there."}],
        "S002": [{"speaker_id": "BOB", "text": "Hi Alice."}, {"speaker_id": "ALICE", "text": "Welcome."}],
        "S003": [{"speaker_id": "BOB", "text": "Later."}],
    }
    first = nvc.first_qualifying_speaking_shots(dialogue)
    assert first["ALICE"] == "S001"
    assert first["BOB"] == "S002"
    deps = nvc.bootstrap_dependencies(dialogue)
    assert deps["S001"] == []
    assert deps["S002"] == ["ALICE"]
    assert set(deps["S003"]) == {"BOB"}


def test_canonical_immutable_and_job_isolated():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        src = _wav(td / "src.wav", b"SRC-A")
        ref = _wav(td / "alice_v1.wav", b"REF-A")
        nvc.register_candidate(
            db,
            candidate_id="cand1",
            job_id="jobA",
            character_id="ALICE",
            bootstrap_shot_id="S001",
            bootstrap_attempt_id="att1",
            source_audio_path=src,
            segment_start_sample=0,
            segment_end_sample=1000,
            reference_audio_path=ref,
            exact_reference_transcript="Hello there.",
            qa_evidence={"speaker_attribution_ok": True},
        )
        rec = nvc.promote_canonical(db, job_id="jobA", character_id="ALICE", candidate_id="cand1")
        assert rec.selection_status == nvc.CANONICAL
        ref2 = _wav(td / "alice_v2.wav", b"REF-B-DIFFERENT")
        nvc.register_candidate(
            db,
            candidate_id="cand2",
            job_id="jobA",
            character_id="ALICE",
            bootstrap_shot_id="S002",
            bootstrap_attempt_id="att2",
            source_audio_path=src,
            segment_start_sample=0,
            segment_end_sample=1000,
            reference_audio_path=ref2,
            exact_reference_transcript="Hello there.",
        )
        try:
            nvc.promote_canonical(db, job_id="jobA", character_id="ALICE", candidate_id="cand2")
            raise AssertionError("should refuse recursive replace")
        except nvc.NativeVoiceError:
            pass
        assert nvc.get_canonical_voice(db, job_id="jobB", character_id="ALICE") is None
        got = nvc.get_canonical_voice(db, job_id="jobA", character_id="ALICE")
        assert got is not None
        assert got.reference_audio_hash == rec.reference_audio_hash


def test_missing_canonical_blocks_dependent_shot_only():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    dialogue = {
        "S001": [{"speaker_id": "ALICE", "text": "Hi."}],
        "S002": [{"speaker_id": "ALICE", "text": "Again."}],
    }
    nvc.require_canonical_voices_for_shot(
        db,
        job_id="jobA",
        shot_id="S001",
        dialogue_lines=dialogue["S001"],
        shot_dialogue_index=dialogue,
    )
    try:
        nvc.require_canonical_voices_for_shot(
            db,
            job_id="jobA",
            shot_id="S002",
            dialogue_lines=dialogue["S002"],
            shot_dialogue_index=dialogue,
        )
        raise AssertionError("dependent shot should block")
    except nvc.NativeVoiceError:
        pass


def test_forbid_c001_master_for_other_character_and_tts_fallback():
    try:
        nvc.assert_not_global_c001_voice("BOB", "C001_master_voice.wav")
        raise AssertionError("expected reject")
    except nvc.NativeVoiceError:
        pass
    try:
        nvc.forbid_tts_fallback("fish_audio", native_required=True)
        raise AssertionError("expected reject")
    except nvc.NativeVoiceError:
        pass


def test_graph_builder_dotted_autogrow_and_limits():
    plan = ggb.RefBindingPlan(
        images=[ggb.ImageRef("still_a.png", character_id="ALICE")],
        audios=[ggb.AudioRef("alice.wav", character_id="ALICE", exact_transcript="Hi.")],
    )
    g = ggb.apply_ref2va_autogrow(
        {"31": {"class_type": "CLIPLoader", "inputs": {}}, "32": {"class_type": "VAELoader", "inputs": {}}},
        prompt="A scene.",
        plan=plan,
        width=864,
        height=480,
        length=124,
    )
    inputs = g["20"]["inputs"]
    assert "ref_images.ref_image_0" in inputs
    assert "ref_audios.ref_audio_0" in inputs
    assert "ref_images" not in inputs
    assert "<Picture 1>" in inputs["prompt"]
    assert "<Audio 1>" in inputs["prompt"]
    assert "ALICE" in inputs["prompt"]
    ggb.assert_no_bare_ref_images_key(g)
    bad = ggb.RefBindingPlan(
        audios=[
            ggb.AudioRef(f"a{i}.wav", character_id=f"C{i}", exact_transcript="x")
            for i in range(4)
        ]
    )
    try:
        bad.validate()
        raise AssertionError("expected over-limit")
    except ggb.GraphBuildError:
        pass


def main() -> int:
    tests = [
        test_per_character_bootstrap_not_global_c001,
        test_canonical_immutable_and_job_isolated,
        test_missing_canonical_blocks_dependent_shot_only,
        test_forbid_c001_master_for_other_character_and_tts_fallback,
        test_graph_builder_dotted_autogrow_and_limits,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print("PASS", fn.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL", fn.__name__, exc)
    print("summary", {"ok": failed == 0, "failed": failed, "total": len(tests)})
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
