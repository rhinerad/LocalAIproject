"""Read-only job ledger status; never prints raw artifacts or secrets."""
from __future__ import annotations

import argparse
import json

from .job_registry import JobRegistry


def _public(record: dict) -> dict:
    return {
        key: record.get(key)
        for key in ("job_id", "workflow", "state", "result_artifact_id", "failure_code", "created_at", "updated_at")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Show Phase 1 metadata-only job status")
    parser.add_argument("--job", help="specific job ID")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    registry = JobRegistry()
    if args.job:
        record = registry.get(args.job)
        print(json.dumps(_public(record) if record else {"job_id": args.job, "found": False}, indent=2))
    else:
        print(json.dumps([_public(record) for record in registry.recent(args.limit)], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
