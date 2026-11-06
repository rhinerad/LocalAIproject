from __future__ import annotations

import sys
import tempfile
import unittest
import json
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import turbosparse_agentic_quality_gate as gate  # noqa: E402


class TurboSparseAgenticGateTests(unittest.TestCase):
    def contract(self) -> dict:
        return {"schema": "turbosparse-prompt-contract-v1", "status": "verified_local_contract", "chat_template_sha256": "a" * 64}

    def test_packet_uses_checkpoint_chatml_and_strict_expected_calls(self) -> None:
        packet = gate.packet(self.contract())
        self.assertIn("<|im_start|>system", packet["turns"][0]["prompt"])
        self.assertEqual(packet["turns"][0]["expected"], gate.EXPECTED_ONE)
        self.assertEqual(packet["turns"][1]["expected"], gate.EXPECTED_TWO)

    def test_capture_passes_two_grounded_turns(self) -> None:
        responses = [
            '{"tool_calls":[{"name":"search_files","arguments":{"path":".","query":"*.py"}}]}',
            '{"tool_calls":[{"name":"read_file","arguments":{"path":"A:\\\\workspace\\\\local_agent\\\\agent.py","max_lines":80}}]}',
        ]
        with mock.patch.object(gate, "completion", side_effect=responses) as completion:
            result = gate.capture(gate.packet(self.contract()), "http://127.0.0.1:8080")
        self.assertEqual(result["status"], "passed")
        self.assertIn("TOOL_RESULT search_files", completion.call_args_list[1].args[1])

    def test_capture_refuses_prose_before_second_turn(self) -> None:
        with mock.patch.object(gate, "completion", return_value="I will search now.") as completion:
            result = gate.capture(gate.packet(self.contract()), "http://127.0.0.1:8080")
        self.assertEqual(result["status"], "failed_turn_1")
        self.assertEqual(completion.call_count, 1)

    def test_load_prompt_contract_refuses_unverified_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "contract.json"
            path.write_text(json.dumps({"schema": "wrong", "status": "unverified"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                gate.load_prompt_contract(path)


if __name__ == "__main__":
    unittest.main()
