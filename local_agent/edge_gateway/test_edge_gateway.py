"""Edge gateway unit tests. System Python from the repository root:

  python -m unittest local_agent.edge_gateway.test_edge_gateway -v

Not the farm venv. This package must stay unloadable of farm broker config.
"""
from __future__ import annotations

import io
import json
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

from local_agent.edge_gateway import constants as C
from local_agent.edge_gateway.ledger import EdgeLedger, EdgeLedgerError
from local_agent.edge_gateway.logutil import EdgeLogError, edge_log
from local_agent.edge_gateway.server import (
    BindPolicyError,
    _PhoneTLSServer,
    _handler_class,
    assert_admin_bind,
    assert_phone_bind,
    phone_ssl_context,
    start_admin_server,
)
from local_agent.edge_gateway.tlsutil import TlsMaterial


PRODUCTION_PY = [
    Path(__file__).resolve().parent / name
    for name in (
        "__init__.py", "__main__.py", "constants.py", "ledger.py",
        "logutil.py", "server.py", "tlsutil.py",
    )
]

FORBIDDEN_SOURCE = (
    "FARM_BROKER_URL",
    "REDIS_PASSWORD",
    "FARM_RESULT_BACKEND",
    "FARM_AES",
    "celery_app",
    "import celery",
    "from celery",
    "import redis",
    "from redis",
    "kombu",
    "load_dotenv",
    ".env.mac_worker",
    "redis-acl",
    "FARM_REDIS",
    "worker_farm",
)


class BindPolicyTests(unittest.TestCase):
    def test_admin_loopback_only(self):
        assert_admin_bind("127.0.0.1", 8744)
        for host in ("0.0.0.0", "10.90.91.1", "10.90.90.1", "192.168.1.1"):
            with self.assertRaises(BindPolicyError):
                assert_admin_bind(host, 8744)
        for port in (6379, 8188, 11434, 11435, 8765, 80):
            with self.assertRaises(BindPolicyError):
                assert_admin_bind("127.0.0.1", port)

    def test_phone_overlay_only(self):
        assert_phone_bind("10.90.91.1", 8743)
        for host in ("0.0.0.0", "127.0.0.1", "10.90.90.1", "10.90.90.2", "192.168.1.1"):
            with self.assertRaises(BindPolicyError):
                assert_phone_bind(host, 8743)
        for port in (6379, 8188, 11434, 11435, 8765, 443):
            with self.assertRaises(BindPolicyError):
                assert_phone_bind("10.90.91.1", port)


class GrepLockTests(unittest.TestCase):
    def test_production_source_has_no_farm_broker_strings(self):
        for path in PRODUCTION_PY:
            text = path.read_text(encoding="utf-8")
            for needle in FORBIDDEN_SOURCE:
                self.assertNotIn(
                    needle, text,
                    f"{path.name} contains forbidden {needle!r}",
                )

    def test_import_does_not_load_farm_modules(self):
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "import local_agent.edge_gateway.server as s\n"
            "mods = set(sys.modules)\n"
            "bad = [m for m in mods if m == 'celery' or m.startswith('celery.') "
            "or m == 'redis' or m.startswith('redis.') "
            "or 'celery_app' in m or m.endswith('.worker_farm.celery_app')]\n"
            "print('OK' if not bad else 'BAD:' + ','.join(sorted(bad)))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "OK", completed.stdout + completed.stderr)


