import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work"))
import image_render as ir  # noqa: E402


class _FakeProc:
    pid = 4242

    def __init__(self):
        self.dead = False
        self.kill_called = False

    def poll(self):
        return 1 if self.dead else None

    def kill(self):
        self.kill_called = True
        self.dead = True

    def wait(self, timeout=None):
        if not self.dead:
            raise subprocess.TimeoutExpired("backend", timeout)
        return 1


class ImageRenderCleanupTests(unittest.TestCase):
    def test_pid_alive_uses_positive_absent_fallback_when_tasklist_is_denied(self):
        denied = SimpleNamespace(returncode=1, stdout="", stderr="ERROR: Access denied")
        absent = SimpleNamespace(returncode=0, stdout="ABSENT\n", stderr="")
        with mock.patch.object(ir.os, "name", "nt"), \
                mock.patch.object(ir.subprocess, "run", side_effect=[denied, absent]):
            self.assertFalse(ir._pid_alive(4242))

    def test_pid_alive_remains_fail_closed_when_both_probes_are_uncertain(self):
        denied = SimpleNamespace(returncode=1, stdout="", stderr="ERROR: Access denied")
        uncertain = SimpleNamespace(returncode=1, stdout="", stderr="also denied")
        with mock.patch.object(ir.os, "name", "nt"), \
                mock.patch.object(ir.subprocess, "run", side_effect=[denied, uncertain]):
            self.assertTrue(ir._pid_alive(4242))

    def test_verified_owned_backend_uses_handle_when_taskkill_is_denied(self):
        proc = _FakeProc()
        verified = SimpleNamespace(
            returncode=0,
            stdout=f'python main.py --user-directory "{ir.IMAGE_USER}" {ir.COMFY_PYTHON}',
            stderr="",
        )
        denied = SimpleNamespace(returncode=1, stdout="", stderr="ERROR: Access denied")
        with mock.patch.object(ir.subprocess, "run", side_effect=[verified, denied]), \
                mock.patch.object(ir.urllib.request, "urlopen", side_effect=OSError("offline")), \
                mock.patch.object(ir, "_port_open", return_value=False):
            ir._stop_owned_backend(proc)
        self.assertTrue(proc.kill_called)
        self.assertIsNotNone(proc.poll())


if __name__ == "__main__":
    unittest.main()
