#!/usr/bin/env python3
"""Guarded local image, audio and video analysis. No network and no downloads."""
from __future__ import annotations

import base64
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

import capabilities as caps
import llama_cpp_client
import ollama_client as oll
import router

if not hasattr(router, "gpu_free_mb"):
    raise ImportError(
        "media_tools: router.gpu_free_mb is missing — the server is running a stale "
        "router module. Restart START_LOCAL_AGENT_GUI.ps1 to reload."
    )

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
UPLOADS = HERE / "uploads"
DERIVED = UPLOADS / "derived"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


class MediaError(ValueError):
    pass


class MediaPreempted(RuntimeError):
    """A render claimed the GPU between safe media-work boundaries."""


def _raise_if_preempted(args: dict) -> None:
    check = args.get("__preempt_check")
    if callable(check):
        reason = check()
        if reason:
            raise MediaPreempted(str(reason))


def _set_progress(args: dict, stage: str, done: int, total: int) -> None:
    update = args.get("__progress_update")
    if callable(update):
        update(stage, done, total)


def _path(value: object, allowed: set[str] | None = None) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise MediaError("path is required")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    if not p.is_file():
        raise MediaError(f"media file not found: {p}")
    if allowed is not None and p.suffix.lower() not in allowed:
        raise MediaError(f"unsupported media type {p.suffix!r}")
    return p


def capabilities(_: dict) -> str:
    return json.dumps(caps.all_capabilities(), indent=2)


def _build_prompt(question: str, instruction: str | None) -> str:
    base = instruction or (
        "Analyze only what is visibly supported by the attached image(s). "
        "Return concise evidence useful for a MiniMax H3 generation prompt: "
        "subjects and stable appearance, setting, lighting/color, composition, "
        "camera/shot, visible action, spatial relationships, and continuity details. "
        "For a sequence, distinguish per-frame observations from inferred motion. "
        "Never claim to hear audio. Separate observation from inference.\n\n"
    )
    # A custom instruction is a rubric, not a replacement for the operator's
    # actual question.  Dropping ``question`` here caused prompt-pack QA to see
    # only a generic review schema: the VLM could approve a plausible room
    # without ever seeing the requested subject, pose, or action.
    focus = str(question or "").strip()
    if focus:
        return f"{base}\n\nOPERATOR REQUEST / EXPECTED CONTENT:\n{focus}"
    return base


VISION_SYSTEM_PROMPT = (
    "You are the local visual-analysis component. Ground every claim in the supplied "
    "image input and follow the user instruction precisely. Do not claim audio, "
    "hidden context, or events outside the visible evidence."
)


def _run_vision_gpu(images: list[Path], question: str, model: str, host: str,
                    instruction: str | None = None,
                    num_ctx: int = 16384,
                    num_predict: int | None = None,
                    json_mode: bool = False,
                    repeat_penalty: float = 1.08,
                    cache_prompt: bool | None = None) -> str:
    """Low-level GPU vision call. No VRAM check, no queue gate.

    repeat_penalty: llama.cpp repetition penalty (1.0 = off). Until 2026-09-24
    llama_cpp_client dropped it, so every caller effectively ran at 1.0; it is
    live now. Free-text callers keep 1.08. Callers whose output is a fixed
    yes/no checklist must pass 1.0: the penalty makes a repeated "yes" cheaper
    to flip to "no" by token frequency alone (CHANGELOG 2026-09-24ae).

    cache_prompt: None leaves llama-server's prompt-cache reuse as it is (the
    server default: the shared prefix is kept from the previous request);
    False makes the server prefill the whole prompt cold. The GVD judge
    passes False so a judgement does not depend on what the server saw
    before it (CHANGELOG 2026-09-25n, measured; 2026-09-25o, applied).

    num_ctx: context window for the vision model. Single-image calls need only
    16384. Multi-image action batches need 32768+ because each 768px frame
    encodes to ~1000–1500 visual tokens and the batch silently truncates when
    the context overflows.
    """
    # The agent has one approved visual model: the locally paired Qwen2.5-VL
    # Caption V4 GGUF plus its version-matched projector.  Do not silently
    # substitute an Ollama VLM when that lazy runtime is unavailable.
    if model != caps.QWEN25_VL_MODEL:
        return json.dumps({
            "available": False,
            "reason": "only the exact Qwen2.5-VL Caption V4 GGUF pair is permitted for vision",
        }, indent=2)
    if not caps.qwen25_vl_runtime_available():
        return json.dumps({
            "available": False,
            "reason": "the exact Qwen2.5-VL Caption V4 runtime is not active",
        }, indent=2)
    payload_images = [base64.b64encode(p.read_bytes()).decode("ascii") for p in images]
    # llama.cpp receives structured images and applies the Qwen2.5-VL chat
    # template. Do not embed literal
    # Qwen image-token strings in the text: doing so would duplicate the visual
    # placeholder; duplicate literal image tokens make the paired mmproj model
    # less reliable.
    # Caption/inspection turns should finish promptly; dense 20-frame action
    # batches retain a larger response allowance.
    options = {"num_gpu": 99, "num_ctx": num_ctx, "temperature": 0.0,
               "repeat_penalty": float(repeat_penalty),
               "json_mode": bool(json_mode),
               "num_predict": (num_predict if num_predict is not None
                               else (2048 if num_ctx > 16384 else 512))}
    if cache_prompt is not None:
        # Forwarded only when the caller decided; None keeps the server default.
        options["cache_prompt"] = bool(cache_prompt)
    text, _ = llama_cpp_client.chat(
        [{"role": "system", "content": VISION_SYSTEM_PROMPT},
         {"role": "user", "content": _build_prompt(question, instruction),
          "images": payload_images}],
        model=model, host=caps.QWEN25_VL_RUNTIME_HOST,
        options=options,
        timeout=1200,
    )
    return json.dumps({"available": True, "tier": "gpu", "host": caps.QWEN25_VL_RUNTIME_HOST,
                       "runtime": "llama.cpp",
                       "model": model, "analysis": text.strip()},
                      indent=2, ensure_ascii=False)


