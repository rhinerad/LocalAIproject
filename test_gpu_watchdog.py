#!/usr/bin/env python3
"""Unit tests for gpu_watchdog.py hardening: env-driven stall timeout, step-counter
aware progress signature, no placeholder restart command, NVML sample guard, the
restart-counter precedence bug, and the real render-lock check.  pynvml/requests
are not required; nothing touches a GPU."""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gpu_lock  # noqa: E402
import gpu_watchdog as gw  # noqa: E402


class StallTimeoutConfigTests(unittest.TestCase):
    def _reload(self, env: dict):
        with patch.dict(os.environ, env, clear=False):
            for k in ("GVD_WATCHDOG_STALL_S", "COMFYUI_LAUNCH_CMD", "COMFYUI_LAUNCH_CWD"):
                if k not in env:
                    os.environ.pop(k, None)
            return importlib.reload(gw)

    def tearDown(self):
        importlib.reload(gw)

    def test_default_is_3900_which_exceeds_the_3600s_wan_timeout(self):
        mod = self._reload({})
        self.assertEqual(mod.COMFYUI_STALL_TIMEOUT_SEC, 3900.0)
        self.assertGreater(mod.COMFYUI_STALL_TIMEOUT_SEC, 3600)

    def test_env_override_and_invalid_values(self):
        self.assertEqual(self._reload({"GVD_WATCHDOG_STALL_S": "120"}).COMFYUI_STALL_TIMEOUT_SEC, 120.0)
        self.assertEqual(self._reload({"GVD_WATCHDOG_STALL_S": "nope"}).COMFYUI_STALL_TIMEOUT_SEC, 3900.0)
        self.assertEqual(self._reload({"GVD_WATCHDOG_STALL_S": "-5"}).COMFYUI_STALL_TIMEOUT_SEC, 3900.0)

    def test_launch_cmd_has_no_placeholder_default(self):
        mod = self._reload({})
        self.assertEqual(mod.COMFYUI_LAUNCH_CMD, [])
        self.assertIsNone(mod.COMFYUI_LAUNCH_CWD)
        mod = self._reload({"COMFYUI_LAUNCH_CMD": "python main.py --port 8188", "COMFYUI_LAUNCH_CWD": "/x"})
        self.assertEqual(mod.COMFYUI_LAUNCH_CMD, ["python", "main.py", "--port", "8188"])
        self.assertEqual(mod.COMFYUI_LAUNCH_CWD, "/x")


class RestartGuardTests(unittest.TestCase):
    def test_restart_refused_when_unconfigured(self):
        with patch.object(gw, "render_lock_is_held_by_someone_else", return_value=False), \
                patch.object(gw, "port_is_listening", return_value=False), \
                patch.object(gw, "COMFYUI_LAUNCH_CMD", []), patch.object(gw, "COMFYUI_LAUNCH_CWD", None), \
                patch.object(gw, "write_evidence"), patch.object(gw.subprocess, "Popen") as popen:
            self.assertFalse(gw.restart_comfyui())
            popen.assert_not_called()

    def test_restart_refused_when_lock_held(self):
        with patch.object(gw, "render_lock_is_held_by_someone_else", return_value=True), \
                patch.object(gw.subprocess, "Popen") as popen:
            self.assertFalse(gw.restart_comfyui())
            popen.assert_not_called()

    def test_restart_runs_configured_command(self):
        with tempfile.TemporaryDirectory() as td, \
                patch.object(gw, "render_lock_is_held_by_someone_else", return_value=False), \
                patch.object(gw, "port_is_listening", return_value=False), \
                patch.object(gw, "COMFYUI_LAUNCH_CMD", ["python", "main.py"]), \
                patch.object(gw, "COMFYUI_LAUNCH_CWD", td), \
                patch.object(gw.subprocess, "Popen") as popen:
            self.assertTrue(gw.restart_comfyui())
            self.assertEqual(popen.call_args.args[0], ["python", "main.py"])
            self.assertEqual(popen.call_args.kwargs["cwd"], td)

    def test_render_lock_check_is_real_and_fails_closed(self):
        with patch.object(gpu_lock, "is_held_by_other", return_value=True):
            self.assertTrue(gw.render_lock_is_held_by_someone_else())
        with patch.object(gpu_lock, "is_held_by_other", return_value=False):
            self.assertFalse(gw.render_lock_is_held_by_someone_else())
        with patch.object(gpu_lock, "is_held_by_other", side_effect=OSError("disk")):
            self.assertTrue(gw.render_lock_is_held_by_someone_else())

    def test_render_lock_sees_a_real_holder(self):
        with tempfile.TemporaryDirectory() as td:
            lock_path, owner_path = Path(td) / "runner.lock", Path(td) / "owner.json"
            with patch.object(gpu_lock, "DEFAULT_LOCK_PATH", lock_path), \
                    patch.object(gpu_lock, "DEFAULT_OWNER_PATH", owner_path):
                self.assertFalse(gw.render_lock_is_held_by_someone_else())
                owner_path.write_text('{"pid": 4242, "holder": "gvd_watcher"}', encoding="utf-8")
                with patch.object(gpu_lock, "pid_alive", return_value=True):
                    self.assertTrue(gw.render_lock_is_held_by_someone_else())


