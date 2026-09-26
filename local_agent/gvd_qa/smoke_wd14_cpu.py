#!/usr/bin/env python3
"""CPU-only WD14 tag pass on a still. Never uses Comfy CUDA providers."""
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
from gvd_qa.wd14_cpu import cpu_wd14_fn, ensure_model, models_dir, tag_image

OUT = ROOT / "local_agent" / "runtime" / "gvd_qa"
STILL = ROOT / "local_agent" / "runtime" / "dspy_opt" / "br24_C017_start_00001_.png"


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
    dest = OUT / "smoke_wd14_cpu.json"
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "still": str(STILL),
        "models_dir": str(models_dir()),
        "vram_before": nvidia(),
        "note": "CPUExecutionProvider only; isolated runtime/gvd_qa/wd14_models; Rockernow custom_nodes untouched.",
    }
    if not STILL.is_file():
        report["status"] = "blocked"
        report["reason"] = "still missing"
        dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2
    try:
        onnx, csv_path = ensure_model(download=True)
        report["onnx"] = str(onnx)
        report["csv"] = str(csv_path)
        report["onnx_bytes"] = onnx.stat().st_size
        tagged = tag_image(STILL.read_bytes(), download=False)
        report["providers"] = tagged["providers"]
        report["model"] = tagged["model"]
        report["tags"] = tagged["tags"]
        report["general"] = tagged["general"][:40]
        report["character"] = tagged["character"][:20]
        png = STILL.read_bytes()
        import hashlib
        digest = hashlib.sha256(png).hexdigest()
        qa = LocalQaClient(
            clip_score_fn=lambda b, t: 0.0,
            wd14_fn=cpu_wd14_fn(download=False),
        )
        qa.upload(png, digest)
        graph = {
            "90": {"class_type": "GVDMetricReport", "inputs": {
                "attempt_id": "wd14_cpu_smoke",
                "image_sha256": digest,
                "profile_id": "unmeasured_clip",
                "clip_text_unit": "torchmetrics_clipscore_0_100",
            }},
        }
        journal = OUT / "smoke_wd14_cpu_fast.json"
        if journal.exists():
            journal.unlink()
        history = qa.run(graph, "wd14_cpu_smoke", journal)
        report["history_tags"] = history.get("outputs", {}).get("30", {}).get("tags")
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
    print(json.dumps({
        "status": report["status"],
        "wrote": str(dest),
        "providers": report.get("providers"),
        "tags": report.get("tags"),
        "vram_before": report.get("vram_before"),
        "vram_after": report.get("vram_after"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
