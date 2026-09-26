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
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCAL_AGENT = ROOT / "local_agent"
LOG_DIR = LOCAL_AGENT / "runtime" / "logs"
AUDIT_LOG = LOG_DIR / "watcher_audit.log"
PID_FILE = LOG_DIR / "gvd_watcher.pid"
PROGRESS_PATH = LOCAL_AGENT / "runtime" / "gvd_backrooms_batch" / "progress.json"
BATCH_SCRIPT = ROOT / "batch_run_backrooms_gvd.py"
DEFAULT_PYTHON = Path(
    os.environ.get(
        "GVD_PYTHON",
        r"A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe",
    )
)
COMFY_URL = os.environ.get("GVD_COMFY_URL", "http://127.0.0.1:8188")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

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


def already_done(entry: dict | None) -> bool:
    if not isinstance(entry, dict):
        return False
    status = str(entry.get("status") or "").lower()
    if status in {"done", "ok", "success"}:
        return True
    if entry.get("ok") is True and entry.get("video_path"):
        return True
    return False


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


def acquire_pid_lock() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if PID_FILE.is_file():
        try:
            old = int(PID_FILE.read_text(encoding="utf-8").strip().split()[0])
        except Exception:
            old = 0
        if old and _pid_alive(old):
            raise SystemExit(f"Another gvd_watcher is alive (pid={old}). Refusing second instance.")
    PID_FILE.write_text(str(os.getpid()) + "\n", encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        # Windows: OpenProcess via tasklist is simpler
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True,
            timeout=10,
            creationflags=CREATE_NO_WINDOW,
        )
        return str(pid) in out and "No tasks" not in out
    except Exception:
        return False


def release_pid_lock() -> None:
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


def run_clip(
    cid: str,
    *,
    python: Path,
    silent: bool = False,
    force: bool = False,
    timeout_s: float = 7200.0,
) -> tuple[int, str, float]:
    cmd = [str(python), "-u", str(BATCH_SCRIPT), "--clip", cid]
    if silent:
        cmd.append("--silent-fallback")
    if force:
        cmd.append("--force")
    audit("clip_start", clip=cid, silent=silent, cmd=" ".join(cmd), **sample_vram())
    t0 = time.time()
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
    try:
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                chunks.append(line)
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except UnicodeEncodeError:
                    safe = line.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace")
                    sys.stdout.write(safe)
                    sys.stdout.flush()
                with AUDIT_LOG.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"ts": _now(), "event": "stdout", "clip": cid, "line": line.rstrip("\n")}, ensure_ascii=False) + "\n")
            if time.time() - t0 > timeout_s:
                proc.kill()
                chunks.append("\n[watcher] TIMEOUT killed subprocess\n")
                break
    finally:
        try:
            proc.wait(timeout=30)
        except Exception:
            proc.kill()
    elapsed = time.time() - t0
    blob = "".join(chunks)
    rc = int(proc.returncode if proc.returncode is not None else 1)
    audit(
        "clip_end",
        clip=cid,
        rc=rc,
        elapsed_sec=round(elapsed, 1),
        silent=silent,
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
    p.add_argument("--force-rerun-failed", action="store_true", help="Retry error/qa_failed clips")
    p.add_argument("--force-all", action="store_true", help="Force every selected clip (dangerous)")
    p.add_argument("--python", type=Path, default=DEFAULT_PYTHON)
    p.add_argument("--timeout", type=float, default=7200.0, help="Per-clip seconds")
    return p


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

    # Ensure rules lock exists up front
    try:
        sys.path.insert(0, str(LOCAL_AGENT))
        import gvd_pipeline_rules as rules

        lock = rules.write_rules_lock()
        audit("rules_lock", path=str(lock))
    except Exception as exc:
        audit("rules_lock_error", error=str(exc))

    progress = load_progress()
    clips = iter_clip_ids(args.start_from, 0, args.clip or None)
    plan: list[str] = []
    for cid in clips:
        entry = (progress.get("clips") or {}).get(cid)
        if already_done(entry) and not args.force_all:
            continue
        status = str((entry or {}).get("status") or "").lower()
        if status == "running" and not already_done(entry):
            # Stale mid-run marker (watcher/crash) — retry
            plan.append(cid)
            continue
        if status in {"error", "qa_failed", "failed"}:
            # default: retry failed clips under watcher
            plan.append(cid)
            continue
        if already_done(entry):
            continue
        plan.append(cid)
    if args.limit and args.limit > 0:
        plan = plan[: args.limit]

    audit(
        "plan",
        total_planned=len(plan),
        first=plan[0] if plan else None,
        last=plan[-1] if plan else None,
        skipped_done=sum(1 for c in clips if already_done((progress.get("clips") or {}).get(c))),
        dry_run=bool(args.dry_run),
    )

    if args.dry_run:
        for cid in plan:
            print(f"DRY would run {cid}")
        print(f"Dry-run plan size={len(plan)}")
        return 0

    acquire_pid_lock()
    ok = failed = 0
    try:
        for cid in plan:
            force = bool(args.force_all or args.force_rerun_failed)
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