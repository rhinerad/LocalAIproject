"""Bounded seed reroll around evaluate_artifact."""
from __future__ import annotations

from typing import Any, Callable

from .constants import DEFAULT_ATTEMPT_BUDGET
from .evaluate import evaluate_artifact
from .vram_phases import (
    PHASE_FLUSH,
    PHASE_GENERATE,
    PHASE_VALIDATE,
    finish_validate,
    run_phase,
)

RenderFn = Callable[[int], dict[str, Any]]


def next_seed(seed: int, attempt: int) -> int:
    """Deterministic successor seed. Attempt is 0-based."""
    return int(seed) + int(attempt) + 1


def run_qa_loop(
    *,
    prompt: str,
    seed: int,
    render: RenderFn,
    attempt_budget: int = DEFAULT_ATTEMPT_BUDGET,
    expected_tags: list[str] | tuple[str, ...] = (),
    clip_min: float | None = None,
    require_vlm: bool = False,
    prepare_comfy=None,
    release_comfy=None,
    prepare_vlm=None,
    release_vlm=None,
    comfy_free=None,
    evaluate: Callable[..., dict[str, Any]] | None = None,
    prior_artifacts: Any = (),
) -> dict[str, Any]:
    """Render, flush, validate, reroll on Qwen-VL false or low CLIP.

    `render(seed)` must return a dict with optional keys artifact_path,
    history, graph, vlm_caption, artifact_bytes. It must not load the VLM.

    `prior_artifacts` (fix 2026-09-23, readiness-audit finding 1.2): an
    iterable of (caption, image_bytes_or_path) pairs for prior accepted
    attempts in this run, forwarded to evaluate_fn's own `prior_artifacts`
    parameter so duplicate detection (which evaluate_artifact only runs
    `if prior_artifacts:`) actually engages here. Previously this loop never
    passed prior_artifacts/artifact_bytes at all, so duplicate detection was
    silently disabled for every caller of this generic loop.
    """
    budget = max(1, int(attempt_budget))
    evaluate_fn = evaluate or evaluate_artifact
    attempts: list[dict[str, Any]] = []
    current = int(seed)

    for index in range(budget):
        run_phase(
            PHASE_GENERATE,
            prepare_comfy=prepare_comfy,
            release_comfy=release_comfy,
            prepare_vlm=None,
            release_vlm=None,
            comfy_free=None,
        )
        # Fix 2026-09-23 (readiness-audit finding 1.2): render/evaluate were
        # not wrapped in try/finally, so an exception here (e.g. render()
        # raising, or a VLM network error inside evaluate_fn) skipped
        # finish_validate(release_vlm) entirely, leaking a loaded VLM on the
        # GPU with nothing to release it. finally now guarantees release
        # runs on every path, success or exception, exactly as it already
        # ran unconditionally on the success path before this fix.
        try:
            rendered = render(current) or {}
            run_phase(
                PHASE_FLUSH,
                prepare_comfy=None,
                release_comfy=release_comfy,
                comfy_free=comfy_free,
            )
            run_phase(
                PHASE_VALIDATE,
                prepare_vlm=prepare_vlm if (require_vlm or rendered.get("vlm_caption") is not None) else None,
            )
            kwargs: dict[str, Any] = {
                "prompt": prompt,
                "artifact_path": rendered.get("artifact_path"),
                "history": rendered.get("history"),
                "graph": rendered.get("graph"),
                "expected_tags": expected_tags,
                "require_vlm": require_vlm,
                "vlm_caption": rendered.get("vlm_caption"),
                "object_info": rendered.get("object_info"),
                "installed_nodes": rendered.get("installed_nodes") or (),
                "artifact_bytes": rendered.get("artifact_bytes"),
                "prior_artifacts": prior_artifacts,
            }
            if clip_min is not None:
                kwargs["clip_min"] = clip_min
            report = evaluate_fn(**kwargs)
        finally:
            finish_validate(release_vlm)
        record = {
            "attempt": index,
            "seed": current,
            "report": report,
            "artifact_path": rendered.get("artifact_path"),
        }
        attempts.append(record)
        if report.get("passed"):
            return {
                "status": "accepted",
                "seed": current,
                "attempts": attempts,
                "report": report,
            }
        if report.get("action") != "reroll" or index + 1 >= budget:
            return {
                "status": "rejected" if report.get("action") == "reroll" else "hold_review",
                "seed": current,
                "next_seed": next_seed(current, index),
                "attempts": attempts,
                "report": report,
            }
        current = next_seed(current, index)

    last = attempts[-1]["report"] if attempts else {}
    return {
        "status": "rejected",
        "seed": current,
        "attempts": attempts,
        "report": last,
    }
