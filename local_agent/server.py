#!/usr/bin/env python3
"""Local chat app — ChatGPT-desktop shape, running entirely on this machine.

WHY IT IS BUILT THIS WAY
------------------------
**No downloads.** The operator is on a phone hotspot. So no Electron, no Tauri,
no FastAPI, no Flask, no npm. `http.server` and `urllib` from the standard
library, plus one self-contained HTML file. It runs on the Python already here.

**No GPU when the GPU is busy.** `router.py` picks the tier before every turn —
big model on the card when it is free, small CPU model the moment a render
claims it, and the GPU model is actively evicted rather than left resident.

Binds **127.0.0.1 only**. Nothing on the network can reach it, which matters
because the actions can regenerate project files.

    python local_agent\\server.py        then open http://127.0.0.1:8760
"""
from __future__ import annotations

import json
import base64
import os
import hashlib
import hmac
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent              # noqa: E402
from atomic_io import atomic_write_text  # noqa: E402
import exemplar_curator   # noqa: E402
import exemplar_embeddings  # noqa: E402
import feedback           # noqa: E402
import feedback_manager   # noqa: E402
import intent_mismatch    # noqa: E402
import memory_extractor   # noqa: E402
import file_edit_gate     # noqa: E402
import gpu_gate           # noqa: E402
import learning           # noqa: E402
import loop_controller    # noqa: E402
import ollama_client as oll     # noqa: E402
import remote_security          # noqa: E402
import router             # noqa: E402
import store              # noqa: E402
import tools              # noqa: E402

HOST, PORT = "127.0.0.1", 8760
APP_REVISION = "2026-09-22i-gvd-video-pipeline-readiness"
SESSION_CSRF = secrets.token_hex(32)
_LOCAL_HOSTS = frozenset({
    f"127.0.0.1:{PORT}", "localhost:{PORT}", f"[::1]:{PORT}",
    "127.0.0.1", "localhost", "[::1]",
})
_LOCAL_ORIGINS = frozenset({
    f"http://127.0.0.1:{PORT}",
    f"http://localhost:{PORT}",
    f"http://[::1]:{PORT}",
})
INDEX = HERE / "static" / "index.html"
UPLOADS = HERE / "uploads"
AUTO_FARM_ROUTING = "auto_farm"
AUTO_FARM_MODEL_TOKEN = "auto_farm"


def wants_auto_farm(value) -> bool:
    """True when the picker sent the explicit unpinned Mac-farm mode."""
    return str(value or "").strip().lower().replace("-", "_") == AUTO_FARM_MODEL_TOKEN


def is_auto_farm_conversation(conv: dict | None) -> bool:
    if not isinstance(conv, dict):
        return False
    return str(conv.get("routing") or "") == AUTO_FARM_ROUTING


def answer_model_for_conversation(conv: dict | None) -> str | None:
    """Tag passed to agent.answer. None is farm-eligible (unpinned).

    Pinned Huihui/Coder chats keep their tag. Auto-farm chats always pass
    None even if model is an empty string. Do not treat empty-model legacy
    chats as auto-farm — those still go through the pin migration.
    """
    if is_auto_farm_conversation(conv):
        return None
    name = str((conv or {}).get("model") or "").strip()
    return name or None


MAX_UPLOAD_BYTES = 75 * 1024 * 1024
MAX_JSON_BYTES = 105 * 1024 * 1024
MEDIA_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus",
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
}

# render_story_image's owned ComfyUI backend writes every general-story still
# under this one shared root (see work/image_render.py's IMAGE_OUTPUT). This
# app is bound to 127.0.0.1 only, so serving from here is desktop-only by
# construction — nothing remote can ever reach these HTTP routes.
STORY_OUTPUT_ROOT = (HERE.parent / "outputs" / "stories").resolve()
STORY_IMAGE_ROOT = (STORY_OUTPUT_ROOT / "_comfy_output").resolve()
EQUAL_SHARES_ROOT = (HERE.parent / "outputs" / "equal_shares").resolve()
CHATS_ROOT = (HERE / "chats").resolve()
# Shared Rockernow output (comfy_generate / comfy_job_status). Same default as
# mcp_client.COMFYUI_PATH. Never Equal Shares.
_SHARED_COMFY_ROOT = Path(os.environ.get(
    "EQUAL_SHARES_COMFYUI_PATH", r"A:\Users\rhine\ComfyUI-Shared"))
SHARED_OUTPUT_ROOT = (_SHARED_COMFY_ROOT / "output").resolve()
SHARED_INPUT_ROOT = (_SHARED_COMFY_ROOT / "input").resolve()
# start_current_chat_render jobs (chat_render_jobs.JOBS). Only the finished
# videos in <cid>/<job>/renders/ are servable: the job folder also holds copies
# of the chat's uploads (img0/img1/video_refs) and the runner's Comfy runtime.
CHAT_RENDER_JOBS_ROOT = (HERE / "render_jobs").resolve()
# Allow-list ids the browser may send. Never a filesystem path.
ALLOWED_MEDIA_ROOT_IDS = frozenset({"story_comfy", "story_output", "shared_output",
                                    "chat_render"})
STORY_MEDIA_TOOLS = frozenset({
    "story_image_job_status", "render_story_image", "render_story_image_batch",
    "await_story_image_job",
})
COMFY_MEDIA_TOOLS = frozenset({"comfy_job_status"})
# A separate flag (rather than checking os.name directly at call time) so
# tests can flip this without breaking pathlib, which dispatches Path() to
# WindowsPath/PosixPath based on the real os.name and raises if the two
# disagree on a given interpreter.
_IS_WINDOWS = os.name == "nt"
_IMAGE_CTYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".bmp": "image/bmp", ".gif": "image/gif"}
_VIDEO_CTYPES = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
                 ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
                 ".m4v": "video/x-m4v"}


def _path_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def forbidden_media_roots() -> tuple[Path, ...]:
    """Roots that must never be served, even if a locator tries to walk into them."""
    return (EQUAL_SHARES_ROOT, CHATS_ROOT, UPLOADS.resolve(), SHARED_INPUT_ROOT)


def media_root_dir(root_id: object) -> Path | None:
    """Look up an allow-listed root by id. Reads live module globals so tests can patch."""
    key = str(root_id or "").strip()
    if key not in ALLOWED_MEDIA_ROOT_IDS:
        return None
    if key == "story_comfy":
        return STORY_IMAGE_ROOT
    if key == "story_output":
        return STORY_OUTPUT_ROOT
    if key == "shared_output":
        return SHARED_OUTPUT_ROOT
    if key == "chat_render":
        return CHAT_RENDER_JOBS_ROOT
    return None


def media_kinds_for_root(root_id: object) -> str:
    """Suffix class a root may serve: story stills are images, chat renders videos."""
    key = str(root_id or "").strip()
    if key == "shared_output":
        return "media"
    if key == "chat_render":
        return "video"
    return "image"


def _suffix_allowed(suffix: str, kinds: str) -> bool:
    if kinds == "image":
        return suffix in _IMAGE_CTYPES
    if kinds == "video":
        return suffix in _VIDEO_CTYPES
    if kinds == "media":
        return suffix in _IMAGE_CTYPES or suffix in _VIDEO_CTYPES
    return False


def resolve_generated_media(root_id: object, subfolder: object, filename: object,
                            *, kinds: str = "image") -> Path | None:
    """Map a (root id, subfolder, filename) locator to a real allow-listed file.

    Returns None for an unknown root, a path that escapes the root, a forbidden
    tree (uploads / chats / equal_shares / Shared input), a disallowed suffix,
    or a missing file. Story roots stay image-only even if kinds=media/video;
    chat_render is video-only and only <cid>/<job>/renders/<file>.
    """
    root = media_root_dir(root_id)
    if root is None:
        return None
    key = str(root_id or "").strip()
    effective_kinds = {"story_comfy": "image", "story_output": "image",
                       "chat_render": "video"}.get(key, kinds)
    subfolder = str(subfolder or "").strip().strip("/\\").replace("\\", "/")
    filename = str(filename or "").strip()
    if not filename or Path(filename).name != filename:
        return None
    if any(part in ("..", "") for part in Path(subfolder).parts) and subfolder:
        return None
    try:
        candidate = (root / subfolder / filename).resolve()
        root = root.resolve()
    except (OSError, ValueError):
        return None
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if key in {"story_comfy", "story_output"} and not _path_under(candidate, STORY_OUTPUT_ROOT):
        return None
    if key == "shared_output" and not _path_under(candidate, SHARED_OUTPUT_ROOT):
        return None
    if key == "chat_render":
        parts = candidate.relative_to(root).parts
        if len(parts) != 4 or parts[2].lower() != "renders":
            return None
    for banned in forbidden_media_roots():
        if _path_under(candidate, banned):
            return None
    suffix = candidate.suffix.lower()
    if not _suffix_allowed(suffix, effective_kinds):
        return None
    if not candidate.is_file():
        return None
    return candidate


