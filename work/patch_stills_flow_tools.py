# -*- coding: utf-8 -*-
"""Patch local_agent for stills->review->video flow (r93)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] if False else Path.cwd()
TOOLS = ROOT / "local_agent" / "tools.py"
AGENT = ROOT / "local_agent" / "agent.py"
REMOTE = ROOT / "local_agent" / "remote_security.py"
SERVER = ROOT / "local_agent" / "server.py"
LAUNCHER = ROOT / "local_agent" / "START_LOCAL_AGENT_GUI.ps1"

NEW_FUNCS = r'''
# ── story stills batch + review gate (2026-09-06 r93) ─────────────────────────

_STORY_STILLS_REVIEW_DIR = ROOT / "work" / "runtime" / "story_stills_review"
_VIDEO_TOOLS_NEEDING_STILL_APPROVAL = frozenset({
    "prepare_chat_render",
    "start_current_chat_render",
})
_DEFAULT_BATCH_POLL_S = 5.0
_DEFAULT_BATCH_TIMEOUT_S = 900.0
_MAX_BATCH_JOBS = 24


def _pid_is_live(pid: object) -> bool:
    """Read-only liveness check used before a guarded render launch.

    On Windows, ``os.kill(pid, 0)`` can report a dead PID as live (access /
    handle quirks). Match ``work/image_render.py`` and use ``tasklist`` there.
    """
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {value}", "/NH"],
                capture_output=True, text=True, timeout=8, check=False,
            ).stdout or ""
        except (OSError, subprocess.SubprocessError):
            return False
        return str(value) in out
    try:
        os.kill(value, 0)
        return True
    except OSError:
        return False


def _image_owner_snapshot() -> dict:
    """Best-effort read of the image-render owner file (may be released)."""
    try:
        sys.path.insert(0, str(ROOT / "work"))
        import image_render
        path = image_render.IMAGE_OWNER
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_story_still_outputs(manifest: dict | None) -> list[dict]:
    """Turn a complete image manifest into concrete file paths when possible."""
    if not isinstance(manifest, dict):
        return []
    outputs = manifest.get("outputs") or []
    if not isinstance(outputs, list):
        return []
    resolved: list[dict] = []
    comfy_root = ROOT / "outputs" / "stories" / "_comfy_output"
    for item in outputs:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename") or "").strip()
        subfolder = str(item.get("subfolder") or "").strip()
        if not filename:
            continue
        path = comfy_root / subfolder / filename if subfolder else comfy_root / filename
        entry = {
            "filename": filename,
            "subfolder": subfolder,
            "type": item.get("type"),
            "path": str(path) if path.is_file() else None,
            "expected_path": str(path),
        }
        resolved.append(entry)
    return resolved


def await_story_image_job(args: dict) -> str:
    """Poll ``story_image_job_status`` until complete, failed, or timeout.

    Use after ``render_story_image`` (or inside ``render_story_image_batch``)
    so one tool call can wait out a multi-minute owned-backend render without
    burning MAX_TOOL_HOPS on empty status polls.
    """
    story = str(args.get("story", "")).strip()
    if not story:
        raise ToolError("story is required")
    try:
        poll_s = float(args.get("poll_s", _DEFAULT_BATCH_POLL_S))
        timeout_s = float(args.get("timeout_s", _DEFAULT_BATCH_TIMEOUT_S))
    except (TypeError, ValueError) as exc:
        raise ToolError(f"poll_s/timeout_s invalid: {exc}") from exc
    poll_s = max(1.0, min(poll_s, 30.0))
    timeout_s = max(30.0, min(timeout_s, 3600.0))
    deadline = time.monotonic() + timeout_s
    last = None
    while True:
        last = json.loads(story_image_job_status({
            "story": story,
            "pid": args.get("pid"),
            "log": args.get("log", ""),
        }))
        state = str(last.get("state") or "")
        if state == "complete":
            last["awaited"] = True
            last["outputs_resolved"] = _resolve_story_still_outputs(last.get("manifest"))
            return json.dumps(last, indent=2)
        if state in {"finished_or_crashed", "unknown"} and last.get("pid_running") is False:
            last["awaited"] = True
            last["failed"] = True
            return json.dumps(last, indent=2)
        if time.monotonic() >= deadline:
            last = dict(last or {})
            last["awaited"] = True
            last["timed_out"] = True
            last["timeout_s"] = timeout_s
            return json.dumps(last, indent=2)
        time.sleep(poll_s)


def _normalize_batch_job(raw: object, *, default_profile: str, index: int) -> dict:
    if not isinstance(raw, dict):
        raise ToolError(f"jobs[{index}] must be an object with story and prompt")
    story = str(raw.get("story", "")).strip()
    prompt = str(raw.get("prompt", "")).strip()
    if not story or not prompt:
        raise ToolError(f"jobs[{index}] requires story and prompt")
    job = dict(raw)
    job["story"] = story
    job["prompt"] = prompt
    profile = str(job.get("model_profile") or default_profile or "realvisxl").strip().lower()
    # Operator "using flux" sheets often omit profile per frame.
    flux_hint = "flux" in profile or "flux" in str(job.get("model") or "").lower()
    if flux_hint and profile not in {"realpro_flux", "realvisxl", "alicemix_sd15"}:
        profile = "realpro_flux"
    if default_profile == "realpro_flux" and not job.get("model_profile"):
        profile = "realpro_flux"
    job["model_profile"] = profile
    if "width" not in job and "size" in job:
        size = job.get("size")
        if isinstance(size, (list, tuple)) and len(size) == 2:
            job["width"], job["height"] = int(size[0]), int(size[1])
        elif isinstance(size, str) and "x" in size.lower():
            w, h = size.lower().split("x", 1)
            job["width"], job["height"] = int(w.strip()), int(h.strip())
    return job


def render_story_image_batch(args: dict) -> str:
    """Sequentially render many stills: start → await → next (one owns backend).

    Prefer this over N parallel ``render_story_image`` calls. One tool call
    finishes the queue without MAX_TOOL_HOPS exhaustion or "owns the backend"
    dead-ends. On full success it marks the chat's stills as pending operator
    review so video tools stay blocked until approval.
    """
    jobs_raw = args.get("jobs")
    if not isinstance(jobs_raw, list) or not jobs_raw:
        raise ToolError("jobs must be a non-empty list of still render requests")
    if len(jobs_raw) > _MAX_BATCH_JOBS:
        raise ToolError(f"jobs capped at {_MAX_BATCH_JOBS} stills per batch")
    default_profile = str(args.get("model_profile") or args.get("default_model_profile") or "realvisxl").strip().lower()
    if str(args.get("flux") or "").lower() in {"1", "true", "yes"} or default_profile in {"flux", "realpro_flux"}:
        default_profile = "realpro_flux"
    try:
        poll_s = float(args.get("poll_s", _DEFAULT_BATCH_POLL_S))
        timeout_s = float(args.get("timeout_s", _DEFAULT_BATCH_TIMEOUT_S))
    except (TypeError, ValueError) as exc:
        raise ToolError(f"poll_s/timeout_s invalid: {exc}") from exc
    conversation_id = str(args.get("__conversation_id") or "").strip()
    stop_on_failure = bool(args.get("stop_on_failure", True))

    completed: list[dict] = []
    failures: list[dict] = []
    pending: list[dict] = []
    normalized = [
        _normalize_batch_job(raw, default_profile=default_profile, index=i)
        for i, raw in enumerate(jobs_raw)
    ]

    for index, job in enumerate(normalized):
        label = {"index": index, "story": job["story"], "prompt_preview": job["prompt"][:120]}
        # Launch with a short retry loop if a previous owner is still draining.
        started = None
        launch_error = None
        for attempt in range(60):
            try:
                payload = dict(job)
                # Internal identity must survive if call() injected it on the batch.
                if args.get("__remote_render_identity"):
                    payload["__remote_render_identity"] = args["__remote_render_identity"]
                started = json.loads(render_story_image(payload))
                launch_error = None
                break
            except ToolError as exc:
                launch_error = str(exc)
                owned = "owns the backend" in launch_error or "already listening on port 8188" in launch_error
                if not owned:
                    break
                # Wait for the foreign/prior owner to clear, then retry.
                time.sleep(max(2.0, poll_s))
                continue
        if launch_error or not isinstance(started, dict) or not started.get("started"):
            entry = {**label, "error": launch_error or "render did not start", "phase": "launch"}
            failures.append(entry)
            if stop_on_failure:
                pending.extend(
                    {"index": i, "story": normalized[i]["story"], "reason": "not_started_after_failure"}
                    for i in range(index + 1, len(normalized))
                )
                break
            continue

        awaited = json.loads(await_story_image_job({
            "story": started.get("story") or job["story"],
            "pid": started.get("pid"),
            "log": started.get("log", ""),
            "poll_s": poll_s,
            "timeout_s": timeout_s,
        }))
        if awaited.get("state") == "complete" and not awaited.get("timed_out"):
            completed.append({
                **label,
                "pid": started.get("pid"),
                "log": started.get("log"),
                "manifest": awaited.get("manifest"),
                "outputs": awaited.get("outputs_resolved") or _resolve_story_still_outputs(awaited.get("manifest")),
            })
        else:
            failures.append({
                **label,
                "pid": started.get("pid"),
                "log": started.get("log"),
                "phase": "await",
                "status": awaited,
                "error": "timed_out" if awaited.get("timed_out") else "finished_without_manifest",
            })
            if stop_on_failure:
                pending.extend(
                    {"index": i, "story": normalized[i]["story"], "reason": "not_started_after_failure"}
                    for i in range(index + 1, len(normalized))
                )
                break

    review = None
    if completed and not failures and conversation_id:
        review = json.loads(present_story_stills_for_review({
            "story": completed[0]["story"],
            "stills": [
                {
                    "story": c["story"],
                    "outputs": c.get("outputs") or [],
                    "manifest": c.get("manifest"),
                }
                for c in completed
            ],
            "__conversation_id": conversation_id,
        }))

    summary = {
        "batch": True,
        "total": len(normalized),
        "completed_count": len(completed),
        "failure_count": len(failures),
        "pending_count": len(pending),
        "completed": completed,
        "failures": failures,
        "pending": pending,
        "review": review,
        "next_step": (
            "Stills are ready for operator review. Present the output paths, "
            "ask the operator to approve (e.g. 'looks good' / 'approved' / "
            "'go ahead with video'), and call approve_story_stills only after "
            "that explicit approval. Do NOT call prepare_chat_render, "
            "start_current_chat_render, or comfy_generate video until approved."
            if completed and not failures else
            "Some stills failed or remain pending. Fix failures before video. "
            "Do not claim the sheet is ready for review until completed_count "
            "covers every unique frame."
        ),
    }
    return json.dumps(summary, indent=2, default=str)


def _review_state_path(conversation_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in conversation_id.strip())[:80]
    if not safe:
        raise ToolError("conversation id missing for stills review state")
    return _STORY_STILLS_REVIEW_DIR / f"{safe}.json"


def present_story_stills_for_review(args: dict) -> str:
    """Mark generated story stills as pending operator review (chat-scoped)."""
    conversation_id = str(args.get("__conversation_id") or args.get("conversation_id") or "").strip()
    if not conversation_id:
        raise ToolError("present_story_stills_for_review requires the current chat id")
    story = str(args.get("story", "")).strip() or "story"
    stills = args.get("stills")
    if not isinstance(stills, list) or not stills:
        raise ToolError("stills must be a non-empty list of generated frame records")
    path = _review_state_path(conversation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "status": "pending_review",
        "conversation_id": conversation_id,
        "story": story,
        "stills": stills,
        "presented_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "approved_at": None,
    }
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    return json.dumps({
        "pending_review": True,
        "conversation_id": conversation_id,
        "story": story,
        "still_count": len(stills),
        "state_path": str(path),
        "note": (
            "Show these stills to the operator and wait. Continuation phrases "
            "like 'continue' or 'go on to the next step' do NOT approve video. "
            "Need explicit approval: 'looks good', 'approved', or 'go ahead with video'."
        ),
    }, indent=2)


def approve_story_stills(args: dict) -> str:
    """Unlock video tools after explicit operator approval of story stills."""
    if args.get("operator_confirmed") is not True:
        raise ToolError(
            "story stills remain pending review: set operator_confirmed=true only "
            "after the operator explicitly approved the images"
        )
    conversation_id = str(args.get("__conversation_id") or args.get("conversation_id") or "").strip()
    if not conversation_id:
        raise ToolError("approve_story_stills requires the current chat id")
    path = _review_state_path(conversation_id)
    if not path.is_file():
        raise ToolError("no pending story-stills review state for this chat")
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ToolError(f"could not read stills review state: {exc}") from exc
    if not isinstance(state, dict):
        raise ToolError("corrupt stills review state")
    if state.get("status") == "approved":
        return json.dumps({"approved": True, "already": True, "state": state}, indent=2)
    if state.get("status") != "pending_review":
        raise ToolError(f"stills review status is {state.get('status')!r}, not pending_review")
    state["status"] = "approved"
    state["approved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")
    return json.dumps({
        "approved": True,
        "conversation_id": conversation_id,
        "story": state.get("story"),
        "still_count": len(state.get("stills") or []),
        "next_step": (
            "Operator approved the stills. You may now prepare/start video using "
            "prepare_chat_render / start_current_chat_render with the generated "
            "frame assets."
        ),
    }, indent=2)


def story_stills_review_status(args: dict) -> str:
    """Read-only: pending/approved/none for this chat's story stills review."""
    conversation_id = str(args.get("__conversation_id") or args.get("conversation_id") or "").strip()
    if not conversation_id:
        raise ToolError("story_stills_review_status requires the current chat id")
    path = _review_state_path(conversation_id)
    if not path.is_file():
        return json.dumps({"status": "none", "conversation_id": conversation_id}, indent=2)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ToolError(f"could not read stills review state: {exc}") from exc
    out = dict(state) if isinstance(state, dict) else {"status": "unknown"}
    out["conversation_id"] = conversation_id
    out["state_path"] = str(path)
    return json.dumps(out, indent=2, default=str)