def _vision_direct(images: list[Path], question: str,
                   instruction: str | None = None) -> str:
    """Run vision on the best available GPU tier now — no queue gate.

    Used by analyze_video() after a preflight VRAM check, and by the watcher
    when it is about to re-run a queued job.
    """
    if not caps.qwen25_vl_runtime_available():
        return json.dumps({
            "available": False,
            "reason": ("the exact Qwen2.5-VL Caption V4 runtime is not active; "
                       "the media watcher must own its lazy start"),
        }, indent=2)
    return _run_vision_gpu(images, question, caps.QWEN25_VL_MODEL, router.GPU_HOST,
                           instruction)


def _remote_media_metadata(args: dict) -> dict:
    """Copy bridge-injected completion routing metadata, if any.

    This is deliberately an allowlist.  It is not model input and it never
    reaches the VLM; it rides with the durable queue job so the LXMF bridge can
    return a completed analysis to the paired requester.
    """
    return {key: str(args.get(key) or "") for key in (
        "__remote_media_identity", "__remote_media_conversation_id",
        "__remote_media_request_id") if args.get(key)}


def _vision(images: list[Path], question: str, *, instruction: str | None = None,
            remote_metadata: dict | None = None) -> str:
    """Tiered GPU vision with queue fallback.

    Tries the primary model (8B Q8_0) first.  If free VRAM is not enough, drops
    to the secondary model (4B / Llama 3.2 11B when installed).  If neither tier
    fits, enqueues the job and returns {"queued": true, ...}.

    router.gpu_busy() now correctly treats resident Ollama models as NOT a render
    conflict, so this function does not need its own false-positive filter.
    """
    # The watcher owns VLM startup and the documented chat-yield ladder. A
    # foreground chat turn must never evict a resident reasoning model itself.
    import media_queue as mq
    # Preserve only bridge-injected routing metadata. It is never supplied to
    # the VLM prompt; the Sideband bridge consumes it after a job is complete.
    job_args = {
        "images": [str(p) for p in images],
        "question": question,
        "instruction": instruction,
        **(remote_metadata or {}),
    }
    source = str(images[0]) if images else None
    reused = _completed_reuse("vision", job_args, source) if source else None
    if reused:
        return reused
    job = mq.enqueue("vision", job_args, priority="interactive", source=source)
    return json.dumps({
        "queued": True,
        "reason": "queued for the next safe media GPU window",
        "job_id": job["id"],
        "free_mb": router.gpu_free_mb(),
        "message": ("Vision analysis queued. "
                    "The background watcher will run it when the GPU is free."),
    }, indent=2)


def _completed_reuse(kind: str, args: dict, source: str) -> str | None:
    """A completed queue job's result for an identical request, or None.

    Consulted only on the queue path (the exact VLM runtime is not active, or
    a render owns the GPU), so an operator who re-attaches an already-analysed
    file gets the finished analysis instead of a second multi-minute wait —
    enqueue() only coalesces against pending/processing, so without this the
    same 11-minute analyze_video ran again (2026-09-25q). A result is reused
    only if it is complete: no frame left ``unavailable`` and the VLM did not
    report itself unavailable part-way through. The returned JSON carries a
    ``reused_completed_job`` marker naming the original job.
    """
    import media_queue as mq
    finder = getattr(mq, "find_completed", None)
    if not callable(finder):
        # A queue module without the lookup (an older module still loaded in a
        # long-running server, or a test stub that only provides enqueue) just
        # means no reuse; the request queues exactly as before.
        return None
    job = finder(kind, args, source=source)
    if not job:
        return None
    result = str(job.get("result") or "")
    if '"analysis_status": "unavailable"' in result or '"available": false' in result:
        return None
    try:
        parsed = json.loads(result)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    parsed["reused_completed_job"] = {
        "job_id": job.get("id"), "kind": kind,
        "queued_at": job.get("queued_at"), "done_at": job.get("done_at"),
        "note": ("Stored result of an earlier identical analysis of the same "
                 "unchanged file; no new inference ran."),
    }
    return json.dumps(parsed, indent=2, ensure_ascii=False)


