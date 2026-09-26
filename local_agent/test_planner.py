#!/usr/bin/env python3
"""Checks for non-executing structured plan proposals."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import planner


class _Route:
    model, host = "stub-model", "127.0.0.1:11435"
    def options(self): return {"num_ctx": 8192}


class PlannerTests(unittest.TestCase):
    def test_accepts_inert_structured_checklist(self):
        plan = planner.validate_plan({
            "goal": "Verify the local agent routing behavior",
            "steps": [
                {"title": "Inspect current routing evidence", "success_condition": "Evidence is recorded"},
                {"title": "Verify fallback behavior", "success_condition": "Outcome is reported"},
            ],
            "needs_operator_decision": False,
        }, "operator task")
        self.assertEqual("structured_local_model", plan["source"])
        self.assertEqual(2, len(plan["steps"]))

    def test_rejects_executable_plan_language(self):
        self.assertIsNone(planner.validate_plan({
            "goal": "bad", "steps": [
                {"title": "Start a render", "success_condition": "done"},
                {"title": "Verify it", "success_condition": "done"},
            ], "needs_operator_decision": False,
        }, "operator task"))
        self.assertIsNone(planner.validate_plan({
            "goal": "bad", "steps": [
                {"title": "Inspect safeguards", "success_condition": "Delete the old output"},
                {"title": "Verify it", "success_condition": "done"},
            ], "needs_operator_decision": False,
        }, "operator task"))

    def test_propose_uses_json_schema_and_validates_reply(self):
        reply = json.dumps({
            "goal": "Check routing", "steps": [
                {"title": "Inspect routing evidence", "success_condition": "A source is available"},
                {"title": "Verify fallback", "success_condition": "Result is reported"},
            ], "needs_operator_decision": False,
        })
        seen = {}
        def fake_chat(_messages, **kwargs):
            seen.update(kwargs)
            return reply, []
        with patch.object(planner.router, "decide", return_value=_Route()), \
             patch.object(planner.oll, "chat", fake_chat):
            plan, reason = planner.propose("Check routing")
        self.assertEqual("structured plan accepted", reason)
        self.assertEqual(planner.PLAN_SCHEMA, seen["response_format"])
        self.assertEqual("stub-model", seen["model"])
        self.assertEqual(0.0, seen["options"]["temperature"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
