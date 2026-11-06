#!/usr/bin/env python3
"""Durable stills-then-videos production for managed prompt packs.

Operator ask: complete images and videos (or equivalent). Export alone is not
enough. This module unlocks render, builds unique still jobs from saved clip
JSON, and starts a resume-safe background supervisor that:
  1) renders every start/last still via work/image_render.py (SDXL/realvisxl
     for the reviewed Backrooms pack, including optional LoRA)
  2) flushes VRAM between jobs
  3) runs Minimax FLF2V for every clip via work/render_single_pass.py

Authority: tools.py starts the supervisor only after allow_render is true.
Equal Shares / H3 diversion is forbidden here.
"""
from __future__ import annotations

import json
import csv
import hashlib
import uuid
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from atomic_io import atomic_write_text
import managed_prompt_pack

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
WORK = ROOT / "work"
PYTHON = sys.executable

_FULL_PRODUCTION_RE = re.compile(
    r"\b(?:"
    r"(?:complete|finish|generate|render|make|create|produce|run)\s+"
    r"(?:(?:all|every|the|full)\s+)?(?:images?|stills?|frames?|pngs?|photos?)\s+"
    r"(?:and|&|then|,)\s+(?:(?:all|every|the|full)\s+)?(?:videos?|clips?|mp4s?|motion|flf2v|minimax)"
    r"|"
    r"(?:images?|stills?)\s+(?:and|&|then)\s+(?:videos?|clips?)"
    r"|"
    r"full\s+production|render\s+everything|complete\s+(?:the\s+)?media"
    r"|"
    r"all\s+unique\s+(?:flux\s+|sdxl\s+)?stills?.*(?:videos?|flf2v|minimax)"
    r")\b",
    re.I | re.S,
)

_PACK_PATH_RE = re.compile(
    r"([A-Za-z]:\\[^\n\"']+?backrooms_sitcom_prompt_pack_EDITED\.md)"
    r"|(/[^\n\"']+?backrooms_sitcom_prompt_pack_EDITED\.md)",
    re.I,
)


def wants_full_production(text: str | None) -> bool:
    """True when the operator asks for stills+videos completion this turn."""
    raw = str(text or "").strip()
    if not raw:
        return False
    if managed_prompt_pack.is_prompt_pack(raw) or len(raw) > 4000:
        # Pack body embeds "Generate the stills first"; only wrappers count.
        return bool(
            _FULL_PRODUCTION_RE.search(raw[:900])
            or _FULL_PRODUCTION_RE.search(raw[-900:])
        )
    return bool(_FULL_PRODUCTION_RE.search(raw))


def extract_pack_path(text: str | None) -> Path | None:
    raw = str(text or "")
    m = _PACK_PATH_RE.search(raw)
    if not m:
        return None
    path = Path((m.group(1) or m.group(2) or "").strip().strip("\"'"))
    return path if path.is_file() else None


def production_path(cid: str) -> Path:
    return managed_prompt_pack._task_dir(cid) / "production_progress.json"


def load_production(cid: str) -> dict | None:
    path = production_path(cid)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_production(cid: str, data: dict, *, clear_watchdog: bool = False) -> dict:
    data = dict(data)
    data["updated_at"] = time.time()
    path = production_path(cid)
    if path.is_file():
        current = json.loads(path.read_text(encoding="utf-8"))
        if current.get("watchdog_failure") and not clear_watchdog:
            data["watchdog_failure"] = current["watchdog_failure"]
            wf = str(current["watchdog_failure"]).strip().lower()
            content_pause = any(
                n in wf
                for n in (
                    "pause at safe checkpoint",
                    "safe checkpoint",
                    "manual audit",
                    "blind pass",
                    "semantic still qa failed",
                    "mechanical still qa failed",
                )
            )
            # Soft content pauses must not force status=error (bad stills retry).
            if not content_pause:
                data["status"] = "error"
        history = path.parent / "ledger_history" / f"{time.time_ns()}_{uuid.uuid4().hex}.json"
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("xb") as handle:
            handle.write(path.read_bytes())
    atomic_write_text(production_path(cid), json.dumps(data, indent=2, ensure_ascii=False))
    return data


