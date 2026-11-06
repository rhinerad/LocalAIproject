#!/usr/bin/env python3
"""Stdlib regression checks for the private-safe H3 evaluation harness."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from h3_evaluation import evaluate


VALID = """subject_definitions:
<Picture 1>: a test reference.
summary:
A single test shot.
retention_analysis:
detailed_description:
[Shot 1] A person stands still.
overall_soundscape:
quiet room tone.
non_diegetic_music:
N/A
"""


class H3EvaluationTests(unittest.TestCase):
    def test_evaluation_is_aggregate_and_negative_controls_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "private_prompt_name.txt").write_text(VALID, encoding="utf-8")
            result = evaluate(directory)

        self.assertEqual(result["corpus_file_count"], 1)
        self.assertEqual(result["valid_count"], 1)
        self.assertEqual(result["invalid_count"], 0)
        self.assertTrue(result["synthetic_negative_controls_passed"])
        self.assertIn("E01", result["synthetic_negative_controls"]["prefixed_wrapper"])
        self.assertNotIn("private_prompt_name", str(result))
        self.assertNotIn("A person stands still", str(result))


if __name__ == "__main__":
    unittest.main(verbosity=2)
