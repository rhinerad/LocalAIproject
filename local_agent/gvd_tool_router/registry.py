"""Catalog + active snapshot. Only promotion writes active.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import GvdLayout, SCHEMA_VERSION
from .schema import (
    PUBLIC_TOOL_NAMES,
    ToolImplementation,
    can_activate,
    implementation_from_dict,
    sha256_json,
    to_plain,
)


class RegistryError(ValueError):
    pass


class Registry:
    def __init__(self, layout: GvdLayout):
        self.layout = layout
        self.layout.ensure()

    def load_catalog(self) -> dict[str, Any]:
        if not self.layout.catalog_json.exists():
            return {"schema_version": SCHEMA_VERSION, "tools": {}, "implementations": []}
        return json.loads(self.layout.catalog_json.read_text(encoding="utf-8"))

    def save_catalog(self, catalog: dict[str, Any]) -> None:
        self.layout.catalog_json.write_text(json.dumps(catalog, indent=2), encoding="utf-8")

    def implementations(self) -> list[ToolImplementation]:
        catalog = self.load_catalog()
        return [implementation_from_dict(row) for row in catalog.get("implementations") or []]

    def by_id(self) -> dict[str, ToolImplementation]:
        return {impl.implementation_id: impl for impl in self.implementations()}

    def load_active(self) -> dict[str, Any]:
        if not self.layout.active_json.exists():
            return {"schema_version": SCHEMA_VERSION, "digest": None, "implementations": []}
        return json.loads(self.layout.active_json.read_text(encoding="utf-8"))

    def active_implementations(self) -> list[ToolImplementation]:
        payload = self.load_active()
        rows = payload.get("implementations") or []
        return [implementation_from_dict(row) for row in rows]

    def snapshot_digest(self, implementations: list[ToolImplementation]) -> str:
        payload = [to_plain(impl) for impl in implementations]
        return sha256_json(payload)

    def promote(
        self,
        implementations: list[ToolImplementation],
        *,
        allow_unvalidated: bool = False,
    ) -> str:
        """Atomic active.json write. Callers must be the promotion service."""
        active_rows = []
        for impl in implementations:
            ok, _reasons = can_activate(impl)
            if impl.status == "active":
                if impl.peak_unknown() and not allow_unvalidated:
                    raise RegistryError(
                        f"{impl.implementation_id} cannot enter production without a local VRAM profile"
                    )
                if ok or allow_unvalidated:
                    active_rows.append(to_plain(impl))
            elif impl.tool_name in PUBLIC_TOOL_NAMES:
                continue
        digest = sha256_json(active_rows)
        snapshot = {
            "schema_version": SCHEMA_VERSION,
            "digest": digest,
            "implementations": active_rows,
        }
        release = self.layout.release_dir(digest)
        release.mkdir(parents=True, exist_ok=True)
        (release / "active.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        tmp = self.layout.active_json.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        tmp.replace(self.layout.active_json)
        return digest

    def rollback(self, digest: str) -> None:
        source = self.layout.release_dir(digest) / "active.json"
        if not source.exists():
            raise RegistryError(f"no release {digest}")
        tmp = self.layout.active_json.with_suffix(".json.tmp")
        tmp.write_bytes(source.read_bytes())
        tmp.replace(self.layout.active_json)
