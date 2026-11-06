#!/usr/bin/env python3
"""GVD Watcher Daemon — supervise Backrooms 102-clip batch_run_backrooms_gvd.py.

Launches each clip as a monitored subprocess, audits stdout/stderr + VRAM,
self-heals audio/auth failures via --silent-fallback, and flushes Comfy VRAM
between clips.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# GVD_ROOT: repo root override (defaults to this file's directory, i.e. the checkout).
ROOT = Path(os.environ.get("GVD_ROOT") or Path(__file__).resolve().parent).resolve()
LOCAL_AGENT = ROOT / "local_agent"
LOG_DIR = LOCAL_AGENT / "runtime" / "logs"
AUDIT_LOG = LOG_DIR / "watcher_audit.log"
PID_FILE = LOG_DIR / "gvd_watcher.pid"
PROGRESS_PATH = LOCAL_AGENT / "runtime" / "gvd_backrooms_batch" / "progress.json"
BATCH_SCRIPT = ROOT / "batch_run_backrooms_gvd.py"
# GVD_PYTHON overrides; otherwise the interpreter running this watcher (the
# keepalive launches both with the same python.exe).
DEFAULT_PYTHON = Path(os.environ.get("GVD_PYTHON") or sys.executable)
COMFY_URL = os.environ.get("GVD_COMFY_URL", "http://127.0.0.1:8188")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

for _p in (str(ROOT), str(LOCAL_AGENT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ONE finished-clip vocabulary, shared with the batch (and mirrored by the keepalive).
from batch_run_backrooms_gvd import already_done, is_failed  # noqa: E402
from gpu_lock import GpuLock, GpuLockHeld  # noqa: E402
import gpu_lock as _gpu_lock  # noqa: E402

AUDIO_AUTH_RE = re.compile(
    r"Unauthorized|Please login first|InstantVoiceClone|FishAudio|F5TTS|login first|401|403",
    re.I,
)
OOM_RE = re.compile(r"CUDA out of memory|torch\.OutOfMemoryError|out of memory", re.I)
NODE_RE = re.compile(
    r"HTTP\s*400|node class|class_type.*(not found|unknown)|Prompt outputs failed validation",
    re.I,
)
TIMEOUT_RE = re.compile(r"timed?\s*out|TimeoutError|Read timed out|Connection refused", re.I)

FORCE_ALL_WARNING = (
    "!!! --force-all RE-RENDERS EVERY CLIP, INCLUDING SELECTED ONES, AND REPLACES "
    "THEIR video_path. Prior evidence is kept in progress.json attempts[], but the "
    "SELECTED outputs will be superseded. Pass --yes-overwrite-selected to confirm. !!!"
)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def audit(event: str, **fields) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    row = {"ts": _now(), "event": event, **fields}
    line = json.dumps(row, ensure_ascii=False)
    with AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(f"[watcher] {event} " + " ".join(f"{k}={v}" for k, v in fields.items() if k != "tail"), flush=True)


def load_progress() -> dict:
    if PROGRESS_PATH.is_file():
        try:
            return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"clips": {}}


def sample_vram() -> dict:
    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW,
        )
        used, util, temp = [float(x.strip()) for x in raw.splitlines()[0].split(",")]
        return {"vram_mib": used, "gpu_util": util, "temp_c": temp}
    except Exception as exc:
        return {"vram_error": str(exc)}


def comfy_free() -> bool:
    body = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
    req = urllib.request.Request(
        COMFY_URL.rstrip("/") + "/free",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        return True
    except Exception as exc:
        audit("comfy_free_error", error=str(exc))
        return False


def torch_empty_cache() -> None:
    py = str(DEFAULT_PYTHON if DEFAULT_PYTHON.is_file() else sys.executable)
    try:
        subprocess.run(
            [py, "-c", "import torch; torch.cuda.empty_cache() if torch.cuda.is_available() else None"],
            timeout=30,
            creationflags=CREATE_NO_WINDOW,
            check=False,
            capture_output=True,
        )
    except Exception:
        pass


def post_clip_sanitize() -> None:
    ok = comfy_free()
    torch_empty_cache()
    time.sleep(2.0)
    audit("vram_flush", comfy_free=ok, **sample_vram())


# --- GPU / instance lock -----------------------------------------------------
# The watcher holds the SHARED render lock (gpu_lock.py: OS file lock + owner
# JSON) for the whole batch, so master_batch_runner / backrooms_watch cannot
# submit GPU work next to it, and a second gvd_watcher is refused.  The old
# check-then-write PID file is kept only as an informational marker.
_LOCK: GpuLock | None = None
LOCK_PATH = _gpu_lock.DEFAULT_LOCK_PATH
OWNER_PATH = _gpu_lock.DEFAULT_OWNER_PATH


def _pid_alive(pid: int) -> bool | str:
    """True / False / "unknown".  "unknown" (tasklist or psutil failed) must be
    treated as ALIVE by any lock logic: unknown never steals the lock."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    alive = _gpu_lock.pid_alive(pid)
    if alive is None:
        return "unknown"
    return bool(alive)


