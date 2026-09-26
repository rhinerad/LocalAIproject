#!/usr/bin/env python3
"""Sequential prompt-pack batch runner (style-profile driven).

Conservative by design:
* Never imports generate_video.py — each clip is a fresh child process.
* Resumable via progress.json + clip JSON; resume-skip requires SELECTED/verified.
* Resolves frame handoff notes like "Use Last Frame of C001" to SELECTED media only.
* P1: optional style profile (no hardcoded Backrooms/VHS on generic path),
  SQLite production_store attempts, SELECTED-only media resolution.

Default managed task:
    local_agent/runtime/managed_tasks/backrooms_sitcom_pack_20260917

Dry plan:
    python master_batch_runner.py --dry-run --limit 1 --style-profile backrooms_sitcom
"""
from __future__ import annotations

try:
    import native_voice_continuity as _nvc
    _HAS_NATIVE_VOICE = True
except Exception:
    _HAS_NATIVE_VOICE = False


import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STYLE_PROFILES_DIR = ROOT / "style_profiles"
DEFAULT_STYLE_PROFILE = "generic"
PRODUCTION_DB_NAME = "production_attempts.sqlite3"
DEFAULT_TASK_DIR = (
    ROOT / "local_agent" / "runtime" / "managed_tasks" / "backrooms_sitcom_pack_20260917"
)
DEFAULT_GENERATOR = ROOT / "generate_video.py"
RUNNER_VERSION = "2026-09-22-master-batch-runner-literal-dryrun"
OVERRIDES_DIR = ROOT / "clip_overrides"
PACK_DIALOGUE_MD = ROOT / "Backrooms_Sitcom_Audition_Prompt_Pack_MERGED_FINAL.md"
TAGGED_DIALOGUE_RE = re.compile(
    r"<d>(?:\[.*?\])?\s*(.*?)</d>",
    flags=re.IGNORECASE | re.DOTALL,
)
_PACK_MD_CACHE: str | None = None
VIDEO_PATH_PATTERNS = [
    re.compile(r"Done\.\s*Clip\s+at:\s*\r?\n\s*(?P<path>.+?\.mp4)\s*$", re.I | re.M),
    re.compile(r"\bvideo\s*=\s*(?P<path>.+?\.mp4)\s*$", re.I | re.M),
]
FRAME_REF_RE = re.compile(
    r"(?:use\s+)?(?:(?P<kind>start|last)\s+frame\s+(?:of|from)\s+)?(?P<clip>C\d{3})",
    re.I,
)

try:
    from production_store import (
        connect as store_connect,
        create_attempt,
        set_attempt_state,
        get_selected_artifact_path,
        get_selected_attempt,
        export_progress_view,
        sha256_file,
    )
    _HAS_STORE = True
except Exception:  # pragma: no cover
    _HAS_STORE = False
    store_connect = None  # type: ignore
    create_attempt = None  # type: ignore
    set_attempt_state = None  # type: ignore
    get_selected_artifact_path = None  # type: ignore
    get_selected_attempt = None  # type: ignore
    export_progress_view = None  # type: ignore
    sha256_file = None  # type: ignore


try:
    from canonical_assets import (
        AssetRegistry,
        build_continuity_bind_plan,
        edit_strategy,
        parent_switch_invalidates_child,
        record_boundary_from_png,
    )
    from audio_timeline import (
        AudioMode,
        AudioTimeline,
        DialogueLineRecord,
        ShotAudioPlan,
        VoiceAssetRecord,
        frames_to_samples,
        gate_shot_audio_mode,
    )
    _HAS_ASSETS_AUDIO = True
except Exception:  # pragma: no cover
    _HAS_ASSETS_AUDIO = False
    AssetRegistry = None  # type: ignore
    build_continuity_bind_plan = None  # type: ignore
    edit_strategy = None  # type: ignore
    parent_switch_invalidates_child = None  # type: ignore
    record_boundary_from_png = None  # type: ignore
    AudioMode = None  # type: ignore
    AudioTimeline = None  # type: ignore
    DialogueLineRecord = None  # type: ignore
    ShotAudioPlan = None  # type: ignore
    VoiceAssetRecord = None  # type: ignore
    frames_to_samples = None  # type: ignore
    gate_shot_audio_mode = None  # type: ignore




def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return value


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def load_style_profile(
    profile: str | Path | dict | None = None,
    *,
    env_var: str = "GVD_STYLE_PROFILE",
) -> dict:
    """Load optional project style profile. Generic path has no genre hardcoding."""
    if isinstance(profile, dict):
        return dict(profile)
    raw = profile
    if raw is None or raw == "":
        raw = os.environ.get(env_var) or DEFAULT_STYLE_PROFILE
    p = Path(str(raw))
    candidates: list[Path] = []
    if p.suffix.lower() == ".json":
        candidates.append(p if p.is_absolute() else (ROOT / p))
        candidates.append(STYLE_PROFILES_DIR / p.name)
    else:
        candidates.append(STYLE_PROFILES_DIR / f"{raw}.json")
    for cand in candidates:
        if cand.is_file():
            data = json.loads(cand.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"style profile must be a JSON object: {cand}")
            data.setdefault("_profile_path", str(cand))
            return data
    return {
        "profile_id": "generic",
        "display_name": "Generic",
        "category": "generic",
        "intent_prefix": "",
        "constraints": ["No text, no watermark, no UI overlay."],
        "focus": "scene, motion_smoothness",
        "vhs_finishing": {"enabled": False, "rec_overlay": False},
        "backend_profile": "h3_distilled",
        "quality_tier_default": "standard",
        "motion_complexity_default": "moderate",
    }


def open_production_store(task_dir: Path, db_path: Path | None = None):
    if not _HAS_STORE or store_connect is None:
        return None
    return store_connect(db_path or (task_dir / PRODUCTION_DB_NAME))


def clip_json_path(task_dir: Path, clip_id: str) -> Path:
    return task_dir / "clips" / f"{clip_id}.json"


def clip_ids_from_progress(progress: dict[str, Any]) -> list[str]:
    ids = progress.get("clip_ids") or []
    return [str(x).upper() for x in ids if str(x).strip()]


def existing_file(path_text: Any) -> Path | None:
    if not path_text:
        return None
    try:
        path = Path(str(path_text).strip().strip('"'))
    except Exception:
        return None
    if not path.is_absolute():
        path = ROOT / path
    try:
        if path.is_file() and path.stat().st_size > 0:
            return path
    except OSError:
        return None
    return None


