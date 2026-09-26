"""Farm dashboard pure-helper tests (no live farm required).

Correct invocation — from the repository root, farm venv or system Python:

  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m unittest local_agent.worker_farm.test_farm_dashboard -v

Do not run this file by path.
"""
from __future__ import annotations

import socket
import sys
import threading
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_FARM_UNITTEST = (
    r"local_agent\worker_farm\.venv\Scripts\python.exe -m unittest "
    "local_agent.worker_farm.test_farm_dashboard -v"
)


def _require_package_layout() -> None:
    try:
        import local_agent.worker_farm  # noqa: F401
    except ModuleNotFoundError as exc:
        if getattr(exc, "name", None) not in {"local_agent", "local_agent.worker_farm"}:
            raise
        sys.stderr.write(
            "ERROR: local_agent is not importable because this file was run by path.\n"
            "From the repository root, use:\n"
            f"  {_FARM_UNITTEST}\n"
        )
        raise SystemExit(2) from exc


_require_package_layout()

from local_agent.worker_farm.dashboard import collect


class ParseOutageEventsTests(unittest.TestCase):
    def test_filters_and_caps_last_n(self) -> None:
        lines = []
        for i in range(30):
            lines.append(f"noise {i}")
            lines.append(
                f"FARM_STATUS_OUTAGE consecutive_failures={i} status=no_workers error=x"
            )
        lines.append("FARM_STATUS_RECOVERED after_consecutive_failures=3 status=ok")
        text = "\n".join(lines)
        events = collect.parse_outage_events(text, n=20)
        self.assertEqual(len(events), 20)
        self.assertTrue(events[-1].startswith("FARM_STATUS_RECOVERED"))
        self.assertTrue(all(
            "FARM_STATUS_OUTAGE" in e or "FARM_STATUS_RECOVERED" in e for e in events
        ))

    def test_empty_and_zero_cap(self) -> None:
        self.assertEqual(collect.parse_outage_events("", n=20), [])
        self.assertEqual(
            collect.parse_outage_events("FARM_STATUS_OUTAGE consecutive_failures=1", n=0),
            [],
        )


class StaleThresholdTests(unittest.TestCase):
    def test_age_over_90s_is_stale(self) -> None:
        now = datetime(2026, 9, 3, 17, 0, 0, tzinfo=timezone.utc)
        fresh = (now - timedelta(seconds=30)).isoformat()
        old = (now - timedelta(seconds=91)).isoformat()
        self.assertFalse(collect.is_stale(fresh, now=now))
        self.assertTrue(collect.is_stale(old, now=now))
        self.assertTrue(collect.is_stale(None, now=now))
        self.assertTrue(collect.is_stale("not-a-timestamp", now=now))
        age = collect.snapshot_age_s(old, now=now)
        self.assertIsNotNone(age)
        self.assertGreater(age, 90.0)


class BindHostRejectionTests(unittest.TestCase):
    def test_wildcard_and_spoke_and_apipa_refused(self) -> None:
        for host in ("0.0.0.0", "10.90.90.2", "169.254.12.207"):
            self.assertTrue(collect.is_forbidden_bind_host(host), host)
            with self.assertRaises(ValueError):
                collect.resolve_bind_host(env_host=host)

    def test_default_is_loopback_even_when_lan_candidates_exist(self) -> None:
        chosen = collect.resolve_bind_host(
            env_host=None,
            candidates=["10.0.0.5", "192.168.50.208"],
        )
        self.assertEqual(chosen, "127.0.0.1")
        self.assertFalse(collect.is_forbidden_bind_host("127.0.0.1"))
        self.assertEqual(
            collect.resolve_bind_host(env_host="127.0.0.1"),
            "127.0.0.1",
        )

    def test_lan_opt_in_restores_explicit_lan_host(self) -> None:
        self.assertFalse(collect.is_forbidden_bind_host("192.168.50.208"))
        self.assertTrue(collect.is_acceptable_lan_ipv4("192.168.50.208"))
        self.assertEqual(
            collect.resolve_bind_host(env_host="192.168.50.208"),
            "192.168.50.208",
        )

    def test_overlay_hub_opt_in(self) -> None:
        self.assertFalse(collect.is_forbidden_bind_host("10.90.90.1"))
        self.assertEqual(
            collect.resolve_bind_host(env_host="10.90.90.1"),
            "10.90.90.1",
        )
        self.assertFalse(collect.is_acceptable_lan_ipv4("10.90.90.1"))

    def test_loopback_socket_does_not_accept_lan(self) -> None:
        """Default bind 127.0.0.1 must not be reachable on a LAN address."""
        class _H(BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), _H)
        _host, port = httpd.server_address
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as resp:
                self.assertEqual(resp.read(), b"ok")
            lan = "192.168.50.208"
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            try:
                sock.connect((lan, port))
                self.fail(f"loopback-bound port {port} accepted a connect from {lan}")
            except OSError:
                pass
            finally:
                sock.close()
        finally:
            httpd.shutdown()
            httpd.server_close()


