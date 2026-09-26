"""M6: dialogue, lip-sync, repair, assembly, character bible, quality gates."""
from __future__ import annotations

import hashlib
import json
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import GvdLayout
from .schema import ArtifactRef, require_sha256, sha256_bytes, sha256_json


@dataclass(frozen=True)
class DialogueAsset:
    speaker_id: str
    transcript: str
    sample_rate: int
    wav_sha256: str
    duration_s: float
    timing: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class RepairRequest:
    source: ArtifactRef
    start_frame: int
    end_frame: int
    handle_frames: int
    mask_track: ArtifactRef | None
    desired_change: str
    protected_regions: tuple[str, ...]


def store_dialogue(
    layout: GvdLayout,
    *,
    project: str,
    shot: str,
    wav_path: Path,
    speaker_id: str,
    transcript: str,
    timing: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    data = Path(wav_path).read_bytes()
    digest = sha256_bytes(data)
    dest_dir = layout.job_dir(project, shot, "dialogue")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{digest}.wav"
    if not dest.exists():
        dest.write_bytes(data)
    rate = 0
    frames = 0
    try:
        with wave.open(str(wav_path), "rb") as handle:
            rate = handle.getframerate()
            frames = handle.getnframes()
    except Exception:
        pass
    duration = (frames / rate) if rate else 0.0
    record = {
        "speaker_id": speaker_id,
        "transcript": transcript,
        "sample_rate": rate,
        "wav_sha256": digest,
        "duration_s": duration,
        "timing": timing or [],
        "path": str(dest),
        "provider": "adapter_required",
        "note": "F5-TTS is registered adapter_required; this stores authorized references only",
    }
    (dest_dir / "dialogue.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def synthesize_dialogue(args: dict[str, Any], layout: GvdLayout) -> dict[str, Any]:
    """Local F5 adapter is not an executable Comfy template yet."""
    return {
        "status": "blocked",
        "reason_codes": ["UNAVAILABLE_CAPABILITY", "adapter_required:f5_tts"],
        "tool_name": "synthesize_dialogue",
        "note": "Would call a pinned local F5 service under the GPU lease; no generic shell.",
    }


def apply_lipsync(args: dict[str, Any], layout: GvdLayout) -> dict[str, Any]:
    return {
        "status": "blocked",
        "reason_codes": ["UNAVAILABLE_CAPABILITY", "blocked_missing_nodes:musetalk"],
        "tool_name": "apply_lipsync",
        "note": "MuseTalk is not installed. Sonic/other voice nodes are not substitutes.",
    }


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repair_video(args: dict[str, Any], layout: GvdLayout) -> dict[str, Any]:
    """Fail closed until a local ProPainter profile exists. Preserve source bytes."""
    source = args.get("source_path")
    if source:
        src = Path(str(source))
        if src.is_file():
            digest = _hash_file(src)
            dest = layout.job_dir(str(args.get("project") or "default"), str(args.get("shot_id") or "S01"), "repair")
            dest.mkdir(parents=True, exist_ok=True)
            copy = dest / f"source_{digest}{src.suffix}"
            if not copy.exists():
                copy.write_bytes(src.read_bytes())
            (dest / "repair_request.json").write_text(json.dumps({
                "source_sha256": digest,
                "start_frame": args.get("start_frame"),
                "end_frame": args.get("end_frame"),
                "handle_frames": args.get("handle_frames", 8),
                "desired_change": args.get("desired_change"),
                "protected_regions": args.get("protected_regions") or [],
            }, indent=2), encoding="utf-8")
    return {
        "status": "blocked",
        "reason_codes": ["UNAVAILABLE_CAPABILITY", "blocked_pending_local_profile:propainter"],
        "tool_name": "repair_video",
        "note": "ProPainter nodes may be installed; no local VRAM profile, so no production submit.",
        "preserved_source": True,
    }


def assemble_scene(
    layout: GvdLayout,
    *,
    project: str,
    shots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Narrative-order EDL. Generation order is ignored."""
    ordered = sorted(shots, key=lambda s: int(s.get("edit_index") or 0))
    edl = []
    cursor = 0
    for shot in ordered:
        frames = int(shot.get("actual_frames") or 0)
        edl.append({
            "shot_id": shot.get("shot_id"),
            "start_frame": cursor,
            "end_frame": cursor + frames,
            "artifact": shot.get("artifact"),
            "audio_cue_sample": shot.get("audio_cue_sample"),
        })
        cursor += frames
    receipt = {
        "project": project,
        "total_frames": cursor,
        "edl": edl,
        "order": "narrative",
        "vhs_overlay": False,
    }
    dest = layout.jobs / project / "_assembly"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "edl.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def persist_character_state(layout: GvdLayout, character_id: str, revision: str, state: dict[str, Any]) -> Path:
    dest = layout.character_dir(character_id, revision)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "approved_state.json"
    if path.exists():
        raise ValueError("character revision is immutable")
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def quality_gate(
    *,
    requested_duration_s: float,
    actual_duration_s: float,
    tolerance_s: float,
    protected_before: str | None = None,
    protected_after: str | None = None,
) -> dict[str, Any]:
    reasons = []
    if abs(actual_duration_s - requested_duration_s) > tolerance_s:
        reasons.append("duration_out_of_tolerance")
    if protected_before and protected_after and protected_before != protected_after:
        reasons.append("protected_region_changed")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "note": "automatic metrics nominate failures; they do not certify human quality",
    }
