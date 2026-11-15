"""chat_id must be a safe file stem before any sidecar path is built.

Audit 2026-11-02 #19: the Celery envelope's chat_id became
runtime/judge_semantic/verdicts/<chat_id>.json with no validation, so a
secondary node could write outside that directory. Also covers #7 of the
farm fix list: submit_judge_batch writes its ledger atomically.

Correct invocation -- from the repository root:

  python -m pytest -p no:cacheprovider -q local_agent/worker_farm/test_semantic_judge_paths.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
for entry in (str(REPO), str(HERE.parent)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from local_agent.worker_farm import semantic_judge, submit_judge_batch  # noqa: E402
import ollama_client as oll  # noqa: E402
import operator_eval  # noqa: E402

GOOD_IDS = ("abc", "chat_2026-11-02", "A-Z_09", "x" * 64)
BAD_IDS = (
    "", ".", "..", "../escape", "a/b", "a\\b", "x.json", "x" * 65,
    "../../../../etc/passwd", "chat id", "chat\n", "C:\\win", None,
)


class ChatIdValidationTests(unittest.TestCase):
    def test_accepts_safe_stems(self):
        for value in GOOD_IDS:
            with self.subTest(value=value):
                self.assertEqual(value, semantic_judge.validate_chat_id(value))

    def test_rejects_traversal_and_other_shapes(self):
        for value in BAD_IDS:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    semantic_judge.validate_chat_id(value)

    def test_regex_is_the_audited_one(self):
        self.assertEqual(r"[A-Za-z0-9_-]{1,64}", semantic_judge.CHAT_ID_RE.pattern)


class SidecarPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_verdict_path_stays_inside_verdicts_dir(self):
        verdicts = semantic_judge._layout(self.root)["verdicts"].resolve()
        path = semantic_judge._verdict_path(self.root, "chat-1").resolve()
        self.assertEqual(verdicts, path.parent)
        for bad in ("../escape", "a/b", "..", "x.json"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    semantic_judge._verdict_path(self.root, bad)

    def test_judge_chat_rejects_bad_chat_id_before_any_model_call(self):
        envelope = {"chat_id": "../../escape", "messages": [{"role": "user", "content": "hi"}],
                    "mechanical": {"status": "ok"}}
        with patch.object(oll, "chat", side_effect=AssertionError("model must not run")), \
             patch.object(semantic_judge, "calls_allowed", return_value=True):
            with self.assertRaises(ValueError):
                semantic_judge.judge_chat(envelope, root=self.root)
        self.assertFalse(list(self.root.rglob("*.json")), "nothing written outside or inside")

    def test_judge_chat_still_needs_messages_list(self):
        with patch.object(semantic_judge, "calls_allowed", return_value=True):
            with self.assertRaises(ValueError):
                semantic_judge.judge_chat({"chat_id": "ok", "messages": "no",
                                           "mechanical": {"status": "ok"}}, root=self.root)

    def test_load_paired_verdict_returns_none_for_bad_id(self):
        self.assertIsNone(semantic_judge.load_paired_verdict(self.root, "../x"))
        self.assertIsNone(semantic_judge.load_paired_verdict(self.root, ""))

    def test_record_operator_grade_refuses_bad_id_as_eval_case_error(self):
        with self.assertRaises(operator_eval.EvalCaseError):
            semantic_judge.record_operator_grade("../x", 3, root=self.root)
        with self.assertRaises(operator_eval.EvalCaseError):
            semantic_judge.record_operator_grade("missing_but_valid", 3, root=self.root)

    def test_mechanical_task_validates_chat_id_with_the_same_helper(self):
        source = (HERE / "tasks.py").read_text(encoding="utf-8")
        start = source.index("def judge_transcript(")
        end = source.index("def judge_transcript_semantic(")
        body = source[start:end]
        self.assertIn('semantic_judge.validate_chat_id(envelope.get("chat_id"))', body)
        self.assertNotIn('chat_id = str(envelope.get("chat_id") or "")', body)


class LedgerAtomicWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "runtime" / "judge_ledger.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_ledger_is_written_through_atomic_write_json(self):
        with patch.object(submit_judge_batch, "LEDGER_PATH", self.ledger), \
             patch.object(submit_judge_batch, "atomic_write_json",
                          wraps=submit_judge_batch.atomic_write_json) as atomic:
            submit_judge_batch._save_ledger({"chat-1": {"updated": 1, "task_id": "t"}})
        atomic.assert_called_once()
        self.assertEqual(self.ledger, Path(atomic.call_args.args[0]))
        self.assertEqual({"chat-1": {"updated": 1, "task_id": "t"}},
                         json.loads(self.ledger.read_text(encoding="utf-8")))
        leftovers = [p for p in self.ledger.parent.iterdir() if p != self.ledger]
        self.assertEqual([], leftovers, "no temp file left behind")

    def test_round_trip_through_load(self):
        with patch.object(submit_judge_batch, "LEDGER_PATH", self.ledger):
            submit_judge_batch._save_ledger({"a": {"updated": 2, "task_id": "x"}})
            self.assertEqual({"a": {"updated": 2, "task_id": "x"}},
                             submit_judge_batch._load_ledger())

    def test_source_no_longer_uses_write_text_for_the_ledger(self):
        source = (HERE / "submit_judge_batch.py").read_text(encoding="utf-8")
        self.assertNotIn("LEDGER_PATH.write_text", source)
        self.assertIn("from atomic_io import atomic_write_json", source)


if __name__ == "__main__":
    unittest.main()