def recorded_video_path(clip: dict[str, Any]) -> Path | None:
    state = clip.get("master_batch") or {}
    if not isinstance(state, dict):
        return None
    for key in ("video_path", "output_video", "mp4_path"):
        found = existing_file(state.get(key))
        if found:
            return found
    return None


SELECTED_STATUSES = frozenset({"selected", "verified", "qa_passed", "complete_verified"})


def is_clip_selected(clip: dict[str, Any]) -> bool:
    """Resume acceptance: require QA/verified selection, not merely nonempty MP4."""
    state = clip.get("master_batch") or {}
    if not isinstance(state, dict):
        return False
    status = str(state.get("status") or "").lower()
    pipeline_state = str(state.get("pipeline_state") or state.get("state") or "").upper()
    if pipeline_state == "SELECTED":
        return recorded_video_path(clip) is not None
    if status in SELECTED_STATUSES:
        return recorded_video_path(clip) is not None
    if status in {"complete", "done", "rendered"}:
        qa = state.get("qa") or state.get("vlm_qa") or {}
        if isinstance(qa, dict) and qa.get("pass") is True and state.get("verified"):
            return recorded_video_path(clip) is not None
        if state.get("verified") is True and recorded_video_path(clip) is not None:
            return True
        return False
    return False


def is_clip_complete(clip: dict[str, Any]) -> bool:
    return is_clip_selected(clip)


def parse_clip_number(clip_id: str) -> int:
    match = re.search(r"(\d+)", clip_id)
    return int(match.group(1)) if match else -1


def previous_clip_id(clip_id: str, clip_ids: list[str]) -> str | None:
    try:
        index = clip_ids.index(clip_id)
    except ValueError:
        return None
    if index <= 0:
        return None
    return clip_ids[index - 1]


def load_clip(task_dir: Path, clip_id: str) -> dict[str, Any]:
    return read_json(clip_json_path(task_dir, clip_id))


