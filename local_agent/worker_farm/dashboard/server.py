#!/usr/bin/env python3
"""Farm monitoring dashboard — stdlib ThreadingHTTPServer on loopback :8765.

Run with system Python (not the farm venv), from any cwd:

  python local_agent\\worker_farm\\dashboard\\server.py

Or via Start-FarmDashboard.ps1. Env: FARM_DASHBOARD_HOST, FARM_DASHBOARD_PORT.

Default bind is 127.0.0.1 (same family as Redis). Opt in to the WireGuard
hub (10.90.90.1) or a private LAN IPv4 with FARM_DASHBOARD_HOST. Never
0.0.0.0. Polls farm_status.json, farm_health --json, and existing service
checks. Does not reimplement Celery/Redis probes and does not submit jobs.

When overall health is not ok (or the snapshot is stale), prints a greppable
FARM_DASHBOARD_DEGRADED line and a best-effort Windows balloon. Edge-triggered;
FARM_DASHBOARD_RECOVERED on the way back. A 30s watch reads farm_status.json
so this fires without a browser open.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import collect  # noqa: E402

INDEX_PATH = HERE / "index.html"
ALERT_WATCH_INTERVAL_S = 30.0

_alerter = collect.DashboardDegradedAlert()
_alerter_lock = threading.Lock()


def _notify_windows(title: str, body: str) -> None:
    """Best-effort balloon tip. Stdlib + built-in WinForms; never raises."""
    if os.name != "nt":
        return
    title = (title or "Farm dashboard")[:80]
    body = (body or "")[:240]
    title_ps = title.replace("'", "''")
    body_ps = body.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Warning; "
        "$n.Visible = $true; "
        f"$n.ShowBalloonTip(8000, '{title_ps}', '{body_ps}', "
        "[System.Windows.Forms.ToolTipIcon]::Warning); "
        "Start-Sleep -Seconds 10; $n.Dispose()"
    )
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    create = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if create:
        kwargs["creationflags"] = create
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script],
            **kwargs,
        )
    except Exception:
        return


def emit_alert_if_needed(overall: dict) -> str | None:
    """Log a greppable line on healthy<->degraded edges. Optional Windows balloon."""
    with _alerter_lock:
        line = _alerter.observe(overall)
    if not line:
        return None
    sys.stderr.write(line + "\n")
    sys.stderr.flush()
    title = (
        "Farm recovered"
        if line.startswith(collect.RECOVERED_DASHBOARD_TOKEN)
        else "Farm degraded"
    )
    _notify_windows(title, line)
    return line


def _alert_watch_loop(stop: threading.Event, interval_s: float = ALERT_WATCH_INTERVAL_S) -> None:
    """Read farm_status.json on an interval so alerts fire without a browser."""
    while True:
        try:
            snap = collect.read_farm_status()
            emit_alert_if_needed(collect.overall_from_snapshot(snap))
        except Exception as exc:
            sys.stderr.write(
                f"FARM_DASHBOARD_ALERT_ERROR {type(exc).__name__}: {exc}\n"
            )
        if stop.wait(interval_s):
            break


def ensure_firewall_rule(port: int) -> str:
    """Add Private-profile inbound TCP allow for port if missing.

    Returns a short human-readable result string. Never raises.
    """
    if os.name != "nt":
        return "skipped (non-Windows)"
    rule_name = f"FarmDashboard TCP {port} Private"
    try:
        check = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Get-NetFirewallRule -DisplayName '{rule_name}' "
                "-ErrorAction SilentlyContinue | Select-Object -First 1 DisplayName",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if check.returncode == 0 and rule_name in (check.stdout or ""):
            return f"exists: {rule_name}"
        add = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"New-NetFirewallRule -DisplayName '{rule_name}' "
                f"-Direction Inbound -Action Allow -Protocol TCP -LocalPort {port} "
                "-Profile Private -ErrorAction Stop | Out-Null; 'CREATED'",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if add.returncode == 0 and "CREATED" in (add.stdout or ""):
            return f"created: {rule_name} (Private only)"
        err = ((add.stderr or "") + (add.stdout or "")).strip()
        if "Access is denied" in err or "AccessDenied" in err:
            return f"Access Denied creating '{rule_name}' (Private TCP {port}); server will still start"
        if err:
            return f"firewall add failed: {err[:240]}"
        return f"firewall add failed (exit {add.returncode})"
    except Exception as exc:
        return f"firewall check error: {type(exc).__name__}: {exc}"


def load_index_html() -> bytes:
    return INDEX_PATH.read_bytes()


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "FarmDashboard/1.0"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            try:
                self._send(200, load_index_html(), "text/html; charset=utf-8")
            except Exception as exc:
                msg = f"index.html error: {type(exc).__name__}: {exc}".encode("utf-8")
                self._send(500, msg, "text/plain; charset=utf-8")
            return
        if path == "/api/dashboard":
            try:
                payload = collect.build_dashboard_payload()
            except Exception as exc:
                # Last-resort envelope so the page never fully hard-fails.
                payload = {
                    "generated_at": None,
                    "overall": {
                        "status": "error",
                        "stale": True,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc()[-800:],
                }
            try:
                emit_alert_if_needed(payload.get("overall") or {})
            except Exception:
                pass
            self._send_json(200, payload)
            return
        if path == "/api/healthz":
            self._send_json(200, {"ok": True})
            return
        self._send(404, b"not found\n", "text/plain; charset=utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Farm monitoring dashboard (stdlib).")
    parser.add_argument("--host", default=None, help="override FARM_DASHBOARD_HOST")
    parser.add_argument("--port", type=int, default=None, help="override FARM_DASHBOARD_PORT")
    parser.add_argument(
        "--skip-firewall",
        action="store_true",
        help="do not attempt Private-profile firewall rule",
    )
    args = parser.parse_args(argv)

    try:
        host = collect.resolve_bind_host(env_host=args.host)
        port = args.port if args.port is not None else collect.resolve_bind_port()
    except ValueError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 2

    # Belt-and-suspenders: never listen on wildcard / spoke overlay.
    if collect.is_forbidden_bind_host(host) or not collect.is_allowed_bind_host(host):
        sys.stderr.write(f"ERROR: refusing forbidden bind host {host!r}\n")
        return 2

    fw = "skipped (--skip-firewall)"
    if not args.skip_firewall:
        # Loopback and overlay do not need a Private LAN inbound hole.
        if collect.is_acceptable_lan_ipv4(host):
            fw = ensure_firewall_rule(port)
        else:
            fw = "skipped (loopback/overlay bind; no LAN firewall rule)"
    sys.stderr.write(f"firewall: {fw}\n")

    httpd = ThreadingHTTPServer((host, port), DashboardHandler)
    url = f"http://{host}:{port}/"
    sys.stderr.write(f"Farm dashboard listening on {url}\n")
    sys.stderr.write(f"API: http://{host}:{port}/api/dashboard\n")
    print(url, flush=True)
    stop = threading.Event()
    watcher = threading.Thread(
        target=_alert_watch_loop,
        args=(stop,),
        name="farm-dashboard-alert",
        daemon=True,
    )
    watcher.start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\nshutting down\n")
    finally:
        stop.set()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())