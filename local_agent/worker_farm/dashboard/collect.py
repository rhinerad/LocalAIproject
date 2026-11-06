"""Farm dashboard collectors and pure helpers.

Stdlib only. Pure functions are unit-tested without a live farm.
Windows service/process checks are best-effort and never raise into the HTTP layer.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
FARM_DIR = HERE.parent
REPO_ROOT = FARM_DIR.parent.parent  # .../COMFYUI_STORY_HANDOFF_2026-08-09

STATUS_JSON = FARM_DIR / "farm_status.json"
DAEMON_LOG = FARM_DIR / "runtime" / "farm_status_daemon.log"
RELAY_LOG = FARM_DIR / "runtime" / "tunnel_relay.log"
VENV_PY = FARM_DIR / ".venv" / "Scripts" / "python.exe"

OUTAGE_TOKEN = "FARM_STATUS_OUTAGE"
RECOVERED_TOKEN = "FARM_STATUS_RECOVERED"
DEGRADED_TOKEN = "FARM_DASHBOARD_DEGRADED"
RECOVERED_DASHBOARD_TOKEN = "FARM_DASHBOARD_RECOVERED"
EVENT_CAP = 20
STALE_AFTER_S = 90.0
CACHE_TTL_S = 30.0
FARM_HEALTH_TIMEOUT_S = 12.0
RELAY_PEER_RECENT_S = 300.0  # 5 minutes

HOST_ENV = "FARM_DASHBOARD_HOST"
PORT_ENV = "FARM_DASHBOARD_PORT"
DEFAULT_PORT = 8765
DEFAULT_BIND_HOST = "127.0.0.1"
OVERLAY_HUB_HOST = "10.90.90.1"

EXPECTED_REGISTERED_TASKS = (
    "local_agent.worker_farm.tasks.connectivity_probe",
    "local_agent.worker_farm.tasks.judge_transcript",
    "local_agent.worker_farm.tasks.summarize_conversation",
    "local_agent.worker_farm.tasks.embed_chunks",
)

# Scheme-agnostic userinfo masker (redis://user:pw@, redis://:pw@, rediss://,
# amqp://...). Username is kept, password replaced. Same shape as
# farm_health.redact_url_credentials and farm_core._URL_CREDENTIAL_RE.
_PASSWORD_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^\s/@:]*):?[^\s/@]*@")
# Worker-name pattern that identifies the Mac spoke. Override per deployment
# with FARM_DASHBOARD_MAC_WORKER_RE (the default is this workstation's).
MAC_WORKER_RE_ENV = "FARM_DASHBOARD_MAC_WORKER_RE"
DEFAULT_MAC_WORKER_RE = r"celery@.*(?:MBP|Mac|Louise)"


def _compile_mac_worker_re(raw: str | None = None) -> re.Pattern[str]:
    value = raw if raw is not None else os.environ.get(MAC_WORKER_RE_ENV)
    if value is None or not str(value).strip():
        value = DEFAULT_MAC_WORKER_RE
    try:
        return re.compile(str(value), re.IGNORECASE)
    except re.error:
        return re.compile(DEFAULT_MAC_WORKER_RE, re.IGNORECASE)


_MAC_WORKER_RE = _compile_mac_worker_re()
_RELAY_PEER_RE = re.compile(
    r"('|\")?10\.90\.90\.2('|\")?|relay connection (?:from|closed).*10\.90\.90\.2",
    re.IGNORECASE,
)
_LOG_TS_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:,\d+)?)"
)

_cache: dict[str, tuple[float, Any]] = {}
# Guards _cache itself; _cache_locks holds one lock per key so that a cache
# miss is filled by exactly one thread while the others wait for its result
# (single-flight), instead of every concurrent /api/dashboard request
# spawning its own farm_health / powershell / docker subprocess.
_cache_lock = threading.Lock()
_cache_locks: dict[str, threading.Lock] = {}


def redact_secrets(text: str | None) -> str | None:
    """Strip passwords from broker URLs / exception text (any URL scheme)."""
    if text is None:
        return None
    return _PASSWORD_RE.sub(r"\1\2:***@", str(text))


def parse_outage_events(text: str, n: int = EVENT_CAP) -> list[str]:
    """Return the last N lines that contain OUTAGE or RECOVERED tokens."""
    if n <= 0:
        return []
    matched: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if OUTAGE_TOKEN in line or RECOVERED_TOKEN in line:
            matched.append(line)
    if len(matched) > n:
        return matched[-n:]
    return matched


def parse_checked_at(checked_at: str | None) -> datetime | None:
    if not checked_at:
        return None
    raw = str(checked_at).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def snapshot_age_s(
    checked_at: str | None,
    now: datetime | None = None,
) -> float | None:
    """Seconds since checked_at, or None if unparseable."""
    dt = parse_checked_at(checked_at)
    if dt is None:
        return None
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return max(0.0, (ref - dt).total_seconds())


def is_stale(
    checked_at: str | None,
    now: datetime | None = None,
    stale_after_s: float = STALE_AFTER_S,
) -> bool:
    """True when missing/unparseable or age > stale_after_s."""
    age = snapshot_age_s(checked_at, now=now)
    if age is None:
        return True
    return age > stale_after_s


def overall_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Dashboard overall block. Same classification as /api/dashboard."""
    overall_status = snapshot.get("status") or "unknown"
    if snapshot.get("stale"):
        overall_status = "daemon-down"
    return {
        "status": overall_status,
        "checked_at": snapshot.get("checked_at"),
        "age_s": snapshot.get("age_s"),
        "stale": bool(snapshot.get("stale")),
        "error": snapshot.get("error"),
        "latency_ms": snapshot.get("latency_ms"),
    }


