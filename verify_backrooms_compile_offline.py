#!/usr/bin/env python3
"""Offline verify: exact-pack compile contract (no GPU)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "local_agent"))

SOURCE = HERE / "pasted-text.txt"
OUT = HERE / "outputs_compile_verify"


def main() -> int:
    import backrooms_compile as bc

    result = bc.compile_pack(SOURCE, out_dir=OUT)
    report = result["report"]
    clips = result["clips"]
    failures = []

    if report["clip_count"] != 102:
        failures.append(f"clip_count={report['clip_count']} expected 102")
    if not all(str(c.get("model_profile") or "").lower() == "flux" for c in clips):
        bad = [c["id"] for c in clips if str(c.get("model_profile") or "").lower() != "flux"]
        failures.append(f"non-flux model_profile: {bad[:5]}")
    lora_bound = []
    for c in clips:
        for field in ("start_frame_lora", "last_frame_lora"):
            lora = c.get(field)
            if isinstance(lora, dict) and lora.get("name"):
                lora_bound.append(f"{c['id']}.{field}={lora.get('name')}")
    if lora_bound:
        failures.append(f"SDXL LoRA bindings present: {lora_bound[:5]}")
    if report["dialogue_fields_count"] <= 0:
        failures.append("dialogue_fields_count == 0")
    if abs(report["duration_total_s"] - 1020.0) > 1.0:
        failures.append(f"duration_total_s={report['duration_total_s']} expected ~1020")
    if any(str(c.get("aspect_ratio") or "") != "4:3" for c in clips):
        failures.append("aspect_ratio not 4:3 on all clips")
    if not result["ledger"]:
        failures.append("conflict ledger empty")
    if not report.get("flux_ok"):
        failures.append("flux_ok false")

    status = "PASS" if not failures else "FAIL"
    print(status, json.dumps({
        "clip_count": report["clip_count"],
        "flux_ok": report["flux_ok"],
        "dialogue_fields_count": report["dialogue_fields_count"],
        "dialogue_line_count": report["dialogue_line_count"],
        "duration_total_s": report["duration_total_s"],
        "conflict_ledger_count": report["conflict_ledger_count"],
        "lora_bound": len(lora_bound),
        "failures": failures,
    }, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
