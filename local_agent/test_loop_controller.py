"""Regression checks for the opt-in, read-only loop controller."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import loop_controller as loop
import file_edit_gate


class LoopControllerTests(unittest.TestCase):
    def test_disabled_by_default_and_only_one_fixed_check_runs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            goal = loop.create_goal("Regression triage", "Verify safe tests.",
                                    ["general_scope", "agentic_eval"], root=root)
            self.assertFalse(loop.snapshot(root)["enabled"])
            with self.assertRaises(loop.LoopError):
                loop.run_once(goal["id"], root=root)
            loop.set_enabled(True, root)
            with patch.object(loop, "_run_check", return_value={"check": "general_scope", "passed": True,
                                                                   "returncode": 0, "duration_seconds": 0.1, "output": "ok"}) as run:
                record = loop.run_once(goal["id"], root=root)
            run.assert_called_once_with("general_scope", 120)
            self.assertEqual("active", record["goal"]["status"])
            self.assertEqual("passed", record["goal"]["checks"][0]["status"])
            self.assertEqual("pending", record["goal"]["checks"][1]["status"])

    def test_failure_stops_for_review_and_redacts_audit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            goal = loop.create_goal("Sanitize evidence", "Check output without local paths.", ["agentic_eval"], root=root)
            loop.set_enabled(True, root)
            with patch.object(loop, "_run_check", return_value={"check": "agentic_eval", "passed": False,
                                                                   "returncode": 1, "duration_seconds": 0.1,
                                                                   "output": "A:\\Users\\private\\secret.txt token=abc"}):
                record = loop.run_once(goal["id"], root=root)
            self.assertEqual("needs_operator", record["goal"]["status"])
            self.assertNotIn("A:\\Users", record["result"]["output"])
            reviews = json.loads((root / "review_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(1, len(reviews))
            self.assertNotIn("A:\\Users", reviews[0]["evidence"])
            with self.assertRaises(loop.LoopError):
                loop.run_once(goal["id"], root=root)

    def test_goals_are_bounded_and_discovery_never_runs_commands(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaises(loop.LoopError):
                loop.create_goal("Bad", "Try arbitrary shell work", ["not_a_check"], root=root)
            result = loop.discover(root)
            self.assertIn("known_checks", result)
            self.assertTrue((root / "triage.jsonl").is_file())

    def test_completed_goal_cannot_repeat_and_budget_stops_resume(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            complete = loop.create_goal("One check", "Verify a single safe check.", ["agentic_eval"], root=root)
            loop.set_enabled(True, root)
            passed = {"check": "agentic_eval", "passed": True, "returncode": 0,
                      "duration_seconds": 0.1, "output": "ok"}
            with patch.object(loop, "_run_check", return_value=passed):
                result = loop.run_once(complete["id"], root=root)
            self.assertEqual("complete", result["goal"]["status"])
            with self.assertRaises(loop.LoopError):
                loop.run_once(complete["id"], root=root)

            budget = loop.create_goal("Budget", "Verify two safe checks.",
                                      ["agentic_eval", "operator_eval"], max_runs=1, root=root)
            with patch.object(loop, "_run_check", return_value=passed):
                loop.run_once(budget["id"], root=root)
            with self.assertRaises(loop.LoopError):
                loop.run_once(budget["id"], root=root)
            self.assertEqual("needs_operator", loop._read_goal(budget["id"], root)["status"])

    def test_goal_text_cannot_expand_the_fixed_execution_scope(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            goal = loop.create_goal("Try shell", "Run arbitrary stuff; delete files; use tools.",
                                    ["general_scope"], root=root)
            self.assertEqual(["general_scope"], [item["name"] for item in goal["checks"]])
            self.assertNotIn("delete files", json.dumps(goal["checks"]))

    def test_failed_goal_can_only_make_a_non_mutating_review_proposal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            target = Path(td) / "settings.ini"
            target.write_text("before=yes\n", encoding="utf-8")
            goal = loop.create_goal("Proposal", "Propose a repair after a failed check.", ["agentic_eval"], root=root)
            loop.set_enabled(True, root)
            failed = {"check": "agentic_eval", "passed": False, "returncode": 1,
                      "duration_seconds": 0.1, "output": "failed"}
            with patch.object(loop, "_run_check", return_value=failed):
                loop.run_once(goal["id"], root=root)
            proposal = loop.propose_repair(goal["id"], str(target), "after=yes\n", "agentic_eval", root=root)
            self.assertIn("-before=yes", proposal["diff"])
            self.assertIn("+after=yes", proposal["diff"])
            self.assertEqual("before=yes\n", target.read_text(encoding="utf-8"))
            self.assertTrue(proposal["requires_existing_file_edit_approval"])
            reviews = json.loads((root / "review_queue.json").read_text(encoding="utf-8"))
            self.assertNotIn("after=yes", json.dumps(reviews))

    def test_approved_repair_is_applied_elsewhere_then_rerun_once(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            target = Path(td) / "settings.ini"
            target.write_text("before=yes\n", encoding="utf-8")
            with patch.object(file_edit_gate, "STATE_FILE", root / "file_edit_gate.json"):
                goal = loop.create_goal("Repair", "Verify an exact repair.", ["agentic_eval"], root=root)
                loop.set_enabled(True, root)
                failed = {"check": "agentic_eval", "passed": False, "returncode": 1, "duration_seconds": 0.1, "output": "same failure"}
                with patch.object(loop, "_run_check", return_value=failed):
                    loop.run_once(goal["id"], root=root)
                proposal = loop.propose_repair(goal["id"], str(target), "after=yes\n", "agentic_eval", root=root)
                self.assertEqual("before=yes\n", target.read_text(encoding="utf-8"))
                request_id = proposal["file_edit_request"]["id"]
                file_edit_gate.decide(request_id, True)
                # This represents the separate, normal approved write path.
                target.write_text("after=yes\n", encoding="utf-8")
                passed = {"check": "agentic_eval", "passed": True, "returncode": 0, "duration_seconds": 0.1, "output": "ok"}
                with patch.object(loop, "_run_check", return_value=passed) as run:
                    record = loop.verify_approved_repair(goal["id"], root=root)
            run.assert_called_once_with("agentic_eval", 120)
            self.assertEqual("passed", record["repair"]["status"])
            self.assertEqual("complete", record["goal"]["status"])

    def test_two_identical_post_repair_failures_halt_retries(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "state"
            target = Path(td) / "settings.ini"
            target.write_text("before=yes\n", encoding="utf-8")
            with patch.object(file_edit_gate, "STATE_FILE", root / "file_edit_gate.json"):
                goal = loop.create_goal("Repair", "Stop repeated failures.", ["agentic_eval"], root=root)
                loop.set_enabled(True, root)
                failed = {"check": "agentic_eval", "passed": False, "returncode": 1, "duration_seconds": 0.1, "output": "same failure"}
                with patch.object(loop, "_run_check", return_value=failed):
                    loop.run_once(goal["id"], root=root)
                for content in ("after=one\n", "after=two\n"):
                    proposal = loop.propose_repair(goal["id"], str(target), content, "agentic_eval", root=root)
                    file_edit_gate.decide(proposal["file_edit_request"]["id"], True)
                    target.write_text(content, encoding="utf-8")
                    with patch.object(loop, "_run_check", return_value=failed):
                        record = loop.verify_approved_repair(goal["id"], root=root)
            self.assertEqual("halted_identical_failure", record["repair"]["status"])
            reviews = json.loads((root / "review_queue.json").read_text(encoding="utf-8"))
            self.assertTrue(any("repeated after two approved repairs" in item["reason"] for item in reviews))


if __name__ == "__main__":
    unittest.main(verbosity=2)