def see_image(args: dict) -> str:
    p = _path(args.get("path"), IMAGE_EXTS)
    crop = args.get("crop")
    image = p
    if crop is not None:
        if not (isinstance(crop, list) and len(crop) == 4):
            raise MediaError("crop must be [left, top, right, bottom]")
        DERIVED.mkdir(parents=True, exist_ok=True)
        with Image.open(p) as im:
            box = tuple(int(x) for x in crop)
            if box[0] < 0 or box[1] < 0 or box[2] > im.width or box[3] > im.height or box[2] <= box[0] or box[3] <= box[1]:
                raise MediaError(f"crop {box} is outside {im.width}x{im.height}")
            image = DERIVED / f"{p.stem}_crop_{'_'.join(map(str, box))}.png"
            if not image.exists():
                im.crop(box).save(image)
    return _vision([image], str(args.get("question", "")),
                   remote_metadata=_remote_media_metadata(args))


def _probe(path: Path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,size,bit_rate:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
         "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise MediaError(r.stderr.strip() or "ffprobe failed")
    return json.loads(r.stdout)


def _duration(path: Path) -> float:
    return float((_probe(path).get("format") or {}).get("duration") or 0)


def _frame_times(duration: float, args: dict) -> list[float]:
    if args.get("at") is not None:
        raw = args["at"]
        if not isinstance(raw, list):
            raise MediaError("at must be an array of seconds")
        vals = [float(x) for x in raw]
    elif args.get("every_n_seconds") is not None:
        step = float(args["every_n_seconds"])
        if step <= 0:
            raise MediaError("every_n_seconds must be positive")
        vals, t = [], 0.0
        while t < duration:
            vals.append(t)
            t += step
    else:
        # Six native-resolution samples cover temporal structure without turning
        # the video into a downscaled contact sheet that hides faces/hands.
        vals = [duration * x for x in (0.0, 0.2, 0.4, 0.6, 0.8, 0.98)] if duration else [0.0]
    # 300-frame safety ceiling: prevents pathological cases (tiny step, very long video).
    # Leave a short decode margin at the tail. Some MP4s report a container
    # duration slightly beyond their final decodable frame.
    return sorted({round(max(0.0, min(float(v), max(0.0, duration - 0.25))), 3) for v in vals})[:300]


def _extract_frames(path: Path, times: list[float]) -> list[Path]:
    DERIVED.mkdir(parents=True, exist_ok=True)
    out = []
    source_id = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:10]
    for i, sec in enumerate(times):
        # PNG avoids FFmpeg's non-full-range-YUV restriction in its MJPEG
        # encoder. These are analysis intermediates, not deliverables: lossless
        # frames preserve the exact visual evidence used by the VLM.
        target = DERIVED / f"{path.stem}_{source_id}_{i:02d}_{sec:.3f}s.png"
        if not target.exists():
            # Decode through the requested point rather than using input seeking.
            # These are short reference clips, so exact action timing is worth the
            # small cost and avoids accidentally sampling a nearby key frame.
            r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ss", str(sec),
                                "-frames:v", "1", "-c:v", "png", "-y", str(target)],
                               capture_output=True, text=True, timeout=120)
            if r.returncode or not target.exists():
                raise MediaError(r.stderr.strip() or f"could not extract frame at {sec}s")
        out.append(target)
    return out


def video_frames(args: dict) -> str:
    p = _path(args.get("path"), VIDEO_EXTS)
    duration = _duration(p)
    times = _frame_times(duration, args)
    frames = _extract_frames(p, times)
    return json.dumps({"source": str(p), "duration": round(duration, 3),
                       "frames": [{"at": t, "path": str(f)} for t, f in zip(times, frames)]}, indent=2)


def _timeline_times(duration: float, args: dict) -> list[float]:
    """Return frame times suitable for short, action-critical reference clips.

    The default is one exact observation at the start of every second plus a
    final frame at the end of the clip.  A caller can request half-second
    coverage, or supply exact times for a deliberately chosen analysis.
    """
    if args.get("at") is not None:
        return _frame_times(duration, args)
    detail = str(args.get("detail", "per_second")).strip().lower()
    if detail not in {"per_second", "half_second", "overview"}:
        raise MediaError("detail must be per_second, half_second, or overview")
    if detail == "overview":
        return _frame_times(duration, args)
    step = 0.5 if detail == "half_second" else 1.0
    last = max(0.0, duration - 0.25)
    # Cap at 120 frames (≈2 min at 1 fps). Longer clips should use
    # extract_video_actions which batches frames for the action model.
    cap = 120
    vals, t = [], 0.0
    while t < duration and len(vals) < cap:
        vals.append(round(t, 3))
        t += step
    # Always retain the end-state. It matters especially for a 5–8 second beat.
    if not vals or last - vals[-1] >= 0.05:
        vals.append(round(last, 3))
    vals = sorted(set(vals))
    # Keep both the beginning and final state if a long video hits the cap.
    return vals if len(vals) <= cap else vals[:cap - 1] + [vals[-1]]


def _timeline_observation_instruction(at: float, question: str) -> str:
    return (
        f"This is exactly one video frame at {at:.3f} seconds. Analyze only what "
        "is visibly supported in this one frame for an action-critical generation "
        "prompt. State: subjects and identity cues; body pose and facing; hand/object "
        "contact; exact positions in the frame; expression; setting and lighting; "
        "camera angle/framing; and any motion blur or visible motion direction. "
        "Do not invent what happened before or after this frame. If a detail is not "
        "visible, say unknown. Never discuss audio. Keep it compact but specific.\n\n"
        f"Operator focus: {question or 'Build a precise visual prompt.'}"
    )


