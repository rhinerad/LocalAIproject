"""Phone mTLS API + loopback admin. Default is off (no --listen)."""
from __future__ import annotations

import argparse
import hmac
import ipaddress
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .constants import (
    ADMIN_BIND_HOST,
    ADMIN_PORT,
    FARM_OVERLAY_PREFIX,
    FORBIDDEN_PORTS,
    MAX_BODY_BYTES,
    PHONE_BIND_HOST,
    PHONE_PORT,
    WORKER_HEADER,
    WORKER_HEADER_NAME,
)
from .ledger import EdgeLedger, EdgeLedgerError
from .logutil import edge_log
from .tlsutil import TlsMaterial, cert_fingerprint_der


class BindPolicyError(ValueError):
    """Listen address is not the signed-off admin loopback or phone overlay."""


def assert_admin_bind(host: str, port: int) -> None:
    if host != ADMIN_BIND_HOST:
        raise BindPolicyError("admin must bind 127.0.0.1 only")
    if int(port) in FORBIDDEN_PORTS:
        raise BindPolicyError("admin port is reserved")
    if int(port) != ADMIN_PORT:
        raise BindPolicyError("admin port must be 8744")


def assert_phone_bind(host: str, port: int) -> None:
    if host != PHONE_BIND_HOST:
        raise BindPolicyError("phone API must bind 10.90.91.1 only")
    if host.startswith(FARM_OVERLAY_PREFIX):
        raise BindPolicyError("phone API must not bind the farm overlay")
    if host in {"0.0.0.0", "::", "::0"}:
        raise BindPolicyError("phone API must not bind all interfaces")
    if int(port) in FORBIDDEN_PORTS:
        raise BindPolicyError("phone port is reserved")
    if int(port) != PHONE_PORT:
        raise BindPolicyError("phone port must be 8743")


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")