def resolve_story_image(subfolder: object, filename: object) -> Path | None:
    """Map a (subfolder, filename) pair from a render manifest to a real file.

    Returns None for anything that isn't a real, existing image file inside
    STORY_IMAGE_ROOT — this is the only thing standing between "the operator
    clicked a generated thumbnail" and this process reading or opening an
    arbitrary path, so every rejection path matters as much as the success
    path.
    """
    return resolve_generated_media("story_comfy", subfolder, filename)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def media_kind_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _VIDEO_CTYPES:
        return "video"
    return "image"


def media_artifact_for(path: Path, *, root_id: str, subfolder: str, filename: str,
                       local_tool: str, prompt_id: str = "",
                       manifest_relpath: str = "") -> dict:
    kind = media_kind_for_path(path)
    return {
        "kind": kind,
        "status": "ready",
        "root": root_id,
        "subfolder": str(subfolder or "").replace("\\", "/"),
        "filename": Path(str(filename)).name,
        "sha256": file_sha256(path),
        "bytes": path.stat().st_size,
        "prompt_id": str(prompt_id or "")[:80],
        "local_tool": str(local_tool or "")[:80],
        "manifest_relpath": str(manifest_relpath or "")[:260],
    }


def pending_comfy_media_artifact(data: dict) -> dict:
    """Locator for a still-running / timed-out job. No filename, no bytes fetch."""
    state = str(data.get("state") or data.get("status") or "pending")
    if state in {"timeout", "running"}:
        state = "pending"
    return {
        "kind": str(data.get("kind") or "image"),
        "status": state,
        "root": "shared_output",
        "subfolder": "",
        "filename": "",
        "sha256": "",
        "bytes": 0,
        "prompt_id": str(data.get("prompt_id") or "")[:80],
        "local_tool": "comfy_job_status",
        "waited_s": data.get("waited_s"),
        "polls": data.get("polls"),
        "note": str(data.get("note") or data.get("reason") or "")[:240],
    }


def collect_story_media_artifacts(tool_name: str, raw_result: str) -> list[dict]:
    """Build media_artifacts from a complete story-image tool result only.

    v1 does not poll Comfy history. Enqueue-only payloads (no outputs, or
    state other than complete) yield an empty list.

    render_story_image_batch returns an aggregate ({"batch": true,
    "completed": [...], "failures": [...], ...}) with no top-level
    state/manifest; each completed[i] carries its own story + manifest in the
    single-job shape, so it goes through the same per-job extraction.
    Each failures[i] becomes its own error card and all pending[] entries
    share one not-started card (see _batch_status_cards), so a half-failed
    batch shows which frames are missing next to the ones that rendered.
    """
    if str(tool_name or "") not in STORY_MEDIA_TOOLS:
        return []
    try:
        data = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    if data.get("batch") is True:
        artifacts: list[dict] = []
        completed = data.get("completed")
        for entry in completed if isinstance(completed, list) else []:
            if isinstance(entry, dict):
                artifacts.extend(_story_job_artifacts(tool_name, entry))
        artifacts.extend(_batch_status_cards(tool_name, data))
        return artifacts
    return _story_job_artifacts(tool_name, data)


def _batch_item_label(entry: dict) -> str:
    preview = " ".join(str(entry.get("prompt_preview") or "").split())
    label = f"batch item {entry.get('index', '?')}"
    return f"{label}: {preview[:100]}" if preview else label


def _batch_failure_note(entry: dict) -> str:
    """Short why for one failed batch job: who holds 8188, or error + last log line."""
    blocked_by = entry.get("blocked_by")
    if isinstance(blocked_by, dict) and blocked_by.get("summary"):
        kind = str(blocked_by.get("kind") or "blocked")
        return f"{kind}: {blocked_by['summary']}"[:240]
    note = str(entry.get("error") or "render failed")
    if entry.get("pid"):
        note += f" (pid {entry['pid']})"
    status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
    tail = str(status.get("log_tail") or "").strip().splitlines()
    if tail:
        note += f" — {tail[-1].strip()}"
    return note[:240]


def _batch_status_cards(tool_name: str, data: dict) -> list[dict]:
    """Error cards for a batch's failed jobs, plus one card for jobs never started.

    Not-started jobs share a single card: with stop_on_failure every job after
    the first failure lands in pending[], and a 20-still batch should not bury
    its real failure under 18 identical "not started" cards. The card lists
    their indexes so the operator can still see exactly which frames are missing.

    These cards have no file, so each carries a card_key; extend_unique_artifacts
    uses it to keep one card per failure when the same batch result is parsed
    twice in a turn (the clipped tool_result and the full internal event).
    """
    cards: list[dict] = []
    failures = data.get("failures")
    for entry in failures if isinstance(failures, list) else []:
        if not isinstance(entry, dict):
            continue
        cards.append({
            "kind": "image", "status": "error", "filename": "", "prompt_id": "",
            "local_tool": str(tool_name), "label": _batch_item_label(entry),
            "note": _batch_failure_note(entry),
            "batch_index": entry.get("index"), "phase": str(entry.get("phase") or ""),
            "card_key": "batch_failure|" + "|".join(str(entry.get(k) or "") for k in (
                "story", "index", "phase", "pid", "error", "prompt_preview")),
        })
    pending = [p for p in (data.get("pending") if isinstance(data.get("pending"), list) else [])
               if isinstance(p, dict)]
    if pending:
        indexes = [str(p.get("index", "?")) for p in pending]
        stories = sorted({str(p.get("story") or "") for p in pending} - {""})
        reason = str(pending[0].get("reason") or "not started")
        cards.append({
            "kind": "image", "status": "not_started", "filename": "", "prompt_id": "",
            "local_tool": str(tool_name),
            "label": (f"batch item {indexes[0]}" if len(indexes) == 1
                      else f"{len(indexes)} batch items ({', '.join(indexes)})")[:160],
            "note": (reason.replace("_", " ") + (f" — story {', '.join(stories)}" if stories else ""))[:240],
            "batch_indexes": [p.get("index") for p in pending],
            "card_key": "batch_pending|" + ",".join(stories) + "|" + ",".join(indexes),
        })
    return cards


def _story_job_artifacts(tool_name: str, data: dict) -> list[dict]:
    """One story-image job's ready files (single-job result or one batch entry)."""
    manifest = data.get("manifest") if isinstance(data.get("manifest"), dict) else data
    if not isinstance(manifest, dict):
        return []
    state = str(data.get("state") or "")
    status = str(manifest.get("status") or "")
    if state and state != "complete":
        return []
    if status and status != "complete":
        return []
    if not state and not status:
        return []
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list):
        return []
    prompt_id = str(manifest.get("prompt_id") or data.get("prompt_id") or "")
    story = str(data.get("story") or manifest.get("story") or "")
    manifest_relpath = ""
    if story and prompt_id:
        manifest_relpath = f"outputs/stories/{story}/manifests/image_{prompt_id}.json"
    artifacts: list[dict] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        subfolder = str(item.get("subfolder") or "").replace("\\", "/")
        path = resolve_generated_media("story_comfy", subfolder, filename)
        if path is None:
            continue
        artifacts.append(media_artifact_for(
            path, root_id="story_comfy", subfolder=subfolder,
            filename=str(filename), local_tool=str(tool_name),
            prompt_id=prompt_id, manifest_relpath=manifest_relpath))
    return artifacts


def collect_comfy_media_artifacts(tool_name: str, raw_result: str) -> list[dict]:
    """Build media_artifacts from comfy_job_status. Enqueue-only generate is ignored.

    complete + resolved Shared-output files → ready locators (image or video).
    pending / running / timeout → one pending locator (no filename, no GET).
    error / missing files → empty (honest tool JSON, no broken card).
    """
    if str(tool_name or "") not in COMFY_MEDIA_TOOLS:
        return []
    try:
        data = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    state = str(data.get("state") or data.get("status") or "")
    if state in {"pending", "running", "timeout"}:
        return [pending_comfy_media_artifact(data)]
    if state != "complete":
        return []
    prompt_id = str(data.get("prompt_id") or "")
    outputs = data.get("outputs")
    if not isinstance(outputs, list):
        return []
    artifacts: list[dict] = []
    for item in outputs:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        subfolder = str(item.get("subfolder") or "").replace("\\", "/")
        path = resolve_generated_media(
            "shared_output", subfolder, filename, kinds="media")
        if path is None:
            continue
        artifacts.append(media_artifact_for(
            path, root_id="shared_output", subfolder=subfolder,
            filename=str(filename), local_tool=str(tool_name),
            prompt_id=prompt_id))
    return artifacts


