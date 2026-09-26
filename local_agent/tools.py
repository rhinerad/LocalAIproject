#!/usr/bin/env python3
"""What the local agent is allowed to do.

FOUR TIERS
----------
  READ      Project state, counts, prompt text, ladders, validation.
  BUILD     Regenerates derived files — prompts, configs, classifications.
            Safe and idempotent; never touches the GPU.
  GPU       Renders. Requires explicit operator confirmation; the model proposes,
            never starts.
  FILE/WEB  General-purpose file access and internet fetching.
            write_file refuses to overwrite protected project records.

Nothing here deletes anything. The reset tool is deliberately excluded — it is
destructive enough that it stays a human decision at a terminal.
"""
from __future__ import annotations

import html.parser
import difflib
import hashlib
import inspect
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import artifacts
import phone_scheduler
import remote_security
import sonic_pi
from gvd_tool_router.tools import (
    apply_lipsync_tool,
    assemble_scene_tool,
    discover_workflows_tool,
    execute_continuous_take,
    execute_fast_action,
    execute_montage_morph,
    execute_narrative_scene,
    generate_still,
    gvd_family_status,
    gvd_inventory,
    gvd_plan_shot,
    gvd_quality_gate,
    gvd_route_shot,
    repair_video_tool,
    synthesize_dialogue_tool,
    upscale_still,
)
from gvd_qa.tools import (
    gvd_qa_accepted_still,
    gvd_qa_activation,
    gvd_qa_attach_wd14,
    gvd_qa_evaluate,
    gvd_qa_loop_tool,
)

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
PY = sys.executable or "python"
DEV_WORKSPACE = Path(__file__).resolve().parent / "developer_workspace"

CLIP_RE = re.compile(r"^[0-9]{2}[A-Z][0-9]?$")


class ToolError(RuntimeError):
    pass


# ── read helpers ──────────────────────────────────────────────────────────────

def _json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return default if default is not None else {}


def project_state(_: dict) -> str:
    """Counts that answer 'where are we'."""
    req = _json(EQ / "voice_requirements.json")
    man = _json(EQ / "audio_pass_manifest.json", {"clips": {}})
    aud = _json(EQ / "voice_audition_manifest.json", {"characters": {}})
    cfg = _json(EQ / "audio_pass_config_omni_v1.json", {"clips": []})
    prov = sorted({a["character"] for e in cfg.get("clips", [])
                   for a in e.get("ref_audios", []) if a.get("provisional")})
    rendered = sum(1 for v in aud.get("characters", {}).values()
                   for t in v.get("takes", []) if t.get("status") == "rendered")
    chosen = sum(1 for v in aud.get("characters", {}).values() if v.get("chosen"))
    from collections import Counter
    st = Counter(v.get("status") for v in man.get("clips", {}).values())
    n_prompts = len(list((EQ / "prompts_native_r2v").glob("*.txt")))
    return json.dumps({
        "native_prompts": n_prompts,
        "dialogue_clips": len(req.get("clips", [])),
        "recurring_speakers": req.get("recurring", []),
        "one_off_speakers": req.get("one_off", []),
        "fl2va_clips": (req.get("summary") or {}).get("fl2va_clips", []),
        "soundtrack_manifest_records": len(man.get("clips", {})),
        "soundtrack_statuses": dict(st),
        "auditions_rendered": rendered,
        "auditions_chosen": chosen,
        "provisional_masters": prov,
        "audio_gate": "BLOCKED — voices not chosen" if chosen == 0 else "voices partly chosen",
    }, indent=2)


def clip_info(args: dict) -> str:
    cid = str(args.get("clip", "")).strip().upper()
    if not CLIP_RE.match(cid):
        raise ToolError(f"{cid!r} is not a clip id (e.g. 00A, 27E, 00D2)")
    story = _json(EQ / "story_config.json", {"clips": []})
    clip = next((c for c in story["clips"] if c["id"] == cid), None)
    if not clip:
        raise ToolError(f"no clip {cid} in story_config.json")
    req = _json(EQ / "voice_requirements.json")
    route = next((c for c in req.get("clips", []) if c["id"] == cid), {})
    dur = next((r for r in _json(EQ / "audio_pass_durations.json", {"clips": []})["clips"]
                if r["id"] == cid), {})
    return json.dumps({
        "id": cid,
        "scripted_seconds": clip.get("duration"),
        "scripted_frames": clip.get("frames"),
        "soundtrack_seconds": dur.get("audio_pass_seconds"),
        "soundtrack_frames": dur.get("audio_pass_frames"),
        "pad_silence_seconds": dur.get("pad_silence_seconds"),
        "speakers": route.get("speakers", []),
        "audio_reference_speakers": route.get("audio_reference_speakers", []),
        "no_audio_reference_speakers": route.get("no_audio_reference_speakers", []),
        "node": route.get("node"),
        "path": route.get("path"),
        "dialogue": [d["line"] for d in clip.get("dialogue_timing") or []],
        "first_frame": clip.get("first_frame"),
        "last_frame": clip.get("last_frame"),
    }, indent=2, ensure_ascii=False)


def read_prompt(args: dict) -> str:
    cid = str(args.get("clip", "")).strip().upper()
    if not CLIP_RE.match(cid):
        raise ToolError(f"{cid!r} is not a clip id")
    p = EQ / "prompts_native_r2v" / f"{cid}.txt"
    if not p.is_file():
        raise ToolError(f"no generated prompt for {cid}")
    return p.read_text(encoding="utf8")


