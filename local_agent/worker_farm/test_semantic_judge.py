"""Advisory farm semantic judge: isolation lock and synthetic-fixture safeguards.

Correct invocation — from the repository root, farm venv only:

  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m unittest local_agent.worker_farm.test_semantic_judge -v

No live Ollama call and no real chat files.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE.parent))

from local_agent.worker_farm import judge_rubric, semantic_judge
import ollama_client as oll
import operator_eval

_FORBIDDEN_RE = re.compile(
    r"semantic_judge|judge_transcript_semantic|farm-judge-semantic-verdict"
)
ISOLATION_FILES = [
    HERE.parent / "learning.py",
    HERE.parent / "exemplar_embeddings.py",
    HERE / "judge_rubric.py",
    REPO / "tools" / "powerinfer" / "quality_comparison.py",
]


def forbidden_hits(paths: list[Path]) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for index, line in enumerate(text.splitlines(), 1):
            if _FORBIDDEN_RE.search(line):
                hits.append((path.name, index, line.strip()))
    return hits


def _msgs(*pairs: tuple[str, str]) -> list[dict]:
    return [{"role": role, "content": content} for role, content in pairs]


class SemanticJudgeTests(unittest.TestCase):
    def _synthetic(self) -> tuple[str, list[dict], dict]:
        messages = _msgs(
            ("user", "what is 2+2?"),
            ("assistant", "Four. I did not write any files."),
        )
        mechanical = judge_rubric.summarize("synth_clean", messages)
        return "synth_clean", messages, mechanical

    def _envelope(self, root_unused=None) -> dict:
        chat_id, messages, mechanical = self._synthetic()
        return {
            "chat_id": chat_id,
            "messages": messages,
            "mechanical": mechanical,
            "mechanical_task_id": "task-synthetic",
        }

    def _enable(self, root: Path) -> None:
        semantic_judge.judge_enable(root)

    def _allow(self, root: Path):
        return patch.multiple(
            semantic_judge,
            _installed=lambda *a, **k: True,
            _busy_skip=lambda *a, **k: False,
        )

    def test_isolation_locked_modules_do_not_import_semantic_judge(self):
        self.assertEqual([], forbidden_hits(ISOLATION_FILES))

    def test_isolation_lock_fails_on_deliberate_bad_import(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "learning.py"
            bad.write_text("import hashlib\nimport semantic_judge\n", encoding="utf-8")
            hits = forbidden_hits([bad])
            self.assertTrue(hits, "lock must detect a deliberate semantic_judge import")
            self.assertTrue(any("semantic_judge" in line for _, _, line in hits))
        self.assertEqual([], forbidden_hits(ISOLATION_FILES))

    def test_authoritative_score_rejects_farm_verdict(self):
        verdict = {
            "schema": semantic_judge.VERDICT_SCHEMA,
            "advisory": True,
            "auto_accepted": False,
            "score": 5,
            "operator": {"quality_score": 5},
        }
        with self.assertRaises(TypeError):
            operator_eval.authoritative_score(verdict)

    def test_default_control_is_off_and_skips_ollama(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self._allow(root), patch.object(semantic_judge.oll, "chat") as chat:
                skipped = semantic_judge.judge_chat(self._envelope(), root=root)
            self.assertIsNone(skipped)
            chat.assert_not_called()
            self.assertEqual("off", semantic_judge.load_control(root)["status"])
            self.assertFalse(any(root.rglob("*.json")))

    def test_kill_switch_skips_even_when_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._enable(root)
            with patch.dict(os.environ, {semantic_judge.KILL_SWITCH: "0"}), \
                 self._allow(root), \
                 patch.object(semantic_judge.oll, "chat") as chat:
                skipped = semantic_judge.judge_chat(self._envelope(), root=root)
            self.assertIsNone(skipped)
            chat.assert_not_called()

    def test_busy_skip_when_non_qwythos_resident(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._enable(root)
            with patch.object(semantic_judge, "_installed", return_value=True), \
                 patch.object(semantic_judge.router, "_running_models",
                              return_value=["mistral-nemo:latest"]), \
                 patch.object(semantic_judge.oll, "chat") as chat:
                skipped = semantic_judge.judge_chat(self._envelope(), root=root)
            self.assertIsNone(skipped)
            chat.assert_not_called()

    def test_judge_writes_sidecar_not_mechanical_status_or_chats(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chats = root / "chats"
            chats.mkdir()
            chat_file = chats / "synth_clean.json"
            chat_file.write_text("{}", encoding="utf-8")
            self._enable(root)
            envelope = self._envelope()
            mechanical = dict(envelope["mechanical"])

            def fake_chat(*_a, **kwargs):
                self.assertEqual("30m", kwargs.get("keep_alive"))
                self.assertEqual(0, kwargs["options"]["num_gpu"])
                self.assertEqual(4, kwargs["options"]["num_thread"])
                self.assertEqual(8192, kwargs["options"]["num_ctx"])
                self.assertEqual(0, kwargs["options"]["temperature"])
                self.assertEqual("127.0.0.1:11434", kwargs.get("host"))
                self.assertIn("qwythos", str(kwargs.get("model")).lower())
                body = json.dumps({
                    "score": 2,
                    "flags": ["plausible_wrong_answer", "not_a_flag", "bad_reasoning"],
                    "reasoning": "Fluent but the arithmetic does not follow.",
                })
                return oll.ChatResult(body, [], {"eval_count": 4})

            with self._allow(root), \
                 patch.object(semantic_judge.oll, "chat", side_effect=fake_chat):
                verdict = semantic_judge.judge_chat(envelope, root=root)
            self.assertIsNotNone(verdict)
            self.assertTrue(verdict["advisory"])
            self.assertFalse(verdict["auto_accepted"])
            self.assertEqual(semantic_judge.VERDICT_SCHEMA, verdict["schema"])
            self.assertEqual(2, verdict["score"])
            self.assertEqual(["plausible_wrong_answer", "bad_reasoning"], verdict["flags"])
            self.assertEqual(mechanical["status"], verdict["mechanical_status"])
            self.assertEqual(mechanical, envelope["mechanical"])
            sidecar = json.loads(
                (root / "judge_semantic" / "synth_clean.json").read_text(encoding="utf-8"))
            self.assertTrue(sidecar["advisory"])
            self.assertFalse(sidecar["auto_accepted"])
            self.assertEqual("{}", chat_file.read_text(encoding="utf-8"))
            self.assertFalse((root / "learning.json").exists())

    def test_parse_failure_omits_score(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._enable(root)
            with self._allow(root), \
                 patch.object(semantic_judge.oll, "chat",
                              return_value=oll.ChatResult("not-json", [], {})):
                verdict = semantic_judge.judge_chat(self._envelope(), root=root)
            self.assertFalse(verdict["parse_ok"])
            self.assertNotIn("score", verdict)

    def test_mechanical_result_unchanged_when_semantic_followup_fails(self):
        chat_id, messages, mechanical = self._synthetic()
        envelope = {"chat_id": chat_id, "messages": messages}
        snapshot = json.dumps(mechanical, sort_keys=True)

        def boom(_payload):
            raise RuntimeError("broker down")

        with patch.object(semantic_judge, "calls_allowed", return_value=True):
            queued = semantic_judge.try_enqueue_followup(
                boom, envelope, mechanical, "task-x")
        self.assertFalse(queued)
        self.assertEqual(snapshot, json.dumps(mechanical, sort_keys=True))
        self.assertEqual("no_findings", mechanical["status"])

    def test_breaker_trips_and_reenable_requires_ack_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._enable(root)
            for index in range(12):
                chat_id = f"synth_{index}"
                messages = _msgs(("user", "n"), ("assistant", "ok"))
                mechanical = judge_rubric.summarize(chat_id, messages)
                sidecar = {
                    "schema": semantic_judge.VERDICT_SCHEMA,
                    "advisory": True,
                    "auto_accepted": False,
                    "chat_id": chat_id,
                    "mechanical_task_id": f"t{index}",
                    "mechanical_status": mechanical["status"],
                    "judged_at": "2026-09-05T18:00:00Z",
                    "judge_model": "qwythos",
                    "judge_host": "127.0.0.1:11434",
                    "judge_prompt_sha256": semantic_judge.prompt_version(),
                    "parse_ok": True,
                    "score": 0,
                    "flags": [],
                    "reasoning": "test",
                    "telemetry": {},
                    "operator_quality_score": 5,
                }
                semantic_judge._write_verdict(root, sidecar)
            report = semantic_judge.write_report(root)
            self.assertEqual(12, report["n_paired"])
            self.assertEqual("disabled", report["breaker"]["status"])
            self.assertEqual("disabled", semantic_judge.load_control(root)["status"])
            with self._allow(root), patch.object(semantic_judge.oll, "chat") as chat:
                skipped = semantic_judge.judge_chat(self._envelope(), root=root)
            self.assertIsNone(skipped)
            chat.assert_not_called()
            with self.assertRaises(operator_eval.EvalCaseError):
                semantic_judge.judge_enable(root)
            ack = root / report["report_path"]
            enabled = semantic_judge.judge_enable(root, ack_report=ack)
            self.assertEqual("untrusted", enabled["status"])

    def test_reuses_judge_eval_kill_switch_and_spearman(self):
        self.assertEqual(semantic_judge.KILL_SWITCH, "LOCAL_AGENT_LLM_JUDGE")
        self.assertAlmostEqual(1.0, semantic_judge.judge_eval.spearman_rho(
            [1, 2, 3, 4, 5], [1, 2, 3, 4, 5]))
        for flag in ("bad_reasoning", "weak_inference_on_vague_request",
                     "plausible_wrong_answer", "weak_grounding",
                     "unverified_completion_claim"):
            self.assertIn(flag, semantic_judge.FLAGS)


if __name__ == "__main__":
    unittest.main()
