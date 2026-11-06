"""Stage DAG scheduler. Ready stages group by model family; dependents wait."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .schema import ShotManifest, ToolImplementation, WorkflowStage

QUANTUM_SHOTS = 4


@dataclass(frozen=True)
class ScheduledStage:
    shot_id: str
    stage_id: str
    family_key: str
    depends_on: tuple[str, ...]
    ready: bool


def expand_stages(impl: ToolImplementation, manifest: ShotManifest) -> list[ScheduledStage]:
    accepted_deps = set(manifest.dependencies)
    rows = []
    for stage in impl.stages:
        ready = set(stage.depends_on) <= {s.stage_id for s in impl.stages if s.stage_id in accepted_deps} or not stage.depends_on
        if stage.depends_on and not set(stage.depends_on).issubset({s.stage_id for s in impl.stages}):
            ready = False
        intra_ready = set(stage.depends_on) <= {s.stage_id for s in impl.stages} and not stage.depends_on
        ready = not stage.depends_on
        rows.append(ScheduledStage(
            shot_id=manifest.shot_id,
            stage_id=stage.stage_id,
            family_key=stage.template.model_family_key,
            depends_on=stage.depends_on,
            ready=ready,
        ))
    return rows


def topological_stages(impl: ToolImplementation) -> list[WorkflowStage]:
    remaining = {s.stage_id: s for s in impl.stages}
    ordered: list[WorkflowStage] = []
    while remaining:
        ready = [
            s for s in remaining.values()
            if all(dep not in remaining for dep in s.depends_on)
        ]
        if not ready:
            raise ValueError("cyclic stage DAG")
        ready.sort(key=lambda s: s.stage_id)
        pick = ready[0]
        ordered.append(pick)
        remaining.pop(pick.stage_id)
    return ordered


def group_ready(
    stages: Iterable[ScheduledStage],
    *,
    accepted_shots: set[str],
    predecessor: dict[str, str],
) -> dict[str, list[ScheduledStage]]:
    """Group ready stages by family. A continuation cannot leap its predecessor."""
    groups: dict[str, list[ScheduledStage]] = {}
    for stage in stages:
        if not stage.ready:
            continue
        pred = predecessor.get(stage.shot_id)
        if pred and pred not in accepted_shots:
            continue
        groups.setdefault(stage.family_key, []).append(stage)
    return groups


def pick_family(
    groups: dict[str, list[ScheduledStage]],
    *,
    current_family: str | None,
    quantum_used: int,
) -> str | None:
    if current_family and current_family in groups and quantum_used < QUANTUM_SHOTS:
        return current_family
    if not groups:
        return None
    return sorted(groups.keys(), key=lambda k: (-len(groups[k]), k))[0]
