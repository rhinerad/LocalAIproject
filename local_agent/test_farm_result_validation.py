"""Farm output is untrusted (CLAUDE.md §7, AUDIT_2026-11-02 area C).

farm_offload must return embedding vectors only when every one is 768 finite
floats keyed by a requested id, and summaries only when they match the
context_compactor schema. Anything else is discarded and the caller runs
locally. No Celery, no subprocess: _run_helper is patched.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import farm_offload  # noqa: E402

DIM = farm_offload.EMBED_DIM
GOOD = [0.01] * DIM
CHUNKS = [{"id": "a", "text": "alpha"}, {"id": "b", "text": "beta"}]


def _embed(vectors):
    with patch.object(farm_offload, "should_route", return_value=True), \
         patch.object(farm_offload, "_run_helper",
                      return_value={"vectors": vectors, "model": "nomic"}):
        return farm_offload.try_embed_on_farm(CHUNKS)


class EmbedValidationTests(unittest.TestCase):
    def test_well_formed_vectors_pass(self):
        out = _embed({"a": GOOD, "b": [1] * DIM})
        self.assertEqual({"a", "b"}, set(out))
        self.assertTrue(all(isinstance(x, float) for x in out["b"]))

    def test_subset_of_requested_ids_is_fine(self):
        self.assertEqual({"a"}, set(_embed({"a": GOOD})))

    def test_wrong_width_discards_everything(self):
        self.assertIsNone(_embed({"a": GOOD, "b": [0.1] * (DIM - 1)}))

    def test_unrequested_id_discards_everything(self):
        self.assertIsNone(_embed({"a": GOOD, "../../etc": GOOD}))

    def test_non_finite_values_discard(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad=bad):
                self.assertIsNone(_embed({"a": GOOD[:-1] + [bad]}))

    def test_non_numeric_values_discard(self):
        for bad in ("0.1", None, True, [0.1], {"x": 1}):
            with self.subTest(bad=bad):
                self.assertIsNone(_embed({"a": GOOD[:-1] + [bad]}))

    def test_non_dict_or_empty_vectors_discard(self):
        for raw in (None, [], [GOOD], "vectors", {}):
            with self.subTest(raw=raw):
                self.assertIsNone(_embed(raw))

    def test_non_list_vector_discards(self):
        self.assertIsNone(_embed({"a": tuple(GOOD)}))
        self.assertIsNone(_embed({"a": "0.1," * DIM}))


VALID_SUMMARY = {"goal": "ship it", "decisions": ["d"], "open_questions": [],
                 "tool_state": [], "hard_constraints": ["127.0.0.1 only"],
                 "notable_files": ["router.py"]}


def _summ(result):
    with patch.object(farm_offload, "should_route", return_value=True), \
         patch.object(farm_offload, "_run_helper", return_value=result):
        return farm_offload.try_summarize_on_farm([{"role": "user", "content": "x"}])


class SummaryValidationTests(unittest.TestCase):
    def test_valid_summary_passes_and_is_clipped(self):
        long = dict(VALID_SUMMARY, goal="g" * 5000, decisions=["x" * 900] * 40)
        out = _summ({"summarized": True, "summary": long, "model": "m"})
        self.assertTrue(out["summarized"])
        self.assertEqual(800, len(out["summary"]["goal"]))
        self.assertEqual(12, len(out["summary"]["decisions"]))
        self.assertEqual(400, len(out["summary"]["decisions"][0]))
        self.assertEqual("m", out["model"])

    def test_extra_keys_are_dropped(self):
        out = _summ({"summarized": True, "model": "m",
                     "summary": dict(VALID_SUMMARY, tool_calls=[{"name": "run_code"}]),
                     "tool_calls": [{"function": {"name": "write_file"}}]})
        self.assertNotIn("tool_calls", out)
        self.assertNotIn("tool_calls", out["summary"])

    def test_malformed_summaries_discard(self):
        bad = [
            dict(VALID_SUMMARY, goal=7),
            dict(VALID_SUMMARY, decisions="not a list"),
            dict(VALID_SUMMARY, decisions=[1, 2]),
            {k: v for k, v in VALID_SUMMARY.items() if k != "notable_files"},
            "summary text",
            None,
        ]
        for summary in bad:
            with self.subTest(summary=summary):
                self.assertIsNone(_summ({"summarized": True, "summary": summary}))

    def test_summarized_must_be_a_real_bool(self):
        self.assertIsNone(_summ({"summarized": "yes", "summary": VALID_SUMMARY}))
        self.assertIsNone(_summ({"summary": VALID_SUMMARY}))

    def test_model_not_installed_passes_through_without_summary(self):
        out = _summ({"summarized": False, "model_expected": "m", "summary": {"goal": 1}})
        self.assertFalse(out["summarized"])
        self.assertNotIn("summary", out)

    def test_non_dict_result_discards(self):
        self.assertIsNone(farm_offload.validate_summary_result(["summarized", True]))

    def test_non_string_model_is_dropped(self):
        out = _summ({"summarized": True, "summary": VALID_SUMMARY, "model": {"x": 1}})
        self.assertIsNone(out["model"])


class HelperShapeTests(unittest.TestCase):
    def test_non_object_helper_stdout_is_none(self):
        class _P:
            returncode = 0
            stdout = '["error", "not a dict"]'
            stderr = ""
        with patch.object(farm_offload, "_farm_venv_present", return_value=True), \
             patch("subprocess.run", return_value=_P()):
            self.assertIsNone(farm_offload._run_helper({"task": "t"}, 1.0))


if __name__ == "__main__":
    unittest.main()