def _timeline_change_instruction(start: float, end: float, question: str) -> str:
    return (
        f"These are two frames from one short video: first at {start:.3f}s and "
        f"second at {end:.3f}s. This is a comparison task, not a scene description. "
        "Report only a change that can be supported by a visible difference between "
        "the first and second frame. For every claimed movement, name the first-frame "
        "position or pose and the second-frame position or pose. Do not use verbs such "
        "as walks, reaches, turns, or camera pans without that two-frame evidence. "
        "Cover subject movement/direction, pose, hand/object interaction, entrance/exit, "
        "expression, camera framing, and continuity; write 'no confirmed change' for "
        "a category that does not visibly change. Do not assume unseen intermediate "
        "events. If direction or action is ambiguous, explicitly say uncertain. Never "
        "discuss audio. Keep it compact and usable as a motion beat.\n\n"
        f"Operator focus: {question or 'Build a precise visual prompt.'}"
    )


def analyze_video(args: dict) -> str:
    p = _path(args.get("path"), VIDEO_EXTS)
    detail = str(args.get("detail", "per_second")).strip().lower()
    if detail not in {"per_second", "half_second", "overview"}:
        raise MediaError("detail must be per_second, half_second, or overview")

    # Preflight: only the watcher may have already created the exact VLM window. A
    # normal tool call queues instead of evicting the chat model.
    # extracting every frame. A partial analysis (some frames queued, some not) is
    # worse than queuing the whole job and getting a complete result later.
    free_mb = router.gpu_free_mb()
    direct_qwen = caps.qwen25_vl_runtime_available()
    if not direct_qwen:
        import media_queue as mq
        job_args = dict(args, path=str(p))
        reused = _completed_reuse("analyze_video", job_args, str(p))
        if reused:
            return reused
        job = mq.enqueue("analyze_video", job_args, priority="interactive", source=str(p))
        return json.dumps({
            "queued": True,
            "reason": "exact Qwen2.5-VL Caption V4 runtime is not active",
            "job_id": job["id"],
            "free_mb": free_mb,
            "message": ("Video analysis queued. "
                        "The background watcher will run it when the GPU is free."),
        }, indent=2)

    duration = _duration(p)
    times = _timeline_times(duration, args)
    frames = _extract_frames(p, times)
    question = str(args.get("question", "Analyze this video for prompt creation."))
    observations = []
    for at, frame in zip(times, frames):
        _raise_if_preempted(args)
        _set_progress(args, "analyzing frames", len(observations), len(times))
        # Use _vision_direct: preflight already confirmed VRAM is available.
        result = json.loads(_vision_direct(
            [frame], question,
            instruction=_timeline_observation_instruction(at, question)))
        observations.append({
            "at": at,
            "frame": str(frame),
            "visible_state": result.get("analysis") if result.get("available") else None,
            "analysis_status": "ok" if result.get("available") else "unavailable",
            "reason": result.get("reason"),
        })

    actions = []
    for i in range(len(frames) - 1):
        _raise_if_preempted(args)
        _set_progress(args, "comparing frames", i, max(1, len(frames) - 1))
        start, end = times[i], times[i + 1]
        # An identical pair has no visual evidence for a motion claim. This is a
        # deterministic safeguard against a generative vision model narrating
        # a plausible action where the extracted images prove nothing changed.
        if frames[i].read_bytes() == frames[i + 1].read_bytes():
            result = {"available": True,
                      "analysis": "No confirmed change: the extracted frames are identical."}
        else:
            result = json.loads(_vision_direct(
                [frames[i], frames[i + 1]], question,
                instruction=_timeline_change_instruction(start, end, question)))
        actions.append({
            "start": start,
            "end": end,
            "visible_change": result.get("analysis") if result.get("available") else None,
            "analysis_status": "ok" if result.get("available") else "unavailable",
            "reason": result.get("reason"),
        })
    measured = json.loads(audio_measure({"path": str(p)}))
    return json.dumps({
        "source": str(p), "duration": round(duration, 3),
        "timeline_detail": detail,
        "sample_times": times,
        "frame_by_frame": observations,
        "action_timeline": actions,
        "prompt_building_note": (
            "Use frame_by_frame for exact visual states and action_timeline for each "
            "motion beat. Fields marked unknown or uncertain are not evidence and must "
            "not be invented into a generation prompt."
        ),
        "audio_measurement": measured,
        "audio_content_warning": "This result contains measurements only; use the transcribe tool separately for words. Measurements do not identify speakers, music, or sound events.",
    }, indent=2, ensure_ascii=False)


