#!/usr/bin/env python3
"""Bounded continuity failure / resume harness (offline, no ComfyUI/GPU).

Proves four contracts at logic level:
1. RENDERED → QA_PENDING; crash before SELECTED → resume does NOT skip
2. Intentional technical QA fail → RETRY_PENDING / not SELECTED
3. After SELECTED parent, child binds first_frame; parent re-select to B
   invalidates child
4. SUBMITTING without prompt_id → reconcile path does not duplicate-enqueue
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from production_store import (  # noqa: E402
    connect,
    create_attempt,
    ensure_shot,
    get_selected_attempt,
    mark_qa_flags,
    mark_technical_qa,
    reconcile_submitting_without_prompt_id,
    resume_should_skip_attempt,
    select_attempt,
    set_attempt_state,
    sha256_file,
)
from canonical_assets import (  # noqa: E402
    AssetRegistry,
    EditRelationship,
    apply_bind_plan_to_graph,
    build_continuity_bind_plan,
    parent_switch_invalidates_child,
    record_boundary_from_png,
)

TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _write_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(TINY_PNG)
    return path


def scenario_crash_before_selected(db) -> dict[str, Any]:
    """attempt goes RENDERED → QA_PENDING; crash before SELECTED → resume continues."""
    ensure_shot(db, "S_CRASH")
    aid = create_attempt(
        db,
        shot_id="S_CRASH",
        input_payload={"prompt": "crash_before_selected", "frames": 124},
        attempt_id="att_crash_1",
    )
    set_attempt_state(
        db,
        aid,
        "RENDERED",
        artifact_path="/tmp/fake_crash.mp4",
        artifact_sha256="abc123",
    )
    # Promote to QA_PENDING (pipeline alias via TECHNICAL_QA + meta)
    set_attempt_state(db, aid, "TECHNICAL_QA")
    from production_store import merge_attempt_meta

    merge_attempt_meta(db, aid, {"pipeline_state": "QA_PENDING"})
    row = db.execute(
        "SELECT state, meta_json FROM attempts WHERE attempt_id=?", (aid,)
    ).fetchone()
    meta = json.loads(row["meta_json"] or "{}")
    pipeline = str(meta.get("pipeline_state") or row["state"]).upper()
    # Simulate crash: no select_attempt call
    skip = resume_should_skip_attempt(pipeline)
    skip_rendered = resume_should_skip_attempt("RENDERED")
    skip_qa = resume_should_skip_attempt("QA_PENDING")
    return {
        "scenario": "crash_before_selected",
        "attempt_id": aid,
        "states_seen": ["RENDERED", "QA_PENDING"],
        "final_state": row["state"],
        "pipeline_state": pipeline,
        "resume_skips": skip,
        "resume_skips_rendered": skip_rendered,
        "resume_skips_qa_pending": skip_qa,
        "ok": (not skip) and (not skip_rendered) and (not skip_qa),
    }


def scenario_technical_qa_fail(db) -> dict[str, Any]:
    """Intentional technical QA fail → RETRY_PENDING / not SELECTED."""
    ensure_shot(db, "S_TECH")
    aid = create_attempt(
        db,
        shot_id="S_TECH",
        input_payload={"prompt": "tech_fail", "frames": 124},
        attempt_id="att_tech_1",
    )
    set_attempt_state(
        db,
        aid,
        "RENDERED",
        artifact_path="/tmp/fake_tech.mp4",
        artifact_sha256="def456",
    )
    new_state = mark_technical_qa(
        db, aid, passed=False, reason="black_frame_ratio_high"
    )
    row = db.execute(
        "SELECT state FROM attempts WHERE attempt_id=?", (aid,)
    ).fetchone()
    selected = get_selected_attempt(db, "S_TECH")
    return {
        "scenario": "technical_qa_fail",
        "attempt_id": aid,
        "state": row["state"],
        "mark_returned": new_state,
        "is_selected": selected is not None,
        "ok": row["state"] == "RETRY_PENDING"
        and new_state == "RETRY_PENDING"
        and selected is None,
    }


def scenario_parent_reselect_invalidates_child(
    db, work: Path
) -> dict[str, Any]:
    """SELECTED parent → child binds first_frame; re-select parent B invalidates."""
    ensure_shot(db, "C001")
    ensure_shot(db, "C002", parent_shot_id="C001", continuity_mode="continuous")

    png_a = _write_png(work / "boundary_a.png")
    png_b = _write_png(work / "boundary_b.png")
    # Make B distinct so hashes differ if needed
    png_b.write_bytes(TINY_PNG + b"\x00")

    parent_a = create_attempt(
        db,
        shot_id="C001",
        input_payload={"prompt": "parent_a", "variant": "A"},
        attempt_id="att_parent_a",
    )
    set_attempt_state(
        db,
        parent_a,
        "RENDERED",
        artifact_path=str(work / "parent_a.mp4"),
        artifact_sha256="parent_a_hash",
    )
    (work / "parent_a.mp4").write_bytes(b"FAKE_MP4_A" + b"0" * 100)
    mark_qa_flags(db, parent_a, technical_pass=True, visual_pass=True, audio_pass=True)
    # artifact_sha256 required by select_attempt
    set_attempt_state(
        db,
        parent_a,
        "RENDERED",
        artifact_path=str(work / "parent_a.mp4"),
        artifact_sha256=sha256_file(work / "parent_a.mp4"),
    )
    mark_qa_flags(db, parent_a, technical_pass=True, visual_pass=True, audio_pass=True)
    select_attempt(db, "C001", 0, parent_a)

    registry = AssetRegistry()
    boundary = record_boundary_from_png(
        registry,
        attempt_id=parent_a,
        shot_id="C001",
        frame_index=123,
        png_path=png_a,
        source_artifact=str(work / "parent_a.mp4"),
    )
    bind = build_continuity_bind_plan(
        registry,
        parent_attempt_id=parent_a,
        parent_state="SELECTED",
        edit_relationship=EditRelationship.CONTINUOUS.value,
        upload_prefix="C001",
    )
    graph: dict[str, Any] = {
        "20": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"prompt": "child"}},
    }
    apply_bind_plan_to_graph(graph, bind)
    first_frame = graph["20"]["inputs"].get("first_frame")

    child = create_attempt(
        db,
        shot_id="C002",
        input_payload={"prompt": "child", "parent": parent_a},
        attempt_id="att_child_1",
        parent_attempt_id=parent_a,
    )

    # Parent B candidate
    parent_b = create_attempt(
        db,
        shot_id="C001",
        input_payload={"prompt": "parent_b", "variant": "B"},
        attempt_id="att_parent_b",
    )
    (work / "parent_b.mp4").write_bytes(b"FAKE_MP4_B" + b"1" * 100)
    set_attempt_state(
        db,
        parent_b,
        "RENDERED",
        artifact_path=str(work / "parent_b.mp4"),
        artifact_sha256=sha256_file(work / "parent_b.mp4"),
    )
    mark_qa_flags(db, parent_b, technical_pass=True, visual_pass=True, audio_pass=True)
    # Re-select parent to B (revision advanced by prior select)
    shot = db.execute("SELECT revision FROM shots WHERE shot_id=?", ("C001",)).fetchone()
    select_attempt(db, "C001", int(shot["revision"]), parent_b)

    child_row = db.execute(
        "SELECT state FROM attempts WHERE attempt_id=?", (child,)
    ).fetchone()
    invalidated_by_switch = parent_switch_invalidates_child(
        bound_parent_attempt_id=parent_a,
        current_selected_parent_attempt_id=parent_b,
    )
    return {
        "scenario": "parent_reselect_invalidates_child",
        "parent_a": parent_a,
        "parent_b": parent_b,
        "child": child,
        "child_state": child_row["state"],
        "first_frame_bound": first_frame == ["1001", 0],
        "boundary_hash": boundary.content_hash[:16],
        "parent_switch_invalidates": invalidated_by_switch,
        "ok": (
            first_frame == ["1001", 0]
            and invalidated_by_switch is True
            and child_row["state"] == "INVALIDATED"
        ),
    }


def scenario_submitting_uncertain_no_duplicate() -> dict[str, Any]:
    """SUBMITTING without prompt_id → reconcile does not duplicate-enqueue."""
    enqueued: list[str] = []

    def enqueue_fn():
        enqueued.append("NEW_PROMPT")
        return "NEW_PROMPT"

    # Case A: no prompt_id
    d1 = reconcile_submitting_without_prompt_id(
        attempt_id="att_sub_1",
        attempt_state="SUBMITTING",
        prompt_id=None,
        queue_prompt_ids=[],
        history_prompt_ids=[],
        enqueue_fn=enqueue_fn,
    )
    # Case B: prompt_id known and already in history
    d2 = reconcile_submitting_without_prompt_id(
        attempt_id="att_sub_2",
        attempt_state="SUBMITTING",
        prompt_id="pid_existing",
        queue_prompt_ids=[],
        history_prompt_ids=["pid_existing"],
        enqueue_fn=enqueue_fn,
    )
    # Case C: not SUBMITTING
    d3 = reconcile_submitting_without_prompt_id(
        attempt_id="att_sub_3",
        attempt_state="RUNNING",
        prompt_id=None,
        enqueue_fn=enqueue_fn,
    )
    ok = (
        d1["duplicate_enqueue_prevented"] is True
        and d1["enqueued"] is False
        and d1["action"] == "reconcile_uncertain"
        and len(enqueued) == 0
        and d2["duplicate_enqueue_prevented"] is True
        and d2["enqueued"] is False
        and d3["enqueued"] is False
    )
    return {
        "scenario": "submitting_uncertain_no_duplicate",
        "no_prompt_id": d1,
        "existing_in_history": d2,
        "not_submitting": d3,
        "enqueue_calls": len(enqueued),
        "ok": ok,
    }


def run_all(work: Path | None = None) -> dict[str, Any]:
    work = Path(work) if work else Path(tempfile.mkdtemp(prefix="cont_fail_"))
    work.mkdir(parents=True, exist_ok=True)
    results: dict[str, Any] = {"work": str(work), "scenarios": {}, "comfy_called": False}
    with connect(work / "continuity_fail.sqlite") as db:
        results["scenarios"]["crash_before_selected"] = scenario_crash_before_selected(db)
        results["scenarios"]["technical_qa_fail"] = scenario_technical_qa_fail(db)
        results["scenarios"]["parent_reselect_invalidates_child"] = (
            scenario_parent_reselect_invalidates_child(db, work)
        )
    results["scenarios"]["submitting_uncertain_no_duplicate"] = (
        scenario_submitting_uncertain_no_duplicate()
    )
    results["ok"] = all(s.get("ok") for s in results["scenarios"].values())
    report_path = work / "continuity_failure_resume_report.json"
    report_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    results["report_path"] = str(report_path)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--work",
        type=Path,
        default=None,
        help="Working directory for sqlite + fixtures (temp if omitted)",
    )
    args = parser.parse_args(argv)
    results = run_all(args.work)
    summary = {
        "ok": results["ok"],
        "comfy_called": results["comfy_called"],
        "scenarios": {k: v.get("ok") for k, v in results["scenarios"].items()},
        "report_path": results.get("report_path"),
    }
    print(json.dumps(summary, indent=2))
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
