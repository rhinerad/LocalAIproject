#!/usr/bin/env python3
"""Native MiniMax voice + transcript QA (diagnostic spectral features).

Spectral cosine alone must NOT authorize speaker identity when between-speaker
scores are high. Authorization requires similarity >= min AND optional
reference-contrast margin, plus transcript gates and audio-present flag.
"""
from __future__ import annotations

import math
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import numpy as np


class VoiceQAError(RuntimeError):
    pass


@dataclass
class VoiceQAThresholds:
    voice_similarity_min: float = 0.55
    voice_similarity_uncertain: float = 0.45
    transcript_exact: float = 1.0
    transcript_min: float = 0.85
    # Margin between same-speaker similarity and contrast (other speaker).
    # ALICE-vs-BOB spectral scores ~0.986 must FAIL identity authorization.
    speaker_margin_min: float = 0.05
    # below uncertain => fail; between uncertain and min => uncertain

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any] | None) -> "VoiceQAThresholds":
        obj = dict(obj or {})
        return cls(
            voice_similarity_min=float(obj.get("voice_similarity_min", 0.55)),
            voice_similarity_uncertain=float(obj.get("voice_similarity_uncertain", 0.45)),
            transcript_exact=float(obj.get("transcript_exact", 1.0)),
            transcript_min=float(obj.get("transcript_min", 0.85)),
            speaker_margin_min=float(obj.get("speaker_margin_min", 0.05)),
        )


