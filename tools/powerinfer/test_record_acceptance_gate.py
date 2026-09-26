from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("record_acceptance_gate", HERE / "record_acceptance_gate.py")
assert SPEC and SPEC.loader
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class RecordAcceptanceGateTests(unittest.TestCase):
    def test_checkpoint_chatml_uses_local_markers_not_inst(self) -> None:
        prompt, _history = gate._render_prompt([], "Find a file.", "checkpoint_chatml")
        self.assertEqual(prompt, "<|im_start|>user\nFind a file.<|im_end|>\n<|im_start|>assistant\n")
        self.assertNotIn("[INST]", prompt)

    def test_session_retains_reply_only_in_memory(self) -> None:
        response = {"content": "{\"tool_calls\":[]}", "total_s": 0.1, "ttft_s": 0.01}
        with mock.patch.object(gate, "_stream_completion", return_value=response.copy()) as completion:
            rows = gate._run_session("http://127.0.0.1:8080", ["one", "two"], 32, "checkpoint_chatml")
        self.assertNotIn("content", rows[0])
        self.assertIn('{"tool_calls":[]}', completion.call_args_list[1].args[1])
        self.assertEqual(completion.call_args_list[0].kwargs["stop"], ["<|im_end|>", "</s>", "<|im_start|>"])


if __name__ == "__main__":
    unittest.main()
