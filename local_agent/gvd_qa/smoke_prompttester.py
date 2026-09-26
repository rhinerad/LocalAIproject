#!/usr/bin/env python3
"""Expand a locked prompt the way PromptTester does; record ablation jobs. No GPU."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent))

from gvd_qa.evidence import connect_evidence
from gvd_qa.prompt_ablation import expand_prompt_variants, plan_history, record_ablation_from_plan

PROMPT = (
    "empty yellow carpet hallway receding into the distance, yellow curtain "
    "at the far end, white walls, fluorescent lights, camcorder still, no people"
)
OUT = ROOT / "local_agent" / "runtime" / "gvd_qa" / "smoke_prompttester.json"


def main() -> int:
    variants = expand_prompt_variants(PROMPT)
    plan = plan_history(variants)
    db = connect_evidence(ROOT / "local_agent" / "runtime" / "gvd_qa" / "qa_evidence.sqlite")
    jobs = record_ablation_from_plan(
        db, plan, [17], PROMPT, "unmeasured_clip", "027847a376093c9bf48d5a2b8cfa16cd8c3c92f941982e3cdd8bcd9f88b8e9ab",
        held_out_outcome=None,
    )
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "prompt": PROMPT,
        "variant_count": len(variants),
        "jobs": len(jobs),
        "max_attempts": 1,
        "held_out_outcome": None,
        "note": "Ablation jobs recorded only. Do not promote prompt edits without held-out evaluation.",
        "variants": [{"index": v["index"], "label": v["label"], "omitted": v["omitted"]} for v in variants],
        "status": "ok",
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "variants": report["variant_count"], "jobs": report["jobs"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