def get_completed_media(
    task_dir: Path,
    clip_id: str,
    *,
    db=None,
    require_selected: bool = True,
) -> Path | None:
    """Resolve completed media ONLY via SELECTED attempt / SELECTED state (P1-G)."""
    if db is not None and _HAS_STORE:
        try:
            art = get_selected_artifact_path(db, clip_id)
            found = existing_file(art) if art else None
            if found:
                return found
            sel = get_selected_attempt(db, clip_id)
            if sel is not None:
                return existing_file(sel["artifact_path"]) if sel["artifact_path"] else None
        except Exception:
            pass

    path = clip_json_path(task_dir, clip_id)
    if path.is_file():
        try:
            clip = read_json(path)
            if require_selected and not is_clip_selected(clip):
                return None
            found = recorded_video_path(clip)
            if found:
                return found
        except Exception:
            pass

    if require_selected:
        return None

    output_dir = task_dir / "outputs"
    if output_dir.exists():
        candidates = sorted(
            output_dir.rglob(f"*{clip_id}*.mp4"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        )
        for candidate in candidates:
            found = existing_file(candidate)
            if found:
                return found
    return None


def resolve_frame_reference(
    *,
    task_dir: Path,
    clip_ids: list[str],
    current_clip_id: str,
    field_text: str,
    preferred_kind: str,
    db=None,
) -> tuple[Path | None, str]:
    text = str(field_text or "")
    match = FRAME_REF_RE.search(text)
    referenced_clip = None
    referenced_kind = preferred_kind
    if match:
        referenced_clip = match.group("clip").upper()
        if match.group("kind"):
            referenced_kind = match.group("kind").lower()
    else:
        lower = text.lower()
        if "previous" in lower or "prior clip" in lower or "last frame" in lower:
            referenced_clip = previous_clip_id(current_clip_id, clip_ids)

    if not referenced_clip:
        return None, "no explicit prior-frame reference"

    try:
        referenced = load_clip(task_dir, referenced_clip)
    except Exception as exc:
        return None, f"{referenced_clip} could not be loaded: {exc}"

    state = referenced.get("master_batch") or {}
    if isinstance(state, dict) and is_clip_selected(referenced):
        for key in (
            f"{referenced_kind}_frame_path",
            "last_frame_path",
            "start_frame_path",
            "video_path",
            "output_video",
        ):
            found = existing_file(state.get(key))
            if found:
                return found, f"resolved {referenced_kind} frame reference to {referenced_clip}:{key}"

    found = get_completed_media(task_dir, referenced_clip, db=db, require_selected=True)
    if found:
        return found, f"resolved {referenced_kind} frame reference to SELECTED media for {referenced_clip}"

    return None, f"{referenced_clip} is referenced but no SELECTED media is recorded yet"



def resolve_clip_audio_mode(clip: dict[str, Any]) -> str | None:
    """Return per-shot audio mode from clip if present (audit §10)."""
    raw = clip.get("audio_mode")
    if raw is None and isinstance(clip.get("audio"), dict):
        raw = clip["audio"].get("mode")
    if raw is None:
        return None
    return str(raw).strip() or None


def continuity_parent_still_valid(
    *,
    bound_parent_attempt_id: str | None,
    current_selected_parent_attempt_id: str | None,
) -> bool:
    """False when intentional parent SELECTED switch invalidates the child."""
    if not _HAS_ASSETS_AUDIO or parent_switch_invalidates_child is None:
        if not bound_parent_attempt_id:
            return True
        return bound_parent_attempt_id == current_selected_parent_attempt_id
    return not parent_switch_invalidates_child(
        bound_parent_attempt_id=bound_parent_attempt_id,
        current_selected_parent_attempt_id=current_selected_parent_attempt_id,
    )


def extract_tagged_dialogue(text: str) -> str | None:
    """Pull the raw spoken line from ``<d>[English] ...</d>`` pack prose."""
    if not text:
        return None
    match = TAGGED_DIALOGUE_RE.search(text)
    if not match:
        return None
    line = re.sub(r"\s+", " ", match.group(1)).strip()
    return line or None


def caption_v4_listening(host: str = "127.0.0.1", port: int = 11436, timeout: float = 1.0) -> bool:
    import socket
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _read_pack_md() -> str:
    global _PACK_MD_CACHE
    if _PACK_MD_CACHE is None:
        if PACK_DIALOGUE_MD.is_file():
            _PACK_MD_CACHE = PACK_DIALOGUE_MD.read_text(encoding="utf-8")
        else:
            _PACK_MD_CACHE = ""
    return _PACK_MD_CACHE


def pack_video_prompt_section(clip_id: str) -> str:
    """Video-prompt section of the merged sitcom pack, if that file is present."""
    text = _read_pack_md()
    cid = str(clip_id or "").strip().upper()
    if not text or not cid:
        return ""
    match = re.search(
        rf"^### {re.escape(cid)} [—-] VIDEO PROMPT.*?(?=^### |\Z)",
        text,
        flags=re.M | re.S,
    )
    return match.group(0) if match else ""


def load_clip_override(clip_id: str) -> dict[str, Any]:
    """Per-clip JSON in clip_overrides/<ID>.json. Missing file returns {{}}."""
    cid = str(clip_id or "").strip().upper()
    if not cid:
        return {}
    for name in (f"{cid}.json", f"{cid.lower()}.json"):
        path = OVERRIDES_DIR / name
        if path.is_file():
            data = read_json(path)
            data["_override_path"] = str(path)
            return data
    return {}


def wants_literal(override: dict[str, Any] | None) -> bool:
    if not isinstance(override, dict):
        return False
    return bool(override.get("bypass_director") or override.get("literal_prompt"))


def literal_plan_from_override(override: dict[str, Any], clip: dict[str, Any]) -> dict[str, Any]:
    """Exact prompts from the override file. Pack scene text is only a last resort."""
    start = str(override.get("start_prompt") or "").strip()
    video = str(override.get("video_prompt") or "").strip()
    if not start:
        start = str(clip.get("start_frame") or "").strip()
    if not video:
        video = str(clip.get("video_prompt") or "").strip()
    if not start or not video:
        raise ValueError(f"literal override for {clip.get('id')} missing start_prompt or video_prompt")
    if "negative_prompt" in override and override.get("negative_prompt") is not None:
        neg = str(override.get("negative_prompt"))
    else:
        neg = ""
    return {
        "start_prompt": start,
        "video_prompt": video,
        "negative_prompt": neg,
        "cfg_scale": float(override.get("cfg_scale", 5.5)),
        "step_count": float(override.get("step_count", 28)),
        "denoise": float(override.get("denoise", 1.0)),
        "bypass_director": True,
        "literal_prompt": True,
    }


def clip_dialogue_payload(clip: dict[str, Any]) -> list[dict[str, Any]] | None:
    for key in ("dialogue", "dialogue_lines", "spoken_lines"):
        val = clip.get(key)
        if isinstance(val, list) and val:
            out = []
            for item in val:
                if isinstance(item, dict):
                    text = str(item.get("text") or item.get("line") or "").strip()
                    if not text:
                        continue
                    out.append(
                        {
                            "speaker": str(
                                item.get("speaker")
                                or item.get("speaker_id")
                                or item.get("character")
                                or "unknown"
                            ),
                            "text": text,
                            "voice_asset_id": item.get("voice_asset_id"),
                        }
                    )
                elif isinstance(item, str) and item.strip():
                    out.append({"speaker": "unknown", "text": item.strip(), "voice_asset_id": None})
            if out:
                return out
        if isinstance(val, str) and val.strip() and key == "dialogue":
            return [{"speaker": "unknown", "text": val.strip(), "voice_asset_id": None}]
    for key in ("spoken_line", "spoken_text", "line"):
        val = str(clip.get(key) or "").strip()
        if val:
            return [{"speaker": "unknown", "speaker_id": "unknown", "text": val, "voice_asset_id": None}]
    texts: list[str] = []
    for key in ("video_prompt", "body", "motion_prompt"):
        val = clip.get(key)
        if isinstance(val, str) and val.strip():
            texts.append(val)
    override = load_clip_override(str(clip.get("id") or ""))
    for key in ("video_prompt", "body", "dialogue"):
        val = override.get(key)
        if isinstance(val, str) and "<d>" in val.lower():
            texts.append(val)
    section = pack_video_prompt_section(str(clip.get("id") or ""))
    if section:
        texts.append(section)
    for text in texts:
        line = extract_tagged_dialogue(text)
        if line:
            return [{
                "speaker": "ACTOR",
                "speaker_id": "ACTOR",
                "text": line,
                "voice_asset_id": None,
            }]
    plain = override.get("dialogue")
    if isinstance(plain, str) and plain.strip() and "<d>" not in plain.lower():
        return [{
            "speaker": "ACTOR",
            "speaker_id": "ACTOR",
            "text": plain.strip(),
            "voice_asset_id": None,
        }]
    return None


def build_intent(clip: dict[str, Any], style: dict | None = None) -> str:
    clip_id = str(clip.get("id") or "").upper()
    style = style or {}
    prefix = str(style.get("intent_prefix") or "").strip()
    if prefix and "{clip_id}" in prefix:
        head = prefix.format(clip_id=clip_id)
    elif prefix:
        head = f"{clip_id} {prefix}".strip()
    else:
        head = f"{clip_id} production clip."
    return "\n".join(
        part
        for part in (
            head,
            f"Start frame: {str(clip.get('start_frame') or '').strip()}",
            f"Last frame target: {str(clip.get('last_frame') or '').strip()}",
            f"Video motion: {str(clip.get('video_prompt') or '').strip()}",
        )
        if part.strip()
    )


def build_constraints(
    *,
    clip: dict[str, Any],
    start_ref: Path | None,
    start_note: str,
    last_ref: Path | None,
    last_note: str,
    previous_video: Path | None,
    style: dict | None = None,
) -> str:
    style = style or {}
    profile_constraints = style.get("constraints") or [
        "No text, no watermark, no UI overlay.",
    ]
    if isinstance(profile_constraints, str):
        profile_constraints = [profile_constraints]
    constraints = [str(c) for c in profile_constraints if str(c).strip()]
    constraints.append(f"Clip id: {clip.get('id')}")
    if style.get("profile_id"):
        constraints.append(f"Style profile: {style.get('profile_id')}")
    if start_ref:
        constraints.append(f"Resolved start-frame reference file: {start_ref}")
    else:
        constraints.append(f"Start-frame reference note: {start_note}")
    if last_ref:
        constraints.append(f"Resolved last-frame reference file: {last_ref}")
    else:
        constraints.append(f"Last-frame reference note: {last_note}")
    if previous_video:
        constraints.append(f"Continuity reference from prior SELECTED clip: {previous_video}")
    return " ".join(constraints)


def parse_video_path(stdout: str, stderr: str) -> Path | None:
    combined = f"{stdout}\n{stderr}"
    for pattern in VIDEO_PATH_PATTERNS:
        match = pattern.search(combined)
        if not match:
            continue
        raw = match.group("path").strip().strip('"')
        found = existing_file(raw)
        if found:
            return found
        path = Path(raw)
        return path if path.is_absolute() else ROOT / path
    return None


def tail(text: str, limit: int = 4000) -> str:
    text = text or ""
    return text[-limit:]


def update_progress(
    progress_path: Path,
    progress: dict[str, Any],
    *,
    clip_id: str,
    status: str,
    video_path: Path | None = None,
    error: str | None = None,
) -> None:
    state = progress.setdefault("master_batch_runner", {})
    if not isinstance(state, dict):
        state = {}
        progress["master_batch_runner"] = state
    state["version"] = RUNNER_VERSION
    state.setdefault("started_at", utc_now())
    state["updated_at"] = utc_now()
    state["last_clip_id"] = clip_id
    state["last_status"] = status
    completed = set(str(x).upper() for x in state.get("completed_clip_ids", []))
    failed = set(str(x).upper() for x in state.get("failed_clip_ids", []))
    # Only SELECTED/verified count as completed production (not mere renders).
    if status in {"selected", "verified", "qa_passed", "complete_verified"}:
        completed.add(clip_id)
        failed.discard(clip_id)
    elif status in {"rendered", "qa_pending", "technical_qa"}:
        # Track rendered separately; do not inflate completed_count.
        rendered = set(str(x).upper() for x in state.get("rendered_clip_ids", []))
        rendered.add(clip_id)
        state["rendered_clip_ids"] = sorted(rendered, key=parse_clip_number)
        state["rendered_count"] = len(rendered)
        failed.discard(clip_id)
    elif status in {"failed", "blocked_voice", "blocked"}:
        failed.add(clip_id)
        completed.discard(clip_id)
    state["completed_clip_ids"] = sorted(completed, key=parse_clip_number)
    state["failed_clip_ids"] = sorted(failed, key=parse_clip_number)
    state["completed_count"] = len(completed)
    state["failed_count"] = len(failed)
    if video_path:
        state["last_video_path"] = str(video_path)
    if error:
        state["last_error"] = error
    atomic_write_json(progress_path, progress)


def mark_clip(
    path: Path,
    clip: dict[str, Any],
    *,
    status: str,
    started_at: str,
    finished_at: str,
    command: list[str],
    returncode: int,
    start_ref: Path | None,
    start_note: str,
    last_ref: Path | None,
    last_note: str,
    previous_video: Path | None,
    video_path: Path | None,
    stdout: str,
    stderr: str,
    pipeline_state: str | None = None,
    attempt_id: str | None = None,
) -> None:
    attempts = []
    existing = clip.get("master_batch")
    if isinstance(existing, dict):
        attempts = list(existing.get("attempts") or [])
    attempts.append(
        {
            "started_at": started_at,
            "finished_at": finished_at,
            "returncode": returncode,
            "video_path": str(video_path) if video_path else None,
            "attempt_id": attempt_id,
            "stdout_tail": tail(stdout),
            "stderr_tail": tail(stderr),
        }
    )
    clip["master_batch"] = {
        "version": RUNNER_VERSION,
        "status": status,
        "pipeline_state": pipeline_state or (
            "SELECTED" if status in SELECTED_STATUSES
            else "QA_PENDING" if status in {"rendered", "qa_pending"}
            else "RENDERED" if status == "complete"
            else "FAILED" if status == "failed"
            else str(status).upper()
        ),
        "verified": False,
        "attempt_id": attempt_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "command": command,
        "returncode": returncode,
        "start_reference_path": str(start_ref) if start_ref else None,
        "start_frame_path": str(start_ref) if start_ref else None,
        "start_reference_note": start_note,
        "last_reference_path": str(last_ref) if last_ref else None,
        "last_frame_path": str(last_ref) if last_ref else None,
        "end_frame_path": str(last_ref) if last_ref else None,
        "last_reference_note": last_note,
        "previous_clip_video": str(previous_video) if previous_video else None,
        "video_path": str(video_path) if video_path else None,
        "attempts": attempts[-5:],
    }
    atomic_write_json(path, clip)


def mark_clip_blocked(
    path: Path,
    clip: dict[str, Any],
    *,
    reason: str,
    pipeline_state: str = "BLOCKED_VOICE",
    error: str | None = None,
) -> None:
    """Durable blocked status using the real mark_clip / clip JSON contract."""
    now = utc_now()
    mark_clip(
        path,
        clip,
        status="blocked",
        started_at=now,
        finished_at=now,
        command=[],
        returncode=1,
        start_ref=None,
        start_note="",
        last_ref=None,
        last_note="",
        previous_video=None,
        video_path=None,
        stdout="",
        stderr=str(error or reason),
        pipeline_state=pipeline_state,
        attempt_id=None,
    )
    mb = clip.get("master_batch")
    if isinstance(mb, dict):
        mb["blocked_reason"] = reason
        mb["error"] = str(error or reason)
        atomic_write_json(path, clip)


def clip_requires_audio(clip: dict[str, Any]) -> bool:
    """Authoritative audio requirement from compiled dialogue / flags."""
    if clip.get("required_audio") is True:
        return True
    if clip.get("required_audio") is False and clip.get("dialogue_lines") is not None:
        # Explicit compile said no — still allow payload override if lines exist with text
        pass
    payload = clip_dialogue_payload(clip)
    if payload:
        return True
    lines = clip.get("dialogue_lines")
    if isinstance(lines, list) and lines:
        for item in lines:
            if isinstance(item, dict) and (
                item.get("exact_text") or item.get("text") or item.get("improvisation_permitted")
            ):
                return True
            if isinstance(item, str) and item.strip():
                return True
    return False


def accept_clip_after_gates(
    *,
    db,
    attempt_id: str | None,
    clip: dict[str, Any],
    clip_path: Path,
    video_path: Path | None,
    gates_run: dict[str, bool] | None = None,
) -> bool:
    """Conservative stub: TECHNICAL_QA -> SELECTED only if visual/audio/boundary gates pass.

    Fails closed when gates have not been run.
    """
    gates_run = gates_run or {}
    required = ("technical", "visual", "audio", "boundary")
    missing = [g for g in required if not gates_run.get(g)]
    if missing:
        mb = clip.setdefault("master_batch", {})
        if isinstance(mb, dict):
            mb["pipeline_state"] = "TECHNICAL_QA"
            mb["status"] = "rendered"
            mb["acceptance"] = {
                "ok": False,
                "missing_gates": missing,
                "note": "fail-closed: gates not run; cannot SELECTED",
            }
            atomic_write_json(clip_path, clip)
        return False
    if not all(gates_run.get(g) for g in required):
        return False
    mb = clip.setdefault("master_batch", {})
    if isinstance(mb, dict):
        mb["pipeline_state"] = "SELECTED"
        mb["status"] = "selected"
        mb["verified"] = True
        atomic_write_json(clip_path, clip)
    if db is not None and _HAS_STORE and attempt_id and set_attempt_state:
        try:
            set_attempt_state(db, attempt_id, "SELECTED")
        except Exception:
            pass
    return True


def enforce_native_voice_gate(*, db, job_id: str, clip_id: str, clip: dict, all_clips_dialogue: dict | None = None) -> None:
    """Fail closed for dependent shots missing canonical MiniMax voices.

    Enabled when db is present and clip audio mode is native / dialogue-bearing.
    """
    if not _HAS_NATIVE_VOICE or db is None:
        return
    mode = str(clip.get("audio_mode") or clip.get("shot_audio_mode") or "").lower()
    dialogue = clip_dialogue_payload(clip) if "clip_dialogue_payload" in globals() else (clip.get("dialogue") or [])
    if not dialogue and mode not in {"native_h3_audio", "visible_dialogue", "narration_over_picture"}:
        return
    lines = dialogue if isinstance(dialogue, list) else []
    # normalize
    norm = []
    for item in lines:
        if isinstance(item, dict):
            row = dict(item)
            if not str(row.get("speaker_id") or "").strip():
                row["speaker_id"] = str(
                    row.get("speaker") or row.get("character_id") or "ACTOR"
                )
            norm.append(row)
        elif isinstance(item, str) and item.strip():
            norm.append({"speaker_id": "ACTOR", "text": item})
    if not norm:
        return
    _nvc.require_canonical_voices_for_shot(
        db,
        job_id=str(job_id),
        shot_id=str(clip_id),
        dialogue_lines=norm,
        shot_dialogue_index=all_clips_dialogue,
    )


def register_bootstrap_voices(
    *,
    db,
    job_id: str,
    task_dir: Path,
    clip_id: str,
    clip: dict[str, Any],
    video_path: Path | None,
    attempt_id: str | None,
    dialogue_index: dict | None,
) -> None:
    """Save the first speaking take for each character and promote it to canonical.

    Later shots stay blocked until this row exists. The Comfy reference file
    C001_master_voice.wav is a copy for LoadAudio; the canonical path itself
    is character-scoped so it is not a shared C001 filename.
    """
    if db is None or not _HAS_NATIVE_VOICE or video_path is None or not Path(video_path).is_file():
        return
    lines = clip_dialogue_payload(clip) or []
    if not lines:
        return
    index = dict(dialogue_index or {})
    index.setdefault(clip_id, lines)
    first = _nvc.first_qualifying_speaking_shots(index)
    from voice_extract import ExtractionPlan, extract_speaker_wav
    import shutil

    comfy_input = Path(r"A:\Users\rhine\ComfyUI-Shared\input")
    for item in lines:
        if not isinstance(item, dict):
            continue
        character_id = str(item.get("speaker_id") or item.get("speaker") or "").strip()
        transcript = str(item.get("text") or "").strip()
        if not character_id or not transcript:
            continue
        if first.get(character_id) != clip_id:
            continue
        if _nvc.get_canonical_voice(db, job_id=job_id, character_id=character_id):
            print(f"[voice] {clip_id} canonical already set for {character_id}", flush=True)
            continue
        out = task_dir / "outputs" / "voices" / f"{character_id}_{clip_id}_bootstrap.wav"
        plan = ExtractionPlan(
            source_media=str(video_path),
            output_wav=str(out),
            start_s=0.0,
            end_s=10.0,
            sample_rate=32000,
            exact_transcript=transcript,
            character_id=character_id,
        )
        extracted = extract_speaker_wav(plan, transcript_matches_script=True)
        if not extracted.ok or not extracted.output_wav:
            raise RuntimeError(
                f"bootstrap voice extract failed for {clip_id}/{character_id}: "
                f"{extracted.rejection_reasons}"
            )
        candidate_id = f"cand_{clip_id.lower()}_{character_id.lower()}"
        _nvc.register_candidate(
            db,
            candidate_id=candidate_id,
            job_id=job_id,
            character_id=character_id,
            bootstrap_shot_id=clip_id,
            bootstrap_attempt_id=str(attempt_id or clip_id),
            source_audio_path=video_path,
            segment_start_sample=int(extracted.start_sample),
            segment_end_sample=int(extracted.end_sample),
            reference_audio_path=extracted.output_wav,
            exact_reference_transcript=transcript,
            qa_evidence={"source": "rendered_bootstrap_take"},
        )
        _nvc.promote_canonical(
            db,
            job_id=job_id,
            character_id=character_id,
            candidate_id=candidate_id,
        )
        if clip_id.upper() == "C001" and comfy_input.is_dir():
            dest = comfy_input / "C001_master_voice.wav"
            shutil.copyfile(extracted.output_wav, dest)
            print(f"[voice] copied bootstrap wav to {dest}", flush=True)
        print(
            f"[voice] canonical {character_id} from {clip_id} -> {extracted.output_wav}",
            flush=True,
        )


def run_clip(
    *,
    args: argparse.Namespace,
    task_dir: Path,
    clip_ids: list[str],
    clip_id: str,
    progress: dict[str, Any],
) -> bool:
    path = clip_json_path(task_dir, clip_id)
    clip = read_json(path)
    if is_clip_complete(clip) and not args.force:
        print(f"[skip] {clip_id} already SELECTED/verified: {recorded_video_path(clip)}", flush=True)
        return True

    style = getattr(args, "style_profile_data", None) or load_style_profile(args.style_profile)
    db = getattr(args, "_production_db", None)

    # Native MiniMax voice continuity gate (per-character canonical refs).
    if db is not None:
        job_key = str(getattr(args, "job_id", None) or task_dir.name)
        if getattr(args, "_dialogue_index", None) is None:
            index: dict[str, list] = {}
            for cid in clip_ids:
                try:
                    lines = clip_dialogue_payload(load_clip(task_dir, cid))
                except Exception:
                    lines = None
                if lines:
                    index[cid] = lines
            args._dialogue_index = index
        try:
            enforce_native_voice_gate(
                db=db,
                job_id=job_key,
                clip_id=clip_id,
                clip=clip,
                all_clips_dialogue=args._dialogue_index,
            )
        except Exception as _voice_exc:
            print(f"[voice-gate] {clip_id}: {_voice_exc}", flush=True)
            mark_clip_blocked(
                path,
                clip,
                reason="native_voice_gate",
                pipeline_state="BLOCKED_VOICE",
                error=str(_voice_exc),
            )
            update_progress(
                task_dir / "progress.json",
                progress,
                clip_id=clip_id,
                status="blocked_voice",
                error=str(_voice_exc),
            )
            return False

    start_ref, start_note = resolve_frame_reference(
        task_dir=task_dir,
        clip_ids=clip_ids,
        current_clip_id=clip_id,
        field_text=str(clip.get("start_frame") or ""),
        preferred_kind="start",
        db=db,
    )
    last_ref, last_note = resolve_frame_reference(
        task_dir=task_dir,
        clip_ids=clip_ids,
        current_clip_id=clip_id,
        field_text=str(clip.get("last_frame") or ""),
        preferred_kind="last",
        db=db,
    )
    prev_id = previous_clip_id(clip_id, clip_ids)
    previous_video = get_completed_media(task_dir, prev_id, db=db) if prev_id else None

    clip_duration = float(
        clip.get("duration_seconds")
        if clip.get("duration_seconds") is not None
        else getattr(args, "duration", 8.0)
    )
    # Backrooms editorial default is 10s when pack omits duration but style is backrooms.
    style_id = str((getattr(args, "style_profile_data", None) or {}).get("profile_id") or args.style_profile or "")
    if clip.get("duration_seconds") is None and (
        "backrooms" in style_id.lower() or getattr(args, "backrooms_production", False)
    ):
        clip_duration = 10.0
    editorial_frames = max(1, int(round(float(clip_duration) * 24)))
    category = str(style.get("category") or "generic")
    focus = str(style.get("focus") or "scene, motion_smoothness")
    backend_profile = str(style.get("backend_profile") or "h3_distilled")
    quality_tier = str(
        args.quality_tier or style.get("quality_tier_default") or "standard"
    )
    motion_complexity = str(
        args.motion_complexity or style.get("motion_complexity_default") or "moderate"
    )

    override = load_clip_override(clip_id)
    literal = wants_literal(override)
    literal_plan = None
    if literal:
        literal_plan = literal_plan_from_override(override, clip)
        print(
            f"[literal] {clip_id} bypass_director from {override.get('_override_path')}",
            flush=True,
        )

    attempt_id = None
    input_payload = {
        "clip_id": clip_id,
        "intent": (
            f"{clip_id} literal override"
            if literal
            else build_intent(clip, style)
        ),
        "category": category,
        "editorial_frames": editorial_frames,
        "backend_profile": backend_profile,
        "quality_tier": quality_tier,
        "motion_complexity": motion_complexity,
        "style_profile": style.get("profile_id"),
        "start_ref": str(start_ref) if start_ref else None,
        "last_ref": str(last_ref) if last_ref else None,
    }
    if db is not None and _HAS_STORE:
        try:
            initial_state = "DRY_RUN" if args.dry_run else "READY"
            attempt_id = create_attempt(
                db,
                shot_id=clip_id,
                input_payload=input_payload,
                required_audio=clip_requires_audio(clip),
                meta={
                    "runner": RUNNER_VERSION,
                    "style": style.get("profile_id"),
                    "literal": bool(literal),
                },
                state=initial_state,
            )
            if not args.dry_run:
                set_attempt_state(db, attempt_id, "SUBMITTING")
        except Exception as exc:
            require_store = bool(
                getattr(args, "require_store", False)
                or getattr(args, "backrooms_production", False)
            )
            print(f"[store] create_attempt {'ERROR' if require_store else 'warning'}: {exc}", flush=True)
            if require_store:
                mark_clip_blocked(
                    path, clip,
                    reason="store_create_attempt_failed",
                    pipeline_state="BLOCKED_STORE",
                    error=str(exc),
                )
                update_progress(
                    task_dir / "progress.json", progress,
                    clip_id=clip_id, status="failed", error=str(exc),
                )
                return False

    if literal and literal_plan is not None:
        intent_text = f"{clip_id} literal override"
        constraints_text = "literal override; prompts are fixed; no style rewrite"
    else:
        intent_text = build_intent(clip, style)
        constraints_text = build_constraints(
            clip=clip,
            start_ref=start_ref,
            start_note=start_note,
            last_ref=last_ref,
            last_note=last_note,
            previous_video=previous_video,
            style=style,
        )
    command = [
        sys.executable,
        str(args.generator),
        "--intent",
        intent_text,
        "--category",
        category,
        "--focus",
        focus,
        "--duration",
        str(clip_duration),
        "--editorial-frames",
        str(editorial_frames),
        "--constraints",
        constraints_text,
        "--clip-id",
        clip_id.lower(),
        "--backend-profile",
        backend_profile,
        "--quality-tier",
        quality_tier,
        "--motion-complexity",
        motion_complexity,
    ]
    if attempt_id:
        command.extend(["--attempt-id", attempt_id])
    if start_ref:
        command.extend(["--start-frame-path", str(start_ref)])
    if last_ref:
        command.extend(["--end-frame-path", str(last_ref)])
    dialogue = clip_dialogue_payload(clip)
    needs_audio = clip_requires_audio(clip)
    if dialogue:
        command.extend(["--dialogue-json", json.dumps(dialogue, ensure_ascii=False)])
    elif needs_audio and clip.get("dialogue_lines"):
        # Pass structured compile lines even when payload filter skipped improv-only.
        command.extend(
            ["--dialogue-json", json.dumps(clip.get("dialogue_lines"), ensure_ascii=False)]
        )
    if needs_audio and (
        getattr(args, "native_minimax_voice", False)
        or getattr(args, "backrooms_production", False)
        or clip.get("native_minimax_voice")
    ):
        command.append("--native-minimax-voice")
        voice_ref = getattr(args, "voice_ref_json", None) or clip.get("voice_ref_json")
        image_ref = getattr(args, "image_ref_json", None) or clip.get("image_ref_json")
        if voice_ref:
            command.extend(["--voice-ref-json", str(voice_ref)])
        if image_ref:
            command.extend(["--image-ref-json", str(image_ref)])
    if literal and literal_plan is not None:
        plan_path = task_dir / "outputs" / "literal_plans" / f"{clip_id}.json"
        atomic_write_json(plan_path, literal_plan)
        command.extend([
            "--bypass-director",
            "--literal-prompt",
            "--literal-plan-json",
            str(plan_path),
        ])
    if args.compiled and not literal:
        command.extend(["--compiled", str(args.compiled)])
    if args.dry_run:
        command.append("--dry-run")
    if getattr(args, "skip_visual_qa", False) or not caption_v4_listening():
        command.append("--skip-visual-qa")
    if getattr(args, "qa_loop", False):
        policy_json = getattr(args, "qa_policy_json", None)
        requirements_json = getattr(args, "qa_requirements_json", None)
        gen_graph = getattr(args, "qa_generation_graph", None)
        qa_receipt = getattr(args, "qa_receipt", None)
        qa_candidate = getattr(args, "qa_candidate", None)
        has_receipt = bool(qa_receipt and policy_json and requirements_json)
        has_candidate = bool(qa_candidate and policy_json and requirements_json)
        has_generate = bool(policy_json and requirements_json and gen_graph)
        if not (has_receipt or has_candidate or has_generate):
            print(f"[qa] {clip_id} blocked: --qa-loop needs policy+rubric and one of --qa-receipt, --qa-candidate, or --qa-generation-graph", flush=True)
            mark_clip(
                path, clip, status="failed", started_at=utc_now(), finished_at=utc_now(),
                command=[], returncode=4, start_ref=start_ref, start_note=start_note,
                last_ref=last_ref, last_note=last_note, previous_video=previous_video,
                video_path=None, stdout="", stderr="QA_ERROR missing still-QA inputs",
                pipeline_state="QA_ERROR", attempt_id=attempt_id,
            )
            update_progress(task_dir / "progress.json", progress, clip_id=clip_id,
                            status="failed", error="QA_ERROR missing still-QA inputs")
            return False
        command.append("--require-qa-receipt")
        command.extend(["--qa-policy-json", str(policy_json),
                        "--qa-requirements-json", str(requirements_json)])
        if has_receipt:
            command.extend(["--qa-receipt", str(qa_receipt)])
            try:
                policy = json.loads(Path(policy_json).read_text(encoding="utf-8"))
                if policy.get("policy_id"):
                    command.extend(["--qa-policy-id", str(policy["policy_id"])])
            except Exception:
                pass
        elif has_candidate:
            job_root = Path(getattr(args, "qa_job_root", None) or (task_dir / "qa_jobs"))
            job_dir = job_root / clip_id
            command.extend([
                "--qa-candidate", str(qa_candidate),
                "--qa-job-dir", str(job_dir),
                "--qa-local",
            ])
            if getattr(args, "qa_audit_caption", None):
                command.extend(["--qa-audit-caption", str(args.qa_audit_caption)])
        else:
            job_root = Path(getattr(args, "qa_job_root", None) or (task_dir / "qa_jobs"))
            job_dir = job_root / clip_id
            command.extend([
                "--qa-job-dir", str(job_dir),
                "--qa-generation-graph", str(gen_graph),
            ])
            if getattr(args, "qa_local", False):
                command.append("--qa-local")
            if getattr(args, "qa_object_info", None):
                command.extend(["--qa-object-info", str(args.qa_object_info)])
            if getattr(args, "qa_resume", False):
                command.append("--qa-resume")
    else:
        command.append("--allow-ungated-i2v")

    print(f"[run] {clip_id}", flush=True)
    started_at = utc_now()
    qa_budget = max(1, int(getattr(args, "qa_attempts", 3) or 3)) if getattr(args, "qa_loop", False) else 1
    proc = None
    video_path = None
    for qa_attempt in range(qa_budget):
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=args.timeout,
        )
        video_path = parse_video_path(proc.stdout, proc.stderr)
        if proc.returncode == 0:
            break
        if proc.returncode != 3 or qa_attempt + 1 >= qa_budget:
            break
        print(f"[qa-reroll] {clip_id} attempt {qa_attempt + 2}/{qa_budget}", flush=True)
    finished_at = utc_now()
    complete = proc.returncode == 0 and (args.dry_run or existing_file(video_path))
    if args.dry_run and proc.returncode == 0:
        status = "dry_run_complete"
        pipeline_state = "DRY_RUN"
    elif complete and getattr(args, "qa_loop", False):
        status = "qa_passed"
        pipeline_state = "QA_PASSED"
    elif complete:
        status = "rendered"
        pipeline_state = "QA_PENDING"
    elif getattr(args, "qa_loop", False) and proc.returncode == 3:
        status = "failed"
        pipeline_state = "QA_FAILED"
    else:
        status = "failed"
        pipeline_state = "FAILED"

    mark_clip(
        path,
        clip,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        command=command,
        returncode=proc.returncode,
        start_ref=start_ref,
        start_note=start_note,
        last_ref=last_ref,
        last_note=last_note,
        previous_video=previous_video,
        video_path=video_path,
        stdout=proc.stdout,
        stderr=proc.stderr,
        pipeline_state=pipeline_state,
        attempt_id=attempt_id,
    )

    if status == "rendered":
        if db is not None and _HAS_STORE and attempt_id:
            try:
                art_sha = None
                if video_path and Path(video_path).is_file():
                    art_sha = sha256_file(video_path)
                set_attempt_state(
                    db,
                    attempt_id,
                    "RENDERED",
                    artifact_path=str(video_path) if video_path else None,
                    artifact_sha256=art_sha,
                )
                set_attempt_state(db, attempt_id, "TECHNICAL_QA")
                try:
                    progress["production_store_export"] = export_progress_view(db)
                except Exception:
                    pass
            except Exception as exc:
                print(f"[store] render state warning: {exc}", flush=True)
        # Acceptance stub: fail closed until visual/audio/boundary gates run.
        accepted = accept_clip_after_gates(
            db=db,
            attempt_id=attempt_id,
            clip=clip,
            clip_path=path,
            video_path=video_path,
            gates_run={"technical": True},  # only technical reached here
        )
        update_progress(
            task_dir / "progress.json", progress,
            clip_id=clip_id,
            status="selected" if accepted else "rendered",
            video_path=video_path,
        )
        print(
            f"[{'selected' if accepted else 'rendered/qa_pending'}] {clip_id}: {video_path}",
            flush=True,
        )
        try:
            register_bootstrap_voices(
                db=db,
                job_id=str(getattr(args, "job_id", None) or task_dir.name),
                task_dir=task_dir,
                clip_id=clip_id,
                clip=clip,
                video_path=video_path,
                attempt_id=attempt_id,
                dialogue_index=getattr(args, "_dialogue_index", None),
            )
        except Exception as exc:
            print(f"[voice] {clip_id} bootstrap failed: {exc}", flush=True)
            update_progress(
                task_dir / "progress.json",
                progress,
                clip_id=clip_id,
                status="blocked_voice",
                video_path=video_path,
                error=str(exc),
            )
            return False
        return True

    if status == "dry_run_complete":
        if db is not None and _HAS_STORE and attempt_id and set_attempt_state:
            try:
                set_attempt_state(db, attempt_id, "DRY_RUN")
            except Exception as exc:
                print(f"[store] dry-run state warning: {exc}", flush=True)
        print(f"[dry-run-ok] {clip_id}", flush=True)
        return True

    if db is not None and _HAS_STORE and attempt_id:
        try:
            set_attempt_state(db, attempt_id, "FAILED_RENDER")
        except Exception:
            pass

    error = f"child returncode={proc.returncode}; video_path={video_path}"
    update_progress(
        task_dir / "progress.json", progress,
        clip_id=clip_id, status="failed", video_path=video_path, error=error,
    )
    print(f"[failed] {clip_id}: {error}", flush=True)
    if proc.stdout:
        print("--- child stdout tail ---", flush=True)
        print(tail(proc.stdout, 1200), flush=True)
    if proc.stderr:
        print("--- child stderr tail ---", flush=True)
        print(tail(proc.stderr, 1200), flush=True)
    return False