def _stills_review_blocks_video(conversation_id: str) -> str | None:
    """Return a refusal reason when stills are awaiting review for this chat."""
    cid = str(conversation_id or "").strip()
    if not cid:
        return None
    path = _STORY_STILLS_REVIEW_DIR / (
        "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in cid)[:80] + ".json"
    )
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(state, dict) and state.get("status") == "pending_review":
        return (
            "story stills are awaiting operator review for this chat; "
            "do not start video until approve_story_stills after explicit approval "
            "('looks good' / 'approved' / 'go ahead with video'). "
            "Bare 'continue' is not approval."
        )
    return None
'''

def main():
    text = TOOLS.read_text(encoding="utf-8")

    # 1) Replace _pid_is_live with improved version — remove old def, insert comes with NEW_FUNCS
    # First remove old _pid_is_live (keep start_batch_render intact)
    old_pid = '''def _pid_is_live(pid: object) -> bool:
    """Read-only liveness check used before a guarded render launch."""
    try:
        value = int(pid)
        if value <= 0:
            return False
        os.kill(value, 0)
        return True
    except (TypeError, ValueError, OSError):
        return False


'''
    if old_pid not in text:
        raise SystemExit("old _pid_is_live block not found")
    # Temporarily replace with a marker; full new def lives near story tools to avoid
    # duplicating before start_batch_render uses it — actually start_batch_render uses it
    # so we need the new def at the original location.
    new_pid_only = '''def _pid_is_live(pid: object) -> bool:
    """Read-only liveness check used before a guarded render launch.

    On Windows, ``os.kill(pid, 0)`` can falsely report a dead PID as live.
    Match ``work/image_render.py`` and use ``tasklist`` on Windows.
    """
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {value}", "/NH"],
                capture_output=True, text=True, timeout=8, check=False,
            ).stdout or ""
        except (OSError, subprocess.SubprocessError):
            return False
        return str(value) in out
    try:
        os.kill(value, 0)
        return True
    except OSError:
        return False


