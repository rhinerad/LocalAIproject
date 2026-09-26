"""CPU judge sidecar, circuit breaker, and type-isolation lock."""
from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

import judge_eval
import ollama_client as oll
import operator_eval

_FORBIDDEN_RE = re.compile(r"\bjudge_eval\b|operator-eval-judge-verdict")
ISOLATION_FILES = [
    HERE / "learning.py",
    HERE / "exemplar_embeddings.py",
    HERE / "worker_farm" / "judge_rubric.py",
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


class JudgeEvalTests(unittest.TestCase):
    def _case(self):
        return {
            "title": "Tool choice for local documentation",
            "prompt": "What does the current project policy say about GPU routing?",
            "kind": "tool_choice",
            "acceptance": {"required_tools": ["search_docs"], "forbidden_tools": ["run_build"],
                           "must_contain": ["policy"]},
            "operator_notes": "Anonymized and approved for evaluation.",
        }

    def _approve(self, root: Path) -> dict:
        staged = operator_eval.stage(self._case(), root=root,
                                     tool_names={"search_docs", "run_build"})
        return operator_eval.approve(staged["id"], root=root)

    def _enable(self, root: Path) -> None:
        judge_eval.judge_enable(root)

    def _verdict_file(self, root: Path, run_id: str, case_id: str, score: int,
                      *, parse_ok: bool = True) -> None:
        payload = {
            "schema": judge_eval.VERDICT_SCHEMA,
            "advisory": True,
            "auto_accepted": False,
            "case_id": case_id,
            "run_id": run_id,
            "judged_at": "2026-09-05T18:00:00Z",
            "judge_model": "llama3.1:8b",
            "judge_host": "127.0.0.1:11435",
            "judge_prompt_sha256": judge_eval.prompt_version(),
            "parse_ok": parse_ok,
            "flags": [],
            "reasoning": "test",
            "telemetry": {},
        }
        if parse_ok:
            payload["score"] = score
        (root / "judge").mkdir(parents=True, exist_ok=True)
        (root / "judge" / f"{run_id}.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def test_isolation_locked_modules_do_not_import_judge(self):
        self.assertEqual([], forbidden_hits(ISOLATION_FILES))

    def test_isolation_lock_fails_on_deliberate_bad_import(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "learning.py"
            bad.write_text("import hashlib\nimport judge_eval\n", encoding="utf-8")
            hits = forbidden_hits([bad])
            self.assertTrue(hits, "lock must detect a deliberate judge_eval import")
            self.assertTrue(any("judge_eval" in line for _, _, line in hits))
        self.assertEqual([], forbidden_hits(ISOLATION_FILES))

    def test_spearman_known_values(self):
        self.assertAlmostEqual(1.0, judge_eval.spearman_rho([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]))
        self.assertAlmostEqual(-1.0, judge_eval.spearman_rho([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]))
        self.assertIsNone(judge_eval.spearman_rho([1, 1, 1], [2, 2, 2]))

    def test_default_control_is_off_and_skips_ollama(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case = self._approve(root)
            captured = operator_eval.capture_run(
                case, answer="The policy is documented.",
                tools_called=["search_docs"], quality_score=4, root=root)
            with patch.object(judge_eval, "_installed", return_value=True), \
                 patch.object(judge_eval.router, "chat_busy", return_value=False), \
                 patch.object(judge_eval.oll, "chat") as chat:
                skipped = judge_eval.judge_case(captured, case, root=root)
            self.assertIsNone(skipped)
            chat.assert_not_called()
            self.assertEqual("off", judge_eval.load_control(root)["status"])

    def test_kill_switch_skips_even_when_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case = self._approve(root)
            self._enable(root)
            captured = operator_eval.capture_run(
                case, answer="The policy is documented.",
                tools_called=["search_docs"], quality_score=4, root=root)
            with patch.dict(os.environ, {"LOCAL_AGENT_LLM_JUDGE": "0"}), \
                 patch.object(judge_eval, "_installed", return_value=True), \
                 patch.object(judge_eval.router, "chat_busy", return_value=False), \
                 patch.object(judge_eval.oll, "chat") as chat:
                skipped = judge_eval.judge_case(captured, case, root=root)
            self.assertIsNone(skipped)
            chat.assert_not_called()

    def test_busy_skip_matches_memory_extractor(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case = self._approve(root)
            self._enable(root)
            captured = operator_eval.capture_run(
                case, answer="The policy is documented.",
                tools_called=["search_docs"], quality_score=4, root=root)
            with patch.object(judge_eval, "_installed", return_value=True), \
                 patch.object(judge_eval.router, "chat_busy", return_value=True), \
                 patch.object(judge_eval.oll, "chat") as chat:
                skipped = judge_eval.judge_case(captured, case, root=root)
            self.assertIsNone(skipped)
            chat.assert_not_called()

    def test_judge_writes_sidecar_not_operator_fields(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case = self._approve(root)
            self._enable(root)
            captured = operator_eval.capture_run(
                case, answer="The policy is documented.",
                tools_called=["search_docs"], quality_score=2, root=root)

            def fake_chat(*_a, **kwargs):
                self.assertEqual("0", kwargs.get("keep_alive"))
                self.assertEqual(0, kwargs["options"]["num_gpu"])
                self.assertIs(kwargs.get("tools"), None)
                self.assertEqual(kwargs.get("host"), judge_eval.router.CPU_HOST)
                body = json.dumps({
                    "score": 5,
                    "flags": ["weak_grounding", "not_a_flag"],
                    "reasoning": "Looks strong.",
                })
                return oll.ChatResult(body, [], {"eval_count": 9})

            with patch.object(judge_eval, "_installed", return_value=True), \
                 patch.object(judge_eval.router, "chat_busy", return_value=False), \
                 patch.object(judge_eval.oll, "chat", side_effect=fake_chat):
                verdict = judge_eval.judge_case(captured, case, root=root)
            self.assertIsNotNone(verdict)
            self.assertTrue(verdict["advisory"])
            self.assertFalse(verdict["auto_accepted"])
            self.assertEqual(5, verdict["score"])
            self.assertEqual(["weak_grounding"], verdict["flags"])
            reloaded = operator_eval.load_result(captured["run_id"], root=root)
            self.assertEqual(2, reloaded["operator"]["quality_score"])
            self.assertTrue(reloaded["deterministic"]["passed"])
            self.assertNotIn("judge", reloaded)
            self.assertEqual(2, operator_eval.authoritative_score(reloaded))
            self.assertNotEqual(verdict["score"], reloaded["operator"]["quality_score"])

    def test_parse_failure_omits_score_and_is_dropped_from_correlation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            case = self._approve(root)
            self._enable(root)
            captured = operator_eval.capture_run(
                case, answer="The policy is documented.",
                tools_called=["search_docs"], quality_score=4, root=root)
            with patch.object(judge_eval, "_installed", return_value=True), \
                 patch.object(judge_eval.router, "chat_busy", return_value=False), \
                 patch.object(judge_eval.oll, "chat",
                              return_value=oll.ChatResult("not-json", [], {})):
                verdict = judge_eval.judge_case(captured, case, root=root)
            self.assertFalse(verdict["parse_ok"])
            self.assertNotIn("score", verdict)
            report = judge_eval.write_report(root)
            self.assertEqual(0, report["n_paired"])

    def test_breaker_trips_and_reenable_requires_ack_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            operator_eval._dirs(root)
            self._enable(root)
            for index in range(12):
                case = dict(self._case())
                case["title"] = f"Case {index} policy"
                staged = operator_eval.stage(case, root=root,
                                             tool_names={"search_docs", "run_build"})
                approved = operator_eval.approve(staged["id"], root=root)
                captured = operator_eval.capture_run(
                    approved, answer="The policy is documented.",
                    tools_called=["search_docs"], quality_score=5, root=root)
                self._verdict_file(root, captured["run_id"], approved["id"], 0)
            report = judge_eval.write_report(root)
            self.assertEqual(12, report["n_paired"])
            self.assertEqual("disabled", report["breaker"]["status"])
            self.assertEqual("disabled", judge_eval.load_control(root)["status"])
            with patch.object(judge_eval, "_installed", return_value=True), \
                 patch.object(judge_eval.router, "chat_busy", return_value=False), \
                 patch.object(judge_eval.oll, "chat") as chat:
                skipped = judge_eval.judge_case(
                    operator_eval.load_result(captured["run_id"], root=root),
                    approved, root=root)
            self.assertIsNone(skipped)
            chat.assert_not_called()
            with self.assertRaises(operator_eval.EvalCaseError):
                judge_eval.judge_enable(root)
            ack = root / report["report_path"]
            enabled = judge_eval.judge_enable(root, ack_report=ack)
            self.assertEqual("untrusted", enabled["status"])
            self.assertIsNone(enabled["disabled_reason"])

    def test_breaker_does_not_calibrate_below_min_paired(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._enable(root)
            case = self._approve(root)
            captured = operator_eval.capture_run(
                case, answer="The policy is documented.",
                tools_called=["search_docs"], quality_score=4, root=root)
            self._verdict_file(root, captured["run_id"], case["id"], 4)
            report = judge_eval.write_report(root)
            self.assertEqual(1, report["n_paired"])
            self.assertEqual("untrusted", report["breaker"]["status"])

    def test_calibrated_when_thresholds_met(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._enable(root)
            for index in range(12):
                case = dict(self._case())
                case["title"] = f"Aligned {index} policy"
                staged = operator_eval.stage(case, root=root,
                                             tool_names={"search_docs", "run_build"})
                approved = operator_eval.approve(staged["id"], root=root)
                score = 2 + (index % 4)
                captured = operator_eval.capture_run(
                    approved, answer="The policy is documented.",
                    tools_called=["search_docs"], quality_score=score, root=root)
                self._verdict_file(root, captured["run_id"], approved["id"], score)
            report = judge_eval.write_report(root)
            self.assertEqual(12, report["n_paired"])
            self.assertEqual("calibrated", report["breaker"]["status"])
            self.assertLessEqual(report["mean_abs_error"], 1.5)


if __name__ == "__main__":
    unittest.main()
