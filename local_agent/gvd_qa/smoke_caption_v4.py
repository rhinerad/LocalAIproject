#!/usr/bin/env python3
"""Owned Caption V4 still checklist. Starts and stops the llama.cpp runtime."""
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

from gvd_qa.caption_v4 import caption_v4_checklist

OUT = ROOT / "local_agent" / "runtime" / "gvd_qa"
STILL = ROOT / "local_agent" / "runtime" / "dspy_opt" / "br24_C017_start_00001_.png"
RUBRIC = [
    {"id": "yellow_walls", "criterion": "Yellow wallpaper or yellow wall surfaces are visibly present."},
    {"id": "person_visible", "criterion": "A person is clearly visible in the frame."},
]


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
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "still": str(STILL),
        "vram_before": nvidia(),
    }
    if not STILL.is_file():
        report["status"] = "blocked"
        report["reason"] = "still missing"
        (OUT / "smoke_caption_v4.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2
    import vram_controller
    import capabilities
    try:
        vram_controller.comfy_free_memory(unload_models=True, free_memory=True, update_state=False)
    except Exception as exc:
        report["comfy_free"] = str(exc)
    vram_controller.prepare_for_vlm("gvd_qa caption v4 smoke")
    started = capabilities.ensure_qwen25_vl_runtime(timeout_seconds=150)
    report["vlm_started"] = bool(started)
    report["vram_after_start"] = nvidia()
    if not started:
        report["status"] = "blocked"
        report["reason"] = "Caption V4 runtime did not come up"
        try:
            vram_controller.release_after_vlm("gvd_qa smoke failed to start")
        except Exception:
            pass
        (OUT / "smoke_caption_v4.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 3
    try:
        checks = caption_v4_checklist(STILL.read_bytes(), RUBRIC)
        report["checks"] = checks
        report["status"] = "ok"
    except Exception as exc:
        report["status"] = "error"
        report["error"] = f"{type(exc).__name__}: {exc}"
        try:
            vram_controller.release_after_vlm("gvd_qa smoke error")
        except Exception:
            pass
        (OUT / "smoke_caption_v4.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1
    try:
        vram_controller.release_after_vlm("gvd_qa caption v4 smoke complete")
    except Exception as exc:
        report["release_error"] = str(exc)
    report["vram_after_release"] = nvidia()
    dest = OUT / "smoke_caption_v4.json"
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