def is_farm_degraded(overall: dict[str, Any] | None) -> bool:
    """True when the dashboard's existing overall block is not healthy.

    Reuses overall.status / overall.stale. status == "ok" and not stale is
    the only healthy case. Does not invent a second health definition
    (no extra latency cutoff, no missing-task alert).
    """
    if not overall:
        return True
    if overall.get("stale"):
        return True
    status = str(overall.get("status") or "unknown").strip().lower()
    return status != "ok"


def format_degraded_line(overall: dict[str, Any]) -> str:
    status = overall.get("status") or "unknown"
    stale = "true" if overall.get("stale") else "false"
    error = redact_secrets(overall.get("error")) or "(none)"
    latency = overall.get("latency_ms")
    return (
        f"{DEGRADED_TOKEN} status={status} stale={stale} "
        f"latency_ms={latency} error={error}"
    )


def format_dashboard_recovered_line(overall: dict[str, Any]) -> str:
    status = overall.get("status") or "ok"
    return f"{RECOVERED_DASHBOARD_TOKEN} status={status}"


class DashboardDegradedAlert:
    """Edge-triggered greppable lines from the dashboard overall block.

    First degraded observation emits FARM_DASHBOARD_DEGRADED. Stay-degraded
    polls are silent. First healthy observation after an alert emits
    FARM_DASHBOARD_RECOVERED. No consecutive-N / heartbeat — the snapshot
    already has the daemon's 3-fail outage line and a 90s stale threshold.
    """

    def __init__(self) -> None:
        self.alerted = False

    def observe(self, overall: dict[str, Any] | None) -> str | None:
        now_degraded = is_farm_degraded(overall)
        payload = overall or {}
        if now_degraded:
            if self.alerted:
                return None
            self.alerted = True
            return format_degraded_line(payload)
        if not self.alerted:
            return None
        self.alerted = False
        return format_dashboard_recovered_line(payload)


