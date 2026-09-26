"""PromptTester-compatible phrase ablation. max_attempts is always 1 per variant."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from .evidence import insert_experiment


def expand_prompt_variants(prompt: str, delimiter: str = ",", include_baseline: bool = True) -> list[dict[str, Any]]:
    phrases = [p.strip() for p in prompt.split(delimiter) if p.strip()]
    if not phrases:
        return [{"index": 0, "prompt": "", "label": "Empty Prompt", "omitted": None}]
    rows: list[dict[str, Any]] = []
    index = 0
    if include_baseline:
        rows.append({"index": 0, "prompt": prompt, "label": "Baseline Full Prompt", "omitted": None})
        index = 1
    for i, phrase in enumerate(phrases):
        remaining = phrases[:i] + phrases[i + 1:]
        new_prompt = delimiter.join(remaining)
        label = phrase[:30] if len(phrase) > 30 else phrase
        rows.append({"index": index, "prompt": new_prompt, "label": label, "omitted": phrase})
        index += 1
    return rows


def plan_history(variants: list[dict[str, Any]]) -> dict[str, Any]:
    gvd = [{"index": v["index"], "prompt": v["prompt"], "label": v["label"]} for v in variants]
    return {"outputs": {"61": {"gvd_variants": gvd}}}


def record_ablation_from_plan(conn, plan: dict[str, Any], seeds: list[int],
                              parent_prompt: str, model_profile: str, rubric_sha256: str,
                              *, held_out_outcome: str | None = None) -> list[dict[str, Any]]:
    import importlib.util
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("_gvd_qa_runner_ablate", root / "gvd_qa.py")
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules.setdefault("_gvd_qa_runner_ablate", runner)
    spec.loader.exec_module(runner)
    parent = runner.sha256(parent_prompt.encode())
    written = []
    for job in runner.ablation_jobs(plan, seeds, model_profile, rubric_sha256):
        if job.get("max_attempts") != 1:
            raise RuntimeError("ablation jobs must pin max_attempts to 1")
        row = {
            "parent_prompt_sha256": parent,
            "variant_index": job["variant_index"],
            "variant_hash": job["variant_hash"],
            "seed": job["seed"],
            "scores": {},
            "held_out_outcome": held_out_outcome,
            "label": None,
        }
        insert_experiment(conn, row)
        written.append(job)
    return written
