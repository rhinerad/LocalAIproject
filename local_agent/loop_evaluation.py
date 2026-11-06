#!/usr/bin/env python3
"""Golden scenario contract for the opt-in loop-engineering controller.

These are controller cases, not model prompts.  They make the intended stop
states reviewable without consuming a model context window or pretending that a
static test can measure broad agent intelligence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SCENARIO_FILE = HERE / "evaluations" / "loop_golden_scenarios.json"
REQUIRED_KEYS = {"id", "category", "operator_goal", "expected_state", "must_not"}
ALLOWED_STATES = {"active", "complete", "needs_operator", "refused"}


def load(path: Path = SCENARIO_FILE) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("golden scenario file must contain a JSON array")
    return raw


def evaluate(path: Path = SCENARIO_FILE) -> dict[str, Any]:
    scenarios = load(path)
    ids = [item.get("id") for item in scenarios if isinstance(item, dict)]
    failures = []
    for index, item in enumerate(scenarios, 1):
        if not isinstance(item, dict) or REQUIRED_KEYS - set(item):
            failures.append(f"scenario {index} is missing required fields")
            continue
        if not isinstance(item["id"], str) or not item["id"].startswith("loop_"):
            failures.append(f"scenario {index} has an invalid id")
        if item["expected_state"] not in ALLOWED_STATES:
            failures.append(f"scenario {item['id']} has invalid expected_state")
        if not isinstance(item["must_not"], list) or not item["must_not"]:
            failures.append(f"scenario {item['id']} needs an explicit prohibition")
    if len(scenarios) < 20:
        failures.append("at least 20 golden scenarios are required")
    if len(set(ids)) != len(ids):
        failures.append("scenario IDs must be unique")
    return {
        "suite": "loop_engineering_golden_contract",
        "total": len(scenarios), "passed": len(scenarios) if not failures else len(scenarios) - len(failures),
        "ok": not failures, "failures": failures,
        "model_calls": "none; deterministic controller contract only",
    }


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
