"""Stdlib checks for the one-shot local GPU permission gate."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gpu_gate


def run() -> None:
    with tempfile.TemporaryDirectory() as td:
        old = gpu_gate.STATE_FILE
        try:
            gpu_gate.STATE_FILE = Path(td) / "gate.json"
            gpu_gate._LAST_GOOD = None
            first = gpu_gate.request("vision", source="test", key="a")
            assert not first["granted"] and first["request"]
            again = gpu_gate.request("vision", source="test", key="a")
            assert again["request"]["id"] == first["request"]["id"]
            gpu_gate.decide(first["request"]["id"], "approve")
            assert gpu_gate.request("vision", source="test", key="a")["granted"]
            assert not gpu_gate.request("vision", source="test", key="a")["granted"]
            gpu_gate.set_mode("block")
            assert gpu_gate.request("chat", source="test", key="b")["blocked"]
            gpu_gate.set_mode("allow")
            assert gpu_gate.request("chat", source="test", key="b")["granted"]
        finally:
            gpu_gate.STATE_FILE = old
            gpu_gate._LAST_GOOD = None
    print("gpu gate tests: 6/6 passed")


class GpuGateTests(unittest.TestCase):
    """unittest wrapper so pytest / python -m unittest collect the checks above."""

    def test_one_shot_flow_and_modes(self):
        run()


if __name__ == "__main__":
    run()