def is_forbidden_bind_host(host: str) -> bool:
    """Reject wildcard, unspecified, link-local, and non-hub overlay addresses.

    Loopback (default) and the WireGuard hub ``10.90.90.1`` are allowed.
    Home-LAN IPv4 is allowed only as an explicit ``FARM_DASHBOARD_HOST`` opt-in.
    """
    h = (host or "").strip().lower()
    if not h:
        return True
    if h in {"0.0.0.0", "::", "::0", "*"}:
        return True
    if h in {"127.0.0.1", "::1", "localhost"}:
        return False
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        # Hostnames are not used for bind selection here.
        return True
    if ip.is_unspecified or ip.is_link_local:
        return True
    if ip.is_loopback:
        return False
    if str(ip) == OVERLAY_HUB_HOST:
        return False
    if ipaddress.IPv4Address("10.90.90.0") <= ip <= ipaddress.IPv4Address("10.90.90.255"):
        return True
    return False


def is_loopback_bind_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if h in {"127.0.0.1", "::1", "localhost"}:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def is_overlay_hub_bind_host(host: str) -> bool:
    return (host or "").strip() == OVERLAY_HUB_HOST


def is_acceptable_lan_ipv4(host: str) -> bool:
    """True for private home-LAN IPv4 (not loopback, not WireGuard overlay)."""
    if is_forbidden_bind_host(host) or is_loopback_bind_host(host):
        return False
    if is_overlay_hub_bind_host(host):
        return False
    try:
        ip = ipaddress.ip_address(host.strip())
    except ValueError:
        return False
    if not isinstance(ip, ipaddress.IPv4Address):
        return False
    return bool(ip.is_private)


def is_allowed_bind_host(host: str) -> bool:
    """True for loopback, overlay hub, or explicit private LAN IPv4."""
    if is_forbidden_bind_host(host):
        return False
    return (
        is_loopback_bind_host(host)
        or is_overlay_hub_bind_host(host)
        or is_acceptable_lan_ipv4(host)
    )


