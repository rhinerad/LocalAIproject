#!/usr/bin/env python3
"""Shared cross-process GPU/render lock for every batch runner on this workstation.

Extracted from ``backrooms_watch.BackroomsWatch.acquire()`` (the only runner
that had a correct lock) so ``gvd_watcher.py``, ``master_batch_runner.py``,
``backrooms_watch.py`` and ``gpu_watchdog.py`` all agree on ONE lock:

* an OS-level byte lock on ``logs/backrooms_batch/runner.lock``
  (``msvcrt.locking`` on Windows, ``fcntl.flock`` elsewhere) that the kernel
  releases automatically when the holder dies, and
* an owner record ``batch_render_queue_owner.json`` (pid / started_at /
  holder / purpose) written atomically via ``local_agent.atomic_io`` so other
  tools (and humans) can see who holds the GPU.

Stale-PID rule: an owner whose pid is provably dead is stale and may be
replaced.  If liveness cannot be determined (``pid_alive`` returns ``None``)
the lock is treated as HELD -- "unknown" never steals the lock.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("GVD_ROOT") or Path(__file__).resolve().parent).resolve()
DEFAULT_LOCK_PATH = ROOT / "logs" / "backrooms_batch" / "runner.lock"
DEFAULT_OWNER_PATH = ROOT / "batch_render_queue_owner.json"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

try:  # optional; os-level fallbacks below
    import psutil  # type: ignore
except Exception:  # pragma: no cover - depends on the host
    psutil = None  # type: ignore


def _atomic_write_json(path: Path, data: Any) -> None:
    try:
        from local_agent.atomic_io import atomic_write_json  # type: ignore
    except Exception:  # pragma: no cover - sys.path variations between callers
        import sys

        la = str(ROOT / "local_agent")
        if la not in sys.path:
            sys.path.insert(0, la)
        from atomic_io import atomic_write_json  # type: ignore
    atomic_write_json(Path(path), data)


class GpuLockHeld(RuntimeError):
    """Raised when another live process owns the render queue."""

    def __init__(self, message: str, owner: dict | None = None):
        super().__init__(message)
        self.owner = dict(owner or {})


def pid_alive(pid: int | None) -> bool | None:
    """True = alive, False = provably dead, None = unknown (probe failed).

    Callers must treat ``None`` as "assume alive": unknown never steals a lock.
    """
    try:
        pid = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if psutil is not None:
        try:
            return bool(psutil.pid_exists(pid))
        except Exception:
            return None
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                text=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception:
            return None
        return f'"{pid}"' in out and "No tasks" not in out
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return None


def read_owner(owner_path: Path | str = DEFAULT_OWNER_PATH) -> dict:
    p = Path(owner_path)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def owner_status(owner: dict | None) -> str:
    """'free' (no live owner), 'self', 'held' (live or unknown pid)."""
    owner = owner or {}
    try:
        pid = int(owner.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid <= 0:
        return "free"
    if pid == os.getpid():
        return "self"
    alive = pid_alive(pid)
    if alive is False:
        return "free"  # stale: provably dead
    return "held"  # alive, or unknown -> do not steal


def _os_lock(fh) -> None:
    fh.seek(0)
    if os.name == "nt":
        import msvcrt  # type: ignore

        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl  # type: ignore

        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _os_unlock(fh) -> None:
    try:
        fh.seek(0)
        if os.name == "nt":
            import msvcrt  # type: ignore

            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl  # type: ignore

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass


class GpuLock:
    """Exclusive render-queue lock.  Use as a context manager or acquire()/release()."""

    def __init__(
        self,
        holder: str,
        *,
        purpose: str = "GPU batch render",
        lock_path: Path | str | None = None,
        owner_path: Path | str | None = None,
    ):
        self.holder = str(holder)
        self.purpose = str(purpose)
        # Resolved at call time so tests/operators can repoint the module defaults.
        self.lock_path = Path(lock_path or DEFAULT_LOCK_PATH)
        self.owner_path = Path(owner_path or DEFAULT_OWNER_PATH)
        self.lock_file = None
        self.held = False

    # -- lifecycle -----------------------------------------------------------
    def acquire(self) -> "GpuLock":
        if self.held:
            return self
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.lock_path.open("a+b")
        try:
            fh.seek(0)
            if not fh.read(1):
                fh.write(b"0")
                fh.flush()
            try:
                _os_lock(fh)
            except OSError as exc:
                owner = read_owner(self.owner_path)
                raise GpuLockHeld(
                    f"GPU render lock {self.lock_path} is held by another process: {owner or exc}",
                    owner,
                ) from exc
            owner = read_owner(self.owner_path)
            status = owner_status(owner)
            if status == "held":
                _os_unlock(fh)
                raise GpuLockHeld(
                    f"Another renderer owns the queue (pid liveness={pid_alive(owner.get('pid'))}): {owner}",
                    owner,
                )
        except Exception:
            fh.close()
            raise
        self.lock_file = fh
        self.held = True
        now = time.time()
        _atomic_write_json(
            self.owner_path,
            {
                "pid": os.getpid(),
                "holder": self.holder,
                "purpose": self.purpose,
                "started_at": now,
                "started": now,  # legacy key written by BackroomsWatch
                "host": socket.gethostname(),
                "lock_path": str(self.lock_path),
            },
        )
        return self

    def release(self) -> None:
        if not self.held:
            return
        try:
            owner = read_owner(self.owner_path)
            if int(owner.get("pid") or 0) == os.getpid():
                _atomic_write_json(
                    self.owner_path,
                    {"pid": 0, "purpose": "released", "holder": self.holder, "released_at": time.time()},
                )
        except Exception:
            pass
        finally:
            fh = self.lock_file
            self.lock_file = None
            self.held = False
            if fh is not None:
                _os_unlock(fh)
                try:
                    fh.close()
                except Exception:
                    pass

    def __enter__(self) -> "GpuLock":
        return self.acquire()

    def __exit__(self, *exc) -> None:
        self.release()


def is_held_by_other(
    lock_path: Path | str | None = None,
    owner_path: Path | str | None = None,
) -> bool:
    """Real check for supervisors/watchdogs: True when another process owns the GPU.

    Fails closed: any probe error counts as "held".
    """
    try:
        status = owner_status(read_owner(owner_path or DEFAULT_OWNER_PATH))
        if status == "held":
            return True
        if status == "self":
            return False
        lock_path = Path(lock_path or DEFAULT_LOCK_PATH)
        if not lock_path.is_file():
            return False
        with lock_path.open("a+b") as fh:
            try:
                _os_lock(fh)
            except OSError:
                return True
            _os_unlock(fh)
        return False
    except Exception:
        return True


__all__ = [
    "DEFAULT_LOCK_PATH",
    "DEFAULT_OWNER_PATH",
    "GpuLock",
    "GpuLockHeld",
    "is_held_by_other",
    "owner_status",
    "pid_alive",
    "read_owner",
]