def chat_render_job_dir(value: object) -> Path | None:
    """An existing <CHAT_RENDER_JOBS_ROOT>/<cid>/<job> folder, else None.

    Accepts the absolute job_folder a launch result reports or a path relative
    to the jobs root (what a render watch stores). Anything else — another
    operator-supplied batch folder, outputs/equal_shares, a deeper or
    shallower path — is not a chat render job and is never watched or served.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        raw = Path(text)
        job = (raw if raw.is_absolute() else CHAT_RENDER_JOBS_ROOT / raw).resolve()
        rel = job.relative_to(CHAT_RENDER_JOBS_ROOT)
    except (OSError, ValueError):
        return None
    if len(rel.parts) != 2 or not job.is_dir():
        return None
    return job


def collect_chat_render_media_artifacts(job: Path, manifest: object, *,
                                        local_tool: str = "start_current_chat_render"
                                        ) -> list[dict]:
    """Ready video cards for the "done" entries of a chat job's batch_manifest.json.

    work/batch_render_folder.py records each finished take as
    renders[<key>] = {"status": "done", "output_path": <job>/renders/<key>.mp4};
    failed / invalid / error entries have no file and yield nothing here.
    """
    renders = manifest.get("renders") if isinstance(manifest, dict) else None
    if not isinstance(renders, dict):
        return []
    try:
        rel_job = job.resolve().relative_to(CHAT_RENDER_JOBS_ROOT).as_posix()
    except (OSError, ValueError):
        return []
    subfolder = f"{rel_job}/renders"
    renders_dir = CHAT_RENDER_JOBS_ROOT / rel_job / "renders"
    artifacts: list[dict] = []
    for key in sorted(renders):
        entry = renders[key]
        if not isinstance(entry, dict) or entry.get("status") != "done":
            continue
        output = Path(str(entry.get("output_path") or ""))
        if not output.name or not _path_under(output, renders_dir):
            continue
        path = resolve_generated_media("chat_render", subfolder, output.name, kinds="video")
        if path is None:
            continue
        art = media_artifact_for(
            path, root_id="chat_render", subfolder=subfolder, filename=path.name,
            local_tool=local_tool,
            manifest_relpath=f"local_agent/render_jobs/{rel_job}/batch_manifest.json")
        art["label"] = f"render {key}"
        artifacts.append(art)
    return artifacts


def collect_media_artifacts(tool_name: str, raw_result: str) -> list[dict]:
    """Story stills (v1) plus comfy_job_status Shared output (v2)."""
    if str(tool_name or "") in STORY_MEDIA_TOOLS:
        return collect_story_media_artifacts(tool_name, raw_result)
    if str(tool_name or "") in COMFY_MEDIA_TOOLS:
        return collect_comfy_media_artifacts(tool_name, raw_result)
    return []


def media_artifact_key(art: dict) -> tuple:
    """Identity of one generated file, for de-duplicating cards within a chat.

    A file-less card that names its own card_key (batch failure / not-started
    cards) is identified by that key instead.
    """
    if not art.get("filename") and art.get("card_key"):
        return ("card", str(art["card_key"]))
    return (str(art.get("root") or ""), str(art.get("subfolder") or ""),
            str(art.get("filename") or ""), str(art.get("sha256") or ""))


def _has_card_identity(art: dict) -> bool:
    return bool(art.get("filename") or art.get("card_key"))


def extend_unique_artifacts(target: list[dict], new: list[dict]) -> list[dict]:
    """Append artifacts not already in target. Returns what was added.

    A turn can surface the same still more than once (a batch result, then a
    story_image_job_status poll on the same job); the operator should see one
    card per file. Batch failure cards carry a card_key and are de-duplicated
    the same way. Other pending/error locators have no identity and always pass.
    """
    seen = {media_artifact_key(a) for a in target if _has_card_identity(a)}
    added: list[dict] = []
    for art in new:
        key = media_artifact_key(art)
        if _has_card_identity(art):
            if key in seen:
                continue
            seen.add(key)
        target.append(art)
        added.append(art)
    return added


def generated_media_payload(root_id: object, subfolder: object, filename: object,
                            expected_sha256: object = None) -> tuple[object, int, str]:
    """Re-resolve a stored locator. Missing → 404 JSON; hash mismatch → 409 JSON."""
    path = resolve_generated_media(root_id, subfolder, filename,
                                   kinds=media_kinds_for_root(root_id))
    if path is None:
        return ({"error": "file missing", "status": "missing"}, 404, "application/json")
    expected = str(expected_sha256 or "").strip().lower()
    if expected:
        actual = file_sha256(path)
        if actual != expected:
            return ({"error": "file changed on disk since this turn; not showing a substitute",
                     "status": "hash_mismatch"}, 409, "application/json")
    suffix = path.suffix.lower()
    ctype = _IMAGE_CTYPES.get(suffix) or _VIDEO_CTYPES.get(suffix)
    if not ctype:
        return ({"error": "file missing", "status": "missing"}, 404, "application/json")
    return (path.read_bytes(), 200, ctype)


# Operator-visible activity trace. Sibling of tracing.py (investigator SQLite);
# this list is persisted on the assistant message and restored by the GUI.
# Never add trace_id. Never store raw tool argument bodies or thinking text.
_ACTIVITY_LIMIT = 48
_ACTIVITY_SUMMARY_CHARS = 240
_EVIDENCE_COPY_KEYS = ("path", "valid", "reason", "records", "file_changed",
                       "repaired", "next_step")


def _clip_activity(value, limit: int = _ACTIVITY_SUMMARY_CHARS) -> str:
    return str(value or "").replace("\n", " ")[:limit]


def redact_activity_args(args) -> dict:
    """Persist tool-arg receipts the same way remote audits do: keys + hash, no bodies."""
    if not isinstance(args, dict):
        args = {}
    return remote_security._redact_args(args)


def classify_activity_note(text: str) -> str:
    """Map a free-text `note` onto a lifecycle kind. Unknown notes stay live-only."""
    low = str(text or "").lower()
    if "task plan prepared" in low:
        return "planning"
    if ("permission is pending" in low or "awaiting approval" in low
            or "waiting for gpu permission" in low or "file edit pending" in low):
        return "waiting_for_permission"
    if "hop limit" in low or "hop-limit" in low:
        return "blocked"
    return ""


def _copy_hop(event: dict, payload: dict) -> dict:
    """Copy hop when present (including JSON null). Ignore if missing (old chats)."""
    if "hop" in payload:
        hop = payload["hop"]
        if hop is None or isinstance(hop, int):
            event["hop"] = hop
        return event
    hop = payload.get("hop_index")
    if isinstance(hop, int) and hop >= 0:
        event["hop"] = hop
    return event


def activity_from_sse(kind: str, data: str) -> dict | None:
    """Map one live SSE event to a redacted lifecycle card for persistence.

    Intention (`tool` announce, planner notes, drafting progress) is tagged
    `source=proposal` / `state=announced` so the GUI cannot treat a plan as
    proof the action ran. Observed results use `source=observation`.
    """
    kind = str(kind or "")
    if kind == "route":
        try:
            route = json.loads(data) if data else {}
        except Exception:
            route = {}
        if not isinstance(route, dict):
            route = {}
        detail = route.get("detail") if isinstance(route.get("detail"), dict) else {}
        proposal = str(route.get("source") or "") == "proposal"
        event = {
            "kind": "route",
            "state": "announced" if proposal else "result",
            "source": "proposal" if proposal else "observation",
            "tier": str(route.get("tier") or "")[:24],
            "model": str(route.get("model") or "")[:120],
            "backend": str(route.get("backend") or "")[:40],
            "reason": _clip_activity(route.get("reason")),
            "gpu_busy": bool(route.get("gpu_busy")),
            "capability": str(detail.get("capability") or "")[:40],
            "host": str(route.get("host") or "")[:80],
            "label": _clip_activity(
                "attempting farm" if proposal else
                f"{route.get('tier') or ''} {route.get('model') or ''}".strip()),
        }
        _copy_hop(event, route)
        return event
    if kind == "progress":
        payload: dict
        try:
            parsed = json.loads(data) if isinstance(data, str) and data.lstrip().startswith("{") else None
            payload = parsed if isinstance(parsed, dict) else {"label": data}
        except Exception:
            payload = {"label": data}
        stage = str(payload.get("stage") or "")
        label = _clip_activity(payload.get("label") or data)
        if stage in ("decide", "review"):
            event = {"kind": "planning", "state": "announced", "source": "proposal",
                     "label": label, "stage": stage}
            return _copy_hop(event, payload)
        if stage == "write":
            event = {"kind": "planning", "state": "announced", "source": "proposal",
                     "label": label or "Drafting the answer — not yet complete",
                     "stage": stage}
            return _copy_hop(event, payload)
        if stage == "evidence":
            event = {"kind": "verification", "state": "announced", "source": "observation",
                     "label": label, "stage": stage}
            return _copy_hop(event, payload)
        return None
    if kind == "tool":
        try:
            tool_data = json.loads(data) if data else {}
        except Exception:
            tool_data = {}
        if not isinstance(tool_data, dict):
            tool_data = {}
        args = tool_data.get("args") if isinstance(tool_data.get("args"), dict) else {}
        name = str(tool_data.get("tool") or "unknown")[:80]
        event = {
            "kind": "tool_call",
            "state": "announced",
            "source": "proposal",
            "tool": name,
            "label": name,
            "args": redact_activity_args(args),
        }
        return _copy_hop(event, tool_data)
    if kind == "tool_result":
        text = str(data)
        stripped = text.lstrip()
        outcome = "error" if stripped.startswith(("ERROR:", "REFUSED")) else "result"
        event = {
            "kind": "tool_result",
            "state": "error" if outcome == "error" else "result",
            "source": "observation",
            "outcome": outcome,
            "summary": _clip_activity(text),
            "label": outcome,
        }
        try:
            parsed = json.loads(data)
            if isinstance(parsed, dict):
                for key in _EVIDENCE_COPY_KEYS:
                    if key in parsed:
                        value = parsed[key]
                        if isinstance(value, str):
                            value = value[:520]
                        event[key] = value
        except Exception:
            pass
        return event
    if kind == "queued":
        try:
            queued = json.loads(data) if isinstance(data, str) and data.lstrip().startswith("{") else {"reason": data}
        except Exception:
            queued = {"reason": data}
        if not isinstance(queued, dict):
            queued = {"reason": str(data)}
        return {
            "kind": "queued",
            "state": "announced",
            "source": "observation",
            "label": _clip_activity(queued.get("reason") or "GPU busy"),
            "job_id": str(queued.get("job_id") or "")[:80],
        }
    if kind == "note":
        mapped = classify_activity_note(str(data))
        if mapped == "planning":
            return {"kind": "planning", "state": "announced", "source": "proposal",
                    "label": _clip_activity(data)}
        if mapped == "waiting_for_permission":
            return {"kind": "waiting_for_permission", "state": "announced",
                    "source": "observation", "label": _clip_activity(data)}
        if mapped == "blocked":
            return {"kind": "blocked", "state": "error", "source": "observation",
                    "label": _clip_activity(data)}
        return None
    if kind == "error":
        return {"kind": "blocked", "state": "error", "source": "observation",
                "label": _clip_activity(data)}
    if kind == "done":
        return {"kind": "complete", "state": "result", "source": "observation",
                "label": "Turn complete"}
    return None


def activity_from_tool_evidence(evidence) -> list[dict]:
    """Restore observation cards from stored tool_evidence when `activity` is absent.

    Evidence is an observed receipt. This never invents an announced intention.
    """
    out: list[dict] = []
    if not isinstance(evidence, list):
        return out
    for item in evidence:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "unknown")[:80]
        outcome = str(item.get("outcome") or "result")[:24]
        event = {
            "kind": "tool_result",
            "state": "error" if outcome == "error" else "result",
            "source": "observation",
            "tool": tool,
            "outcome": outcome,
            "summary": str(item.get("summary") or "")[:_ACTIVITY_SUMMARY_CHARS],
            "label": tool,
        }
        for key in _EVIDENCE_COPY_KEYS:
            if key in item:
                event[key] = item[key]
        out.append(event)
    return out


def restore_activity(message: dict | None) -> list[dict]:
    """Events the GUI should render for one stored assistant message."""
    if not isinstance(message, dict):
        return []
    activity = message.get("activity")
    if isinstance(activity, list) and activity:
        events = [item for item in activity if isinstance(item, dict)]
        return reconcile_queued_activity(events)
    return activity_from_tool_evidence(message.get("tool_evidence"))


_QUEUED_TERMINAL = frozenset({"done", "failed", "cancelled"})


def restamp_queued_event(event: dict, job: dict) -> dict:
    """Turn an announced queue card into an observed receipt. Never invents a filename."""
    status = str(job.get("status") or "")
    out = dict(event)
    out["kind"] = "queued"
    out["source"] = "observation"
    out["job_id"] = str(job.get("id") or event.get("job_id") or "")[:80]
    out["job_status"] = status
    out.pop("filename", None)
    if status == "done":
        out["state"] = "result"
        out["label"] = "media job complete"
        out["summary"] = _clip_activity(job.get("result"))
    elif status == "failed":
        out["state"] = "error"
        out["label"] = "media job failed"
        out["summary"] = _clip_activity(job.get("error"))
    else:
        out["state"] = "error"
        out["label"] = "media job cancelled"
        out["summary"] = _clip_activity(job.get("cancel_reason") or "cancelled")
    return out


def reconcile_queued_activity(activity) -> list:
    """Restamp announced queued cards from media_queue/{done,failed,cancelled}.

    Pending/processing jobs stay announced. The watcher already writes those
    files; this is the chat/GUI read path so a later GET /api/chat or openChat
    sees completion without a watcher SSE push.
    """
    if not isinstance(activity, list):
        return []
    import media_queue as mq
    out: list = []
    for item in activity:
        if not isinstance(item, dict):
            continue
        if item.get("kind") != "queued" or item.get("state") != "announced":
            out.append(item)
            continue
        job_id = str(item.get("job_id") or "").strip()
        if not job_id:
            out.append(item)
            continue
        try:
            job = mq.get(job_id)
        except Exception:
            job = None
        if not job or job.get("status") not in _QUEUED_TERMINAL:
            out.append(item)
            continue
        out.append(restamp_queued_event(item, job))
    return out


def reconcile_conversation_activity(conv: dict | None) -> bool:
    """Patch queued cards on a loaded conversation. Returns True if anything changed."""
    if not isinstance(conv, dict):
        return False
    changed = False
    for message in conv.get("messages") or []:
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        activity = message.get("activity")
        if not isinstance(activity, list) or not activity:
            continue
        restamped = reconcile_queued_activity(activity)
        if restamped != activity:
            message["activity"] = restamped
            changed = True
    return changed


# Generations the operator has asked to stop, by conversation id.
_stops: set[str] = set()
_stop_lock = threading.Lock()
_instance_mutex = None
_STATUS_TTL_SECONDS = 2.0
_status_cache: dict | None = None
_status_cache_at = 0.0
_status_lock = threading.Lock()


def _parse_ctx_ceiling(value) -> int | None:
    """Parse the GUI context-ceiling select. Returns None for Auto or any invalid value."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n < 4096 or n > 32768:
        return None
    return n


