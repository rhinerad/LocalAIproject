"""Configurable GVD_ROOT layout. ComfyUI is never assumed to live inside it."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_LOCAL_AGENT = _HERE.parent
_HANDOFF_ROOT = _LOCAL_AGENT.parent

DEFAULT_GVD_ROOT = _LOCAL_AGENT / "runtime" / "gvd_tool_router"
SCHEMA_VERSION = 1
HEADROOM_MIB = 2048


def resolve_gvd_root(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("GVD_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return DEFAULT_GVD_ROOT.resolve()


@dataclass(frozen=True)
class GvdLayout:
    root: Path

    @classmethod
    def from_env(cls, explicit: str | Path | None = None) -> "GvdLayout":
        return cls(resolve_gvd_root(explicit))

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def runtime_json(self) -> Path:
        return self.config_dir / "runtime.json"

    @property
    def registry_dir(self) -> Path:
        return self.root / "registry"

    @property
    def catalog_json(self) -> Path:
        return self.registry_dir / "catalog.json"

    @property
    def active_json(self) -> Path:
        return self.registry_dir / "active.json"

    @property
    def releases_dir(self) -> Path:
        return self.registry_dir / "releases"

    @property
    def workflows_approved(self) -> Path:
        return self.root / "workflows" / "approved"

    @property
    def quarantine(self) -> Path:
        return self.root / "quarantine"

    @property
    def validation(self) -> Path:
        return self.root / "validation"

    @property
    def assets(self) -> Path:
        return self.root / "assets" / "characters"

    @property
    def jobs(self) -> Path:
        return self.root / "jobs"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def sqlite(self) -> Path:
        return self.state_dir / "gvd.sqlite"

    @property
    def lease_lock(self) -> Path:
        return self.state_dir / "gpu_lease.lock"

    @property
    def lease_json(self) -> Path:
        return self.state_dir / "gpu_lease.json"

    @property
    def inventory_dir(self) -> Path:
        return self.root / "inventory"

    def ensure(self) -> None:
        for path in (
            self.config_dir,
            self.registry_dir,
            self.releases_dir,
            self.workflows_approved,
            self.quarantine,
            self.validation,
            self.assets,
            self.jobs,
            self.state_dir,
            self.inventory_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def job_dir(self, project: str, shot: str, attempt: str) -> Path:
        return self.jobs / _safe(project) / _safe(shot) / _safe(attempt)

    def character_dir(self, character_id: str, revision: str) -> Path:
        return self.assets / _safe(character_id) / _safe(revision)

    def workflow_dir(self, digest: str) -> Path:
        return self.workflows_approved / _require_digest(digest)

    def release_dir(self, digest: str) -> Path:
        return self.releases_dir / _require_digest(digest)

    def quarantine_dir(self, digest: str) -> Path:
        return self.quarantine / _require_digest(digest)


def _safe(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(name))
    return cleaned.strip("._-") or "unnamed"


def _require_digest(digest: str) -> str:
    text = str(digest).strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError("digest must be 64 hexadecimal characters")
    return text


HANDOFF_ROOT = _HANDOFF_ROOT
LOCAL_AGENT_ROOT = _LOCAL_AGENT
