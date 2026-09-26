"""Offline tests for the optional separate-model loop verifier."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import loop_independent_verifier as verifier


class IndependentVerifierTests(unittest.TestCase):
    def _packet(self):
        return {
            "goal": {"id": "loop_12345678", "title": "Check", "objective": "Verify one test."},
            "repair": {"target_check": "agentic_eval", "diff_sha256": "a" * 64},
            "test_result": {"check": "agentic_eval", "passed": True, "returncode": 0, "output": "ok"},
            "deterministic_evidence": [{"kind": "result_predicate", "passed": True}],
        }

    def test_disabled_review_never_calls_a_model(self):
        def fail(**_):
            raise AssertionError("model must not be called without explicit opt-in")
        result = verifier.review(**self._packet(), chat_fn=fail)
        self.assertEqual("needs_operator", result["verdict"])

    def test_cpu_only_structured_review_and_agreement(self):
        calls = []
        def fake_chat(*args, **kwargs):
            calls.append((args, kwargs))
            return json.dumps({"verdict": "supported", "evidence_ids": ["result_predicate"], "reason": "The targeted test passed."}), []
        result = verifier.review(**self._packet(), allow_model_call=True, chat_fn=fake_chat)
        self.assertEqual("supported", result["verdict"])
        self.assertEqual(verifier.router.CPU_HOST, calls[0][1]["host"])
        self.assertEqual(0, calls[0][1]["options"]["num_gpu"])
        self.assertEqual("0", calls[0][1]["keep_alive"])
        self.assertTrue(verifier.agreement(deterministic_passed=True, independent=result)["completion_allowed"])

    def test_invalid_or_unavailable_review_cannot_complete(self):
        result = verifier.review(**self._packet(), allow_model_call=True,
            chat_fn=lambda *a, **k: ("not json", []))
        self.assertEqual("needs_operator", result["verdict"])
        self.assertFalse(verifier.agreement(deterministic_passed=True, independent=result)["completion_allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
