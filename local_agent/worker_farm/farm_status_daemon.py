"""Periodic farm-health snapshot writer.

CLI, from the repository root, farm venv only:

  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m local_agent.worker_farm.farm_status_daemon

(`python -m worker_farm.farm_status_daemon` also works if cwd is local_agent/.)

Writes worker_farm/farm_status.json via an atomic temp-file + rename so a
reader never sees a half-written object. Calls check_farm_health() on each
tick; a failed check is recorded in the snapshot and the loop continues.

After N consecutive failed checks (status != "ok"), prints a greppable
FARM_STATUS_OUTAGE line. N defaults to 3 (--fail-alert-after, or
FARM_STATUS_FAIL_ALERT_AFTER). The line is emitted when the count first
reaches N, then every N failures thereafter. The consecutive counter
resets on a healthy check; FARM_STATUS_RECOVERED is printed if an outage
had already been declared.

Not wired into agent.py or farm_offload.py.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ._farm_submit_wait import _load_env_file
from .farm_health import check_farm_health, format_status_line, with_checked_at

HERE = Path(__file__).resolve().parent
DEFAULT_STATUS_PATH = HERE / "farm_status.json"
DEFAULT_INTERVAL_S = 30.0
INTERVAL_ENV = "FARM_STATUS_INTERVAL_S"
PATH_ENV = "FARM_STATUS_PATH"
DEFAULT_FAIL_ALERT_AFTER = 3
FAIL_ALERT_AFTER_ENV = "FARM_STATUS_FAIL_ALERT_AFTER"
OUTAGE_TOKEN = "FARM_STATUS_OUTAGE"
RECOVERED_TOKEN = "FARM_STATUS_RECOVERED"

SNAPSHOT_FIELDS = (
    "checked_at",
    "broker_reachable",
    "workers_responding",
    "latency_ms",
    "workers",
    "status",
    "error",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def snapshot_from_health(result: dict, checked_at: str | None = None) -> dict:
    """Stable farm_status.json object. Always includes SNAPSHOT_FIELDS."""
    stamped = with_checked_at(result, checked_at=checked_at)
    return {
        "checked_at": stamped["checked_at"],
        "broker_reachable": bool(stamped.get("broker_reachable")),
        "workers_responding": bool(stamped.get("workers_responding")),
        "latency_ms": stamped.get("latency_ms"),
        "workers": list(stamped.get("workers") or []),
        "status": stamped.get("status"),
        "error": stamped.get("error"),
    }


def atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON by temp file + os.replace so readers never see a partial dest."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def write_status_snapshot(
    path: Path | None = None,
    timeout_s: float = 5.0,
    health_fn: Callable | None = None,
) -> dict:
    """Run one health check, atomically write the snapshot, return it.

    Never raises: a blown health_fn becomes status=unreachable in the file.
    """
    dest = Path(path) if path is not None else DEFAULT_STATUS_PATH
    fn = health_fn or check_farm_health
    try:
        result = fn(timeout_s=timeout_s)
        if not isinstance(result, dict):
            raise TypeError(f"health check returned {type(result).__name__}")
    except Exception as exc:
        result = {
            "broker_reachable": False,
            "workers_responding": False,
            "latency_ms": None,
            "workers": [],
            "status": "unreachable",
            "error": f"{type(exc).__name__}: {exc}",
        }
    snap = snapshot_from_health(result)
    atomic_write_json(dest, snap)
    return snap


def interval_s(cli_value: float | None = None) -> float:
    if cli_value is not None:
        return float(cli_value)
    raw = (os.environ.get(INTERVAL_ENV) or "").strip()
    if raw:
        return float(raw)
    return DEFAULT_INTERVAL_S


def status_path(cli_value: str | None = None) -> Path:
    if cli_value:
        return Path(cli_value)
    raw = (os.environ.get(PATH_ENV) or "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_STATUS_PATH


def fail_alert_after(cli_value: int | None = None) -> int:
    """Consecutive failed checks before FARM_STATUS_OUTAGE. CLI, else env, else 3."""
    if cli_value is not None:
        n = int(cli_value)
    else:
        raw = (os.environ.get(FAIL_ALERT_AFTER_ENV) or "").strip()
        n = int(raw) if raw else DEFAULT_FAIL_ALERT_AFTER
    return max(n, 1)


def format_outage_line(consecutive: int, status: str, error: str | None) -> str:
    reason = error if error else "(none)"
    return (
        f"{OUTAGE_TOKEN} consecutive_failures={consecutive} "
        f"status={status} error={reason}"
    )


def format_recovered_line(previous_consecutive: int, status: str) -> str:
    return (
        f"{RECOVERED_TOKEN} after_consecutive_failures={previous_consecutive} "
        f"status={status}"
    )


class ConsecutiveFailureAlert:
    """Tracks consecutive non-ok health checks and emits greppable alert lines.

    A failed check is whatever check_farm_health already treats as not
    healthy: any snapshot whose status is not "ok" (unreachable,
    no_workers, unconfigured, ...). Do not invent a second health definition.

    Alert policy: emit FARM_STATUS_OUTAGE when consecutive failures first
    reach N, then again every N failures thereafter (heartbeat). Emit
    FARM_STATUS_RECOVERED on the first healthy check after an outage was
    declared. The consecutive counter resets on status=="ok".
    """

    def __init__(self, n: int = DEFAULT_FAIL_ALERT_AFTER):
        self.n = max(int(n), 1)
        self.consecutive = 0
        self.outage_declared = False

    def observe(self, status: str | None, error: str | None = None) -> str | None:
        healthy = status == "ok"
        if healthy:
            extra = None
            if self.outage_declared:
                extra = format_recovered_line(self.consecutive, status or "ok")
            self.consecutive = 0
            self.outage_declared = False
            return extra
        self.consecutive += 1
        if self.consecutive >= self.n and self.consecutive % self.n == 0:
            self.outage_declared = True
            return format_outage_line(
                self.consecutive, status or "unreachable", error)
        return None


def run_loop(
    *,
    interval: float = DEFAULT_INTERVAL_S,
    timeout_s: float = 5.0,
    path: Path | None = None,
    once: bool = False,
    max_ticks: int | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    health_fn: Callable | None = None,
    fail_alert_after_n: int = DEFAULT_FAIL_ALERT_AFTER,
) -> int:
    """Loop until killed, --once, or max_ticks. Always continues after a failed check."""
    dest = Path(path) if path is not None else DEFAULT_STATUS_PATH
    tick = 0
    last_status = "unreachable"
    alerter = ConsecutiveFailureAlert(fail_alert_after_n)
    while True:
        tick += 1
        snap = write_status_snapshot(path=dest, timeout_s=timeout_s, health_fn=health_fn)
        last_status = snap.get("status") or "unreachable"
        print(
            f"{format_status_line(snap)}  checked_at: {snap['checked_at']}",
            flush=True,
        )
        extra = alerter.observe(last_status, snap.get("error"))
        if extra:
            print(extra, flush=True)
        if once or (max_ticks is not None and tick >= max_ticks):
            break
        sleep_fn(interval)
    return 0 if last_status == "ok" else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write farm_status.json on an interval. Does not submit farm jobs.")
    parser.add_argument("--interval", type=float, default=None,
                        help=f"seconds between checks (default {DEFAULT_INTERVAL_S}, "
                             f"or ${INTERVAL_ENV})")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="seconds for each check_farm_health call (default 5)")
    parser.add_argument("--path", default=None,
                        help=f"snapshot path (default worker_farm/farm_status.json, "
                             f"or ${PATH_ENV})")
    parser.add_argument("--once", action="store_true",
                        help="write one snapshot and exit")
    parser.add_argument("--fail-alert-after", type=int, default=None,
                        help=f"consecutive failed checks before {OUTAGE_TOKEN} "
                             f"(default {DEFAULT_FAIL_ALERT_AFTER}, "
                             f"or ${FAIL_ALERT_AFTER_ENV})")
    args = parser.parse_args()
    _load_env_file()
    return run_loop(
        interval=interval_s(args.interval),
        timeout_s=args.timeout,
        path=status_path(args.path),
        once=args.once,
        fail_alert_after_n=fail_alert_after(args.fail_alert_after),
    )


if __name__ == "__main__":
    raise SystemExit(main())
