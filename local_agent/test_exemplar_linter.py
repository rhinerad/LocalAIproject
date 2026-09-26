#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import exemplar_filter
import prompt_normalizer


class ExemplarLinterTests(unittest.TestCase):
    def test_malformed_workflow_is_refused(self):
        report = exemplar_filter.check_candidate({"category": "comfyui_workflow", "content": "not json"})
        self.assertFalse(report["ok"])

    def test_duplicate_fingerprint_is_refused(self):
        content = "A person walks through a rainy city, turns toward camera, then enters a warm shop."
        report = exemplar_filter.check_candidate({"category": "video_prompt", "content": content},
                                                 {exemplar_filter.fingerprint(content)})
        self.assertFalse(report["ok"])

    def test_unstructured_prompt_becomes_valid_six_section_h3_scaffold(self):
        result = prompt_normalizer.normalize(
            "[0-5 s] A woman crosses a sunlit room and raises her hand toward the window.")
        self.assertTrue(result["valid_h3"], result["report"])
        self.assertIn("from 0 to 5 seconds", result["normalized"])
        self.assertNotIn("[0-5 s]", result["normalized"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