def select_clip_ids(
    all_ids: list[str], *, start_at: str | None, only: list[str], limit: int | None
) -> list[str]:
    selected = list(all_ids)
    if only:
        wanted = {x.upper() for x in only}
        selected = [x for x in selected if x in wanted]
    if start_at:
        start = start_at.upper()
        if start not in selected:
            raise SystemExit(f"--start-at {start!r} is not in the managed task")
        selected = selected[selected.index(start) :]
    if limit is not None:
        selected = selected[: max(0, limit)]
    return selected


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Sequential prompt-pack renderer (style-profile driven)."
    )
    p.add_argument("--task-dir", type=Path, default=DEFAULT_TASK_DIR)
    p.add_argument("--generator", type=Path, default=DEFAULT_GENERATOR)
    p.add_argument("--compiled", type=Path, default=None)
    p.add_argument("--duration", type=float, default=8.0)
    p.add_argument("--timeout", type=float, default=60 * 60 * 2)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--start-at", default=None)
    p.add_argument("--only", nargs="*", default=[])
    p.add_argument("--force", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--continue-on-error", action="store_true")
    p.add_argument(
        "--style-profile",
        default=None,
        help="Style profile id or JSON path (default: env GVD_STYLE_PROFILE or generic). "
             "Backrooms/VHS constraints live in style_profiles/backrooms_sitcom.json only.",
    )
    p.add_argument(
        "--quality-tier",
        default=None,
        choices=["draft", "standard", "high", "hero"],
    )
    p.add_argument(
        "--motion-complexity",
        default=None,
        choices=["static", "subtle", "moderate", "complex"],
    )
    p.add_argument("--production-db", type=Path, default=None)
    p.add_argument(
        "--require-store",
        action="store_true",
        default=False,
        help="Treat production_store create_attempt failures as blocking.",
    )
    p.add_argument(
        "--backrooms-production",
        action="store_true",
        default=False,
        help="Backrooms production mode: require-store, native voice, 10s defaults.",
    )
    p.add_argument(
        "--native-minimax-voice",
        action="store_true",
        default=False,
        help="Pass --native-minimax-voice to generate_video when clip requires audio.",
    )
    p.add_argument(
        "--enable-native-voice",
        action="store_true",
        default=False,
        help="Alias of --native-minimax-voice.",
    )
    p.add_argument("--voice-ref-json", default=None)
    p.add_argument("--image-ref-json", default=None)
    p.add_argument(
        "--qa-loop",
        action="store_true",
        default=False,
        help="After a rendered clip, run GVD QA and rerun the child generator on fail (bounded).",
    )
    p.add_argument(
        "--qa-attempts",
        type=int,
        default=3,
        help="QA reroll budget including the first render (default 3).",
    )
    p.add_argument(
        "--qa-expected-tags",
        default="",
        help="Comma-separated WD14 tags required for --qa-loop.",
    )
    p.add_argument("--qa-policy-json", type=Path, default=None)
    p.add_argument("--qa-requirements-json", type=Path, default=None)
    p.add_argument("--qa-generation-graph", type=Path, default=None)
    p.add_argument("--qa-job-root", type=Path, default=None)
    p.add_argument("--qa-object-info", type=Path, default=None)
    p.add_argument("--qa-resume", action="store_true", default=False)
    p.add_argument("--qa-receipt", type=Path, default=None,
                   help="Existing accepted.json for --qa-loop I2V.")
    p.add_argument("--qa-candidate", type=Path, default=None,
                   help="Existing still PNG to score before I2V.")
    p.add_argument("--qa-local", action="store_true", default=False)
    p.add_argument("--qa-audit-caption", default="")
    p.add_argument(
        "--skip-visual-qa",
        action="store_true",
        default=False,
        help="Do not score with Caption V4. Also applied when port 11436 is closed.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    args.task_dir = args.task_dir.resolve()
    args.generator = args.generator.resolve()
    if args.compiled:
        args.compiled = args.compiled.resolve()
    if getattr(args, "enable_native_voice", False):
        args.native_minimax_voice = True
    if getattr(args, "backrooms_production", False):
        args.require_store = True
        args.native_minimax_voice = True
        if float(args.duration) == 8.0:
            args.duration = 10.0

    progress_path = args.task_dir / "progress.json"
    if not progress_path.is_file():
        raise SystemExit(f"progress.json not found: {progress_path}")
    if not args.generator.is_file():
        raise SystemExit(f"generator not found: {args.generator}")

    args.style_profile_data = load_style_profile(args.style_profile)
    args._production_db = open_production_store(args.task_dir, args.production_db)

    progress = read_json(progress_path)
    clip_ids = clip_ids_from_progress(progress)
    if not clip_ids:
        raise SystemExit("progress.json has no clip_ids")
    selected = select_clip_ids(
        clip_ids, start_at=args.start_at, only=args.only, limit=args.limit
    )
    if not selected:
        print("No clips selected.")
        return 0

    print(f"Task: {args.task_dir}", flush=True)
    print(
        f"Style profile: {args.style_profile_data.get('profile_id')} "
        f"(backend={args.style_profile_data.get('backend_profile')})",
        flush=True,
    )
    print(f"Selected clips: {selected[0]}..{selected[-1]} ({len(selected)})", flush=True)
    print("VRAM isolation: child process per clip; generate_video.py is not imported.", flush=True)

    for clip_id in selected:
        ok = run_clip(
            args=args, task_dir=args.task_dir, clip_ids=clip_ids,
            clip_id=clip_id, progress=progress,
        )
        progress = read_json(progress_path)
        if not ok and not args.continue_on_error:
            print("Stopping at first failed clip. Fix it, then rerun to resume.", flush=True)
            return 1

    print("Batch runner finished selected clip range.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