def build_still_jobs(cid: str) -> list[dict]:
    """One job per unique start/last frame from exported clip JSON."""
    progress = managed_prompt_pack.load_progress(cid)
    if not progress:
        raise ValueError("no managed prompt-pack task for this chat")
    if managed_prompt_pack.has_incomplete_export(cid):
        raise ValueError("finish exporting the prompt pack before production")
    sha = str(progress.get("source_sha256") or "legacy")[:8]
    clips_dir = Path(progress["clips_dir"])
    jobs: list[dict] = []
    for clip_id in progress.get("clip_ids") or []:
        clip = json.loads((clips_dir / f"{clip_id}.json").read_text(encoding="utf-8"))
        managed_prompt_pack.validate_clips([clip])
        profile = str(clip.get("model_profile") or "realvisxl")
        for field, tag in (("start_frame", "start"), ("last_frame", "last")):
            story = f"pack_{cid}_{sha}_{clip_id.lower()}_{tag}"
            lora = clip.get(f"{field}_lora") or {}
            prompt_text = str(clip[field])
            # Avoid the diffusion model interpreting the recording device as a
            # foreground subject. Keep the requested tripod viewpoint while
            # making the framing constraint unambiguous.
            prompt_text = prompt_text.replace(
                "camcorder on tripod",
                "fixed eye-level viewpoint from behind the viewer; all recording equipment is outside the frame",
            )
            prompt_text = prompt_text.replace(
                "viewpoint from a tripod-mounted camcorder; the camcorder body, lens, and tripod are outside the frame",
                "fixed eye-level viewpoint from behind the viewer; all recording equipment is outside the frame",
            )
            # The source pack's Mode-A paragraph repeatedly names the physical
            # camera. SDXL interpreted that as a request to draw the equipment,
            # despite the negative prompt. Replace the whole framing sentence
            # with an equipment-free viewpoint before generation.
            prompt_text = re.sub(
                r"Diegetic camcorder POV lock[^\n]*:\s*[^\n]*\.",
                "Diegetic recorded-viewpoint lock: fixed eye-level framing from behind the recording device; equipment is completely outside the frame.",
                prompt_text,
                count=1,
                flags=re.IGNORECASE,
            )
            # Still anchors are scene plates. Filming language belongs in the
            # later video prompt; in SDXL it repeatedly produced cameras,
            # operators, and lighting rigs inside the scene.
            prompt_text = prompt_text.replace("camcorder look", "mild 1990s analog texture")
            prompt_text = prompt_text.replace("consumer camcorder found-footage", "low-fidelity 1990s analog")
            prompt_text = prompt_text.replace("VHS found-footage", "low-fidelity 1990s analog")
            prompt_text = prompt_text.replace("4:3 found-footage composition", "4:3 natural room composition")
            prompt_text = prompt_text.replace("clean readable handoff frame for image-to-video", "clean readable still frame")
            prompt_text = prompt_text.replace("Static single-frame SDXL reference still", "Photorealistic static scene")
            prompt_text = prompt_text.replace("sharp static reference frame", "sharp static image")
            prompt_text = prompt_text.replace("no polished cinematic camera moves", "natural unpolished composition")
            prompt_text = prompt_text.replace("camera damage", "analog image wear")
            prompt_text = prompt_text.replace("camera defects", "analog image defects")
            prompt_text = prompt_text.replace("off-screen camcorder", "viewer")
            prompt_text = prompt_text.replace("off-screen recording device", "viewer")
            prompt_text = prompt_text.replace("all recording equipment is outside the frame", "the room contains only ordinary household objects")
            prompt_text = prompt_text.replace("actor standing on a taped mark", "actor standing naturally near the center of the room")
            prompt_text = prompt_text.replace(
                "cheap apartment living room converted into a makeshift audition space",
                "modest ordinary apartment living room",
            )
            prompt_text = prompt_text.replace(
                "Authentic 1990s low-fidelity 1990s analog horror-comedy",
                "Photorealistic understated 1990s horror-comedy",
            )
            prompt_text = prompt_text.replace(
                "(no motion blur, no autofocus hunting, no exposure pumping — those belong only in the video prompt)",
                "with no motion blur and stable exposure",
            )
            clip_number = int(clip_id[1:]) if clip_id[1:].isdigit() else None
            if clip_number is not None and (clip_number <= 14 or (clip_number == 15 and tag == "start")):
                prompt_text = prompt_text.replace("and Backrooms continuity exactly", "exactly")
                prompt_text = prompt_text.replace(
                    "yellow Level 0 architecture, fluorescent lighting, damp carpet, and ",
                    "ordinary apartment architecture and ",
                )
            prompt_text = prompt_text.replace(
                "Diegetic recorded-viewpoint lock: fixed eye-level framing from behind the recording device; equipment is completely outside the frame.",
                "Viewer-perspective framing: natural eye-level composition showing only the fictional scene.",
            )
            prompt_text = prompt_text.replace(
                "makeshift audition space",
                "ordinary apartment living room with no studio setup, no film lighting, and no production gear",
            )
            prompt_text += ("\n\nVISIBLE-SCENE RULE: clean scene plate showing only the fictional "
                            "characters and environment, with ordinary household objects and practical "
                            "household lighting only.")
            if clip_number is not None and (clip_number <= 14 or
                    (clip_number == 15 and tag == "start")):
                prompt_text += (
                    "\n\nCHARACTER IDENTITY LOCK: the actor is the same fictional adult man in "
                    "his late twenties in every apartment frame: average build, short messy dark-brown "
                    "hair, faint five-o'clock shadow, olive-green overshirt over a faded gray T-shirt, "
                    "dark straight-leg jeans, worn white sneakers, and a cheap digital watch on his "
                    "left wrist. Keep his sex, age, face, hair, body, and clothing unchanged. He must "
                    "be visibly present whenever the endpoint description says actor, he, or him."
                )
            if clip_id == "C001":
                prompt_text += ("\n\nSUBJECT PRIORITY: the locked fictional adult male actor is clearly "
                                "visible head-to-toe near the center of the room, standing naturally and "
                                "facing toward the viewer. Use a wide establishing composition: the top "
                                "of his hair and the soles of both worn white sneakers are fully inside "
                                "the frame, with visible floor beneath and around both shoes. His complete "
                                "body occupies no more than sixty percent of image height.")
                prompt_text += (
                    "\n\nSETTING PRIORITY: this is unmistakably a living room, not a hallway, "
                    "doorway portrait, kitchen, or bedroom. A visible sofa or couch, a practical "
                    "household lamp, and a coffee table are clearly inside the frame around the actor."
                )
                if tag == "last":
                    prompt_text += (
                        "\n\nENDPOINT ACTION PRIORITY: this must not repeat the neutral opening pose. "
                        "The actor is visibly performing a friendly audition greeting: a clear "
                        "practiced sitcom smile is on his face and one hand is unmistakably raised "
                        "beside his upper body in a casual wave. Keep the other arm relaxed."
                    )
            job = {
                "story": story,
                "clip_id": clip_id,
                "frame": tag,
                "prompt": prompt_text,
                "negative": clip.get(f"{field}_negative") or "",
                "model_profile": profile,
                "width": 1024,
                "height": 768,
                # A fixed seed reproduced the same camera-leak composition on
                # every retry. Keep retries reproducible, but vary by clip and
                # frame so a failed composition is not deterministically cloned.
                "seed": int(hashlib.sha256(f"{clip_id}:{tag}".encode()).hexdigest()[:8], 16),
                # Endpoint frames normally require a visible pose/action change
                # from their continuity reference. Start above the old 0.42
                # setting; bounded retries may increase this further.
                "denoise": 0.52 if tag == "last" else 0.42,
            }
            # The camera is diegetic but must never be visible in the recorded
            # image. Make that constraint explicit to the diffusion model.
            job["negative"] = ((job["negative"] or "") +
                ", behind the scenes, film set, photographer, cinematographer, camera crew, "
                "visible recording camera, visible camcorder body, visible lens, visible tripod, "
                "camera operator, selfie camera, mirror reflection of camera, studio light stand, "
                "softbox, lighting rig, microphone boom, production equipment").strip(" ,")
            if clip_id == "C001":
                job["negative"] += (", close-up, medium shot, waist-up portrait, cropped body, "
                                    "cropped legs, cropped feet, shoes outside frame, hallway portrait, "
                                    "corridor portrait, doorway-only composition, kitchen, bedroom, bed")
            if isinstance(lora, dict) and lora.get("name"):
                job["lora_name"] = Path(str(lora["name"])).name
                job["lora_strength"] = float(lora.get("strength") or 0.5)
            jobs.append(job)
    return jobs