def read_video_metadata(args: dict) -> str:
    p = _path(args.get("path"), VIDEO_EXTS | IMAGE_EXTS)
    graph = None
    if p.suffix.lower() == ".png":
        try:
            raw = Image.open(p).info.get("prompt")
            graph = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            pass
    else:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=prompt",
                            "-of", "json", str(p)], capture_output=True, text=True, timeout=60)
        try:
            graph = json.loads(json.loads(r.stdout)["format"]["tags"]["prompt"])
        except Exception:
            pass
    if not isinstance(graph, dict):
        return json.dumps({"source": str(p), "embedded_comfy_graph": False,
                           "media": _probe(p)}, indent=2)
    sys.path.insert(0, str(ROOT / "work"))
    from harvest_good_audio_masters import graph_facts
    facts = graph_facts(graph)
    classes = [str(n.get("class_type", "")) for n in graph.values()]
    checkpoints, steps, mp = [], [], []
    for node in graph.values():
        ins = node.get("inputs") or {}
        for key in ("unet_name", "model_name", "ckpt_name"):
            if isinstance(ins.get(key), str): checkpoints.append(ins[key])
        if isinstance(ins.get("steps"), (int, float)): steps.append(ins["steps"])
        for key in ("megapixels", "mp"):
            if isinstance(ins.get(key), (int, float)): mp.append(ins[key])
    return json.dumps({"source": str(p), "embedded_comfy_graph": True,
                       "node_path": "ref2va" if any("ReferenceToVideo" in c for c in classes) else "fl2va" if any("ImageToVideo" in c for c in classes) else "unknown",
                       "checkpoints": sorted(set(checkpoints)), "megapixels": mp,
                       "steps": steps, **facts}, indent=2, ensure_ascii=False)


def audio_measure(args: dict) -> str:
    p = _path(args.get("path"), AUDIO_EXTS | VIDEO_EXTS)
    sys.path.insert(0, str(ROOT / "work"))
    import harvest_good_audio_masters as harvest
    import speech_density
    density = speech_density.analyse(p)
    detailed = harvest.analyse(harvest.load_mono(p))
    return json.dumps({"source": str(p), **density,
                       "leading_artifact": detailed.get("leading_artifact"),
                       "leading_artifact_peak_dbfs": detailed.get("leading_artifact_peak_dbfs"),
                       "suggested_head_trim_seconds": detailed.get("trim_seconds"),
                       "limitations": ("These measurements cannot determine the words, gibberish, "
                                       "pronunciation, speaker identity, voice quality, music, sound "
                                       "events, or whether a human should accept the take.")}, indent=2)


def _do_transcribe(p: Path, cap: dict, args: dict) -> str:
    """Run Whisper transcription. No render-busy check — call transcribe() for that."""
    if cap.get("engine") == "faster_whisper":
        from faster_whisper import WhisperModel
        model = WhisperModel("large-v3", device="cpu", compute_type="int8", cpu_threads=4)
        segments, info = model.transcribe(str(p), word_timestamps=True)
        rows = [{"start": s.start, "end": s.end, "text": s.text.strip()}
                for s in segments]
        text = " ".join(s["text"] for s in rows).strip()
        engine = "faster_whisper large-v3, CPU int8"
        language = info.language
    else:
        DERIVED.mkdir(parents=True, exist_ok=True)
        source_id = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
        wav = DERIVED / f"{source_id}_asr_16k_mono.wav"
        if not wav.is_file():
            converted = subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(p), "-ar", "16000",
                 "-ac", "1", "-c:a", "pcm_s16le", "-y", str(wav)],
                capture_output=True, text=True, timeout=180)
            if converted.returncode or not wav.is_file():
                raise MediaError(converted.stderr.strip() or "could not prepare audio for Whisper")

        # One local CPU inference model at a time: evict the CPU chat model
        # before standalone Whisper loads, then Ollama reloads chat after the
        # tool result returns.
        unloaded = router._running_models(router.CPU_HOST) or []
        for resident in unloaded:
            router.unload(router.CPU_HOST, resident)
        env = {**os.environ, "EQUAL_SHARES_WHISPER_DEVICE": "cpu",
               "CUDA_VISIBLE_DEVICES": "-1",
               "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
               "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4"}
        worker = HERE / "whisper_transcribe_worker.py"
        run = subprocess.run(
            [str(caps.COMFY_PYTHON), str(worker), str(wav), str(caps.WHISPER_MODEL)],
            capture_output=True, text=True, timeout=900, env=env)
        if run.returncode:
            raise MediaError((run.stderr or run.stdout).strip() or "local Whisper failed")
        try:
            result = json.loads(run.stdout.strip().splitlines()[-1])
        except Exception as exc:
            raise MediaError(f"local Whisper returned invalid output: {exc}") from exc
        rows = result.get("segments") or []
        text = str(result.get("transcript") or "").strip()
        engine = result.get("engine")
        language = result.get("language")
    expected = str(args.get("expected_text", "")).strip()
    diff = None
    if expected:
        diff = list(difflib.ndiff(expected.split(), text.split()))
    return json.dumps({"source": str(p), "available": True,
                       "engine": engine, "model": cap.get("model"),
                       "language": language, "segments": rows,
                       "transcript": text, "expected_text": expected or None,
                       "word_diff": diff,
                       "warning": ("Whisper-tiny can mishear words, names, music and noisy speech. "
                                   "A transcript is evidence, not operator acceptance; an empty "
                                   "transcript means unknown.")},
                      indent=2, ensure_ascii=False)


