#!/usr/bin/env python3
"""Clean speaker-segment extraction for native MiniMax voice bootstrap."""
from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


class VoiceExtractError(RuntimeError):
    pass


@dataclass
class ExtractionPlan:
    source_media: str
    output_wav: str
    start_s: float
    end_s: float
    sample_rate: int = 32000
    mono: bool = True
    exact_transcript: str = ""
    character_id: str = ""
    speaker_attribution_ok: bool = True
    overlapping_dialogue: bool = False
    unusable_noise: bool = False
    leaked_music: bool = False

    def duration_s(self) -> float:
        return float(self.end_s) - float(self.start_s)


@dataclass
class ExtractionResult:
    ok: bool
    output_wav: str | None
    rejection_reasons: list[str] = field(default_factory=list)
    start_sample: int = 0
    end_sample: int = 0
    ffmpeg_argv: list[str] = field(default_factory=list)
    executed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def rejection_reasons(plan: ExtractionPlan, *, transcript_matches_script: bool) -> list[str]:
    reasons: list[str] = []
    if plan.duration_s() <= 0.05:
        reasons.append("segment_too_short")
    if not plan.speaker_attribution_ok:
        reasons.append("ambiguous_speaker_attribution")
    if plan.overlapping_dialogue:
        reasons.append("overlapping_dialogue")
    if plan.unusable_noise:
        reasons.append("unusable_noise")
    if plan.leaked_music:
        reasons.append("leaked_music")
    if not str(plan.exact_transcript or "").strip():
        reasons.append("missing_transcript")
    if not transcript_matches_script:
        reasons.append("transcript_mismatch")
    if not plan.character_id:
        reasons.append("missing_character_id")
    return reasons


def build_ffmpeg_extract_argv(plan: ExtractionPlan) -> list[str]:
    if plan.end_s <= plan.start_s:
        raise VoiceExtractError("end_s must be > start_s")
    argv = [
        "ffmpeg", "-y",
        "-ss", f"{plan.start_s:.3f}",
        "-to", f"{plan.end_s:.3f}",
        "-i", str(plan.source_media),
        "-vn",
        "-ac", "1" if plan.mono else "2",
        "-ar", str(int(plan.sample_rate)),
        "-c:a", "pcm_s16le",
        str(plan.output_wav),
    ]
    return argv


def extract_speaker_wav(
    plan: ExtractionPlan,
    *,
    transcript_matches_script: bool = True,
    dry_run: bool = False,
) -> ExtractionResult:
    reasons = rejection_reasons(plan, transcript_matches_script=transcript_matches_script)
    if reasons:
        return ExtractionResult(ok=False, output_wav=None, rejection_reasons=reasons)
    argv = build_ffmpeg_extract_argv(plan)
    start_sample = int(round(plan.start_s * plan.sample_rate))
    end_sample = int(round(plan.end_s * plan.sample_rate))
    if dry_run:
        return ExtractionResult(
            ok=True,
            output_wav=str(plan.output_wav),
            start_sample=start_sample,
            end_sample=end_sample,
            ffmpeg_argv=argv,
            executed=False,
        )
    Path(plan.output_wav).parent.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(argv, capture_output=True, text=True, timeout=300)
    if cp.returncode != 0:
        return ExtractionResult(
            ok=False,
            output_wav=None,
            rejection_reasons=["ffmpeg_failed"],
            ffmpeg_argv=argv,
            executed=True,
        )
    if not Path(plan.output_wav).is_file() or Path(plan.output_wav).stat().st_size < 44:
        return ExtractionResult(
            ok=False,
            output_wav=None,
            rejection_reasons=["empty_output"],
            ffmpeg_argv=argv,
            executed=True,
        )
    return ExtractionResult(
        ok=True,
        output_wav=str(plan.output_wav),
        start_sample=start_sample,
        end_sample=end_sample,
        ffmpeg_argv=argv,
        executed=True,
    )