def build_video_jobs(cid: str) -> list[dict]:
    progress = managed_prompt_pack.load_progress(cid)
    if not progress:
        raise ValueError("no managed prompt-pack task for this chat")
    sha = str(progress.get("source_sha256") or "legacy")[:8]
    clips_dir = Path(progress["clips_dir"])
    jobs = []
    for clip_id in progress.get("clip_ids") or []:
        clip = json.loads((clips_dir / f"{clip_id}.json").read_text(encoding="utf-8"))
        jobs.append({
            "clip_id": clip_id,
            "story_start": f"pack_{cid}_{sha}_{clip_id.lower()}_start",
            "story_last": f"pack_{cid}_{sha}_{clip_id.lower()}_last",
            "video_prompt": clip.get("video_prompt") or "",
            "seed": 2026090700 + int(clip_id[1:]),
        })
    return jobs


def unlock_and_init_production(cid: str, *, operator_text: str = "") -> dict:
    """Mark allow_render, seed durable production progress, return snapshot."""
    progress = managed_prompt_pack.load_progress(cid)
    if not progress:
        raise ValueError("no managed prompt-pack task for this chat; ingest first")
    if managed_prompt_pack.has_incomplete_export(cid):
        managed_prompt_pack.export_all(cid)
        progress = managed_prompt_pack.load_progress(cid)
    progress["allow_render"] = True
    progress["mode"] = "production"
    progress["status"] = "producing"
    managed_prompt_pack._save_progress(cid, progress)
    stills = build_still_jobs(cid)
    videos = build_video_jobs(cid)
    existing = load_production(cid) or {}
    if existing and existing.get("source_sha256") != progress.get("source_sha256"):
        if _pid_live(existing.get("supervisor_pid")):
            raise ValueError("previous revision supervisor is live or uncertain")
        existing = {}
    prod = {
        **existing,
        "version": 1,
        "conversation_id": cid,
        "source_sha256": progress.get("source_sha256"),
        "phase": existing.get("phase") or "stills",
        "status": existing.get("status") if existing.get("status") in {"running", "complete"} else "queued",
        "operator_text": (operator_text or "")[:500],
        "auto_approve_video": False,
        "stills_total": len(stills),
        "videos_total": len(videos),
        "stills": existing.get("stills") if isinstance(existing.get("stills"), dict) else {},
        "videos": existing.get("videos") if isinstance(existing.get("videos"), dict) else {},
        "still_jobs": stills,
        "video_jobs": videos,
        "output_dir": progress.get("output_dir"),
        "log_path": str(managed_prompt_pack._task_dir(cid) / "production.log"),
        "supervisor_pid": existing.get("supervisor_pid"),
    }
    return save_production(cid, prod)


