"""Cross-platform worker launcher with deliberately conservative defaults."""
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queues", default=os.environ.get("FARM_QUEUES", "distill"))
    parser.add_argument("--concurrency", type=int, default=int(os.environ.get("FARM_CONCURRENCY", "1")))
    args = parser.parse_args()
    system = platform.system().lower()
    pool = "solo" if system in {"windows", "android"} else "prefork"
    command = [sys.executable, "-m", "celery", "-A", "local_agent.worker_farm.celery_app:app",
               "worker", "--loglevel=INFO", "--queues", args.queues,
               "--concurrency", str(max(1, args.concurrency)), "--pool", pool]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