def app_status() -> dict:
    """Return a short-lived status snapshot without stampeding Ollama.

    The browser polls status frequently, while ``router.status()`` probes both
    Ollama endpoints several times.  During a server restart those overlapping
    probes can accumulate abandoned loopback sockets and make the GUI appear
    offline.  A two-second snapshot is fresh enough for the status badge and
    preserves the authoritative per-turn routing check in ``agent.answer()``.
    """
    global _status_cache, _status_cache_at
    now = time.monotonic()
    with _status_lock:
        if _status_cache is not None and now - _status_cache_at < _STATUS_TTL_SECONDS:
            return dict(_status_cache)
        status = router.status()
        status["app_revision"] = APP_REVISION
        status["knowledge_pack"] = agent.KNOWLEDGE.is_file()
        status["actions"] = list(tools.TOOLS)
        status["gpu_gateway"] = gpu_gate.snapshot()
        status["file_edit_gateway"] = file_edit_gate.snapshot()
        # This is read-only. The controller is disabled by default and has no
        # HTTP mutation route, so a status poll cannot start a verification run.
        status["loop_engineering"] = loop_controller.snapshot()
        _status_cache = dict(status)
        _status_cache_at = now
        return status


def yield_gpu() -> dict:
    """Evict every model resident on the GPU server. Safe when nothing is loaded."""
    if not router.up(router.GPU_HOST):
        return {"freed": [], "vram_mb": None, "message": "GPU Ollama server is not reachable"}
    gpu_tags = router._tags(router.GPU_HOST)
    resident = router._running_models(router.GPU_HOST) or []
    preferred = router._pick(gpu_tags, router.GPU_MODELS)
    to_unload = list(dict.fromkeys(resident + ([preferred] if preferred and preferred not in resident else [])))
    freed = []
    for m in to_unload:
        router.unload(router.GPU_HOST, m)
        freed.append(m)
    used_mb, _ = router.gpu_memory()
    msg = (f"Evicted: {', '.join(freed)}." if freed
           else "Nothing was resident — GPU VRAM already clear.")
    return {"freed": freed, "vram_mb": used_mb, "message": msg}


