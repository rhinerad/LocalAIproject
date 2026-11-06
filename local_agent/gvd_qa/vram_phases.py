"""Generate → flush → validate occupancy. Never overlap Comfy, Ollama, and VLM."""
from __future__ import annotations

from typing import Any, Callable

PHASE_GENERATE = "generate"
PHASE_FLUSH = "flush"
PHASE_VALIDATE = "validate"


def run_phase(
    phase: str,
    *,
    prepare_comfy: Callable[[str], Any] | None = None,
    release_comfy: Callable[[str], Any] | None = None,
    prepare_vlm: Callable[[str], Any] | None = None,
    release_vlm: Callable[[str], Any] | None = None,
    comfy_free: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Drive the occupancy handoff. Callers inject the real VRAM helpers."""
    notes: list[str] = []
    if phase == PHASE_GENERATE:
        if prepare_comfy is not None:
            prepare_comfy("gvd_qa generate")
        notes.append("comfy_owns_gpu")
    elif phase == PHASE_FLUSH:
        if comfy_free is not None:
            comfy_free()
            notes.append("comfy_free_requested")
        if release_comfy is not None:
            release_comfy("gvd_qa flush")
            notes.append("comfy_released")
        notes.append("/free is a request not proof CUDA is empty")
    elif phase == PHASE_VALIDATE:
        if prepare_vlm is not None:
            prepare_vlm("gvd_qa validate")
            notes.append("vlm_owns_gpu")
        else:
            notes.append("cpu_or_injected_scores_only")
    else:
        raise ValueError(f"unknown QA phase {phase!r}")
    return {"phase": phase, "notes": notes}


def finish_validate(release_vlm: Callable[[str], Any] | None = None) -> dict[str, Any]:
    if release_vlm is not None:
        release_vlm("gvd_qa validate complete")
        return {"phase": PHASE_VALIDATE, "notes": ["vlm_released"]}
    return {"phase": PHASE_VALIDATE, "notes": ["no_vlm_handle"]}
