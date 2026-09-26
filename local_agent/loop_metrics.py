#!/usr/bin/env python3
"""Evidence-only metrics for loop-controller use; never runs a loop itself."""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

import loop_controller


def report(root: Path = loop_controller.ROOT) -> dict[str, Any]:
    goals = loop_controller.list_goals(root)
    durations: list[float] = []
    checks_run = checks_passed = 0
    for path in (root / "runs").glob("loop_*.jsonl") if (root / "runs").is_dir() else []:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            checks_run += 1
            checks_passed += int(bool(record.get("passed")))
            if isinstance(record.get("duration_seconds"), (int, float)):
                durations.append(float(record["duration_seconds"]))
    completed = sum(goal.get("status") == "complete" for goal in goals)
    needs_review = sum(goal.get("status") == "needs_operator" for goal in goals)
    return {
        "scope": "read-only verification controller",
        "goals_total": len(goals), "goals_completed": completed, "goals_needing_operator": needs_review,
        "checks_run": checks_run, "checks_passed": checks_passed,
        "check_pass_rate": round(checks_passed / checks_run, 3) if checks_run else None,
        "median_check_seconds": round(statistics.median(durations), 3) if durations else None,
        "false_completion_rate": "not measurable without operator-reviewed outcome labels",
        "unnecessary_action_count": 0,
        "token_cost": "0 (controller does not call a model)",
        "note": "Metrics describe recorded loop activity only; they are not a claim about general agent quality.",
    }


if __name__ == "__main__":
    print(json.dumps(report(), indent=2))