@dataclass
class VoiceQAResult:
    ok: bool
    uncertain: bool
    voice_similarity: float | None
    transcript_score: float | None
    transcript_exact: bool | None
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    authorize_speaker_identity: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_transcript(text: str) -> str:
    import re
    t = str(text or "").lower().strip()
    t = re.sub(r"[^a-z0-9\s']", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def transcript_similarity(expected: str, actual: str) -> float:
    """Token Jaccard as a calibrated proxy when ASR text is available."""
    a = set(normalize_transcript(expected).split())
    b = set(normalize_transcript(actual).split())
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def transcript_exact_match(expected: str, actual: str) -> bool:
    return normalize_transcript(expected) == normalize_transcript(actual)


def _read_wav_mono(path: Path | str, target_sr: int = 16000) -> tuple[np.ndarray, int]:
    path = Path(path)
    if not path.is_file():
        raise VoiceQAError(f"missing wav: {path}")
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        ch = wf.getnchannels()
        sw = wf.getsampwidth()
        raw = wf.readframes(n)
    if sw == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        x = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise VoiceQAError(f"unsupported sample width {sw}")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != target_sr and len(x) > 1:
        duration = len(x) / float(sr)
        n_out = max(1, int(round(duration * target_sr)))
        xp = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        x = np.interp(x_new, xp, x).astype(np.float32)
        sr = target_sr
    return x, sr


def _log_mel_vector(x: np.ndarray, sr: int, n_mels: int = 40) -> np.ndarray:
    if len(x) < 256:
        x = np.pad(x, (0, 256 - len(x)))
    n_fft = 512
    hop = 256
    window = np.hanning(n_fft).astype(np.float32)
    frames = []
    for i in range(0, len(x) - n_fft + 1, hop):
        frame = x[i : i + n_fft] * window
        spec = np.abs(np.fft.rfft(frame))
        frames.append(spec)
    if not frames:
        frame = x[:n_fft]
        if len(frame) < n_fft:
            frame = np.pad(frame, (0, n_fft - len(frame)))
        frames = [np.abs(np.fft.rfft(frame * window))]
    mag = np.mean(np.stack(frames, axis=0), axis=0)
    freqs = np.linspace(0, sr / 2, num=len(mag))
    mel_edges = np.geomspace(max(1.0, freqs[1]), max(freqs[-1], 2.0), num=n_mels + 2)
    vec = np.zeros(n_mels, dtype=np.float32)
    for i in range(n_mels):
        lo, mid, hi = mel_edges[i], mel_edges[i + 1], mel_edges[i + 2]
        left = np.clip((freqs - lo) / max(mid - lo, 1e-6), 0, 1)
        right = np.clip((hi - freqs) / max(hi - mid, 1e-6), 0, 1)
        w = np.minimum(left, right)
        vec[i] = float(np.dot(mag, w) + 1e-8)
    vec = np.log(vec)
    nrm = float(np.linalg.norm(vec) + 1e-8)
    return vec / nrm


def voice_similarity(ref_wav: Path | str, hyp_wav: Path | str) -> float:
    """Cosine similarity of log-mel average vectors in [0,1] after shift.

    DIAGNOSTIC ONLY — not a calibrated production speaker-identity lock.
    """
    a, sr = _read_wav_mono(ref_wav)
    b, _ = _read_wav_mono(hyp_wav, target_sr=sr)
    va = _log_mel_vector(a, sr)
    vb = _log_mel_vector(b, sr)
    cos = float(np.dot(va, vb))
    return max(0.0, min(1.0, 0.5 * (cos + 1.0)))


def evaluate_voice_qa(
    *,
    reference_wav: Path | str | None,
    hypothesis_wav: Path | str | None,
    expected_transcript: str | None,
    actual_transcript: str | None,
    thresholds: VoiceQAThresholds | Mapping[str, Any] | None = None,
    require_voice: bool = True,
    require_transcript: bool = True,
    contrast_wav: Path | str | None = None,
    audio_stream_present: bool | None = None,
) -> VoiceQAResult:
    thr = (
        thresholds
        if isinstance(thresholds, VoiceQAThresholds)
        else VoiceQAThresholds.from_dict(thresholds)
    )
    reasons: list[str] = []
    metrics: dict[str, Any] = {
        "thresholds": thr.to_dict(),
        "spectral_is_diagnostic_only": True,
        "calibrated_production_lock": False,
    }
    vsim: float | None = None
    contrast_sim: float | None = None
    tscore: float | None = None
    texact: bool | None = None
    uncertain = False
    authorize = False

    if audio_stream_present is False:
        reasons.append("audio_stream_missing")

    if require_voice:
        if not reference_wav or not hypothesis_wav:
            reasons.append("missing_voice_wav")
        else:
            vsim = voice_similarity(reference_wav, hypothesis_wav)
            metrics["voice_similarity"] = vsim
            metrics["voice_similarity_diagnostic"] = vsim
            if vsim < thr.voice_similarity_uncertain:
                reasons.append("voice_similarity_fail")
            elif vsim < thr.voice_similarity_min:
                uncertain = True
                reasons.append("voice_similarity_uncertain")

            if contrast_wav:
                try:
                    contrast_sim = voice_similarity(reference_wav, contrast_wav)
                    # Also compare hypothesis to contrast (wrong speaker control).
                    hyp_vs_contrast = voice_similarity(hypothesis_wav, contrast_wav)
                    metrics["contrast_similarity_ref"] = contrast_sim
                    metrics["contrast_similarity_hyp"] = hyp_vs_contrast
                    # If hyp is as similar to contrast as to reference (within margin),
                    # fail wrong_speaker_control — spectral cannot discriminate.
                    if vsim is not None and hyp_vs_contrast >= (vsim - thr.speaker_margin_min):
                        reasons.append("wrong_speaker_control")
                        authorize = False
                    # If ref-vs-contrast is already extremely high, spectral alone
                    # cannot authorize identity even for same-speaker matches.
                    if contrast_sim is not None and contrast_sim >= (
                        thr.voice_similarity_min - 1e-9
                    ):
                        metrics["contrast_too_high_for_spectral_auth"] = True
                except VoiceQAError as exc:
                    reasons.append(f"contrast_wav_error:{exc}")
                    metrics["contrast_error"] = str(exc)

    if require_transcript:
        if expected_transcript is None or actual_transcript is None:
            reasons.append("missing_transcript")
        else:
            texact = transcript_exact_match(expected_transcript, actual_transcript)
            tscore = 1.0 if texact else transcript_similarity(expected_transcript, actual_transcript)
            metrics["transcript_score"] = tscore
            metrics["transcript_exact"] = texact
            if texact:
                pass
            elif tscore < thr.transcript_min:
                reasons.append("transcript_mismatch")
            else:
                uncertain = True
                reasons.append("transcript_uncertain")

    hard = [r for r in reasons if not r.endswith("_uncertain")]
    ok = not hard and not uncertain

    # Speaker identity authorization: stricter than diagnostic ok.
    # Requires: similarity >= min, transcript gates pass, audio present,
    # AND (contrast provided with adequate margin OR we refuse authorization).
    transcript_ok = (not require_transcript) or (
        "missing_transcript" not in reasons
        and "transcript_mismatch" not in reasons
        and "transcript_uncertain" not in reasons
    )
    voice_floor_ok = vsim is not None and vsim >= thr.voice_similarity_min
    audio_ok = audio_stream_present is not False
    contrast_ok = False
    if contrast_wav and vsim is not None and "wrong_speaker_control" not in reasons:
        hyp_vs_contrast = metrics.get("contrast_similarity_hyp")
        if hyp_vs_contrast is not None and (vsim - float(hyp_vs_contrast)) >= thr.speaker_margin_min:
            contrast_ok = True
        # If ref-vs-contrast is itself near ceiling, refuse auth (uncalibrated).
        cref = metrics.get("contrast_similarity_ref")
        if cref is not None and float(cref) >= 0.90:
            contrast_ok = False
            metrics["refused_auth_uncalibrated_spectral"] = True
    elif contrast_wav is None:
        # Without contrast, spectral alone never authorizes production identity.
        metrics["authorize_requires_contrast"] = True
        contrast_ok = False

    authorize = bool(
        voice_floor_ok
        and transcript_ok
        and audio_ok
        and contrast_ok
        and "wrong_speaker_control" not in reasons
        and not hard
    )
    metrics["authorize_speaker_identity"] = authorize

    if uncertain and not hard:
        ok = False
    # ok for overall QA may still be true for transcript+same-ref diagnostics,
    # but authorize_speaker_identity stays False without contrast margin.
    return VoiceQAResult(
        ok=ok,
        uncertain=uncertain and not hard,
        voice_similarity=vsim,
        transcript_score=tscore,
        transcript_exact=texact,
        reasons=reasons,
        metrics=metrics,
        authorize_speaker_identity=authorize,
    )
