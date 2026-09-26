"""Regression checks for Windows ownership probing of the lazy exact VLM."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import capabilities


class QwenReleaseTests(unittest.TestCase):
    def test_windows_powershell_detects_an_owned_runtime(self):
        # `_runtime_pid_alive()` deliberately uses Get-Process rather than
        # tasklist, whose access-denied pseudo-results are unreliable for the
        # CUDA child. A zero exit code is the explicit live-PID proof.
        result = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(capabilities.os, "name", "nt"), \
             patch.object(capabilities.subprocess, "run", return_value=result):
            self.assertTrue(capabilities._runtime_pid_alive(6476))

    def test_windows_powershell_detects_a_gone_runtime(self):
        # Get-Process exits 1 for a missing PID; stdout text is not parsed.
        result = SimpleNamespace(returncode=1, stdout="", stderr="")
        with patch.object(capabilities.os, "name", "nt"), \
             patch.object(capabilities.subprocess, "run", return_value=result):
            self.assertFalse(capabilities._runtime_pid_alive(6476))


if __name__ == "__main__":
    unittest.main()