def _admin_token_ok(presented: str, expected: str) -> bool:
    if not presented.startswith("Bearer "):
        return False
    got = presented[len("Bearer "):].strip().encode("utf-8")
    exp = expected.encode("utf-8")
    if len(got) != len(exp):
        return False
    return hmac.compare_digest(got, exp)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length < 0 or length > MAX_BODY_BYTES:
        raise EdgeLedgerError("body too large")
    raw = handler.rfile.read(length) if length else b"{}"
    if len(raw) > MAX_BODY_BYTES:
        raise EdgeLedgerError("body too large")
    try:
        parsed = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EdgeLedgerError("invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise EdgeLedgerError("JSON object required")
    return parsed


class _BaseHandler(BaseHTTPRequestHandler):
    ledger: EdgeLedger
    tls: TlsMaterial
    mode: str
    admin_token: str
    server_version = "PowerInferEdge/1.0"

    def log_message(self, fmt: str, *args) -> None:
        path = ""
        try:
            path = urlparse(self.path).path
        except Exception:
            path = ""
        try:
            edge_log(
                "http",
                path=path,
                http_status=0,
                peer_ip=self.client_address[0],
                reason=(fmt % args)[:80],
            )
        except Exception:
            return

    def _send(self, code: int, payload: dict) -> None:
        body = _json_bytes(payload)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.mode != "admin":
            self._send(405, {"error": "method not allowed"})
            return
        if not self._admin_authorized():
            return
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if parts[:3] == ["v1", "admin", "jobs"] and len(parts) == 4:
            try:
                view = self.ledger.admin_job_view(parts[3])
            except EdgeLedgerError as exc:
                self._send(404, {"error": str(exc)})
                return
            self._send(200, view)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if self.mode == "admin":
                self._admin_post(path)
            else:
                self._phone_post(path)
        except (TimeoutError, socket.timeout):
            self._send(408, {"error": "timeout"})
            return
        except EdgeLedgerError as exc:
            reason = str(exc)
            code = 401 if reason == "unauthorized" else 400
            if reason == "forbidden":
                code = 403
            if reason == "replay conflict":
                code = 409
            if reason == "rate limited":
                code = 429
            edge_log(
                "error",
                path=path,
                http_status=code,
                peer_ip=self.client_address[0],
                reason=reason[:80],
            )
            self._send(code, {"error": reason})

    def _admin_authorized(self) -> bool:
        if self.client_address[0] not in {"127.0.0.1", "::1"}:
            self._send(403, {"error": "admin is loopback only"})
            return False
        if not _admin_token_ok(self.headers.get("Authorization", ""), self.admin_token):
            self._send(401, {"error": "unauthorized"})
            return False
        return True

    def _admin_post(self, path: str) -> None:
        if not self._admin_authorized():
            return
        body = _read_json(self)
        parts = path.strip("/").split("/")
        if parts == ["v1", "admin", "devices"]:
            device_id = str(body.get("device_id") or "")
            try:
                self.tls.device_dir(device_id)
            except ValueError as exc:
                raise EdgeLedgerError(str(exc)) from exc
            if self.ledger.device_exists(device_id):
                raise EdgeLedgerError("device_id already exists")
            try:
                cert_pem, key_pem, fingerprint = self.tls.issue_device_cert(device_id)
            except ValueError as exc:
                raise EdgeLedgerError(str(exc)) from exc
            try:
                token = self.ledger.create_device(device_id, fingerprint)
            except EdgeLedgerError:
                self.tls.remove_device_material(device_id)
                raise
            edge_log("device_created", device_id=device_id, path=path, http_status=201)
            self._send(201, {
                "device_id": device_id,
                "token": token,
                "client_cert_pem": cert_pem.decode("ascii"),
                "client_key_pem": key_pem.decode("ascii"),
                "ca_cert_pem": self.tls.ca_cert_path.read_text(encoding="ascii"),
                "delivery": "usb_adb_only",
            })
            return
        if (
            parts[:3] == ["v1", "admin", "devices"]
            and len(parts) == 5
            and parts[4] == "revoke"
        ):
            result = self.ledger.revoke_device(parts[3])
            edge_log(
                "device_revoked",
                device_id=parts[3],
                path=path,
                http_status=200,
            )
            self._send(200, result)
            return
        if parts == ["v1", "admin", "jobs"]:
            prompt = body.get("prompt")
            max_tokens = body.get("max_tokens")
            job = self.ledger.inject_job(prompt, max_tokens)
            edge_log(
                "job_injected",
                job_id=job["job_id"],
                prompt_chars=job["prompt_chars"],
                path=path,
                http_status=201,
            )
            self._send(201, {
                "id": job["job_id"],
                "kind": job["kind"],
                "state": job["state"],
                "prompt_chars": job["prompt_chars"],
                "max_tokens": job["max_tokens"],
            })
            return
        self._send(404, {"error": "not found"})

    def _phone_auth(self) -> dict:
        header = self.headers.get(WORKER_HEADER_NAME, "")
        if header != WORKER_HEADER:
            raise EdgeLedgerError("unauthorized")
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise EdgeLedgerError("unauthorized")
        token = auth[len("Bearer "):].strip()
        der = None
        try:
            der = self.connection.getpeercert(binary_form=True)
        except Exception:
            der = None
        if not der:
            raise EdgeLedgerError("unauthorized")
        fingerprint = cert_fingerprint_der(der)
        return self.ledger.lookup_auth(token, fingerprint)

    def _phone_post(self, path: str) -> None:
        device = self._phone_auth()
        body = _read_json(self)
        parts = path.strip("/").split("/")
        if parts == ["v1", "edge", "jobs", "claim"]:
            # capabilities in the body are ignored for authorization (device row).
            job = self.ledger.claim(device)
            edge_log(
                "claim",
                device_id=device["device_id"],
                job_id="" if job is None else job["id"],
                prompt_chars=0 if job is None else len(job["prompt"]),
                path=path,
                http_status=200,
                peer_ip=self.client_address[0],
            )
            self._send(200, {"job": job})
            return
        if (
            parts[:3] == ["v1", "edge", "jobs"]
            and len(parts) == 5
            and parts[4] == "complete"
        ):
            job_id = parts[3]
            body_id = body.get("id")
            if body_id is not None and body_id != job_id:
                raise EdgeLedgerError("job id is invalid")
            attempt = body.get("attempt")
            outcome, code = self.ledger.complete(
                device, job_id, str(body.get("status") or ""),
                body.get("result") or "", attempt,
            )
            http_status = 200 if code != "conflict" else 409
            edge_log(
                "complete",
                device_id=device["device_id"],
                job_id=job_id,
                status=outcome["status"],
                result_chars=len(outcome["result"]),
                path=path,
                http_status=http_status,
                peer_ip=self.client_address[0],
            )
            self._send(http_status, outcome)
            return
        self._send(404, {"error": "not found"})


def _handler_class(ledger: EdgeLedger, tls: TlsMaterial, mode: str):
    class Handler(_BaseHandler):
        pass

    Handler.ledger = ledger
    Handler.tls = tls
    Handler.mode = mode
    Handler.admin_token = ""
    return Handler


class _BoundedServer(ThreadingHTTPServer):
    """Cap worker threads. Handshake must not run on the accept loop."""

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 8
    max_in_flight = 4

    def __init__(self, address, handler):
        self._slots = threading.BoundedSemaphore(self.max_in_flight)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class _PhoneTLSServer(_BoundedServer):
    handshake_timeout = 10
    request_timeout = 30

    def __init__(self, address, handler, ssl_context: ssl.SSLContext):
        self.ssl_context = ssl_context
        super().__init__(address, handler)

    def process_request_thread(self, request, client_address):
        tls_sock = None
        try:
            request.settimeout(self.handshake_timeout)
            try:
                tls_sock = self.ssl_context.wrap_socket(request, server_side=True)
            except Exception:
                try:
                    request.close()
                except Exception:
                    pass
                return
            tls_sock.settimeout(self.request_timeout)
            try:
                self.finish_request(tls_sock, client_address)
            except Exception:
                self.handle_error(tls_sock, client_address)
            finally:
                self.shutdown_request(tls_sock)
        finally:
            self._slots.release()


class _AdminServer(_BoundedServer):
    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(30)
        except Exception:
            pass
        super().process_request_thread(request, client_address)


def phone_ssl_context(tls: TlsMaterial) -> ssl.SSLContext:
    tls.ensure_ca_and_server()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_cert_chain(str(tls.server_cert_path), str(tls.server_key_path))
    ctx.load_verify_locations(str(tls.ca_cert_path))
    ctx.check_hostname = False
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _read_admin_token(data_dir: Path) -> str:
    path = Path(data_dir) / "admin.token"
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise BindPolicyError("admin token is missing") from exc
    if len(token) < 24:
        raise BindPolicyError("admin token is missing")
    return token


def _restrict_token_acl(path: Path) -> None:
    if sys.platform != "win32":
        path.chmod(0o600)
        return
    who = subprocess.run(
        ["whoami"], capture_output=True, text=True, check=False,
    )
    user = (who.stdout or "").strip() or os.environ.get("USERNAME", "")
    if not user:
        return
    subprocess.run(
        [
            "icacls", str(path), "/inheritance:r", "/grant:r",
            "NT AUTHORITY\\SYSTEM:F", "BUILTIN\\Administrators:F", f"{user}:F",
        ],
        check=False, capture_output=True,
    )


def ensure_admin_token(data_dir: Path) -> None:
    path = Path(data_dir) / "admin.token"
    if not path.is_file() or len(path.read_text(encoding="utf-8").strip()) < 24:
        path.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
        sys.stderr.write(f"admin token created at {path}; contents not shown\n")
    _restrict_token_acl(path)


def start_admin_server(
    ledger: EdgeLedger, tls: TlsMaterial, host: str, port: int,
    *, enforce_reserved_port: bool = True,
):
    if enforce_reserved_port:
        assert_admin_bind(host, port)
    elif host not in {"127.0.0.1", "::1"}:
        raise BindPolicyError("admin must bind loopback")
    token = _read_admin_token(ledger.root)
    handler = _handler_class(ledger, tls, "admin")
    handler.admin_token = token
    httpd = _AdminServer((host, port), handler)
    bound = httpd.socket.getsockname()
    if bound[0] not in {"127.0.0.1", "::1"}:
        httpd.server_close()
        raise BindPolicyError("admin socket is not loopback")
    return httpd


def start_phone_server(ledger: EdgeLedger, tls: TlsMaterial, host: str, port: int):
    assert_phone_bind(host, port)
    ctx = phone_ssl_context(tls)
    httpd = _PhoneTLSServer((host, port), _handler_class(ledger, tls, "phone"), ctx)
    bound = httpd.socket.getsockname()[0]
    try:
        ipaddress.ip_address(bound)
    except ValueError:
        httpd.server_close()
        raise BindPolicyError("phone socket address is invalid")
    if bound != PHONE_BIND_HOST:
        httpd.server_close()
        raise BindPolicyError("phone socket is not the overlay unicast")
    return httpd


def serve_in_thread(httpd) -> threading.Thread:
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return thread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Disabled-by-default PowerInfer-2 edge gateway (workstation)"
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument(
        "--listen", action="store_true",
        help="bind admin 127.0.0.1:8744 and phone 10.90.91.1:8743 (mTLS)",
    )
    args = parser.parse_args(argv)
    if not args.listen:
        sys.stderr.write("edge gateway disabled; pass --listen to bind\n")
        return 2
    try:
        assert_admin_bind(ADMIN_BIND_HOST, ADMIN_PORT)
        assert_phone_bind(PHONE_BIND_HOST, PHONE_PORT)
    except BindPolicyError as exc:
        sys.stderr.write(f"edge gateway bind refused: {exc}\n")
        return 2
    data_dir = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    ensure_admin_token(data_dir)
    ledger = EdgeLedger(data_dir)
    tls = TlsMaterial(data_dir)
    tls.ensure_ca_and_server()
    admin = None
    phone = None
    try:
        # Phone overlay first: if 10.90.91.1 is missing, do not leave admin open.
        phone = start_phone_server(ledger, tls, PHONE_BIND_HOST, PHONE_PORT)
        admin = start_admin_server(ledger, tls, ADMIN_BIND_HOST, ADMIN_PORT)
    except OSError as exc:
        if phone is not None:
            phone.server_close()
        if admin is not None:
            admin.server_close()
        sys.stderr.write(f"edge gateway listen failed: {exc}\n")
        return 2
    edge_log("listen", path="admin", peer_ip=ADMIN_BIND_HOST, reason="admin-loopback")
    edge_log("listen", path="phone", peer_ip=PHONE_BIND_HOST, reason="phone-overlay")
    try:
        phone_thread = serve_in_thread(phone)
        admin.serve_forever()
        phone_thread.join()
    except KeyboardInterrupt:
        return 0
    finally:
        admin.shutdown()
        phone.shutdown()
        admin.server_close()
        phone.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