def reveal_generated_media(root_id: object, subfolder: object,
                           filename: object) -> tuple[dict, int]:
    """Open Explorer on an allow-listed generated file. Same resolver as GET."""
    path = resolve_generated_media(root_id, subfolder, filename,
                                   kinds=media_kinds_for_root(root_id))
    if path is None:
        return {"error": "file not found or not an allow-listed generated file"}, 404
    if not _IS_WINDOWS:
        return {"error": "opening File Explorer is only supported on Windows"}, 400
    try:
        subprocess.Popen(["explorer", "/select,", str(path)])
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}, 500
    return {"opened": True, "path": str(path)}, 200


def reveal_story_image(subfolder: object, filename: object) -> tuple[dict, int]:
    """Open Windows Explorer with a real, already-rendered image pre-selected."""
    return reveal_generated_media("story_comfy", subfolder, filename)


def cancel_media_queue_job(job_id: object) -> tuple[dict, int]:
    """Validate and cancel one media job; deliberately cannot target renders."""
    import media_queue as mq
    identifier = str(job_id or "").strip()
    if not identifier:
        return {"ok": False, "error": "media job id is required"}, 400
    result = mq.cancel(identifier)
    return result, 200 if result.get("ok") else 404


# ── render watches: announce background renders that land after the turn ────
# render_story_image and comfy_generate return as soon as the job is launched,
# so if the agent's turn ends first nothing ever tells the operator the file
# landed. media_queue is deliberately not reused: it is a work queue the media
# watcher *claims* (vision/transcribe), so a render parked there would sit
# "pending" forever and "Clear queue" would mark it cancelled without stopping
# anything. This is a small status registry instead: registered from the full
# tool result during a turn, resolved by the GUI's /api/render_watch poll
# once that chat's turn has ended (an active turn surfaces its own cards).
RENDER_WATCH_PATH = HERE / "runtime" / "render_watch.json"
_RENDER_WATCH_MAX_AGE_S = 2 * 3600   # stop waiting on a job that never reports
# A chat video batch runs every prompt in turn, each attempt allowed 120 min by
# the runner plus thermal cool-downs, so 2 h would expire a healthy job. Its
# watch resolves as soon as the runner PID exits; this cap only ends a watch
# whose PID Windows has since reused.
_CHAT_RENDER_WATCH_MAX_AGE_S = 72 * 3600
# start_current_chat_render nests the start_batch_render result under "launch";
# a bare start_batch_render is watched only when its folder is a chat job.
CHAT_RENDER_WATCH_TOOLS = frozenset({"start_current_chat_render", "start_batch_render"})
_BATCH_DONE_MARKER = "Batch complete:"   # last line work/batch_render_folder.py logs
_RENDER_WATCH_KEEP_S = 24 * 3600     # finished records kept for a late tab
_RENDER_WATCH_CHECK_TTL_S = 5.0      # several tabs polling must not stampede tasklist
_render_watch_lock = threading.Lock()
_render_watch_checked_at = 0.0
_active_turns: set[str] = set()
_active_turns_lock = threading.Lock()


