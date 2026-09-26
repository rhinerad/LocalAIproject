"""One-shot GVD-B01 FLF spatial validation. Does NOT start MIPRO."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import generalized_video_director as gvd
import dspy_orchestrator as orch


def still_delta(start: Path, end: Path) -> dict:
    a = np.asarray(Image.open(start).convert("RGB"), dtype=np.float32)
    b = np.asarray(Image.open(end).convert("RGB"), dtype=np.float32)
    mse = float(np.mean((a - b) ** 2)) if a.shape == b.shape else None
    mae = float(np.mean(np.abs(a - b))) if a.shape == b.shape else None
    near = float(np.mean(np.abs(a - b) <= 1.0)) if a.shape == b.shape else None
    return {
        "exact_bytes_equal": start.read_bytes() == end.read_bytes(),
        "mse": mse,
        "mae": mae,
        "near_eq_frac": near,
        "start": str(start),
        "end": str(end),
        "start_bytes": start.stat().st_size,
        "end_bytes": end.stat().st_size,
    }


def find_latest_b01_stills(after_ts: float) -> dict:
    roots = [
        Path(r"A:\Users\rhine\ComfyUI-Shared\output\dspy_opt"),
        HERE / "runtime" / "dspy_opt",
        Path(r"A:\Users\rhine\ComfyUI-Shared\output"),
    ]
    starts: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        starts.extend(root.rglob("*GVD-B01*start*.png"))
    starts = [p for p in starts if p.stat().st_mtime >= after_ts - 5]
    if not starts:
        # fallback: newest overall
        all_starts=[]
        for root in roots:
            if root.exists():
                all_starts.extend(root.rglob("*GVD-B01*start*.png"))
        if not all_starts:
            return {}
        starts = all_starts
    start = max(starts, key=lambda p: p.stat().st_mtime)
    end = Path(str(start).replace("_start_", "_end_"))
    if not end.exists() and "_start_" in start.name:
        key = start.name.split("_start_")[1].split("_")[0]
        ends = list(start.parent.glob(f"*GVD-B01_end_{key}*.png"))
        if ends:
            end = max(ends, key=lambda p: p.stat().st_mtime)
    if not end.exists():
        return {"start": str(start), "end": None}
    return still_delta(start, end)


def main() -> int:
    row = next(r for r in gvd.BETA_SET if r["id"] == "GVD-B01")
    example = gvd.load_beta_trainset([row])[0]

    class Pred:
        positive_prompt = (
            f"{row['user_intent']} {row['constraints']} "
            "handheld walking momentum, first-person camcorder tracking, "
            "continuous unbroken shot, realistic camera shake, heavy VHS artifacting"
        )
        negative_prompt = (
            "static camera, tripod, freeze frame, still image, no motion, "
            "actor face, apartment furniture, readable text"
        )
        cfg_scale = 5.5
        denoise = 1.0
        step_count = 28

    pred = Pred()
    print("START:", getattr(example, "start_prompt", None))
    print("END:", getattr(example, "end_prompt", None))
    print("POSITIVE:", pred.positive_prompt[:220], "...")

    t0 = time.time()
    result = orch.evaluate_live_candidate(example, pred, iteration=0)
    elapsed = time.time() - t0
    stills = find_latest_b01_stills(t0)

    out = {
        "elapsed_s": elapsed,
        "clip_id": "GVD-B01",
        "start_prompt": row.get("start_prompt"),
        "end_prompt": row.get("end_prompt"),
        "scores": result.get("scores"),
        "mean": result.get("mean"),
        "minimum": result.get("minimum"),
        "mipro": result.get("mipro"),
        "passes_curriculum": result.get("passes_curriculum"),
        "error": result.get("error"),
        "video_path": result.get("video_path"),
        "positive_prompt": result.get("positive_prompt"),
        "stills": stills,
        "result": {k: result.get(k) for k in result if k != "vram_trace"},
    }
    scores = result.get("scores") or {}
    if isinstance(scores, dict):
        out["rationale"] = scores.get("rationale") or scores.get("motion_rationale")
    out_path = Path(r"A:\Users\rhine\.grok\long-running-background-tasks\gvd_b01_flf_spatial_validation.json")
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    print("WROTE", out_path)
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
