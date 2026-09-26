from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import quality_comparison as quality  # noqa: E402


class QualityComparisonTests(unittest.TestCase):
    def test_packet_is_fixed_and_benign(self) -> None:
        packet = quality.build_packet("candidate", "baseline")
        self.assertEqual(packet["status"], "prepared")
        self.assertEqual(len(packet["cases"]), 10)
        self.assertTrue(packet["case_set_sha256"])

    def test_incomplete_packet_is_refused(self) -> None:
        result = quality.validate_review(quality.build_packet("candidate", "baseline"), min_candidate_mean=1.5, max_baseline_gap=0.25)
        self.assertFalse(result["complete"])
        self.assertFalse(result["accepted"])

    def test_threshold_is_applied(self) -> None:
        packet = quality.build_packet("candidate", "baseline")
        for row in packet["cases"]:
            row.update({"baseline_response": "baseline", "candidate_response": "candidate", "baseline_score": 2, "candidate_score": 2})
        result = quality.validate_review(packet, min_candidate_mean=1.5, max_baseline_gap=0.25)
        self.assertTrue(result["complete"])
        self.assertTrue(result["accepted"])
        packet["cases"][0]["candidate_score"] = 0
        result = quality.validate_review(packet, min_candidate_mean=1.9, max_baseline_gap=0.25)
        self.assertFalse(result["accepted"])

    def test_capture_ollama_records_only_the_requested_slot(self) -> None:
        packet = quality.build_packet("candidate", "baseline")
        with mock.patch.object(quality, "_post_json", return_value={"response": "READY"}) as post:
            captured = quality.capture_packet(packet, endpoint="http://127.0.0.1:11434", endpoint_kind="ollama", model="baseline", slot="baseline")
        self.assertEqual(captured["status"], "captured")
        self.assertTrue(all(row["baseline_response"] == "READY" for row in captured["cases"]))
        self.assertTrue(all(row["candidate_response"] == "" for row in captured["cases"]))
        self.assertFalse(post.call_args.args[1]["think"])
        self.assertEqual(post.call_args.args[1]["options"]["num_predict"], 128)

    def test_evidence_writer_refuses_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.json"
            quality.write_json(path, {"first": True})
            with self.assertRaises(FileExistsError):
                quality.write_json(path, {"second": True})


if __name__ == "__main__":
    unittest.main()
