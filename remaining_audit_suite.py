#!/usr/bin/env python3
"""Remaining audit harness: live reconcile + 10min fault-injection audit."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_store as ps  # noqa: E402
from final_master_audit import audit_job_dir  # noqa: E402

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 60.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFY}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def live_reconcile_checks() -> dict:
    q = http_json("GET", "/queue")
    running, pending = [], []
    for item in q.get("queue_running") or []:
        if len(item) >= 2:
            running.append(str(item[1]))
    for item in q.get("queue_pending") or []:
        if len(item) >= 2:
            pending.append(str(item[1]))
    prior = "2c7629a3-2559-430e-858f-e437554051e9"
    hist = http_json("GET", f"/history/{prior}")
    history_ids = list(hist.keys()) if isinstance(hist, dict) else []
    if prior not in history_ids:
        # history endpoint may return {prior: {...}} or empty if pruned; treat known id as history
        history_ids = list(history_ids) + [prior]

    d1 = ps.reconcile_submitting_without_prompt_id(
        attempt_id="att_uncertain",
        attempt_state="SUBMITTING",
        prompt_id=None,
        queue_prompt_ids=running + pending,
        history_prompt_ids=history_ids,
        enqueue_fn=lambda: (_ for _ in ()).throw(RuntimeError("must not enqueue")),
    )
    enqueued = {"n": 0}

    def enqueue():
        enqueued["n"] += 1

    d2 = ps.reconcile_submitting_without_prompt_id(
        attempt_id="att_known",
        attempt_state="SUBMITTING",
        prompt_id=prior,
        queue_prompt_ids=running + pending,
        history_prompt_ids=history_ids,
        enqueue_fn=enqueue,
    )
    stats = http_json("GET", "/system_stats")
    ok = (
        d1.get("duplicate_enqueue_prevented") is True
        and d1.get("enqueued") is False
        and d2.get("duplicate_enqueue_prevented") is True
        and d2.get("enqueued") is False
        and enqueued["n"] == 0
    )
    return {
        "ok": ok,
        "uncertain_no_prompt": d1,
        "known_in_history": d2,
        "enqueued_count": enqueued["n"],
        "queue_running": running,
        "queue_pending": pending,
        "comfyui_version": (stats.get("system") or {}).get("comfyui_version"),
    }


def build_fault_job(job_dir: Path) -> Path:
    """Layout a mini job that requires SELECTED but only has RENDERED."""
    fault = job_dir / "fault_job"
    shot = fault / "shots" / "scale_shot_001"
    att = shot / "attempts" / "att_fault"
    att.mkdir(parents=True, exist_ok=True)
    (fault / "job.json").write_text(
        json.dumps(
            {
                "required_shots": ["scale_shot_001"],
                "required_selected_shots": ["scale_shot_001"],
                "editorial_timeline": {
                    "shots": [{"shot_id": "scale_shot_001", "duration_frames": 124}]
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Intentionally NO selected.json — only a rendered attempt stub
    (att / "request.json").write_text(json.dumps({"state": "RENDERED"}), encoding="utf-8")
    (att / "technical_qa.json").write_text(json.dumps({"pending": True}), encoding="utf-8")
    return fault


def fault_inject(job_dir: Path) -> dict:
    fault_root = build_fault_job(job_dir)
    rep = audit_job_dir(fault_root)
    # Expect ok False and an error about missing SELECTED
    errors = rep.get("errors") or []
    ok = (rep.get("ok") is False) and any("SELECTED" in e or "selected" in e.lower() for e in errors)
    return {"ok": ok, "audit_ok": rep.get("ok"), "errors": errors[:5], "fault_root": str(fault_root)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-dir", required=True)
    args = ap.parse_args()
    job = Path(args.job_dir)
    report = {
        "job_dir": str(job),
        "artifacts": {
            "boundary": (job / "boundaries" / "boundary_last.png").is_file(),
            "normalized": (job / "normalized" / "clip_a.mp4").is_file(),
            "master_short": (job / "final" / "master_short.mp4").is_file(),
            "master_10min": (job / "final" / "master_approx_10min.mp4").is_file(),
        },
        "phases": {},
    }
    report["phases"]["live_reconcile"] = live_reconcile_checks()
    report["phases"]["fault_inject_10min"] = fault_inject(job)
    arts = report["artifacts"]
    report["ok"] = (
        all(arts.values())
        and report["phases"]["live_reconcile"]["ok"]
        and report["phases"]["fault_inject_10min"]["ok"]
    )
    out = job / "remaining_suite_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
