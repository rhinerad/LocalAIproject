"""Durable, metadata-only idempotency ledger for Phase 1 worker-farm jobs."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .farm_core import FarmPolicyError, _root

_STAGED = "staged"
_QUEUED = "queued"
_RUNNING = "running"
_COMPLETED = "completed"
_FAILED = "failed"
_ALLOWED_STATES = frozenset({_STAGED, _QUEUED, _RUNNING, _COMPLETED, _FAILED})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(envelope: dict) -> str:
    # job_id/artifact_id are intentionally excluded: staging the same export a
    # second time creates fresh opaque IDs, but its idempotency hash is stable.
    safe = {
        "workflow": envelope.get("workflow"),
        "privacy_class": envelope.get("privacy_class"),
        "idempotency_key": envelope.get("idempotency_key"),
    }
    return hashlib.sha256(json.dumps(safe, sort_keys=True).encode("utf-8")).hexdigest()


class JobRegistry:
    """SQLite stores IDs/hashes/states only; source and results stay encrypted."""

    def __init__(self, root: str | Path | None = None):
        root_path = _root(root)
        self.path = root_path / "runtime" / "worker_farm_jobs.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    workflow TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    envelope_fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL,
                    result_artifact_id TEXT,
                    failure_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            conn.close()

    def register(self, envelope: dict) -> tuple[bool, dict]:
        """Atomically register a staged job, returning ``(is_new, metadata)``."""
        required = ("job_id", "workflow", "artifact_id", "idempotency_key")
        if any(not envelope.get(key) for key in required):
            raise FarmPolicyError("job envelope lacks required metadata")
        if envelope["workflow"] != "historical_memory_distillation":
            raise FarmPolicyError("workflow is not enabled in Phase 1")
        fingerprint = _fingerprint(envelope)
        now = _utc_now()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?", (envelope["idempotency_key"],)
            ).fetchone()
            if existing is not None:
                record = self._record(existing)
                if record["envelope_fingerprint"] != fingerprint:
                    raise FarmPolicyError("idempotency key was reused with different job metadata")
                conn.execute("COMMIT")
                return False, record
            conn.execute(
                """INSERT INTO jobs (
                    job_id, idempotency_key, workflow, artifact_id, envelope_fingerprint,
                    state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (envelope["job_id"], envelope["idempotency_key"], envelope["workflow"],
                 envelope["artifact_id"], fingerprint, _STAGED, now, now),
            )
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (envelope["job_id"],)).fetchone()
            conn.execute("COMMIT")
            return True, self._record(row)

    def mark_queued(self, job_id: str) -> dict:
        return self._transition(job_id, {_STAGED}, _QUEUED)

    def unqueue(self, job_id: str, failure_code: str) -> dict:
        """Undo a failed broker submission without marking the job completed."""
        return self._transition(job_id, {_QUEUED}, _STAGED, failure_code=failure_code[:120])

    def by_idempotency_key(self, idempotency_key: str) -> dict | None:
        """Return metadata only; encrypted source text is never read here."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            return self._record(row) if row is not None else None

    def claim(self, job_id: str) -> tuple[bool, dict]:
        """Claim once. Duplicate deliveries return existing metadata without work."""
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise FarmPolicyError("job is not registered")
            record = self._record(row)
            if record["state"] != _QUEUED:
                conn.execute("COMMIT")
                return False, record
            now = _utc_now()
            conn.execute("UPDATE jobs SET state = ?, updated_at = ? WHERE job_id = ?", (_RUNNING, now, job_id))
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            conn.execute("COMMIT")
            return True, self._record(row)

    def complete(self, job_id: str, result_artifact_id: str) -> dict:
        if not result_artifact_id.startswith("result_distill_"):
            raise FarmPolicyError("invalid result artifact ID")
        return self._transition(job_id, {_RUNNING}, _COMPLETED, result_artifact_id=result_artifact_id)

    def fail(self, job_id: str, failure_code: str) -> dict:
        return self._transition(job_id, {_RUNNING}, _FAILED, failure_code=failure_code[:120])

    def requeue(self, job_id: str, failure_code: str) -> dict:
        """Return a transiently failed job to the broker-visible queued state.

        Celery redelivers a retry as a fresh task.  Leaving the registry in
        ``failed`` would cause that delivery to be silently deduplicated rather
        than retried.
        """
        return self._transition(job_id, {_RUNNING}, _QUEUED, failure_code=failure_code[:120])

    def get(self, job_id: str) -> dict | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            return self._record(row) if row is not None else None

    def recent(self, limit: int = 20) -> list[dict]:
        limit = max(1, min(int(limit), 100))
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._record(row) for row in rows]

    def _transition(self, job_id: str, expected: set[str], target: str, **fields) -> dict:
        if target not in _ALLOWED_STATES:
            raise FarmPolicyError("invalid target job state")
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise FarmPolicyError("job is not registered")
            record = self._record(row)
            if record["state"] not in expected:
                conn.execute("COMMIT")
                return record
            assignments = ["state = ?", "updated_at = ?"]
            values: list[str] = [target, _utc_now()]
            for key, value in fields.items():
                assignments.append(f"{key} = ?")
                values.append(value)
            values.append(job_id)
            conn.execute(f"UPDATE jobs SET {', '.join(assignments)} WHERE job_id = ?", values)
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            conn.execute("COMMIT")
            return self._record(row)

    @staticmethod
    def _record(row) -> dict:
        keys = ("job_id", "idempotency_key", "workflow", "artifact_id", "envelope_fingerprint", "state",
                "result_artifact_id", "failure_code", "created_at", "updated_at")
        return dict(zip(keys, row))