def validate_prompt(args: dict) -> str:
    """Check prompt text against the format. THE safety net for model output."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate_h3_prompt import validate
    text = args.get("text")
    if not text:
        cid = str(args.get("clip", "")).strip().upper()
        if not CLIP_RE.match(cid):
            raise ToolError("give either text= or clip=")
        text = read_prompt({"clip": cid})
    r = validate(text, args.get("name", "prompt"),
                 expect_audio=args.get("expect_audio"))
    return json.dumps(r.as_dict(), indent=2)


def validate_powerinfer_calibration(args: dict) -> str:
    """Validate an operator-supplied calibration JSONL without doing model work.

    This is deliberately an intake check only.  It never edits a checkpoint,
    starts PowerInfer, allocates the GPU, generates predictors, or treats a
    passing schema check as permission to do any of those things.
    """
    raw = str(args.get("path", "")).strip()
    if not raw:
        raise ToolError("path is required; provide the operator-approved calibration JSONL")
    path = (Path(raw) if Path(raw).is_absolute() else ROOT / raw).resolve()
    root = ROOT.resolve()
    if path.suffix.lower() != ".jsonl" or not path.is_file():
        raise ToolError("path must be an existing .jsonl file")
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ToolError("calibration JSONL must be inside this project workspace") from exc
    if path.stat().st_size > 2_000_000:
        raise ToolError("calibration JSONL exceeds the 2 MB intake limit")
    powerinfer = ROOT / "tools" / "powerinfer"
    sys.path.insert(0, str(powerinfer))
    try:
        from validate_approved_calibration_pairs import validate
        result = validate(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return json.dumps({
            "valid": False,
            "path": str(path),
            "reason": str(exc),
            "next_step": ("Correct or explicitly approve the JSONL, then validate it again. "
                          "No model, predictor, GPU, render, or registry action ran."),
        }, indent=2)
    return json.dumps({
        "valid": True,
        "path": str(path),
        "approval": result,
        "next_step": ("Schema/approval intake passed only. The PowerInfer checkpoint remains "
                      "parked; do not generate predictors, edit weights, benchmark, serve, "
                      "or register a model without a separate authorized research step."),
        "gpu": False,
        "model_weights_touched": False,
        "predictors_touched": False,
        "registry_touched": False,
    }, indent=2)


def repair_jsonl_format(args: dict) -> str:
    """Convert a JSON object array to JSONL, without approving its meaning.

    This is intentionally a syntax-only text repair. It neither adds missing
    fields nor changes record values, and it never treats the result as a valid
    calibration, an approval, or permission for model work.
    """
    raw = str(args.get("path", "")).strip()
    if not raw:
        raise ToolError("path is required")
    path = (Path(raw) if Path(raw).is_absolute() else ROOT / raw).resolve()
    root = ROOT.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ToolError("JSONL repair path must be inside this project workspace") from exc
    if path.suffix.lower() != ".jsonl" or not path.is_file():
        raise ToolError("path must be an existing .jsonl file")
    if path.stat().st_size > 2_000_000:
        raise ToolError("JSONL repair input exceeds the 2 MB limit")
    try:
        raw_text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ToolError(f"cannot read {path}: {exc}") from exc

    # A .jsonl file is sometimes accidentally saved as one top-level JSON
    # object list. This conversion is lossless: every list item must already
    # be an object and becomes one compact JSONL line.
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        if not parsed:
            raise ToolError("JSON array is empty; no JSONL records to write")
        if not all(isinstance(item, dict) for item in parsed):
            raise ToolError("JSON array must contain objects only; no file was changed")
        text = "\n".join(json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                         for item in parsed) + "\n"
        path.write_text(text, encoding="utf-8")
        return json.dumps({
            "repaired": True,
            "path": str(path),
            "records": len(parsed),
            "operation": "converted one top-level JSON object array into JSONL",
            "approval_changed": False,
            "file_changed": True,
            "record_values_changed": False,
            "next_step": "Re-run the requested validator against this exact path.",
        }, indent=2)
    if isinstance(parsed, dict):
        raise ToolError("file contains one JSON object, not a JSON object array or JSONL; no file was changed")

    # Do not guess how to repair arbitrary fragments. A normal JSONL file is
    # already structurally valid only when each nonblank line is an object.
    try:
        records = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise ToolError(f"not a repairable JSON array or JSONL: {exc}; no file was changed") from exc
    if not records or not all(isinstance(item, dict) for item in records):
        raise ToolError("JSONL must contain one object per nonblank line; no file was changed")
    return json.dumps({
        "repaired": False,
        "path": str(path),
        "records": len(records),
        "operation": "already structurally valid JSONL; no file change",
        "approval_changed": False,
        "file_changed": False,
        "record_values_changed": False,
    }, indent=2)


def duration_ladder(args: dict) -> str:
    sys.path.insert(0, str(ROOT / "work"))
    import duration_ladder as dl
    cid = str(args.get("clip", "")).strip().upper()
    if CLIP_RE.match(cid):
        row = next((r for r in _json(EQ / "audio_pass_durations.json", {"clips": []})["clips"]
                    if r["id"] == cid), None)
        if not row:
            raise ToolError(f"no duration row for {cid}")
        rungs = dl.ladder(float(row["audio_pass_seconds"]),
                          max_frames=int(row["scripted_frames"]))
    else:
        secs = float(args.get("seconds", 0) or 0)
        if secs <= 0:
            raise ToolError("give clip= or seconds=")
        rungs = dl.ladder(secs)
    return json.dumps(rungs, indent=2)


# ── batch renderer tools ──────────────────────────────────────────────────────

_BATCH_FOLDER_PLACEHOLDERS = frozenset({
    "d:/jobs/scene12",
    "path/to/job",
    "your/job/folder",
    "...",
})


def _batch_job_folder(args: dict) -> Path:
    """Resolve a supplied job folder without ever accepting documentation examples."""
    raw = str(args.get("folder", "")).strip()
    if not raw:
        raise ToolError(
            "folder is required. Do not invent one; ask the operator for the actual "
            "existing job-folder path."
        )

    normalised = raw.replace("\\", "/").rstrip("/").casefold()
    if normalised in _BATCH_FOLDER_PLACEHOLDERS:
        raise ToolError(
            "No real job folder was supplied. 'D:/jobs/scene12' was a documentation "
            "example, not a project path. Ask the operator for the actual folder."
        )

    folder = Path(raw) if Path(raw).is_absolute() else ROOT / raw
    folder = folder.resolve()
    if not folder.is_dir():
        raise ToolError(
            f"{folder} is not a directory. Do not substitute another path; ask the "
            "operator for the intended existing job folder."
        )
    return folder


def batch_plan(args: dict) -> str:
    """Scan a job folder, pair refs, validate prompts, return the plan.

    Read-only — renders nothing and never touches outputs/equal_shares/**.
    """
    folder = _batch_job_folder(args)

    sys.path.insert(0, str(ROOT / "work"))
    import batch_render_folder as brf

    scan    = brf.scan_job(folder)
    renders = brf.build_render_plan(scan, folder, brf.DEFAULT_MP, brf.DEFAULT_DUR)

    plan_rows = []
    for r in renders:
        errors: list[str] = []
        if r["prompt_path"] and r["prompt_path"].is_file():
            raw_text  = r["prompt_path"].read_text(encoding="utf-8").strip()
            assembled = brf.assemble_prompt(raw_text, r["image_count"], r["has_video"])
            errors    = brf.validate_assembled_prompt(
                assembled, r["image_count"], r["has_video"], r["prompt_path"].name)
        else:
            errors = [f"missing prompt file: {r['prompt_path']}"]

        plan_rows.append({
            "render":       r["index"] + 1,
            "prompt":       str(r["prompt_path"]) if r["prompt_path"] else None,
            "video":        str(r["video_path"])  if r["video_path"]  else None,
            "images":       [str(p) for p in r["img_paths"]],
            "picture_tags": r["picture_tags"],
            "video_tag":    r["video_tag"],
            "duration":     r["duration"],
            "frames":       r["frames"],
            "output":       str(r["out_path"]),
            "valid":        not errors,
            "errors":       errors,
        })

    invalid = [row for row in plan_rows if not row["valid"]]
    return json.dumps({
        "job_folder":    str(folder),
        "render_count":  scan.render_count,
        "warnings":      scan.warnings,
        "invalid_count": len(invalid),
        "plan":          plan_rows,
    }, indent=2)


def batch_render(args: dict) -> str:
    """Propose a batch render command for operator approval. Never executes it.

    The agent must never start a batch render — the operator runs the returned
    command themselves after reviewing the plan from batch_plan.
    """
    folder = _batch_job_folder(args)

    extra: list[str] = []
    if args.get("limit"):
        extra += ["--limit", str(int(args["limit"]))]
    if args.get("megapixels"):
        extra += ["--megapixels", str(float(args["megapixels"]))]
    if args.get("duration"):
        extra += ["--duration", str(float(args["duration"]))]
    if args.get("force"):
        extra.append("--force")

    cmd = "python work/batch_render_folder.py " + str(folder)
    if extra:
        cmd += " " + " ".join(extra)

    return json.dumps({
        "requires_operator_approval": True,
        "command": cmd,
        "note": ("The local agent cannot start this. Run the command above from "
                 "the project root after reviewing batch_plan output."),
    }, indent=2)


def _pid_is_live(pid: object) -> bool:
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


def start_batch_render(args: dict) -> str:
    """Launch the isolated batch runner after strict preflight.

    ``__remote_render_identity`` is an internal value injected only by
    :func:`call` after it has authenticated a paired phone and checked that
    exact identity's explicit render-tool grant. It is never model-controlled.
    """
    folder = _batch_job_folder(args)
    remote_identity = str(args.get("__remote_render_identity") or "")
    try:
        folder.relative_to(EQ)
    except ValueError:
        pass
    else:
        raise ToolError("batch rendering never operates inside outputs/equal_shares")
    if bool(args.get("force")):
        raise ToolError("force is not allowed from the local agent; existing evidence is never replaced")

    # This sees resident Ollama as available but blocks a live owner or any
    # ComfyUI listener. That prevents the batch runner from interrupting a
    # backend it did not create.
    import router
    busy, reason, _detail = router.gpu_busy()
    if busy:
        raise ToolError(f"render preflight refused: {reason}")
    # A desktop render needs a visible one-shot gateway approval. A paired phone
    # can substitute its *separately granted, cryptographically authenticated*
    # render capability for that one-shot desktop card. The global Block mode
    # always wins, and every remote execution is audited by ``call`` below.
    import gpu_gate
    if remote_identity:
        if gpu_gate.snapshot().get("mode") == "block":
            raise ToolError("GPU gateway is set to Block; no render was started")
    else:
        gate = gpu_gate.request("ComfyUI batch render", source="desktop tool",
                                detail=str(folder), key=f"render:{folder}")
        if not gate.get("granted"):
            if gate.get("blocked"):
                raise ToolError("GPU gateway is set to Block; no render was started")
            raise ToolError("GPU permission pending in the sidebar; approve the batch render once, then retry")
    batch_owner = _json(ROOT / "batch_render_queue_owner.json", {})
    if _pid_is_live(batch_owner.get("pid")):
        raise ToolError(f"render preflight refused: another batch render owns the queue (pid={batch_owner['pid']})")

    # Read-only plan plus validation gate before starting any process.
    plan = json.loads(batch_plan({"folder": str(folder)}))
    if not int(plan.get("render_count", 0)):
        raise ToolError("render preflight refused: the job folder has no prompts to render")
    if int(plan.get("invalid_count", 0)):
        raise ToolError(f"render preflight refused: {plan['invalid_count']} prompt(s) failed validation; repair them first")

    try:
        limit = args.get("limit")
        limit = int(limit) if limit not in (None, "") else None
        if limit is not None and limit <= 0:
            raise ValueError
        megapixels = args.get("megapixels")
        megapixels = float(megapixels) if megapixels not in (None, "") else None
        if megapixels is not None and not 0.4 <= megapixels <= 2.0:
            raise ValueError
        duration = args.get("duration")
        duration = float(duration) if duration not in (None, "") else None
        if duration is not None and not 1.0 <= duration <= 60.0:
            raise ValueError
    except (TypeError, ValueError):
        raise ToolError("limit must be positive; megapixels must be 0.4–2.0; duration must be 1–60 seconds")

    runner = ROOT / "work" / "batch_render_folder.py"
    if not runner.is_file():
        raise ToolError("batch renderer is missing")
    argv = [PY, str(runner), str(folder)]
    if limit is not None:
        argv += ["--limit", str(limit)]
    if megapixels is not None:
        argv += ["--megapixels", str(megapixels)]
    if duration is not None:
        argv += ["--duration", str(duration)]

    log_dir = folder / "batch_runtime" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"agent_batch_{time.strftime('%Y%m%d_%H%M%S')}.log"
    log = log_path.open("ab")
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(argv, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
                                creationflags=flags)
    except Exception:
        log.close()
        raise
    log.close()
    return json.dumps({
        "started": True,
        "pid": proc.pid,
        "job_folder": str(folder),
        "planned_renders": plan["render_count"],
        "limit": limit,
        "log": str(log_path),
        "note": "The runner owns its queue lock, thermal guard, and ComfyUI lifecycle. It creates no overwrite path.",
    }, indent=2)


def _chat_render_conversation(args: dict) -> str:
    """Return the trusted server/bridge-injected conversation id, never a model value."""
    cid = str(args.get("__conversation_id", "")).strip()
    if not cid:
        raise ToolError("this action is available only from a desktop chat")
    return cid


def prepare_chat_render(args: dict) -> str:
    """Build an immutable job from the latest complete prompt set in this chat."""
    import chat_render_jobs
    try:
        prepared = chat_render_jobs.prepare_from_chat(_chat_render_conversation(args))
    except chat_render_jobs.ChatRenderError as exc:
        raise ToolError(str(exc))
    return json.dumps({"prepared": True, **prepared}, indent=2)


def start_current_chat_render(args: dict) -> str:
    """Prepare then launch the latest valid prompt set from this trusted chat."""
    import chat_render_jobs
    try:
        prepared = chat_render_jobs.prepare_from_chat(_chat_render_conversation(args))
    except chat_render_jobs.ChatRenderError as exc:
        raise ToolError(str(exc))
    launch_args = {key: value for key, value in args.items()
                   if key in {"limit", "megapixels", "duration"}}
    if args.get("__remote_render_identity"):
        launch_args["__remote_render_identity"] = str(args["__remote_render_identity"])
    launch_args["folder"] = prepared["job_folder"]
    launched = json.loads(start_batch_render(launch_args))
    return json.dumps({"prepared": prepared, "launch": launched}, indent=2)


def _powershell_pid_list(command: str) -> list[int]:
    """Run one fixed read-only PID query and normalise its numeric output."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode:
            return []
        return sorted({int(value) for value in re.findall(r"\d+", proc.stdout)
                       if int(value) > 0})
    except subprocess.SubprocessError:
        return []


def _port_8188_listener_ids() -> list[int]:
    """Read TCP listeners without CIM/WMI (which is denied on some desktops)."""
    try:
        proc = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                              text=True, timeout=10)
        pids: set[int] = set()
        for line in proc.stdout.splitlines():
            if "LISTENING" not in line.upper() or ":8188" not in line:
                continue
            match = re.search(r"\s(\d+)\s*$", line)
            if match:
                pids.add(int(match.group(1)))
        return sorted(pids)
    except subprocess.SubprocessError:
        return []


def _process_path(pid: int) -> str:
    """Return one PID's executable path without requiring WMI/CIM access."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue).Path"],
            capture_output=True, text=True, timeout=5,
        )
        return proc.stdout.strip()
    except (TypeError, ValueError, subprocess.SubprocessError):
        return ""


def _comfyui_process_ids() -> list[int]:
    """Find only locally-running ComfyUI processes, never arbitrary Python."""
    # The listener catches a differently-packaged ComfyUI. The path/command-line
    # query catches a backend that has just crashed and released its socket.
    listener = _port_8188_listener_ids()
    python_pids = _powershell_pid_list(
        # Wildcard avoids PowerShell returning a failure just because pythonw
        # is absent, which would otherwise hide every running python.exe PID.
        "Get-Process -Name python* -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty Id"
    )
    comfy = [pid for pid in python_pids
             if "\\comfyui\\" in _process_path(pid).lower()]
    return sorted(set(listener + comfy))


def _request_elevated_comfyui_stop() -> bool:
    """Ask Windows for a one-time UAC-confirmed execution of the fixed helper."""
    helper = Path(__file__).resolve().parent / "STOP_COMFYUI_ELEVATED.ps1"
    if not helper.is_file():
        return False
    quoted = str(helper).replace("'", "''")
    command = (
        "Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList "
        "@('-NoProfile','-ExecutionPolicy','Bypass','-File','%s')" % quoted
    )
    try:
        # This opens Windows' consent prompt. It never passes a caller-supplied
        # process, path, or command to the elevated process.
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                              capture_output=True, text=True, timeout=15)
        return proc.returncode == 0
    except subprocess.SubprocessError:
        return False


def stop_all_comfyui(_: dict) -> str:
    """Emergency desktop stop for the active batch runner and all ComfyUI backends.

    This does not touch uploads, prompts, rendered outputs, Ollama, or the local
    agent. It is intentionally a fixed-target recovery action rather than a
    general process-killer.
    """
    interrupt_sent = False
    try:
        request = urllib.request.Request(
            "http://127.0.0.1:8188/interrupt", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(request, timeout=4).read()
        interrupt_sent = True
    except Exception:
        pass

    owner_path = ROOT / "batch_render_queue_owner.json"
    owner = _json(owner_path, {})
    target_pids = set(_comfyui_process_ids())
    if _pid_is_live(owner.get("pid")):
        target_pids.add(int(owner["pid"]))

    stopped: list[int] = []
    failures: list[int] = []
    for pid in sorted(target_pids):
        try:
            proc = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, text=True, timeout=15,
            )
            (stopped if proc.returncode == 0 else failures).append(pid)
        except subprocess.SubprocessError:
            failures.append(pid)

    # Some ComfyUI launches are elevated, while the desktop chat app is not.
    # The fixed helper repeats the same target discovery only after Windows UAC
    # consent; this is safer than silently widening desktop privileges.
    elevation_requested = _request_elevated_comfyui_stop() if failures else False

    # A forced batch-runner stop cannot execute its normal finally block. This
    # is a small lock-state reset, never a render/evidence mutation.
    released = False
    if owner.get("pid") and not _pid_is_live(owner.get("pid")):
        owner_path.write_text(json.dumps({
            "pid": 0,
            "released_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "purpose": "emergency ComfyUI stop",
        }, indent=2) + "\n", encoding="utf-8")
        released = True

    # Give Windows a moment to release the port and CUDA allocation before the
    # next routed chat/model request checks availability.
    for _ in range(10):
        if not _comfyui_process_ids():
            break
        time.sleep(0.5)
    import router
    busy, reason, _detail = router.gpu_busy()
    return json.dumps({
        "interrupted": interrupt_sent,
        "stopped_pids": stopped,
        "failed_pids": failures,
        "elevation_requested": elevation_requested,
        "batch_queue_released": released,
        "gpu_busy": busy,
        "gpu_reason": reason,
        "preserved": "prompts, uploads, source media, and renders were not changed",
    }, indent=2)


# ── comfyui-mcp wrappers (explicit whitelist, not a raw MCP passthrough) ──────

_COMFY_GENERATE_TOOL = "generate_image"
_COMFY_WORKFLOW_TOOLS = frozenset({
    "enqueue_workflow", "queue", "create_workflow", "visualize_workflow",
    "get_workflow", "save_workflow",
})
_COMFY_ASSET_TOOLS = frozenset({"get_image", "upload_image"})
_COMFY_MODEL_TOOLS = frozenset({"download_model", "list_local_models"})
_COMFY_NODE_TOOLS = frozenset({"search_custom_nodes", "install_custom_node", "node_pack"})
_COMFY_SYSTEM_TOOLS = frozenset({"get_system_stats", "clear_vram", "get_history", "comfy_cli"})
_COMFY_PROCESS_TOOL = "restart_comfyui"
_COMFY_AUDIT_PATH = Path(__file__).resolve().parent / "runtime" / "comfy_mcp_audit.jsonl"
_LAST_COMFY_AUDIT: tuple | None = None
_IMAGE_RENDER_OWNER = ROOT / "work" / "runtime" / "image_render_owner.json"
_COMFY_WORKFLOW_MAX_BYTES = 4 * 1024 * 1024
_ENQUEUE_PATH_KEYS = ("workflow_path", "path", "file", "filename")


def _mcp_format(result) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, ensure_ascii=False, default=str)


def _mcp_call(mcp_tool: str, args: dict):
    import mcp_client
    try:
        return mcp_client.call(mcp_tool, args)
    except mcp_client.McpError as exc:
        raise ToolError(str(exc)) from exc


def _comfy_caller() -> dict:
    """Identify who invoked a comfy_* wrapper: pid, argv, first frame outside tools.py."""
    info = {
        "pid": os.getpid(),
        "argv0": sys.argv[0] if sys.argv else "",
    }
    here = Path(__file__).resolve()
    frame = inspect.currentframe()
    try:
        while frame is not None:
            frame = frame.f_back
            if frame is None:
                break
            try:
                fname = Path(frame.f_code.co_filename).resolve()
            except (OSError, RuntimeError):
                continue
            if fname == here:
                continue
            info["file"] = str(fname)
            info["function"] = frame.f_code.co_name
            info["line"] = frame.f_lineno
            break
    finally:
        del frame
    return info


def _extract_prompt_id(result) -> str | None:
    """Pull ComfyUI prompt_id out of an MCP generate_image /prompt return."""
    data = result
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    for key in ("prompt_id", "promptId"):
        value = data.get(key)
        if value:
            return str(value)
    nested = data.get("result")
    if isinstance(nested, dict):
        for key in ("prompt_id", "promptId"):
            value = nested.get(key)
            if value:
                return str(value)
    return None


def last_comfy_audit() -> tuple | None:
    """Process-local ``(offset, prompt_id, caller_file)`` from the last JSONL write.

    Overwritten on every audited comfy_* call. Not the model-visible tool result.
    """
    return _LAST_COMFY_AUDIT


def _comfy_audit(local_tool: str, mcp_tool: str, args: dict, extra: dict | None = None) -> None:
    """Durable JSONL record for generate / irreversible / code-execution-risk MCP actions.

    Writes binary JSONL so ``tell()`` is a stable byte offset on Windows.
    Tracing gets a pointer (offset + prompt_id + caller_file), never a copy
    of ``args`` / the generate prompt.
    """
    global _LAST_COMFY_AUDIT
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "local_tool": local_tool,
        "mcp_tool": mcp_tool,
        "action": args.get("action"),
        "args": {k: v for k, v in args.items() if k != "__remote_render_identity"},
    }
    if extra:
        record.update(extra)
    line = (json.dumps(record, ensure_ascii=False, default=str) + "\n").encode("utf-8")
    try:
        _COMFY_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _COMFY_AUDIT_PATH.open("ab") as fh:
            offset = fh.tell()
            fh.write(line)
    except OSError as exc:
        raise ToolError(f"failed to write comfy MCP audit log: {exc}") from exc

    extra = extra or {}
    caller = extra.get("caller") if isinstance(extra.get("caller"), dict) else {}
    prompt_id = extra.get("prompt_id")
    caller_file = caller.get("file")
    mcp_status = extra.get("mcp_status")
    _LAST_COMFY_AUDIT = (offset, prompt_id, caller_file)
    try:
        import tracing
        span = tracing.current_span()
        if span is not None:
            span.link(
                "comfy_mcp_audit",
                target=f"runtime/comfy_mcp_audit.jsonl#{offset}",
                offset=offset,
                ts=time.time(),
                extra={
                    "prompt_id": prompt_id,
                    "mcp_status": mcp_status,
                    "caller_file": caller_file,
                },
            )
    except Exception:
        logging.getLogger("local_agent.tracing").warning(
            "comfy audit span link failed", exc_info=True)


def _pop_mcp_tool(args: dict, allowed: frozenset[str], default: str | None = None) -> tuple[str, dict]:
    payload = dict(args or {})
    name = str(payload.pop("tool", "") or payload.pop("mcp_tool", "") or default or "").strip()
    if name not in allowed:
        raise ToolError(
            f"tool must be one of {sorted(allowed)}; got {name or '(missing)'!r}. "
            "This is not a raw MCP passthrough."
        )
    return name, payload


def _resolve_workflow_file(raw: str) -> Path:
    """Absolute or repo-relative path, same rule as read_file. No URLs."""
    text = str(raw or "").strip().strip("\"'")
    if not text:
        raise ToolError("workflow path is empty")
    if re.match(r"https?://", text, re.I):
        raise ToolError(
            "workflow path cannot be a URL; pass a local JSON file or the "
            "parsed graph object"
        )
    p = (Path(text) if Path(text).is_absolute() else ROOT / text).resolve()
    if not p.is_file():
        raise ToolError(f"workflow file not found: {p}")
    return p


def _normalize_api_graph(data: object, *, source: str) -> dict:
    """Accept API-format graphs; unwrap a top-level prompt wrapper."""
    if not isinstance(data, dict):
        raise ToolError(
            f"{source}: workflow JSON must be an object (node id -> "
            f"{{class_type, inputs}}), not {type(data).__name__}"
        )
    graph = data.get("prompt") if isinstance(data.get("prompt"), dict) else data
    if not isinstance(graph, dict) or not graph:
        raise ToolError(f"{source}: workflow graph is empty")
    if isinstance(graph.get("nodes"), list) and "class_type" not in graph:
        raise ToolError(
            f"{source}: UI-format workflow (nodes/links) is not accepted; "
            "save API format (node id -> {{class_type, inputs}}) or use "
            "get_workflow"
        )
    nodes = [
        node for node in graph.values()
        if isinstance(node, dict) and node.get("class_type")
    ]
    if not nodes:
        raise ToolError(
            f"{source}: no class_type nodes; enqueue_workflow needs ComfyUI "
            "API format, not a file path string and not a UI export"
        )
    return graph


def _load_workflow_file(raw: str) -> dict:
    path = _resolve_workflow_file(raw)
    size = path.stat().st_size
    if size > _COMFY_WORKFLOW_MAX_BYTES:
        raise ToolError(
            f"workflow file {path} is {size} bytes; cap is "
            f"{_COMFY_WORKFLOW_MAX_BYTES}"
        )
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ToolError(f"cannot read workflow file {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolError(f"workflow file {path} is not valid JSON: {exc}") from exc
    return _normalize_api_graph(data, source=str(path))


def _coerce_enqueue_workflow(payload: dict) -> dict:
    """Load a path/JSON-string `workflow` server-side. Models must not inline graphs.

    Live 2026-09-05b: models passed workflow_path=... then workflow="<path>".
    MCP requires a record. Resolve here; strip path aliases so they never
    reach comfyui-mcp.
    """
    out = dict(payload)
    path_raw = None
    for key in _ENQUEUE_PATH_KEYS:
        value = out.pop(key, None)
        if value and path_raw is None:
            path_raw = value
    graph = out.get("workflow")
    if isinstance(graph, dict):
        out["workflow"] = _normalize_api_graph(graph, source="workflow")
        return out
    if isinstance(graph, str):
        text = graph.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if parsed is not None:
                out["workflow"] = _normalize_api_graph(parsed, source="workflow JSON string")
                return out
        path_raw = path_raw or text
    if path_raw:
        out["workflow"] = _load_workflow_file(str(path_raw))
    return out


def _thermal_blocks_comfy_process() -> str | None:
    """Return a refusal reason if thermal_guard's current sample forbids process control.

    thermal_guard.py has no on-disk 'state file' — its state is a live
    nvidia-smi sample plus the START_MAX_C / EMERGENCY_C ceilings. Unknown
    telemetry fails closed, same as router.gpu_busy().
    """
    work = str(ROOT / "work")
    if work not in sys.path:
        sys.path.insert(0, work)
    import thermal_guard
    try:
        sample = thermal_guard.sample_gpu()
    except thermal_guard.ThermalTelemetryError as exc:
        return f"thermal telemetry unavailable ({exc}); unknown GPU heat is never permission to restart ComfyUI"
    if sample.temperature_c >= thermal_guard.EMERGENCY_C:
        return (
            f"GPU {sample.temperature_c} C reached thermal_guard emergency ceiling "
            f"{thermal_guard.EMERGENCY_C} C"
        )
    if sample.temperature_c > thermal_guard.START_MAX_C:
        return (
            f"GPU {sample.temperature_c} C exceeds thermal_guard start ceiling "
            f"{thermal_guard.START_MAX_C} C"
        )
    return None


def _supervisor_owns_comfyui() -> str | None:
    """Return a refusal reason if the stage supervisor or a local render dispatch owns ComfyUI.

    Same live-PID owner checks start_batch_render already uses, plus the Equal
    Shares stage-supervisor lock and the image-render owner. A listening 8188
    alone is not enough to refuse — that would make restart of an unmanaged
    backend impossible. Owning the process is.
    """
    import router
    owned, why = router.queue_owner()
    if owned:
        return f"stage supervisor owns ComfyUI ({why})"
    batch_owner = _json(ROOT / "batch_render_queue_owner.json", {})
    if _pid_is_live(batch_owner.get("pid")):
        return f"batch render owns the queue (pid={batch_owner['pid']})"
    image_owner = _json(_IMAGE_RENDER_OWNER, {})
    if _pid_is_live(image_owner.get("pid")):
        return f"image renderer owns ComfyUI (pid={image_owner['pid']})"
    return None


def comfy_process_preflight() -> None:
    """Refuse restart_comfyui when thermal_guard or a live supervisor owns the GPU."""
    thermal = _thermal_blocks_comfy_process()
    if thermal:
        raise ToolError(f"comfy_process refused: {thermal}")
    owner = _supervisor_owns_comfyui()
    if owner:
        raise ToolError(f"comfy_process refused: {owner}")


def comfy_generate(args: dict) -> str:
    """Wrap comfyui-mcp generate_image (image/controlnet/ip_adapter/video/3d/upscale/remove_background/audio).

    Every call (desktop agent or a probe script) appends
    runtime/comfy_mcp_audit.jsonl with timestamp, caller, args, and prompt_id.

    filename_prefix is forwarded to MCP but is a documented no-op for
    action image / controlnet / ip_adapter / upscale — comfyui-mcp hardcodes
    SaveImage to "ComfyUI". See docs/COMFYUI_MCP_INTEGRATION_PLAN.md.
    Probe scripts that need isolated files must use mcp_test_output.py, not
    this wrapper's filename_prefix.
    """
    payload = dict(args or {})
    payload.pop("tool", None)
    payload.pop("mcp_tool", None)
    if not payload.get("action"):
        payload["action"] = "image"
    extra = {"risk": "generate", "caller": _comfy_caller()}
    try:
        result = _mcp_call(_COMFY_GENERATE_TOOL, payload)
    except ToolError as exc:
        extra["mcp_status"] = "error"
        extra["error"] = str(exc)
        extra["prompt_id"] = None
        _comfy_audit("comfy_generate", _COMFY_GENERATE_TOOL, payload, extra)
        raise
    extra["mcp_status"] = "ok"
    extra["prompt_id"] = _extract_prompt_id(result)
    _comfy_audit("comfy_generate", _COMFY_GENERATE_TOOL, payload, extra)
    return _mcp_format(result)


# Bounded poll for /history/{prompt_id}. Does not wait forever. Default 90s,
# hard cap 300s. Backoff 0.5s doubling to 5s. Uses ComfyUI HTTP, not MCP, so
# an in-flight generate holding the MCP lock cannot stall the status probe.
COMFY_JOB_STATUS_TIMEOUT_S = 90.0
COMFY_JOB_STATUS_TIMEOUT_MAX_S = 300.0
COMFY_JOB_STATUS_BACKOFF_START_S = 0.5
COMFY_JOB_STATUS_BACKOFF_MAX_S = 5.0
COMFY_JOB_STATUS_HTTP_TIMEOUT_S = 2.0
_COMFY_PROMPT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
_COMFY_HISTORY_MEDIA_KEYS = ("images", "gifs", "videos", "files")


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _comfy_history_url(prompt_id: str) -> str:
    import mcp_client
    base = str(mcp_client.COMFYUI_URL).rstrip("/")
    return f"{base}/history/{urllib.parse.quote(prompt_id, safe='')}"


def _fetch_comfy_history(prompt_id: str):
    url = _comfy_history_url(prompt_id)
    try:
        with urllib.request.urlopen(url, timeout=COMFY_JOB_STATUS_HTTP_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {}
        raise ToolError(f"ComfyUI /history HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise ToolError(f"ComfyUI /history unreadable: {exc}") from exc


def _history_entry(payload, prompt_id: str) -> dict | None:
    if not isinstance(payload, dict):
        return None
    if not payload:
        return None
    entry = payload.get(prompt_id)
    if isinstance(entry, dict):
        return entry
    if "outputs" in payload or "status" in payload:
        return payload
    if len(payload) == 1:
        only = next(iter(payload.values()))
        if isinstance(only, dict):
            return only
    return None


def _history_output_items(entry: dict) -> list[dict]:
    outputs = entry.get("outputs")
    if not isinstance(outputs, dict):
        return []
    items: list[dict] = []
    for node_out in outputs.values():
        if not isinstance(node_out, dict):
            continue
        for key in _COMFY_HISTORY_MEDIA_KEYS:
            block = node_out.get(key)
            if not isinstance(block, list):
                continue
            for item in block:
                if not isinstance(item, dict) or not item.get("filename"):
                    continue
                kind = str(item.get("type") or "output").lower()
                if kind != "output":
                    continue
                items.append({
                    "filename": Path(str(item["filename"])).name,
                    "subfolder": str(item.get("subfolder") or "").replace("\\", "/"),
                    "type": "output",
                    "media_key": key,
                })
    return items


def parse_comfy_history(payload, prompt_id: str) -> dict:
    """Classify a /history payload. No filesystem I/O."""
    entry = _history_entry(payload, prompt_id)
    if entry is None:
        return {"state": "pending", "prompt_id": prompt_id, "outputs": []}
    status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
    status_str = str(status.get("status_str") or "")
    completed = bool(status.get("completed"))
    items = _history_output_items(entry)
    if status_str.lower() in {"error", "failed"} or (
            completed and status_str.lower() not in {"success", ""} and not items):
        return {
            "state": "error",
            "prompt_id": prompt_id,
            "status_str": status_str,
            "outputs": items,
        }
    if completed or items:
        return {
            "state": "complete",
            "prompt_id": prompt_id,
            "status_str": status_str or "success",
            "outputs": items,
        }
    return {"state": "pending", "prompt_id": prompt_id, "outputs": items}


def comfy_job_status(args: dict) -> str:
    """Read-only: poll ComfyUI /history/{prompt_id} until complete, error, or timeout.

    Bounded: default 90s, cap 300s (timeout_s). Backoff 0.5s → 5s. Does not
    hold the MCP lock. If still running at the deadline, returns state=pending
    so the caller can invoke this tool again. Does not invent a file path.
    """
    prompt_id = str((args or {}).get("prompt_id") or "").strip()
    if not _COMFY_PROMPT_ID_RE.fullmatch(prompt_id):
        raise ToolError(
            "prompt_id is required and must be the ComfyUI id from comfy_generate "
            "(8-80 characters, letters/digits/._- only)"
        )
    raw_timeout = (args or {}).get("timeout_s", COMFY_JOB_STATUS_TIMEOUT_S)
    if raw_timeout is None:
        raw_timeout = COMFY_JOB_STATUS_TIMEOUT_S
    try:
        timeout_s = float(raw_timeout)
    except (TypeError, ValueError):
        timeout_s = COMFY_JOB_STATUS_TIMEOUT_S
    timeout_s = max(0.0, min(timeout_s, COMFY_JOB_STATUS_TIMEOUT_MAX_S))
    deadline = time.monotonic() + timeout_s
    delay = COMFY_JOB_STATUS_BACKOFF_START_S
    polls = 0
    started = time.monotonic()
    last: dict = {"state": "pending", "prompt_id": prompt_id, "outputs": []}
    while True:
        polls += 1
        last = parse_comfy_history(_fetch_comfy_history(prompt_id), prompt_id)
        last["polls"] = polls
        last["waited_s"] = round(time.monotonic() - started, 3)
        if last["state"] in {"complete", "error"}:
            break
        # timeout_s=0 is a single snapshot. Do not sleep: tests mock _sleep
        # without advancing the clock, and a zero budget means "look once".
        remaining = deadline - time.monotonic()
        if timeout_s <= 0 or remaining <= 0:
            last["state"] = "pending"
            last["timeout"] = True
            last["timeout_s"] = timeout_s
            last["note"] = (
                f"still running after {timeout_s:.0f}s bounded poll; "
                "call comfy_job_status again"
            )
            break
        _sleep(min(delay, remaining))
        delay = min(delay * 2, COMFY_JOB_STATUS_BACKOFF_MAX_S)
    return json.dumps(last, indent=2, ensure_ascii=False)


def comfy_workflow(args: dict) -> str:
    """Wrap enqueue_workflow, queue, create_workflow, visualize_workflow, get_workflow, save_workflow.

    enqueue action: `workflow` may be the API-format object, a JSON string of
    that object, or a local file path. `workflow_path` / `path` are aliases.
    The wrapper loads and parses the file; do not inline the graph in the
    tool call.
    """
    name, payload = _pop_mcp_tool(args, _COMFY_WORKFLOW_TOOLS)
    action = str(payload.get("action") or "").strip().lower()
    if name == "enqueue_workflow" and action in {"", "enqueue"}:
        if not action:
            payload["action"] = "enqueue"
        payload = _coerce_enqueue_workflow(payload)
    else:
        for key in _ENQUEUE_PATH_KEYS:
            payload.pop(key, None)
    return _mcp_format(_mcp_call(name, payload))


def comfy_assets(args: dict) -> str:
    """Wrap get_image and upload_image."""
    name, payload = _pop_mcp_tool(args, _COMFY_ASSET_TOOLS, default="get_image")
    return _mcp_format(_mcp_call(name, payload))


def comfy_models(args: dict) -> str:
    """Wrap download_model and list_local_models (including remove)."""
    name, payload = _pop_mcp_tool(args, _COMFY_MODEL_TOOLS)
    action = str(payload.get("action") or "")
    if name == "list_local_models" and action == "remove":
        _comfy_audit("comfy_models", name, payload, {"risk": "model_delete"})
    elif name == "download_model" and action in {"download", "download_civitai"}:
        _comfy_audit("comfy_models", name, payload, {"risk": "model_download"})
    return _mcp_format(_mcp_call(name, payload))


def comfy_nodes(args: dict) -> str:
    """Wrap search_custom_nodes, install_custom_node, node_pack."""
    name, payload = _pop_mcp_tool(args, _COMFY_NODE_TOOLS)
    if name in {"install_custom_node", "node_pack"}:
        _comfy_audit("comfy_nodes", name, payload, {"risk": "custom_node_install"})
    return _mcp_format(_mcp_call(name, payload))


def comfy_system(args: dict) -> str:
    """Wrap get_system_stats, clear_vram, get_history, comfy_cli."""
    name, payload = _pop_mcp_tool(args, _COMFY_SYSTEM_TOOLS, default="get_system_stats")
    if name == "get_system_stats" and not payload.get("action"):
        payload["action"] = "stats"
    return _mcp_format(_mcp_call(name, payload))


def comfy_process(args: dict) -> str:
    """Wrap restart_comfyui after thermal_guard + supervisor-ownership checks."""
    payload = dict(args or {})
    payload.pop("tool", None)
    payload.pop("mcp_tool", None)
    if not payload.get("action"):
        payload["action"] = "restart"
    action = str(payload.get("action"))
    if action not in {"start", "stop", "restart"}:
        raise ToolError("comfy_process action must be start, stop, or restart")
    comfy_process_preflight()
    _comfy_audit("comfy_process", _COMFY_PROCESS_TOOL, payload, {"risk": "process_control"})
    return _mcp_format(_mcp_call(_COMFY_PROCESS_TOOL, payload))


def remember_fact(args: dict) -> str:
    """Store a durable operator fact. Only call when explicitly asked ('remember that…')."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import memory as _mem
    fact = str(args.get("fact", "")).strip()
    if not fact:
        raise ToolError("fact is required")
    category = str(args.get("category", "general")).strip() or "general"
    return _mem.remember(fact, category)


def list_memory(_: dict) -> str:
    """List all active remembered facts with their ids."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import memory as _mem
    facts = _mem.list_facts()
    if not facts:
        return "[Source: persistent memory]\nno facts remembered yet"
    return "[Source: persistent memory]\n" + json.dumps(facts, indent=2)


def forget_fact(args: dict) -> str:
    """Move a fact to the forgotten archive (never hard-deletes). Use list_memory first."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import memory as _mem
    idx = args.get("id")
    if idx is None:
        raise ToolError("id is required")
    return _mem.forget(int(idx))


def search_docs(args: dict) -> str:
    """Hybrid (lexical+embedding) search over the indexed project document tree.

    Returns chunks with source + heading. Falls back to lexical-only ranking
    if the embedding endpoint is unreachable. For a model-graded cited answer
    with retries, prefer agentic_search_docs.
    """
    import retrieval
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("query is required")
    max_results = min(int(args.get("max_results", 5)), 10)
    # A deterministic relevance filter prevents a generic lexical near-match
    # from being presented as project evidence.  It is a filter only; it does
    # not replace this tool's existing server-side boundary or validation.
    results = retrieval.search_relevant(query, max_results=max_results)
    if not results:
        return json.dumps({"query": query, "results": [],
                           "note": "No matching chunks found. Try different terms."})
    return json.dumps({"query": query, "results": results}, indent=2, ensure_ascii=False)


def agentic_search_docs(args: dict) -> str:
    """Preferred local-docs search when a grounded cited answer is needed.

    Retrieves with HybridScorer, has the model judge whether the evidence
    actually answers the question, and retries with rewritten queries
    (bounded) if not. Token-heavier than search_docs (which stays the fast
    concurrency-safe chunk-list lookup). Read-only.
    """
    import agentic_retrieval
    return agentic_retrieval.agentic_search_docs(args)


def list_changelog(_: dict) -> str:
    d = ROOT / "CHANGELOG"
    return "\n".join(sorted(p.name for p in d.glob("*.md"))) if d.is_dir() else "(none)"


def read_doc(args: dict) -> str:
    """Read one of a fixed set of documents. Not an arbitrary file read."""
    allowed = {
        "proven_facts": ROOT / "docs" / "GOLDEN_REFERENCE" / "PROVEN_FACTS.md",
        "golden_reference": ROOT / "docs" / "GOLDEN_REFERENCE" / "README.md",
        "prompt_rules": ROOT / "docs" / "H3_PROMPT_RULES.md",
        "runbook": ROOT / "docs" / "AUDIO_PASS_RUNBOOK.md",
        "claude_md": ROOT / "CLAUDE.md",
        "agent_questions": EQ / "runtime" / "agent_questions.md",
    }
    name = str(args.get("name", "")).strip().lower()
    if name not in allowed:
        raise ToolError(f"unknown doc {name!r}; choose from {sorted(allowed)}")
    p = allowed[name]
    if not p.is_file():
        raise ToolError(f"{p} not found")
    text = p.read_text(encoding="utf8")
    limit = int(args.get("max_chars", 6000))
    return text[:limit] + (f"\n\n[truncated at {limit} chars of {len(text)}]"
                           if len(text) > limit else "")


# ── build actions ─────────────────────────────────────────────────────────────

def _run(argv: list[str], timeout: int = 900) -> str:
    r = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
    return f"exit {r.returncode}\n{out.strip()[:8000]}"


BUILD = {
    "classify_voices": [PY, "work/classify_voice_requirements.py"],
    "build_prompts": [PY, "work/build_native_r2v_prompts.py"],
    "build_durations": [PY, "work/build_audio_pass_durations.py"],
    "sync_config": [PY, "work/sync_omni_audio_config.py"],
    "check_config": [PY, "work/sync_omni_audio_config.py", "--check"],
    "build_auditions": [PY, "work/build_voice_auditions.py", "--out",
                        r"A:\Users\rhine\Desktop\EQUAL_SHARES_VOICE_AUDITIONS"],
    "audition_dry_run": [PY, "work/render_voice_auditions.py", "--dry-run"],
    "rebuild_knowledge": [PY, "local_agent/build_knowledge_pack.py"],
    "validate_all_prompts": [PY, "local_agent/validate_h3_prompt.py", "--dir",
                             "outputs/equal_shares/prompts_native_r2v"],
}


def run_build(args: dict) -> str:
    name = str(args.get("action", "")).strip()
    if name not in BUILD:
        raise ToolError(f"unknown build action {name!r}; choose from {sorted(BUILD)}")
    return _run(BUILD[name])


# ── GPU actions — proposed only, never auto-run ───────────────────────────────

GPU = {
    "render_auditions": {
        "argv": [PY, "work/render_voice_auditions.py"],
        "why": "27 takes at 0.2 MP, roughly 2-3 hours. This is the current gate.",
    },
    "render_audio_pass": {
        "argv": [PY, "work/render_audio_pass.py"],
        "why": "all 124 soundtracks. BLOCKED until the operator has chosen voices.",
    },
}


def propose_gpu(args: dict) -> str:
    """Return the command for the operator to approve. Never executes it.

    The GUI shows this as a button. Even then the runner itself claims
    `render_queue_owner.json` and refuses to start beside another backend — one
    ComfyUI, ever.
    """
    name = str(args.get("action", "")).strip()
    if name not in GPU:
        raise ToolError(f"unknown gpu action {name!r}; choose from {sorted(GPU)}")
    spec = GPU[name]
    return json.dumps({
        "requires_operator_approval": True,
        "action": name,
        "command": " ".join(spec["argv"]),
        "why": spec["why"],
        "note": "The local agent cannot start this. Approve it in the GUI or run it "
                "in a terminal.",
    }, indent=2)


# ── file access ───────────────────────────────────────────────────────────────

# These project files must never be silently overwritten — they hold irreplaceable
# records. The write_file tool refuses them so the model cannot clobber them by
# accident; the operator can always edit them at a terminal.
_PROTECTED_NAMES = frozenset([
    "manifest.json", "audio_pass_manifest.json", "visual_audit.json",
    "generation_audit.json", "voice_requirements.json",
    "render_queue_owner.json", "agent_questions.md",
    "SYSTEM_PROMPT.md",        # legacy generated brief; hand-edits are lost anyway
    "EQUAL_SHARES_REFERENCE.md",  # rebuilt on every launch; hand-edits are lost anyway
])
_MAX_HEX_INSPECT_BYTES = 4096
_MAX_HEX_PATCH_BYTES = 4096


def read_file(args: dict) -> str:
    raw = str(args.get("path", "")).strip()
    if not raw:
        raise ToolError("path is required")
    p = (Path(raw) if Path(raw).is_absolute() else ROOT / raw).resolve()
    if not p.is_file():
        raise ToolError(f"{p} is not a file or does not exist")
    try:
        data = p.read_bytes()
    except Exception as e:
        raise ToolError(f"cannot read {p}: {e}")
    if b"\x00" in data[:1024]:
        raise ToolError(f"{p.name} appears to be binary; only text files are supported")
    text = data.decode("utf-8-sig", errors="replace")
    limit = int(args.get("max_chars", 12000))
    suffix = f"\n\n[truncated at {limit} of {len(text)} chars]" if len(text) > limit else ""
    return f"[File: {p}]\n\n" + text[:limit] + suffix


def inspect_workspace(args: dict) -> str:
    """Report a supplied project root's type and candidate authoritative docs.

    The inspection is deliberately read-only and never changes the active chat
    workspace.  This prevents a path heuristic from smuggling in specialist
    context, a render permission, or an edit authority.
    """
    raw = str(args.get("root", "")).strip()
    if not raw:
        raise ToolError("root is required")
    import workspace_inspector
    try:
        return json.dumps(workspace_inspector.inspect(raw), indent=2, ensure_ascii=False)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


def write_file(args: dict) -> str:
    raw = str(args.get("path", "")).strip()
    if not raw:
        raise ToolError("path is required")
    content = args.get("content")
    if content is None:
        raise ToolError("content is required")
    p = (Path(raw) if Path(raw).is_absolute() else ROOT / raw).resolve()
    if p.name in _PROTECTED_NAMES:
        raise ToolError(
            f"{p.name} is a protected project file. Edit it at a terminal if certain.")
    # A concrete desktop-chat request already authorizes a normal text edit.
    # Protected records still refuse here; remote identities are gated at the
    # dispatch boundary, and binary patching retains exact-byte approval.
    existed = p.is_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(content), encoding="utf-8")
    return f"{'overwrote' if existed else 'created'} {p}  ({len(str(content))} chars)"


def propose_file_diff(args: dict) -> str:
    """Show a complete text-file change without writing it.

    This intentionally shares write_file's protected-file behaviour: a preview
    must never become a route around the evidence-record safeguard.
    """
    raw = str(args.get("path", "")).strip()
    if not raw:
        raise ToolError("path is required")
    content = args.get("content")
    if content is None:
        raise ToolError("content is required")
    p = (Path(raw) if Path(raw).is_absolute() else ROOT / raw).resolve()
    if p.name in _PROTECTED_NAMES:
        raise ToolError(
            f"{p.name} is a protected project file. Edit it at a terminal if certain.")
    before = p.read_text(encoding="utf-8") if p.is_file() else ""
    after = str(content)
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=str(p), tofile=str(p), lineterm=""))
    return diff or f"No changes proposed for {p}."


def inspect_binary(args: dict) -> str:
    """Return a bounded hex/ASCII view of a binary file without changing it."""
    raw = str(args.get("path", "")).strip()
    if not raw:
        raise ToolError("path is required")
    p = (Path(raw) if Path(raw).is_absolute() else ROOT / raw).resolve()
    if not p.is_file():
        raise ToolError(f"{p} is not a file or does not exist")
    try:
        offset = int(args.get("offset", 0))
        length = int(args.get("length", 256))
    except (TypeError, ValueError) as exc:
        raise ToolError("offset and length must be integers") from exc
    if offset < 0 or length < 1 or length > _MAX_HEX_INSPECT_BYTES:
        raise ToolError(f"offset must be non-negative and length must be 1–{_MAX_HEX_INSPECT_BYTES}")
    try:
        size = p.stat().st_size
        with p.open("rb") as fh:
            fh.seek(offset)
            data = fh.read(length)
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError as exc:
        raise ToolError(f"cannot read {p}: {exc}") from exc
    if offset > size:
        raise ToolError(f"offset {offset} is beyond file size {size}")
    ascii_view = "".join(chr(b) if 32 <= b <= 126 else "." for b in data)
    return json.dumps({
        "path": str(p), "size": size, "sha256": digest, "offset": offset,
        "length": len(data), "hex": data.hex(" ").upper(), "ascii": ascii_view,
    }, indent=2)


_ARTIFACT_ID_RE = re.compile(r"^artifact_[0-9a-f]{16}$")
_MAX_ARTIFACT_READ_CHARS = 8000


def read_artifact(args: dict) -> str:
    """Read back one bounded slice of a previously pruned large tool result.

    A tool result larger than its context budget is stored in full locally
    and replaced, in the model's context, with a pointer (see
    artifacts.prune_large_text). Until this tool existed that pointer was a
    dead end — nothing could ever resolve it back into text. This is
    deliberately a paging read, not an automatic re-inject or summary: the
    model must ask for a specific bounded slice by offset, so it always knows
    exactly how much of the original it has actually seen, rather than being
    handed an unrequested chunk it could mistake for the whole result.
    """
    artifact_id = str(args.get("artifact_id", "")).strip()
    if not _ARTIFACT_ID_RE.match(artifact_id):
        raise ToolError(
            "artifact_id must look like artifact_<16 hex chars>, copied exactly "
            "from a prior tool result's pruned-output pointer")
    path = artifacts.ARTIFACT_DIR / f"{artifact_id}.json"
    if not path.is_file():
        raise ToolError(
            f"no stored artifact {artifact_id!r} (it may be from a different "
            "chat/session, or was never actually produced)")
    try:
        offset = int(args.get("offset", 0))
        length = int(args.get("length", 4000))
    except (TypeError, ValueError) as exc:
        raise ToolError("offset and length must be integers") from exc
    if offset < 0 or length < 1 or length > _MAX_ARTIFACT_READ_CHARS:
        raise ToolError(
            f"offset must be non-negative and length must be 1-{_MAX_ARTIFACT_READ_CHARS}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"cannot read artifact {artifact_id}: {exc}") from exc
    content = str(payload.get("content", ""))
    total = len(content)
    if offset > total:
        raise ToolError(f"offset {offset} is beyond the stored content length {total}")
    chunk = content[offset:offset + length]
    end = offset + len(chunk)
    return json.dumps({
        "artifact_id": artifact_id, "kind": payload.get("kind"), "total_chars": total,
        "offset": offset, "length": len(chunk), "text": chunk,
        "more_remaining": end < total,
        "next_offset": end if end < total else None,
    }, indent=2)


def _hex_bytes(value, field: str) -> bytes:
    if not isinstance(value, str):
        raise ToolError(f"{field} must be a hexadecimal string")
    compact = "".join(value.split())
    if not compact:
        raise ToolError(f"{field} must not be empty")
    if len(compact) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", compact):
        raise ToolError(f"{field} must contain complete hexadecimal bytes, for example '4D 5A'")
    return bytes.fromhex(compact)


def apply_hex_patch(args: dict) -> str:
    """Apply one approved, exact, fixed-length byte replacement to a binary file."""
    raw = str(args.get("path", "")).strip()
    if not raw:
        raise ToolError("path is required")
    p = (Path(raw) if Path(raw).is_absolute() else ROOT / raw).resolve()
    if p.name in _PROTECTED_NAMES or p.is_relative_to(EQ):
        raise ToolError("protected Equal Shares evidence cannot be changed with the hex editor")
    if not p.is_file():
        raise ToolError(f"{p} is not a file or does not exist; the hex editor never creates files")
    try:
        offset = int(args.get("offset"))
    except (TypeError, ValueError) as exc:
        raise ToolError("offset is required and must be a non-negative integer") from exc
    if offset < 0:
        raise ToolError("offset must be a non-negative integer")
    expected = _hex_bytes(args.get("expected_hex"), "expected_hex")
    replacement = _hex_bytes(args.get("replacement_hex"), "replacement_hex")
    if len(expected) != len(replacement):
        raise ToolError("hex edits must replace the same number of bytes; inserts and deletions are not allowed")
    if len(expected) > _MAX_HEX_PATCH_BYTES:
        raise ToolError(f"hex edits are limited to {_MAX_HEX_PATCH_BYTES} bytes per approved patch")
    try:
        before = p.read_bytes()
    except OSError as exc:
        raise ToolError(f"cannot read {p}: {exc}") from exc
    actual = before[offset:offset + len(expected)]
    if actual != expected:
        raise ToolError("expected_hex does not match the current bytes at that offset; inspect the file again before patching")
    original_sha256 = hashlib.sha256(before).hexdigest()
    approval_record = json.dumps({
        "kind": "hex_patch_v1", "path": str(p), "original_sha256": original_sha256,
        "offset": offset, "expected_hex": expected.hex().upper(),
        "replacement_hex": replacement.hex().upper(),
    }, sort_keys=True, separators=(",", ":"))
    import file_edit_gate
    approval = file_edit_gate.request(p, approval_record, metadata={
        "kind": "exact byte patch", "offset": offset, "bytes": len(expected),
        "before": expected.hex().upper(), "after": replacement.hex().upper(),
        "original_sha256": original_sha256,
    })
    if not approval.get("granted"):
        raise ToolError("explicit byte-patch permission is pending in the sidebar; approve this exact patch once, then retry")
    current = p.read_bytes()
    if hashlib.sha256(current).hexdigest() != original_sha256:
        raise ToolError("the file changed after approval; inspect it again and request a new exact patch")
    if current[offset:offset + len(expected)] != expected:
        raise ToolError("the bytes changed after approval; inspect it again and request a new exact patch")
    try:
        with p.open("r+b") as fh:
            fh.seek(offset)
            fh.write(replacement)
            fh.flush()
    except OSError as exc:
        raise ToolError(f"cannot patch {p}: {exc}") from exc
    after_sha256 = hashlib.sha256(p.read_bytes()).hexdigest()
    return json.dumps({
        "patched": True, "path": str(p), "offset": offset, "bytes": len(expected),
        "before": expected.hex(" ").upper(), "after": replacement.hex(" ").upper(),
        "original_sha256": original_sha256, "sha256": after_sha256,
    }, indent=2)


# ── controlled developer workspace ───────────────────────────────────────────

_SAFE_CHECKS = {
    "agent_tests": [PY, "-m", "unittest", "local_agent/test_native_tool_calling.py"],
    "routing_tests": [PY, "local_agent/test_router_switching.py"],
    "context_tests": [PY, "local_agent/test_context_resilience.py"],
    "prompt_validation": [PY, "local_agent/validate_h3_prompt.py", "--dir", "outputs/equal_shares/prompts_native_r2v"],
}


def write_candidate_tool(args: dict) -> str:
    """Save a proposed helper script in an isolated, non-executable workspace."""
    name = str(args.get("name", "")).strip()
    content = args.get("content")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}\.py", name):
        raise ToolError("candidate name must be a simple .py filename")
    if content is None:
        raise ToolError("content is required")
    DEV_WORKSPACE.mkdir(parents=True, exist_ok=True)
    path = DEV_WORKSPACE / name
    if path.exists():
        raise ToolError(f"candidate already exists: {name}; create a new versioned filename")
    path.write_text(str(content), encoding="utf8")
    return (f"candidate saved: {path}. It cannot run or replace project code. "
            "To try it, copy the contents into the sandbox and call run_code. "
            "Review it, add a regression test, then promote it manually.")


def run_code(args: dict) -> str:
    """Execute code only inside local_agent/sandbox/run_<id>/."""
    import sandbox_runner as _sb
    try:
        return _sb.run_code(args or {})
    except _sb.SandboxError as e:
        raise ToolError(str(e)) from e


def run_safe_check(args: dict) -> str:
    """Run one fixed, non-rendering regression command."""
    action = str(args.get("action", "")).strip()
    if action not in _SAFE_CHECKS:
        raise ToolError(f"unknown safe check {action!r}; choose from {sorted(_SAFE_CHECKS)}")
    return _run(_SAFE_CHECKS[action], timeout=900)


def list_dir(args: dict) -> str:
    raw = str(args.get("path", "")).strip() or "."
    p = (Path(raw) if Path(raw).is_absolute() else ROOT / raw).resolve()
    if not p.is_dir():
        raise ToolError(f"{p} is not a directory")
    entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
    lines = []
    for e in entries[:200]:
        tag = "DIR " if e.is_dir() else "    "
        lines.append(f"{tag}{e.name}")
    if len(list(p.iterdir())) > 200:
        lines.append("... (truncated at 200 entries)")
    return f"{p}\n" + "\n".join(lines)


# ── web access ────────────────────────────────────────────────────────────────

class _Stripper(html.parser.HTMLParser):
    """Strip HTML to readable text. Standard library only."""
    # Tags whose content is always invisible (code, UI elements, etc.)
    _SKIP = frozenset(["script", "style", "noscript", "select", "option",
                       "textarea", "iframe"])
    _BREAK = frozenset(["p", "br", "li", "div", "h1", "h2", "h3", "h4", "h5", "tr"])

    def __init__(self):
        super().__init__()
        self._buf: list[str] = []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._depth += 1
        if tag in self._BREAK:
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if not self._depth:
            self._buf.append(data)

    def text(self) -> str:
        raw = "".join(self._buf)
        lines = [l.strip() for l in raw.split("\n")]
        non_empty = "\n".join(l for l in lines if l)
        return re.sub(r"\n{2,}", "\n\n", non_empty).strip()


_BINARY_CTYPES = (
    "application/pdf", "application/octet-stream", "application/zip",
    "application/wasm", "application/vnd.", "application/x-",
    "image/", "audio/", "video/", "font/",
)


def fetch_url(args: dict) -> str:
    url = str(args.get("url", "")).strip()
    if not url.startswith(("http://", "https://")):
        raise ToolError("url must start with http:// or https://")
    limit = int(args.get("max_chars", 8000))
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            final_url = resp.geturl()
            ctype = resp.headers.get("Content-Type", "")
            if any(ctype.lower().startswith(p) for p in _BINARY_CTYPES):
                return (f"REFUSED: {url} serves {ctype or 'binary content'}. "
                        f"Only text and HTML URLs are supported.")
            raw = resp.read(400_000).decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        return f"ERROR fetching {url}: {e}"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
    redirect_note = f"\n[redirected from {url}]" if final_url != url else ""
    if "html" in ctype.lower() or raw.lstrip().startswith("<"):
        s = _Stripper()
        s.feed(raw)
        text = s.text()
    else:
        text = raw
    suffix = f"\n\n[truncated at {limit} chars]" if len(text) > limit else ""
    return f"[{final_url}]{redirect_note}\n\n{text[:limit]}{suffix}"


def web_search(args: dict) -> str:
    """Search the web. For project-specific questions, check read_doc or read_file first.

    Reports the failure reason clearly: no internet | rate-limited | zero results |
    parse failure — never silently returns nothing.
    """
    import search_backend
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("query is required")
    max_chars = int(args.get("max_chars", 6000))
    backend = None
    try:
        backend = search_backend.get_backend()
        items = backend.search(query, max_results=8)
    except search_backend.SearchError as exc:
        name = backend.name if backend is not None else (
            os.environ.get("EQUAL_SHARES_SEARCH_BACKEND") or "duckduckgo")
        return search_backend.web_search_error_text(query, exc, backend=str(name))
    return search_backend.format_results_text(
        query, items, backend=getattr(backend, "name", "search"), max_chars=max_chars)


def deep_research(args: dict) -> str:
    """Plan sub-queries, fetch several sources, synthesize a cited answer.

    Token-heavy. Routes through the existing GPU/CPU router and must not force
    the GPU while a render owns the card. Read-only: never writes files or
    starts ComfyUI.
    """
    import deep_research as _dr
    return _dr.deep_research(args)


def dispatch_subtasks(args: dict) -> str:
    """Coordinator/worker fan-out: answer several independent sub-questions
    concurrently, each a tool-free CPU worker call, then return them labeled
    for you to synthesize. For genuinely independent sub-questions only (e.g.
    comparing several unrelated topics) — not for steps that depend on each
    other's answers, and not a substitute for this agent's normal tools:
    workers have no tool access at all.
    """
    import subtask_dispatch
    try:
        return subtask_dispatch.dispatch_json(args)
    except subtask_dispatch.DispatchError as e:
        raise ToolError(str(e)) from e


# ── local media analysis ─────────────────────────────────────────────────────

def _media(name: str, args: dict) -> str:
    import media_tools
    return getattr(media_tools, name)(args)


def capabilities(args: dict) -> str: return _media("capabilities", args)
def see_image(args: dict) -> str: return _media("see_image", args)
def video_frames(args: dict) -> str: return _media("video_frames", args)
def analyze_video(args: dict) -> str: return _media("analyze_video", args)
def extract_video_actions(args: dict) -> str: return _media("extract_video_actions", args)


def plan_video_from_reference(args: dict) -> str:
    """Planning only: can this install turn a reference video + character still
    into a new clip with that character performing the reference motion?

    Reports, per approach (Wan 2.2 Animate 14B / Wan 2.1 VACE 1.3B /
    AnimateDiff SDXL + pose ControlNet + IP-Adapter), what is installed and
    exactly which weights or nodes are missing with sizes, the frame plan for
    the clip's full length, and the GVD route decision. Never renders, never
    starts ComfyUI, never loads a model, never downloads. 2026-09-25q;
    docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md.
    """
    import motion_transfer
    fps = args.get("target_fps")
    try:
        result = motion_transfer.plan(
            args.get("reference_video") or args.get("video") or args.get("path"),
            args.get("character_image") or args.get("image"),
            target_fps=float(fps) if fps not in (None, "") else None)
    except motion_transfer.PlanError as exc:
        return f"ERROR: plan_video_from_reference: {exc}"
    except (TypeError, ValueError) as exc:
        return f"ERROR: plan_video_from_reference: {exc}"
    return json.dumps(result, indent=2, ensure_ascii=False)


def render_video_from_reference(args: dict) -> str:
    """ACTUALLY RENDER a reference-video motion transfer in the BACKGROUND.

    The character still's identity performs the reference clip's body motion
    (AnimateDiff-SDXL + union-promax pose ControlNet + IP-Adapter, FaceID in a
    video face-detail pass; motion_transfer_render.py). Same discipline as
    render_story_image: router.gpu_busy / Equal Shares owner / port 8188 /
    live image owner refusals and the gpu_gate approval under
    _IMAGE_RENDER_LAUNCH_LOCK, then one background job that owns one private
    backend. Desktop only. Returns a job_id immediately; nothing exists yet.
    """
    if args.get("__remote_render_identity"):
        raise ToolError("render_video_from_reference is desktop-only; no render was started")
    import motion_transfer_render as mtr
    try:
        spec = mtr.prepare_request(_public_args(args))
    except mtr.RenderRequestError as exc:
        raise ToolError(f"render_video_from_reference: {exc}") from exc
    sys.path.insert(0, str(ROOT / "work"))
    import image_render
    import router
    import gpu_gate
    with _IMAGE_RENDER_LAUNCH_LOCK:
        busy, reason, detail = router.gpu_busy()
        if busy:
            if isinstance(detail, dict) and detail.get("comfy_port_8188") == "listening":
                raise _port_8188_refusal()
            raise ToolError(f"motion-transfer preflight refused: {reason}")
        if image_render._live_owner():
            raise ToolError("motion-transfer preflight refused: an Equal Shares render owns the GPU")
        if image_render._port_open():
            raise _port_8188_refusal()
        existing = _image_owner_snapshot()
        if _pid_is_live(existing.get("pid")):
            raise ToolError("motion-transfer preflight refused: another render owns the backend "
                            f"(pid={existing.get('pid')})")
        gate = gpu_gate.request("ComfyUI motion-transfer video render", source="desktop tool",
                                detail=f"{Path(spec['reference_video']['path']).name} -> "
                                       f"{spec['frames']} frames",
                                key=f"motion_transfer:{spec['reference_video']['sha256'][:16]}")
        if not gate.get("granted"):
            if gate.get("blocked"):
                raise ToolError("GPU gateway is set to Block; no video render was started")
            raise ToolError("GPU permission pending in the sidebar; approve the video render once, then retry")
        job_id, job_dir = mtr.new_job(spec)
        log_path = job_dir / "runner.log"
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        with log_path.open("ab") as log:
            proc = subprocess.Popen([PY, str(Path(mtr.__file__).resolve()), "--job-dir", str(job_dir)],
                                    cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, env=env,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        mtr.record_launch(job_dir, proc.pid)
    minutes = 2 + round(spec["frames"] / 24 * 10)
    return json.dumps({
        "started": True, "job_id": job_id, "pid": proc.pid, "job_dir": str(job_dir), "log": str(log_path),
        "frames": spec["frames"], "fps": spec["target_fps"], "windows": spec["windows"],
        "size": f"{spec['width']}x{spec['height']}", "size_measured": spec["size_measured"],
        "estimated_minutes": f"{minutes}-{minutes + 13}",
        "note": ("Running in the background: backend start can take up to ~15 minutes on a cold disk, "
                 "then roughly 10 minutes per 24 frames. No video exists yet. Call "
                 "video_reference_job_status with this job_id; only report a video when it says "
                 "state=complete and verified_outputs=true, and say that likeness and motion still "
                 "need the operator's own visual check."),
    }, indent=2)


def video_reference_job_status(args: dict) -> str:
    """Read-only: state, evidence and identity score of a render_video_from_reference job."""
    import motion_transfer_render as mtr
    try:
        return json.dumps(mtr.job_status(str(args.get("job_id") or "")), indent=2, ensure_ascii=False)
    except mtr.RenderRequestError as exc:
        raise ToolError(str(exc)) from exc


def _media_job_view(job: dict, *, full_result: bool) -> dict:
    status = str(job.get("status") or "")
    a = job.get("args") or {}
    images = a.get("images") or []
    source = a.get("path") or a.get("video_path") or (images[0] if images else None)
    view = {
        "job_id": job.get("id"), "kind": job.get("kind"), "status": status,
        "source": source, "queued_at": job.get("queued_at"),
        "started_at": job.get("started_at"), "done_at": job.get("done_at"),
        "progress": job.get("progress"),
    }
    if status == "done":
        raw = str(job.get("result") or "")
        if full_result:
            try:
                view["result"] = json.loads(raw)
            except Exception:
                view["result"] = raw
        else:
            view["result_chars"] = len(raw)
        view["message"] = ("Complete. result is the analysis the original tool "
                           "would have returned had the model been loaded.")
    elif status == "failed":
        view["error"] = job.get("error")
        view["message"] = ("The watcher ran this job and it failed; it is not "
                           "retried automatically.")
    elif status == "cancelled":
        view["cancel_reason"] = job.get("cancel_reason")
        view["message"] = "Cancelled before it ran; call the original tool again to re-queue it."
    elif status == "processing":
        view["message"] = "The watcher is running this job now; ask again shortly."
    else:
        view["message"] = ("Still waiting in the queue; the background watcher runs it "
                           "when the GPU is free. Nothing has been analysed yet.")
    return view


def media_job_status(args: dict) -> str:
    """Read-only status / result of a queued media analysis job.

    analyze_video, see_image, extract_video_actions and transcribe return
    {"queued": true, "job_id": ...} when the exact VLM runtime is not active
    (or a render owns the GPU). The media watcher runs the job later and files
    the result under media_queue/done/<job_id>.json. Before 2026-09-25q nothing
    could bring that result back into a chat. Never loads a model or touches
    the GPU; reads queue JSON only.
    """
    import media_queue as mq
    job_id = str(args.get("job_id") or "").strip()
    path = str(args.get("path") or "").strip()
    if not job_id and not path:
        return ("ERROR: media_job_status needs job_id (from the queued tool result) "
                "or path (the analysed file).")
    if job_id:
        job = mq.get(job_id)
        if not job:
            return (f"ERROR: no media job {job_id!r} in any queue state "
                    "(pending, processing, done, failed, cancelled).")
        return json.dumps(_media_job_view(job, full_result=True), indent=2,
                          ensure_ascii=False)
    jobs = mq.find_for_path(path)
    if not jobs:
        return json.dumps({"path": path, "jobs": [],
                           "message": "No media job has been queued for this path."},
                          indent=2, ensure_ascii=False)
    latest_done = next((j for j in jobs if j.get("status") == "done"), None)
    return json.dumps({
        "path": path,
        "jobs": [_media_job_view(j, full_result=False) for j in jobs],
        "latest_done": (_media_job_view(latest_done, full_result=True)
                        if latest_done else None),
    }, indent=2, ensure_ascii=False)
def read_video_metadata(args: dict) -> str: return _media("read_video_metadata", args)
def audio_measure(args: dict) -> str: return _media("audio_measure", args)
def transcribe(args: dict) -> str: return _media("transcribe", args)
def compare_voice(args: dict) -> str: return _media("compare_voice", args)


# ── general storyboard still-image planning ──────────────────────────────────

_STORY_IMAGE_MODEL = "RealVisXL_V5.0_fp16.safetensors"


def plan_story_image(args: dict) -> str:
    """Build a general still-image graph without starting ComfyUI or loading a model."""
    try:
        sys.path.insert(0, str(ROOT / "work"))
        import image_render
        mode = str(args.get("mode", "t2i")).strip().lower()
        model_profile = str(args.get("model_profile", "realvisxl")).strip().lower()
        profile_data = image_render.MODEL_PROFILES.get(model_profile)
        if not profile_data:
            raise ToolError("model_profile must be realvisxl, realpro_flux, or alicemix_sd15")
        defaults = image_render.profile_defaults(model_profile)
        story = image_render._safe_segment(str(args.get("story", "")).strip(), "story")
        prompt = str(args.get("prompt", "")).strip()
        negative = str(args.get("negative", image_render.DEFAULT_NEGATIVE)).strip()
        seed = int(args.get("seed", 1))
        width = int(args.get("width", defaults["width"]))
        height = int(args.get("height", defaults["height"]))
        steps = int(args.get("steps", defaults["steps"]))
        cfg = float(args.get("cfg", defaults["cfg"]))
        denoise = float(args.get("denoise", 0.55 if mode == "i2i" else 1.0))
        hires_fix = bool(args.get("hires_fix", True))
        face_detail = bool(args.get("face_detail", False))
    except (TypeError, ValueError) as exc:
        raise ToolError(f"image-plan parameters are invalid: {exc}") from exc

    if not 1 <= seed <= 2**63 - 1:
        raise ToolError("seed must be a positive 64-bit integer")
    if not 1 <= steps <= 60:
        raise ToolError("steps must be 1–60")
    if not 1.0 <= cfg <= 20.0:
        raise ToolError("cfg must be 1.0–20.0")
    reference = args.get("reference_name")
    if reference is not None:
        reference = Path(str(reference)).name
        if not reference or reference in {".", ".."}:
            raise ToolError("reference_name must be a simple uploaded filename")
    prefix = f"stories/{story}/renders/PLANNED"
    try:
        graph = image_render.build_graph(
            mode=mode, prompt=prompt, negative=negative, model=profile_data["model"],
            seed=seed, width=width, height=height, steps=steps, cfg=cfg,
            sampler=defaults["sampler"], scheduler=defaults["scheduler"], denoise=denoise,
            prefix=prefix, reference_name=reference, hires_fix=hires_fix,
            face_detail=face_detail, profile=model_profile,
        )
    except image_render.ImageRenderError as exc:
        raise ToolError(str(exc)) from exc
    return json.dumps({
        "planned": True,
        "model": profile_data["model"],
        "model_profile": model_profile,
        "mode": mode,
        "story": story,
        "output_tree": f"outputs/stories/{story}/",
        "model_load": False,
        "gpu_action": "none",
        "face_detail": face_detail,
        "next_step": (
            "This is a read-only graph plan ONLY. No model was loaded, no GPU work "
            "ran, and no image file was written anywhere, including under "
            f"outputs/stories/{story}/ — that folder does not exist yet. Do not tell "
            "the operator an image was generated, rendered, saved, or is ready — none "
            "of that happened. For a CLIP start/end still sheet, dedupe chained frames "
            "and call render_story_image_batch with ALL unique start/end frames in one "
            "batch — no artificial batch size limit; never tell the operator a "
            "batch was capped (model_profile=realpro_flux when Flux was requested) "
            "so they run sequentially; or call "
            "render_story_image then await_story_image_job / story_image_job_status. "
            "Do not dump many plan_story_image calls and claim ready. After stills "
            "exist, present them for review and wait — do not start video yet."
        ),
        "graph": graph,
    }, indent=2)


_IMAGE_JOB_LOG_DIR = ROOT / "work" / "runtime" / "agent_image_jobs"
# The desktop and a paired phone can both call render_story_image at nearly
# the same instant (ThreadingHTTPServer serves both concurrently). Without
# this lock, two threads could both pass the "no other image render owns the
# backend" check before either subprocess has written image_render.py's own
# owner file, and both would go on to fight over port 8188 — exactly the
# "one backend, ever" invariant this project treats as sacred. This closes
# the race for two callers inside this one running agent process; it does
# not add cross-process protection beyond what image_render.py's own
# check-then-write owner file already provides (same limitation as the
# pre-existing Equal Shares batch_owner check elsewhere in this file).
_IMAGE_RENDER_LAUNCH_LOCK = threading.Lock()

_PORT_8188_REFUSAL = "image-render preflight refused: another ComfyUI backend is already listening on port 8188"


class Port8188BusyError(ToolError):
    """render_story_image refused because something already holds port 8188.

    ``blocked_by`` says who: ``kind="draining_image_job"`` is this agent's own
    previous still job still tearing down its private backend (image_render.py
    writes its manifest *before* stopping that backend, so the next batch job
    routinely lands in this window), while ``kind="foreign_backend"`` is some
    other pipeline's ComfyUI that will not go away on its own. Callers branch
    on this instead of pattern-matching refusal text — 2026-09-23: the router's
    wording ("a ComfyUI backend is listening on port 8188") did not match the
    batch's retry filter, so a resident Grok-launched backend failed job 1
    instantly with a message the agent could only paraphrase as a vague
    "backend issue".
    """

    def __init__(self, message: str, blocked_by: dict):
        super().__init__(message)
        self.blocked_by = blocked_by


def _process_ancestry(pid: int, depth: int = 4) -> list[dict]:
    """Best-effort pid -> parent chain with command lines (CIM may be denied)."""
    script = (
        f"$out=@(); $p={int(pid)}; for($i=0; $i -lt {int(depth)} -and $p; $i++){{ "
        "$w=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $p) -ErrorAction SilentlyContinue; "
        "if(-not $w){break}; "
        "$c=''; if($w.CreationDate){$c=$w.CreationDate.ToString('yyyy-MM-dd HH:mm:ss')}; "
        "$out+=[pscustomobject]@{pid=[int]$w.ProcessId; ppid=[int]$w.ParentProcessId; "
        "created=$c; cmd=[string]$w.CommandLine}; $p=$w.ParentProcessId }; "
        "ConvertTo-Json -Compress -InputObject @($out)"
    )
    try:
        proc = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                              capture_output=True, text=True, timeout=10)
        data = json.loads(proc.stdout or "[]")
    except (subprocess.SubprocessError, ValueError, OSError):
        return []
    if isinstance(data, dict):
        data = [data]
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _comfy_queue_counts(timeout: float = 3.0) -> dict | None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8188/queue", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return {"running": len(data.get("queue_running") or []),
                "pending": len(data.get("queue_pending") or [])}
    except Exception:
        return None


def _describe_port_8188_holder() -> dict:
    """Name whatever foreign process holds 8188 so the refusal is actionable."""
    info: dict = {"kind": "foreign_backend", "port": 8188,
                  "listener_pids": _port_8188_listener_ids()}
    pid = info["listener_pids"][0] if info["listener_pids"] else None
    chain = _process_ancestry(pid) if pid else []
    if chain:
        info["process"] = chain[0]
        # ComfyUI's venv shim re-execs main.py under a second python.exe, so
        # the first ancestor that is not main.py is the actual launcher.
        launcher = next((c for c in chain[1:] if "main.py" not in str(c.get("cmd") or "")), None)
        if launcher:
            info["launcher"] = launcher
    elif pid:
        info["process"] = {"pid": pid, "exe": _process_path(pid)}
    info["queue"] = _comfy_queue_counts()
    batch_owner = _json(ROOT / "batch_render_queue_owner.json", {}) or {}
    if _pid_is_live(batch_owner.get("pid")):
        info["batch_render_owner"] = {"pid": batch_owner.get("pid"), "purpose": batch_owner.get("purpose")}

    held_by = "an unidentified process"
    proc_info = info.get("process") or {}
    if proc_info.get("pid"):
        held_by = f"pid {proc_info['pid']}"
        if proc_info.get("created"):
            held_by += f" (started {proc_info['created']})"
    if info.get("launcher", {}).get("cmd"):
        held_by += f", launched by {str(info['launcher']['cmd']).strip()[:240]}"
    if info.get("batch_render_owner"):
        held_by += (f", claimed by the batch renderer pid {info['batch_render_owner']['pid']}"
                    f" ({info['batch_render_owner'].get('purpose') or '?'})")
    queue = info["queue"]
    if queue and (queue["running"] or queue["pending"]):
        state = (f"It is actively rendering ({queue['running']} running, {queue['pending']} pending). "
                 "Wait for that render to finish, then stop that backend or retry.")
    else:
        state = ("Its queue is " + ("idle" if queue else "unreadable") + ", so it is most likely a "
                 "resident backend left running by the video pipeline or another launcher; it will "
                 "not exit on its own. Stop it (close its launcher, or stop_all_comfyui once the "
                 "operator confirms nothing else needs it), then retry.")
    info["summary"] = (f"port 8188 is held by {held_by}. The stills renderer only runs on its own "
                       f"private ComfyUI and will not share or stop another pipeline's backend. {state}")
    return info


def _port_8188_refusal() -> Port8188BusyError:
    owner = _image_owner_snapshot()
    if _pid_is_live(owner.get("pid")):
        blocked_by = {"kind": "draining_image_job", "port": 8188, "image_owner_pid": owner.get("pid"),
                      "summary": (f"the previous still-image job (pid {owner.get('pid')}) is still "
                                  "shutting down its private backend")}
    else:
        blocked_by = _describe_port_8188_holder()
    return Port8188BusyError(f"{_PORT_8188_REFUSAL}: {blocked_by['summary']}", blocked_by)


def render_story_image(args: dict) -> str:
    """Actually execute a general still-image render via the guarded owned backend.

    This is the counterpart ``plan_story_image`` used to say did not exist.
    ``work/image_render.py --execute --allow-model-load`` already implements
    the real GPU-ownership / port-8188 / thermal preflight discipline (it
    refuses an existing Equal Shares owner or ComfyUI listener, starts its own
    throwaway backend on a private input/output tree under
    ``work/runtime/image_render_runtime/``, submits the graph, polls for
    output, then always stops its backend and releases its own lock). This
    tool adds the two things that script cannot do for itself: the same
    ``router.gpu_busy()`` / ``gpu_gate`` desktop-approval gate every other GPU
    action in this agent goes through, and running it in the background so a
    ~1-5 minute backend-start-plus-render doesn't block the chat turn.

    Call ``story_image_job_status`` afterward to find out whether it actually
    finished — do not assume completion just because this call returned.
    """
    try:
        sys.path.insert(0, str(ROOT / "work"))
        import image_render
        mode = str(args.get("mode", "t2i")).strip().lower()
        model_profile = str(args.get("model_profile", "realvisxl")).strip().lower()
        profiles = getattr(image_render, "MODEL_PROFILES", {"realvisxl": {"model": _STORY_IMAGE_MODEL,
                                                                             "defaults": {"width": 1024, "height": 1024, "steps": 35, "cfg": 6.0, "sampler": "dpmpp_2m_sde", "scheduler": "karras"}}})
        if model_profile not in profiles:
            raise ToolError("model_profile must be realvisxl, realpro_flux, or alicemix_sd15")
        defaults = dict(profiles[model_profile].get("defaults") or {"width": 1024, "height": 1024,
                                                                       "steps": 35, "cfg": 6.0, "sampler": "dpmpp_2m_sde", "scheduler": "karras"})
        story = image_render._safe_segment(str(args.get("story", "")).strip(), "story")
        prompt = str(args.get("prompt", "")).strip()
        negative = str(args.get("negative", image_render.DEFAULT_NEGATIVE)).strip()
        seed = int(args.get("seed", 1))
        width = int(args.get("width", defaults["width"]))
        height = int(args.get("height", defaults["height"]))
        steps = int(args.get("steps", defaults["steps"]))
        cfg = float(args.get("cfg", defaults["cfg"]))
        denoise = float(args.get("denoise", 0.55 if mode == "i2i" else 1.0))
        hires_fix = bool(args.get("hires_fix", True))
        face_detail = bool(args.get("face_detail", False))
    except (TypeError, ValueError) as exc:
        raise ToolError(f"image-render parameters are invalid: {exc}") from exc
    if mode not in {"t2i", "i2i"}:
        raise ToolError("mode must be t2i or i2i")
    if model_profile == "realpro_flux" and face_detail:
        raise ToolError(
            "face_detail is not available with model_profile=realpro_flux "
            "(the isolated custom-node startup this needs is not repaired yet). "
            "Omit face_detail for this render, or use model_profile=realvisxl if a "
            "face-repair pass is required."
        )
    # Older/lightweight test doubles expose only the long-standing RealVisXL
    # surface.  Preserve that default path while production image_render
    # supplies the expanded explicit profile registry.
    if not prompt:
        raise ToolError("prompt is required")
    if not 1 <= seed <= 2**63 - 1:
        raise ToolError("seed must be a positive 64-bit integer")
    if width < 256 or height < 256 or width % 8 or height % 8:
        raise ToolError("width and height must be multiples of 8 and at least 256")
    if not 1 <= steps <= 60:
        raise ToolError("steps must be 1-60")
    if not 1.0 <= cfg <= 20.0:
        raise ToolError("cfg must be 1.0-20.0")
    if not 0.0 <= denoise <= 1.0:
        raise ToolError("denoise must be 0.0-1.0")
    reference = args.get("reference_name")
    if reference is not None:
        reference = Path(str(reference)).name
        if not reference or reference in {".", ".."}:
            raise ToolError("reference_name must be a simple uploaded filename")
    if mode == "i2i" and not reference:
        raise ToolError("reference_name is required for i2i")

    # Same desktop-approval gate every other GPU action in this agent goes
    # through. image_render.py's own preflight only checks the Equal Shares
    # owner, port 8188, and thermal — it has no concept of this agent's
    # gateway, so the gate has to live here, before the process is spawned.
    # Everything from the owner-liveness check through the launch (and a
    # bounded wait for the subprocess to confirm its own ownership) happens
    # under one lock — see _IMAGE_RENDER_LAUNCH_LOCK above.
    import router
    import gpu_gate
    with _IMAGE_RENDER_LAUNCH_LOCK:
        busy, reason, detail = router.gpu_busy()
        if busy:
            if isinstance(detail, dict) and detail.get("comfy_port_8188") == "listening":
                raise _port_8188_refusal()
            raise ToolError(f"image-render preflight refused: {reason}")
        if image_render._live_owner():
            raise ToolError("image-render preflight refused: an Equal Shares render owns the GPU")
        if image_render._port_open():
            raise _port_8188_refusal()
        if image_render.IMAGE_OWNER.is_file():
            try:
                existing = json.loads(image_render.IMAGE_OWNER.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
            if _pid_is_live(existing.get("pid")):
                raise ToolError(f"image-render preflight refused: another image render owns the backend (pid={existing['pid']})")

        remote_identity = str(args.get("__remote_render_identity") or "")
        if remote_identity:
            if gpu_gate.snapshot().get("mode") == "block":
                raise ToolError("GPU gateway is set to Block; no image render was started")
        else:
            gate = gpu_gate.request("ComfyUI still-image render", source="desktop tool",
                                    detail=f"story={story}", key=f"image_render:{story}")
            if not gate.get("granted"):
                if gate.get("blocked"):
                    raise ToolError("GPU gateway is set to Block; no image render was started")
                raise ToolError("GPU permission pending in the sidebar; approve the image render once, then retry")

        argv = [PY, str(ROOT / "work" / "image_render.py"),
                "--story", story, "--prompt", prompt, "--negative", negative,
                "--mode", mode, "--seed", str(seed), "--width", str(width),
                "--height", str(height), "--steps", str(steps), "--cfg", str(cfg),
                "--denoise", str(denoise), "--model-profile", model_profile,
                "--execute", "--allow-model-load"]
        if reference:
            argv += ["--reference", reference]
        if args.get('lora_name'):
            argv += ['--lora-name', str(args['lora_name']), '--lora-strength', str(args.get('lora_strength', 0.5))]
        if not hires_fix:
            argv += ["--no-hires-fix"]
        if face_detail:
            argv += ["--face-detail"]

        _IMAGE_JOB_LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        log_path = _IMAGE_JOB_LOG_DIR / f"{story}_{stamp}.log"
        log = log_path.open("ab")
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            # A prompt containing any character outside the Windows console's
            # codepage (cp1252) crashes image_render.py's own final status
            # print with UnicodeEncodeError — seen in production from a
            # single stray non-Latin character in an otherwise-normal prompt.
            # The manifest write just before that print always uses an
            # explicit encoding="utf-8" and is unaffected, so this crash was
            # cosmetic (the render itself always completed), but it still
            # pollutes the log with a traceback and a nonzero exit code.
            # Force UTF-8 the same way _start_owned_backend() already does
            # for the ComfyUI backend subprocess it launches.
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.Popen(argv, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=flags, env=env)
        except Exception:
            log.close()
            raise
        log.close()

        # Best-effort: wait briefly for the subprocess to write its own real
        # owner file before releasing the lock, so a second caller blocked on
        # this lock sees a genuine live claim rather than a still-empty one.
        # Bounded short because a hot GPU can make image_render.py's own
        # thermal wait (which runs before it writes the owner file) take much
        # longer than this — that is not a failure, just an untightened
        # residual race window, matching this codebase's existing tolerance
        # for the same pattern in the Equal Shares batch-owner check.
        for _ in range(25):
            if proc.poll() is not None:
                break
            try:
                owner_now = json.loads(image_render.IMAGE_OWNER.read_text(encoding="utf-8"))
            except Exception:
                owner_now = {}
            if int(owner_now.get("pid") or 0) == proc.pid:
                break
            time.sleep(0.2)
    return json.dumps({
        "started": True,
        "pid": proc.pid,
        "story": story,
        "face_detail": face_detail,
        "log": str(log_path),
        "note": ("Running in the background: the owned ComfyUI backend can take up to "
                 "~3 minutes to start and generation adds more time on top. No file "
                 "exists yet just because this call returned. Call "
                 "story_image_job_status with this pid and story to check real progress "
                 "— do not tell the operator an image was generated until that tool "
                 "reports a manifest."),
        "manifest_glob": f"outputs/stories/{story}/manifests/image_*.json",
    }, indent=2)


_STORY_JOB_LOG_STAMP_RE = re.compile(r"_(\d{8}_\d{6})\.log$")


def _story_job_started_at(log_path: str) -> float | None:
    """Launch time from render_story_image's '<story>_<YYYYmmdd_HHMMSS>.log' name."""
    match = _STORY_JOB_LOG_STAMP_RE.search(str(log_path or ""))
    if not match:
        return None
    try:
        return time.mktime(time.strptime(match.group(1), "%Y%m%d_%H%M%S"))
    except (ValueError, OverflowError):
        return None


def story_image_job_status(args: dict) -> str:
    """Read-only: is a render_story_image job still running, and did it finish?

    Never call this only once and assume silence means failure — a real
    render can legitimately take several minutes. Poll it again rather than
    guessing.
    """
    pid = args.get("pid")
    story = str(args.get("story", "")).strip()
    log_path = str(args.get("log", "")).strip()
    # Only used to pick the QA continuity anchor (chat-scoped fallback).
    conversation_id = str(args.get("__conversation_id") or args.get("conversation_id") or "").strip()
    if not story:
        raise ToolError("story is required")
    sys.path.insert(0, str(ROOT / "work"))
    import image_render
    try:
        safe_story = image_render._safe_segment(story, "story")
    except image_render.ImageRenderError as exc:
        raise ToolError(str(exc)) from exc

    running = _pid_is_live(pid) if pid is not None else None
    owner = _image_owner_snapshot()
    owner_pid = 0
    try:
        owner_pid = int(owner.get("pid") or 0)
    except (TypeError, ValueError):
        owner_pid = 0
    # Positive evidence only: an on-disk owner record that was released (pid 0 /
    # purpose=released). A missing owner file is NOT "released" — the job may
    # still be starting and has not written its claim yet.
    owner_released = bool(owner) and (
        owner_pid <= 0 or str(owner.get("purpose") or "") == "released"
    )
    # Stale-PID fix: when the owner was explicitly released or the job PID is
    # dead, do not keep reporting running (Windows os.kill flakes).
    if running and pid is not None:
        try:
            job_pid = int(pid)
        except (TypeError, ValueError):
            job_pid = 0
        if owner_released:
            try:
                sys.path.insert(0, str(ROOT / "work"))
                import image_render as _ir_status
                port_busy = bool(_ir_status._port_open())
            except Exception:
                port_busy = False
            if not _pid_is_live(job_pid) or not port_busy:
                running = False
        elif owner_pid and job_pid and owner_pid != job_pid and not _pid_is_live(job_pid):
            running = False
    manifests_dir = ROOT / "outputs" / "stories" / safe_story / "manifests"
    manifests = sorted(manifests_dir.glob("image_*.json")) if manifests_dir.is_dir() else []
    # image_render.py writes a manifest exactly once, on completion. When the
    # job's launch time is known (render_story_image's log name carries it),
    # a manifest from an earlier render of the same story is not this job's
    # result — reporting it would put the previous image in front of the
    # operator as if it were the new one. Earliest manifest after launch wins.
    job_started = _story_job_started_at(log_path)
    if job_started is not None:
        manifests = [p for p in manifests if p.stat().st_mtime >= job_started - 2.0]
    latest_manifest = None
    newest = None
    if manifests:
        newest = (min if job_started is not None else max)(
            manifests, key=lambda p: p.stat().st_mtime)
        try:
            latest_manifest = json.loads(newest.read_text(encoding="utf-8"))
        except Exception:
            latest_manifest = {"error": f"could not parse {newest.name}"}

    log_tail = None
    if log_path:
        p = Path(log_path)
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                log_tail = text[-3000:]
            except Exception:
                log_tail = None

    if latest_manifest and latest_manifest.get("status") == "complete":
        state = "complete"
    elif running:
        state = "running"
    elif running is False:
        state = "finished_or_crashed"
    else:
        state = "unknown"

    # The render is finished and its file is known only here, so this is where
    # the automated still QA runs (cached per manifest; see _story_still_qa).
    qa = None
    if state == "complete" and newest is not None:
        qa = _story_still_qa_cached(newest, latest_manifest, safe_story, conversation_id)

    return json.dumps({
        "state": state,
        "pid_running": running,
        "owner_pid": owner_pid,
        "owner_released": owner_released,
        "story": safe_story,
        "manifest_found": bool(latest_manifest),
        "manifest": latest_manifest,
        "qa": qa,
        "log_tail": log_tail,
        "note": ("state=complete with a manifest means a real file was written. The "
                 "actual location is NOT outputs/stories/<story>/ itself — read "
                 "manifest['outputs'] (each item has filename/subfolder/type from "
                 "ComfyUI) and combine with the owned backend's private output root, "
                 "outputs/stories/_comfy_output/<subfolder>/<filename>. Do not guess a "
                 "different path. state=running means keep waiting and poll again. "
                 "state=finished_or_crashed with no manifest means it did not produce "
                 "an image — check log_tail for the reason and report that plainly "
                 "rather than guessing. When state=complete, qa is the real automated "
                 "still-QA record: state its verdict and reject_reasons plainly, respect "
                 "its scope, and never describe a QA result it does not contain."),
    }, indent=2, default=str)


def _storyboard_module():
    sys.path.insert(0, str(ROOT / "work"))
    import storyboard_from_story
    return storyboard_from_story


def prepare_storyboard_review(args: dict) -> str:
    """Persist a validated general storyboard plan in the pending-review state."""
    plan = args.get("plan")
    if not isinstance(plan, dict):
        raise ToolError("plan must be a structured JSON object with characters and shots")
    try:
        return json.dumps(_storyboard_module().initialise(str(args.get("story", "")), plan), indent=2)
    except Exception as exc:
        raise ToolError(str(exc)) from exc


def record_storyboard_reference_sheets(args: dict) -> str:
    """Record reviewed sheet names; frames remain locked until separate approval."""
    sheets = args.get("reference_sheets")
    if not isinstance(sheets, dict):
        raise ToolError("reference_sheets must map each character id to a sheet filename")
    try:
        return json.dumps(_storyboard_module().record_reference_sheets(
            str(args.get("story", "")), sheets), indent=2)
    except Exception as exc:
        raise ToolError(str(exc)) from exc


def approve_storyboard_references(args: dict) -> str:
    """Unlock only the non-GPU frame plan after an explicit desktop approval."""
    if args.get("operator_confirmed") is not True:
        raise ToolError("reference overview remains pending: explicit operator confirmation is required")
    try:
        return json.dumps(_storyboard_module().approve_reference_overview(
            str(args.get("story", "")), operator_confirmed=True), indent=2)
    except Exception as exc:
        raise ToolError(str(exc)) from exc


def storyboard_frame_plan(args: dict) -> str:
    """Read the gated frame plan. This does not generate a still or video."""
    try:
        return json.dumps(_storyboard_module().frame_plan(str(args.get("story", ""))), indent=2)
    except Exception as exc:
        raise ToolError(str(exc)) from exc


def _scene_reasoner_module():
    sys.path.insert(0, str(ROOT / "work"))
    import scene_reasoner
    return scene_reasoner


def plan_shot_reasoning(args: dict) -> str:
    """Resident-model reasoning step: decide model/LoRA + continuity, record, then unload.

    Reads the shot prompt plus this story's recorded shot-decision history and
    asks the resident chat model to decide which still model profile (and
    LoRA, if any) best completes this specific prompt, and, for a video shot,
    whether to chain the previous shot's actual last frame/video (same scene,
    no returning character) or use a fresh reference image (scene change, or
    a character last seen further back than the immediately preceding shot,
    to avoid character drift). The decision is recorded to
    outputs/stories/<story>/shot_decisions.jsonl, then the reasoning model is
    unloaded before any render may start. A low-confidence or ambiguous read
    never guesses: it returns status=blocked_awaiting_operator with a
    question instead, and nothing is recorded in that case. Never starts a
    render itself. {"story":"...","shot_id":"c001","prompt":"...","is_video_shot":false}
    """
    story = str(args.get("story", "")).strip()
    shot_id = str(args.get("shot_id", "")).strip()
    prompt_text = str(args.get("prompt", args.get("prompt_text", "")) or "")
    if not story or not shot_id or not prompt_text.strip():
        raise ToolError("story, shot_id, and prompt are required")
    is_video_shot = bool(args.get("is_video_shot"))
    model = str(args.get("model") or "").strip()
    try:
        module = _scene_reasoner_module()
        kwargs: dict = dict(story=story, shot_id=shot_id, prompt_text=prompt_text,
                            is_video_shot=is_video_shot)
        if model:
            kwargs["model"] = model
        return json.dumps(module.reason_about_shot(**kwargs), indent=2)
    except Exception as exc:
        raise ToolError(str(exc)) from exc


# ── story stills batch + review gate (2026-09-06 r93) ─────────────────────────

_STORY_STILLS_REVIEW_DIR = ROOT / "work" / "runtime" / "story_stills_review"
_VIDEO_TOOLS_NEEDING_STILL_APPROVAL = frozenset({
    "prepare_chat_render",
    "start_current_chat_render",
    # Fix 2026-09-23 (readiness-audit finding 1.1): the GVD video-producing
    # tools reached live ComfyUI submission with no coverage from this gate
    # at all. generate_still/upscale_still are intentionally excluded: they
    # produce the still itself, not a video, so "stills awaiting review"
    # does not apply to them.
    "execute_narrative_scene",
    "execute_continuous_take",
    "execute_montage_morph",
    "execute_fast_action",
})
_DEFAULT_BATCH_POLL_S = 5.0
_DEFAULT_BATCH_TIMEOUT_S = 900.0
# A foreign 8188 listener is re-checked a few times in case it is mid-shutdown.
_FOREIGN_BACKEND_GRACE_ATTEMPTS = 3


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


def _split_comfy_subpath(value: object) -> list[str]:
    """Split a ComfyUI-reported ``subfolder``/``filename`` into path segments.

    ComfyUI reports ``subfolder`` with the separator of the machine it runs on
    ("stories\\Leo\\renders" from a Windows ComfyUI) and image_render stores that
    string verbatim in every manifest. pathlib only splits on the *running*
    interpreter's separator, so joining the raw string under a POSIX pathlib
    (Linux, WSL, macOS) keeps the backslashes as filename characters, is_file()
    is False, and the still QA reports not_run for a file that exists exactly
    where the manifest says (2026-09-24ab). Split on both separators so the
    lookup matches the manifest on either platform.
    """
    return [seg for seg in re.split(r"[\\/]+", str(value or "").strip()) if seg and seg != "."]


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
        segments = _split_comfy_subpath(subfolder) + _split_comfy_subpath(filename)
        if not segments:
            continue
        path = comfy_root.joinpath(*segments)
        entry = {
            "filename": filename,
            "subfolder": subfolder,
            "type": item.get("type"),
            "path": str(path) if path.is_file() else None,
            "expected_path": str(path),
        }
        resolved.append(entry)
    return resolved


# ── automated still QA for chat-rendered stills (2026-09-24) ─────────────────
#
# render_story_image(_batch) used to hand stills to the operator with no
# automated check at all, so when asked "what did QA say?" the model had no
# data and invented a verdict ("the QA process confirmed... now marked as
# SELECTED"). Every completed still now runs through the repo's local,
# CPU-only creative_still_qa.creative_approve -- the same checker
# flux_still_batch.py uses -- and the real report rides along with the job
# result into the review payload. Advisory, not blocking: a failed still is
# still shown to the operator, labelled with its reasons; the human review
# gate (present_story_stills_for_review -> approve_story_stills) is unchanged.
#
# Continuity anchor: the last still the operator actually approved for the
# same story (recorded by approve_story_stills), never merely the last one
# generated. No approved still yet -> anchor=None, which compare_stills
# handles by skipping only the continuity comparisons. clip=None/kind="last":
# the chat path has no clip register, and compare_stills only reads clip for
# camera_mode/visibility_mode/require_room_continuity overrides (kind is
# accepted but unused by infer_visibility_expectation).
_STORY_STILL_QA_CHECKER = "creative_still_qa.creative_approve"
_STORY_STILL_QA_SCOPE = (
    "creative_still_qa checks only (1) whether people/faces are present when the "
    "prompt implies an actor should be visible, or absent when the prompt implies an "
    "empty frame, and (2) when an operator-approved earlier still exists for this "
    "story (or, failing that, the last still the operator approved in this chat), "
    "room/clothing/face continuity against that still; a deliberate change of "
    "location between stills lowers room continuity. It does NOT check that "
    "the scene, setting, objects, or lighting match the prompt text: an image of the "
    "wrong environment can pass.")


def _story_qa_key(story: str) -> str:
    """Normalise a story label the same way image_render names its directories."""
    try:
        sys.path.insert(0, str(ROOT / "work"))
        import image_render
        return image_render._safe_segment(str(story or ""), "story")
    except Exception:
        return str(story or "").strip()


def _story_qa_anchors_path() -> Path:
    return ROOT / "work" / "runtime" / "story_qa_anchors.json"


def _load_story_qa_anchors() -> dict:
    try:
        data = json.loads(_story_qa_anchors_path().read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


# Registry layout (work/runtime/story_qa_anchors.json):
#   {"<story slug>": {"path", "approved_at", "conversation_id"}, ...,
#    "_conversations": {"<chat id>": {"path", "story", "approved_at"}}}
# Story slugs come from image_render._safe_segment, which strips leading "_",
# so the chat section can never collide with a story key.
_STORY_QA_ANCHOR_CHAT_SECTION = "_conversations"


def _story_qa_anchor_lookup(story: str, conversation_id: str = "") -> dict:
    """Resolve the continuity anchor for a still: {path, source, story_key, approved_at}.

    Order: the operator-approved still recorded for the same story slug, else
    the last still the operator approved in the same chat (chat-driven stills
    are often labelled per image -- "Scene Start Image 1", then "... 2" -- so
    the slug alone cannot link two stills of one character). A missing or
    corrupt registry, or a recorded file that is gone, yields no anchor; this
    never raises, so the render path degrades to anchor=None.
    """
    found: dict = {"path": None, "source": None, "story_key": None, "approved_at": None}
    anchors = _load_story_qa_anchors()
    key = _story_qa_key(story)
    candidates = [("story", anchors.get(key), key)]
    cid = str(conversation_id or "").strip()
    chats = anchors.get(_STORY_QA_ANCHOR_CHAT_SECTION)
    if cid and isinstance(chats, dict):
        entry = chats.get(cid)
        chat_key = str(entry.get("story") or key) if isinstance(entry, dict) else key
        candidates.append(("conversation", entry, chat_key))
    for source, entry, entry_key in candidates:
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        try:
            path = Path(str(entry["path"]))
            if not path.is_file():
                continue
        except (OSError, ValueError):
            continue
        found.update({"path": path, "source": source, "story_key": entry_key,
                      "approved_at": entry.get("approved_at")})
        return found
    return found


def _story_qa_anchor(story: str, conversation_id: str = "") -> Path | None:
    return _story_qa_anchor_lookup(story, conversation_id)["path"]


def _record_story_qa_anchors(stills: list, *, default_story: str, conversation_id: str) -> dict:
    """After operator approval, make each story's last approved still its QA anchor."""
    latest: dict[str, str] = {}
    last_approved: tuple[str, str] | None = None
    for still in stills if isinstance(stills, list) else []:
        if not isinstance(still, dict):
            continue
        key = _story_qa_key(still.get("story") or default_story)
        for out in still.get("outputs") or []:
            if isinstance(out, dict) and out.get("path") and Path(str(out["path"])).is_file():
                latest[key] = str(out["path"])
                last_approved = (key, str(out["path"]))
    if not latest:
        return {}
    anchors = _load_story_qa_anchors()
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for key, path in latest.items():
        anchors[key] = {"path": path, "approved_at": stamp, "conversation_id": conversation_id}
    # Chat-scoped fallback anchor: the last still approved in this chat,
    # whatever story label it carried (see _story_qa_anchor_lookup).
    cid = str(conversation_id or "").strip()
    if cid and last_approved is not None:
        chats = anchors.get(_STORY_QA_ANCHOR_CHAT_SECTION)
        if not isinstance(chats, dict):
            chats = {}
        chats[cid] = {"path": last_approved[1], "story": last_approved[0], "approved_at": stamp}
        anchors[_STORY_QA_ANCHOR_CHAT_SECTION] = chats
    target = _story_qa_anchors_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(anchors, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return latest


def _jsonable(value: object) -> object:
    return value.item() if hasattr(value, "item") else str(value)


def _story_still_qa(outputs: list[dict], *, prompt: str, story: str,
                    conversation_id: str = "") -> dict:
    """Run creative_still_qa on a completed still; never reports a pass it didn't get."""
    found = _story_qa_anchor_lookup(story, conversation_id)
    anchor = found["path"]
    if anchor is None:
        anchor_note = ("no operator-approved still is recorded for this story or this chat "
                       "yet (first still), so the room/clothing/face continuity checks "
                       "were skipped; only the people/face-presence checks ran")
    elif found["source"] == "conversation":
        anchor_note = (f"no operator-approved still is recorded under story "
                       f"{_story_qa_key(story)!r}; continuity was checked against the last "
                       f"still the operator approved in this chat (story {found['story_key']!r})")
    else:
        anchor_note = ("continuity was checked against the last still the operator "
                       "approved for this story")
    record: dict = {
        "checker": _STORY_STILL_QA_CHECKER,
        "advisory": True,
        "scope": _STORY_STILL_QA_SCOPE,
        "anchor": str(anchor) if anchor else None,
        "anchor_source": found["source"],
        "anchor_story": found["story_key"] if anchor else None,
        "anchor_approved_at": found["approved_at"] if anchor else None,
        "anchor_note": anchor_note,
        "verdict": "not_run",
        "ok": None,
        "reject_reasons": [],
        "report": None,
    }
    listed = [o for o in outputs or [] if isinstance(o, dict)]
    paths = [Path(str(o["path"])) for o in listed if o.get("path")]
    if not str(prompt or "").strip():
        record["error"] = "the render manifest has no prompt to check the still against"
        return record
    if not paths:
        # not_run means QA never got a file to look at. Say where it looked, so
        # a missing or mis-resolved output path reads as the problem it is
        # instead of looking like a QA verdict (2026-09-24ab).
        looked = [str(o.get("expected_path") or o.get("filename") or "") for o in listed]
        looked = [p for p in looked if p]
        if not listed:
            record["error"] = "the render manifest lists no output file to check"
        elif looked:
            record["error"] = ("no rendered output file was found on disk to check "
                               f"(looked for: {'; '.join(looked)})")
        else:
            record["error"] = "no rendered output file was found on disk to check"
        return record
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import creative_still_qa
    except Exception as exc:
        record["verdict"] = "error"
        record["error"] = f"creative_still_qa could not load: {type(exc).__name__}: {exc}"
        return record
    per_output: list[dict] = []
    for path in paths:
        try:
            ok, reasons, report = creative_still_qa.creative_approve(
                path, prompt=prompt, anchor=anchor, clip=None, kind="last")
            report = json.loads(json.dumps(report, default=_jsonable))
            per_output.append({"path": str(path), "ok": bool(ok),
                               "reject_reasons": list(reasons), "report": report})
        except Exception as exc:
            per_output.append({"path": str(path), "ok": None,
                               "error": f"{type(exc).__name__}: {exc}"})
    errors = [p["error"] for p in per_output if p.get("error")]
    if errors:
        record["verdict"] = "error"
        record["error"] = "; ".join(errors)
    else:
        record["ok"] = all(p["ok"] for p in per_output)
        record["verdict"] = "pass" if record["ok"] else "fail"
    prefix = len(per_output) > 1
    record["reject_reasons"] = [
        (f"{Path(p['path']).name}: {r}" if prefix else r)
        for p in per_output for r in p.get("reject_reasons") or []
    ]
    if len(per_output) == 1:
        record["report"] = per_output[0].get("report")
    else:
        record["per_output"] = per_output
    return record


def _story_still_qa_cached(manifest_path: Path, manifest: dict | None, story: str,
                           conversation_id: str = "") -> dict:
    """QA a completed manifest once; status polls reuse the stored verdict.

    Stored outside manifests/ so image_render's image_*.json glob never sees
    it. Re-run if the continuity anchor has changed since it was stored.
    """
    manifest = manifest if isinstance(manifest, dict) else {}
    cache = ROOT / "outputs" / "stories" / story / "still_qa" / f"{Path(manifest_path).stem}.json"
    anchor = _story_qa_anchor(story, conversation_id)
    try:
        cached = json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        cached = None
    if isinstance(cached, dict) and cached.get("anchor") == (str(anchor) if anchor else None) \
            and cached.get("verdict") in {"pass", "fail"}:
        return cached
    record = _story_still_qa(_resolve_story_still_outputs(manifest),
                             prompt=str(manifest.get("prompt") or ""), story=story,
                             conversation_id=conversation_id)
    record["prompt_source"] = f"manifest {Path(manifest_path).name}"
    if record["verdict"] in {"pass", "fail"}:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        except OSError:
            pass
    return record


def _story_qa_summary(stills: list) -> dict:
    """Per-still verdict digest the chat reply must report verbatim."""
    items = []
    for i, still in enumerate(stills if isinstance(stills, list) else []):
        qa = still.get("qa") if isinstance(still, dict) else None
        if isinstance(qa, dict):
            items.append({"index": i, "verdict": qa.get("verdict"),
                          "reject_reasons": qa.get("reject_reasons") or [],
                          **({"error": qa["error"]} if qa.get("error") else {})})
        else:
            items.append({"index": i, "verdict": "not_run", "reject_reasons": [],
                          "error": "no automated QA record exists for this still"})
    counts: dict[str, int] = {}
    for item in items:
        counts[item["verdict"]] = counts.get(item["verdict"], 0) + 1
    return {"checker": _STORY_STILL_QA_CHECKER, "scope": _STORY_STILL_QA_SCOPE,
            "counts": counts, "stills": items,
            "all_passed": bool(items) and counts.get("pass", 0) == len(items)}


_STORY_QA_REPORTING_RULE = (
    "Automated still QA ran (creative_still_qa, advisory). In your reply, state each "
    "still's QA verdict exactly as recorded in qa_summary (pass / fail / error / "
    "not_run, with its reject_reasons) -- including failures. Do not add any QA claim "
    "the record does not contain, and do not say a still matches the described "
    "scene/environment on the strength of this QA: its scope excludes that. A QA pass "
    "is not operator approval and nothing is SELECTED until approve_story_stills.")


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
            "__conversation_id": str(args.get("__conversation_id")
                                     or args.get("conversation_id") or ""),
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

    Prefer this over N parallel `render_story_image` calls. Queue ALL unique
    start/end frames in one batch — there is no artificial product still-batch
    cap (full CLIP sheets may be dozens to ~250). Never tell the operator a
    batch was capped. One tool call finishes the queue without MAX_TOOL_HOPS
    exhaustion or "owns the backend" dead-ends. On full success it marks the
    chat's stills as pending operator review so video tools stay blocked until
    approval.
    """
    jobs_raw = args.get("jobs")
    if not isinstance(jobs_raw, list) or not jobs_raw:
        raise ToolError("jobs must be a non-empty list of still render requests")
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
        # The "…" and prompt_chars make the preview visibly partial: a bare
        # 120-char cut that lands on a period reads as a whole prompt, and the
        # model copied one back as a job prompt (live 2026-09-24).
        preview = job["prompt"][:120] + ("…" if len(job["prompt"]) > 120 else "")
        label = {"index": index, "story": job["story"], "prompt_preview": preview,
                 "prompt_chars": len(job["prompt"])}
        # Launch with a retry loop while a previous still job is draining. A
        # foreign backend only gets a short grace: it will not release 8188 on
        # its own, so burning minutes of retries there just hides who holds it.
        started = None
        launch_error = None
        blocked_by = None
        foreign_attempts = 0
        for attempt in range(60):
            try:
                payload = dict(job)
                # Internal identity must survive if call() injected it on the batch.
                if args.get("__remote_render_identity"):
                    payload["__remote_render_identity"] = args["__remote_render_identity"]
                started = json.loads(render_story_image(payload))
                launch_error = None
                blocked_by = None
                break
            except ToolError as exc:
                launch_error = str(exc)
                blocked_by = getattr(exc, "blocked_by", None)
                kind = (blocked_by or {}).get("kind")
                if kind == "foreign_backend":
                    foreign_attempts += 1
                    if foreign_attempts >= _FOREIGN_BACKEND_GRACE_ATTEMPTS:
                        break
                elif kind != "draining_image_job" and "owns the backend" not in launch_error:
                    break
                time.sleep(max(2.0, poll_s))
                continue
        if launch_error or not isinstance(started, dict) or not started.get("started"):
            entry = {**label, "error": launch_error or "render did not start", "phase": "launch"}
            if blocked_by:
                entry["blocked_by"] = blocked_by
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
            "__conversation_id": conversation_id,
        }))
        if awaited.get("state") == "complete" and not awaited.get("timed_out"):
            completed.append({
                **label,
                "pid": started.get("pid"),
                "log": started.get("log"),
                "manifest": awaited.get("manifest"),
                "outputs": awaited.get("outputs_resolved") or _resolve_story_still_outputs(awaited.get("manifest")),
                "qa": awaited.get("qa"),
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
                    "qa": c.get("qa"),
                }
                for c in completed
            ],
            "__conversation_id": conversation_id,
        }))

    foreign = next((f["blocked_by"] for f in failures
                    if (f.get("blocked_by") or {}).get("kind") == "foreign_backend"), None)
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
        "qa_summary": _story_qa_summary(completed) if completed else None,
        "next_step": (
            "Stills are ready for operator review. Present the output paths "
            "together with each still's automated QA verdict, ask the operator "
            "to approve (e.g. 'looks good' / 'approved' / 'go ahead with "
            "video'), and call approve_story_stills only after that explicit "
            "approval. Do NOT call prepare_chat_render, "
            "start_current_chat_render, or comfy_generate video until approved. "
            + _STORY_QA_REPORTING_RULE
            if completed and not failures else
            (f"Stills are blocked, not flaky: {foreign['summary']} Tell the operator "
             "exactly who holds port 8188 and what to do; do not call it a temporary "
             "backend issue, and do not stop that backend without their confirmation. "
             "Re-run this batch once port 8188 is free."
             if foreign else
             "Some stills failed or remain pending. Fix failures before video. "
             "Do not claim the sheet is ready for review until completed_count "
             "covers every unique frame.")
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
        "qa_summary": _story_qa_summary(stills),
        "note": (
            "Show these stills to the operator and wait. Continuation phrases "
            "like 'continue' or 'go on to the next step' do NOT approve video. "
            "Need explicit approval: 'looks good', 'approved', or 'go ahead with video'. "
            + _STORY_QA_REPORTING_RULE
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
    # Human-approved stills become the continuity anchor for this story's next
    # automated still QA. Best-effort: approval itself must not fail on this.
    try:
        qa_anchors = _record_story_qa_anchors(
            state.get("stills") or [], default_story=str(state.get("story") or ""),
            conversation_id=conversation_id)
    except Exception as exc:
        qa_anchors = {"error": f"{type(exc).__name__}: {exc}"}
    return json.dumps({
        "approved": True,
        "conversation_id": conversation_id,
        "story": state.get("story"),
        "still_count": len(state.get("stills") or []),
        "qa_anchors_recorded": qa_anchors,
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

# ── registry ──────────────────────────────────────────────────────────────────

# ── scheduled phone messages ──────────────────────────────────────────────────
#
# WHY THESE EXIST
# ---------------
# The bridge had no scheduler at all. Asked from a phone to "send a message every
# 30 seconds counting up", the model had no tool that could do it, so it narrated
# success and nothing was ever sent. It then reached for a gated execution tool,
# which is where the unrelated permission language came from.
#
# The fix is a real capability, not a relaxed permission. These three tools are
# **phone-only and source-bound**: the recipient is always the calling identity,
# injected by the trusted dispatch seam in call(). The model cannot choose,
# forge, or even name a target — there is no recipient parameter.

def _schedule_identity(args: dict) -> str:
    """The calling phone identity, injected by call(). Never model-supplied."""
    identity = str(args.get("__remote_schedule_identity") or "")
    if not identity:
        raise ToolError(
            "scheduled messages are phone-only. This tool sends to the paired "
            "phone that asked for it, so it cannot be used from the desktop chat.")
    return identity


def schedule_phone_messages(args: dict) -> str:
    """Queue a repeating message back to the calling phone."""
    identity = _schedule_identity(args)
    # For a counter-only request ("count from 0"), the useful and safe
    # default is the counter itself. Native tool calling models sometimes omit
    # this optional presentation field even when they correctly select the
    # interval, count, and start values. An explicitly blank message remains
    # invalid in phone_scheduler.create().
    message = args.get("message", "{n}")
    try:
        job = phone_scheduler.create(
            identity, message,
            args.get("interval_seconds"), args.get("count"),
            start=args.get("start", 0))
    except phone_scheduler.ScheduleError as e:
        raise ToolError(str(e)) from e
    return json.dumps({
        "scheduled": job,
        "note": ("Each message is queued to LXMF at its due time. Radio delivery "
                 "is not guaranteed by this workstation, and the bridge must stay "
                 "running for the schedule to continue."),
        "counter_hint": "Use {n} in the message to insert the counter.",
    }, indent=2)


def list_phone_schedules(args: dict) -> str:
    identity = _schedule_identity(args)
    return json.dumps(phone_scheduler.list_for_identity(identity), indent=2)


def cancel_phone_schedule(args: dict) -> str:
    identity = _schedule_identity(args)
    try:
        return json.dumps(phone_scheduler.cancel(identity, args.get("job_id")), indent=2)
    except phone_scheduler.ScheduleError as e:
        raise ToolError(str(e)) from e



# ── managed creative/storyboard prompt packs ──────────────────────────────────

def ingest_prompt_pack(args: dict) -> str:
    """Save a large prompt pack as a managed task artifact (no rendering)."""
    import managed_prompt_pack
    cid = str(args.get("__conversation_id") or args.get("conversation_id") or "").strip()
    if not cid:
        raise ToolError("conversation_id is required to persist a managed prompt pack")
    text = args.get("text")
    if text is None or str(text).strip() == "":
        text = None
    else:
        text = str(text)
    allow = args.get("allow_render")
    if allow is None and text:
        allow = managed_prompt_pack.wants_explicit_render(text)
    try:
        progress = managed_prompt_pack.ingest(
            cid, text, allow_render=bool(allow) if allow is not None else None,
            title=str(args.get("title") or "") or None,
        )
    except Exception as exc:
        raise ToolError(str(exc)) from exc
    count = progress.get("clip_count")
    profiles = progress.get("model_profiles") or {}
    profile_text = ", ".join(f"{k}={v}" for k, v in sorted(profiles.items())) or "unknown"
    if progress.get("allow_render"):
        ask = "Render was explicitly requested; production still needs the GPU gate."
    else:
        ask = "Say 'render it' to start stills+video production."
    return json.dumps({
        "ingested": True,
        "kind": "prompt_pack",
        "conversation_id": cid,
        "title": progress.get("title"),
        "clip_count": count,
        "model_profiles": profiles,
        "operator_message": (
            f"{count} clips parsed and saved (still model: {profile_text}). "
            f"Exporting per-clip files next; nothing is rendering yet. {ask}"
        ),
        "source_path": progress.get("source_path"),
        "clips_dir": progress.get("clips_dir"),
        "output_dir": progress.get("output_dir"),
        "progress_path": progress.get("progress_path"),
        "allow_render": progress.get("allow_render"),
        "status": progress.get("status"),
        "next_step": (
            "Call export_prompt_pack_outputs to write per-clip files. "
            "Do not call render_story_image* unless allow_render is true. "
            "Relay operator_message to the operator verbatim; never end the "
            "turn silently after an ingest."
        ),
    }, indent=2)


def export_prompt_pack_outputs(args: dict) -> str:
    """Write the next chunk (or all remaining) clip output files to disk."""
    import managed_prompt_pack
    cid = str(args.get("__conversation_id") or args.get("conversation_id") or "").strip()
    if not cid:
        raise ToolError("conversation_id is required")
    chunk_size = int(args.get("chunk_size") or 24)
    export_all = bool(args.get("export_all", True))
    try:
        if export_all:
            result = managed_prompt_pack.export_all(cid, chunk_size=chunk_size)
        else:
            result = managed_prompt_pack.export_chunk(cid, chunk_size=chunk_size)
    except Exception as exc:
        raise ToolError(str(exc)) from exc
    result = dict(result)
    if result.get("remaining", 0) <= 0:
        waiting = ("Render is unlocked; production still needs the GPU gate."
                   if result.get("allow_render")
                   else "Say 'render it' to start stills+video production.")
        result["operator_message"] = (
            f"{result.get('clip_count')} clips exported and ready in "
            f"{result.get('output_dir')}. {waiting}"
        )
    result["next_step"] = (
        "Outputs written. On continue/proceed, call export_prompt_pack_outputs again "
        "if remaining > 0. Do not invent placeholders. Do not render unless allow_render."
        if result.get("remaining", 0) > 0
        else "All clip outputs written. Relay operator_message to the operator "
             "verbatim, then wait for an explicit render ask."
    )
    return json.dumps(result, indent=2)


def prompt_pack_status(args: dict) -> str:
    """Read-only managed prompt-pack progress for this chat."""
    import managed_prompt_pack
    import prompt_pack_production
    cid = str(args.get("__conversation_id") or args.get("conversation_id") or "").strip()
    if not cid:
        raise ToolError("conversation_id is required")
    progress = managed_prompt_pack.load_progress(cid)
    if not progress:
        return json.dumps({"exists": False, "conversation_id": cid}, indent=2)
    snap = prompt_pack_production.status_snapshot(cid)
    prod = snap.get("production") or {}
    complete = prod.get("status") == "complete"
    return json.dumps({
        "exists": True,
        "conversation_id": cid,
        "title": progress.get("title"),
        "status": progress.get("status"),
        "mode": progress.get("mode"),
        "clip_count": progress.get("clip_count"),
        "exported_count": len(progress.get("exported_ids") or []),
        "remaining": max(0, int(progress.get("clip_count") or 0) - int(progress.get("next_index") or 0)),
        "production_complete": complete,
        "stage": prod.get("phase") or ("prompt_files_only" if not progress.get("allow_render") else "render_unlocked"),
        "production": prod,
        "next_index": progress.get("next_index"),
        "source_path": progress.get("source_path"),
        "output_dir": progress.get("output_dir"),
        "progress_path": progress.get("progress_path"),
        "allow_render": progress.get("allow_render"),
    }, indent=2)


def run_prompt_pack_production(args: dict) -> str:
    """Unlock allow_render and start durable stills-then-videos production."""
    import prompt_pack_production
    import gpu_gate
    cid = str(args.get("__conversation_id") or args.get("conversation_id") or "").strip()
    if not cid:
        raise ToolError("conversation_id is required")
    operator_text = str(args.get("operator_text") or "")
    # __remote_render_identity is injected by call() after a phone grant.
    # A caller-supplied value never reaches this function through dispatch.
    remote_identity = str(args.get("__remote_render_identity") or "")
    if remote_identity:
        if gpu_gate.snapshot().get("mode") == "block":
            raise ToolError("GPU gateway is set to Block; production was not started")
    else:
        gate = gpu_gate.request(
            "Prompt-pack stills+videos production",
            source="desktop tool",
            detail=f"cid={cid}",
            key=f"prompt_pack_production:{cid}",
        )
        if not gate.get("granted"):
            if gate.get("blocked"):
                raise ToolError("GPU gateway is set to Block; production was not started")
            raise ToolError(
                "GPU gateway needs operator approval in the desktop sidebar before "
                "stills+videos production can start"
            )
    try:
        result = prompt_pack_production.start_supervisor(cid, operator_text=operator_text)
    except Exception as exc:
        raise ToolError(str(exc)) from exc
    return json.dumps(result, indent=2, default=str)




TOOLS = {
    # ── project ──
    "search_docs": (search_docs, 'Hybrid lexical+embedding search over project docs (CHANGELOG, docs/, CLAUDE.md, UPGRADE notes). {"query":"why was pace corrected","max_results":5}. Returns source file and heading so claims can be cited. Fast chunk-list lookup; for a judged cited answer with retries, prefer agentic_search_docs.'),
    "agentic_search_docs": (agentic_search_docs, 'Preferred project-docs search when you need a grounded cited answer: hybrid lexical+embedding retrieval, model judges if the evidence actually answers the question, retries with rewritten queries (up to 3 rounds) if not. {"question":"...","max_rounds":2}. Read-only. Use search_docs instead for a fast chunk list without a model-graded answer.'),
    "project_state": (project_state, "Current counts: prompts, speakers, manifest, auditions, blockers. No arguments."),
    "clip_info": (clip_info, 'Everything about one clip. {"clip":"27E"}'),
    "read_prompt": (read_prompt, 'The generated prompt text for a clip. {"clip":"00A"}'),
    "validate_prompt": (validate_prompt, 'Check prompt text against the H3 format. {"text":"..."} or {"clip":"00A"}'),
    "validate_powerinfer_calibration": (validate_powerinfer_calibration, "Validate an operator-supplied PowerInfer calibration JSONL. Intake only: read-only CPU validation; never renders, loads a model, edits weights, generates predictors, benchmarks, serves, or changes the registry. Use only a real existing exact path returned by file/list/earlier tool evidence; never use ellipses, placeholders, documentation examples, or guessed paths. Use for a current PowerInfer/calibration JSON request, never batch_plan."),
    "repair_jsonl_format": (repair_jsonl_format, "Repair only JSONL container formatting for an existing project-local .jsonl file when the desktop operator explicitly asks to fix it after a JSON parsing error. Converts a top-level JSON array of objects into one object per line at the same exact path, without creating records, altering values, approving content, validating schema, or starting any model/GPU/render work. Revalidate the exact returned path afterward."),
    "duration_ladder": (duration_ladder, 'Frame-quantized retry rungs for a clip. {"clip":"00B"} or {"seconds":10}'),
    "read_doc": (read_doc, 'Read a project doc. {"name":"proven_facts"} — also golden_reference, prompt_rules, runbook, claude_md, agent_questions'),
    "list_changelog": (list_changelog, "List CHANGELOG entries. No arguments."),
    "run_build": (run_build, f'Regenerate derived files. {{"action":"..."}} one of {sorted(BUILD)}'),
    "propose_gpu": (propose_gpu, f'Propose a render for operator approval — never runs it. {{"action":"..."}} one of {sorted(GPU)}'),
    # ── memory ──
    "remember_fact": (remember_fact, 'Remember a durable operator fact. Only call when operator explicitly says "remember that…" or states a preference. {"fact":"...","category":"preferences|hardware|project|goal"}'),
    "schedule_phone_messages": (schedule_phone_messages, 'PERIODIC TEXT MESSAGES TO THIS PHONE — call this tool whenever the caller asks to "send me a message every N seconds/minutes", "message me every", "text me every", "keep messaging me", or "count up to me". This is NOT video rendering; it sends repeating text messages back to the caller\'s phone only — the recipient is always the caller and cannot be changed. {"message":"count {n}","interval_seconds":30,"count":40} optional start (first counter value, default 0). interval 10-3600s, count 1-120, within 24h.'),
    "list_phone_schedules": (list_phone_schedules, "List this phone's scheduled message jobs and their status. Phone-only. No arguments."),
    "cancel_phone_schedule": (cancel_phone_schedule, 'Cancel one of this phone\'s scheduled message jobs. Phone-only. {"job_id":"phone_schedule_..."} — use list_phone_schedules first.'),
    "list_memory": (list_memory, "List all remembered facts with their ids. No arguments."),
    "forget_fact": (forget_fact, 'Move a fact to the forgotten archive. {"id":N} — use list_memory first to find the id.'),
    # ── batch renderer ──
    "batch_plan": (batch_plan, "Scan an operator-supplied existing job folder, pair refs, validate prompts, and return a plan. Read-only; never renders. Never invent a folder path."),
    "batch_render": (batch_render, "Propose a batch-render command for an operator-supplied existing job folder. Optional limit, megapixels, duration, force. Never invent a folder path."),
    "start_batch_render": (start_batch_render, "Start the fixed guarded batch renderer for an operator-supplied existing, validated general job folder. It rejects an active render, a generator already listening on port 8188, invalid prompts, placeholders, and force. A phone request requires its exact paired-identity grant; all normal preflights still apply. Optional limit, megapixels, duration. Never invent a folder path."),
    "prepare_chat_render": (prepare_chat_render, "Create a new immutable batch job from the current chat's latest complete video prompt set plus its earlier attached character/setting images and source-video chunks. Does not start rendering. A phone request requires its exact paired-identity grant."),
    "start_current_chat_render": (start_current_chat_render, "GPU VIDEO RENDERING ONLY — use this tool ONLY when the operator explicitly says 'render it' or 'start render' for video generation in this chat. Never use this tool to send periodic text messages or any other messaging task. Prepare and start the current chat's latest complete video prompt set with its earlier attached assets. A phone request requires its exact paired-identity grant; all normal preflights still apply. Optional limit, megapixels, duration."),
    "stop_all_comfyui": (stop_all_comfyui, "Desktop-only emergency stop: if a generator or batch-render process is running, interrupt it, terminate only identified generator and batch-render processes, release a stale batch lock, and preserve all prompts, uploads, sources, and outputs. Never use from a phone."),
    "comfy_generate": (comfy_generate, 'Generate via comfyui-mcp generate_image against the shared ComfyUI instance. {"action":"image","prompt":"..."}. Other actions: controlnet, ip_adapter, video, 3d, upscale, remove_background, audio. filename_prefix is ignored for action image/controlnet/ip_adapter/upscale (MCP hardcodes SaveImage to ComfyUI). Returns {status:enqueued, prompt_id} — the file is not ready yet. Call comfy_job_status with that prompt_id before telling the operator a file exists. Never run at the same time as this project\'s own render dispatch.'),
    "comfy_job_status": (comfy_job_status, 'Read-only: poll ComfyUI /history for a comfy_generate prompt_id until the job completes, errors, or the bounded timeout (default 90s, cap 300s, backoff 0.5s→5s). {"prompt_id":"..."} optional timeout_s. Returns state=complete with outputs[] (filename/subfolder), state=pending if still running (call again), or state=error. Does not invent paths. Poll again rather than assuming failure.'),
    "comfy_workflow": (comfy_workflow, 'Workflow tools via comfyui-mcp. {"tool":"enqueue_workflow|queue|create_workflow|visualize_workflow|get_workflow|save_workflow"}. For enqueue: pass a local JSON file as workflow or workflow_path (the wrapper loads it); do not inline the graph. workflow may also be the parsed API-format object. Not a raw MCP passthrough.'),
    "comfy_assets": (comfy_assets, 'Asset tools via comfyui-mcp. {"tool":"get_image|upload_image", ...}. Default tool is get_image.'),
    "comfy_models": (comfy_models, 'Model search/download/list/remove via comfyui-mcp. {"tool":"download_model|list_local_models","action":"..."}. list_local_models action=remove deletes a file in the shared ComfyUI tree — logged to runtime/comfy_mcp_audit.jsonl.'),
    "comfy_nodes": (comfy_nodes, 'Custom-node search/install via comfyui-mcp. {"tool":"search_custom_nodes|install_custom_node|node_pack", ...}. Install is project-only and audit-logged. Never incidental.'),
    "comfy_system": (comfy_system, 'Read ComfyUI system stats/history or clear VRAM via comfyui-mcp. {"tool":"get_system_stats|clear_vram|get_history|comfy_cli"}. Default is get_system_stats (read-only).'),
    "comfy_process": (comfy_process, 'Start/stop/restart the shared ComfyUI process via comfyui-mcp restart_comfyui. {"action":"start|stop|restart"}. Refuses if thermal_guard is over ceiling or the stage supervisor / batch runner / image renderer currently owns the process. Project-only.'),
    # ── file & web ──
    "read_file": (read_file, 'Read any text file. {"path":"relative/or/absolute"} optional max_chars (default 12000)'),
    "inspect_workspace": (inspect_workspace, 'Read-only: inspect an operator-supplied project root and report detected type, evidence, and candidate authoritative docs. Never changes the active chat workspace or starts work. {"root":"absolute path"}'),
    "write_file": (write_file, 'Write or create a text file. {"path":"...","content":"..."} — protected files refused'),
    "propose_file_diff": (propose_file_diff, 'Preview a unified diff for a text-file change without writing it. {"path":"...","content":"..."} — protected files refused'),
    "inspect_binary": (inspect_binary, 'Inspect a binary file as bounded hexadecimal bytes and ASCII without changing it. {"path":"...","offset":0,"length":256} — length is at most 4096 bytes.'),
    "apply_hex_patch": (apply_hex_patch, 'Apply one exact fixed-length hexadecimal byte replacement to a non-protected binary file. First call inspect_binary, then provide {"path":"...","offset":N,"expected_hex":"...","replacement_hex":"..."}. The existing bytes must match and the operator must approve the exact patch in the sidebar before it writes. No insertions, deletions, or protected project evidence.'),
    "read_artifact": (read_artifact, 'Read back a bounded slice of a large tool result that was pruned from context (its result will have said "output pruned; artifact_id=..."). {"artifact_id":"artifact_...","offset":0,"length":4000} — length capped at 8000 chars; page through with next_offset from the previous call.'),
    "list_dir": (list_dir, 'List a directory. {"path":"."} (default: project root)'),
    "write_candidate_tool": (write_candidate_tool, 'Create a proposed Python helper in the isolated developer workspace. It cannot run or replace project code. To try it, copy it into the sandbox and call run_code. {"name":"helper_v1.py","content":"..."}'),
    "run_safe_check": (run_safe_check, f'Run a fixed non-rendering regression check. {{"action":"..."}} one of {sorted(_SAFE_CHECKS)}'),
    "run_code": (run_code, 'Execute code in an OS-confined sandbox (local_agent/sandbox/run_<id>/). Low integrity, one process, memory cap, network off. CPU only, timeout 30s (cap 120). Cannot see the project tree, outputs/, or uploads. A phone request requires its exact paired-identity grant. {"language":"python","code":"..."} or {"language":"python","path":"sandbox/run_x/main.py"} optional stdin, timeout.'),
    "fetch_url": (fetch_url, 'Fetch a URL and return its text content. {"url":"https://..."} optional max_chars'),
    "web_search": (web_search, 'Search the web (DuckDuckGo by default; EQUAL_SHARES_SEARCH_BACKEND selects the backend). {"query":"..."} optional max_chars'),
    "deep_research": (deep_research, 'Multi-source researched answer with citations. Token-heavy — best when the GPU is free; routes through the existing GPU/CPU router and never forces the GPU during a render. {"question":"...","max_rounds":2,"max_sources":6}. Caps: rounds 4, sources 12. Read-only.'),
    "dispatch_subtasks": (dispatch_subtasks, 'Answer up to 5 genuinely INDEPENDENT sub-questions concurrently instead of one at a time (e.g. "compare X, Y, and Z" where each is unrelated to the others). {"tasks":["question 1","question 2"]}. Workers are tool-free CPU calls, 500 chars per task, 60s timeout each — not for tasks that depend on each other, and not for anything needing a tool.'),
    "plan_story_image": (plan_story_image, "Prepare an inspectable still-image graph (optional). If the operator pastes a CLIP start/end still sheet and says Generate these photos using flux, do NOT dump many plan-only calls and claim ready — plan only when inspecting a graph, otherwise go straight to render_story_image_batch with model_profile=realpro_flux for ALL unique start/end frames in one batch (dedupe chained frames; dozens to ~250 OK — no artificial batch size limit; never say a batch was capped). There is NO tool named flux. Read-only: never starts ComfyUI or writes a file. Continuation after plans means RENDER stills, not more planning."),
    "render_story_image": (render_story_image, "ACTUALLY GENERATE one general still — launches a private guarded ComfyUI backend in the BACKGROUND (not done when this returns). Prefer render_story_image_batch when the operator wants multiple CLIP start/end frames. Flux => model_profile=realpro_flux. Default mode is t2i (a fresh still from scratch, no reference_name needed) — only pass mode=i2i together with a real, already-uploaded reference_name; never invent a filename that was not actually uploaded, that will just fail differently. After launch, await_story_image_job or story_image_job_status until complete. Only one render owns the backend at a time."),
    "render_story_image_batch": (render_story_image_batch, 'PREFERRED for CLIP still sheets: queue ALL unique start/end frames in one batch (no artificial still-batch size limit; never tell the operator a batch was capped). Sequentially render the list (start then await complete/fail then next) so one tool call finishes full CLIP sheets (dozens to ~250) without MAX_TOOL_HOPS exhaustion or owns-the-backend dead-ends. Pass jobs as a list of story/prompt objects (optional model_profile). Flux sheet => model_profile/default realpro_flux. On full success marks this chat pending stills review — present outputs and WAIT; do not start video until approve_story_stills after explicit operator approval.'),
    "await_story_image_job": (await_story_image_job, 'Poll story_image_job_status until complete, failed, or timeout (default 900s). Pass story/pid/log from render_story_image; optional poll_s/timeout_s. Use after a single render_story_image when not using the batch tool.'),
    "story_image_job_status": (story_image_job_status, 'Read-only: check whether a render_story_image job is still running and whether it produced a real file. Pass story/pid/log. Detects stale PIDs when the owner was released / process is dead. Poll again if state is running.'),
    "present_story_stills_for_review": (present_story_stills_for_review, 'Mark generated story stills as pending operator review for this chat. Call after stills exist (batch does this automatically). Video tools stay blocked until approve_story_stills. Bare continue is not approval.'),
    "approve_story_stills": (approve_story_stills, 'Unlock video for this chat after the operator explicitly approves the stills (looks good / approved / go ahead with video). Requires operator_confirmed=true. Do not call on bare continue.'),
    "story_stills_review_status": (story_stills_review_status, 'Read-only: pending_review / approved / none for this chat story stills review gate.'),
    "prepare_storyboard_review": (prepare_storyboard_review, "Desktop-only: validate and persist a general story character/shot plan in a pending reference-review state. Does not generate images or render video."),
    "record_storyboard_reference_sheets": (record_storyboard_reference_sheets, "Desktop-only: record reviewed character reference-sheet filenames for a pending storyboard. This does not approve or generate frames."),
    "approve_storyboard_references": (approve_storyboard_references, "Desktop-only: after the operator explicitly approves every recorded reference sheet, unlock only the read-only storyboard frame plan. Never generates frames."),
    "storyboard_frame_plan": (storyboard_frame_plan, "Read the general storyboard frame plan after reference approval. Never generates a still image or video."),
    "plan_shot_reasoning": (plan_shot_reasoning, 'Resident-model reasoning step: reads the shot prompt + this story\'s recorded shot history, decides still model_profile/LoRA and (for video) whether to chain the last frame or use a fresh reference image (this means a plain render_story_image / render_story_image_batch call with mode=t2i and NO reference_name -- it is NOT the i2i reference_name parameter, and no file should be invented if none was uploaded), records the decision, then unloads the model. status=blocked_awaiting_operator means it asked a question instead of guessing; nothing was recorded and it is not cleared to render. Call this BEFORE render_story_image / render_story_image_batch / execute_continuous_take for a shot whose model/LoRA/continuity was not explicitly stated. {"story":"...","shot_id":"c001","prompt":"...","is_video_shot":false}'),
    "ingest_prompt_pack": (ingest_prompt_pack, 'Save a large creative/storyboard prompt pack as a managed task artifact (full source.md + parsed clips + progress.json). No rendering. {"text":"..."} optional if source already saved; conversation id injected. Use for Backrooms-style multi-clip packs BEFORE any still render.'),
    "export_prompt_pack_outputs": (export_prompt_pack_outputs, 'Write real per-clip output files from the saved managed prompt pack into its output folder (chunked, resume-safe). {"chunk_size":24,"export_all":true}. No rendering. On continue/proceed, call again until remaining=0.'),
    "prompt_pack_status": (prompt_pack_status, 'Read-only status of this chat managed prompt-pack task (source path, output folder, export progress, allow_render, production phase). No arguments beyond conversation id.'),
    "run_prompt_pack_production": (run_prompt_pack_production, 'Unlock allow_render and start durable SDXL stills then Minimax FLF2V videos for the managed prompt pack. Use when the operator says complete images and videos / generate all stills then videos. Returns immediately; poll prompt_pack_status / continue. {"operator_text":"..."}'),
    # ── live music (Sonic Pi OSC; same protocol as abhishekjairath/sonic-pi-mcp) ──
    "ensure_sonic_pi": (sonic_pi.ensure_sonic_pi, "Start Sonic Pi if needed, install the OSC queue runner, and inject it so this agent can play music. Call this before the first music request if Sonic Pi might not be running. Optional {\"timeout\":90}."),
    "queue_sonic_pi": (sonic_pi.queue_segment, 'Play or change live music in Sonic Pi. Write a full Sonic Pi Ruby segment with named live_loops (optional use_bpm) and send it. Sonic Pi must be open with sonic-pi-queue.rb running. {"code":"use_bpm 120\\nlive_loop :drums do\\n  sample :bd_haus\\n  sleep 1\\nend"}'),
    "play_sonic_pi_note": (sonic_pi.play_note, 'Play one test MIDI note in Sonic Pi (sanity check, not a full track). {"note":60} optional synth, sustain, cutoff.'),
    "stop_sonic_pi": (sonic_pi.stop_all, "Hard-stop Sonic Pi jobs (same as the Stop button). Use when the operator asks to stop the music."),
    # ── sensory ──
    "capabilities": (capabilities, "Report which local image, video, audio, transcription and voice-analysis capabilities are installed. No arguments."),
    "see_image": (see_image, 'Analyze an image at native resolution with the installed local vision model. {"path":"...","question":"..."} optional crop [left,top,right,bottom].'),
    "video_frames": (video_frames, 'Extract native-resolution frames from a video. {"path":"...","at":[1.0,4.5]} or every_n_seconds.'),
    "analyze_video": (analyze_video, 'Build a timestamped visual-action timeline from a local video and measure its audio track. Default is one exact observation per second plus adjacent-frame motion comparisons. {"path":"...","question":"...","detail":"per_second|half_second|overview"}.'),
    "extract_video_actions": (extract_video_actions, 'Dense second-by-second action log from a video using the configured local Qwen2.5-VL caption model. Extracts frames at 1 FPS, analyzes all frames in one pass. {"video_path":"...","format_h3_beats":false,"focus_character":""}. Read-only; never modifies manifests or starts renders.'),
    "read_video_metadata": (read_video_metadata, 'Read media metadata and any embedded ComfyUI graph/prompt. {"path":"..."}.'),
    "media_job_status": (media_job_status, 'Read-only status or result of a queued media analysis job (analyze_video / see_image / extract_video_actions / transcribe returned {"queued": true}). {"job_id":"<id from that result>"} or {"path":"..."}. Returns pending|processing|done|failed|cancelled with progress, and the full analysis once done. Never loads a model.'),
    "audio_measure": (audio_measure, 'Measure duration, speech density, speech spans, leading burst and trim point in audio or video. {"path":"..."}.'),
    "transcribe": (transcribe, 'Transcribe local audio/video when a transcription model is installed. {"path":"...","expected_text":"..."}.'),
    "compare_voice": (compare_voice, 'Compare two speakers when a local speaker model is installed. {"a":"...","b":"..."}.'),
    # ── GVD tool router (M0–M2) ──
    "gvd_inventory": (gvd_inventory, "Read-only GVD bootstrap inventory: GPU telemetry, Comfy/Ollama endpoints, node-schema availability. Never downloads or starts ComfyUI."),
    "gvd_route_shot": (gvd_route_shot, 'Deterministic GVD router. {"manifest":{shot_id,continuity_mode,duration_s,width,height,motion_reference_video,requested_engine,...}}. Does not render. MiniMax is the default engine; set requested_engine:"wan" only when the operator names Wan. Returns selected implementation with engine/engine_selection/operator_notice (Wan chosen without being asked is flagged ENGINE_FALLBACK_WAN), or UNAVAILABLE_CAPABILITY with missing_capabilities and the blocked_candidates that could supply them.'),
    "plan_video_from_reference": (plan_video_from_reference, 'Planning only, never renders or downloads: given a reference video and a character still, report which reference-video motion-transfer approaches (Wan 2.2 Animate 14B, Wan 2.1 VACE 1.3B, AnimateDiff SDXL + pose ControlNet + IP-Adapter) this ComfyUI install can run now, exactly which weights or nodes each missing one needs with sizes, the frame plan for the whole clip, and the GVD route decision. {"reference_video":"...","character_image":"...","target_fps":16}'),
    "render_video_from_reference": (render_video_from_reference, 'ACTUALLY RENDER a reference-video motion transfer: the character still performs the reference clip\'s body motion (AnimateDiff-SDXL + pose ControlNet + IP-Adapter, FaceID face-detail). Starts a BACKGROUND job on a private ComfyUI backend and returns a job_id; nothing exists until video_reference_job_status says state=complete with verified_outputs=true. Desktop only; up to 64 frames per job (8 s at 8 fps; use start_seconds/max_seconds for a section). Requires likeness_attestation=true: the character is fictional or consented, and a real, identifiable person\'s likeness is never put into sexual content. Run plan_video_from_reference first if unsure what is installed. {"reference_video":"...","character_image":"...","prompt":"describe the character and scene","likeness_attestation":true}'),
    "video_reference_job_status": (video_reference_job_status, 'Read-only: state of a render_video_from_reference job (queued/analysing_inputs/starting_backend/rendering/complete/failed/finished_or_crashed), the final mp4 with sha256 and ffprobe, frame counts vs plan, and a machine identity score. Poll again while running. {"job_id":"mtr_..."}'),
    "execute_narrative_scene": (execute_narrative_scene, 'GVD narrative-scene tool. Plans the stage DAG; live=true submits only with GPU lease. Identity/wardrobe are acceptance criteria. {"manifest":{...},"live":false}'),
    "execute_continuous_take": (execute_continuous_take, 'GVD continuous-take tool. Requires start/context artifacts. live=false plans only. {"manifest":{...},"live":false}'),
    "execute_montage_morph": (execute_montage_morph, 'GVD montage/morph tool. Requires prompt_keyframes. live=false plans only. {"manifest":{...},"live":false}'),
    "execute_fast_action": (execute_fast_action, 'GVD fast-action / B-roll tool. live=false plans only. {"manifest":{...},"live":false}'),
    "generate_still": (generate_still, 'GVD still generation. Plans/submits only an active still implementation. {"manifest":{...},"live":false}'),
    "upscale_still": (upscale_still, "GVD still upscale. TiledDiffusion is not installed; stays UNAVAILABLE until a local profile exists."),
    "discover_workflows": (discover_workflows_tool, 'Discover Comfy API JSON candidates into quarantine. HTTPS + public DNS only; never installs. {"capability":"fast_action"}'),
    "gvd_plan_shot": (gvd_plan_shot, 'Turn narrative text into a typed GVD shot manifest and route it. Does not invent node classes. {"text":"..."}'),
    "gvd_family_status": (gvd_family_status, "Report which GVD families have custom nodes installed and why they remain blocked without local VRAM profiles."),
    "synthesize_dialogue": (synthesize_dialogue_tool, "GVD dialogue tool. F5-TTS is adapter_required; fails closed until a pinned local service exists."),
    "apply_lipsync": (apply_lipsync_tool, "GVD lip-sync tool. MuseTalk is not installed; other voice nodes are not substitutes."),
    "repair_video": (repair_video_tool, "GVD localized repair. Preserves source bytes. ProPainter stays blocked without a local VRAM profile."),
    "assemble_scene": (assemble_scene_tool, 'Assemble accepted shots in narrative order into an EDL. {"project":"...","shots":[{"shot_id":"S01","edit_index":0,"actual_frames":24}]}'),
    "gvd_quality_gate": (gvd_quality_gate, 'Mechanical duration/protected-region gate. {"requested_duration_s":4,"actual_duration_s":4,"tolerance_s":0.25}'),
    "gvd_qa_evaluate": (gvd_qa_evaluate, 'Score a still/video against prompt via WD14/CLIP/Qwen-VL/Caption V4. Does not render. {"prompt":"...","history":{},"expected_tags":["yellow wallpaper"],"artifact_path":"..."}'),
    "gvd_qa_attach_wd14": (gvd_qa_attach_wd14, 'Copy an API graph and attach WD14Tagger|pysssss to an IMAGE node without replacing SaveImage. {"graph":{...},"image_node_id":"8"}'),
    "gvd_qa_loop": (gvd_qa_loop_tool, 'Bounded seed reroll over injected render records. GPU render is not implied. {"prompt":"...","seed":1,"renders":[{"seed":1,"history":{}}]}'),
    "gvd_qa_accepted_still": (gvd_qa_accepted_still, 'Verify accepted.json and return the hash-locked still for I2V. {"receipt":".../accepted.json","policy_id":"...","requirements_json":"..."}'),
    "gvd_qa_activation": (gvd_qa_activation, 'Fail-closed /object_info report for QA graphs and GVD adapters. {"object_info":{}} or path string.'),
}

# These tools expose facts and build actions belonging specifically to the
# Equal Shares reference project. They remain fully available in an explicitly
# scoped project chat, but are intentionally absent from the schema sent to an
# ordinary chat. Hiding irrelevant specialist actions is not a security control
# (tools.call() still validates every request); it reduces false tool selection
# by small local models and keeps new projects from inheriting this project's
# assumptions.
PROJECT_ONLY_TOOLS = frozenset({
    "search_docs", "agentic_search_docs", "project_state", "clip_info", "read_prompt",
    "validate_prompt", "duration_ladder", "read_doc", "list_changelog",
    "run_build", "propose_gpu",
    "comfy_process", "comfy_nodes",
})

# A model turn may request several tools at once (agent.py's hop loop).
# These may run concurrently in background threads because each one is a
# pure read: no shared mutable state, no write, no lock/queue/schedule, and
# no GPU-model load. Deliberately excluded: everything that writes a file,
# starts/stops a render, touches Sonic Pi, schedules or cancels a phone job,
# remembers/forgets a fact, or loads a vision/whisper/speaker model onto the
# GPU (see_image, video_frames, analyze_video, extract_video_actions,
# transcribe, compare_voice) — those either mutate shared state or could
# race on GPU residency if two ran at once, so they stay strictly
# sequential. When adding a new tool, default to leaving it OUT of this set;
# only add it after confirming it neither writes anything nor touches a
# GPU-resident model.
CONCURRENCY_SAFE_TOOLS = frozenset({
    "search_docs", "project_state", "clip_info", "read_prompt",
    "validate_prompt", "validate_powerinfer_calibration", "duration_ladder", "read_doc", "list_changelog",
    "read_file", "inspect_workspace", "inspect_binary", "list_dir",
    "fetch_url", "web_search",
    "list_memory", "list_phone_schedules", "read_artifact", "prompt_pack_status",
    "capabilities", "audio_measure", "read_video_metadata",
    "story_image_job_status",
    "story_stills_review_status",
    "comfy_job_status",
    "media_job_status",
    # Virtual compact-profile catalog tools. call_tool is NOT in this set;
    # after unwrap, the inner name's membership decides parallelism.
    "list_tools", "describe_tool",
    "gvd_inventory", "gvd_route_shot", "discover_workflows",
    "gvd_family_status", "gvd_plan_shot", "gvd_quality_gate",
    "plan_video_from_reference",
    "video_reference_job_status",
})

# Virtual compact-profile tools. Not members of TOOLS; schemas(profile="gpu")
# (the default) never advertises them. See docs/HARNESS_PROFILES_DESIGN_2026-09-04.md.
META_TOOL_NAMES = ("list_tools", "describe_tool", "call_tool")

# Farm-down / skip_farm tool-classified GPU fallback (profile gpu_core),
# plus the compact v1.1 allowlist from harness-profile design §9.
CORE_DIRECT_TOOLS = (
    "list_dir", "read_file", "web_search", "fetch_url", "capabilities", "run_code",
)

# Non-project Comfy tools added to gpu_core only when the prompt is a
# Comfy/workflow turn (2026-09-05bc). comfy_nodes/comfy_process stay
# PROJECT_ONLY and are never in this subset.
COMFY_CORE_TOOLS = (
    "comfy_generate", "comfy_job_status", "comfy_workflow",
    "comfy_assets", "comfy_models", "comfy_system",
)

# capability=image GPU/CPU hops (2026-09-06): advertise only the story-image
# path so the ~68-tool catalog cannot drown native tool_calls. Live probes
# showed 1-tool plan_story_image works; full catalog yields empty content.
IMAGE_DIRECT_TOOLS = (
    "plan_story_image",
    "render_story_image",
    "render_story_image_batch",
    "await_story_image_job",
    "story_image_job_status",
    "present_story_stills_for_review",
    "approve_story_stills",
    "story_stills_review_status",
)

_COMFY_WORKFLOW_TURN_RE = re.compile(
    r"(?i)\b(?:comfyui|comfy_workflow|comfy_generate|comfy_system|"
    r"enqueue_workflow|workflow_path)\b",
)

_TOOL_CATEGORY: dict[str, str] = {
    "search_docs": "project", "agentic_search_docs": "project",
    "project_state": "project", "clip_info": "project", "read_prompt": "project",
    "validate_prompt": "project", "validate_powerinfer_calibration": "project",
    "repair_jsonl_format": "project", "duration_ladder": "project",
    "read_doc": "project", "list_changelog": "project", "run_build": "project",
    "propose_gpu": "project",
    "gvd_inventory": "gvd", "gvd_route_shot": "gvd",
    "execute_narrative_scene": "gvd", "execute_continuous_take": "gvd",
    "execute_montage_morph": "gvd", "execute_fast_action": "gvd",
    "discover_workflows": "gvd", "gvd_plan_shot": "gvd", "gvd_family_status": "gvd",
    "synthesize_dialogue": "gvd", "apply_lipsync": "gvd", "repair_video": "gvd",
    "plan_video_from_reference": "gvd",
    "render_video_from_reference": "gvd",
    "video_reference_job_status": "gvd",
    "assemble_scene": "gvd", "gvd_quality_gate": "gvd",
    "gvd_qa_evaluate": "gvd", "gvd_qa_attach_wd14": "gvd", "gvd_qa_loop": "gvd",
    "gvd_qa_accepted_still": "gvd", "gvd_qa_activation": "gvd",
    "generate_still": "gvd", "upscale_still": "gvd",
    "remember_fact": "memory", "schedule_phone_messages": "memory",
    "list_phone_schedules": "memory", "cancel_phone_schedule": "memory",
    "list_memory": "memory", "forget_fact": "memory",
    "batch_plan": "batch", "batch_render": "batch", "start_batch_render": "batch",
    "prepare_chat_render": "batch", "start_current_chat_render": "batch",
    "stop_all_comfyui": "batch",
    "comfy_generate": "comfy", "comfy_job_status": "comfy",
    "comfy_workflow": "comfy", "comfy_assets": "comfy",
    "comfy_models": "comfy", "comfy_nodes": "comfy", "comfy_system": "comfy",
    "comfy_process": "comfy",
    "read_file": "file", "inspect_workspace": "file", "write_file": "file",
    "propose_file_diff": "file", "inspect_binary": "file", "apply_hex_patch": "file",
    "read_artifact": "file", "list_dir": "file", "write_candidate_tool": "file",
    "run_safe_check": "file", "run_code": "file",
    "fetch_url": "web", "web_search": "web", "deep_research": "web",
    "dispatch_subtasks": "web",
    "plan_story_image": "story_image", "render_story_image": "story_image",
    "render_story_image_batch": "story_image", "await_story_image_job": "story_image",
    "story_image_job_status": "story_image",
    "present_story_stills_for_review": "story_image",
    "approve_story_stills": "story_image",
    "story_stills_review_status": "story_image",
    "prepare_storyboard_review": "storyboard",
    "record_storyboard_reference_sheets": "storyboard",
    "approve_storyboard_references": "storyboard",
    "storyboard_frame_plan": "storyboard",
    "plan_shot_reasoning": "storyboard",
    "ensure_sonic_pi": "sonic_pi", "queue_sonic_pi": "sonic_pi",
    "play_sonic_pi_note": "sonic_pi", "stop_sonic_pi": "sonic_pi",
    "capabilities": "sensory", "see_image": "sensory", "video_frames": "sensory",
    "analyze_video": "sensory", "extract_video_actions": "sensory",
    "read_video_metadata": "sensory", "audio_measure": "sensory",
    "media_job_status": "sensory",
    "transcribe": "sensory", "compare_voice": "sensory",
}

_META_SCHEMAS: dict[str, dict] = {
    "list_tools": {
        "type": "object",
        "properties": {
            "category": {"type": "string",
                         "description": "Optional group filter"},
            "search": {"type": "string",
                       "description": "Optional substring over name+summary"},
        },
    },
    "describe_tool": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "names": {"type": "array", "items": {"type": "string"}},
        },
    },
    "call_tool": {
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {"type": "string"},
            "tool_name": {"type": "string"},
            "args": {"description": "object or JSON string"},
            "arguments": {"description": "alias of args"},
        },
    },
}

_META_DESCRIPTIONS = {
    "list_tools": (
        "Token-light catalog of available tools: name + one-line summary, "
        "grouped by category. Optional category or search filters. Then "
        "describe_tool for parameters and call_tool to run one."
    ),
    "describe_tool": (
        "Full description and JSON Schema for one tool (or up to 3 via names). "
        "Call this before the first call_tool of a name you have not used this turn."
    ),
    "call_tool": (
        "Run a cataloged tool by name. Pass its parameters in args (object or "
        "JSON string). Aliases: tool_name, arguments. Result is exactly what "
        "the underlying tool returns."
    ),
}

# ── JSON schemas for Ollama's native function-calling API ─────────────────────

_SCHEMAS: dict[str, dict] = {
    "search_docs": {
        "type": "object",
        "properties": {
            "query": {"type": "string",
                      "description": "Search terms — any English phrase, rule name, or measurement"},
            "max_results": {"type": "integer",
                            "description": "Number of chunks to return (default 5, max 10)"},
        },
        "required": ["query"],
    },
    "agentic_search_docs": {
        "type": "object",
        "properties": {
            "question": {"type": "string",
                         "description": "The question to answer from local project documents"},
            "max_rounds": {"type": "integer",
                           "minimum": 1,
                           "maximum": 3,
                           "description": "Retrieve/grade/retry rounds (default 2, cap 3)"},
        },
        "required": ["question"],
    },
    "project_state": {
        "type": "object",
        "properties": {},
    },
    "clip_info": {
        "type": "object",
        "properties": {
            "clip": {"type": "string", "description": "Clip id, e.g. 00A, 27E, 00D2"},
        },
        "required": ["clip"],
    },
    "read_prompt": {
        "type": "object",
        "properties": {
            "clip": {"type": "string", "description": "Clip id, e.g. 00A"},
        },
        "required": ["clip"],
    },
    "validate_prompt": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Prompt text to validate directly"},
            "clip": {"type": "string", "description": "Clip id — validates its generated prompt file"},
            "expect_audio": {"type": "integer",
                             "description": "Expected number of <Audio N> references"},
        },
    },
    "validate_powerinfer_calibration": {
        "type": "object",
        "properties": {
            "path": {"type": "string",
                     "description": "Existing operator-approved calibration .jsonl inside the project workspace"},
        },
        "required": ["path"],
    },
    "repair_jsonl_format": {
        "type": "object",
        "properties": {
            "path": {"type": "string",
                     "description": "Existing project-local .jsonl path returned by prior tool evidence"},
        },
        "required": ["path"],
    },
    "duration_ladder": {
        "type": "object",
        "properties": {
            "clip": {"type": "string",
                     "description": "Clip id — looks up duration from project data"},
            "seconds": {"type": "number",
                        "description": "Duration in seconds (use when no clip id)"},
        },
    },
    "read_doc": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "enum": ["proven_facts", "golden_reference", "prompt_rules",
                         "runbook", "claude_md", "agent_questions"],
                "description": "Document to read",
            },
            "max_chars": {"type": "integer",
                          "description": "Maximum characters to return (default 6000)"},
        },
        "required": ["name"],
    },
    "list_changelog": {
        "type": "object",
        "properties": {},
    },
    "run_build": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": sorted(BUILD),
                "description": "Build action to run",
            },
        },
        "required": ["action"],
    },
    "propose_gpu": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": sorted(GPU),
                "description": "GPU render to propose for operator approval",
            },
        },
        "required": ["action"],
    },
    "remember_fact": {
        "type": "object",
        "properties": {
            "fact": {"type": "string", "description": "The fact to remember"},
            "category": {
                "type": "string",
                "enum": ["preferences", "hardware", "project", "goal", "general"],
                "description": "Category for grouping in the system prompt",
            },
        },
        "required": ["fact"],
    },
    "schedule_phone_messages": {
        "type": "object",
        "properties": {
            "message": {"type": "string",
                        "description": "Optional message text, 1-500 chars. Defaults to {n} for a counter-only request; {n} is replaced by the counter."},
            "interval_seconds": {"type": "integer",
                                 "description": "Seconds between messages, 10 to 3600"},
            "count": {"type": "integer", "description": "How many messages, 1 to 120"},
            "start": {"type": "integer", "description": "First counter value (default 0)"},
        },
        "required": ["interval_seconds", "count"],
    },
    "list_phone_schedules": {"type": "object", "properties": {}},
    "cancel_phone_schedule": {
        "type": "object",
        "properties": {"job_id": {"type": "string", "description": "Job id from list_phone_schedules"}},
        "required": ["job_id"],
    },
    "list_memory": {
        "type": "object",
        "properties": {},
    },
    "forget_fact": {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "description": "Fact id to forget — use list_memory to find it"},
        },
        "required": ["id"],
    },
    "batch_plan": {
        "type": "object",
        "properties": {
            "folder": {"type": "string",
                       "description": "Absolute path to the job folder (contains prompts/, img0/, etc.)"},
        },
        "required": ["folder"],
    },
    "batch_render": {
        "type": "object",
        "properties": {
            "folder":     {"type": "string",  "description": "Absolute path to the job folder"},
            "limit":      {"type": "integer", "description": "Stop after N renders (operator preview)"},
            "megapixels": {"type": "number",  "description": "Starting megapixels (default 0.9)"},
            "duration":   {"type": "number",  "description": "Default duration in seconds (default 8.0)"},
            "force":      {"type": "boolean", "description": "Re-render even if output exists"},
        },
        "required": ["folder"],
    },
    "start_batch_render": {
        "type": "object",
        "properties": {
            "folder":     {"type": "string", "description": "Actual existing general job folder; never a documentation example"},
            "limit":      {"type": "integer", "description": "Optional positive maximum number of renders"},
            "megapixels": {"type": "number", "description": "Optional starting megapixels, 0.4 through 2.0"},
            "duration":   {"type": "number", "description": "Optional default duration in seconds, 1 through 60"},
        },
        "required": ["folder"],
    },
    "prepare_chat_render": {
        "type": "object",
        "properties": {},
    },
    "start_current_chat_render": {
        "type": "object",
        "properties": {
            "limit":      {"type": "integer", "description": "Optional positive maximum number of renders"},
            "megapixels": {"type": "number", "description": "Optional starting megapixels, 0.4 through 2.0"},
            "duration":   {"type": "number", "description": "Optional default duration in seconds, 1 through 60"},
        },
    },
    "stop_all_comfyui": {
        "type": "object",
        "properties": {},
    },
    "read_file": {
        "type": "object",
        "properties": {
            "path": {"type": "string",
                     "description": "Absolute path or path relative to project root"},
            "max_chars": {"type": "integer",
                          "description": "Maximum characters to return (default 12000)"},
        },
        "required": ["path"],
    },
    "inspect_workspace": {
        "type": "object",
        "properties": {"root": {"type": "string", "description": "Existing absolute project-root directory"}},
        "required": ["root"],
    },
    "write_file": {
        "type": "object",
        "properties": {
            "path": {"type": "string",
                     "description": "Absolute path or path relative to project root"},
            "content": {"type": "string", "description": "Text content to write"},
        },
        "required": ["path", "content"],
    },
    "propose_file_diff": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path or path relative to project root"},
            "content": {"type": "string", "description": "Proposed complete text content"},
        },
        "required": ["path", "content"],
    },
    "inspect_binary": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Existing binary file path"},
            "offset": {"type": "integer", "description": "Byte offset, default 0"},
            "length": {"type": "integer", "description": "Bytes to inspect, 1 through 4096; default 256"},
        },
        "required": ["path"],
    },
    "apply_hex_patch": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Existing non-protected binary file path"},
            "offset": {"type": "integer", "description": "Non-negative byte offset"},
            "expected_hex": {"type": "string", "description": "Current bytes at offset, hexadecimal"},
            "replacement_hex": {"type": "string", "description": "Same-length replacement bytes, hexadecimal"},
        },
        "required": ["path", "offset", "expected_hex", "replacement_hex"],
    },
    "read_artifact": {
        "type": "object",
        "properties": {
            "artifact_id": {"type": "string", "description": "artifact_<16 hex chars>, from a prior pruned tool result"},
            "offset": {"type": "integer", "description": "Character offset, default 0"},
            "length": {"type": "integer", "description": "Characters to read, 1 through 8000; default 4000"},
        },
        "required": ["artifact_id"],
    },
    "list_dir": {
        "type": "object",
        "properties": {
            "path": {"type": "string",
                     "description": "Directory path (default: project root)"},
        },
    },
    "write_candidate_tool": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Simple versioned Python filename, e.g. helper_v1.py"},
            "content": {"type": "string", "description": "Candidate Python source code"},
        },
        "required": ["name", "content"],
    },
    "run_safe_check": {
        "type": "object",
        "properties": {"action": {"type": "string", "enum": sorted(_SAFE_CHECKS),
                                    "description": "Approved non-rendering check"}},
        "required": ["action"],
    },
    "run_code": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["python", "javascript", "js", "node"],
                "description": "Interpreter allowlist; default python",
            },
            "code": {
                "type": "string",
                "description": "Source written into a new sandbox run dir and executed",
            },
            "path": {
                "type": "string",
                "description": "Existing file inside local_agent/sandbox/run_<id>/",
            },
            "stdin": {"type": "string", "description": "Optional stdin for the process"},
            "timeout": {
                "type": "integer",
                "description": "Seconds (default 30, cap 120)",
            },
            "allow_network": {
                "type": "boolean",
                "description": "Off by default; Windows isolation is best-effort",
            },
        },
    },
    "fetch_url": {
        "type": "object",
        "properties": {
            "url": {"type": "string",
                    "description": "URL to fetch — must start with http:// or https://"},
            "max_chars": {"type": "integer",
                          "description": "Maximum characters to return (default 8000)"},
        },
        "required": ["url"],
    },
    "web_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_chars": {"type": "integer",
                          "description": "Maximum characters to return (default 6000)"},
        },
        "required": ["query"],
    },
    "deep_research": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The research question to answer from multiple web sources",
            },
            "max_rounds": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4,
                "description": "Plan/gather/synthesize rounds (default 2, cap 4)",
            },
            "max_sources": {
                "type": "integer",
                "minimum": 1,
                "maximum": 12,
                "description": "Unique pages to fetch (default 6, cap 12)",
            },
        },
        "required": ["question"],
    },
    "dispatch_subtasks": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 5,
                "description": "2-5 short, mutually independent questions to answer concurrently, 500 chars each",
            },
        },
        "required": ["tasks"],
    },
    "ingest_prompt_pack": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Full prompt-pack markdown. Omit to reuse saved source.md"},
            "title": {"type": "string"},
            "allow_render": {"type": "boolean", "description": "Only true when operator explicitly asked to render"},
        },
    },
    "export_prompt_pack_outputs": {
        "type": "object",
        "properties": {
            "chunk_size": {"type": "integer", "description": "Clips per durable progress chunk (default 24)"},
            "export_all": {"type": "boolean", "description": "Default true: keep writing chunks until done"},
        },
    },
    "run_prompt_pack_production": {
        "type": "object",
        "properties": {
            "operator_text": {"type": "string", "description": "Operator utterance that requested full production"},
            "conversation_id": {"type": "string"}
        },
    },
    "prompt_pack_status": {
        "type": "object",
        "properties": {},
    },
    "plan_story_image": {
        "type": "object",
        "properties": {
            "story": {"type": "string", "description": "Short story or storyboard slug for outputs/stories/. Reuse the SAME slug for every still of one story/character (e.g. 'leo-audition' for shots 1, 2, 3), never one slug per image: automated still QA checks continuity against the last operator-approved still recorded under that slug."},
            "prompt": {"type": "string", "description": "Complete still-image prompt"},
            "model_profile": {"type": "string", "enum": ["realvisxl", "realpro_flux", "alicemix_sd15"], "description": "Default realvisxl. If the operator asks for Flux / using flux / with flux, use realpro_flux (Flux UNet + clip_l/t5xxl/ae). There is no tool named flux. alicemix_sd15 is a separate complete SD 1.5 checkpoint, not a LoRA."},
            "mode": {"type": "string", "enum": ["t2i", "i2i"], "description": "t2i for text-to-image; i2i for reference image-to-image"},
            "reference_name": {"type": "string", "description": "Simple uploaded image filename required for i2i"},
            "seed": {"type": "integer", "minimum": 1, "description": "Deterministic positive seed"},
            "width": {"type": "integer", "minimum": 256, "description": "Output width, multiple of 8 (default 1024)"},
            "height": {"type": "integer", "minimum": 256, "description": "Output height, multiple of 8 (default 1024)"},
            "steps": {"type": "integer", "minimum": 1, "maximum": 60, "description": "Sampling steps (default 35)"},
            "cfg": {"type": "number", "minimum": 1.0, "maximum": 20.0, "description": "Guidance scale (default 6)"},
            "denoise": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "i2i only, default 0.55 — a t2i request always forces 1.0 regardless of this value, since starting from an empty latent at partial denoise produces a hazy/washed-out image"},
            "negative": {"type": "string", "description": "Optional negative prompt"},
            "hires_fix": {"type": "boolean", "description": "t2i only, default true. A second-pass latent upscale + refine that fixes small/distant faces (e.g. crossed eyes) at the cost of some extra render time. Set false only for a quick low-detail draft."},
            "face_detail": {"type": "boolean", "description": "Default false. Opt in to an automatic detected-face repair pass for crooked eyes, facial artifacts, or small damaged faces. NOT available with model_profile=realpro_flux (Flux) -- that combination always fails after the backend has already started. Use realvisxl if face_detail is needed."},
        },
        "required": ["story", "prompt"],
    },
    "render_story_image": {
        "type": "object",
        "properties": {
            "lora_name": {"type": "string", "description": "Optional installed SDXL LoRA filename, realvisxl only; never a wildcard or absolute path."},
            "lora_strength": {"type": "number", "minimum": 0, "maximum": 1, "description": "Optional SDXL LoRA strength, default 0.5."},
            "story": {"type": "string", "description": "Short story or storyboard slug for outputs/stories/. Reuse the SAME slug for every still of one story/character (e.g. 'leo-audition' for shots 1, 2, 3), never one slug per image: automated still QA checks continuity against the last operator-approved still recorded under that slug."},
            "prompt": {"type": "string", "description": "Complete still-image prompt"},
            "model_profile": {"type": "string", "enum": ["realvisxl", "realpro_flux", "alicemix_sd15"], "description": "Default realvisxl. If the operator asks for Flux / using flux / with flux, use realpro_flux (Flux UNet + clip_l/t5xxl/ae). There is no tool named flux. alicemix_sd15 is a separate complete SD 1.5 checkpoint, not a LoRA."},
            "mode": {"type": "string", "enum": ["t2i", "i2i"], "description": "t2i for text-to-image; i2i for reference image-to-image"},
            "reference_name": {"type": "string", "description": "Simple uploaded image filename required for i2i"},
            "seed": {"type": "integer", "minimum": 1, "description": "Deterministic positive seed"},
            "width": {"type": "integer", "minimum": 256, "description": "Output width, multiple of 8 (default 1024)"},
            "height": {"type": "integer", "minimum": 256, "description": "Output height, multiple of 8 (default 1024)"},
            "steps": {"type": "integer", "minimum": 1, "maximum": 60, "description": "Sampling steps (default 35)"},
            "cfg": {"type": "number", "minimum": 1.0, "maximum": 20.0, "description": "Guidance scale (default 6)"},
            "denoise": {"type": "number", "minimum": 0.0, "maximum": 1.0, "description": "i2i only, default 0.55 — a t2i request always forces 1.0 regardless of this value, since starting from an empty latent at partial denoise produces a hazy/washed-out image"},
            "negative": {"type": "string", "description": "Optional negative prompt"},
            "hires_fix": {"type": "boolean", "description": "t2i only, default true. A second-pass latent upscale + refine that fixes small/distant faces (e.g. crossed eyes) at the cost of some extra render time. Set false only for a quick low-detail draft."},
            "face_detail": {"type": "boolean", "description": "Default false. Opt in to an automatic detected-face repair pass for crooked eyes, facial artifacts, or small damaged faces. NOT available with model_profile=realpro_flux (Flux) -- that combination always fails after the backend has already started. Use realvisxl if face_detail is needed."},
        },
        "required": ["story", "prompt"],
    },
    "story_image_job_status": {
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
                "description": "Ordered still jobs; each needs story+prompt. Queue ALL unique start/end frames in one batch — no artificial batch size limit. Optional mode/size/model_profile per job.",
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
    "prepare_storyboard_review": {
        "type": "object",
        "properties": {
            "story": {"type": "string", "description": "Short general-story slug"},
            "plan": {"type": "object", "description": "Structured characters and shots plan"},
        },
        "required": ["story", "plan"],
    },
    "record_storyboard_reference_sheets": {
        "type": "object",
        "properties": {
            "story": {"type": "string", "description": "Existing general-story slug"},
            "reference_sheets": {"type": "object", "description": "Character id to reviewed simple sheet filename"},
        },
        "required": ["story", "reference_sheets"],
    },
    "approve_storyboard_references": {
        "type": "object",
        "properties": {
            "story": {"type": "string", "description": "Existing general-story slug"},
            "operator_confirmed": {"type": "boolean", "description": "True only when the operator explicitly approved the reference overview"},
        },
        "required": ["story", "operator_confirmed"],
    },
    "storyboard_frame_plan": {
        "type": "object",
        "properties": {"story": {"type": "string", "description": "Existing general-story slug"}},
        "required": ["story"],
    },
    "plan_shot_reasoning": {
        "type": "object",
        "properties": {
            "story": {"type": "string", "description": "Story slug (used to load/record shot_decisions.jsonl)"},
            "shot_id": {"type": "string", "description": "This shot/clip id"},
            "prompt": {"type": "string", "description": "The shot's prompt/script text to reason over"},
            "is_video_shot": {"type": "boolean", "description": "True for a video shot (adds continuity_mode/continuity_source to the decision)"},
            "model": {"type": "string", "description": "Optional override of the resident reasoning chat model"},
        },
        "required": ["story", "shot_id", "prompt"],
    },
    "capabilities": {"type": "object", "properties": {}},
    "see_image": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Local image path"},
            "question": {"type": "string", "description": "What to inspect or extract for the prompt"},
            "crop": {"type": "array", "items": {"type": "integer"},
                     "minItems": 4, "maxItems": 4,
                     "description": "Optional native-resolution crop [left, top, right, bottom]"},
        },
        "required": ["path"],
    },
    "video_frames": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Local video path"},
            "at": {"type": "array", "items": {"type": "number"}, "description": "Exact frame times in seconds"},
            "every_n_seconds": {"type": "number", "description": "Sampling interval in seconds"},
        },
        "required": ["path"],
    },
    "analyze_video": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Local video path"},
            "question": {"type": "string", "description": "What to inspect or extract for the prompt"},
            "at": {"type": "array", "items": {"type": "number"}, "description": "Optional exact sample times in seconds"},
            "detail": {"type": "string", "enum": ["per_second", "half_second", "overview"],
                       "description": "Temporal detail: per_second is the default; half_second adds denser coverage; overview retains six broad samples"},
        },
        "required": ["path"],
    },
    "render_video_from_reference": {
        "type": "object",
        "properties": {
            "reference_video": {"type": "string", "description": "Local path of the clip whose body motion to reuse"},
            "character_image": {"type": "string", "description": "Local path of the character still (a clear face works best)"},
            "prompt": {"type": "string", "description": "Describe the character (clothes, hair) and the scene to generate"},
            "negative": {"type": "string", "description": "Optional negative prompt"},
            "face_prompt": {"type": "string", "description": "Optional prompt for the face-detail pass"},
            "target": {"type": "string", "enum": ["auto", "largest", "left", "right", "center"],
                       "description": "Which person in the reference becomes the character (default auto = largest face)"},
            "target_fps": {"type": "number", "description": "Output fps, 4-12 (default 8)"},
            "start_seconds": {"type": "number", "description": "Where in the reference to start (default 0)"},
            "max_seconds": {"type": "number", "description": "Length to render; at most 64 frames per job"},
            "seed": {"type": "integer", "description": "Sampler seed"},
            "face_detail": {"type": "boolean", "description": "Video face-detail pass (default true)"},
            "likeness_attestation": {"type": "boolean",
                                     "description": "Must be true: character is fictional or consented; never a real person's likeness in sexual content"},
        },
        "required": ["reference_video", "character_image", "prompt", "likeness_attestation"],
    },
    "video_reference_job_status": {
        "type": "object",
        "properties": {"job_id": {"type": "string", "description": "mtr_... id returned by render_video_from_reference"}},
        "required": ["job_id"],
    },
    "plan_video_from_reference": {
        "type": "object",
        "properties": {
            "reference_video": {"type": "string",
                                "description": "Local path of the clip whose motion should be reused"},
            "character_image": {"type": "string",
                                "description": "Local path of the character still to put into the motion"},
            "target_fps": {"type": "number",
                           "description": "Optional output fps; default per approach (16 Wan, 8 AnimateDiff)"},
        },
        "required": ["reference_video", "character_image"],
    },
    "media_job_status": {
        "type": "object",
        "properties": {
            "job_id": {"type": "string",
                       "description": "job_id from a {\"queued\": true} tool result"},
            "path": {"type": "string",
                     "description": "Alternative: the analysed file path; lists every job for it"},
        },
    },
    "extract_video_actions": {
        "type": "object",
        "properties": {
            "video_path": {
                "type": "string",
                "description": "Absolute or repo-relative path to the target video file",
            },
            "format_h3_beats": {
                "type": "boolean",
                "description": "Format output as Equal Shares H3 shot beats (default false)",
            },
            "focus_character": {
                "type": "string",
                "description": "Equal Shares character name to track closely (e.g. 'Kent', 'Avery', 'Doris')",
            },
            "fps": {
                "type": "number", "minimum": 0.1, "maximum": 2.0,
                "description": "Observation rate; default 1.0 means one labelled evidence window per second. Use 2.0 only when half-second visual changes matter.",
            },
        },
        "required": ["video_path"],
    },
    "read_video_metadata": {
        "type": "object", "properties": {"path": {"type": "string", "description": "Local video or PNG path"}},
        "required": ["path"],
    },
    "audio_measure": {
        "type": "object", "properties": {"path": {"type": "string", "description": "Local audio or video path"}},
        "required": ["path"],
    },
    "transcribe": {
        "type": "object", "properties": {
            "path": {"type": "string", "description": "Local audio or video path"},
            "expected_text": {"type": "string", "description": "Optional expected words for a word-level diff"}},
        "required": ["path"],
    },
    "compare_voice": {
        "type": "object", "properties": {
            "a": {"type": "string", "description": "First local audio/video path"},
            "b": {"type": "string", "description": "Second local audio/video path"}},
        "required": ["a", "b"],
    },
    "ensure_sonic_pi": {
        "type": "object",
        "properties": {
            "timeout": {"type": "number", "description": "Seconds to wait for Sonic Pi to boot (default 90)"},
        },
    },
    "queue_sonic_pi": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Full Sonic Pi Ruby for the next segment. Use named live_loops; prefer use_bpm when tempo matters.",
            },
        },
        "required": ["code"],
    },
    "play_sonic_pi_note": {
        "type": "object",
        "properties": {
            "note": {"type": "integer", "description": "MIDI note number 0-127 (default 60)"},
            "synth": {"type": "string", "description": "Synth name, e.g. :beep, :saw, :prophet"},
            "sustain": {"type": "number", "description": "Note length in seconds (default 1)"},
            "cutoff": {"type": "number", "description": "Filter cutoff (default 100)"},
        },
        "required": ["note"],
    },
    "stop_sonic_pi": {
        "type": "object",
        "properties": {},
    },
    "comfy_generate": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["image", "controlnet", "ip_adapter", "video", "3d",
                         "upscale", "remove_background", "audio"],
                "description": "generate_image action (default image)",
            },
            "prompt": {"type": "string", "description": "Text prompt"},
            "filename_prefix": {
                "type": "string",
                "description": (
                    "Forwarded to MCP. Honored only for action audio, video, "
                    "and remove_background. action image/controlnet/ip_adapter/"
                    "upscale hardcode SaveImage filename_prefix to ComfyUI."
                ),
            },
        },
    },
    "comfy_job_status": {
        "type": "object",
        "properties": {
            "prompt_id": {
                "type": "string",
                "description": "prompt_id returned by comfy_generate",
            },
            "timeout_s": {
                "type": "number",
                "description": "Bounded poll budget in seconds (default 90, cap 300)",
            },
        },
        "required": ["prompt_id"],
    },
    "comfy_workflow": {
        "type": "object",
        "properties": {
            "tool": {
                "type": "string",
                "enum": ["enqueue_workflow", "queue", "create_workflow",
                         "visualize_workflow", "get_workflow", "save_workflow"],
                "description": "Which comfyui-mcp workflow tool to call",
            },
            "action": {
                "type": "string",
                "description": (
                    "enqueue_workflow: enqueue (default), rerun, run_url, "
                    "template_schema, run_template"
                ),
            },
            "workflow": {
                "description": (
                    "enqueue: API-format graph object, JSON string of that "
                    "object, or local file path. A path is loaded server-side; "
                    "do not paste the graph into the tool call."
                ),
            },
            "workflow_path": {
                "type": "string",
                "description": (
                    "enqueue: local JSON file of an API-format graph. Alias of "
                    "passing a path as workflow. Preferred when the graph is on disk."
                ),
            },
        },
        "required": ["tool"],
    },
    "comfy_assets": {
        "type": "object",
        "properties": {
            "tool": {
                "type": "string",
                "enum": ["get_image", "upload_image"],
                "description": "Which asset tool (default get_image)",
            },
        },
    },
    "comfy_models": {
        "type": "object",
        "properties": {
            "tool": {
                "type": "string",
                "enum": ["download_model", "list_local_models"],
                "description": "Which model tool",
            },
            "action": {"type": "string", "description": "comfyui-mcp action (list, remove, download, …)"},
        },
        "required": ["tool"],
    },
    "comfy_nodes": {
        "type": "object",
        "properties": {
            "tool": {
                "type": "string",
                "enum": ["search_custom_nodes", "install_custom_node", "node_pack"],
                "description": "Which node tool",
            },
        },
        "required": ["tool"],
    },
    "comfy_system": {
        "type": "object",
        "properties": {
            "tool": {
                "type": "string",
                "enum": ["get_system_stats", "clear_vram", "get_history", "comfy_cli"],
                "description": "Which system tool (default get_system_stats)",
            },
            "action": {
                "type": "string",
                "description": "For get_system_stats: stats (default), logs, or health",
            },
        },
    },
    "comfy_process": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "stop", "restart"],
                "description": "restart_comfyui action (default restart)",
            },
        },
    },
}


def profile_for(decision) -> str:
    """'cpu' compact, 'gpu' full, 'gpu_core' farm-down, or 'gpu_image'."""
    backend = getattr(decision, "backend", "ollama")
    tier = getattr(decision, "tier", "gpu")
    detail = getattr(decision, "detail", None) or {}
    # Farm compact stays first. Image intent overrides CPU-tier fallback so a
    # busy-GPU Huihui-8B hop still sees plan/render/status instead of meta-tools.
    if backend == "farm" or tier == "farm":
        return "cpu"
    if detail.get("capability") == "image":
        return "gpu_image"
    if tier == "cpu":
        return "cpu"
    if detail.get("gpu_tool_fallback"):
        return "gpu_core"
    return "gpu"


def is_comfy_workflow_prompt(text: str | None) -> bool:
    """True when the operator asked to enqueue/inspect a Comfy graph."""
    return bool(_COMFY_WORKFLOW_TURN_RE.search(str(text or "")))


def gpu_core_tool_names(prompt: str | None = None) -> tuple[str, ...]:
    names = list(CORE_DIRECT_TOOLS)
    if is_comfy_workflow_prompt(prompt):
        names.extend(COMFY_CORE_TOOLS)
    return tuple(names)


def schemas(*, include_project: bool = True, profile: str = "gpu",
            prompt: str | None = None) -> list[dict]:
    """OpenAI-style tool schemas for Ollama.

    General chats omit Equal Shares-only actions so their presence cannot bias
    model tool selection. Direct callers retain the historical full schema by
    default, and server-side dispatch remains the authoritative guard.

    ``profile="cpu"`` advertises only the three compact meta-tools; the
    catalog they wrap still honours ``include_project``. Meta-tools are
    never members of TOOLS and never appear in the default GPU surface.

    ``profile="gpu_core"`` is the farm-down / skip_farm tool-classified GPU
    fallback: CORE_DIRECT_TOOLS, plus COMFY_CORE_TOOLS when ``prompt`` is a
    Comfy/workflow turn. Not used for pinned Huihui conversation hops.

    ``profile="gpu_image"`` is capability=image: IMAGE_DIRECT_TOOLS only
    (plan/render/status). Used for both GPU 14B and busy-GPU CPU 8B hops.
    """
    if profile == "cpu":
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": _META_DESCRIPTIONS[name],
                    "parameters": _META_SCHEMAS[name],
                },
            }
            for name in META_TOOL_NAMES
        ]
    allow = None
    if profile == "gpu_core":
        allow = set(gpu_core_tool_names(prompt))
    elif profile == "gpu_image":
        allow = set(IMAGE_DIRECT_TOOLS)
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": _SCHEMAS.get(name, {"type": "object", "properties": {}}),
            },
        }
        for name, (_, desc) in TOOLS.items()
        if (include_project or name not in PROJECT_ONLY_TOOLS)
        and (allow is None or name in allow)
    ]


def describe() -> str:
    return "\n".join(f"- {n}: {d}" for n, (_, d) in TOOLS.items())


def _visible_tool_names(*, include_project: bool = True) -> list[str]:
    return [
        name for name in TOOLS
        if include_project or name not in PROJECT_ONLY_TOOLS
    ]


def _one_line_summary(desc: str, limit: int = 160) -> str:
    text = " ".join((desc or "").strip().split())
    for sep in (". ", " — ", " – "):
        if sep in text:
            text = text.split(sep, 1)[0].rstrip(" .") + "."
            break
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


_CATEGORY_ALIASES = {
    "file_operations": "file",
    "files": "file",
    "filesystem": "file",
    "fs": "file",
    "web_search": "web",
    "search": "web",
    "images": "story_image",
    "image": "story_image",
    "music": "sonic_pi",
    "audio": "sensory",
    "vision": "sensory",
}


def _catalog(*, include_project: bool = True,
             category: str | None = None, search: str | None = None) -> dict:
    grouped: dict[str, list[dict]] = {}
    needle = (search or "").strip().lower()
    want = (category or "").strip().lower() or None
    if want:
        want = _CATEGORY_ALIASES.get(want, want)
    for name in _visible_tool_names(include_project=include_project):
        group = _TOOL_CATEGORY.get(name, "other")
        if want and group != want:
            continue
        summary = _one_line_summary(TOOLS[name][1])
        if needle and needle not in name.lower() and needle not in summary.lower():
            continue
        grouped.setdefault(group, []).append({"name": name, "summary": summary})
    return {"categories": grouped}


def parse_call_tool_args(args: dict) -> tuple[str, dict]:
    """Resolve call_tool aliases. Returns (inner_name, inner_args).

    Missing/invalid names become empty string; invalid args become
    ``{"__invalid_tool_arguments__": ...}`` so run_one can refuse them.
    """
    raw = dict(args or {})
    inner_name = str(raw.get("name") or raw.get("tool_name") or "").strip()
    inner_args = raw.get("args", raw.get("arguments", {}))
    if inner_args is None:
        inner_args = {}
    if isinstance(inner_args, str):
        try:
            inner_args = json.loads(inner_args)
        except json.JSONDecodeError:
            return inner_name, {"__invalid_tool_arguments__": inner_args}
    if not isinstance(inner_args, dict):
        return inner_name, {"__invalid_tool_arguments__": repr(inner_args)}
    return inner_name, inner_args


def _handle_list_tools(args: dict, *, include_project: bool) -> str:
    return json.dumps(_catalog(
        include_project=include_project,
        category=str(args.get("category") or "") or None,
        search=str(args.get("search") or "") or None,
    ), indent=2)


def _handle_describe_tool(args: dict, *, include_project: bool) -> str:
    names: list[str] = []
    if args.get("names"):
        raw_names = args.get("names")
        if isinstance(raw_names, str):
            names = [raw_names]
        elif isinstance(raw_names, list):
            names = [str(n).strip() for n in raw_names if str(n).strip()]
    single = str(args.get("name") or "").strip()
    if single and single not in names:
        names.insert(0, single)
    names = names[:3]
    visible = _visible_tool_names(include_project=include_project)
    visible_set = set(visible)
    if not names:
        return ("ERROR: describe_tool needs name or names. "
                f"Visible: {', '.join(visible)}")
    described = []
    for name in names:
        if name not in visible_set:
            return (f"ERROR: no visible tool {name!r}. "
                    f"Visible: {', '.join(visible)}")
        described.append({
            "name": name,
            "description": TOOLS[name][1],
            "parameters": _SCHEMAS.get(name, {"type": "object", "properties": {}}),
        })
    return json.dumps(described if len(described) > 1 else described[0], indent=2)


# The system prompt and the server's attachment note once named tools that
# do not exist (analyze_image, measure_audio); the model was told to call them
# and got "no tool" back. The prompt now names see_image / audio_measure; these
# aliases keep any model or replay that still uses the old names working.
_TOOL_ALIASES = {
    "analyze_image": "see_image",
    "measure_audio": "audio_measure",
}
_SCHEDULE_TOOLS = frozenset({
    "schedule_phone_messages", "list_phone_schedules", "cancel_phone_schedule"})
_QUEUED_MEDIA_TOOLS = frozenset({
    "see_image", "analyze_video", "extract_video_actions", "transcribe"})


_catalog_include_project = True


def set_catalog_include_project(include_project: bool) -> None:
    """Hop-loop catalog visibility for list_tools/describe_tool.

    Kept off the tools.call() signature so existing mocks that accept
    ``(name, args, context=None)`` stay valid.
    """
    global _catalog_include_project
    _catalog_include_project = bool(include_project)


_CONVERSATION_BOUND_TOOLS = frozenset({
    "prepare_chat_render",
    "start_current_chat_render",
    "render_story_image",
    "render_story_image_batch",
    "story_image_job_status",
    "await_story_image_job",
    "present_story_stills_for_review",
    "approve_story_stills",
    "story_stills_review_status",
    "ingest_prompt_pack",
    "export_prompt_pack_outputs",
    "prompt_pack_status",
    "run_prompt_pack_production",
})
_REMOTE_GPU_TOOLS = frozenset({
    "start_batch_render",
    "render_video_from_reference",
    "start_current_chat_render",
    "render_story_image",
    "render_story_image_batch",
    "run_prompt_pack_production",
})


def _public_args(args: dict) -> dict:
    """Drop caller-supplied reserved fields. call() re-adds the trusted ones."""
    return {key: value for key, value in args.items() if not str(key).startswith("__")}


def call(name: str, args: dict,
         context: remote_security.ToolContext | None = None,
         *, include_project: bool | None = None) -> str:
    context = context or remote_security.DESKTOP_CONTEXT
    args = dict(args or {})
    if "__invalid_tool_arguments__" in args:
        raw = args["__invalid_tool_arguments__"]
        return ("ERROR: malformed JSON tool arguments; the tool was not run. "
                f"Raw arguments: {raw!r}")
    args = _public_args(args)
    if include_project is None:
        include_project = _catalog_include_project
    if name == "list_tools":
        result = _handle_list_tools(args, include_project=include_project)
        remote_security.audit_tool(context, name, args or {}, "allowed",
                                   "compact catalog")
        return result
    if name == "describe_tool":
        result = _handle_describe_tool(args, include_project=include_project)
        status = "refused" if result.startswith("ERROR") else "allowed"
        remote_security.audit_tool(context, name, args or {}, status,
                                   "compact describe")
        return result
    if name == "call_tool":
        inner_name, inner_args = parse_call_tool_args(args)
        if not inner_name:
            result = "ERROR: call_tool needs name or tool_name."
            remote_security.audit_tool(context, name, args or {}, "refused",
                                       "missing inner name")
            return result
        if inner_name in META_TOOL_NAMES:
            result = (f"ERROR: call_tool cannot invoke meta-tool {inner_name!r}. "
                      "Pass a cataloged tool name.")
            remote_security.audit_tool(context, name, args or {}, "refused",
                                       "nested meta-tool")
            return result
        return call(inner_name, inner_args, context=context,
                    include_project=include_project)
    name = _TOOL_ALIASES.get(name, name)
    if name not in TOOLS:
        result = f"ERROR: no tool {name!r}. Available: {', '.join(TOOLS)}"
        remote_security.audit_tool(context, name, args or {}, "refused", "unknown tool")
        return result
    if not context.permits(name):
        result = (f"ERROR: tool {name!r} is not permitted from this phone identity. "
                  "The desktop operator must explicitly grant it.")
        remote_security.audit_tool(context, name, args or {}, "denied",
                                   "remote capability not granted")
        return result
    # Only this trusted dispatch seam may label a render request as remote.
    # The model's tool JSON cannot forge or choose another phone identity.
    if context.remote and name in _REMOTE_GPU_TOOLS:
        args["__remote_render_identity"] = context.remote_identity
    if name in _CONVERSATION_BOUND_TOOLS:
        args["__conversation_id"] = str(context.conversation_id or "")
    # Managed prompt-pack dry-run: block still renders until explicitly unlocked.
    if name in {"render_story_image", "render_story_image_batch", "await_story_image_job"}:
        try:
            import managed_prompt_pack
            cid = str(args.get("__conversation_id") or context.conversation_id or "")
            op_text = str(args.get("__operator_text") or "")
            allowed, reason = managed_prompt_pack.render_allowed(cid, op_text or None)
            if not allowed:
                remote_security.audit_tool(context, name, args or {}, "refused",
                                           "prompt-pack dry-run gate")
                return f"ERROR: {reason}"
            # Refuse obvious placeholder prompts even when unlocked.
            prompt_val = str(args.get("prompt") or "")
            if managed_prompt_pack.is_placeholder_prompt(prompt_val):
                remote_security.audit_tool(context, name, args or {}, "refused",
                                           "placeholder prompt")
                return ("ERROR: refusing placeholder image prompt "
                        f"{prompt_val!r}; use the saved prompt-pack source clips.")
            jobs = args.get("jobs")
            if isinstance(jobs, list):
                for job in jobs:
                    if isinstance(job, dict) and managed_prompt_pack.is_placeholder_prompt(
                            job.get("prompt")):
                        remote_security.audit_tool(context, name, args or {}, "refused",
                                                   "placeholder prompt in batch")
                        return ("ERROR: refusing placeholder batch prompt "
                                f"{job.get('prompt')!r}; use saved pack clips.")
        except Exception:
            pass
    block = None
    if name in _VIDEO_TOOLS_NEEDING_STILL_APPROVAL:
        block = _stills_review_blocks_video(str(args.get("__conversation_id") or context.conversation_id or ""))
    elif name == "comfy_generate" and str(args.get("action") or "").strip().lower() == "video":
        block = _stills_review_blocks_video(str(context.conversation_id or ""))
    if block:
        remote_security.audit_tool(context, name, args or {}, "refused", "stills review gate")
        return f"ERROR: {block}"
    # Queued sensory work may complete after the model turn and its Sideband
    # request have ended.  These values are injected only below the model, at
    # the same trusted dispatch seam as remote render/schedule attribution;
    # callers cannot select a recipient or conversation themselves.
    if context.remote and name in _QUEUED_MEDIA_TOOLS:
        args["__remote_media_identity"] = context.remote_identity
        args["__remote_media_conversation_id"] = context.conversation_id
        args["__remote_media_request_id"] = context.request_id
    # Scheduled messages always go back to the caller. Injected here so the model
    # cannot name a recipient; a desktop call leaves this empty and is refused.
    if name in _SCHEDULE_TOOLS:
        args.pop("__remote_schedule_identity", None)
        if context.remote:
            args["__remote_schedule_identity"] = context.remote_identity
    try:
        result = TOOLS[name][0](args)
        remote_security.audit_tool(context, name, args or {}, "allowed",
                                   "tool completed")
        return result
    except ToolError as e:
        result = f"ERROR: {e}"
        remote_security.audit_tool(context, name, args or {}, "refused", str(e))
        return result
    except Exception as e:
        result = f"ERROR: {type(e).__name__}: {e}"
        remote_security.audit_tool(context, name, args or {}, "error",
                                   f"{type(e).__name__}: {e}")
        return result


if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(call(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}))
    else:
        print(describe())