def acquire_pid_lock() -> GpuLock:
    global _LOCK
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    lock = GpuLock(
        "gvd_watcher", purpose="Backrooms GVD batch (gvd_watcher)",
        lock_path=LOCK_PATH, owner_path=OWNER_PATH,
    )
    try:
        lock.acquire()
    except GpuLockHeld as exc:
        owner = exc.owner or {}
        raise SystemExit(
            f"Another renderer holds the GPU lock (pid={owner.get('pid')} holder={owner.get('holder')} "
            f"liveness={_pid_alive(owner.get('pid') or 0)}). Refusing second instance."
        ) from exc
    _LOCK = lock
    try:
        PID_FILE.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    except Exception:
        pass
    return lock


def release_pid_lock() -> None:
    global _LOCK
    try:
        if _LOCK is not None:
            _LOCK.release()
    finally:
        _LOCK = None
    try:
        if PID_FILE.is_file():
            cur = PID_FILE.read_text(encoding="utf-8").strip().split()[0]
            if cur == str(os.getpid()):
                PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def classify_failure(blob: str) -> str | None:
    if OOM_RE.search(blob):
        return "oom"
    if AUDIO_AUTH_RE.search(blob):
        return "audio_auth"
    if NODE_RE.search(blob):
        return "missing_node"
    if TIMEOUT_RE.search(blob):
        return "timeout"
    return None


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        import psutil  # type: ignore

        try:
            parent = psutil.Process(proc.pid)
            kids = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            kids = []
        for k in kids:
            try:
                k.kill()
            except Exception:
                pass
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _pump_stdout(stream, out_q: "queue.Queue[str | None]") -> None:
    """Reader thread: push each child line onto the queue; None = EOF."""
    try:
        for line in iter(stream.readline, ""):
            out_q.put(line)
    except Exception:
        pass
    finally:
        out_q.put(None)