def _load_render_watches() -> list[dict]:
    try:
        data = json.loads(RENDER_WATCH_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [w for w in data if isinstance(w, dict)] if isinstance(data, list) else []


def _save_render_watches(watches: list[dict]) -> None:
    RENDER_WATCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(RENDER_WATCH_PATH, json.dumps(watches, indent=2, default=str))


def register_render_watch(cid: str, tool_name: str, raw_result: str) -> dict | None:
    """Remember a just-launched background render so its completion can be announced."""
    if not cid:
        return None
    watch = None
    if tool_name == "render_story_image":
        try:
            data = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        if isinstance(data, dict) and data.get("started") and data.get("pid"):
            story = str(data.get("story") or "")
            watch = {"id": f"story:{data['pid']}:{story}", "kind": "story_image",
                     "label": story, "story": story, "pid": int(data["pid"]),
                     "log": str(data.get("log") or "")}
    elif tool_name == "comfy_generate":
        prompt_id = tools._extract_prompt_id(raw_result)
        if prompt_id:
            watch = {"id": f"comfy:{prompt_id}", "kind": "comfy",
                     "label": f"prompt {prompt_id}", "prompt_id": str(prompt_id)}
    elif tool_name in CHAT_RENDER_WATCH_TOOLS:
        watch = _chat_render_watch(raw_result)
    if not watch:
        return None
    watch.update({"cid": str(cid), "status": "running", "started_at": time.time()})
    with _render_watch_lock:
        watches = [w for w in _load_render_watches() if w.get("id") != watch["id"]]
        watches.append(watch)
        _save_render_watches(watches)
    return watch


def _chat_render_watch(raw_result: str) -> dict | None:
    """Watch record for a started chat video batch, or None.

    Identified by the runner PID plus its job folder (stored relative to the
    jobs root). Completion is observed read-only afterwards: the PID, the
    runner's own log in <job>/batch_runtime/logs/, and <job>/batch_manifest.json.
    """
    try:
        data = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    launch = data.get("launch") if isinstance(data.get("launch"), dict) else data
    if not (launch.get("started") and launch.get("pid")):
        return None
    job = chat_render_job_dir(launch.get("job_folder"))
    if job is None:
        return None
    try:
        pid = int(launch["pid"])
        planned = int(launch.get("planned_renders") or 0)
        limit = int(launch.get("limit") or 0)
    except (TypeError, ValueError):
        return None
    rel = job.relative_to(CHAT_RENDER_JOBS_ROOT).as_posix()
    log = Path(str(launch.get("log") or ""))
    log_name = log.name if log.name and _path_under(log, job / "batch_runtime" / "logs") else ""
    return {"id": f"chat_render:{pid}:{rel}", "kind": "chat_render",
            "label": f"video job {job.name}", "pid": pid, "job": rel, "log": log_name,
            "expected": min(planned, limit) if planned and limit else planned}


def _batch_log_tail(job: Path, log_name: object, limit: int = 4096) -> str:
    name = str(log_name or "")
    if not name or Path(name).name != name:
        return ""
    try:
        with (job / "batch_runtime" / "logs" / name).open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            handle.seek(max(0, handle.tell() - limit))
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _check_chat_render_watch(watch: dict) -> tuple[str, list[dict], str]:
    """Read-only: running until the runner exits, then its manifest's finished videos."""
    job = chat_render_job_dir(watch.get("job"))
    if job is None:
        return "failed", [], "the render job folder is no longer present"
    tail = _batch_log_tail(job, watch.get("log"))
    if _BATCH_DONE_MARKER not in tail and tools._pid_is_live(watch.get("pid")):
        return "running", [], ""
    try:
        manifest = json.loads((job / "batch_manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    arts = collect_chat_render_media_artifacts(job, manifest)
    renders = manifest.get("renders") if isinstance(manifest, dict) else None
    problems = [(key, entry) for key, entry in sorted((renders or {}).items())
                if isinstance(entry, dict) and entry.get("status") != "done"]
    detail = "; ".join(
        f"{key} {entry.get('status')}: "
        f"{entry.get('error') or ', '.join(map(str, entry.get('errors') or [])) or 'no detail'}"
        for key, entry in problems[:3])
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    if not arts:
        # A crash before any render is recorded (e.g. ComfyUI failing to start)
        # leaves only the runner's traceback, whose last line names the error.
        return "failed", [], (detail or (lines[-1] if lines else
                                         "the runner exited without finishing a render"))[:240]
    expected = int(watch.get("expected") or 0)
    if not problems and len(arts) >= expected:
        return "complete", arts, ""
    note = (f"{len(arts)} of {max(expected, len(arts) + len(problems))} renders done"
            + (f"; {detail}" if detail else ""))[:240]
    partial = {"kind": "video", "status": "error", "filename": "", "prompt_id": "",
               "local_tool": "chat_render", "label": watch.get("label"), "note": note,
               "card_key": f"chat_render_partial|{watch.get('id')}"}
    return "complete", arts + [partial], note


def _check_render_watch(watch: dict, now: float) -> tuple[str, list[dict], str]:
    """(status, artifacts, note) for one open watch; status running/complete/failed/expired."""
    max_age = _RENDER_WATCH_MAX_AGE_S
    try:
        if watch.get("kind") == "chat_render":
            max_age = _CHAT_RENDER_WATCH_MAX_AGE_S
            status, arts, note = _check_chat_render_watch(watch)
            if status != "running":
                return status, arts, note
        elif watch.get("kind") == "story_image":
            raw = tools.story_image_job_status({
                "story": watch.get("story"), "pid": watch.get("pid"), "log": watch.get("log")})
            data = json.loads(raw)
            state = str(data.get("state") or "")
            if state == "complete":
                arts = collect_story_media_artifacts("story_image_job_status", raw)
                if arts:
                    return "complete", arts, ""
                return "failed", [], "manifest is complete but its output file was not found"
            if state == "finished_or_crashed":
                tail = str(data.get("log_tail") or "").strip().splitlines()
                return "failed", [], (tail[-1] if tail else "process exited without a manifest")[:240]
        elif watch.get("kind") == "comfy":
            raw = tools.comfy_job_status({"prompt_id": watch.get("prompt_id"), "timeout_s": 0})
            data = json.loads(raw)
            state = str(data.get("state") or "")
            if state == "complete":
                arts = collect_comfy_media_artifacts("comfy_job_status", raw)
                if arts:
                    return "complete", arts, ""
                return "failed", [], "ComfyUI reports complete but no output file was found"
            if state == "error":
                return "failed", [], str(data.get("error") or data.get("note") or "ComfyUI error")[:240]
    except Exception as exc:
        # A transient status failure (Comfy briefly down) keeps waiting until expiry.
        watch["last_check_error"] = f"{type(exc).__name__}: {exc}"[:240]
    if now - float(watch.get("started_at") or now) > max_age:
        return "expired", [], (f"no completion reported within {max_age // 3600} hours; "
                               "check the render log")
    return "running", [], ""


def _attach_late_artifacts(cid: str, watch_id: str, arts: list[dict]) -> tuple[list[dict], str]:
    """Persist late cards onto the chat's latest assistant message so a reload keeps them.

    Returns (artifacts actually added, chat title). A file the turn already
    showed inline (the agent awaited it itself) is not added a second time.
    """
    added: list[dict] = []
    title = ""

    def _apply(conv: dict):
        nonlocal title
        title = str(conv.get("title") or "")
        messages = [m for m in conv.get("messages") or []
                    if isinstance(m, dict) and m.get("role") == "assistant"]
        if not messages:
            return False
        existing = [a for m in messages for a in (m.get("media_artifacts") or [])
                    if isinstance(a, dict)]
        target = messages[-1]
        if not isinstance(target.get("media_artifacts"), list):
            target["media_artifacts"] = []
        stamped = [dict(a, watch_id=watch_id, late=True) for a in arts]
        added.extend(extend_unique_artifacts(existing, stamped))
        if not added:
            return False
        target["media_artifacts"].extend(added)
        return None

    store.mutate(cid, _apply)
    return added, title


def poll_render_watches(*, force: bool = False) -> dict:
    """Resolve open watches whose chat is idle, prune old records, return the list."""
    global _render_watch_checked_at
    now = time.time()
    with _active_turns_lock:
        busy_chats = set(_active_turns)
    with _render_watch_lock:
        watches = _load_render_watches()
        changed = False
        if force or time.monotonic() - _render_watch_checked_at >= _RENDER_WATCH_CHECK_TTL_S:
            _render_watch_checked_at = time.monotonic()
            for watch in watches:
                if watch.get("status") != "running" or watch.get("cid") in busy_chats:
                    continue
                status, arts, note = _check_render_watch(watch, now)
                if status == "running":
                    continue
                if status != "complete":
                    arts = [{"kind": "video" if watch.get("kind") == "chat_render" else "image",
                             "status": "error", "filename": "",
                             "prompt_id": str(watch.get("prompt_id") or "")[:80],
                             "local_tool": watch.get("kind"), "label": watch.get("label"),
                             "note": note}]
                added, title = _attach_late_artifacts(str(watch.get("cid") or ""),
                                                      str(watch.get("id")), arts)
                watch.update({"status": status, "finished_at": now, "note": note,
                              "artifacts": added, "title": title})
                changed = True
        kept = [w for w in watches if w.get("status") == "running"
                or now - float(w.get("finished_at") or now) < _RENDER_WATCH_KEEP_S]
        if changed or len(kept) != len(watches):
            _save_render_watches(kept)
    public = ("id", "cid", "kind", "label", "status", "started_at", "finished_at",
              "note", "artifacts", "title")
    return {"now": now, "watches": [{k: w.get(k) for k in public} for w in kept]}


def _claim_single_instance() -> bool:
    """Use a named Windows mutex because Windows permits duplicate TCP binds.

    Keeping the handle in a module global holds the claim for the process
    lifetime. On non-Windows the socket bind remains the single-instance gate.
    """
    global _instance_mutex
    if os.name != "nt":
        return True
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "Local\\EqualSharesLocalAgent8760")
    if not handle:
        raise OSError(ctypes.get_last_error(), "could not create local-agent mutex")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return False
    _instance_mutex = handle
    return True


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _csrf_cookie(self) -> None:
        self.send_header(
            "Set-Cookie",
            f"la_csrf={SESSION_CSRF}; Path=/; SameSite=Strict",
        )

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        return host in _LOCAL_HOSTS

    def _origin_ok(self) -> bool:
        origin = (self.headers.get("Origin") or "").strip().rstrip("/")
        return origin in _LOCAL_ORIGINS

    def _json_content_type(self) -> bool:
        raw = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        return raw == "application/json"

    def _csrf_ok(self) -> bool:
        header = (self.headers.get("X-CSRF-Token") or "").strip()
        cookie = ""
        for part in (self.headers.get("Cookie") or "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == "la_csrf":
                cookie = value.strip()
                break
        if not header or not cookie:
            return False
        return (hmac.compare_digest(header, SESSION_CSRF)
                and hmac.compare_digest(cookie, SESSION_CSRF))

    def _reject(self, code: int, message: str) -> None:
        body = json.dumps({"error": message}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _mutation_guard(self) -> bool:
        """True when this state-changing request is allowed to proceed."""
        if not self._host_ok():
            self._reject(403, "host is not a local application host")
            return False
        if not self._origin_ok():
            self._reject(403, "origin is not a local application origin")
            return False
        if not self._json_content_type():
            self._reject(415, "content type must be application/json")
            return False
        if not self._csrf_ok():
            self._reject(403, "missing anti-forgery credential")
            return False
        return True

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._csrf_cookie()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode(), "application/json")

    # ── GET ──────────────────────────────────────────────────────────────────
    def do_OPTIONS(self) -> None:
        self._reject(403, "cross-origin requests are not allowed")

    def do_GET(self) -> None:
        if not self._host_ok():
            self._reject(403, "host is not a local application host")
            return
        u = urlparse(self.path)
        q = parse_qs(u.query)

        if u.path in ("/", "/index.html"):
            if not INDEX.is_file():
                self._send(500, b"static/index.html missing", "text/plain")
                return
            self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")

        elif u.path == "/api/status":
            self._json(app_status())

        elif u.path == "/api/media_queue":
            import media_queue as mq
            self._json(mq.list_queue())

        elif u.path == "/api/render_watch":
            self._json(poll_render_watches())

        elif u.path == "/api/gpu_gateway":
            self._json({"gateway": gpu_gate.snapshot(), "status": router.status()})

        elif u.path == "/api/file_edit_gateway":
            self._json(file_edit_gate.snapshot())

        elif u.path == "/api/loop_engineering":
            self._json(loop_controller.snapshot())

        elif u.path == "/api/exemplars/pending":
            self._json(exemplar_curator.pending())

        elif u.path in ("/api/story_image_file", "/api/generated_media"):
            root_id = (q.get("root") or ["story_comfy"])[0]
            if u.path == "/api/story_image_file":
                root_id = "story_comfy"
            body, code, ctype = generated_media_payload(
                root_id,
                (q.get("subfolder") or [""])[0],
                (q.get("filename") or [""])[0],
                (q.get("sha256") or [""])[0],
            )
            if ctype == "application/json":
                self._json(body, code)
                return
            self._send(code, body, ctype)

        elif u.path == "/api/state":
            self._send(200, tools.call("project_state", {}).encode(), "application/json")

        elif u.path == "/api/chats":
            self._json(store.listing())

        elif u.path == "/api/chat":
            cid = (q.get("id") or [""])[0]

            def _reconcile(loaded: dict):
                if reconcile_conversation_activity(loaded):
                    return loaded
                return False

            conv = store.mutate(cid, _reconcile)
            self._json(conv or {"error": "not found"}, 200 if conv else 404)

        else:
            self._send(404, b"not found", "text/plain")

    # ── POST ─────────────────────────────────────────────────────────────────
    def do_POST(self) -> None:
        if not self._mutation_guard():
            return
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length", 0))
        if n > MAX_JSON_BYTES:
            self._json({"error": "request too large; media uploads are capped at 75 MB"}, 413)
            return
        try:
            p = json.loads(self.rfile.read(n) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json({"error": "invalid JSON request"}, 400)
            return

        if u.path == "/api/upload":
            self._upload(p)
        elif u.path == "/api/reveal_story_image":
            result, code = reveal_generated_media(
                p.get("root") or "story_comfy",
                p.get("subfolder"), p.get("filename"))
            self._json(result, code)
        elif u.path == "/api/send":
            self._send_turn(p)
        elif u.path == "/api/new":
            try:
                if wants_auto_farm(p.get("model")):
                    self._json(store.create(p.get("first", ""), model="",
                                            workspace=p.get("workspace", "auto"),
                                            routing=AUTO_FARM_ROUTING))
                else:
                    model = self._valid_chat_model(p.get("model"))
                    if not model:
                        self._json({"error": "choose an available chat model"}, 400)
                        return
                    self._json(store.create(p.get("first", ""), model=model,
                                            workspace=p.get("workspace", "auto")))
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
        elif u.path == "/api/rename":
            self._json({"ok": store.rename(p.get("id", ""), p.get("title", ""))})
        elif u.path == "/api/delete":
            self._json({"ok": store.delete(p.get("id", ""))})
        elif u.path == "/api/stop":
            with _stop_lock:
                _stops.add(p.get("id", ""))
            self._json({"ok": True})
        elif u.path == "/api/regenerate":
            # Drop the last assistant reply, then re-answer from the same point.
            conv = store.load(p.get("id", ""))
            if not conv or not conv["messages"]:
                self._json({"error": "nothing to regenerate"}, 400)
                return
            msgs = conv["messages"]
            last_user = max((i for i, m in enumerate(msgs) if m["role"] == "user"),
                            default=None)
            if last_user is None:
                self._json({"error": "no user message"}, 400)
                return
            store.truncate_after(conv["id"], last_user)
            self._send_turn({"id": conv["id"], "message": None, "prefer": p.get("prefer", "auto")})
        elif u.path == "/api/action":
            self._json({"result": tools.call(p.get("action", ""), p.get("args") or {})})
        elif u.path == "/api/feedback":
            try:
                self._json(feedback.submit(p.get("id", ""), p.get("verdict", ""),
                                           p.get("correction", ""),
                                           mode=p.get("mode", "rule_only"),
                                           category=p.get("category", ""),
                                           exemplar_ids=p.get("exemplar_ids")))
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
        elif u.path == "/api/intent_mismatch":
            try:
                self._json(intent_mismatch.capture(p.get("id", ""),
                                                   p.get("message_index")))
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
        elif u.path == "/api/exemplars/stage":
            try:
                self._json({"ok": True, "item": exemplar_curator.stage(p.get("item") or {})})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
        elif u.path == "/api/exemplars/review":
            try:
                self._json({"ok": True, "item": exemplar_curator.review(
                    p.get("id", ""), p.get("action", ""), content=p.get("content"))})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
        elif u.path == "/api/exemplars/sync":
            self._json(exemplar_embeddings.sync_approved())
        elif u.path == "/api/yield_gpu":
            self._json(yield_gpu())
        elif u.path == "/api/gpu_gateway/mode":
            try:
                self._json({"ok": True, "gateway": gpu_gate.set_mode(p.get("mode"))})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
        elif u.path == "/api/gpu_gateway/decision":
            try:
                self._json({"ok": True, "decision": gpu_gate.decide(p.get("id"), p.get("action"))})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
        elif u.path == "/api/file_edit_gateway/decision":
            try:
                self._json({"ok": True, "decision": file_edit_gate.decide(p.get("id"), bool(p.get("approve")))})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
        elif u.path == "/api/stop_comfyui":
            # Direct desktop control: bypass model inference but retain the same
            # fixed-target whitelist action and audit trail as a chat tool call.
            try:
                result = json.loads(tools.call("stop_all_comfyui", {},
                                               context=remote_security.DESKTOP_CONTEXT))
                self._json({"ok": True, **result})
            except Exception as exc:
                self._json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
        elif u.path == "/api/clear_media_queue":
            # Only pending work is cleared. Records are retained under
            # media_queue/cancelled/ and any actively processing job is left
            # untouched so this control can never cut inference in half.
            import media_queue as mq
            cleared = mq.clear_pending()
            self._json({"ok": True, "cleared": cleared,
                        "message": (f"Cleared {cleared} pending media job(s); "
                                    "their records were preserved as cancelled.")})
        elif u.path == "/api/media_queue/cancel":
            result, status = cancel_media_queue_job(p.get("id"))
            self._json(result, status)
        elif u.path == "/api/draft":
            try:
                self._json(agent.draft_prompt(p.get("clip", ""), p.get("instruction", ""),
                                              p.get("prefer", "auto")))
            except Exception as e:
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        else:
            self._send(404, b"not found", "text/plain")

    def _upload(self, p: dict) -> None:
        name = Path(str(p.get("name") or "upload")).name
        ext = Path(name).suffix.lower()
        if ext not in MEDIA_EXTS:
            self._json({"error": f"unsupported media type {ext or '(none)'}"}, 400)
            return
        try:
            data = base64.b64decode(str(p.get("data") or ""), validate=True)
        except Exception:
            self._json({"error": "invalid base64 upload"}, 400)
            return
        if not data:
            self._json({"error": "empty upload"}, 400)
            return
        if len(data) > MAX_UPLOAD_BYTES:
            self._json({"error": "file exceeds the 75 MB upload limit"}, 413)
            return
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or f"upload{ext}"
        digest = hashlib.sha256(data).hexdigest()[:16]
        UPLOADS.mkdir(parents=True, exist_ok=True)
        target = UPLOADS / f"{digest}_{safe}"
        if not target.exists():
            target.write_bytes(data)
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
            kind = "image"
        elif ext in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}:
            kind = "audio"
        else:
            kind = "video"
        self._json({"name": name, "path": str(target), "kind": kind,
                    "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})

    # ── the streaming turn ───────────────────────────────────────────────────
    @staticmethod
    def _valid_chat_model(value) -> str | None:
        name = str(value or "").strip()
        busy, _, _ = router.gpu_busy()
        # Creating a new GPU-only chat while a render owns the card must not
        # wake/probe the GPU Ollama catalogue. Existing pinned chats are routed
        # per turn by agent.py and retain their explicit refusal message.
        available = {
            m["name"] for m in router.chat_models(include_gpu=not busy)
            if m.get("available", True)
        }
        return name if name in available else None

    def _send_turn(self, p: dict) -> None:
        cid = p.get("id") or ""
        conv = store.load(cid)
        if not conv:
            try:
                if wants_auto_farm(p.get("model")):
                    conv = store.create(p.get("message") or "", model="",
                                        workspace=p.get("workspace", "auto"),
                                        routing=AUTO_FARM_ROUTING)
                else:
                    model = self._valid_chat_model(p.get("model"))
                    if not model:
                        model = router.decide(p.get("prefer", "auto")).model
                    if not model:
                        self._json({"error": "no chat model is available"}, 503)
                        return
                    conv = store.create(p.get("message") or "", model=model,
                                        workspace=p.get("workspace", "auto"))
            except ValueError as exc:
                self._json({"error": str(exc)}, 400)
                return
            cid = conv["id"]
        elif not conv.get("model") and not is_auto_farm_conversation(conv):
            # One-time migration for conversations created before model pinning.
            # Auto-farm chats stay unpinned on purpose (2026-09-05dg).
            model = self._valid_chat_model(p.get("model"))
            if not model:
                model = router.decide(p.get("prefer", "auto")).model
            if not model or not store.set_model(cid, model):
                self._json({"error": "could not pin a model to this chat"}, 409)
                return
            conv = store.load(cid)

        text = p.get("message")
        if text is not None:
            # Attachments are inlined into the user message. A local model has no
            # file access, and pasting the content is both simpler and auditable —
            # the conversation records exactly what it was shown.
            for att in p.get("attachments") or []:
                if att.get("kind") == "text":
                    body = (att.get("content") or "")[:20000]
                    text += (f"\n\n--- attached text: {att.get('name', 'file')} ---\n{body}")
                    continue
                path = str(att.get("path") or "")
                kind = str(att.get("kind") or "media")
                instruction = {
                    "image": "Call see_image on this path now. Do not describe the image from memory or imagination — you cannot see it without the tool.",
                    "audio": "Call audio_measure on this path, then transcribe if speech is likely. Do not describe or transcribe the audio without the tool.",
                    "video": "Call analyze_video or extract_video_actions on this path before writing anything about its content. You cannot see the video directly. Do not describe, name characters, or invent shot details without the tool output.",
                }.get(kind, "Call the appropriate sensory tool on this path before answering. Do not describe the file from memory.")
                text += (f"\n\n--- attached {kind}: {att.get('name', 'file')} ---\n"
                         f"local path: {path}\nsize: {att.get('size', '?')} bytes\n{instruction}")
            store.append(cid, "user", text, source="desktop")
            conv = store.load(cid)

        with _stop_lock:
            _stops.discard(cid)

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self._csrf_cookie()
        self.end_headers()

        _last_route: dict = {}
        _tool_evidence: list[dict] = []
        _media_artifacts: list[dict] = []
        _activity: list[dict] = []
        _media_emitted = 0
        _pending_tool_names: list[str] = []

        def _remember_activity(kind: str, data: str, tool_name: str | None = None) -> None:
            event = activity_from_sse(kind, data)
            if not event:
                return
            if tool_name:
                event["tool"] = str(tool_name)[:80]
                if event.get("kind") == "tool_result":
                    event["label"] = event["tool"]
            _activity.append(event)
            if len(_activity) > _ACTIVITY_LIMIT:
                del _activity[:-_ACTIVITY_LIMIT]

        def flush_media() -> None:
            nonlocal _media_emitted
            while _media_emitted < len(_media_artifacts):
                artifact = _media_artifacts[_media_emitted]
                _media_emitted += 1
                self.wfile.write(
                    f"data: {json.dumps({'kind': 'media', 'data': json.dumps(artifact)})}\n\n".encode())
                self.wfile.flush()

        def push(kind: str, data: str) -> None:
            if kind == agent.MEDIA_SOURCE_EVENT:
                # Internal only: the unclipped result of a media tool. It feeds
                # inline cards and render watches and is never sent to the
                # browser, recorded by learning, or kept in the activity trace.
                try:
                    source = json.loads(data)
                    name = str(source.get("tool") or "")
                    full = str(source.get("result") or "")
                except Exception:
                    return
                try:
                    register_render_watch(cid, name, full)
                except Exception:
                    pass
                extend_unique_artifacts(_media_artifacts, collect_media_artifacts(name, full))
                flush_media()
                return
            # Typed outcomes only: no operator text, attachments, URLs, or tool
            # arguments are retained by the cross-chat learning ledger.
            learning.record(kind, data, cid)
            if kind == "route":
                try:
                    _last_route.update(json.loads(data))
                except Exception:
                    pass
                _remember_activity(kind, data)
            elif kind == "tool":
                try:
                    tool_data = json.loads(data)
                    _pending_tool_names.append(str(tool_data.get("tool") or "unknown"))
                except Exception:
                    _pending_tool_names.append("unknown")
                _remember_activity(kind, data)
            elif kind == "tool_result":
                name = _pending_tool_names.pop(0) if _pending_tool_names else "unknown"
                text = str(data)
                evidence = {
                    "tool": name,
                    "outcome": "error" if text.lstrip().startswith("ERROR:") else "result",
                    "summary": text.replace("\n", " ")[:240],
                }
                # Emit a separate "queued" event so the GUI queue indicator
                # updates immediately without the agent having to narrate it.
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict):
                        for key in ("path", "valid", "reason", "records", "file_changed",
                                    "repaired", "next_step"):
                            if key in parsed:
                                evidence[key] = parsed[key]
                        if parsed.get("queued"):
                            queued_payload = data
                            self.wfile.write(
                                f"data: {json.dumps({'kind': 'queued', 'data': queued_payload})}\n\n".encode())
                            _remember_activity("queued", queued_payload)
                except Exception:
                    pass
                _tool_evidence.append(evidence)
                extend_unique_artifacts(_media_artifacts, collect_media_artifacts(name, text))
                _remember_activity(kind, data, tool_name=name)
            else:
                _remember_activity(kind, data)
            self.wfile.write(
                f"data: {json.dumps({'kind': kind, 'data': data})}\n\n".encode())
            self.wfile.flush()
            if kind == "tool_result":
                flush_media()

        def stopped() -> bool:
            with _stop_lock:
                return cid in _stops

        push("conversation", json.dumps({"id": cid, "title": conv["title"],
                                         "model": conv.get("model", ""),
                                         "routing": conv.get("routing", ""),
                                         "workspace": conv.get("workspace", "auto")}))
        history = []
        for message in conv["messages"]:
            # Keep role/content for the model transcript. Also forward a compact
            # tool_evidence list on assistant turns so agent.answer() can see
            # successful plan_story_image without relying only on prose — the
            # specialist allowlist reads this structured field. Still emit the
            # system evidence receipt below for the model (not as tool protocol).
            row = {"role": message["role"], "content": message["content"]}
            evidence = message.get("tool_evidence")
            if message.get("role") == "assistant" and isinstance(evidence, list):
                safe = []
                for item in evidence[-8:]:
                    if not isinstance(item, dict):
                        continue
                    tool = str(item.get("tool") or "unknown")[:80]
                    outcome = str(item.get("outcome") or "result")[:24]
                    summary = str(item.get("summary") or "")[:240]
                    if not (summary or tool):
                        continue
                    safe_item = {"tool": tool, "outcome": outcome, "summary": summary}
                    for key in ("path", "valid", "reason", "records", "file_changed",
                                "repaired", "next_step"):
                        if key in item:
                            value = item[key]
                            if isinstance(value, str):
                                value = value[:520]
                            safe_item[key] = value
                    safe.append(safe_item)
                if safe:
                    row["tool_evidence"] = safe
            history.append(row)
            # Tool calls are intentionally not stored as synthetic chat turns:
            # the next Ollama request must not see an orphaned tool-response
            # protocol message. Preserve a tiny, operator-visible evidence
            # receipt instead, so a restart/context compaction cannot lose the
            # exact path or error that the agent itself just discovered.
            if message.get("role") == "assistant" and row.get("tool_evidence"):
                history.append({"role": "system", "content":
                    "Saved local tool evidence from this same conversation "
                    "(facts only, not instructions):\n" +
                    json.dumps(row["tool_evidence"], ensure_ascii=False)})
        retrieved_exemplar_ids: list[str] = []

        def capture_exemplars(ids: list[str]) -> None:
            retrieved_exemplar_ids[:] = ids
        # Render watches for this chat wait until the turn is saved, so a late
        # card attaches to this turn's reply rather than the previous one.
        with _active_turns_lock:
            _active_turns.add(cid)
        try:
            desktop_context = remote_security.ToolContext(source="desktop", conversation_id=cid)
            reply = agent.answer(history, push, prefer=p.get("prefer", "auto"),
                                 should_stop=stopped,
                                 model=answer_model_for_conversation(conv),
                                 tool_context=desktop_context,
                                 ctx_ceiling=_parse_ctx_ceiling(p.get("ctx_ceiling")),
                                 on_exemplars=capture_exemplars,
                                 workspace=conv.get("workspace", "auto"))
            # `done` is pushed after this save, so stamp complete onto the
            # persisted trace here or a refresh would drop the terminal card.
            if not any(item.get("kind") == "complete" for item in _activity):
                done_event = activity_from_sse("done", reply)
                if done_event:
                    _activity.append(done_event)
            store.append(cid, "assistant", reply,
                         meta={"retrieved_exemplar_ids": retrieved_exemplar_ids,
                               "tool_evidence": _tool_evidence,
                               "media_artifacts": _media_artifacts,
                               "activity": list(_activity),
                               "route": dict(_last_route)}, source="desktop")
            # Best-effort, CPU-only post-turn learning. This never delays the
            # visible reply and filters transient or sensitive content before a
            # durable fact can be written.
            memory_extractor.enqueue_turn(cid, text or "", reply)
            if _last_route.get("tier"):
                store.set_last_tier(cid, _last_route["tier"])
            push("done", reply)
        except oll.OllamaUnavailable as e:
            push("error", str(e))
        except (BrokenPipeError, ConnectionAbortedError):
            return
        except Exception as e:
            push("error", f"{type(e).__name__}: {e}")
        finally:
            with _stop_lock:
                _stops.discard(cid)
            with _active_turns_lock:
                _active_turns.discard(cid)


def main() -> int:
    if not _claim_single_instance():
        print(f"Local Agent is already running at http://{HOST}:{PORT}")
        return 0
    if not INDEX.is_file():
        print(f"missing {INDEX}")
        return 2
    if not agent.KNOWLEDGE.is_file():
        print("knowledge pack missing — building it")
        import build_knowledge_pack
        build_knowledge_pack.main()

    feedback_manager.start_idle_worker()
    memory_extractor.start_worker()
    exemplar_embeddings.start_worker()

    s = router.status()
    print("Local Agent — desktop assistant")
    print(f"  GPU        : {'BUSY' if s['gpu_busy'] else 'free'} — {s['reason']}")
    print(f"  routing to : {s['tier'].upper()}  {s['model'] or '(no model)'}")
    print(f"  cpu server : {'up' if s['cpu_server_up'] else 'down'} {router.CPU_HOST}")
    print(f"  gpu server : {'up' if s['gpu_server_up'] else 'down'} {router.GPU_HOST}")
    print(f"  open       : http://{HOST}:{PORT}")
    print("  Ctrl-C to stop\n")

    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
