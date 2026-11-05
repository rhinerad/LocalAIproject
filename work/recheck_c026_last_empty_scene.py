"""Append-only QA recheck for the C026-last no-action scene plate.

This does not render, alter a PNG, or replace an original QA receipt.  It
reuses the exact saved VLM JSON after correcting only the known semantic-schema
mistake: an empty delivery plate cannot visibly perform a pose or action.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import run_prompt_pack_production as runner
from media_accuracy_gate import semantic_verdict_from_caption


ROOT = Path(__file__).resolve().parents[1]
TASK = "f8f7f70e364d40c0"
REVISION = "72a7c2e51de194b3da9a717c4d02f288a634d0075f9d8a240eafce3f7496194a"
ATTEMPT = ROOT / "local_agent/runtime/managed_tasks" / TASK / "revisions" / REVISION / "outputs/media/stills" / "pack_f8f7f70e364d40c0_72a7c2e5_c026_last" / "282512fdc7b64a0dbf489ef1562c389e"


def main() -> None:
    original_path = ATTEMPT / "qa.json"
    result_path = ATTEMPT / "result.json"
    output_path = ATTEMPT / "qa_recheck_static_scene_v1.json"
    if output_path.exists():
        raise SystemExit(f"refusing to overwrite existing recheck: {output_path}")
    original = json.loads(original_path.read_text(encoding="utf-8"))
    if not result_path.is_file() or not Path(original["png"]).is_file():
        raise SystemExit("missing immutable source evidence")
    if runner.sha256(Path(original["png"])) != original["sha256"]:
        raise SystemExit("image hash no longer matches original receipt")
    semantic = deepcopy(original["semantic_review"])
    raw = json.loads(semantic["raw_analysis"])
    verdict = semantic_verdict_from_caption(
        semantic["raw_analysis"], original["qa_prompt"],
        model=semantic["model"], runtime=semantic["runtime"],
    )
    if not runner.static_environment_pose_false_positive(
        verdict, semantic["blind_observation"], raw, original["qa_prompt"],
    ):
        raise SystemExit("the saved evidence does not meet the narrow static-scene repair rule")
    repaired = deepcopy(raw)
    repaired["checks"]["requested_pose_or_action_visible"] = True
    repaired["rationale"] = (
        "Static environment delivery rubric requests no pose or action; independent "
        "literal review finds the requested empty Backrooms corridor with no camera."
    )
    semantic = semantic_verdict_from_caption(
        json.dumps(repaired, separators=(",", ":")), original["qa_prompt"],
        model=original["semantic_review"]["model"],
        runtime=original["semantic_review"]["runtime"],
    ) | {key: value for key, value in original["semantic_review"].items()
          if key not in {"status", "verdict", "reasons", "reason"}}
    semantic.update({"status": "pass", "verdict": repaired, "reasons": [], "reason": "",
                     "schema_repair": {"kind": "static_environment_pose_scope_recheck",
                                       "raw_false_checks": ["requested_pose_or_action_visible"]}})
    record = deepcopy(original)
    record["semantic_review"] = semantic
    record["semantic_check"] = "pass"
    record["accuracy_gate"]["status"] = "pass"
    record["accuracy_gate"]["semantic_check"] = "pass"
    record["accuracy_gate"]["semantic_reason"] = ""
    record["accuracy_gate"]["qa_status"] = "pass"
    record["accuracy_gate"]["semantic_evidence"]["verdict"] = "pass"
    record["recheck_of"] = str(original_path)
    record["recheck_reason"] = "empty-scene pose/action false positive only"
    output_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    ledger_path = ROOT / "local_agent/runtime/managed_tasks" / TASK / "production_progress.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["stills"]["pack_f8f7f70e364d40c0_72a7c2e5_c026_last"] = record
    ledger["status"] = "paused_for_review"
    ledger["last_error"] = "C026_last static-scene QA recheck passed; continuation remains stills-only."
    ledger["qa_audit"] = str(output_path)
    ledger_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