class EventCapConstantTests(unittest.TestCase):
    def test_event_cap_is_20(self) -> None:
        self.assertEqual(collect.EVENT_CAP, 20)


class DegradedAlertTests(unittest.TestCase):
    def test_ok_not_stale_is_healthy(self) -> None:
        self.assertFalse(
            collect.is_farm_degraded({"status": "ok", "stale": False})
        )

    def test_stale_or_non_ok_is_degraded(self) -> None:
        self.assertTrue(
            collect.is_farm_degraded({"status": "ok", "stale": True})
        )
        self.assertTrue(
            collect.is_farm_degraded({"status": "no_workers", "stale": False})
        )
        self.assertTrue(
            collect.is_farm_degraded({"status": "unreachable", "stale": False})
        )
        self.assertTrue(
            collect.is_farm_degraded({"status": "daemon-down", "stale": True})
        )
        self.assertTrue(collect.is_farm_degraded({}))
        self.assertTrue(collect.is_farm_degraded(None))

    def test_overall_from_snapshot_marks_stale_daemon_down(self) -> None:
        overall = collect.overall_from_snapshot(
            {
                "status": "ok",
                "stale": True,
                "age_s": 120.0,
                "error": "stale or missing checked_at",
                "latency_ms": 12.0,
                "checked_at": "2026-09-03T00:00:00+00:00",
            }
        )
        self.assertEqual(overall["status"], "daemon-down")
        self.assertTrue(overall["stale"])
        self.assertTrue(collect.is_farm_degraded(overall))

    def test_edge_triggered_degraded_and_recovered(self) -> None:
        alerter = collect.DashboardDegradedAlert()
        down = {
            "status": "no_workers",
            "stale": False,
            "error": "quiet",
            "latency_ms": 1400,
        }
        first = alerter.observe(down)
        self.assertIsNotNone(first)
        self.assertIn(collect.DEGRADED_TOKEN, first)
        self.assertIn("status=no_workers", first)
        self.assertIn("stale=false", first)
        self.assertIn("error=quiet", first)
        self.assertIsNone(alerter.observe(down))
        recovered = alerter.observe({"status": "ok", "stale": False})
        self.assertIsNotNone(recovered)
        self.assertIn(collect.RECOVERED_DASHBOARD_TOKEN, recovered)
        self.assertIn("status=ok", recovered)
        self.assertIsNone(alerter.observe({"status": "ok", "stale": False}))

    def test_healthy_start_does_not_emit_recovered(self) -> None:
        alerter = collect.DashboardDegradedAlert()
        self.assertIsNone(alerter.observe({"status": "ok", "stale": False}))
        self.assertFalse(alerter.alerted)

    def test_degraded_line_redacts_redis_password(self) -> None:
        line = collect.format_degraded_line(
            {
                "status": "unreachable",
                "stale": False,
                "error": "redis://:super-secret@127.0.0.1:6379/0",
                "latency_ms": None,
            }
        )
        self.assertIn("***", line)
        self.assertNotIn("super-secret", line)


class RedactTests(unittest.TestCase):
    def test_redacts_redis_password(self) -> None:
        raw = "redis://:super-secret@127.0.0.1:6379/0"
        self.assertIn("***", collect.redact_secrets(raw) or "")
        self.assertNotIn("super-secret", collect.redact_secrets(raw) or "")


if __name__ == "__main__":
    raise SystemExit(
        unittest.main(module=None, verbosity=2, exit=False).result.wasSuccessful()
        and 0
        or 1
    )