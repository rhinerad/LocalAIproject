#!/usr/bin/env python3
"""Prove I2V refuses without a receipt and binds the C017-end accepted still."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE.parent))

from gvd_qa.i2v_gate import apply_qa_gate

RECEIPT = ROOT / "local_agent" / "runtime" / "gvd_qa" / "jobs" / "br24_C017_end_20260921T182819Z" / "accepted.json"
RUBRIC = HERE / "profiles" / "br24_c017_end_rubric.json"
BLOCKED = ROOT / "local_agent" / "runtime" / "gvd_qa" / "jobs"
OUT = ROOT / "local_agent" / "runtime" / "gvd_qa" / "smoke_i2v_receipt_gate.json"


def _args(**kwargs):
    base = dict(
        allow_ungated_i2v=False,
        require_qa_receipt=True,
        qa_receipt=None,
        qa_candidate=None,
        qa_job_dir=None,
        qa_policy_json=None,
        qa_requirements_json=None,
        qa_generation_graph=None,
        qa_policy_id=None,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def main() -> int:
    report = {"utc": datetime.now(timezone.utc).isoformat()}
    missing_code, missing_still = apply_qa_gate(_args(), root=ROOT, local_agent=HERE.parent)
    report["missing_receipt"] = {"exit": missing_code, "still": missing_still}
    blocked = next(BLOCKED.glob("br24_C017_2026*/blocked.json"), None)
    if blocked:
        b_code, b_still = apply_qa_gate(_args(
            qa_receipt=str(blocked),
            qa_policy_id="observed_5080_finite_clip_v1",
            qa_requirements_json=str(HERE / "profiles" / "br24_c017_rubric.json"),
        ), root=ROOT, local_agent=HERE.parent)
        report["blocked_receipt"] = {"exit": b_code, "still": None if b_still is None else str(b_still), "path": str(blocked)}
    ok_code, ok_still = apply_qa_gate(_args(
        qa_receipt=str(RECEIPT),
        qa_policy_id="observed_5080_c017_end_v1",
        qa_requirements_json=str(RUBRIC),
    ), root=ROOT, local_agent=HERE.parent)
    report["accepted_receipt"] = {
        "exit": ok_code,
        "still": None if ok_still is None else str(ok_still),
        "receipt": str(RECEIPT),
    }
    report["status"] = "ok" if missing_code == 4 and ok_code is None and ok_still is not None else "error"
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