'''
    text = text.replace(old_pid, new_pid_only, 1)

    # 2) Patch story_image_job_status for stale owner/pid
    old_status_running = '''    running = _pid_is_live(pid) if pid is not None else None
    manifests_dir = ROOT / "outputs" / "stories" / safe_story / "manifests"
'''
    new_status_running = '''    running = _pid_is_live(pid) if pid is not None else None
    owner = _image_owner_snapshot()
    owner_pid = 0
    try:
        owner_pid = int(owner.get("pid") or 0)
    except (TypeError, ValueError):
        owner_pid = 0
    owner_released = (not owner) or owner_pid <= 0 or str(owner.get("purpose") or "") == "released"
    # Stale-PID fix: if the job PID is gone OR the owner file was released and
    # no longer claims this pid, do not keep reporting running.
    if running and pid is not None:
        try:
            job_pid = int(pid)
        except (TypeError, ValueError):
            job_pid = 0
        if owner_released and not _pid_is_live(job_pid):
            running = False
        elif owner_pid and job_pid and owner_pid != job_pid and not _pid_is_live(job_pid):
            running = False
        elif running and owner_released:
            # Owner released while tasklist/os.kill still looked live — trust release.
            try:
                sys.path.insert(0, str(ROOT / "work"))
                import image_render as _ir_status
                port_busy = bool(_ir_status._port_open())
            except Exception:
                port_busy = False
            if not port_busy and not _pid_is_live(job_pid):
                running = False
            elif not port_busy and owner_released:
                # Released + :8188 down => treat as not running even if PID check flaked.
                running = False
    manifests_dir = ROOT / "outputs" / "stories" / safe_story / "manifests"
