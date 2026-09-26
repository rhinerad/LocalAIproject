"""SQLite edge ledger. Metadata + one untrusted result blob. Not a farm DB."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .constants import (
    ALLOWED_JOB_KINDS,
    CLAIM_RATE_MAX,
    CLAIM_RATE_WINDOW_SECONDS,
    COMPLETE_STATUSES,
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_TOKENS,
    JOB_RETENTION_DAYS,
    MAX_ACTIVE_JOBS,
    MAX_BODY_BYTES,
    MAX_DEVICE_ID_CHARS,
    MAX_JOB_ID_CHARS,
    MAX_PROMPT_CHARS,
    MAX_RESULT_CHARS,
    MAX_TOKENS,
    MIN_TOKEN_CHARS,
    STATE_COMPLETED,
    STATE_EXPIRED,
    STATE_LEASED,
    STATE_QUEUED,
    STATE_REFUSED,
    prompt_fits_context,
)

_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,%d}$" % MAX_DEVICE_ID_CHARS)


class EdgeLedgerError(ValueError):
    """Operator or protocol error; safe to return to admin/phone as reason."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class EdgeLedger:
    def __init__(self, data_dir: str | Path):
        self.root = Path(data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "edge_ledger.sqlite3"
        with self._connection() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    cert_fingerprint TEXT NOT NULL,
                    capabilities TEXT NOT NULL,
                    revoked_at TEXT,
                    created_at TEXT NOT NULL,
                    claim_window_start TEXT,
                    claim_count INTEGER NOT NULL DEFAULT 0
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    prompt_chars INTEGER NOT NULL,
                    max_tokens INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    lease_device TEXT,
                    lease_until TEXT,
                    status TEXT,
                    untrusted_result TEXT,
                    result_chars INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
            if "attempt" not in columns:
                conn.execute(
                    "ALTER TABLE jobs ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0"
                )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS jobs_state_created ON jobs(state, created_at)"
            )
            conn.execute(
                """CREATE INDEX IF NOT EXISTS jobs_lease_device_state
                   ON jobs(lease_device, state)"""
            )

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
        finally:
            conn.close()

    def _device_row(self, conn, device_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM devices WHERE device_id = ?", (device_id,)
        ).fetchone()

    def device_exists(self, device_id: str) -> bool:
        with self._connection() as conn:
            return self._device_row(conn, device_id) is not None

    def create_device(self, device_id: str, cert_fingerprint: str) -> str:
        device_id = device_id or ""
        if device_id in {".", ".."} or not _DEVICE_ID_RE.fullmatch(device_id):
            raise EdgeLedgerError("device_id is invalid")
        if not cert_fingerprint or len(cert_fingerprint) != 64:
            raise EdgeLedgerError("client certificate fingerprint is required")
        token = secrets.token_urlsafe(32)
        if len(token) < MIN_TOKEN_CHARS:
            raise EdgeLedgerError("generated token is implausibly short")
        now = _iso(_utc_now())
        caps = json.dumps(["edge_text_inference"])
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = self._device_row(conn, device_id)
            if existing is not None:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("device_id already exists")
            conn.execute(
                """INSERT INTO devices (
                    device_id, token_hash, cert_fingerprint, capabilities,
                    revoked_at, created_at, claim_window_start, claim_count
                ) VALUES (?, ?, ?, ?, NULL, ?, NULL, 0)""",
                (device_id, hash_token(token), cert_fingerprint, caps, now),
            )
            conn.execute("COMMIT")
        return token

    def lookup_auth(self, token: str, cert_fingerprint: str) -> dict:
        if not isinstance(token, str) or len(token) < MIN_TOKEN_CHARS:
            raise EdgeLedgerError("unauthorized")
        if not cert_fingerprint:
            raise EdgeLedgerError("unauthorized")
        digest = hash_token(token)
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM devices WHERE token_hash = ?", (digest,)
            ).fetchone()
        if row is None:
            raise EdgeLedgerError("unauthorized")
        if row["revoked_at"]:
            raise EdgeLedgerError("unauthorized")
        if row["cert_fingerprint"] != cert_fingerprint:
            raise EdgeLedgerError("unauthorized")
        return dict(row)

    def revoke_device(self, device_id: str) -> dict:
        now = _utc_now()
        now_s = _iso(now)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._device_row(conn, device_id)
            if row is None:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("device_id is unknown")
            conn.execute(
                "UPDATE devices SET revoked_at = ? WHERE device_id = ?",
                (now_s, device_id),
            )
            leased = conn.execute(
                "SELECT * FROM jobs WHERE lease_device = ? AND state = ?",
                (device_id, STATE_LEASED),
            ).fetchall()
            for job in leased:
                conn.execute(
                    """UPDATE jobs SET state = ?, status = ?, lease_device = NULL,
                       lease_until = NULL, updated_at = ? WHERE job_id = ?""",
                    (STATE_EXPIRED, "expired", now_s, job["job_id"]),
                )
            conn.execute("COMMIT")
            return {
                "device_id": device_id,
                "revoked_at": now_s,
                "expired_leases": len(leased),
            }

    def inject_job(self, prompt: str, max_tokens: int | None = None) -> dict:
        if not isinstance(prompt, str) or not prompt.strip():
            raise EdgeLedgerError("prompt is empty")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise EdgeLedgerError("prompt exceeds the edge limit")
        tokens = DEFAULT_MAX_TOKENS if max_tokens is None else max_tokens
        if not isinstance(tokens, int) or not 1 <= tokens <= MAX_TOKENS:
            raise EdgeLedgerError("job token budget is outside the edge limit")
        if not prompt_fits_context(prompt, tokens):
            raise EdgeLedgerError("prompt does not fit the runtime context")
        encoded = len(json.dumps(
            {"prompt": prompt, "max_tokens": tokens},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8"))
        if encoded > MAX_BODY_BYTES:
            raise EdgeLedgerError("prompt exceeds the edge limit")
        job_id = secrets.token_urlsafe(16)
        if len(job_id) > MAX_JOB_ID_CHARS:
            job_id = job_id[:MAX_JOB_ID_CHARS]
        now = _utc_now()
        now_s = _iso(now)
        cutoff = _iso(now - timedelta(days=JOB_RETENTION_DAYS))
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            active = conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE state IN (?, ?)",
                (STATE_QUEUED, STATE_LEASED),
            ).fetchone()[0]
            if int(active) >= MAX_ACTIVE_JOBS:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("queue is full")
            conn.execute(
                """DELETE FROM jobs
                   WHERE state IN (?, ?, ?) AND updated_at < ?""",
                (STATE_COMPLETED, STATE_REFUSED, STATE_EXPIRED, cutoff),
            )
            conn.execute(
                """INSERT INTO jobs (
                    job_id, kind, prompt, prompt_chars, max_tokens, state,
                    created_at, updated_at, attempt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    job_id, "edge_text_inference", prompt, len(prompt),
                    tokens, STATE_QUEUED, now_s, now_s,
                ),
            )
            conn.execute("COMMIT")
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        if row is None:
            raise EdgeLedgerError("job is unknown")
        return dict(row)

    def _expire_overdue(self, conn, now_s: str) -> None:
        conn.execute(
            """UPDATE jobs
               SET state = ?, status = ?, lease_device = NULL,
                   lease_until = NULL, updated_at = ?
               WHERE state = ? AND lease_until IS NOT NULL AND lease_until < ?""",
            (STATE_EXPIRED, "expired", now_s, STATE_LEASED, now_s),
        )

    def _job_public(self, row) -> dict:
        return {
            "id": row["job_id"],
            "kind": row["kind"],
            "prompt": row["prompt"],
            "max_tokens": int(row["max_tokens"]),
            "attempt": int(row["attempt"] or 0),
        }

    def claim(self, device: dict, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> dict | None:
        device_id = device["device_id"]
        caps = json.loads(device["capabilities"])
        if "edge_text_inference" not in caps:
            raise EdgeLedgerError("device is not granted edge_text_inference")
        lease_seconds = max(15, min(int(lease_seconds), 900))
        now = _utc_now()
        now_s = _iso(now)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            fresh = self._device_row(conn, device_id)
            if fresh is None or fresh["revoked_at"]:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("unauthorized")
            window = parse_iso(fresh["claim_window_start"])
            count = int(fresh["claim_count"] or 0)
            if window is None or (now - window).total_seconds() >= CLAIM_RATE_WINDOW_SECONDS:
                window = now
                count = 0
            if count >= CLAIM_RATE_MAX:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("rate limited")
            conn.execute(
                """UPDATE devices SET claim_window_start = ?, claim_count = ?
                   WHERE device_id = ?""",
                (_iso(window), count + 1, device_id),
            )
            # Every claim recovers every overdue lease, not only this device's.
            self._expire_overdue(conn, now_s)
            current = conn.execute(
                """SELECT * FROM jobs WHERE lease_device = ? AND state = ?""",
                (device_id, STATE_LEASED),
            ).fetchone()
            if current is not None:
                # A live lease stays with the worker that already holds it.
                # Returning it again lets a second process run the same prompt.
                conn.execute("COMMIT")
                return None
            queued = conn.execute(
                """SELECT * FROM jobs WHERE state = ? AND kind = ?
                   ORDER BY created_at ASC LIMIT 1""",
                (STATE_QUEUED, "edge_text_inference"),
            ).fetchone()
            if queued is None:
                conn.execute("COMMIT")
                return None
            if queued["kind"] not in ALLOWED_JOB_KINDS:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("job kind is not approved for the phone")
            until_s = _iso(now + timedelta(seconds=lease_seconds))
            attempt = int(queued["attempt"] or 0) + 1
            conn.execute(
                """UPDATE jobs SET state = ?, lease_device = ?, lease_until = ?,
                   updated_at = ?, attempt = ? WHERE job_id = ?""",
                (STATE_LEASED, device_id, until_s, now_s, attempt, queued["job_id"]),
            )
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (queued["job_id"],)
            ).fetchone()
            conn.execute("COMMIT")
            return self._job_public(row)

    def complete(
        self, device: dict, job_id: str, status: str, result: str, attempt: int,
    ) -> tuple[dict, str]:
        """Return (public_outcome, code) where code is ok / replay / conflict."""
        if not isinstance(job_id, str) or not job_id or len(job_id) > MAX_JOB_ID_CHARS:
            raise EdgeLedgerError("job id is invalid")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise EdgeLedgerError("attempt is invalid")
        if status not in COMPLETE_STATUSES:
            status = "refused"
        if not isinstance(result, str):
            result = ""
        truncated = result[-MAX_RESULT_CHARS:]
        encoded = len(json.dumps(
            {"id": job_id, "status": status, "result": truncated, "attempt": attempt},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8"))
        if encoded > MAX_BODY_BYTES:
            raise EdgeLedgerError("result exceeds the edge limit")
        device_id = device["device_id"]
        now = _utc_now()
        now_s = _iso(now)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            fresh = self._device_row(conn, device_id)
            if fresh is None or fresh["revoked_at"]:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("unauthorized")
            self._expire_overdue(conn, now_s)
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None or row["lease_device"] != device_id:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("forbidden")
            if int(row["attempt"] or 0) != attempt:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("forbidden")
            if row["state"] in {STATE_COMPLETED, STATE_REFUSED}:
                stored = row["untrusted_result"] or ""
                stored_status = row["status"] or ""
                if stored == truncated and stored_status == status:
                    conn.execute("COMMIT")
                    return (
                        {"id": job_id, "status": stored_status, "result": stored},
                        "replay",
                    )
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("replay conflict")
            if row["state"] != STATE_LEASED:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("forbidden")
            until = parse_iso(row["lease_until"])
            if until is None or until < now:
                conn.execute("ROLLBACK")
                raise EdgeLedgerError("forbidden")
            terminal = STATE_COMPLETED if status == "completed" else STATE_REFUSED
            if status in {"timed_out", "runtime_failed"}:
                terminal = STATE_REFUSED
            conn.execute(
                """UPDATE jobs SET state = ?, status = ?, untrusted_result = ?,
                   result_chars = ?, lease_until = NULL, updated_at = ?
                   WHERE job_id = ?""",
                (terminal, status, truncated, len(truncated), now_s, job_id),
            )
            conn.execute("COMMIT")
            return (
                {"id": job_id, "status": status, "result": truncated},
                "ok",
            )

    def admin_job_view(self, job_id: str) -> dict:
        now_s = _iso(_utc_now())
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._expire_overdue(conn, now_s)
            conn.execute("COMMIT")
        row = self.get_job(job_id)
        return {
            "id": row["job_id"],
            "kind": row["kind"],
            "state": row["state"],
            "status": row["status"],
            "prompt_chars": row["prompt_chars"],
            "max_tokens": row["max_tokens"],
            "lease_device": row["lease_device"],
            "untrusted": True,
            "untrusted_result": row["untrusted_result"] or "",
            "result_chars": row["result_chars"] or 0,
        }
