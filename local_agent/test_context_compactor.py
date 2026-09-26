#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import context_compactor


class ContextCompactorTests(unittest.TestCase):
    def test_returns_none_without_exact_local_model(self):
        with patch.object(context_compactor, "_installed", return_value=False):
            self.assertIsNone(context_compactor.summarize_old_messages([
                {"role": "user", "content": "hello"}]))

    def test_uses_cpu_model_and_validates_json_shape(self):
        expected = {"goal": "fix tests", "decisions": ["use CPU"],
                    "open_questions": [], "tool_state": ["tests pending"],
                    "hard_constraints": ["no GPU"], "notable_files": ["agent.py"]}
        seen = {}
        def fake_chat(_messages, **kwargs):
            seen.update(kwargs)
            return json.dumps(expected), []
        with patch.object(context_compactor, "_installed", return_value=True), \
             patch.object(context_compactor.oll, "chat", fake_chat):
            actual = context_compactor.summarize_old_messages([
                {"role": "user", "content": "Please fix tests"}])
        self.assertEqual(actual, expected)
        self.assertEqual(seen["model"], "llama3.1:8b")
        self.assertEqual(seen["host"], context_compactor.router.CPU_HOST)
        self.assertEqual(seen["keep_alive"], "0")
        self.assertEqual(seen["options"]["num_gpu"], 0)

    def test_invalid_model_json_is_refused(self):
        with patch.object(context_compactor, "_installed", return_value=True), \
             patch.object(context_compactor.oll, "chat", return_value=("[]", [])):
            self.assertIsNone(context_compactor.summarize_old_messages([
                {"role": "user", "content": "x"}]))

    def test_model_and_host_and_timeout_overrides_are_honored(self):
        # A worker-farm machine with a different local model (e.g.
        # mac_worker's Mistral Nemo abliterated build, recorded 2026-09-02)
        # must be able to use its own model/host/timeout instead of the
        # workstation's fixed llama3.1:8b default -- see
        # worker_farm/tasks.py::_summarize_messages.
        expected = {"goal": "g", "decisions": [], "open_questions": [],
                    "tool_state": [], "hard_constraints": [], "notable_files": []}
        seen = {}
        checked_model = {}

        def fake_installed(model=context_compactor.MODEL, host=None):
            checked_model["model"] = model
            checked_model["host"] = host
            return True

        def fake_chat(_messages, **kwargs):
            seen.update(kwargs)
            return json.dumps(expected), []

        with patch.object(context_compactor, "_installed", fake_installed), \
             patch.object(context_compactor.oll, "chat", fake_chat):
            actual = context_compactor.summarize_old_messages(
                [{"role": "user", "content": "hi"}],
                model="krith/mistral-nemo-instruct-2407-abliterated:IQ3_XS",
                host="10.90.90.2:11434", timeout=120)

        self.assertEqual(actual, expected)
        self.assertEqual(checked_model["model"],
                         "krith/mistral-nemo-instruct-2407-abliterated:IQ3_XS")
        self.assertEqual(checked_model["host"], "10.90.90.2:11434")
        self.assertEqual(seen["model"], "krith/mistral-nemo-instruct-2407-abliterated:IQ3_XS")
        self.assertEqual(seen["host"], "10.90.90.2:11434")
        self.assertEqual(seen["timeout"], 120)

    def test_default_call_unchanged_for_existing_workstation_callers(self):
        # No model/host/timeout args supplied -> must behave exactly as
        # before this override was added (regression guard).
        import inspect
        sig = inspect.signature(context_compactor.summarize_old_messages)
        self.assertEqual(sig.parameters["model"].default, context_compactor.MODEL)
        self.assertIsNone(sig.parameters["host"].default)
        self.assertEqual(sig.parameters["timeout"].default, 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