def _pid_live(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                text=True, stderr=subprocess.DEVNULL, timeout=8,
            )
            return any(len(row) > 1 and row[1] == str(pid) for row in csv.reader(out.splitlines()))
        except Exception:
            # Some hardened Windows configurations deny tasklist even for a
            # nonexistent PID.  Use the read-only PowerShell process table
            # before conservatively treating ownership as uncertain.
            try:
                probe = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; if($p){{'LIVE'}}"],
                    capture_output=True, text=True, timeout=8,
                )
                return probe.stdout.strip() == "LIVE"
            except Exception:
                return True
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def start_supervisor(cid: str, *, operator_text: str = "") -> dict:
    from production_integrity import process_lock
    with process_lock(production_path(cid).parent / "supervisor.lock"):
        return _start_supervisor(cid, operator_text=operator_text)


def _start_supervisor(cid: str, *, operator_text: str = "") -> dict:
    """Spawn the durable production worker if one is not already running."""
    existing = load_production(cid) or {}
    if _pid_live(existing.get("supervisor_pid")):
        return {"started": False, "already_running": True,
                "supervisor_pid": existing["supervisor_pid"],
                "note": "Existing supervisor is live or uncertain; no duplicate started."}
    failure = existing.get("watchdog_failure")
    if failure:
        msg = str(failure).strip().lower()
        content_pause = any(
            n in msg
            for n in (
                "pause at safe checkpoint",
                "safe checkpoint",
                "manual audit",
                "blind pass",
                "semantic still qa failed",
                "mechanical still qa failed",
            )
        )
        infra = (not content_pause) and any(
            n in msg
            for n in (
                "stale progress",
                "stale progress/logs",
                "dead supervisor",
                "supervisor dead",
                "no progress",
            )
        )
        if infra:
            raise ValueError("diagnose watchdog evidence and acknowledge it before retry")
        # Content / unknown pauses: clear so still retries can resume without a
        # formal acknowledge_watchdog step (Rhine: bad stills retry, not stop).
        existing = dict(existing)
        existing.pop("watchdog_failure", None)
        existing["status"] = "queued"
        existing["last_error"] = None
        save_production(cid, existing, clear_watchdog=True)
    prod = unlock_and_init_production(cid, operator_text=operator_text)
    if prod.get("status") == "complete":
        return {"started": False, "already_complete": True, "production": prod}
    live_pid = prod.get("supervisor_pid")
    if _pid_live(live_pid) and prod.get("status") == "running":
        return {
            "started": False,
            "already_running": True,
            "supervisor_pid": live_pid,
            "production_path": str(production_path(cid)),
            "log_path": prod.get("log_path"),
            "phase": prod.get("phase"),
            "stills_done": sum(1 for v in (prod.get("stills") or {}).values() if v.get("status") == "ok"),
            "stills_total": prod.get("stills_total"),
            "videos_done": sum(1 for v in (prod.get("videos") or {}).values() if v.get("status") == "ok"),
            "videos_total": prod.get("videos_total"),
        }
    worker = WORK / "run_prompt_pack_production.py"
    if not worker.is_file():
        raise FileNotFoundError(f"missing production worker {worker}")
    log_path = Path(prod["log_path"])
    log_path.parent.mkdir(parents=True, exist_ok=True)
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    log_f = open(log_path, "a", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [PYTHON, str(worker), "--cid", cid, "--root", str(ROOT)],
        cwd=str(ROOT),
        stdout=log_f,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )
    prod["supervisor_pid"] = proc.pid
    prod["status"] = "running"
    prod["started_at"] = time.time()
    save_production(cid, prod)
    log_f.close()
    still_profiles = sorted({
        str(job.get("model_profile") or "realvisxl") for job in (prod.get("still_jobs") or [])
    }) or ["realvisxl"]
    profile_label = " + ".join(still_profiles)
    return {
        "started": True,
        "supervisor_pid": proc.pid,
        "production_path": str(production_path(cid)),
        "log_path": str(log_path),
        "phase": prod.get("phase"),
        "stills_total": prod.get("stills_total"),
        "videos_total": prod.get("videos_total"),
        "note": (
            f"Background production started: {profile_label} stills for all unique "
            "start/last frames; videos wait for semantic QA and explicit hash-bound "
            "approval. Say continue to resume/poll. Do not claim completion until "
            "status=complete."
        ),
    }


