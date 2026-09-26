#!/usr/bin/env python3
"""Audio timeline model + modes (audit §10).

Stems stay conceptually separate. Timing uses integer frame/sample fields
with fixed editorial rate: 24 fps ↔ 48 kHz = 2000 samples/frame.

Offline-safe. No ComfyUI / GPU / network / TTS invocation.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

FPS = 24
SAMPLE_RATE_HZ = 48_000
SAMPLES_PER_FRAME = SAMPLE_RATE_HZ // FPS  # 2000

assert SAMPLE_RATE_HZ % FPS == 0
assert SAMPLES_PER_FRAME == 2000


class AudioMode(str, Enum):
    """Per-shot audio modes. Silence only when intentional."""
    NARRATION_OVER_PICTURE = "narration_over_picture"
    VISIBLE_DIALOGUE = "visible_dialogue"
    NATIVE_H3_AUDIO = "native_h3_audio"
    SILENT_ABSTRACT = "silent_abstract"


AUDIO_MODES = frozenset(m.value for m in AudioMode)

STEM_KINDS = frozenset({"narration", "dialogue", "ambience", "music", "fx"})


class AudioTimelineError(ValueError):
    """Raised on timeline / mode gate failures."""


@dataclass
class VoiceAssetRecord:
    """Versioned voice asset — replaces shared C001-style voice assumption."""
    job_id: str
    speaker_id: str
    voice_version: str
    reference_audio_hash: str
    reference_transcript_hash: str
    tts_backend: str
    checkpoint_hash: str
    language: str = "en"
    delivery_params: dict[str, Any] = field(default_factory=dict)
    asset_id: str | None = None

    def __post_init__(self) -> None:
        if not self.job_id or not self.speaker_id or not self.voice_version:
            raise AudioTimelineError("job_id, speaker_id, voice_version required")
        if not self.reference_audio_hash or not self.reference_transcript_hash:
            raise AudioTimelineError("reference audio/transcript hashes required")
        if not self.tts_backend or not self.checkpoint_hash:
            raise AudioTimelineError("tts_backend and checkpoint_hash required")
        if self.asset_id is None:
            self.asset_id = (
                f"voice:{self.job_id}:{self.speaker_id}@{self.voice_version}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "VoiceAssetRecord":
        return cls(
            job_id=str(obj["job_id"]),
            speaker_id=str(obj["speaker_id"]),
            voice_version=str(obj["voice_version"]),
            reference_audio_hash=str(obj["reference_audio_hash"]),
            reference_transcript_hash=str(obj["reference_transcript_hash"]),
            tts_backend=str(obj["tts_backend"]),
            checkpoint_hash=str(obj["checkpoint_hash"]),
            language=str(obj.get("language") or "en"),
            delivery_params=dict(obj.get("delivery_params") or {}),
            asset_id=(str(obj["asset_id"]) if obj.get("asset_id") else None),
        )


@dataclass
class DialogueLineRecord:
    """Dialogue stored separately from voice assets: speaker_id + exact text."""
    speaker_id: str
    text: str
    voice_asset_id: str | None = None
    line_id: str | None = None

    def __post_init__(self) -> None:
        if not self.speaker_id:
            raise AudioTimelineError("dialogue speaker_id required")
        if not str(self.text or "").strip():
            raise AudioTimelineError("dialogue text required")
        self.text = str(self.text).strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "DialogueLineRecord":
        return cls(
            speaker_id=str(obj.get("speaker_id") or obj.get("speaker") or ""),
            text=str(obj.get("text") or ""),
            voice_asset_id=(
                str(obj["voice_asset_id"]) if obj.get("voice_asset_id") else None
            ),
            line_id=(str(obj["line_id"]) if obj.get("line_id") else None),
        )


@dataclass
class AudioStem:
    """One stem on the timeline (narration / dialogue / ambience / music / fx)."""
    kind: str
    start_frame: int
    end_frame: int
    start_sample: int | None = None
    end_sample: int | None = None
    path: str | None = None
    content_hash: str | None = None
    gain_db: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in STEM_KINDS:
            raise AudioTimelineError(
                f"unknown stem kind {self.kind!r}; expected {sorted(STEM_KINDS)}"
            )
        if self.start_frame < 0 or self.end_frame < self.start_frame:
            raise AudioTimelineError("stem frame range invalid")
        if self.start_sample is None:
            self.start_sample = frames_to_samples(self.start_frame)
        if self.end_sample is None:
            self.end_sample = frames_to_samples(self.end_frame)
        # Alignment check
        if self.start_sample != frames_to_samples(self.start_frame):
            raise AudioTimelineError("start_sample misaligned with start_frame")
        if self.end_sample != frames_to_samples(self.end_frame):
            raise AudioTimelineError("end_sample misaligned with end_frame")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "AudioStem":
        return cls(
            kind=str(obj["kind"]),
            start_frame=int(obj["start_frame"]),
            end_frame=int(obj["end_frame"]),
            start_sample=(int(obj["start_sample"]) if obj.get("start_sample") is not None else None),
            end_sample=(int(obj["end_sample"]) if obj.get("end_sample") is not None else None),
            path=(str(obj["path"]) if obj.get("path") else None),
            content_hash=(str(obj["content_hash"]) if obj.get("content_hash") else None),
            gain_db=float(obj.get("gain_db") or 0.0),
            meta=dict(obj.get("meta") or {}),
        )


@dataclass
class ShotAudioPlan:
    """Per-shot audio mode + optional dialogue / stems."""
    shot_id: str
    mode: str
    dialogue_lines: list[DialogueLineRecord] = field(default_factory=list)
    stems: list[AudioStem] = field(default_factory=list)
    voice_asset_ids: list[str] = field(default_factory=list)
    intentional_silence: bool = False

    def __post_init__(self) -> None:
        if self.mode not in AUDIO_MODES:
            raise AudioTimelineError(
                f"unknown audio mode {self.mode!r}; expected {sorted(AUDIO_MODES)}"
            )
        gate_shot_audio_mode(
            mode=self.mode,
            dialogue_lines=self.dialogue_lines,
            intentional_silence=self.intentional_silence,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "mode": self.mode,
            "dialogue_lines": [d.to_dict() for d in self.dialogue_lines],
            "stems": [s.to_dict() for s in self.stems],
            "voice_asset_ids": list(self.voice_asset_ids),
            "intentional_silence": self.intentional_silence,
        }

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "ShotAudioPlan":
        return cls(
            shot_id=str(obj["shot_id"]),
            mode=str(obj["mode"]),
            dialogue_lines=[
                DialogueLineRecord.from_dict(x) for x in (obj.get("dialogue_lines") or [])
            ],
            stems=[AudioStem.from_dict(x) for x in (obj.get("stems") or [])],
            voice_asset_ids=[str(x) for x in (obj.get("voice_asset_ids") or [])],
            intentional_silence=bool(obj.get("intentional_silence", False)),
        )


@dataclass
class AudioTimeline:
    """Job-level timeline: voice assets + per-shot plans + stems."""
    job_id: str
    fps: int = FPS
    sample_rate_hz: int = SAMPLE_RATE_HZ
    voice_assets: dict[str, VoiceAssetRecord] = field(default_factory=dict)
    shots: dict[str, ShotAudioPlan] = field(default_factory=dict)

    def register_voice(self, voice: VoiceAssetRecord) -> VoiceAssetRecord:
        if voice.job_id != self.job_id:
            raise AudioTimelineError(
                f"voice job_id {voice.job_id!r} != timeline job_id {self.job_id!r}"
            )
        assert voice.asset_id is not None
        self.voice_assets[voice.asset_id] = voice
        return voice

    def set_shot_plan(self, plan: ShotAudioPlan) -> ShotAudioPlan:
        self.shots[plan.shot_id] = plan
        return plan

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "fps": self.fps,
            "sample_rate_hz": self.sample_rate_hz,
            "samples_per_frame": samples_per_frame(self.fps, self.sample_rate_hz),
            "voice_assets": {k: v.to_dict() for k, v in self.voice_assets.items()},
            "shots": {k: v.to_dict() for k, v in self.shots.items()},
        }

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "AudioTimeline":
        tl = cls(
            job_id=str(obj["job_id"]),
            fps=int(obj.get("fps") or FPS),
            sample_rate_hz=int(obj.get("sample_rate_hz") or SAMPLE_RATE_HZ),
        )
        for raw in (obj.get("voice_assets") or {}).values():
            tl.register_voice(VoiceAssetRecord.from_dict(raw))
        for raw in (obj.get("shots") or {}).values():
            tl.set_shot_plan(ShotAudioPlan.from_dict(raw))
        return tl


# --- math helpers ----------------------------------------------------------

def samples_per_frame(fps: int = FPS, sample_rate_hz: int = SAMPLE_RATE_HZ) -> int:
    if fps <= 0 or sample_rate_hz <= 0:
        raise AudioTimelineError("fps and sample_rate_hz must be positive")
    if sample_rate_hz % fps != 0:
        raise AudioTimelineError(
            f"sample_rate {sample_rate_hz} not divisible by fps {fps}"
        )
    return sample_rate_hz // fps


def frames_to_samples(frames: int, *, fps: int = FPS, sample_rate_hz: int = SAMPLE_RATE_HZ) -> int:
    if isinstance(frames, bool) or not isinstance(frames, int):
        raise AudioTimelineError("frames must be int")
    if frames < 0:
        raise AudioTimelineError("frames must be >= 0")
    return frames * samples_per_frame(fps, sample_rate_hz)


def samples_to_frames(samples: int, *, fps: int = FPS, sample_rate_hz: int = SAMPLE_RATE_HZ) -> int:
    if isinstance(samples, bool) or not isinstance(samples, int):
        raise AudioTimelineError("samples must be int")
    if samples < 0:
        raise AudioTimelineError("samples must be >= 0")
    spf = samples_per_frame(fps, sample_rate_hz)
    if samples % spf != 0:
        raise AudioTimelineError(
            f"samples {samples} not aligned to {spf} samples/frame"
        )
    return samples // spf


def assert_frame_sample_alignment(
    frames: int,
    samples: int,
    *,
    fps: int = FPS,
    sample_rate_hz: int = SAMPLE_RATE_HZ,
) -> None:
    expected = frames_to_samples(frames, fps=fps, sample_rate_hz=sample_rate_hz)
    if samples != expected:
        raise AudioTimelineError(
            f"misaligned: {frames} frames → {expected} samples, got {samples}"
        )


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- gates -----------------------------------------------------------------

def gate_shot_audio_mode(
    *,
    mode: str,
    dialogue_lines: Iterable[DialogueLineRecord] | Iterable[Mapping[str, Any]] | None,
    intentional_silence: bool = False,
) -> None:
    """Fail closed: required dialogue + silent mode is a conflict.

    Silence is allowed only for ``silent_abstract`` when intentional_silence=True
    and there are no dialogue lines.
    """
    mode_s = str(mode)
    if mode_s not in AUDIO_MODES:
        raise AudioTimelineError(f"unknown audio mode {mode_s!r}")

    lines: list[Any] = list(dialogue_lines or [])
    has_dialogue = False
    for item in lines:
        if isinstance(item, DialogueLineRecord):
            if item.text.strip():
                has_dialogue = True
                break
        elif isinstance(item, Mapping):
            if str(item.get("text") or "").strip():
                has_dialogue = True
                break
        elif isinstance(item, str) and item.strip():
            has_dialogue = True
            break

    if mode_s == AudioMode.SILENT_ABSTRACT.value:
        if has_dialogue:
            raise AudioTimelineError(
                "required dialogue + silent_abstract mode conflict"
            )
        if not intentional_silence:
            raise AudioTimelineError(
                "silent_abstract requires intentional_silence=True"
            )
        return

    if intentional_silence and mode_s != AudioMode.SILENT_ABSTRACT.value:
        raise AudioTimelineError(
            "intentional_silence only valid with silent_abstract mode"
        )

    if mode_s in {
        AudioMode.VISIBLE_DIALOGUE.value,
        AudioMode.NARRATION_OVER_PICTURE.value,
    } and not has_dialogue:
        raise AudioTimelineError(
            f"mode {mode_s} requires at least one dialogue/narration line"
        )
