#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import workspace_evaluation


class WorkspaceEvaluationTests(unittest.TestCase):
    def test_baseline_has_no_false_specialist_or_project_tool_exposure(self):
        report = workspace_evaluation.evaluate()
        self.assertEqual(report["total_cases"], report["scope_passed"])
        self.assertEqual(report["total_cases"], report["tool_scope_passed"])
        self.assertEqual(0, report["false_specialist_activations"])
        self.assertEqual(0, report["false_project_tool_exposures"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