def transcribe(args: dict) -> str:
    p = _path(args.get("path"), AUDIO_EXTS | VIDEO_EXTS)
    cap = caps.capability("transcription")
    if not cap["available"]:
        return json.dumps({"source": str(p), **cap}, indent=2)
    # Whisper runs on four CPU threads. Only an actual project render pauses
    # it; a resident local VLM, browser GPU use, or an unrelated GPU process is
    # not a reason to strand a CPU-only transcription indefinitely.
    owned, owner_reason = router.queue_owner()
    render_active = owned or router.comfy_listening()
    if render_active:
        import media_queue as mq
        job_args = dict(args, path=str(p))
        reused = _completed_reuse("transcribe", job_args, str(p))
        if reused:
            return reused
        job = mq.enqueue("transcribe", job_args, priority="interactive", source=str(p))
        return json.dumps({
            "queued": True,
            "reason": "render active",
            "job_id": job["id"],
            "message": ("Transcription queued (" +
                        (owner_reason if owned else "ComfyUI is listening on port 8188") +
                        "). The watcher will run it when the render finishes."),
        }, indent=2)
    return _do_transcribe(p, cap, args)


def transcribe_direct(args: dict) -> str:
    """Run transcription now, bypassing the render-busy queue gate.

    Called by the watcher after it has confirmed the render is finished.
    """
    p = _path(args.get("path"), AUDIO_EXTS | VIDEO_EXTS)
    cap = caps.capability("transcription")
    if not cap["available"]:
        return json.dumps({"source": str(p), **cap}, indent=2)
    return _do_transcribe(p, cap, args)


