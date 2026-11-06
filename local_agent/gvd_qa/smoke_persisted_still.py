#!/usr/bin/env python3
"""One-shot QA on a saved still: CPU CLIP/WD14, Caption V4, then ImageReward if it qualifies."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent))

from gvd_qa.caption_v4 import caption_v4_checklist
from gvd_qa.evidence import connect_evidence, insert_evidence
from gvd_qa.local_client import cpu_local_client
from gvd_qa.local_phases import CaptionV4Phases, nvidia
from gvd_qa.pipeline import run_persisted_still_qa

OUT = ROOT / "local_agent" / "runtime" / "gvd_qa"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--still", default=str(ROOT / "local_agent" / "runtime" / "dspy_opt" / "br24_C017_start_00001_.png"))
    parser.add_argument("--policy", default=str(HERE / "profiles" / "observed_5080_finite_clip.json"))
    parser.add_argument("--rubric", default=str(HERE / "profiles" / "br24_c017_rubric.json"))
    parser.add_argument("--caption", default="first-person camcorder photo of a person holding a camera")
    parser.add_argument("--job-prefix", default="br24_C017")
    parser.add_argument("--report", default=str(OUT / "smoke_persisted_still.json"))
    args = parser.parse_args()
    still = Path(args.still)
    policy = Path(args.policy)
    rubric = Path(args.rubric)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_dir = OUT / "jobs" / f"{args.job_prefix}_{stamp}"
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "still": str(still),
        "job_dir": str(job_dir),
        "vram_before": nvidia(),
        "policy": str(policy),
        "note": "clip_text_min=0 is finite-only, not a 5080 production floor.",
    }
    dest_report = Path(args.report)
    if not still.is_file():
        report["status"] = "blocked"
        report["reason"] = "still missing"
        dest_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2
    png = still.read_bytes()
    db = connect_evidence(OUT / "qa_evidence.sqlite")

    def record(**kwargs):
        insert_evidence(db, job_id=job_dir.name, verdict=kwargs["verdict"],
                        rubric_sha256=kwargs["rubric_sha256"], peak_gpu_mib=None)

    qa = cpu_local_client(
        audit_caption=str(args.caption),
        checklist_fn=lambda blob, reqs: caption_v4_checklist(blob, reqs),
        download_wd14=False,
    )
    phases = CaptionV4Phases(qa)
    try:
        dest = run_persisted_still_qa(
            image=png,
            policy_path=policy,
            requirements_path=rubric,
            phases=phases,
            job_dir=job_dir,
            expected_size=None,
            wd14_aliases={
                "camera": ("camera", "holding camera"),
                "person": ("1boy", "1girl", "solo"),
            },
            record_evidence=record,
            audit_caption=str(args.caption),
            local=True,
        )
        verdict = json.loads(dest.read_text(encoding="utf-8"))
        report["receipt"] = str(dest)
        report["accepted"] = verdict.get("accepted")
        report["reasons"] = verdict.get("reasons")
        report["scores"] = verdict.get("scores")
        report["qwen_checks"] = verdict.get("qwen_checks")
        report["wd14_traits"] = verdict.get("wd14_traits")
        report["vlm_vram"] = phases.peak
        report["vram_after"] = nvidia()
        report["status"] = "ok"
    except Exception as exc:
        try:
            phases.idle()
        except Exception:
            pass
        report["status"] = "error"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["vram_after"] = nvidia()
        dest_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1
    dest_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "accepted": report.get("accepted"),
        "reasons": report.get("reasons"),
        "scores": report.get("scores"),
        "qwen_checks": report.get("qwen_checks"),
        "receipt": report.get("receipt"),
        "vram_before": report.get("vram_before"),
        "vram_after": report.get("vram_after"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
