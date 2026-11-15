"""Gate hardening found while verifying area A (2026-11-06b).

- file_edit_gate holds a cross-process file lock across load+save, so the GUI
  server and the LXMF bridge cannot both consume one one-shot approval
  (AUDIT_2026-11-02 finding 11, second half).
- comfy_models normalises ``action`` before its risk checks, so "Remove"
  still requires the operator approval (finding 4).
"""
from __future__ import annotations

import json
import multiprocessing
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import file_edit_gate  # noqa: E402
import tools  # noqa: E402


def _hold_lock(state_file: str, ready, release) -> None:  # child process
    sys.path.insert(0, str(HERE))
    import file_edit_gate as gate
    gate.STATE_FILE = Path(state_file)
    with gate._file_lock():
        ready.set()
        release.wait(10)


class FileEditGateLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "runtime" / "file_edit_gate.json"
        p = patch.object(file_edit_gate, "STATE_FILE", self.state)
        p.start()
        self.addCleanup(p.stop)

    def test_request_and_decide_round_trip_still_one_shot(self):
        first = file_edit_gate.request("a.py", "x=1")
        self.assertFalse(first["granted"])
        file_edit_gate.decide(first["request"]["id"], True)
        self.assertTrue(file_edit_gate.request("a.py", "x=1")["granted"])
        again = file_edit_gate.request("a.py", "x=1")
        self.assertFalse(again["granted"], "approval is consumed once")
        self.assertTrue(self.state.with_name(self.state.name + ".lock").exists())

    def test_lock_held_by_another_process_blocks_then_times_out(self):
        ctx = multiprocessing.get_context("spawn")
        ready, release = ctx.Event(), ctx.Event()
        proc = ctx.Process(target=_hold_lock, args=(str(self.state), ready, release))
        proc.start()
        self.addCleanup(proc.join, 10)
        self.addCleanup(release.set)
        self.assertTrue(ready.wait(30), "child never took the lock")
        with patch.object(file_edit_gate, "LOCK_TIMEOUT_SECONDS", 0.3):
            with self.assertRaises(TimeoutError):
                file_edit_gate.request("b.py", "y=2")
        release.set()
        proc.join(10)
        self.assertFalse(file_edit_gate.request("b.py", "y=2")["granted"])

    def test_snapshot_does_not_take_the_file_lock(self):
        with patch.object(file_edit_gate, "_file_lock",
                          side_effect=AssertionError("snapshot must stay lock-free")):
            snap = file_edit_gate.snapshot()
        self.assertEqual([], snap["pending"])


class ComfyModelsActionCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.audit = Path(tmp.name) / "comfy_mcp_audit.jsonl"
        self.calls = []
        for target, kw in (
            ((tools, "_COMFY_AUDIT_PATH"), {"new": self.audit}),
        ):
            p = patch.object(*target, **kw)
            p.start()
            self.addCleanup(p.stop)
        p = patch("mcp_client.call",
                  side_effect=lambda name, args, timeout=None: self.calls.append((name, args)) or {"ok": True})
        p.start()
        self.addCleanup(p.stop)

    def test_mixed_case_remove_still_needs_approval(self):
        with patch("gpu_gate.request", return_value={"granted": False, "request": {"id": "r"}}):
            for action in ("Remove", " REMOVE "):
                with self.subTest(action=action):
                    with self.assertRaises(tools.ToolError):
                        tools.comfy_models({"tool": "list_local_models", "action": action,
                                            "filename": "x.safetensors"})
        self.assertEqual([], self.calls, "nothing reached the MCP server")

    def test_approved_remove_sends_normalised_action_and_audits(self):
        with patch("gpu_gate.request", return_value={"granted": True}):
            tools.comfy_models({"tool": "list_local_models", "action": "Remove",
                                "filename": "x.safetensors"})
        self.assertEqual("remove", self.calls[-1][1]["action"])
        row = json.loads(self.audit.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual("model_delete", row["risk"])


if __name__ == "__main__":
    unittest.main()
