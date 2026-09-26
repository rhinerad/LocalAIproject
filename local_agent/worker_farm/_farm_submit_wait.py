"""Farm-venv helper: submit one Celery task, wait for its result, print JSON.

Designed to be invoked as a subprocess by farm_offload.py (which runs in the
main local-agent Python environment that does not have celery[redis] installed).
This script runs under the farm venv (local_agent/worker_farm/.venv) which does.

Protocol:
  stdin:  one JSON line: {"task": str, "queue": str, "envelope": dict,
                          "timeout_s": float}
  stdout: one JSON line: the Celery task result dict on success, or
                         {"error": "..."} on any failure (exits 0 either way)
  exit 1: reserved for configuration/import failures that are always fatal

The caller (farm_offload._run_helper) treats any "error" key in the stdout JSON
as "farm unavailable" and falls back to the local CPU path. Timeout and
model-not-installed are both reported via stdout so the subprocess always exits
cleanly; they are not hard failures from the caller's perspective.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_env_file() -> None:
    """Parse KEY=VALUE lines from the sibling .env into os.environ.

    Only sets keys not already present in the environment, so a pre-set
    FARM_BROKER_URL (e.g. from a parent shell that already sourced .env) wins.
    URL-encoded values (passwords with %xx) are stored verbatim — Celery/Redis
    client handles the URL decoding itself.
    """
    env_file = HERE / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        task_name: str = request["task"]
        queue_name: str = request["queue"]
        envelope: dict = request["envelope"]
        timeout_s: float = float(request.get("timeout_s", 30.0))
    except Exception as exc:
        print(json.dumps({"error": f"bad input: {exc}"}))
        return 1

    _load_env_file()

    # Ensure the repo root is on sys.path so the package import below resolves.
    repo_root = str(HERE.parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    try:
        from local_agent.worker_farm.celery_app import app  # type: ignore[import]
    except Exception as exc:
        print(json.dumps({"error": f"celery_app import failed: {exc}"}))
        return 1

    if app is None:
        print(json.dumps({"error": "FARM_BROKER_URL not set or Celery unavailable"}))
        return 1

    try:
        async_result = app.send_task(task_name, args=[envelope], queue=queue_name)
    except Exception as exc:
        print(json.dumps({"error": f"send_task failed: {type(exc).__name__}: {exc}"}))
        return 1

    # propagate=False so a task-side exception is returned, not re-raised here.
    # Timeout IS still raised (celery.exceptions.TimeoutError).
    try:
        result = async_result.get(timeout=timeout_s, propagate=False)
    except Exception as exc:
        # TimeoutError or broker connection failure — report as error so the
        # caller falls back cleanly.
        print(json.dumps({"error": f"get failed: {type(exc).__name__}: {exc}"}))
        return 0  # exit 0: this is a fallback trigger, not a hard script failure

    # With propagate=False, a failed task returns an exception instance.
    if isinstance(result, Exception):
        print(json.dumps({"error": f"task raised {type(result).__name__}: {result}"}))
        return 0

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
