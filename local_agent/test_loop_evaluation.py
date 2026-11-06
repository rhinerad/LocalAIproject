"""Regression checks for the loop golden-scenario contract and metrics."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import loop_evaluation
import loop_metrics


class LoopEvaluationTests(unittest.TestCase):
    def test_golden_scenario_contract_has_twenty_safe_cases(self):
        report = loop_evaluation.evaluate()
        self.assertTrue(report["ok"], report)
        self.assertGreaterEqual(report["total"], 20)
        self.assertEqual("none; deterministic controller contract only", report["model_calls"])

    def test_metrics_have_no_implied_model_or_completion_claim(self):
        with tempfile.TemporaryDirectory() as td:
            report = loop_metrics.report(Path(td))
        self.assertEqual(0, report["goals_total"])
        self.assertEqual("0 (controller does not call a model)", report["token_cost"])
        self.assertIn("not measurable", report["false_completion_rate"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