def _fmt_ts(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"


def _action_windows(frame_count: int, fps: float, duration: float) -> list[dict]:
    """Describe the exact evidence window represented by each extracted frame.

    The VLM is asked to label its output against these windows.  We retain the
    table in the tool result as well, so a later prompt-building turn can see
    precisely which seconds were observed instead of treating a prose summary
    as evidence for the whole clip.
    """
    sec_per_frame = 1.0 / fps
    windows = []
    for index in range(frame_count):
        start = round(index * sec_per_frame, 3)
        # A final partial second is still an observation window, not a reason
        # to silently drop the clip's end state.
        end = round(min(duration, start + sec_per_frame), 3)
        if end <= start:
            end = round(start + sec_per_frame, 3)
        windows.append({"frame": index + 1, "start": start, "end": end})
    return windows


def _action_frame_instruction(windows: list[dict], focus_character: str | None,
                              format_h3_beats: bool,
                              measured_camera: dict[int, str] | None = None) -> str:
    """VLM instruction for one batch of action frames.

    measured_camera: optional {frame: label} from camera_motion.py
    (2026-09-25d). When given, each frame-table row carries the measured
    value and the rules tell the model to copy it into the cam= slot unless
    the frames clearly contradict it. The model never sees it otherwise.
    """
    if not windows:
        raise MediaError("cannot create an action instruction without frames")
    fps = 1.0 / max(0.001, windows[0]["end"] - windows[0]["start"])
    focus = f" Focus especially on {focus_character!r}." if focus_character else ""
    measured = measured_camera or {}

    frame_table = "\n".join(
        f"  Frame {window['frame']}: t={_fmt_ts(window['start'])}.{int((window['start'] % 1) * 1000):03d}"
        f"–{_fmt_ts(window['end'])}.{int((window['end'] % 1) * 1000):03d}"
        for window in windows
    )
    if measured:
        # Listed after the table, not inside it: an in-row value pulled the
        # description toward "no visible change" (2026-09-25d first A/B).
        measured_list = ", ".join(
            f"Frame {window['frame']}: {measured[int(window['frame'])]}"
            for window in windows if measured.get(int(window["frame"])))
        frame_table += (
            "\n\nMeasured camera motion per frame (instrument reading of the global image "
            f"motion, not a description of the subject):\n  {measured_list}"
        )
    measured_rule = (
        "- The cam= slot of each line is filled from the measured camera motion above: write "
        "that exact word for that frame (push-in stays push-in, never translate or invert it). "
        "Only where it reads 'uncertain' judge the camera from the frames. The measurement says "
        "nothing about the subject: describe subject position, movement and changes from the "
        "frames exactly as you would without it.\n"
        if measured else ""
    )
    if format_h3_beats:
        output_style = (
            "Output format — shot-beat source notes, one entry per listed frame:\n"
            "  Frame N | t=MM:SS.mmm–MM:SS.mmm | cam=<camera motion> | <visible state or visible change>\n"
            "Do not emit bracketed timing blocks: they are not native H3 grammar.\n"
            "State: subject position, head facing, mouth state (open/closed/neutral/unknown), "
            "hand/object contact. "
            "If nothing perceptibly changes write 'no visible change' after the cam= slot."
        )
    else:
        output_style = (
            "Output format — chronological action log, one entry per frame:\n"
            "  Frame N | t=MM:SS.mmm–MM:SS.mmm | cam=<camera motion> | <visible state, exact movement>\n"
            "One line per requested frame in strict order using the exact absolute timestamps below. "
            "Be specific about spatial positions ('frame-left', 'center frame'), body pose, "
            "hand/object contact, facing direction. "
            "Write 'no visible change' after the cam= slot for a frame that holds still."
        )
    return (
        f"You are analyzing {len(windows)} sequential video frames sampled at approximately {fps:.2f} FPS.{focus}\n\n"
        "Exact evidence-window table (the images are in this exact order):\n"
        f"{frame_table}\n\n"
        "Task: produce a dense, second-by-second chronological action log for use in a "
        "MiniMax H3 video generation prompt.\n\n"
        "Rules:\n"
        "- Return exactly one labelled line for every Frame N in the table; do not merge frames.\n"
        "- Only report what is directly visible in the frames.\n"
        "- Never infer audio, dialogue, or off-screen events.\n"
        "- If motion direction is ambiguous between frames, write 'uncertain'.\n"
        "- Camera motion goes in the third slot of EVERY line as cam=<value>, where <value> is "
        "exactly one of: static | push-in | pull-back | pan-left | pan-right | tilt-up | "
        "tilt-down | uncertain. The slot is mandatory even when the camera is still and even "
        "when the rest of the line is 'no visible change'; never omit it and never leave it blank.\n"
        f"{measured_rule}"
        "- Reproduce each Frame N and its t= timestamp exactly as given above.\n\n"
        f"{output_style}"
    )


# The cam= slot vocabulary the instruction above asks for; checked, never inferred.
_CAMERA_MOTION_VALUES = ("static", "push-in", "pull-back", "pan-left", "pan-right",
                         "tilt-up", "tilt-down", "uncertain")
_CAMERA_SLOT_RE = re.compile(r"^\s*frame\s*(\d+)\b[^\n]*?\bcam\s*=\s*([a-z\-]+)", re.I)


def _action_coverage(windows: list[dict], action_log: str) -> dict:
    """Report whether a VLM actually labelled each requested observation.

    This deliberately does *not* manufacture descriptions for missing seconds.
    A caller receives an explicit gap list and can re-run the analysis rather
    than accidentally turning an unsupported summary into a prompt fact.
    """
    references = {int(value) for value in re.findall(r"\bframe\s*(\d+)\b", action_log, re.I)}
    expected = {window["frame"] for window in windows}
    returned = sorted(expected & references)
    missing = sorted(expected - references)
    # Camera-motion slot per line (2026-09-25b). A line without a valid cam=
    # value gets no camera claim: the field is reported missing, never filled.
    camera: dict[int, str] = {}
    invalid: dict[int, str] = {}
    for line in action_log.splitlines():
        match = _CAMERA_SLOT_RE.match(line)
        if not match:
            continue
        frame, value = int(match.group(1)), match.group(2).lower()
        if frame not in expected or frame in camera:
            continue
        if value in _CAMERA_MOTION_VALUES:
            camera[frame] = value
        else:
            invalid[frame] = value
    missing_camera = sorted(expected - set(camera))
    warnings = []
    if missing:
        warnings.append(
            "The model did not label every requested observation window. Missing "
            "windows contain no inferred action; re-run the analysis if that detail is needed."
        )
    if missing_camera:
        warnings.append(
            "Camera motion is unknown for the listed windows (no valid cam= slot); do not "
            "write a camera move for them into a prompt."
        )
    return {
        "expected_frame_labels": len(windows),
        "returned_frame_labels": returned,
        "missing_frame_labels": missing,
        "complete": not missing,
        "camera_labels": {str(frame): camera[frame] for frame in sorted(camera)},
        "invalid_camera_labels": {str(frame): invalid[frame] for frame in sorted(invalid)},
        "missing_camera_labels": missing_camera,
        "camera_complete": not missing_camera,
        "warning": " ".join(warnings) if warnings else None,
    }


# Each 768px frame encodes to ~1000–1500 visual tokens in Qwen2.5-VL. At
# 16384 ctx the model silently truncated after ~13 frames. At 32768 ctx
# (passed explicitly from extract_video_actions) 20 frames fit with margin.
_ACTION_BATCH_SIZE = 20


def extract_video_actions(args: dict) -> str:
    p = _path(args.get("video_path"), VIDEO_EXTS)
    fps = float(args.get("fps", 1.0))
    if fps <= 0 or fps > 2.0:
        raise MediaError("fps must be between 0 and 2.0")
    format_h3_beats = bool(args.get("format_h3_beats", False))
    focus_character = str(args.get("focus_character", "")).strip() or None

    # Check model before touching the GPU or filesystem.
    try:
        model, vram_need_mb = caps.action_model(router.GPU_HOST)
    except RuntimeError as exc:
        return json.dumps({
            "available": False,
            "reason": str(exc),
            "install": "Run local_agent\\setup_qwen25_vl_caption.ps1.",
        }, indent=2)

    # Only the watcher creates a direct-Qwen runtime. Outside that batch this
    # request queues rather than forcibly taking VRAM from chat.
    free_mb = router.gpu_free_mb()
    owned, owner_reason = router.queue_owner()
    render_active = owned or router.comfy_listening()
    direct_qwen = model == caps.QWEN25_VL_MODEL and caps.qwen25_vl_runtime_available()
    need = vram_need_mb + caps.VRAM_SAFETY_MB
    # Once the watcher has loaded its own Qwen runtime, free VRAM naturally
    # reflects that model's 8 GB allocation.  Requiring another 9 GB at this
    # point rejects the exact runtime that passed the pre-load gate and loops
    # the job back into the queue.  The pre-load watcher gate remains the only
    # place that decides whether the model can be started.
    if render_active or not direct_qwen:
        import media_queue as mq
        job_args = dict(args, video_path=str(p))
        reused = _completed_reuse("video_action", job_args, str(p))
        if reused:
            return reused
        job = mq.enqueue("video_action", job_args, priority="interactive", source=str(p))
        reason = (owner_reason if owned else "ComfyUI is listening on port 8188") if render_active else \
            f"insufficient VRAM ({free_mb} MB free, {need} MB needed)"
        return json.dumps({
            "queued": True,
            "reason": reason,
            "job_id": job["id"],
            "free_mb": free_mb,
            "message": ("Video action extraction queued. "
                        "The background watcher will run it when the GPU is free."),
        }, indent=2)

    duration = _duration(p)

    # Extract frames to a temporary folder; always clean up on exit.
    import uuid as _uuid
    frame_dir = UPLOADS / f"tmp_frames_{_uuid.uuid4().hex[:12]}"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frame_pattern = str(frame_dir / "frame_%04d.jpg")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(p),
             "-vf", f"fps={fps},scale=768:-1",
             "-q:v", "3", frame_pattern],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode:
            raise MediaError(r.stderr.strip() or "ffmpeg frame extraction failed")

        frames = sorted(frame_dir.glob("frame_*.jpg"))
        if not frames:
            raise MediaError("no frames extracted from video")

        all_logs: list[str] = []
        all_windows: list[dict] = _action_windows(len(frames), fps, duration)
        # Measured camera motion per window (CPU, deterministic; 2026-09-25c),
        # computed first so the VLM's frame table can carry it (2026-09-25d).
        # Never fails the tool: an estimator error is reported, not raised.
        try:
            import camera_motion
            camera = camera_motion.estimate_camera_motion(p, all_windows, fps=None)
            camera_error = None
        except Exception as exc:  # pragma: no cover - depends on ffmpeg/file state
            camera, camera_error = [], f"{type(exc).__name__}: {exc}"
        measured_labels = {int(c["frame"]): str(c["camera"]) for c in camera}
        for batch_start in range(0, len(frames), _ACTION_BATCH_SIZE):
            _raise_if_preempted(args)
            _set_progress(args, "analyzing action frames", batch_start, len(frames))
            batch = frames[batch_start:batch_start + _ACTION_BATCH_SIZE]
            instruction = _action_frame_instruction(
                all_windows[batch_start:batch_start + len(batch)],
                focus_character, format_h3_beats, measured_camera=measured_labels)
            result = json.loads(_run_vision_gpu(
                batch, "", model=model, host=router.GPU_HOST,
                instruction=instruction, num_ctx=32768,
                # Off, deliberately. The action log is a fixed per-line format
                # whose required fields repeat on every line (camera motion,
                # "no visible change"); a repeat penalty makes those tokens
                # cheaper to drop. Measured 2026-09-25a on 8 labeled clips:
                # lines carrying the camera-motion field 51% at 1.0 vs 19% at
                # 1.08 (noisy, all-or-nothing per clip), no truncation and
                # full frame-label coverage either way. 1.0 is what this call
                # ran at until 2026-09-24ae forwarded the parameter.
                repeat_penalty=1.0,
            ))
            if result.get("available"):
                all_logs.append(result["analysis"])
            else:
                all_logs.append(f"[batch failed: {result.get('reason', 'unknown')}]")

        action_log = "\n".join(all_logs)
        coverage = _action_coverage(all_windows, action_log)
        camera_vs_model = (camera_motion.compare_with_claims(camera, coverage["camera_labels"])
                           if camera else None)
        return json.dumps({
            "source": str(p),
            "duration": round(duration, 3),
            "fps": fps,
            "frame_count": len(frames),
            "model": model,
            "format_h3_beats": format_h3_beats,
            "focus_character": focus_character,
            "observation_windows": all_windows,
            "action_log": action_log,
            "coverage": coverage,
            "camera_motion": camera,
            "camera_motion_vs_model": camera_vs_model,
            "camera_motion_error": camera_error,
            "note": ("Use action_log only for the labelled observation windows. Entries marked "
                     "'uncertain', 'no visible change', or missing from coverage are not evidence "
                     "of motion and must not be written into a prompt as action beats. "
                     "coverage.camera_labels are the model's per-frame cam= claims, present on "
                     "every line since 2026-09-25b; measured on 8 clips they were 'static' for "
                     "every frame including an aerial follow shot, so cam=static means no camera "
                     "move was claimed, not that a locked-off camera was observed. "
                     "camera_motion is measured from the pixels (global translation and scale "
                     "per window, camera_motion.py); prefer it over the model's claim. It reads "
                     "global image motion, so a subject filling the frame or flowing water can "
                     "register as a camera move; 'uncertain' means no usable estimate. Since "
                     "2026-09-25d the model sees the measured value in its frame table, so "
                     "cam= agreeing with camera_motion is expected, not independent confirmation."),
        }, indent=2, ensure_ascii=False)
    finally:
        import shutil as _shutil
        _shutil.rmtree(frame_dir, ignore_errors=True)


def compare_voice(args: dict) -> str:
    a = _path(args.get("a"), AUDIO_EXTS | VIDEO_EXTS)
    b = _path(args.get("b"), AUDIO_EXTS | VIDEO_EXTS)
    cap = caps.capability("voice_compare")
    return json.dumps({"a": str(a), "b": str(b), **cap}, indent=2)
