"""Hash-named quarantine. Downloaded bytes are immutable; metadata is append-only."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from .paths import GvdLayout, _require_digest


class QuarantineStore:
    def __init__(self, layout: GvdLayout):
        self.layout = layout
        self.layout.quarantine.mkdir(parents=True, exist_ok=True)

    def _dir(self, digest: str):
        return self.layout.quarantine_dir(_require_digest(digest))

    async def contains(self, digest: str) -> bool:
        return (self._dir(digest) / "body.json").is_file() or (
            self._dir(digest) / "body.bin"
        ).is_file()

    async def put_atomic(self, digest: str, body: bytes, metadata: dict[str, Any]) -> None:
        digest = _require_digest(digest)
        dest = self._dir(digest)
        dest.mkdir(parents=True, exist_ok=True)
        payload = dest / "body.bin"
        if payload.exists():
            # Duplicate download may add provenance without replacing bytes.
            self._append_meta(dest, {"duplicate_seen": True, **metadata})
            return
        tmp = dest / f"body.bin.tmp.{os.getpid()}"
        tmp.write_bytes(body)
        os.replace(tmp, payload)
        meta = {
            "digest": digest,
            "stored_at": datetime.now(timezone.utc).isoformat(),
            **metadata,
        }
        (dest / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    async def mark(self, digest: str, state: str, reasons: list[str]) -> None:
        dest = self._dir(_require_digest(digest))
        dest.mkdir(parents=True, exist_ok=True)
        self._append_meta(dest, {
            "state": state,
            "reasons": reasons,
            "marked_at": datetime.now(timezone.utc).isoformat(),
        })
        (dest / "state.txt").write_text(state, encoding="utf-8")

    def _append_meta(self, dest, extra: dict[str, Any]) -> None:
        log = dest / "meta.jsonl"
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": time.time(), **extra}) + "\n")
