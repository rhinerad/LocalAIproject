"""Small, stdlib-only atomic file-write primitives for Local Agent state.

The caller owns serialization and therefore keeps its existing on-disk format.
Both helpers write a unique sibling temp file and replace the destination only
after the whole payload has been written.  The unique name matters on Windows:
nearby requests can otherwise race over the same ``.tmp`` status marker.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import uuid
from typing import Any


def atomic_write_text(path: Path, text: str) -> None:
    """Atomically replace *path* with UTF-8 *text*, creating its parent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(
        f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    temp.write_text(text, encoding="utf-8")
    try:
        # Windows antivirus/indexers and sibling watchdog readers can briefly
        # hold the destination while a supervisor is checkpointing.  A short
        # six-attempt window made long prompt-pack runs fail spuriously with
        # WinError 5; keep the temp file and retry for up to ~30 seconds.
        for attempt in range(120):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == 119:
                    raise
                time.sleep(0.25)
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass


def atomic_write_json(path: Path, data: Any) -> None:
    """Convenience JSON form for standard pretty-printed local state."""
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Atomically replace *path* with *data*, creating its parent."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(
        f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    temp.write_bytes(data)
    try:
        for attempt in range(6):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass
