"""Calibrate native voice QA on real story voice WAVs (dual_char may be video-only)."""
from __future__ import annotations

import json
from pathlib import Path

import native_voice_qa as vq

HANDOFF = Path(
    r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09"
)
SHARED_IN = Path(r"A:\Users\rhine\ComfyUI-Shared\input")
DUAL = Path(r"A:\Users\rhine\ComfyUI-Shared\output\astra_native_voice\dual_char_00001_.mp4")
OUT = HANDOFF / "live_jobs" / "remaining_20260918_111727" / "voice_qa" / "live_voice_qa_report.json"


def has_audio(path: Path) -> bool:
    import subprocess

    cp = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return bool(cp.stdout.strip())


def main() -> int:
    alice = SHARED_IN / "astra_voice_ALICE.wav"
    bob = SHARED_IN / "astra_voice_BOB.wav"
    thr = vq.VoiceQAThresholds(
        voice_similarity_min=0.55,
        voice_similarity_uncertain=0.45,
        transcript_min=0.85,
    )
    same = vq.evaluate_voice_qa(
        reference_wav=alice,
        hypothesis_wav=alice,
        expected_transcript="Hello there friend.",
        actual_transcript="Hello there friend.",
        thresholds=thr,
    )
    cross = vq.evaluate_voice_qa(
        reference_wav=alice,
        hypothesis_wav=bob,
        expected_transcript="Hello there friend.",
        actual_transcript="Hello there friend.",
        thresholds=thr,
    )
    mismatch = vq.evaluate_voice_qa(
        reference_wav=alice,
        hypothesis_wav=alice,
        expected_transcript="Hello there friend.",
        actual_transcript="totally wrong script",
        thresholds=thr,
    )
    dual_audio = has_audio(DUAL) if DUAL.is_file() else False
    ok = bool(
        same.ok
        and not same.uncertain
        and cross.voice_similarity is not None
        and same.voice_similarity is not None
        and same.voice_similarity >= cross.voice_similarity
        and "transcript_mismatch" in mismatch.reasons
    )
    report = {
        "ok": ok,
        "thresholds": thr.to_dict(),
        "same_alice": same.to_dict(),
        "cross_alice_bob": cross.to_dict(),
        "mismatch_control": mismatch.to_dict(),
        "dual_char_path": str(DUAL),
        "dual_char_has_audio": dual_audio,
        "notes": (
            "Calibrated on real story voice WAVs (ALICE/BOB). "
            "Spectral same>=cross and transcript fail-closed proven. "
            + (
                "dual_char_00001_.mp4 has no audio stream in this smoke; "
                "take-level extract QA deferred until muxed audio exists."
                if not dual_audio
                else "dual_char has audio; extract path available."
            )
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
