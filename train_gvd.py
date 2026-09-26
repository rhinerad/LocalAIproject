#!/usr/bin/env python3
"""MIPROv2 trainer for GeneralVideoDirector (scaffolding).

Loads gvd_decomposition_dataset.jsonl, optimizes GeneralVideoDirector with
local qwen2.5:1.5b, and saves the compiled program.
DO NOT run while ComfyUI is saturating the RTX 5080.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import dspy
from dspy.teleprompt import MIPROv2

from gvd_core import GeneralVideoDirector

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "local_agent" / "runtime" / "dspy_datasets" / "gvd_decomposition_dataset.jsonl"
SAVE_PATH = ROOT / "local_agent" / "runtime" / "dspy_compiled" / "gvd_general_optimized.json"
MODEL = "qwen2.5:1.5b"
OLLAMA_BASE = "http://127.0.0.1:11434"

_HALLUCINATION_TOKENS = (
    "liminal",
    "fluorescent",
    "backrooms",
    "damp carpet",
    "yellow wallpaper",
    "vhs artifact",
)


def load_jsonl(path: Path) -> list[dspy.Example]:
    rows: list[dspy.Example] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            ex = dspy.Example(
                raw_narrative=str(obj["raw_narrative"]),
                subject_and_action=str(obj.get("subject_and_action") or ""),
                environment=str(obj.get("environment") or ""),
                camera_and_motion=str(obj.get("camera_and_motion") or ""),
                lighting_and_style=str(obj.get("lighting_and_style") or ""),
                final_comfyui_prompt=str(obj.get("final_comfyui_prompt") or ""),
                cfg=float(obj.get("cfg", 6.0)),
                denoise=float(obj.get("denoise", 1.0)),
                steps=int(obj.get("steps", 30)),
            ).with_inputs("raw_narrative")
            rows.append(ex)
    if not rows:
        raise RuntimeError(f"dataset empty or missing: {path}")
    return rows


def _as_float(value, lo: float, hi: float) -> bool:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return False
    return lo <= x <= hi


def _as_int(value, lo: int, hi: int) -> bool:
    try:
        x = int(value)
    except (TypeError, ValueError):
        return False
    return lo <= x <= hi


def validate_prompt_structure(example, pred, trace=None) -> float:
    """Penalize Backrooms hallucinations; require Wan/FLUX-sane hparams."""
    raw = str(getattr(example, "raw_narrative", "") or "").lower()
    blobs = " ".join(
        [
            str(getattr(pred, "subject_and_action", "") or ""),
            str(getattr(pred, "environment", "") or ""),
            str(getattr(pred, "camera_and_motion", "") or ""),
            str(getattr(pred, "lighting_and_style", "") or ""),
            str(getattr(pred, "final_comfyui_prompt", "") or ""),
        ]
    ).lower()

    for tok in _HALLUCINATION_TOKENS:
        if tok in blobs and tok not in raw:
            return 0.0

    if not str(getattr(pred, "final_comfyui_prompt", "") or "").strip():
        return 0.0
    if not _as_float(getattr(pred, "cfg", None), 1.0, 8.0):
        return 0.0
    if not _as_float(getattr(pred, "denoise", None), 0.35, 1.0):
        return 0.0
    if not _as_int(getattr(pred, "steps", None), 16, 40):
        return 0.0

    # Light structural credit: all four template fields non-empty.
    fields = (
        "subject_and_action",
        "environment",
        "camera_and_motion",
        "lighting_and_style",
    )
    filled = sum(1 for f in fields if str(getattr(pred, f, "") or "").strip())
    return 0.5 + 0.125 * filled


def configure_lm() -> dspy.LM:
    # Preferred modern path; fall back to legacy OllamaLocal if present.
    try:
        lm = dspy.LM(
            f"ollama_chat/{MODEL}",
            api_base=OLLAMA_BASE,
            temperature=0.7,
            max_tokens=2048,
            cache=False,
            extra_body={"keep_alive": 0, "num_predict": 2048},
        )
        dspy.configure(lm=lm)
        return lm
    except Exception:
        lm = dspy.OllamaLocal(model=MODEL, base_url=OLLAMA_BASE, max_tokens=2048)
        dspy.configure(lm=lm)
        return lm


def train(
    *,
    num_candidates: int = 5,
    num_trials: int = 8,
    auto: str | None = None,
) -> Path:
    configure_lm()
    trainset = load_jsonl(DATASET)
    student = GeneralVideoDirector()

    optimizer_kwargs = {
        "metric": validate_prompt_structure,
        "num_threads": 1,
        "max_bootstrapped_demos": 2,
        "max_labeled_demos": 4,
    }
    if auto:
        optimizer_kwargs["auto"] = auto
    else:
        optimizer_kwargs["num_candidates"] = num_candidates

    teleprompter = MIPROv2(**optimizer_kwargs)
    compile_kwargs = {"trainset": trainset, "requires_permission_to_run": False}
    if auto is None:
        compile_kwargs["num_trials"] = num_trials

    optimized = teleprompter.compile(student, **compile_kwargs)
    SAVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    optimized.save(str(SAVE_PATH))
    print(f"saved compiled GVD -> {SAVE_PATH}", flush=True)
    return SAVE_PATH


if __name__ == "__main__":
    # Manual run only when the GPU lane is free.
    train()