class ProgressSignatureTests(unittest.TestCase):
    def _monitor(self, responses: dict):
        mon = gw.ComfyUiProgressMonitor("http://fake:8188")
        mon._fetch = lambda path: responses.get(path)  # type: ignore[assignment]
        return mon

    def _running(self, step):
        return {"queue_running": [[1, "prompt-a", {"nodes": {}}, {"progress": {"value": step, "max": 30}}, []]],
                "queue_pending": []}

    def test_step_counter_advance_counts_as_progress_for_one_long_job(self):
        responses = {"/queue": self._running(3), "/history": {}}
        mon = self._monitor(responses)
        mon.poll(gpu_util_pct=0.0)
        mon._last_progress_ts = time.time() - 5000  # pretend a long time passed
        self.assertGreater(mon.poll(gpu_util_pct=0.0), 4000, "same signature -> no progress")
        responses["/queue"] = self._running(4)  # the sampler advanced one step
        self.assertLess(mon.poll(gpu_util_pct=0.0), 5.0)
        self.assertEqual(mon.last_step["value"], 4)

    def test_progress_endpoint_is_preferred_when_present(self):
        responses = {"/queue": self._running(3), "/history": {}, "/progress": {"value": 17, "max": 30, "node": "9"}}
        mon = self._monitor(responses)
        mon.poll()
        self.assertEqual(mon.last_step, {"value": 17, "max": 30, "node": "9"})
        mon._last_progress_ts = time.time() - 5000
        responses["/progress"] = {"value": 18, "max": 30, "node": "9"}
        self.assertLess(mon.poll(), 5.0)

    def test_gpu_utilization_counts_as_progress(self):
        responses = {"/queue": self._running(3), "/history": {}}
        mon = self._monitor(responses)
        mon.poll(gpu_util_pct=0.0)
        mon._last_progress_ts = time.time() - 5000
        self.assertGreater(mon.poll(gpu_util_pct=0.0), 4000)
        self.assertLess(mon.poll(gpu_util_pct=42.0), 5.0, "busy GPU is not a stall")

    def test_history_growth_and_idle(self):
        responses = {"/queue": self._running(1), "/history": {"a": {}}}
        mon = self._monitor(responses)
        mon.poll()
        mon._last_progress_ts = time.time() - 5000
        responses["/history"] = {"a": {}, "b": {}}
        self.assertLess(mon.poll(), 5.0)
        responses["/queue"] = {"queue_running": [], "queue_pending": []}
        self.assertEqual(mon.poll(), 0.0)
        self.assertIsNone(self._monitor({}).poll(), "unreachable server is unknown, not stalled")


class NvmlGuardTests(unittest.TestCase):
    def test_sample_returns_none_instead_of_raising(self):
        mon = gw.NvmlGpuMonitor.__new__(gw.NvmlGpuMonitor)
        mon.handle = object()
        fake = types.SimpleNamespace(
            nvmlDeviceGetMemoryInfo=lambda h: (_ for _ in ()).throw(RuntimeError("NVML lost")),
            NVMLError=RuntimeError,
        )
        with patch.object(gw, "pynvml", fake):
            self.assertIsNone(mon.sample())

    def test_sample_happy_path(self):
        mon = gw.NvmlGpuMonitor.__new__(gw.NvmlGpuMonitor)
        mon.handle = object()
        mem = types.SimpleNamespace(used=8 * 1024**3, total=16 * 1024**3)
        fake = types.SimpleNamespace(
            nvmlDeviceGetMemoryInfo=lambda h: mem,
            nvmlDeviceGetUtilizationRates=lambda h: types.SimpleNamespace(gpu=55),
            nvmlDeviceGetComputeRunningProcesses=lambda h: [],
            nvmlDeviceGetGraphicsRunningProcesses=lambda h: [],
            NVMLError=RuntimeError,
        )
        with patch.object(gw, "pynvml", fake):
            s = mon.sample()
        self.assertAlmostEqual(s.used_pct, 50.0)
        self.assertEqual(s.gpu_util_pct, 55.0)


class RestartCounterPrecedenceTests(unittest.TestCase):
    def _run(self, started: bool, before: int) -> int:
        state = gw.WatchdogState(consecutive_restarts=before)
        sample = gw.GpuSample(timestamp=0, total_mb=16000, used_mb=15000, used_pct=93.0, gpu_util_pct=0.0,
                              proc_pids={123: 15000})
        info = {"pid": 123, "name": "python", "cmdline": ["python"], "create_time": 0, "age_sec": 999}
        with patch.object(gw, "pick_zombie_pid", return_value=123), \
                patch.object(gw, "describe_process", return_value=info), \
                patch.object(gw, "kill_process_tree", return_value=True), \
                patch.object(gw, "write_evidence"), \
                patch.object(gw.psutil, "pids", return_value=[]), \
                patch.object(gw.time, "sleep", lambda s: None), \
                patch.object(gw, "restart_comfyui", return_value=started):
            gw.handle_stall("test", sample, state)
        return state.consecutive_restarts

    def test_refused_restart_does_not_double_the_counter(self):
        self.assertEqual(self._run(started=False, before=2), 2)

    def test_started_restart_increments_once(self):
        self.assertEqual(self._run(started=True, before=2), 3)


if __name__ == "__main__":
    unittest.main()
