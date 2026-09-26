#!/usr/bin/env python3
"""DINO + CLIP image vs C017-end reference; CLIP text on PromptTester variants. CPU."""
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
from gvd_qa.prompt_ablation import expand_prompt_variants
from gvd_qa.scorers import clip_image_score, clip_text_score, dino_image_score

GEN = ROOT / "local_agent" / "runtime" / "gvd_qa" / "jobs" / "gen_c017_end_20260921T193208Z" / "a70441d416754aaa9e250742532efbf9" / "candidate.png"
REF = ROOT / "local_agent" / "runtime" / "dspy_opt" / "br24_C017_end_00001_.png"
PROMPT = (
    "empty yellow carpet hallway receding into the distance, yellow curtain "
    "at the far end, white walls, fluorescent lights, camcorder still, no people"
)
OUT = ROOT / "local_agent" / "runtime" / "gvd_qa" / "smoke_reference_and_ablation.json"


def main() -> int:
    gen = GEN.read_bytes()
    ref = REF.read_bytes()
    dino = dino_image_score(gen, ref)
    clip_img = clip_image_score(gen, ref)
    variants = expand_prompt_variants(PROMPT)
    rows = []
    for v in variants:
        clip = clip_text_score(gen, v["prompt"])
        rows.append({"index": v["index"], "label": v["label"], "omitted": v["omitted"],
                     "clip_text": clip})
    baseline = next(r["clip_text"] for r in rows if r["omitted"] is None)
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "generated_still": str(GEN),
        "reference_still": str(REF),
        "dino_raw_cosine": dino,
        "clip_image_raw_cosine": clip_img,
        "clip_text_unit": "torchmetrics_clipscore_0_100",
        "baseline_clip_text": baseline,
        "variant_clips": rows,
        "calibration": "none",
        "note": "Reference/ablation observations only. Do not copy as production floors or promote omitted phrases.",
        "status": "ok",
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    db = connect_evidence(ROOT / "local_agent" / "runtime" / "gvd_qa" / "qa_evidence.sqlite")
    db.execute(
        "UPDATE qa_experiments SET scores_json=? WHERE parent_prompt_sha256=? AND seed=17",
        (json.dumps({"note": "see smoke_reference_and_ablation.json variant_clips"}),
         __import__("hashlib").sha256(PROMPT.encode()).hexdigest()),
    )
    db.commit()
    print(json.dumps({
        "status": "ok",
        "dino": dino,
        "clip_image": clip_img,
        "baseline_clip_text": baseline,
        "n_variants": len(rows),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