def run_clip(
    cid: str,
    *,
    python: Path,
    silent: bool = False,
    force: bool = False,
    timeout_s: float = 7200.0,
    poll_s: float = 1.0,
) -> tuple[int, str, float]:
    cmd = [str(python), "-u", str(BATCH_SCRIPT), "--clip", cid]
    if silent:
        cmd.append("--silent-fallback")
    if force:
        cmd.append("--force")
    audit("clip_start", clip=cid, silent=silent, cmd=" ".join(cmd), **sample_vram())
    t0 = time.monotonic()
    child_env = dict(os.environ)
    # Fish InstantVoiceClone needs Comfy login; default skip so batch does not stall on Unauthorized.
    # C001 MiniMax-native and minimax_ref2vid paths do not depend on GVD_F5_TTS.
    child_env.setdefault("GVD_F5_TTS", "0")
    child_env.setdefault("PYTHONUTF8", "1")
    child_env.setdefault("PYTHONIOENCODING", "utf-8")
    if silent:
        child_env["GVD_F5_TTS"] = "0"
        child_env["GVD_SILENT_FALLBACK"] = "1"
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=CREATE_NO_WINDOW,
        env=child_env,
    )
    chunks: list[str] = []
    assert proc.stdout is not None
    # stdout is drained on a thread so the timeout below is honoured even while
    # the child is completely silent (a blocking readline() never returned).
    out_q: "queue.Queue[str | None]" = queue.Queue()
    reader = threading.Thread(target=_pump_stdout, args=(proc.stdout, out_q), daemon=True)
    reader.start()
    timed_out = False
    eof = False
    try:
        while True:
            try:
                line = out_q.get(timeout=poll_s)
            except queue.Empty:
                line = ""
            if line is None:
                eof = True
            elif line:
                chunks.append(line)
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except UnicodeEncodeError:
                    enc = sys.stdout.encoding or "utf-8"
                    safe = line.encode(enc, errors="replace").decode(enc, errors="replace")
                    sys.stdout.write(safe)
                    sys.stdout.flush()
                with AUDIT_LOG.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"ts": _now(), "event": "stdout", "clip": cid, "line": line.rstrip("\n")}, ensure_ascii=False) + "\n")
            if eof and proc.poll() is not None:
                break
            if eof and out_q.empty():
                # pipe closed; give the process a moment to exit
                try:
                    proc.wait(timeout=poll_s)
                except subprocess.TimeoutExpired:
                    pass
            if time.monotonic() - t0 > timeout_s:
                timed_out = True
                _kill_tree(proc)
                chunks.append(f"\n[watcher] TIMEOUT ({timeout_s:.0f}s) killed subprocess\n")
                audit("clip_timeout", clip=cid, timeout_s=timeout_s)
                break
    finally:
        try:
            proc.wait(timeout=30)
        except Exception:
            _kill_tree(proc)
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
        reader.join(timeout=5)
        # drain anything the reader pushed after we stopped consuming
        while True:
            try:
                tail = out_q.get_nowait()
            except queue.Empty:
                break
            if tail:
                chunks.append(tail)
    elapsed = time.monotonic() - t0
    blob = "".join(chunks)
    rc = int(proc.returncode if proc.returncode is not None else 1)
    if timed_out and rc == 0:
        rc = 124
    audit(
        "clip_end",
        clip=cid,
        rc=rc,
        elapsed_sec=round(elapsed, 1),
        silent=silent,
        timed_out=timed_out,
        sig=classify_failure(blob),
        **sample_vram(),
    )
    return rc, blob, elapsed


def iter_clip_ids(start_from: str = "", limit: int = 0, only: list[str] | None = None) -> list[str]:
    if only:
        return [c.upper() for c in only]
    ids = [f"C{i:03d}" for i in range(1, 103)]
    if start_from:
        sf = start_from.strip().upper()
        if sf in ids:
            ids = ids[ids.index(sf) :]
    if limit and limit > 0:
        ids = ids[:limit]
    return ids


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Supervise Backrooms GVD batch clips.")
    p.add_argument("--start-from", default="", help="First clip id inclusive (e.g. C008)")
    p.add_argument("--limit", type=int, default=0, help="Max clips to attempt (0=all remaining)")
    p.add_argument("--clip", action="append", default=[], help="Explicit clip id(s)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--force-rerun-failed",
        action="store_true",
        help="Pass --force to the batch ONLY for clips whose entry is error/failed/qa_failed",
    )
    p.add_argument(
        "--force-all",
        action="store_true",
        help="Re-render EVERY clip including SELECTED ones (dangerous; needs --yes-overwrite-selected)",
    )
    p.add_argument(
        "--yes-overwrite-selected",
        action="store_true",
        help="Required confirmation for --force-all",
    )
    p.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    p.add_argument("--timeout", type=float, default=7200.0, help="Per-clip seconds")
    return p


