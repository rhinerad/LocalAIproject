#!/usr/bin/env python3
"""CPU CLIP + DINO + ImageReward + WD14 on one still. No Comfy GPU graphs."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent))

from gvd_qa.local_client import LocalQaClient
from gvd_qa.scorers import CLIP_MODEL, DINO_MODEL, clip_text_score, dino_image_score, image_reward_score
from gvd_qa.wd14_cpu import cpu_wd14_fn

OUT = ROOT / "local_agent" / "runtime" / "gvd_qa"
STILL = ROOT / "local_agent" / "runtime" / "dspy_opt" / "br24_C017_start_00001_.png"
CAPTION = "first-person camcorder photo of a person holding a camera"


def nvidia():
    try:
        raw = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.free",
             "--format=csv,noheader,nounits"],
            text=True, timeout=8,
        )
        used, free = [int(float(x.strip())) for x in raw.strip().split(",")]
        return {"used_mib": used, "free_mib": free}
    except Exception as exc:
        return {"error": str(exc)}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "smoke_fast_qa_cpu.json"
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "still": str(STILL),
        "clip_model": CLIP_MODEL,
        "dino_model": DINO_MODEL,
        "clip_text_unit": "torchmetrics_clipscore_0_100",
        "reward_unit": "imagereward_raw",
        "device": "cpu",
        "vram_before": nvidia(),
        "calibration": "none",
        "note": "Unmeasured 5080 scores. Do not copy as production floors.",
    }
    if not STILL.is_file():
        report["status"] = "blocked"
        report["reason"] = "still missing"
        dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2
    png = STILL.read_bytes()
    try:
        report["clip_text"] = clip_text_score(png, CAPTION)
        report["dino_self"] = dino_image_score(png, png)
        report["image_reward"] = image_reward_score(png, CAPTION)
        report["wd14_tags"] = cpu_wd14_fn(download=False)(png)
        import hashlib
        digest = hashlib.sha256(png).hexdigest()
        qa = LocalQaClient(
            clip_score_fn=lambda b, t: clip_text_score(b, t),
            reward_fn=lambda b, t: image_reward_score(b, t),
            wd14_fn=cpu_wd14_fn(download=False),
        )
        qa.upload(png, digest)
        journal = OUT / "smoke_fast_qa_cpu_fast.json"
        if journal.exists():
            journal.unlink()
        history = qa.run({
            "90": {"class_type": "GVDMetricReport", "inputs": {
                "attempt_id": "fast_cpu_smoke", "image_sha256": digest,
                "profile_id": "unmeasured_clip",
                "clip_text_unit": "torchmetrics_clipscore_0_100"}},
            "92": {"class_type": "GVDRewardReport", "inputs": {
                "attempt_id": "fast_cpu_smoke", "image_sha256": digest,
                "profile_id": "imagereward_unmeasured"}},
        }, "fast_cpu_smoke", journal)
        report["history_clip"] = history["outputs"]["90"]["gvd_metrics"][0]["clip_text"]
        report["history_reward"] = history["outputs"]["92"]["gvd_reward"][0]["image_reward"]
        report["vram_after"] = nvidia()
        report["status"] = "ok"
    except Exception as exc:
        report["status"] = "error"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["vram_after"] = nvidia()
        dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "status", "clip_text", "dino_self", "image_reward", "wd14_tags",
        "vram_before", "vram_after") if k in report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