'''
    if old_status_running not in text:
        raise SystemExit("story_image_job_status running block not found")
    text = text.replace(old_status_running, new_status_running, 1)

    old_status_return = '''    return json.dumps({
        "state": state,
        "pid_running": running,
        "story": safe_story,
        "manifest_found": bool(latest_manifest),
        "manifest": latest_manifest,
        "log_tail": log_tail,
        "note": ("state=complete with a manifest means a real file was written. The '''
    new_status_return = '''    return json.dumps({
        "state": state,
        "pid_running": running,
        "owner_pid": owner_pid,
        "owner_released": owner_released,
        "story": safe_story,
        "manifest_found": bool(latest_manifest),
        "manifest": latest_manifest,
        "log_tail": log_tail,
        "note": ("state=complete with a manifest means a real file was written. The '''
    if old_status_return not in text:
        raise SystemExit("status return block not found")
    text = text.replace(old_status_return, new_status_return, 1)

    # 3) Insert new functions after storyboard_frame_plan (before registry)
    marker = '''def storyboard_frame_plan(args: dict) -> str:
    """Read the gated frame plan. This does not generate a still or video."""
    try:
        return json.dumps(_storyboard_module().frame_plan(str(args.get("story", ""))), indent=2)
    except Exception as exc:
        raise ToolError(str(exc)) from exc


# ── registry ──────────────────────────────────────────────────────────────────
'''
    # NEW_FUNCS already defines _pid_is_live — strip that duplicate from NEW_FUNCS insert
    insert_funcs = NEW_FUNCS
    # Remove duplicate _pid_is_live from insert (already replaced at top)
    start = insert_funcs.find("def _pid_is_live")
    end = insert_funcs.find("def _image_owner_snapshot")
    if start >= 0 and end > start:
        insert_funcs = insert_funcs[:start] + insert_funcs[end:]

    if marker not in text:
        raise SystemExit("storyboard_frame_plan marker not found")
    text = text.replace(
        marker,
        marker.replace(
            "# ── registry ──────────────────────────────────────────────────────────────────\n",
            insert_funcs + "\n# ── registry ──────────────────────────────────────────────────────────────────\n",
        ),
        1,
    )

    # 4) Update plan_story_image next_step guidance
    old_next = '''        "next_step": (
            "This is a read-only graph plan ONLY. No model was loaded, no GPU work "
            "ran, and no image file was written anywhere, including under "
            f"outputs/stories/{story}/ — that folder does not exist yet. Do not tell "
            "the operator an image was generated, rendered, saved, or is ready — none "
            "of that happened. To actually produce a file, call render_story_image "
            "with the same arguments; it starts a real guarded render in the "
            "background and returns a pid/log to poll with story_image_job_status. "
            "Never claim completion until story_image_job_status reports a manifest."
        ),'''
    new_next = '''        "next_step": (
            "This is a read-only graph plan ONLY. No model was loaded, no GPU work "
            "ran, and no image file was written anywhere, including under "
            f"outputs/stories/{story}/ — that folder does not exist yet. Do not tell "
            "the operator an image was generated, rendered, saved, or is ready — none "
            "of that happened. For a CLIP start/end still sheet, dedupe chained frames "
            "and call render_story_image_batch with all unique stills (model_profile="
            "realpro_flux when Flux was requested) so they run sequentially; or call "
            "render_story_image then await_story_image_job / story_image_job_status. "
            "Do not dump many plan_story_image calls and claim ready. After stills "
            "exist, present them for review and wait — do not start video yet."
        ),'''
    if old_next not in text:
        raise SystemExit("plan next_step not found")
    text = text.replace(old_next, new_next, 1)

    # 5) Registry / categories / IMAGE_DIRECT / TOOLS descriptions / schemas
    text = text.replace(
        '''IMAGE_DIRECT_TOOLS = (
    "plan_story_image",
    "render_story_image",
    "story_image_job_status",
)''',
        '''IMAGE_DIRECT_TOOLS = (
    "plan_story_image",
    "render_story_image",
    "render_story_image_batch",
    "await_story_image_job",
    "story_image_job_status",
    "present_story_stills_for_review",
    "approve_story_stills",
    "story_stills_review_status",
)''',
        1,
    )

    text = text.replace(
        '''    "plan_story_image": "story_image", "render_story_image": "story_image",
    "story_image_job_status": "story_image",''',
        '''    "plan_story_image": "story_image", "render_story_image": "story_image",
    "render_story_image_batch": "story_image", "await_story_image_job": "story_image",
    "story_image_job_status": "story_image",
    "present_story_stills_for_review": "story_image",
    "approve_story_stills": "story_image",
    "story_stills_review_status": "story_image",''',
        1,
    )

    old_tools_entries = '''    "plan_story_image": (plan_story_image, "Prepare an inspectable RealVisXL still-image graph for a general story or storyboard. If the operator asks for Flux / using flux / with flux / via flux, set model_profile=realpro_flux (Flux UNet path). Default remains realvisxl. There is NO tool named flux — never call a tool named flux. Read-only: never starts ComfyUI, loads a model, uses the GPU, or writes output. THIS DOES NOT GENERATE AN IMAGE by itself. After calling this, tell the operator only that a plan was prepared; call render_story_image separately (same arguments) to actually generate the file — never say an image was generated, rendered, saved, or is ready just from this call. Supports text-to-image or reference image-to-image with an uploaded filename. For best prompt adherence: put the single most important, distinguishing detail for EACH subject first in that subject's own clause (SDXL's text encoder tends to blend/average a long single-paragraph prompt, so specific garment/pose details buried mid-sentence are often lost); a taller resolution (e.g. width 896 height 1152) renders full-body multi-person scenes with more detail per face than a 1024x1024 square. Set face_detail=true when a prior image has crooked eyes, facial artifacts, or small damaged faces: it adds an opt-in detected-face repair pass."),
    "render_story_image": (render_story_image, "ACTUALLY GENERATE a general still image — starts a private, guarded, throwaway ComfyUI backend, submits the graph, and returns once the job is launched IN THE BACKGROUND (it is not done when this call returns). If the operator asks for Flux / using flux / with flux / via flux, set model_profile=realpro_flux (Flux UNet path). Default remains realvisxl. There is NO tool named flux — never call a tool named flux. Requires GPU-gateway approval like any other render. A phone request requires its exact paired-identity grant; all normal preflights still apply. Same arguments as plan_story_image. Use face_detail=true to repair crooked eyes/facial artifacts with a detected-face pass; it starts the otherwise-isolated backend with the installed Impact face-detail nodes only when explicitly requested. After this returns, call story_image_job_status with the returned pid, story, and log to find out whether it actually finished before telling the operator an image exists."),
    "story_image_job_status": (story_image_job_status, 'Read-only: check whether a render_story_image job is still running and whether it produced a real file. {"story":"...","pid":1234,"log":"path from render_story_image"}. Poll again if state is "running" rather than assuming failure.'),'''

    new_tools_entries = '''    "plan_story_image": (plan_story_image, "Prepare an inspectable still-image graph (optional). If the operator pastes a CLIP start/end still sheet and says Generate these photos using flux, do NOT dump many plan-only calls and claim ready — plan only when inspecting a graph, otherwise go straight to render_story_image_batch with model_profile=realpro_flux for all unique start/end frames (dedupe chained frames). There is NO tool named flux. Read-only: never starts ComfyUI or writes a file. Continuation after plans means RENDER stills, not more planning."),
    "render_story_image": (render_story_image, "ACTUALLY GENERATE one general still — launches a private guarded ComfyUI backend in the BACKGROUND (not done when this returns). Prefer render_story_image_batch when the operator wants multiple CLIP start/end frames. Flux => model_profile=realpro_flux. After launch, await_story_image_job or story_image_job_status until complete. Only one render owns the backend at a time."),
    "render_story_image_batch": (render_story_image_batch, "PREFERRED for CLIP still sheets: sequentially render a list of stills (start→await complete/fail→next) so one tool call finishes many frames without MAX_TOOL_HOPS exhaustion or 'owns the backend' dead-ends. {\"jobs\":[{\"story\":\"clip15_start\",\"prompt\":\"...\",\"model_profile\":\"realpro_flux\"}, ...]}. Flux sheet => model_profile/default realpro_flux. On full success marks this chat pending stills review — present outputs and WAIT; do not start video until approve_story_stills after explicit operator approval."),
    "await_story_image_job": (await_story_image_job, "Poll story_image_job_status until complete, failed, or timeout (default 900s). {\"story\":\"...\",\"pid\":123,\"log\":\"...\"} optional poll_s/timeout_s. Use after a single render_story_image when not using the batch tool."),
    "story_image_job_status": (story_image_job_status, 'Read-only: check whether a render_story_image job is still running and whether it produced a real file. {"story":"...","pid":1234,"log":"path from render_story_image"}. Detects stale PIDs when the owner was released / process is dead — do not treat pid_running=true as gospel if owner_released and :8188 is down. Poll again if state is "running".'),
    "present_story_stills_for_review": (present_story_stills_for_review, "Mark generated story stills as pending operator review for this chat. Call after stills exist (batch does this automatically). Video tools stay blocked until approve_story_stills. Bare 'continue' is not approval."),
    "approve_story_stills": (approve_story_stills, "Unlock video for this chat after the operator explicitly approves the stills ('looks good' / 'approved' / 'go ahead with video'). Requires operator_confirmed=true. Do not call on bare continue."),
    "story_stills_review_status": (story_stills_review_status, "Read-only: pending_review / approved / none for this chat's story stills review gate."),'''

    if old_tools_entries not in text:
        raise SystemExit("TOOLS story entries not found")
    text = text.replace(old_tools_entries, new_tools_entries, 1)

    # Schemas for new tools — insert after story_image_job_status schema
    old_schema_tail = '''    "story_image_job_status": {
        "type": "object",
        "properties": {
            "story": {"type": "string", "description": "Story slug passed to render_story_image"},
            "pid": {"type": "integer", "description": "pid returned by render_story_image"},
            "log": {"type": "string", "description": "log path returned by render_story_image"},
        },
        "required": ["story"],
    },
    "prepare_storyboard_review": {'''

    new_schema_tail = '''    "story_image_job_status": {
        "type": "object",
        "properties": {
            "story": {"type": "string", "description": "Story slug passed to render_story_image"},
            "pid": {"type": "integer", "description": "pid returned by render_story_image"},
            "log": {"type": "string", "description": "log path returned by render_story_image"},
        },
        "required": ["story"],
    },
    "await_story_image_job": {
        "type": "object",
        "properties": {
            "story": {"type": "string"},
            "pid": {"type": "integer"},
            "log": {"type": "string"},
            "poll_s": {"type": "number", "description": "Poll interval seconds (default 5)"},
            "timeout_s": {"type": "number", "description": "Max wait seconds (default 900)"},
        },
        "required": ["story"],
    },
    "render_story_image_batch": {
        "type": "object",
        "properties": {
            "jobs": {
                "type": "array",
                "description": "Ordered still jobs; each needs story+prompt. Optional mode/size/model_profile per job.",
                "items": {
                    "type": "object",
                    "properties": {
                        "story": {"type": "string"},
                        "prompt": {"type": "string"},
                        "model_profile": {"type": "string", "enum": ["realvisxl", "realpro_flux", "alicemix_sd15"]},
                        "mode": {"type": "string", "enum": ["t2i", "i2i"]},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                        "seed": {"type": "integer"},
                        "negative": {"type": "string"},
                        "face_detail": {"type": "boolean"},
                        "reference_name": {"type": "string"},
                    },
                    "required": ["story", "prompt"],
                },
            },
            "model_profile": {"type": "string", "enum": ["realvisxl", "realpro_flux", "alicemix_sd15"], "description": "Default profile for jobs that omit model_profile. Use realpro_flux for Flux sheets."},
            "default_model_profile": {"type": "string", "description": "Alias of model_profile"},
            "flux": {"type": "boolean", "description": "If true, default model_profile to realpro_flux"},
            "poll_s": {"type": "number"},
            "timeout_s": {"type": "number", "description": "Per-job await timeout seconds"},
            "stop_on_failure": {"type": "boolean", "description": "Default true — stop queue after first failure"},
        },
        "required": ["jobs"],
    },
    "present_story_stills_for_review": {
        "type": "object",
        "properties": {
            "story": {"type": "string"},
            "stills": {"type": "array", "description": "Generated still records with outputs/paths"},
        },
        "required": ["stills"],
    },
    "approve_story_stills": {
        "type": "object",
        "properties": {
            "operator_confirmed": {"type": "boolean", "description": "True only after explicit operator approval of the stills"},
        },
        "required": ["operator_confirmed"],
    },
    "story_stills_review_status": {
        "type": "object",
        "properties": {},
    },
    "prepare_storyboard_review": {'''

    if old_schema_tail not in text:
        raise SystemExit("schema tail not found")
    text = text.replace(old_schema_tail, new_schema_tail, 1)

    # 6) call() — inject conversation id + gate video + remote grant for batch
    old_remote = '''    if context.remote and name in {"start_batch_render", "start_current_chat_render",
                                    "render_story_image"}:
        args["__remote_render_identity"] = context.remote_identity'''
    new_remote = '''    if context.remote and name in {"start_batch_render", "start_current_chat_render",
                                    "render_story_image", "render_story_image_batch"}:
        args["__remote_render_identity"] = context.remote_identity'''
    if old_remote not in text:
        raise SystemExit("remote render identity block not found")
    text = text.replace(old_remote, new_remote, 1)

    # Inject conversation id for review/batch tools — find prepare_chat pattern in call
    # Actually conversation injection for prepare_chat is in agent.py. Add in call() too for safety.
    inject_marker = '''    if context.remote and name in {"start_batch_render", "start_current_chat_render",
                                    "render_story_image", "render_story_image_batch"}:
        args["__remote_render_identity"] = context.remote_identity'''
    inject_extra = inject_marker + '''
    if name in {
        "render_story_image_batch",
        "present_story_stills_for_review",
        "approve_story_stills",
        "story_stills_review_status",
    }:
        if not str(args.get("__conversation_id") or "").strip():
            args["__conversation_id"] = str(context.conversation_id or "")
    block = None
    if name in _VIDEO_TOOLS_NEEDING_STILL_APPROVAL:
        block = _stills_review_blocks_video(str(args.get("__conversation_id") or context.conversation_id or ""))
    elif name == "comfy_generate" and str(args.get("action") or "").strip().lower() == "video":
        block = _stills_review_blocks_video(str(context.conversation_id or ""))
    if block:
        remote_security.audit_tool(context, name, args or {}, "refused", "stills review gate")
        return f"ERROR: {block}"'''
    if inject_marker not in text:
        raise SystemExit("inject marker missing after remote patch")
    text = text.replace(inject_marker, inject_extra, 1)

    TOOLS.write_text(text, encoding="utf-8")
    print("tools.py patched OK", len(text))

if __name__ == "__main__":
    main()
