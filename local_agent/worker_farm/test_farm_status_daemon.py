"""Farm-status daemon tests.

Correct invocation — from the repository root, farm venv only:

  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m unittest local_agent.worker_farm.test_farm_status_daemon -v

Do not run this file by path. PATH Python is not the farm environment.
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_FARM_UNITTEST = (
    r"local_agent\worker_farm\.venv\Scripts\python.exe -m unittest "
    "local_agent.worker_farm.test_farm_status_daemon -v"
)


def _require_package_layout() -> None:
    try:
        import local_agent.worker_farm  # noqa: F401
    except ModuleNotFoundError as exc:
        if getattr(exc, "name", None) not in {"local_agent", "local_agent.worker_farm"}:
            raise
        sys.stderr.write(
            "ERROR: local_agent is not importable because this file was run by path.\n"
            "From the repository root, use the farm venv:\n"
            f"  {_FARM_UNITTEST}\n"
        )
        raise SystemExit(2) from exc


_require_package_layout()

from local_agent.worker_farm import farm_health, farm_status_daemon as daemon

_OK = {
    "broker_reachable": True,
    "workers_responding": True,
    "latency_ms": 12.3,
    "workers": ["celery@Louises-MBP"],
    "status": "ok",
    "error": None,
}

_UNREACHABLE = {
    "broker_reachable": False,
    "workers_responding": False,
    "latency_ms": 1.0,
    "workers": [],
    "status": "unreachable",
    "error": "ConnectionRefusedError: timed out",
}

_NO_WORKERS = {
    "broker_reachable": True,
    "workers_responding": False,
    "latency_ms": 4.0,
    "workers": [],
    "status": "no_workers",
    "error": "broker reachable, no worker answered ping",
}

_REQUIRED = {
    "checked_at",
    "broker_reachable",
    "workers_responding",
    "latency_ms",
    "workers",
    "status",
    "error",
}


class FarmStatusDaemonTests(unittest.TestCase):
    def test_single_check_writes_valid_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "farm_status.json"
            snap = daemon.write_status_snapshot(
                path=dest, timeout_s=1.0, health_fn=lambda timeout_s=5.0: dict(_OK))
            self.assertTrue(dest.is_file())
            loaded = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(set(loaded), _REQUIRED)
            self.assertEqual(loaded["broker_reachable"], True)
            self.assertEqual(loaded["workers_responding"], True)
            self.assertEqual(loaded["latency_ms"], 12.3)
            self.assertEqual(loaded["workers"], ["celery@Louises-MBP"])
            self.assertEqual(loaded["status"], "ok")
            self.assertIsNone(loaded["error"])
            self.assertIsInstance(loaded["checked_at"], str)
            self.assertIn("T", loaded["checked_at"])
            self.assertEqual(snap["checked_at"], loaded["checked_at"])

    def test_atomic_write_keeps_old_file_if_replace_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "farm_status.json"
            good = daemon.snapshot_from_health(_OK, checked_at="2026-09-02T20:00:00+00:00")
            daemon.atomic_write_json(dest, good)
            before = dest.read_text(encoding="utf-8")

            def boom(src, dst):
                raise OSError("simulated crash before rename")

            with patch("os.replace", side_effect=boom):
                with self.assertRaises(OSError):
                    daemon.atomic_write_json(dest, {
                        "checked_at": "corrupt",
                        "status": "unreachable",
                        "broker_reachable": False,
                        "workers_responding": False,
                        "latency_ms": None,
                        "workers": [],
                        "error": "should not land",
                    })
            self.assertEqual(dest.read_text(encoding="utf-8"), before)
            self.assertTrue(json.loads(before)["broker_reachable"])
            leftovers = list(Path(tmp).glob("farm_status.json.*.tmp"))
            self.assertEqual(leftovers, [])

    def test_loop_ticks_without_crashing_on_failed_check(self):
        calls = []

        def flaky(timeout_s=5.0):
            calls.append(timeout_s)
            if len(calls) == 1:
                raise RuntimeError("inspect exploded")
            if len(calls) == 2:
                return dict(_NO_WORKERS)
            return dict(_OK)

        sleeps = []
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "farm_status.json"
            rc = daemon.run_loop(
                interval=0.01,
                timeout_s=1.5,
                path=dest,
                max_ticks=3,
                sleep_fn=lambda s: sleeps.append(s),
                health_fn=flaky,
            )
            loaded = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls, [1.5, 1.5, 1.5])
        self.assertEqual(len(sleeps), 2)
        self.assertEqual(loaded["status"], "ok")
        self.assertEqual(rc, 0)

    def test_json_cli_includes_checked_at(self):
        stamped = farm_health.with_checked_at(dict(_OK), checked_at="2026-09-02T20:43:00+00:00")
        self.assertEqual(stamped["checked_at"], "2026-09-02T20:43:00+00:00")
        self.assertEqual(stamped["status"], "ok")
        text = json.dumps(stamped)
        self.assertIn('"checked_at"', text)
        parsed = json.loads(text)
        self.assertTrue(set(parsed) >= _REQUIRED)

    def test_interval_env_and_cli(self):
        with patch.dict(os.environ, {"FARM_STATUS_INTERVAL_S": "15"}, clear=False):
            self.assertEqual(daemon.interval_s(None), 15.0)
            self.assertEqual(daemon.interval_s(7.0), 7.0)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FARM_STATUS_INTERVAL_S", None)
            self.assertEqual(daemon.interval_s(None), 30.0)


class ConsecutiveFailureAlertTests(unittest.TestCase):
    def test_fail_alert_after_env_and_cli(self):
        with patch.dict(os.environ, {"FARM_STATUS_FAIL_ALERT_AFTER": "5"}, clear=False):
            self.assertEqual(daemon.fail_alert_after(None), 5)
            self.assertEqual(daemon.fail_alert_after(2), 2)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FARM_STATUS_FAIL_ALERT_AFTER", None)
            self.assertEqual(daemon.fail_alert_after(None), 3)
        self.assertEqual(daemon.fail_alert_after(0), 1)

    def test_outage_line_format_is_greppable(self):
        line = daemon.format_outage_line(
            3, "unreachable", "ConnectionRefusedError: timed out")
        self.assertEqual(
            line,
            "FARM_STATUS_OUTAGE consecutive_failures=3 "
            "status=unreachable error=ConnectionRefusedError: timed out",
        )
        self.assertIn(daemon.OUTAGE_TOKEN, line)

    def test_alert_emitted_on_crossing_n_not_before(self):
        alerter = daemon.ConsecutiveFailureAlert(n=3)
        self.assertIsNone(alerter.observe("unreachable", "down"))
        self.assertIsNone(alerter.observe("no_workers", "quiet"))
        line = alerter.observe("unreachable", "still down")
        self.assertIsNotNone(line)
        self.assertIn("FARM_STATUS_OUTAGE", line)
        self.assertIn("consecutive_failures=3", line)
        self.assertIn("status=unreachable", line)
        self.assertIn("error=still down", line)
        self.assertTrue(alerter.outage_declared)

    def test_heartbeat_every_n_thereafter(self):
        alerter = daemon.ConsecutiveFailureAlert(n=3)
        lines = [alerter.observe("unreachable", "e") for _ in range(6)]
        tokens = [item for item in lines if item]
        self.assertEqual(len(tokens), 2)
        self.assertIn("consecutive_failures=3", tokens[0])
        self.assertIn("consecutive_failures=6", tokens[1])
        self.assertTrue(all(daemon.OUTAGE_TOKEN in item for item in tokens))

    def test_healthy_resets_counter_without_recovered_if_no_outage(self):
        alerter = daemon.ConsecutiveFailureAlert(n=3)
        self.assertIsNone(alerter.observe("unreachable", "down"))
        self.assertIsNone(alerter.observe("ok"))
        self.assertEqual(alerter.consecutive, 0)
        self.assertFalse(alerter.outage_declared)
        self.assertIsNone(alerter.observe("unreachable", "down"))
        self.assertEqual(alerter.consecutive, 1)

    def test_recovered_line_after_outage(self):
        alerter = daemon.ConsecutiveFailureAlert(n=3)
        for _ in range(3):
            alerter.observe("no_workers", "quiet")
        self.assertTrue(alerter.outage_declared)
        line = alerter.observe("ok")
        self.assertIsNotNone(line)
        self.assertIn(daemon.RECOVERED_TOKEN, line)
        self.assertIn("after_consecutive_failures=3", line)
        self.assertIn("status=ok", line)
        self.assertEqual(alerter.consecutive, 0)
        self.assertFalse(alerter.outage_declared)
        self.assertIsNone(alerter.observe("ok"))

    def test_unconfigured_counts_as_failed(self):
        alerter = daemon.ConsecutiveFailureAlert(n=2)
        self.assertIsNone(alerter.observe("unconfigured", "FARM_BROKER_URL not set"))
        line = alerter.observe("unconfigured", "FARM_BROKER_URL not set")
        self.assertIsNotNone(line)
        self.assertIn("status=unconfigured", line)

    def test_run_loop_prints_outage_token_after_n_failures(self):
        def always_down(timeout_s=5.0):
            return dict(_UNREACHABLE)

        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "farm_status.json"
            with patch("sys.stdout", buf):
                rc = daemon.run_loop(
                    interval=0.01,
                    timeout_s=1.0,
                    path=dest,
                    max_ticks=3,
                    sleep_fn=lambda s: None,
                    health_fn=always_down,
                    fail_alert_after_n=3,
                )
        text = buf.getvalue()
        self.assertEqual(text.count("FARM_STATUS_OUTAGE"), 1)
        self.assertIn("consecutive_failures=3", text)
        self.assertIn("status=unreachable", text)
        self.assertEqual(rc, 1)

    def test_run_loop_does_not_alert_before_n(self):
        def always_down(timeout_s=5.0):
            return dict(_UNREACHABLE)

        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "farm_status.json"
            with patch("sys.stdout", buf):
                daemon.run_loop(
                    interval=0.01,
                    timeout_s=1.0,
                    path=dest,
                    max_ticks=2,
                    sleep_fn=lambda s: None,
                    health_fn=always_down,
                    fail_alert_after_n=3,
                )
        self.assertNotIn("FARM_STATUS_OUTAGE", buf.getvalue())


if __name__ == "__main__":
    _require_package_layout()
    unittest.main()
