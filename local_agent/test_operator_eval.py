"""Regression checks for explicit, anonymized evaluation cases."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import operator_eval


class OperatorEvalTests(unittest.TestCase):
    def _case(self):
        return {
            "title": "Tool choice for local documentation",
            "prompt": "What does the current project policy say about GPU routing?",
            "kind": "tool_choice",
            "acceptance": {"required_tools": ["search_docs"], "forbidden_tools": ["run_build"],
                           "must_contain": ["policy"]},
            "operator_notes": "Anonymized and approved for evaluation.",
        }

    def test_case_requires_anonymization_and_known_tools(self):
        bad = self._case()
        bad["prompt"] = "Read A:\\Users\\private\\secret.txt"
        with self.assertRaises(operator_eval.EvalCaseError):
            operator_eval.validate_case(bad, tool_names={"search_docs", "run_build"})
        bad = self._case()
        bad["acceptance"]["required_tools"] = ["not_a_tool"]
        with self.assertRaises(operator_eval.EvalCaseError):
            operator_eval.validate_case(bad, tool_names={"search_docs", "run_build"})

    def test_only_explicit_case_moves_from_pending_to_approved_and_scores(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            staged = operator_eval.stage(self._case(), root=root,
                                         tool_names={"search_docs", "run_build"})
            self.assertTrue((root / "pending" / f"{staged['id']}.json").is_file())
            approved = operator_eval.approve(staged["id"], root=root)
            self.assertEqual("approved", approved["status"])
            self.assertFalse((root / "pending" / f"{staged['id']}.json").exists())
            result = operator_eval.score(approved, answer="The policy is documented.",
                                         tools_called=["search_docs"])
            self.assertTrue(result["passed"])
            failed = operator_eval.score(approved, answer="No evidence.", tools_called=["run_build"])
            self.assertFalse(failed["passed"])
            self.assertEqual(["search_docs"], failed["missing_required_tools"])
            self.assertEqual(["run_build"], failed["forbidden_tools_called"])

    def test_score_does_not_import_or_call_judge(self):
        self.assertNotIn("judge_eval", operator_eval.score.__code__.co_names)

    def test_capture_run_persists_quality_without_judge_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            staged = operator_eval.stage(self._case(), root=root,
                                         tool_names={"search_docs", "run_build"})
            approved = operator_eval.approve(staged["id"], root=root)
            record = operator_eval.capture_run(
                approved, answer="The policy is documented.",
                tools_called=["search_docs"], quality_score=4, notes="manual",
                root=root)
            path = root / "results" / f"{record['run_id']}.json"
            self.assertTrue(path.is_file())
            self.assertEqual("operator-eval-result-v1", record["schema"])
            self.assertTrue(record["deterministic"]["passed"])
            self.assertEqual(4, record["operator"]["quality_score"])
            self.assertNotIn("judge", record)
            self.assertNotIn("judge_score", record)
            self.assertIs(True, record["deterministic"]["passed"])
            self.assertEqual(4, operator_eval.authoritative_score(record))
            with self.assertRaises(TypeError):
                operator_eval.capture_run(
                    approved, answer="The policy is documented.",
                    tools_called=["search_docs"], root=root, judge_score=5)

    def test_capture_run_omits_quality_until_operator_grades(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            staged = operator_eval.stage(self._case(), root=root,
                                         tool_names={"search_docs", "run_build"})
            approved = operator_eval.approve(staged["id"], root=root)
            record = operator_eval.capture_run(
                approved, answer="The policy is documented.",
                tools_called=["search_docs"], root=root)
            self.assertNotIn("quality_score", record["operator"])
            with self.assertRaises(operator_eval.EvalCaseError):
                operator_eval.authoritative_score(record)
            zero = operator_eval.capture_run(
                approved, answer="The policy is documented.",
                tools_called=["search_docs"], quality_score=0, root=root)
            self.assertEqual(0, zero["operator"]["quality_score"])

    def test_authoritative_score_rejects_verdict_and_ignores_nested_judge(self):
        result = {
            "schema": "operator-eval-result-v1",
            "operator": {"quality_score": 2, "notes": "", "scored_at": "t"},
            "judge": {"score": 5, "advisory": True},
        }
        self.assertEqual(2, operator_eval.authoritative_score(result))
        verdict = {
            "schema": "operator-eval-judge-verdict-v1",
            "score": 5,
            "advisory": True,
            "operator": {"quality_score": 5},
        }
        with self.assertRaises(TypeError):
            operator_eval.authoritative_score(verdict)
        farm = {
            "schema": "farm-judge-semantic-verdict-v1",
            "score": 4,
            "advisory": True,
            "auto_accepted": False,
            "operator": {"quality_score": 4},
        }
        with self.assertRaises(TypeError):
            operator_eval.authoritative_score(farm)
        with self.assertRaises(TypeError):
            operator_eval.authoritative_score(result, judge=verdict)  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()
