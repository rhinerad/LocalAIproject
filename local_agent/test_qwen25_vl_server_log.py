#!/usr/bin/env python3
"""Qwen2.5-VL llama-server output is logged, not discarded (2026-09-24t).

Both production launchers (capabilities.ensure_qwen25_vl_runtime for the media
watcher, dspy_optimizer._ensure_owned_qwen25_vl_runtime for the GVD judge) used
stdout/stderr=DEVNULL, so four mid-request server crashes left no trace.
Never starts llama.cpp: Popen is mocked throughout.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import capabilities as caps
import dspy_optimizer


class _LogTree(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.log = self.root / "logs" / "qwen25_vl_llama_server.log"
        self.server = self.root / "llama-server.exe"
        self.server.write_bytes(b"stub")
        p = patch.multiple(caps, QWEN25_VL_SERVER_LOG=self.log,
                           QWEN25_VL_RUNTIME_STATE=self.root / "state.json",
                           QWEN25_VL_LLAMA_SERVER=self.server)
        p.start()
        self.addCleanup(p.stop)

    def _fake_popen(self, seen: dict, pid: int = 4242):
        def popen(args, stdout=None, stderr=None, **kwargs):
            seen.update(stdout=stdout, stderr=stderr, closed_at_launch=stdout.closed)
            stdout.write(b"llama server listening\n")   # what the child would write
            proc = MagicMock()
            proc.pid = pid
            proc.poll.return_value = None
            return proc
        return popen

    def _text(self) -> str:
        return self.log.read_text(encoding="utf-8")


class HelperTests(_LogTree):
    def test_header_pid_and_handle_closed(self):
        handle = caps.open_qwen25_vl_server_log("unit")
        self.assertFalse(handle.closed)
        caps.close_qwen25_vl_server_log(handle, 777)
        self.assertTrue(handle.closed)
        text = self._text()
        self.assertIn("llama-server launch by unit", text)
        self.assertIn("pid 777", text)

    def test_appends_across_launches(self):
        for caller in ("one", "two"):
            caps.close_qwen25_vl_server_log(caps.open_qwen25_vl_server_log(caller), 1)
        text = self._text()
        self.assertLess(text.index("launch by one"), text.index("launch by two"))

    def test_oversized_log_rotates_once_to_prev(self):
        self.log.parent.mkdir(parents=True)
        self.log.write_bytes(b"old crash\n")
        with patch.object(caps, "QWEN25_VL_SERVER_LOG_MAX_BYTES", 4):
            caps.close_qwen25_vl_server_log(caps.open_qwen25_vl_server_log("new"))
        self.assertEqual(b"old crash\n", self.log.with_name(self.log.name + ".prev").read_bytes())
        self.assertNotIn("old crash", self._text())

    def test_unopenable_log_falls_back_to_devnull(self):
        with patch.object(Path, "open", side_effect=OSError("locked")):
            handle = caps.open_qwen25_vl_server_log("x")
        self.assertIs(subprocess.DEVNULL, handle)
        caps.close_qwen25_vl_server_log(handle, 5)   # no-op, no error


class WatcherLaunchTests(_LogTree):
    def test_watcher_launch_logs_stdout_and_stderr(self):
        seen: dict = {}
        with patch.object(caps, "qwen25_vl_files_ready", return_value=True), \
             patch.object(caps, "qwen25_vl_checksums_ok", return_value=True), \
             patch.object(caps.llama_cpp_client, "up", side_effect=[False, True]), \
             patch.object(caps.subprocess, "Popen", side_effect=self._fake_popen(seen)), \
             patch.object(caps.time, "sleep"):
            self.assertTrue(caps.ensure_qwen25_vl_runtime(timeout_seconds=1))
        self.assertIsNot(subprocess.DEVNULL, seen["stdout"])
        self.assertEqual(subprocess.STDOUT, seen["stderr"])
        self.assertFalse(seen["closed_at_launch"])
        self.assertTrue(seen["stdout"].closed)   # this process dropped its copy
        text = self._text()
        self.assertIn("launch by capabilities.ensure_qwen25_vl_runtime", text)
        self.assertIn("llama server listening", text)
        self.assertIn("pid 4242", text)

    def test_popen_failure_still_returns_false_and_closes_log(self):
        with patch.object(caps, "qwen25_vl_files_ready", return_value=True), \
             patch.object(caps, "qwen25_vl_checksums_ok", return_value=True), \
             patch.object(caps.llama_cpp_client, "up", return_value=False), \
             patch.object(caps.subprocess, "Popen", side_effect=OSError("no exe")), \
             patch.object(caps, "close_qwen25_vl_server_log",
                          wraps=caps.close_qwen25_vl_server_log) as close:
            self.assertFalse(caps.ensure_qwen25_vl_runtime(timeout_seconds=0))
        close.assert_called_once()


class JudgeLaunchTests(_LogTree):
    def setUp(self):
        super().setUp()
        p = patch.object(dspy_optimizer, "_QWEN25_VL_PROC", None)
        p.start()
        self.addCleanup(p.stop)

    def test_owned_judge_launch_logs_stdout_and_stderr(self):
        seen: dict = {}
        with patch.object(caps, "qwen25_vl_files_ready", return_value=True), \
             patch.object(caps, "qwen25_vl_checksums_ok", return_value=True), \
             patch.object(caps, "_write_qwen25_vl_runtime_state"), \
             patch.object(caps.llama_cpp_client, "up", side_effect=[False, True]), \
             patch.object(dspy_optimizer.subprocess, "Popen", side_effect=self._fake_popen(seen, 99)):
            self.assertTrue(dspy_optimizer._ensure_owned_qwen25_vl_runtime(timeout_seconds=5))
        self.assertIsNot(subprocess.DEVNULL, seen["stdout"])
        self.assertEqual(subprocess.STDOUT, seen["stderr"])
        self.assertTrue(seen["stdout"].closed)
        text = self._text()
        self.assertIn("launch by dspy_optimizer._ensure_owned_qwen25_vl_runtime", text)
        self.assertIn("pid 99", text)

    def test_early_exit_error_names_the_log(self):
        seen: dict = {}
        popen = self._fake_popen(seen)

        def dead(*a, **k):
            proc = popen(*a, **k)
            proc.poll.return_value = 1
            return proc

        with patch.object(caps, "qwen25_vl_files_ready", return_value=True), \
             patch.object(caps, "qwen25_vl_checksums_ok", return_value=True), \
             patch.object(caps, "_write_qwen25_vl_runtime_state"), \
             patch.object(caps.llama_cpp_client, "up", return_value=False), \
             patch.object(dspy_optimizer.subprocess, "Popen", side_effect=dead):
            with self.assertRaises(dspy_optimizer.HandoffError) as ctx:
                dspy_optimizer._ensure_owned_qwen25_vl_runtime(timeout_seconds=5)
        self.assertIn(str(self.log), str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
