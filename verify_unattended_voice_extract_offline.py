#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import unattended_policy as up
import voice_extract as ve

def test_policy_separates_machine_operator():
    pol = up.UnattendedPolicy(job_id="j1", native_minimax_voice_required=True)
    rec = up.evaluate_machine_acceptance(
        pol, technical_pass=True, audio_pass=True, has_dialogue=True,
        selected=True, retry_count=0, replan_count=0, voice_backend="minimax_native",
    )
    assert rec.machine_accepted is True
    assert rec.operator_accepted is None
    assert rec.is_fully_accepted(require_operator=True) is False
    rec.operator_accepted = True
    assert rec.is_fully_accepted(require_operator=True) is True
    bad = up.evaluate_machine_acceptance(
        pol, technical_pass=True, audio_pass=True, has_dialogue=True,
        selected=True, retry_count=0, replan_count=0, voice_backend="fish_audio",
    )
    assert bad.machine_accepted is False
    assert "tts_backend_forbidden_under_native_policy" in bad.machine_reasons

def test_extract_rejects_overlap_and_builds_argv():
    plan = ve.ExtractionPlan(
        source_media="in.mp4", output_wav="out.wav", start_s=1.0, end_s=2.5,
        exact_transcript="Hello", character_id="ALICE", overlapping_dialogue=True,
    )
    r = ve.extract_speaker_wav(plan, transcript_matches_script=True, dry_run=True)
    assert r.ok is False and "overlapping_dialogue" in r.rejection_reasons
    plan2 = ve.ExtractionPlan(
        source_media="in.mp4", output_wav="out.wav", start_s=1.0, end_s=2.5,
        exact_transcript="Hello", character_id="ALICE",
    )
    r2 = ve.extract_speaker_wav(plan2, transcript_matches_script=True, dry_run=True)
    assert r2.ok and r2.executed is False and "-ss" in r2.ffmpeg_argv

def main():
    tests = [test_policy_separates_machine_operator, test_extract_rejects_overlap_and_builds_argv]
    failed = 0
    for fn in tests:
        try:
            fn(); print("PASS", fn.__name__)
        except Exception as e:
            failed += 1; print("FAIL", fn.__name__, e)
    print("summary", {"ok": failed == 0, "failed": failed})
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
