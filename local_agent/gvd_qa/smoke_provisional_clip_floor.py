#!/usr/bin/env python3
"""Live CLIP on the three loop-labeled stills against provisional min 28. CPU."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent))

from gvd_qa.defaults import PROVISIONAL_POLICY
from gvd_qa.pipeline import load_policy
from gvd_qa.scorers import clip_text_score

STILLS = [
    ("reject", ROOT / "local_agent" / "runtime" / "dspy_opt" / "br24_C017_start_00001_.png",
     "first-person camcorder photo of a person holding a camera"),
    ("accept", ROOT / "local_agent" / "runtime" / "dspy_opt" / "br24_C017_end_00001_.png",
     "yellow carpet hallway with a yellow curtain at the far end"),
    ("accept", ROOT / "local_agent" / "runtime" / "gvd_qa" / "jobs" / "gen_c017_end_20260921T193208Z" /
     "a70441d416754aaa9e250742532efbf9" / "candidate.png",
     "yellow carpet hallway with a yellow curtain at the far end"),
]
OUT = ROOT / "local_agent" / "runtime" / "gvd_qa" / "smoke_provisional_clip_floor.json"


def main() -> int:
    policy = load_policy(PROVISIONAL_POLICY)
    rows = []
    ok = True
    for label, path, caption in STILLS:
        score = clip_text_score(path.read_bytes(), caption)
        below = score < policy.clip_text_min
        gate = "reject" if below else "admit"
        match = (gate == "reject" and label == "reject") or (gate == "admit" and label == "accept")
        ok = ok and match
        rows.append({
            "path": str(path), "label": label, "clip_text": score,
            "floor": policy.clip_text_min, "gate": gate, "matches_label": match,
        })
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "policy_id": policy.policy_id,
        "clip_text_min": policy.clip_text_min,
        "rows": rows,
        "status": "ok" if ok else "mismatch",
        "note": "Live CLIP vs 3-image provisional floor. Not production calibration.",
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "rows": [
        {k: r[k] for k in ("label", "clip_text", "gate", "matches_label")} for r in rows
    ]}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
