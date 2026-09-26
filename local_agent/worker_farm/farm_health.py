r"""Standalone worker-farm health/diagnostics.

CLI, from the repository root, farm venv only:

  local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_health

(`python -m worker_farm.farm_health` also works if cwd is local_agent/.)

Public API:
  check_farm_health(timeout_s=5.0) -> dict
  check_registered_tasks(timeout_s=5.0) -> dict

This module never submits summarize/embed/judge/distill jobs. It TCP-checks
the broker from FARM_BROKER_URL, then uses Celery inspect.ping() to see
whether any worker process answers, and inspect.registered() to see which
task functions that worker actually has loaded. Connectivity and task
registration are reported separately: a worker can answer ping while
summarize/embed are missing from registered(). Failures become status
"unreachable" or "no_workers"; the function never raises and never hangs
past timeout_s.

The live CLI is a diagnostic (Celery inspect takes 1–5s). The agent hot
path does not call this module; farm_offload.farm_reachable() reads
farm_status.json, which farm_status_daemon writes from check_farm_health.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from ._farm_submit_wait import _load_env_file


# Task names the live Mac worker is expected to have loaded (queues:
# probe, judge, summarize, embed). Distinct from ping() connectivity.
EXPECTED_REGISTERED_TASKS = (
    "local_agent.worker_farm.tasks.connectivity_probe",
    "local_agent.worker_farm.tasks.judge_transcript",
    "local_agent.worker_farm.tasks.summarize_conversation",
    "local_agent.worker_farm.tasks.embed_chunks",
)


def _redact(text: str) -> str:
    """Strip redis passwords out of exception text before returning it."""
    return re.sub(r"(redis://:)[^@/]+@", r"\1***@", text, flags=re.IGNORECASE)


def _broker_tcp_check(broker_url: str, timeout_s: float) -> None:
    parsed = urlsplit(broker_url)
    host = parsed.hostname
    port = parsed.port or 6379
    if not host:
        raise OSError("FARM_BROKER_URL has no hostname")
    sock = socket.create_connection((host, port), timeout=timeout_s)
    sock.close()


def _inspect_timeout(timeout_s: float) -> float:
    # inspect() waits the full timeout even after the first worker replies,
    # so cap it; TCP still uses the caller's timeout_s.
    return min(max(timeout_s, 0.1), 1.0)


def _celery_inspect(timeout_s: float):
    from .celery_app import create_app
    app = create_app()
    return app.control.inspect(timeout=_inspect_timeout(timeout_s))


def _inspect_ping(timeout_s: float):
    """Celery control ping. Returns {worker_name: {'ok': 'pong'}, ...} or None."""
    return _celery_inspect(timeout_s).ping()


def _inspect_registered(timeout_s: float):
    """Celery control registered(). Returns {worker_name: [task, ...]} or None."""
    return _celery_inspect(timeout_s).registered()


def _normalize_task_names(names) -> list[str]:
    """Drop Celery signature suffixes (name[...]) and empty entries."""
    out: list[str] = []
    for raw in names or []:
        name = str(raw).split("[", 1)[0].strip()
        if name:
            out.append(name)
    return out


def _apply_registered(out: dict, registered) -> None:
    """Fill registered_tasks / tasks_by_worker / missing_expected_tasks."""
    tasks_by_worker: dict[str, list[str]] = {}
    union: set[str] = set()
    if registered:
        for worker, names in registered.items():
            normalized = sorted(set(_normalize_task_names(names)))
            tasks_by_worker[str(worker)] = normalized
            union.update(normalized)
    out["tasks_by_worker"] = dict(sorted(tasks_by_worker.items()))
    out["registered_tasks"] = sorted(union)
    out["missing_expected_tasks"] = [
        task for task in EXPECTED_REGISTERED_TASKS if task not in union
    ]


def _empty_registered_fields() -> dict:
    return {
        "registered_tasks": [],
        "tasks_by_worker": {},
        "missing_expected_tasks": list(EXPECTED_REGISTERED_TASKS),
    }


def check_farm_health(timeout_s: float = 5.0) -> dict:
    """Return a farm health snapshot. Never raises.

    Keys:
      broker_reachable (bool)
      workers_responding (bool)
      latency_ms (float | None)  — elapsed for the checks that ran
      workers (list[str])
      registered_tasks (list[str])  — union of inspect.registered() names
      tasks_by_worker (dict[str, list[str]])
      missing_expected_tasks (list[str])
      status (str)  — ok | unreachable | no_workers | unconfigured
      error (str | None)

    status reflects connectivity only (broker + ping). Missing task
    functions do not change status from "ok"; see check_registered_tasks
    and missing_expected_tasks for registration.
    """
    started = time.perf_counter()
    out = {
        "broker_reachable": False,
        "workers_responding": False,
        "latency_ms": None,
        "workers": [],
        "status": "unreachable",
        "error": None,
    }
    out.update(_empty_registered_fields())

    def _finish(status: str, error: str | None = None) -> dict:
        out["status"] = status
        out["error"] = _redact(error) if error else None
        out["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return out

    try:
        _load_env_file()
        broker = (os.environ.get("FARM_BROKER_URL") or "").strip()
        if not broker:
            return _finish("unconfigured", "FARM_BROKER_URL not set")
        try:
            _broker_tcp_check(broker, timeout_s)
        except (OSError, TimeoutError, socket.timeout) as exc:
            return _finish("unreachable", f"{type(exc).__name__}: {exc}")
        out["broker_reachable"] = True
        try:
            pinged = _inspect_ping(timeout_s)
        except Exception as exc:
            return _finish("no_workers", f"{type(exc).__name__}: {exc}")
        if pinged:
            out["workers_responding"] = True
            out["workers"] = sorted(pinged.keys())
            try:
                _apply_registered(out, _inspect_registered(timeout_s))
            except Exception:
                # Registration is informational; a failed inspect.registered()
                # must not flip connectivity status away from ok.
                _apply_registered(out, None)
            return _finish("ok")
        return _finish("no_workers", "broker reachable, no worker answered ping")
    except Exception as exc:
        return _finish("unreachable", f"{type(exc).__name__}: {exc}")


def registered_report_from_health(health: dict) -> dict:
    """Build a check_registered_tasks dict from an existing health snapshot."""
    conn_status = health.get("status") or "unreachable"
    raw_missing = health.get("missing_expected_tasks")
    if raw_missing is None:
        missing = list(EXPECTED_REGISTERED_TASKS)
    else:
        missing = list(raw_missing)
    if conn_status == "ok":
        status = "missing_tasks" if missing else "ok"
        error = (
            "workers reachable, missing registered tasks: " + ", ".join(missing)
            if missing else None
        )
    else:
        status = conn_status
        error = health.get("error")
    return {
        "workers": list(health.get("workers") or []),
        "registered_tasks": list(health.get("registered_tasks") or []),
        "tasks_by_worker": dict(health.get("tasks_by_worker") or {}),
        "expected_tasks": list(EXPECTED_REGISTERED_TASKS),
        "missing_expected_tasks": missing,
        "status": status,
        "error": error,
        "latency_ms": health.get("latency_ms"),
    }


def check_registered_tasks(timeout_s: float = 5.0) -> dict:
    """Return which task names workers currently have registered. Never raises.

    Uses Celery inspect.registered() (same inspect API as ping). Connectivity
    and registration are different: status is "ok" only when a worker answered
    and every EXPECTED_REGISTERED_TASKS name is present.

    Keys:
      workers (list[str])
      registered_tasks (list[str])
      tasks_by_worker (dict[str, list[str]])
      expected_tasks (list[str])
      missing_expected_tasks (list[str])
      status (str)  — ok | missing_tasks | no_workers | unreachable | unconfigured
      error (str | None)
      latency_ms (float | None)
    """
    return registered_report_from_health(check_farm_health(timeout_s=timeout_s))


def with_checked_at(result: dict, checked_at: str | None = None) -> dict:
    """Copy a check_farm_health dict and stamp checked_at (UTC ISO-8601)."""
    out = dict(result)
    out["checked_at"] = checked_at or datetime.now(timezone.utc).isoformat()
    return out


def format_status_line(result: dict) -> str:
    broker = "yes" if result.get("broker_reachable") else "no"
    workers = "yes" if result.get("workers_responding") else "no"
    line = (
        f"broker reachable: {broker}  "
        f"workers responding: {workers}  "
        f"latency_ms: {result.get('latency_ms')}"
    )
    names = result.get("workers") or []
    if names:
        line += f"  workers: {', '.join(names)}"
    if result.get("workers_responding"):
        registered = result.get("registered_tasks") or []
        line += f"  registered: {', '.join(registered) if registered else '(none)'}"
        missing = result.get("missing_expected_tasks") or []
        if missing:
            line += f"  missing_expected: {', '.join(missing)}"
    if result.get("error") and result.get("status") != "ok":
        line += f"  error: {result['error']}"
    return line


def format_registered_line(result: dict) -> str:
    """One-line registered-task report from check_registered_tasks()."""
    status = result.get("status")
    names = result.get("registered_tasks") or []
    missing = result.get("missing_expected_tasks") or []
    workers = result.get("workers") or []
    line = (
        f"registered-task status: {status}  "
        f"workers: {', '.join(workers) if workers else '(none)'}  "
        f"registered: {', '.join(names) if names else '(none)'}"
    )
    if missing:
        line += f"  missing_expected: {', '.join(missing)}"
    if result.get("error") and status not in {"ok"}:
        line += f"  error: {result['error']}"
    return line


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Worker-farm health check. Does not submit summarize/embed/judge/distill jobs.")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="seconds to wait for broker TCP and inspect ping (default 5)")
    parser.add_argument("--json", action="store_true",
                        help="print the check_farm_health dict plus checked_at as one JSON object")
    args = parser.parse_args()
    result = check_farm_health(timeout_s=args.timeout)
    registered = registered_report_from_health(result)
    if args.json:
        payload = with_checked_at(result)
        payload["registered_check"] = registered
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_status_line(result))
        print(format_registered_line(registered))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())