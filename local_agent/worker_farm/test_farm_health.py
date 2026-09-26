r"""Worker-farm health-check tests.

Correct invocation — from the repository root, farm venv only:

  local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_health -v

Do not run this file by path. PATH Python is not the farm environment.
"""
from __future__ import annotations

import os
import socket
import sys
import unittest
from unittest.mock import patch

_FARM_UNITTEST = (
    r"local_agent\worker_farm\.venv\Scripts\python.exe -m unittest "
    "local_agent.worker_farm.test_farm_health -v"
)


def _require_package_layout() -> None:
    """Fail loudly when this file is executed by path instead of as a package."""
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

from local_agent.worker_farm import farm_health


_FAKE_BROKER = "redis://:unit-test-pass@127.0.0.1:6379/0"
_WORKER = "celery@Louises-MacBook-Pro.local"
_ALL_EXPECTED = list(farm_health.EXPECTED_REGISTERED_TASKS)
_REGISTERED = {
    _WORKER: list(_ALL_EXPECTED) + ["celery.backend_cleanup"],
}


class FarmHealthTests(unittest.TestCase):
    def test_farm_reachable_and_responsive(self):
        pinged = {_WORKER: {"ok": "pong"}}
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check"), \
             patch.object(farm_health, "_inspect_ping", return_value=pinged), \
             patch.object(farm_health, "_inspect_registered", return_value=_REGISTERED):
            result = farm_health.check_farm_health(timeout_s=1.0)
        self.assertTrue(result["broker_reachable"])
        self.assertTrue(result["workers_responding"])
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["error"])
        self.assertEqual(result["workers"], [_WORKER])
        self.assertIsInstance(result["latency_ms"], float)
        for task in _ALL_EXPECTED:
            self.assertIn(task, result["registered_tasks"])
        self.assertEqual(result["missing_expected_tasks"], [])
        line = farm_health.format_status_line(result)
        self.assertIn("broker reachable: yes", line)
        self.assertIn("workers responding: yes", line)
        self.assertIn("latency_ms:", line)
        self.assertIn("summarize_conversation", line)

    def test_farm_unreachable(self):
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check",
                          side_effect=ConnectionRefusedError("refused")), \
             patch.object(farm_health, "_inspect_ping") as inspect, \
             patch.object(farm_health, "_inspect_registered") as registered:
            result = farm_health.check_farm_health(timeout_s=1.0)
        inspect.assert_not_called()
        registered.assert_not_called()
        self.assertFalse(result["broker_reachable"])
        self.assertFalse(result["workers_responding"])
        self.assertEqual(result["status"], "unreachable")
        self.assertIn("ConnectionRefusedError", result["error"] or "")
        self.assertEqual(result["workers"], [])
        self.assertEqual(result["registered_tasks"], [])
        line = farm_health.format_status_line(result)
        self.assertIn("broker reachable: no", line)
        self.assertIn("workers responding: no", line)

    def test_farm_unreachable_on_timeout(self):
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check",
                          side_effect=socket.timeout("timed out")), \
             patch.object(farm_health, "_inspect_ping") as inspect:
            result = farm_health.check_farm_health(timeout_s=0.2)
        inspect.assert_not_called()
        self.assertFalse(result["broker_reachable"])
        self.assertEqual(result["status"], "unreachable")

    def test_broker_up_workers_down(self):
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check"), \
             patch.object(farm_health, "_inspect_ping", return_value=None), \
             patch.object(farm_health, "_inspect_registered") as registered:
            result = farm_health.check_farm_health(timeout_s=1.0)
        registered.assert_not_called()
        self.assertTrue(result["broker_reachable"])
        self.assertFalse(result["workers_responding"])
        self.assertEqual(result["status"], "no_workers")
        self.assertIn("no worker answered ping", result["error"] or "")
        line = farm_health.format_status_line(result)
        self.assertIn("broker reachable: yes", line)
        self.assertIn("workers responding: no", line)

    def test_broker_up_inspect_raises_is_no_workers(self):
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check"), \
             patch.object(farm_health, "_inspect_ping",
                          side_effect=OSError("kombu connection refused")):
            result = farm_health.check_farm_health(timeout_s=1.0)
        self.assertTrue(result["broker_reachable"])
        self.assertFalse(result["workers_responding"])
        self.assertEqual(result["status"], "no_workers")

    def test_missing_broker_url_is_unconfigured(self):
        env = {k: v for k, v in os.environ.items() if k != "FARM_BROKER_URL"}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(farm_health, "_load_env_file"):
            result = farm_health.check_farm_health(timeout_s=1.0)
        self.assertFalse(result["broker_reachable"])
        self.assertEqual(result["status"], "unconfigured")
        self.assertIn("FARM_BROKER_URL", result["error"] or "")

    def test_never_raises(self):
        with patch.object(farm_health, "_load_env_file",
                          side_effect=RuntimeError("unexpected")):
            result = farm_health.check_farm_health(timeout_s=1.0)
        self.assertEqual(result["status"], "unreachable")
        self.assertIn("RuntimeError", result["error"] or "")

    def test_redacts_redis_password_in_errors(self):
        leaked = "kombu failed redis://:super-secret-pass@127.0.0.1:6379/0"
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check"), \
             patch.object(farm_health, "_inspect_ping",
                          side_effect=RuntimeError(leaked)):
            result = farm_health.check_farm_health(timeout_s=1.0)
        self.assertNotIn("super-secret-pass", result["error"] or "")
        self.assertIn("redis://:***@", result["error"] or "")

    def test_broker_tcp_uses_url_host_and_port(self):
        with patch("socket.create_connection") as conn:
            conn.return_value.close = lambda: None
            farm_health._broker_tcp_check(
                "redis://:x@10.90.90.1:6379/0", timeout_s=2.5)
        conn.assert_called_once_with(("10.90.90.1", 6379), timeout=2.5)

    def test_reachable_worker_missing_summarize_embed_stays_ok(self):
        pinged = {_WORKER: {"ok": "pong"}}
        only_probe = {_WORKER: ["local_agent.worker_farm.tasks.connectivity_probe"]}
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check"), \
             patch.object(farm_health, "_inspect_ping", return_value=pinged), \
             patch.object(farm_health, "_inspect_registered", return_value=only_probe):
            result = farm_health.check_farm_health(timeout_s=1.0)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["workers_responding"])
        self.assertIn("local_agent.worker_farm.tasks.connectivity_probe",
                      result["registered_tasks"])
        self.assertIn("local_agent.worker_farm.tasks.summarize_conversation",
                      result["missing_expected_tasks"])
        self.assertIn("local_agent.worker_farm.tasks.embed_chunks",
                      result["missing_expected_tasks"])

    def test_inspect_registered_failure_keeps_connectivity_ok(self):
        pinged = {_WORKER: {"ok": "pong"}}
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check"), \
             patch.object(farm_health, "_inspect_ping", return_value=pinged), \
             patch.object(farm_health, "_inspect_registered",
                          side_effect=OSError("inspect registered failed")):
            result = farm_health.check_farm_health(timeout_s=1.0)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["registered_tasks"], [])
        self.assertEqual(result["missing_expected_tasks"], _ALL_EXPECTED)

    def test_check_registered_tasks_ok_when_expected_present(self):
        pinged = {_WORKER: {"ok": "pong"}}
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check"), \
             patch.object(farm_health, "_inspect_ping", return_value=pinged), \
             patch.object(farm_health, "_inspect_registered", return_value=_REGISTERED):
            result = farm_health.check_registered_tasks(timeout_s=1.0)
        self.assertEqual(result["status"], "ok")
        self.assertIsNone(result["error"])
        self.assertEqual(result["missing_expected_tasks"], [])
        self.assertEqual(result["expected_tasks"], _ALL_EXPECTED)
        self.assertEqual(result["workers"], [_WORKER])
        line = farm_health.format_registered_line(result)
        self.assertIn("registered-task status: ok", line)

    def test_check_registered_tasks_missing_when_expected_absent(self):
        pinged = {_WORKER: {"ok": "pong"}}
        only_probe = {_WORKER: ["local_agent.worker_farm.tasks.connectivity_probe"]}
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check"), \
             patch.object(farm_health, "_inspect_ping", return_value=pinged), \
             patch.object(farm_health, "_inspect_registered", return_value=only_probe):
            result = farm_health.check_registered_tasks(timeout_s=1.0)
        self.assertEqual(result["status"], "missing_tasks")
        self.assertIn("summarize_conversation", result["error"] or "")
        self.assertIn("embed_chunks", result["error"] or "")
        self.assertIn("local_agent.worker_farm.tasks.summarize_conversation",
                      result["missing_expected_tasks"])

    def test_check_registered_tasks_unreachable_keeps_connectivity_status(self):
        with patch.dict(os.environ, {"FARM_BROKER_URL": _FAKE_BROKER}, clear=False), \
             patch.object(farm_health, "_load_env_file"), \
             patch.object(farm_health, "_broker_tcp_check",
                          side_effect=ConnectionRefusedError("refused")):
            result = farm_health.check_registered_tasks(timeout_s=1.0)
        self.assertEqual(result["status"], "unreachable")
        self.assertEqual(result["registered_tasks"], [])
        self.assertEqual(result["missing_expected_tasks"], _ALL_EXPECTED)

    def test_normalize_task_names_strips_signature_suffix(self):
        names = farm_health._normalize_task_names([
            "local_agent.worker_farm.tasks.embed_chunks[abc]",
            "local_agent.worker_farm.tasks.summarize_conversation",
            "",
        ])
        self.assertEqual(names, [
            "local_agent.worker_farm.tasks.embed_chunks",
            "local_agent.worker_farm.tasks.summarize_conversation",
        ])


if __name__ == "__main__":
    _require_package_layout()
    unittest.main()