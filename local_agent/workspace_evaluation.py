#!/usr/bin/env python3
"""Deterministic regression metrics for workspace/specialist scope.

This evaluates routing policy, not model intelligence.  It deliberately uses a
small reviewable corpus and writes only aggregate counts, so it can run without
loading a model or exposing conversation content.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import tools


CASES = (
    # id, workspace, history, expected specialist context
    ("creative_writing", "auto", [{"role": "user", "content": "Write a western story."}], False),
    ("general_comfy", "auto", [{"role": "user", "content": "Upscale my vacation video in ComfyUI."}], False),
    ("code_project", "general", [{"role": "user", "content": "Fix this Python unit test."}], False),
    ("dataset_project", "general", [{"role": "user", "content": "Clean this LoRA training dataset."}], False),
    ("explicit_equal_shares", "auto", [{"role": "user", "content": "Check Equal Shares clip 00A."}], True),
    ("clip_id", "auto", [{"role": "user", "content": "Compare 00B and 27E ladders."}], True),
    ("project_followup", "auto", [
        {"role": "user", "content": "Show the ladder for 00A."},
        {"role": "assistant", "content": "Here it is."},
        {"role": "user", "content": "What about the other one?"},
    ], True),
    ("forced_general", "general", [{"role": "user", "content": "Check Equal Shares clip 00A."}], False),
    ("forced_equal_shares", "equal_shares", [{"role": "user", "content": "What next?"}], True),
)


def evaluate() -> dict:
    project_only = set(tools.PROJECT_ONLY_TOOLS)
    general_schemas = {item["function"]["name"] for item in tools.schemas(include_project=False)}
    project_schemas = {item["function"]["name"] for item in tools.schemas(include_project=True)}
    rows: list[dict] = []
    for case_id, workspace, history, expected in CASES:
        actual = agent.workspace_includes_project(workspace, history)
        offered = project_schemas if actual else general_schemas
        project_tools_offered = bool(project_only & offered)
        rows.append({
            "id": case_id,
            "expected_specialist_context": expected,
            "actual_specialist_context": actual,
            "scope_passed": actual == expected,
            "project_tools_offered": project_tools_offered,
            "tool_scope_passed": project_tools_offered == actual,
        })
    false_activation = sum(not row["expected_specialist_context"] and row["actual_specialist_context"]
                           for row in rows)
    missed_activation = sum(row["expected_specialist_context"] and not row["actual_specialist_context"]
                            for row in rows)
    false_project_tools = sum(not row["actual_specialist_context"] and row["project_tools_offered"]
                              for row in rows)
    return {
        "suite": "workspace_scope_baseline",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_calls": "none",
        "total_cases": len(rows),
        "scope_passed": sum(row["scope_passed"] for row in rows),
        "tool_scope_passed": sum(row["tool_scope_passed"] for row in rows),
        "false_specialist_activations": false_activation,
        "missed_specialist_activations": missed_activation,
        "false_project_tool_exposures": false_project_tools,
        "cases": rows,
    }


def main() -> int:
    report = evaluate()
    print(json.dumps(report, indent=2))
    return 0 if (report["scope_passed"] == report["total_cases"]
                 and report["tool_scope_passed"] == report["total_cases"]
                 and not report["false_specialist_activations"]
                 and not report["false_project_tool_exposures"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
