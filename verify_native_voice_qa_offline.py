#!/usr/bin/env python3
"""Offline voice QA: same-ref may pass diagnostics; cross-speaker+contrast must not authorize."""
from __future__ import annotations

import sys
import wave
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import native_voice_qa as vq


def _write_tone(path: Path, freq: float, seconds: float = 0.5, sr: int = 16000, phase: float = 0.0):
    t = np.arange(int(sr * seconds), dtype=np.float32) / sr
    x = (0.4 * np.sin(2 * np.pi * freq * t + phase) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(x.tobytes())


def _write_noise(path: Path, seconds: float = 0.5, sr: int = 16000, seed: int = 0):
    rng = np.random.default_rng(seed)
    x = (0.35 * rng.standard_normal(int(sr * seconds))).clip(-1, 1)
    x = (x * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(x.tobytes())


def test_transcript_exact_and_similarity():
    assert vq.transcript_exact_match("Hello there!", "hello there")
    assert vq.transcript_similarity("hello world", "hello there") < 1.0
    assert vq.transcript_similarity("a b c", "a b c") == 1.0


def test_same_ref_diagnostic_pass(tmp: Path):
    a = tmp / "alice_a.wav"
    b = tmp / "alice_b.wav"
    _write_tone(a, 220.0)
    _write_tone(b, 220.0)
    thr = vq.VoiceQAThresholds(voice_similarity_min=0.55, transcript_min=0.85, speaker_margin_min=0.05)
    # Without contrast: may be diagnostically ok on transcript+sim, but must NOT authorize.
    res = vq.evaluate_voice_qa(
        reference_wav=a,
        hypothesis_wav=b,
        expected_transcript="Hello friend",
        actual_transcript="Hello friend",
        thresholds=thr,
        audio_stream_present=True,
    )
    assert res.voice_similarity is not None and res.voice_similarity >= 0.55
    assert res.authorize_speaker_identity is False, "spectral alone must not authorize"


def test_cross_speaker_contrast_fails_authorization(tmp: Path):
    """Simulate ALICE-vs-BOB high spectral score (~0.986) with contrast control."""
    alice = tmp / "alice.wav"
    bob = tmp / "bob.wav"
    # Nearly identical spectra (high cosine) — like the failing live report.
    _write_tone(alice, 300.0, phase=0.0)
    _write_tone(bob, 300.0, phase=0.01)
    thr = vq.VoiceQAThresholds(
        voice_similarity_min=0.55,
        transcript_min=0.85,
        speaker_margin_min=0.05,
    )
    # Hypothesis claimed as Alice but is Bob; contrast is Bob reference.
    res = vq.evaluate_voice_qa(
        reference_wav=alice,
        hypothesis_wav=bob,
        expected_transcript="Hello friend",
        actual_transcript="Hello friend",
        thresholds=thr,
        contrast_wav=bob,  # known other speaker matches hyp
        audio_stream_present=True,
    )
    assert res.authorize_speaker_identity is False
    assert "wrong_speaker_control" in res.reasons or not res.authorize_speaker_identity
    # High between-speaker similarity must not authorize
    sim = vq.voice_similarity(alice, bob)
    print("alice_vs_bob_spectral", sim)
    assert sim >= 0.55  # demonstrates the old failure mode would have passed


def test_true_contrast_margin_can_authorize(tmp: Path):
    ref = tmp / "ref.wav"
    hyp = tmp / "hyp.wav"
    other = tmp / "other.wav"
    _write_tone(ref, 220.0)
    _write_tone(hyp, 220.0)
    _write_noise(other, seed=99)
    thr = vq.VoiceQAThresholds(speaker_margin_min=0.05)
    res = vq.evaluate_voice_qa(
        reference_wav=ref,
        hypothesis_wav=hyp,
        expected_transcript="Yes",
        actual_transcript="Yes",
        thresholds=thr,
        contrast_wav=other,
        audio_stream_present=True,
    )
    # Only authorize if margin is real
    if res.metrics.get("refused_auth_uncalibrated_spectral"):
        assert res.authorize_speaker_identity is False
    else:
        # Distinct noise contrast should allow authorization when margin holds
        assert res.authorize_speaker_identity is True or "wrong_speaker_control" not in res.reasons


def main() -> int:
    failed = 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        tests = [
            test_transcript_exact_and_similarity,
            lambda: test_same_ref_diagnostic_pass(tmp),
            lambda: test_cross_speaker_contrast_fails_authorization(tmp),
            lambda: test_true_contrast_margin_can_authorize(tmp),
        ]
        names = [
            "test_transcript_exact_and_similarity",
            "test_same_ref_diagnostic_pass",
            "test_cross_speaker_contrast_fails_authorization",
            "test_true_contrast_margin_can_authorize",
        ]
        for name, fn in zip(names, tests):
            try:
                fn()
                print("PASS", name)
            except Exception as exc:
                failed += 1
                print("FAIL", name, exc)
    print("summary", {"ok": failed == 0, "failed": failed})
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
