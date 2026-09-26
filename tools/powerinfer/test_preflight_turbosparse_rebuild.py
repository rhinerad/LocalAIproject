from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from capture_turbosparse_prompt_contract import EXPECTED  # noqa: E402
from preflight_turbosparse_rebuild import preflight  # noqa: E402


class TurboSparsePreflightTests(unittest.TestCase):
    def test_requires_approved_pairs_and_new_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "config.json").write_text(json.dumps({"model_type": "bamboo", "hidden_act": "relu", "hidden_size": 4096, "intermediate_size": 14336, "num_hidden_layers": 32}), encoding="utf-8")
            (source / "tokenizer_config.json").write_text(json.dumps({"chat_template": EXPECTED, "added_tokens_decoder": {"1": {"content": "<|im_start|>"}, "2": {"content": "<|im_end|>"}}}), encoding="utf-8")
            pairs = root / "pairs.jsonl"
            rows = [
                {"pair_id": f"pa-{i:03d}", "harmful": f"Contrastive prompt {i} with enough words.", "harmless": f"Matched harmless prompt {i} with enough words.", "category": "contrastive_refusal", "source": "operator_authored", "approval_id": "operator-approval-20260831", "operator_approved": True, "schema_version": "projected-abliteration-v1"}
                for i in range(1, 33)
            ]
            pairs.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            result = preflight(source, pairs, root / "new-output")
            self.assertEqual(result["status"], "ready_for_explicit_gpu_approval")
            (root / "taken-output").mkdir()
            with self.assertRaises(ValueError):
                preflight(source, pairs, root / "taken-output")


if __name__ == "__main__":
    unittest.main()