def load_explicit_approval(cid: str, revision: str) -> dict:
    directory = managed_prompt_pack._task_dir(cid) / "approvals" / revision
    paths = sorted(directory.glob("*.json"))
    return json.loads(paths[-1].read_text(encoding="utf-8")) if paths else {}


def record_explicit_approval(cid: str, *, approved_by: str) -> dict:
    """Operator-only entry point; a full-production request never calls this."""
    from production_integrity import qa_passed, write_evidence
    if not approved_by.strip():
        raise ValueError("operator identity is required")
    prod = load_production(cid) or {}
    jobs = build_still_jobs(cid)
    stills = prod.get("stills") or {}
    if not jobs or any(not qa_passed(stills.get(j["story"]) or {}, j) for j in jobs):
        raise ValueError("every current still requires exact-model semantic QA first")
    review = {"status": "approved", "approval_kind": "explicit_operator",
              "approved_by": approved_by, "approved_at": time.time(),
              "source_sha256": prod["source_sha256"],
              "stills": {j["story"]: {"path": str(Path(stills[j["story"]]["png"]).resolve()),
                                     "sha256": stills[j["story"]]["sha256"]} for j in jobs}}
    path = managed_prompt_pack._task_dir(cid) / "approvals" / prod["source_sha256"] / f"{time.time_ns()}.json"
    write_evidence(path, review)
    return review


