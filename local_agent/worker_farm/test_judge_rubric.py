#!/usr/bin/env python3
"""Tests for judge_rubric.py -- pure functions, no broker/Celery needed.

Correct invocation -- from the repository root, farm venv only:

  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m unittest local_agent.worker_farm.test_judge_rubric -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))

from local_agent.worker_farm import judge_rubric


def _msgs(*pairs: tuple[str, str]) -> list[dict]:
    return [{"role": role, "content": content} for role, content in pairs]


class JudgeRubricTests(unittest.TestCase):
    def test_no_findings_on_a_clean_exchange(self):
        messages = _msgs(
            ("user", "what's the capital of France?"),
            ("assistant", "Paris."),
        )
        result = judge_rubric.summarize("chat1", messages)
        self.assertEqual(0, result["finding_count"])
        self.assertEqual("no_findings", result["status"])

    def test_unverified_completion_claim_detected(self):
        messages = _msgs(
            ("user", "fix the config file"),
            ("assistant", "I've fixed the config file and everything works now."),
        )
        result = judge_rubric.summarize("chat2", messages)
        rule_ids = {f["rule_id"] for f in result["findings"]}
        self.assertIn("unverified_completion_claim", rule_ids)
        self.assertEqual("review_required", result["status"])

    def test_ordinary_past_tense_is_not_a_false_positive(self):
        # "I have a question" / "I have read about this before" should not
        # trip the completion-claim detector -- it requires a completion verb.
        messages = _msgs(
            ("user", "tell me about wireguard"),
            ("assistant", "I have read about WireGuard before -- it's a VPN protocol."),
        )
        result = judge_rubric.summarize("chat3", messages)
        rule_ids = {f["rule_id"] for f in result["findings"]}
        self.assertNotIn("unverified_completion_claim", rule_ids)

    def test_work_dumped_on_operator_detected(self):
        messages = _msgs(
            ("user", "what's in the downloads folder?"),
            ("assistant", "You'll need to open the file explorer and check yourself."),
        )
        result = judge_rubric.summarize("chat4", messages)
        rule_ids = {f["rule_id"] for f in result["findings"]}
        self.assertIn("possible_work_dumped_on_operator", rule_ids)

    def test_direct_action_request_not_executed_detected(self):
        messages = _msgs(
            ("user", "read the todo file and tell me what's open"),
            ("assistant", "You should run 'cat TODO.md' in your terminal to see it."),
        )
        result = judge_rubric.summarize("chat5", messages)
        rule_ids = {f["rule_id"] for f in result["findings"]}
        self.assertIn("direct_action_request_not_executed", rule_ids)
        self.assertIn("possible_work_dumped_on_operator", rule_ids)

    def test_specialist_leak_detected_when_user_did_not_invoke_project(self):
        messages = _msgs(
            ("user", "what's a comfortable indoor temperature for sleeping?"),
            ("assistant", "That depends -- by the way, how is the ComfyUI render coming along?"),
        )
        result = judge_rubric.summarize("chat6", messages)
        rule_ids = {f["rule_id"] for f in result["findings"]}
        self.assertIn("specialist_project_leak", rule_ids)
        high = [f for f in result["findings"] if f["rule_id"] == "specialist_project_leak"]
        self.assertEqual("high", high[0]["severity"])

    def test_specialist_leak_not_flagged_when_user_asked_about_the_project(self):
        messages = _msgs(
            ("user", "can you check on the ComfyUI render status?"),
            ("assistant", "The ComfyUI render is still in progress."),
        )
        result = judge_rubric.summarize("chat7", messages)
        rule_ids = {f["rule_id"] for f in result["findings"]}
        self.assertNotIn("specialist_project_leak", rule_ids)

    def test_excerpt_is_bounded_and_whitespace_collapsed(self):
        long_text = "I've fixed it. " + ("word " * 100)
        messages = _msgs(("user", "fix it"), ("assistant", long_text))
        result = judge_rubric.summarize("chat8", messages)
        finding = next(f for f in result["findings"]
                       if f["rule_id"] == "unverified_completion_claim")
        self.assertLessEqual(len(finding["excerpt"]), judge_rubric.MAX_EXCERPT + 1)
        self.assertNotIn("\n", finding["excerpt"])

    def test_empty_messages_produce_no_findings(self):
        result = judge_rubric.summarize("chat9", [])
        self.assertEqual(0, result["finding_count"])
        self.assertEqual(0, result["message_count"])

    def test_by_rule_counts_match_findings(self):
        messages = _msgs(
            ("user", "fix the config"),
            ("assistant", "I've fixed the config. You'll need to restart it yourself though."),
        )
        result = judge_rubric.summarize("chat10", messages)
        total = sum(result["by_rule"].values())
        self.assertEqual(total, result["finding_count"])


if __name__ == "__main__":
    unittest.main()