class LogTests(unittest.TestCase):
    def test_log_rejects_prompt_and_result_keys(self):
        with self.assertRaises(EdgeLogError):
            edge_log("x", prompt="secret-prompt")
        with self.assertRaises(EdgeLogError):
            edge_log("x", result="secret-result")
        with self.assertRaises(EdgeLogError):
            edge_log("x", token="tok")

    def test_log_line_has_sizes_not_bodies(self):
        buf = io.StringIO()
        old = sys.stderr
        sys.stderr = buf
        try:
            line = edge_log("complete", job_id="abc", result_chars=12, prompt_chars=4)
        finally:
            sys.stderr = old
        self.assertIn("abc", line)
        self.assertNotIn("the actual prompt text", line)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = EdgeLedger(self.tmp.name)
        self.tls = TlsMaterial(self.tmp.name)
        cert, _key, fp = self.tls.issue_device_cert("pixel1")
        self.token = self.ledger.create_device("pixel1", fp)
        self.fp = fp
        self.cert = cert

    def tearDown(self):
        self.tmp.cleanup()

    def _device(self):
        return self.ledger.lookup_auth(self.token, self.fp)

    def test_inject_rejects_oversized_prompt(self):
        with self.assertRaises(EdgeLedgerError):
            self.ledger.inject_job("x" * (C.MAX_PROMPT_CHARS + 1), 16)

    def test_claim_complete_happy_path(self):
        job = self.ledger.inject_job("health check", 32)
        claimed = self.ledger.claim(self._device())
        self.assertEqual(claimed["id"], job["job_id"])
        self.assertEqual(claimed["kind"], "edge_text_inference")
        self.assertEqual(claimed["prompt"], "health check")
        outcome, code = self.ledger.complete(
            self._device(), claimed["id"], "completed", "ok-result", claimed["attempt"],
        )
        self.assertEqual(code, "ok")
        self.assertEqual(outcome["result"], "ok-result")
        view = self.ledger.admin_job_view(claimed["id"])
        self.assertTrue(view["untrusted"])
        self.assertEqual(view["untrusted_result"], "ok-result")

    def test_second_claim_does_not_share_live_lease(self):
        self.ledger.inject_job("one", 8)
        a = self.ledger.claim(self._device())
        self.assertIsNone(self.ledger.claim(self._device()))
        self.ledger.inject_job("two", 8)
        self.assertIsNone(self.ledger.claim(self._device()))
        self.ledger.complete(
            self._device(), a["id"], "completed", "done", a["attempt"],
        )
        nxt = self.ledger.claim(self._device())
        self.assertEqual(nxt["prompt"], "two")

    def test_complete_replay_first_result_wins(self):
        self.ledger.inject_job("one", 8)
        job = self.ledger.claim(self._device())
        first, _ = self.ledger.complete(
            self._device(), job["id"], "completed", "first", job["attempt"],
        )
        replay, code = self.ledger.complete(
            self._device(), job["id"], "completed", "first", job["attempt"],
        )
        self.assertEqual(code, "replay")
        self.assertEqual(replay["result"], "first")
        with self.assertRaises(EdgeLedgerError) as ctx:
            self.ledger.complete(
                self._device(), job["id"], "completed", "second", job["attempt"],
            )
        self.assertEqual(str(ctx.exception), "replay conflict")
        self.assertEqual(self.ledger.admin_job_view(job["id"])["untrusted_result"], "first")

    def test_revoke_expires_lease_and_blocks_complete(self):
        self.ledger.inject_job("one", 8)
        device = self._device()
        job = self.ledger.claim(device)
        self.ledger.revoke_device("pixel1")
        with self.assertRaises(EdgeLedgerError):
            self.ledger.lookup_auth(self.token, self.fp)
        with self.assertRaises(EdgeLedgerError):
            self.ledger.complete(device, job["id"], "completed", "late", job["attempt"])
        view = self.ledger.admin_job_view(job["id"])
        self.assertEqual(view["state"], "expired")
        self.assertEqual(view["untrusted_result"], "")

    def test_inject_is_only_edge_text_inference(self):
        job = self.ledger.inject_job("ok", 8)
        claimed = self.ledger.claim(self._device())
        self.assertEqual(claimed["kind"], "edge_text_inference")
        self.assertEqual(claimed["id"], job["job_id"])

    def test_result_truncated(self):
        self.ledger.inject_job("one", 8)
        job = self.ledger.claim(self._device())
        huge = "r" * (C.MAX_RESULT_CHARS + 50)
        outcome, _ = self.ledger.complete(
            self._device(), job["id"], "completed", huge, job["attempt"],
        )
        self.assertEqual(len(outcome["result"]), C.MAX_RESULT_CHARS)

    def test_overdue_lease_is_recovered_for_any_device(self):
        from datetime import datetime, timedelta, timezone
        self.ledger.inject_job("stuck", 8)
        self.ledger.inject_job("next", 8)
        first = self.ledger.claim(self._device())
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with self.ledger._connection() as conn:
            conn.execute(
                "UPDATE jobs SET lease_until = ? WHERE job_id = ?",
                (past, first["id"]),
            )
        other_cert, _key, other_fp = self.tls.issue_device_cert("pixel2")
        other_token = self.ledger.create_device("pixel2", other_fp)
        other = self.ledger.lookup_auth(other_token, other_fp)
        claimed = self.ledger.claim(other)
        self.assertEqual(claimed["prompt"], "next")
        self.assertEqual(self.ledger.admin_job_view(first["id"])["state"], "expired")
        with self.assertRaises(EdgeLedgerError):
            self.ledger.complete(
                self._device(), first["id"], "completed", "late", first["attempt"],
            )
        self.assertIsNotNone(other_cert)

    def test_replay_is_limited_to_the_owning_device(self):
        self.ledger.inject_job("one", 8)
        job = self.ledger.claim(self._device())
        self.ledger.complete(
            self._device(), job["id"], "completed", "first", job["attempt"],
        )
        _cert, _key, other_fp = self.tls.issue_device_cert("pixel2")
        other_token = self.ledger.create_device("pixel2", other_fp)
        other = self.ledger.lookup_auth(other_token, other_fp)
        with self.assertRaises(EdgeLedgerError) as ctx:
            self.ledger.complete(other, job["id"], "completed", "first", job["attempt"])
        self.assertEqual(str(ctx.exception), "forbidden")

    def test_device_id_cannot_escape_the_devices_directory(self):
        with self.assertRaises(ValueError):
            self.tls.issue_device_cert("../escaped")
        self.assertFalse((self.tls.root / "escaped" / "client.key.pem").exists())

    def test_prompt_must_fit_context_window(self):
        with self.assertRaises(EdgeLedgerError):
            self.ledger.inject_job("x" * 3000, 400)


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = EdgeLedger(self.tmp.name)
        self.tls = TlsMaterial(self.tmp.name)
        self.tls.ensure_ca_and_server()
        self.admin_token = "t" * 32
        (Path(self.tmp.name) / "admin.token").write_text(self.admin_token, encoding="utf-8")
        self.admin = start_admin_server(
            self.ledger, self.tls, "127.0.0.1", 0, enforce_reserved_port=False,
        )
        self.admin_thread = threading.Thread(target=self.admin.serve_forever, daemon=True)
        self.admin_thread.start()
        bound = self.admin.socket.getsockname()
        self.assertEqual(bound[0], "127.0.0.1")
        ctx = phone_ssl_context(self.tls)
        self.phone = _PhoneTLSServer(
            ("127.0.0.1", 0),
            _handler_class(self.ledger, self.tls, "phone"),
            ctx,
        )
        self.phone_port = self.phone.socket.getsockname()[1]
        self.phone_thread = threading.Thread(target=self.phone.serve_forever, daemon=True)
        self.phone_thread.start()

    def tearDown(self):
        self.admin.shutdown()
        self.phone.shutdown()
        self.admin.server_close()
        self.phone.server_close()
        self.tmp.cleanup()

    def _admin(self, method, path, body=None, expect=200):
        conn = HTTPConnection("127.0.0.1", self.admin.server_address[1], timeout=5)
        raw = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        if raw:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=raw, headers=headers)
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        self.assertEqual(resp.status, expect, data)
        return data

    def _enroll(self):
        created = self._admin("POST", "/v1/admin/devices", {"device_id": "pixel1"}, 201)
        self.assertEqual(created["delivery"], "usb_adb_only")
        cert_path = Path(self.tmp.name) / "client.crt"
        key_path = Path(self.tmp.name) / "client.key"
        cert_path.write_text(created["client_cert_pem"], encoding="ascii")
        key_path.write_text(created["client_key_pem"], encoding="ascii")
        return created["token"], cert_path, key_path, created["ca_cert_pem"]

    def _phone(self, method, path, token, cert, key, ca_pem, body=None):
        ca_path = Path(self.tmp.name) / "ca.pem"
        ca_path.write_text(ca_pem, encoding="ascii")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_verify_locations(str(ca_path))
        ctx.load_cert_chain(str(cert), str(key))
        conn = HTTPSConnection("127.0.0.1", self.phone_port, context=ctx, timeout=5)
        raw = None if body is None else json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Edge-Worker": "termux-powerinfer-contract-v1",
        }
        conn.request(method, path, body=raw, headers=headers)
        resp = conn.getresponse()
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()
        return resp.status, data

    def test_admin_bind_is_loopback(self):
        self.assertEqual(self.admin.socket.getsockname()[0], "127.0.0.1")

    def test_http_claim_complete_and_revoke(self):
        token, cert, key, ca = self._enroll()
        injected = self._admin(
            "POST", "/v1/admin/jobs",
            {"prompt": "health check", "max_tokens": 32},
            201,
        )
        status, claimed = self._phone(
            "POST", "/v1/edge/jobs/claim", token, cert, key, ca,
            {"capabilities": ["*", "distill"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(claimed["job"]["id"], injected["id"])
        self.assertEqual(claimed["job"]["kind"], "edge_text_inference")
        job_id = claimed["job"]["id"]
        status, done = self._phone(
            "POST", f"/v1/edge/jobs/{job_id}/complete", token, cert, key, ca,
            {"id": job_id, "status": "completed", "result": "hello", "attempt": claimed["job"]["attempt"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(done["result"], "hello")
        status, replay = self._phone(
            "POST", f"/v1/edge/jobs/{job_id}/complete", token, cert, key, ca,
            {
                "id": job_id, "status": "completed", "result": "mutated",
                "attempt": claimed["job"]["attempt"],
            },
        )
        self.assertEqual(status, 409)
        view = self._admin("GET", f"/v1/admin/jobs/{job_id}")
        self.assertEqual(view["untrusted_result"], "hello")
        self.assertTrue(view["untrusted"])

    def test_http_revoke_blocks_complete(self):
        token, cert, key, ca = self._enroll()
        injected = self._admin(
            "POST", "/v1/admin/jobs", {"prompt": "health check", "max_tokens": 8}, 201,
        )
        status, claimed = self._phone(
            "POST", "/v1/edge/jobs/claim", token, cert, key, ca,
            {"capabilities": ["edge_text_inference"]},
        )
        self.assertEqual(status, 200)
        job_id = claimed["job"]["id"]
        self._admin("POST", "/v1/admin/devices/pixel1/revoke", {}, 200)
        status, err = self._phone(
            "POST", f"/v1/edge/jobs/{job_id}/complete", token, cert, key, ca,
            {
                "id": job_id, "status": "completed", "result": "late",
                "attempt": claimed["job"]["attempt"],
            },
        )
        self.assertEqual(status, 401)
        view = self._admin("GET", f"/v1/admin/jobs/{injected['id']}")
        self.assertEqual(view["state"], "expired")

    def test_admin_rejects_oversized_prompt(self):
        self._admin(
            "POST", "/v1/admin/jobs",
            {"prompt": "p" * (C.MAX_PROMPT_CHARS + 1)},
            400,
        )

    def test_phone_without_mtls_is_rejected(self):
        token, cert, key, ca = self._enroll()
        self._admin("POST", "/v1/admin/jobs", {"prompt": "x", "max_tokens": 8}, 201)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
        ca_path = Path(self.tmp.name) / "ca2.pem"
        ca_path.write_text(ca, encoding="ascii")
        ctx.load_verify_locations(str(ca_path))
        conn = HTTPSConnection("127.0.0.1", self.phone_port, context=ctx, timeout=5)
        try:
            conn.request(
                "POST", "/v1/edge/jobs/claim",
                body=b"{}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Edge-Worker": "termux-powerinfer-contract-v1",
                    "Content-Type": "application/json",
                },
            )
            conn.getresponse()
            self.fail("expected TLS handshake failure without client cert")
        except (ssl.SSLError, ConnectionError, OSError):
            pass
        finally:
            conn.close()


class DefaultOffTests(unittest.TestCase):
    def test_main_without_listen_is_disabled(self):
        completed = subprocess.run(
            [sys.executable, "-m", "local_agent.edge_gateway",
             "--data-dir", str(ROOT / "local_agent" / "edge_gateway" / "runtime" / "disabled-probe")],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("disabled", completed.stderr)


if __name__ == "__main__":
    raise SystemExit(
        "Run from the repository root:\n"
        "  python -m unittest local_agent.edge_gateway.test_edge_gateway -v\n"
    )