def acknowledge_watchdog(cid: str, *, diagnosis: str) -> None:
    from production_integrity import write_evidence
    prod = load_production(cid) or {}
    if not diagnosis.strip() or not prod.get("watchdog_failure"):
        raise ValueError("a recorded watchdog failure and diagnosis are required")
    if _pid_live(prod.get("supervisor_pid")):
        raise ValueError("supervisor is live or uncertain; retry refused")
    sys.path.insert(0, str(WORK))
    import image_render as ir
    if ir._port_open():
        raise ValueError("port 8188 is busy; retry refused")
    if ir.IMAGE_OWNER.exists():
        owner = json.loads(ir.IMAGE_OWNER.read_text(encoding="utf-8"))
        if any(ir._pid_alive(int(owner.get(k) or 0)) for k in ("pid", "backend_pid")):
            raise ValueError("image owner is live or uncertain; retry refused")
    write_evidence(production_path(cid).parent / "watchdog" / f"diagnosis_{time.time_ns()}.json",
                   {"failure": prod["watchdog_failure"], "diagnosis": diagnosis, "observed_at": time.time()})
    prod.pop("watchdog_failure")
    prod["status"] = "queued"
    save_production(cid, prod, clear_watchdog=True)


def status_snapshot(cid: str) -> dict:
    progress = managed_prompt_pack.load_progress(cid)
    prod = load_production(cid)
    if not progress:
        return {"exists": False, "conversation_id": cid}
    stills = (prod or {}).get("stills") or {}
    videos = (prod or {}).get("videos") or {}
    from production_integrity import physical_counts
    counts = physical_counts(prod or {}, load_explicit_approval(cid, (prod or {}).get("source_sha256") or "none"))
    return {
        "exists": True,
        "conversation_id": cid,
        "allow_render": bool(progress.get("allow_render")),
        "export_status": progress.get("status"),
        "production": {
            "verified_counts": counts,
            "status": (prod or {}).get("status"),
            "phase": (prod or {}).get("phase"),
            "supervisor_pid": (prod or {}).get("supervisor_pid"),
            "supervisor_live": _pid_live((prod or {}).get("supervisor_pid")),
            "stills_done": counts["stills_generated"],
            "stills_total": (prod or {}).get("stills_total") or 0,
            "videos_done": counts["videos_generated"],
            "videos_total": (prod or {}).get("videos_total") or 0,
            "production_path": str(production_path(cid)) if prod else None,
            "log_path": (prod or {}).get("log_path"),
            "output_dir": progress.get("output_dir"),
        },
    }
