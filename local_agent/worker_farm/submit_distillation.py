"""Stage a review-only distillation job; --sample avoids private operator data."""
from __future__ import annotations

import argparse
import base64
import os
import tempfile
from pathlib import Path

from .celery_app import app
from .farm_core import FarmPolicyError, distillation_source_fingerprint, stage_distillation_source
from .job_registry import JobRegistry

SAMPLE = """Preference: keep the GPU available for interactive work.\nHardware: the workstation has an RTX GPU and CPU fallback.\ndef example(): return 'review this candidate before promotion'\n"""


def _envelope_from_record(record: dict) -> dict:
    """Rebuild only the allow-listed task envelope from metadata."""
    return {
        "job_id": record["job_id"],
        "workflow": record["workflow"],
        "artifact_id": record["artifact_id"],
        "privacy_class": "private",
        "idempotency_key": record["idempotency_key"],
    }


def _queue_envelope(registry: JobRegistry, envelope: dict) -> dict:
    registry.mark_queued(envelope["job_id"])
    try:
        async_result = app.send_task(
            "local_agent.worker_farm.tasks.distill_export", args=[envelope], queue="distill"
        )
    except Exception as exc:
        registry.unqueue(envelope["job_id"], type(exc).__name__)
        raise FarmPolicyError(
            "broker submission failed; job was returned to staged and can be retried"
        ) from exc
    return {"job_id": envelope["job_id"], "task_id": async_result.id,
            "status": "queued", "deduplicated": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", help="JSON, HTML, or text export to stage")
    parser.add_argument("--sample", action="store_true", help="use a benign synthetic fixture")
    args = parser.parse_args()
    if bool(args.source) == bool(args.sample):
        raise SystemExit("Provide exactly one source path or --sample")
    if app is None:
        raise SystemExit("Broker configuration/Celery is unavailable; run doctor first.")
    if args.sample:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as handle:
            handle.write(SAMPLE)
            source = Path(handle.name)
    else:
        source = Path(args.source)
    try:
        registry = JobRegistry()
        existing = registry.by_idempotency_key(distillation_source_fingerprint(source))
        if existing is not None and existing["state"] != "staged":
            print({"job_id": existing["job_id"], "status": existing["state"], "deduplicated": True})
            return 0
        if existing is not None:
            print(_queue_envelope(registry, _envelope_from_record(existing)))
            return 0
        envelope = stage_distillation_source(source)
        is_new, record = registry.register(envelope)
        if not is_new:
            if record["state"] != "staged":
                print({"job_id": record["job_id"], "status": record["state"], "deduplicated": True})
                return 0
            envelope = _envelope_from_record(record)
        print(_queue_envelope(registry, envelope))
    except FarmPolicyError as exc:
        raise SystemExit(f"Refused: {exc}") from exc
    finally:
        if args.sample:
            source.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
