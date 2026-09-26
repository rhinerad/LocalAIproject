#!/usr/bin/env python3
"""Background watcher: drain the media GPU queue when the GPU is free.

    python local_agent/media_watcher.py          # continuous, polls every 15 s
    python local_agent/media_watcher.py --once   # one pass, then exit

Single-instance lock: local_agent/media_queue/watcher_owner.json holds the
watcher PID. A second instance that finds a live PID exits immediately.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from atomic_io import atomic_write_text
import capabilities as caps
import media_queue as mq
import media_tools
import router

POLL_SECONDS = 15
OWNER_FILE = HERE / "media_queue" / "watcher_owner.json"


def _claim() -> bool:
    OWNER_FILE.parent.mkdir(parents=True, exist_ok=True)
    if OWNER_FILE.is_file():
        try:
            d = json.loads(OWNER_FILE.read_text(encoding="utf-8"))
            if router._pid_alive(int(d.get("pid", 0) or 0)):
                return False
        except Exception:
            pass
    atomic_write_text(OWNER_FILE, json.dumps({"pid": os.getpid()}))
    return True


def _release() -> None:
    try:
        OWNER_FILE.unlink()
    except Exception:
        pass


def _prepare_vision_batch() -> dict | None:
    """Apply router's sole VRAM plan, then lazily load the VLM for this batch.

    Pressure is asserted on downgrade/evict *before* the VLM is proven up.
    Every failed/no-op return (``None``) clears the flag so a start miss
    cannot leak ``media_vram_pressure.json`` (2026-09-05dw). A successful
    return leaves the flag for ``_release_vision_batch``.
    """
    ready = False
    try:
        tier, action = router.plan_vision_vram(
            caps.vision_tiers(router.GPU_HOST, include_unloaded=True))
        if tier is None:
            return None
        if action == "downgrade":
            router.set_media_pressure(True)
            router.unload(router.GPU_HOST, router.PRIMARY_REASONING_MODEL)
        elif action == "evict":
            router.set_media_pressure(True)
            for model in router._running_models(router.GPU_HOST) or []:
                router.unload(router.GPU_HOST, model)
        # Re-check after a reclaim. A model server can take a moment to return VRAM;
        # never assume an unload succeeded and never start the VLM on blind faith.
        free_mb = router.gpu_free_mb()
        need_mb = int(tier["vram_need_mb"]) + caps.VRAM_SAFETY_MB
        if free_mb is None or free_mb < need_mb:
            return None
        if tier.get("model") == caps.QWEN25_VL_MODEL:
            if not caps.ensure_qwen25_vl_runtime():
                return None
            tier = dict(tier)
            tier["runtime"] = "llama.cpp"
        ready = True
        return tier
    finally:
        if not ready:
            router.set_media_pressure(False)


def _action_model_ready() -> bool:
    """True when the configured Qwen2.5-VL action model fits and no render runs."""
    if _render_active():
        return False
    if caps.qwen25_vl_runtime_available():
        return True
    free_mb = router.gpu_free_mb()
    if free_mb is None:
        return False
    return free_mb >= caps.MINICPM_VRAM_MB + caps.VRAM_SAFETY_MB


def _render_active() -> bool:
    """Only a real Equal Shares/ComfyUI render blocks queued media work."""
    owned, _ = router.queue_owner()
    return owned or router.comfy_listening()


def _interrupt_reason(job_id: str) -> str:
    if mq.cancel_requested(job_id):
        return "cancelled by operator"
    if _render_active():
        return "pre-empted by render"
    return ""


def _finish_interrupt(job_id: str, reason: str) -> None:
    if reason == "cancelled by operator":
        mq.finish_cancel(job_id, reason)
    else:
        mq.requeue(job_id, reason)


def _progress_with_pressure(job_id: str):
    def _inner(stage, done, total):
        router.refresh_media_pressure()
        mq.set_progress(job_id, stage, done, total)
    return _inner


def _release_vision_batch() -> bool:
    """Release only a VLM process this watcher can prove it owns.

    A listener already present on the exact VLM port may have been launched by
    an operator or another approved process. The capability layer intentionally
    refuses to terminate an unowned PID; reporting that as a release made the
    GPU status misleading. Keep media pressure accurate either way.
    """
    released = caps.release_qwen25_vl_runtime()
    router.set_media_pressure(False)
    if released:
        print("[watcher] released owned Qwen2.5-VL after media batch")
    else:
        print("[watcher] exact Qwen2.5-VL remains resident (not bridge-owned); GPU stays reserved")
    return released


def _run_vision_job(job: dict, tier: dict) -> None:
    router.refresh_media_pressure()
    job_id = job["id"]
    args = job.get("args") or {}
    try:
        interrupt = _interrupt_reason(job_id)
        if interrupt:
            _finish_interrupt(job_id, interrupt)
            print(f"[watcher] {interrupt} {job_id} vision")
            return
        mq.set_progress(job_id, "analyzing")
        images = [Path(p) for p in (args.get("images") or []) if Path(p).is_file()]
        if not images:
            raise ValueError("no valid image paths in queued job")
        question = str(args.get("question") or "")
        instruction = args.get("instruction")
        result = media_tools._run_vision_gpu(
            images, question, tier["model"], router.GPU_HOST, instruction)
        interrupt = _interrupt_reason(job_id)
        if interrupt:
            _finish_interrupt(job_id, interrupt)
            print(f"[watcher] {interrupt} {job_id} vision")
        else:
            mq.complete(job_id, result)
            print(f"[watcher] done    {job_id} vision ({tier['label']})")
    except Exception as exc:
        mq.fail(job_id, str(exc))
        print(f"[watcher] failed  {job_id} vision: {exc}")


def _run_analyze_video_job(job: dict) -> None:
    router.refresh_media_pressure()
    job_id = job["id"]
    args = dict(job.get("args") or {})
    args["__preempt_check"] = lambda: _interrupt_reason(job_id)
    args["__progress_update"] = _progress_with_pressure(job_id)
    try:
        result = media_tools.analyze_video(args)
        parsed = json.loads(result)
        if parsed.get("queued"):
            _finish_interrupt(job_id, _interrupt_reason(job_id) or "GPU busy when watcher attempted to run")
        else:
            mq.complete(job_id, result)
            print(f"[watcher] done    {job_id} analyze_video")
    except media_tools.MediaPreempted as exc:
        _finish_interrupt(job_id, str(exc))
        print(f"[watcher] {exc} {job_id} analyze_video")
    except Exception as exc:
        mq.fail(job_id, str(exc))
        print(f"[watcher] failed  {job_id} analyze_video: {exc}")


def _run_video_action_job(job: dict) -> None:
    router.refresh_media_pressure()
    job_id = job["id"]
    args = dict(job.get("args") or {})
    args["__preempt_check"] = lambda: _interrupt_reason(job_id)
    args["__progress_update"] = _progress_with_pressure(job_id)
    try:
        result = media_tools.extract_video_actions(args)
        parsed = json.loads(result)
        if parsed.get("queued"):
            _finish_interrupt(job_id, _interrupt_reason(job_id) or "GPU busy when watcher attempted to run")
        else:
            mq.complete(job_id, result)
            print(f"[watcher] done    {job_id} video_action")
    except media_tools.MediaPreempted as exc:
        _finish_interrupt(job_id, str(exc))
        print(f"[watcher] {exc} {job_id} video_action")
    except Exception as exc:
        mq.fail(job_id, str(exc))
        print(f"[watcher] failed  {job_id} video_action: {exc}")


def _run_transcribe_job(job: dict) -> None:
    job_id = job["id"]
    args = job.get("args") or {}
    try:
        if _interrupt_reason(job_id):
            _finish_interrupt(job_id, _interrupt_reason(job_id))
            return
        mq.set_progress(job_id, "transcribing")
        result = media_tools.transcribe_direct(args)
        interrupt = _interrupt_reason(job_id)
        if interrupt:
            _finish_interrupt(job_id, interrupt)
        else:
            mq.complete(job_id, result)
            print(f"[watcher] done    {job_id} transcribe")
    except Exception as exc:
        mq.fail(job_id, str(exc))
        print(f"[watcher] failed  {job_id} transcribe: {exc}")


def run_once() -> int:
    """Process all jobs that can run right now. Returns count processed."""
    n = 0

    # Do not even consider loading the VLM unless an actual GPU sensory job is
    # pending.  The watcher itself must be idle-cheap.
    pending = mq.list_queue().get("pending", [])
    needs_vision = any(j.get("kind") in {"vision", "analyze_video", "video_action"}
                       for j in pending)
    # One reclaim window drains every GPU sensory job, then releases the VLM.
    tier = _prepare_vision_batch() if needs_vision else None
    if tier is not None:
        try:
            while True:
                job = mq.claim_next(kind="vision")
                if job is None:
                    break
                _run_vision_job(job, tier)
                n += 1
                if _render_active():
                    break

            while True:
                job = mq.claim_next(kind="analyze_video")
                if job is None:
                    break
                _run_analyze_video_job(job)
                n += 1
                if _render_active():
                    break

            while not _render_active():
                job = mq.claim_next(kind="video_action")
                if job is None:
                    break
                _run_video_action_job(job)
                n += 1
        finally:
            # Always drop the flag after this reclaim window, even if no
            # job was claimed (queue raced empty after a successful start).
            _release_vision_batch()

    # Transcribe jobs: run when no active render (Whisper is CPU-only).
    # A resident vision server must not hold this queue hostage.
    if not _render_active():
        while True:
            job = mq.claim_next(kind="transcribe")
            if job is None:
                break
            _run_transcribe_job(job)
            n += 1

    return n


def main() -> int:
    once = "--once" in sys.argv
    if not _claim():
        print("[watcher] another watcher instance is already running — exiting")
        return 0
    try:
        stale = mq.recover_stale()
        if stale:
            print(f"[watcher] recovered {stale} stale processing job(s) → pending")
        if once:
            n = run_once()
            print(f"[watcher] --once: processed {n} job(s)")
            return 0
        print(f"[watcher] polling every {POLL_SECONDS}s — Ctrl-C to stop")
        while True:
            try:
                run_once()
            except Exception as exc:
                print(f"[watcher] poll error: {exc}")
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("\n[watcher] stopped")
    finally:
        _release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