def detect_lan_ipv4_candidates() -> list[str]:
    """List private LAN IPv4 addresses via Get-NetIPAddress (Windows)."""
    if os.name != "nt":
        return []
    ps = (
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object { $_.IPAddress -and $_.PrefixOrigin -ne 'WellKnown' } | "
        "Select-Object -ExpandProperty IPAddress"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    out: list[str] = []
    for line in (proc.stdout or "").splitlines():
        ip = line.strip()
        if ip and is_acceptable_lan_ipv4(ip) and ip not in out:
            out.append(ip)
    return out


def resolve_bind_host(
    env_host: str | None = None,
    candidates: list[str] | None = None,
) -> str:
    """Pick bind host. Default is loopback. LAN/overlay only when explicit.

    ``candidates`` is ignored for the default (kept so old tests can pass a
    LAN list and prove it is *not* auto-selected). Set ``FARM_DASHBOARD_HOST``
    (or ``env_host``) to a private LAN IPv4 or ``10.90.90.1`` to opt in.
    """
    del candidates  # default must not auto-pick a LAN NIC
    explicit = (env_host if env_host is not None else os.environ.get(HOST_ENV) or "").strip()
    if explicit:
        if not is_allowed_bind_host(explicit):
            raise ValueError(
                f"refusing bind host {explicit!r}: "
                "must be 127.0.0.1, 10.90.90.1, or a private LAN IPv4 "
                "(not 0.0.0.0, link-local, or other 10.90.90.x)"
            )
        return explicit
    return DEFAULT_BIND_HOST


def resolve_bind_port(env_port: str | None = None) -> int:
    raw = env_port if env_port is not None else os.environ.get(PORT_ENV)
    if raw is None or str(raw).strip() == "":
        return DEFAULT_PORT
    port = int(str(raw).strip())
    if not (1 <= port <= 65535):
        raise ValueError(f"invalid FARM_DASHBOARD_PORT: {raw!r}")
    return port


def _cache_get(key: str) -> Any | None:
    with _cache_lock:
        item = _cache.get(key)
    if not item:
        return None
    ts, value = item
    if time.monotonic() - ts > CACHE_TTL_S:
        return None
    return value


def _cache_set(key: str, value: Any) -> Any:
    with _cache_lock:
        _cache[key] = (time.monotonic(), value)
    return value


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _key_lock(key: str) -> threading.Lock:
    with _cache_lock:
        lock = _cache_locks.get(key)
        if lock is None:
            lock = _cache_locks[key] = threading.Lock()
        return lock


def cached_single_flight(key: str, compute: Callable[[], Any],
                         use_cache: bool = True) -> Any:
    """Return the cached value for key, or compute it exactly once per miss.

    Concurrent callers that miss at the same time block on the per-key lock
    and then read the value the first one stored, so a slow probe
    (farm_health subprocess, Get-Service, docker ps) runs once per TTL
    window no matter how many browser tabs poll. use_cache=False bypasses
    both the cache and the lock.
    """
    if not use_cache:
        return compute()
    hit = _cache_get(key)
    if hit is not None:
        return hit
    with _key_lock(key):
        hit = _cache_get(key)
        if hit is not None:
            return hit
        return _cache_set(key, compute())


def read_farm_status(path: Path | None = None) -> dict[str, Any]:
    """Always-fresh snapshot read. Never raises; section carries error/stale."""
    dest = Path(path) if path is not None else STATUS_JSON
    section: dict[str, Any] = {
        "ok": False,
        "stale": True,
        "age_s": None,
        "error": None,
        "checked_at": None,
        "broker_reachable": None,
        "workers_responding": None,
        "latency_ms": None,
        "workers": [],
        "status": "daemon-down",
        "snapshot_error": None,
    }
    try:
        raw = dest.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise TypeError("farm_status.json root is not an object")
    except FileNotFoundError:
        section["error"] = "farm_status.json missing"
        return section
    except Exception as exc:
        section["error"] = f"{type(exc).__name__}: {exc}"
        return section

    checked_at = data.get("checked_at")
    age = snapshot_age_s(checked_at)
    stale = is_stale(checked_at)
    section.update(
        {
            "ok": not stale and data.get("status") is not None,
            "stale": stale,
            "age_s": None if age is None else round(age, 1),
            "checked_at": checked_at,
            "broker_reachable": bool(data.get("broker_reachable")),
            "workers_responding": bool(data.get("workers_responding")),
            "latency_ms": data.get("latency_ms"),
            "workers": list(data.get("workers") or []),
            "status": "daemon-down" if stale else (data.get("status") or "unknown"),
            "snapshot_error": redact_secrets(data.get("error")),
            "error": (
                "stale or missing checked_at"
                if stale
                else None
            ),
        }
    )
    return section


def read_outage_events(path: Path | None = None, n: int = EVENT_CAP) -> dict[str, Any]:
    dest = Path(path) if path is not None else DAEMON_LOG
    section: dict[str, Any] = {"ok": False, "events": [], "error": None}
    try:
        text = dest.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        section["error"] = "farm_status_daemon.log missing"
        return section
    except Exception as exc:
        section["error"] = f"{type(exc).__name__}: {exc}"
        return section
    section["events"] = parse_outage_events(text, n=n)
    section["ok"] = True
    return section


def run_farm_health_json(
    venv_py: Path | None = None,
    cwd: Path | None = None,
    timeout_s: float = FARM_HEALTH_TIMEOUT_S,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Cached, single-flight wrapper around _run_farm_health_json_uncached."""
    return cached_single_flight(
        "farm_health",
        lambda: _run_farm_health_json_uncached(venv_py, cwd, timeout_s),
        use_cache=use_cache,
    )


def _run_farm_health_json_uncached(
    venv_py: Path | None = None,
    cwd: Path | None = None,
    timeout_s: float = FARM_HEALTH_TIMEOUT_S,
) -> dict[str, Any]:
    """Invoke farm_health --json via farm venv. Cached ~30s. Never raises."""
    section: dict[str, Any] = {
        "ok": False,
        "error": None,
        "registered_tasks": [],
        "tasks_by_worker": {},
        "missing_expected_tasks": list(EXPECTED_REGISTERED_TASKS),
        "expected_tasks": list(EXPECTED_REGISTERED_TASKS),
        "registered_check": None,
        "workers": [],
        "status": "unknown",
    }
    py = Path(venv_py) if venv_py is not None else VENV_PY
    work = Path(cwd) if cwd is not None else REPO_ROOT
    if not py.is_file():
        section["error"] = f"farm venv python missing: {py}"
        return section

    try:
        proc = subprocess.run(
            [str(py), "-m", "local_agent.worker_farm.farm_health", "--json"],
            cwd=str(work),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        section["error"] = f"farm_health timed out after {timeout_s}s"
        return section
    except Exception as exc:
        section["error"] = f"{type(exc).__name__}: {exc}"
        return section

    stdout = redact_secrets(proc.stdout or "") or ""
    stderr = redact_secrets(proc.stderr or "") or ""
    if not stdout.strip():
        section["error"] = (
            f"farm_health empty stdout (exit={proc.returncode})"
            + (f"; stderr={stderr.strip()[:240]}" if stderr.strip() else "")
        )
        return section
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        section["error"] = f"farm_health JSON decode: {exc}"
        return section

    if not isinstance(data, dict):
        section["error"] = "farm_health returned non-object"
        return section

    registered = data.get("registered_check") or {}
    # Prefer dedicated registered_check block when present.
    if isinstance(registered, dict) and registered:
        section["registered_tasks"] = list(registered.get("registered_tasks") or [])
        section["tasks_by_worker"] = dict(registered.get("tasks_by_worker") or {})
        raw_missing = registered.get("missing_expected_tasks")
        if raw_missing is None:
            section["missing_expected_tasks"] = list(EXPECTED_REGISTERED_TASKS)
        else:
            section["missing_expected_tasks"] = list(raw_missing)
        section["expected_tasks"] = list(
            registered.get("expected_tasks") or EXPECTED_REGISTERED_TASKS
        )
        section["registered_check"] = {
            "status": registered.get("status"),
            "error": redact_secrets(registered.get("error")),
            "missing_expected_tasks": section["missing_expected_tasks"],
        }
        section["status"] = registered.get("status") or data.get("status") or "unknown"
    else:
        section["registered_tasks"] = list(data.get("registered_tasks") or [])
        section["tasks_by_worker"] = dict(data.get("tasks_by_worker") or {})
        raw_missing = data.get("missing_expected_tasks")
        if raw_missing is None:
            section["missing_expected_tasks"] = list(EXPECTED_REGISTERED_TASKS)
        else:
            section["missing_expected_tasks"] = list(raw_missing)
        section["status"] = data.get("status") or "unknown"

    section["workers"] = list(data.get("workers") or [])
    section["ok"] = True
    section["error"] = redact_secrets(data.get("error"))
    # Keep distill_export visible if present; never treat missing distill as failure
    # (EXPECTED_REGISTERED_TASKS already excludes it).
    return section


def _run_ps(command: str, timeout_s: float = 8.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return 1, "", "powershell timeout"
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def check_wireguard_hub(use_cache: bool = True) -> dict[str, Any]:
    """Cached, single-flight wrapper around _check_wireguard_hub_uncached."""
    return cached_single_flight(
        "wg_hub", lambda: _check_wireguard_hub_uncached(), use_cache=use_cache)


def _check_wireguard_hub_uncached() -> dict[str, Any]:
    section: dict[str, Any] = {
        "ok": False,
        "state": "unknown",
        "status": None,
        "start_type": None,
        "error": None,
    }
    if os.name != "nt":
        section["error"] = "WireGuard hub check is Windows-only"
        return section
    code, out, err = _run_ps(
        "$svc = Get-Service -Name 'WireGuardTunnel$hub' -ErrorAction Stop; "
        "Write-Output ($svc.Status.ToString() + '|' + $svc.StartType.ToString())"
    )
    if code != 0 or not out.strip():
        section["error"] = (err or out or "Get-Service failed").strip()[:300]
        section["state"] = "unknown"
        return section
    parts = out.strip().split("|", 1)
    if len(parts) != 2:
        section["error"] = f"unexpected Get-Service output: {out.strip()[:120]}"
        return section
    status, start_type = parts[0].strip(), parts[1].strip()
    section["status"] = status
    section["start_type"] = start_type
    running = status.lower() == "running"
    section["ok"] = running
    section["state"] = "up" if running else "down"
    return section


def _relay_log_recent_peer(
    path: Path | None = None,
    within_s: float = RELAY_PEER_RECENT_S,
    now: datetime | None = None,
) -> bool:
    dest = Path(path) if path is not None else RELAY_LOG
    try:
        text = dest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    ref = now or datetime.now(timezone.utc)
    # Scan last ~200 lines for peer 10.90.90.2 with a recent timestamp.
    lines = text.splitlines()[-200:]
    for line in reversed(lines):
        if "10.90.90.2" not in line:
            continue
        m = _LOG_TS_RE.match(line.strip())
        if not m:
            # No timestamp: skip (do not treat as recent).
            continue
        ts_raw = m.group("ts").replace(",", ".")
        try:
            # Relay log timestamps are local wall clock on this workstation.
            dt = datetime.strptime(ts_raw[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        try:
            local_tz = datetime.now().astimezone().tzinfo
            dt = dt.replace(tzinfo=local_tz)
        except Exception:
            dt = dt.replace(tzinfo=timezone.utc)
        age = abs((ref - dt.astimezone(timezone.utc)).total_seconds())
        if age <= within_s:
            return True
        # First matching peer line is the newest; if it is old, stop.
        return False
    return False


def infer_wireguard_spoke(
    workers: list[str] | None,
    hub_state: str | None,
    relay_log: Path | None = None,
) -> dict[str, Any]:
    """Infer Mac spoke status without wg show / ICMP."""
    section: dict[str, Any] = {
        "ok": False,
        "state": "unknown",
        "reason": None,
        "error": None,
    }
    names = list(workers or [])
    if any(_MAC_WORKER_RE.search(n or "") for n in names):
        section["ok"] = True
        section["state"] = "up"
        section["reason"] = "mac worker present in snapshot workers[]"
        return section
    if _relay_log_recent_peer(path=relay_log):
        section["ok"] = True
        section["state"] = "up"
        section["reason"] = "recent relay peer 10.90.90.2 within 5m"
        return section
    if (hub_state or "").lower() == "up" and not names:
        section["state"] = "down"
        section["reason"] = "hub up, no workers, no recent relay peer"
        return section
    section["state"] = "unknown"
    section["reason"] = "insufficient signal"
    return section


def check_tunnel_relay(use_cache: bool = True) -> dict[str, Any]:
    """Cached, single-flight wrapper around _check_tunnel_relay_uncached."""
    return cached_single_flight(
        "tunnel_relay", lambda: _check_tunnel_relay_uncached(), use_cache=use_cache)


def _check_tunnel_relay_uncached() -> dict[str, Any]:
    section: dict[str, Any] = {
        "ok": False,
        "state": "unknown",
        "process": False,
        "listening": False,
        "last_log_line": None,
        "error": None,
    }
    if os.name != "nt":
        section["error"] = "tunnel_relay check is Windows-only"
        return section

    # Process command line
    code, out, err = _run_ps(
        "$procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.CommandLine -and "
        "($_.CommandLine -like '*tunnel_relay.py*--bind-ip*10.90.90.1*' "
        "-or $_.CommandLine -like '*tunnel_relay.py* 10.90.90.1*') }; "
        "if ($procs) { 'YES' } else { 'NO' }"
    )
    if code == 0 and "YES" in out:
        section["process"] = True
    elif code != 0 and err:
        section["error"] = err.strip()[:200]

    code2, out2, _err2 = _run_ps(
        "$c = Get-NetTCPConnection -LocalAddress 10.90.90.1 -LocalPort 6379 "
        "-State Listen -ErrorAction SilentlyContinue; "
        "if ($c) { 'YES' } else { 'NO' }"
    )
    if code2 == 0 and "YES" in out2:
        section["listening"] = True

    try:
        lines = RELAY_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        if lines:
            section["last_log_line"] = lines[-1].strip()[:240]
    except OSError:
        pass

    if section["process"] or section["listening"]:
        section["ok"] = True
        section["state"] = "up"
    else:
        section["state"] = "down"
    return section


def check_redis_secondary(use_cache: bool = True) -> dict[str, Any]:
    """Cached, single-flight wrapper around _check_redis_secondary_uncached."""
    return cached_single_flight(
        "redis_docker", lambda: _check_redis_secondary_uncached(), use_cache=use_cache)


def _check_redis_secondary_uncached() -> dict[str, Any]:
    """Optional docker ps secondary display (not a ping)."""
    section: dict[str, Any] = {
        "ok": False,
        "state": "unknown",
        "container": None,
        "status": None,
        "error": None,
    }
    try:
        proc = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "name=local-agent-phase1-redis",
                "--format",
                "{{.Names}}\t{{.Status}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except FileNotFoundError:
        section["error"] = "docker not available"
        return section
    except Exception as exc:
        section["error"] = f"{type(exc).__name__}: {exc}"
        return section
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        section["state"] = "down"
        section["error"] = "container not listed"
        return section
    parts = line[0].split("\t", 1)
    section["container"] = parts[0]
    section["status"] = parts[1] if len(parts) > 1 else ""
    section["ok"] = True
    section["state"] = "up"
    return section


def build_dashboard_payload() -> dict[str, Any]:
    """Combined /api/dashboard body. Each section isolated on failure."""
    snapshot = read_farm_status()
    events = read_outage_events()
    registered = run_farm_health_json()
    hub = check_wireguard_hub()
    relay = check_tunnel_relay()
    spoke = infer_wireguard_spoke(
        workers=snapshot.get("workers") or registered.get("workers"),
        hub_state=hub.get("state"),
    )
    redis_docker = check_redis_secondary()

    workers = list(snapshot.get("workers") or [])
    broker = snapshot.get("broker_reachable")
    redis_section = {
        "ok": bool(broker) and not snapshot.get("stale"),
        "state": (
            "unknown"
            if snapshot.get("stale") or broker is None
            else ("up" if broker else "down")
        ),
        "broker_reachable": broker,
        "source": "farm_status.json",
        "docker": redis_docker,
        "error": snapshot.get("error") if snapshot.get("stale") else None,
    }

    celery_section = {
        "ok": bool(workers) and not snapshot.get("stale"),
        "state": (
            "unknown"
            if snapshot.get("stale")
            else (
                "up"
                if workers
                else (
                    "down"
                    if snapshot.get("status") in {"no_workers", "unreachable", "ok"}
                    else "unknown"
                )
            )
        ),
        "workers": workers,
        "workers_responding": snapshot.get("workers_responding"),
        "status": snapshot.get("status"),
        "error": snapshot.get("snapshot_error") or snapshot.get("error"),
    }
    if not workers and snapshot.get("status") == "no_workers":
        celery_section["state"] = "down"
        celery_section["ok"] = False

    # Short task names for UI chips
    def _short(name: str) -> str:
        return name.rsplit(".", 1)[-1] if name else name

    present = list(registered.get("registered_tasks") or [])
    expected = list(registered.get("expected_tasks") or EXPECTED_REGISTERED_TASKS)
    missing = list(registered.get("missing_expected_tasks") or [])
    tasks_section = {
        "ok": bool(registered.get("ok")),
        "state": (
            "error"
            if not registered.get("ok")
            else registered.get("status") or "unknown"
        ),
        "expected": expected,
        "expected_short": [_short(t) for t in expected],
        "present": present,
        "present_short": [_short(t) for t in present],
        "missing": missing,
        "missing_short": [_short(t) for t in missing],
        "tasks_by_worker": registered.get("tasks_by_worker") or {},
        "registered_check": registered.get("registered_check"),
        "error": registered.get("error") if not registered.get("ok") else (
            (registered.get("registered_check") or {}).get("error")
        ),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall_from_snapshot(snapshot),
        "snapshot": snapshot,
        "wireguard_hub": hub,
        "wireguard_spoke": spoke,
        "tunnel_relay": relay,
        "redis": redis_section,
        "celery_workers": celery_section,
        "registered_tasks": tasks_section,
        "outage_events": events,
    }