def build_plan(progress: dict, clips: list[str], *, force_all: bool, force_rerun_failed: bool) -> list[tuple[str, bool]]:
    """Return [(clip_id, force)] for this run.

    * SELECTED/done clips are skipped unless --force-all.
    * --force-rerun-failed forces ONLY clips whose entry is error/failed/qa_failed.
    * stale "running" markers and never-run clips are planned without --force.
    """
    entries = progress.get("clips") or {}
    plan: list[tuple[str, bool]] = []
    for cid in clips:
        entry = entries.get(cid)
        done = already_done(entry)
        failed = is_failed(entry)
        if force_all:
            plan.append((cid, True))
            continue
        if done:
            continue
        plan.append((cid, bool(force_rerun_failed and failed)))
    return plan


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = build_argparser().parse_args(argv)
    python = Path(args.python)
    if not python.is_file():
        python = Path(sys.executable)

    if args.force_all:
        print(FORCE_ALL_WARNING, file=sys.stderr, flush=True)
        audit("force_all_requested", confirmed=bool(args.yes_overwrite_selected))
        if not args.yes_overwrite_selected:
            print("Refusing --force-all without --yes-overwrite-selected.", file=sys.stderr, flush=True)
            return 2

    # Ensure rules lock exists up front
    try:
        import gvd_pipeline_rules as rules

        lock = rules.write_rules_lock()
        audit("rules_lock", path=str(lock))
    except Exception as exc:
        audit("rules_lock_error", error=str(exc))

    progress = load_progress()
    clips = iter_clip_ids(args.start_from, 0, args.clip or None)
    plan = build_plan(
        progress, clips, force_all=bool(args.force_all), force_rerun_failed=bool(args.force_rerun_failed)
    )
    if args.limit and args.limit > 0:
        plan = plan[: args.limit]

    audit(
        "plan",
        total_planned=len(plan),
        forced=sum(1 for _, f in plan if f),
        first=plan[0][0] if plan else None,
        last=plan[-1][0] if plan else None,
        skipped_done=sum(1 for c in clips if already_done((progress.get("clips") or {}).get(c))),
        dry_run=bool(args.dry_run),
    )

    if args.dry_run:
        for cid, force in plan:
            print(f"DRY would run {cid}" + (" (--force)" if force else ""))
        print(f"Dry-run plan size={len(plan)}")
        return 0

    acquire_pid_lock()
    ok = failed = 0
    try:
        for cid, force in plan:
            # First attempt (normal audio path)
            rc, blob, _elapsed = run_clip(cid, python=python, silent=False, force=force, timeout_s=args.timeout)
            sig = classify_failure(blob)
            progress = load_progress()
            entry = (progress.get("clips") or {}).get(cid) or {}
            success = rc == 0 and already_done(entry)

            if (not success) and sig == "oom":
                audit("heal_oom", clip=cid)
                post_clip_sanitize()
                time.sleep(5)
                rc, blob, _ = run_clip(cid, python=python, silent=False, force=True, timeout_s=args.timeout)
                progress = load_progress()
                entry = (progress.get("clips") or {}).get(cid) or {}
                success = rc == 0 and already_done(entry)
                sig = classify_failure(blob)

            if (not success) and sig in {"audio_auth", "missing_node"}:
                audit("heal_silent_fallback", clip=cid, sig=sig)
                post_clip_sanitize()
                rc, blob, _ = run_clip(cid, python=python, silent=True, force=True, timeout_s=args.timeout)
                progress = load_progress()
                entry = (progress.get("clips") or {}).get(cid) or {}
                success = rc == 0 and already_done(entry)

            post_clip_sanitize()

            if success:
                ok += 1
                audit("clip_ok", clip=cid, video=entry.get("video_path"))
            else:
                failed += 1
                audit("clip_failed", clip=cid, rc=rc, sig=classify_failure(blob), error=entry.get("error"))
                # continue — never halt the multi-hour batch
        audit("batch_done", ok=ok, failed=failed)
        return 0 if failed == 0 else 1
    finally:
        release_pid_lock()


if __name__ == "__main__":
    raise SystemExit(main())
