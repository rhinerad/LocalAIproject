"""GVD tool router control plane (spec M0–M2).

Public tools exist even when every implementation is disabled. Discovery
orchestration is present; M3–M6 (profiles, live discovery, promotion,
dialogue/repair) are not claimed complete.
"""
from __future__ import annotations

from .paths import GvdLayout, resolve_gvd_root
from .schema import (
    ArtifactRef,
    CharacterState,
    ExecutionResult,
    ShotManifest,
    ToolImplementation,
    ToolName,
)

__all__ = [
    "ArtifactRef",
    "CharacterState",
    "ExecutionResult",
    "GvdLayout",
    "ShotManifest",
    "ToolImplementation",
    "ToolName",
    "resolve_gvd_root",
]
