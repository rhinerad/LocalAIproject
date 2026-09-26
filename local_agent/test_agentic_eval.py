#!/usr/bin/env python3
"""Smoke test for the repeatable agentic harness baseline."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agentic_eval


class AgenticEvalTests(unittest.TestCase):
    def test_baseline_is_fully_green(self):
        report = agentic_eval.evaluate()
        self.assertEqual(report["total"], report["passed"], report)
        self.assertEqual("mocked; no model loaded", report["model_calls"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
