#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import three_d_contract


class ThreeDContractTests(unittest.TestCase):
    def _contract(self, root: Path, *, checksum: str) -> Path:
        data = {"status": "approved", "approved_by": "operator", "workflow": "trellis.json",
                "workflow_sha256": checksum, "required_node_types": ["OperatorNamedNode"],
                "bindings": {key: {"node_id": "1", "input": "value"}
                             for key in ("prompt", "reference_image", "mesh_output")},
                "mesh_extensions": [".glb"]}
        path = root / "contract.json"
        path.write_text(json.dumps(data), encoding="utf8")
        return path

    def test_requires_approved_checksum_pinned_explicit_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow = root / "workflows" / "trellis.json"
            workflow.parent.mkdir()
            workflow.write_text('{"prompt": {}}', encoding="utf8")
            checksum = hashlib.sha256(workflow.read_bytes()).hexdigest()
            contract = self._contract(root, checksum=checksum)
            report = three_d_contract.validate(contract, shared_root=root)
            self.assertTrue(report["ready_for_future_tool_review"])
            self._contract(root, checksum="wrong")
            with self.assertRaises(three_d_contract.ContractError):
                three_d_contract.validate(contract, shared_root=root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
