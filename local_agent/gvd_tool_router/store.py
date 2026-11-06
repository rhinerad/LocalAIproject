"""SQLite job DAG, attempts, prompt IDs, and leases. JSON progress is a projection."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .paths import GvdLayout

SCHEMA = """
-- Fix 2026-09-23 (readiness-audit finding "other risks", fix-set item #8):
-- production_store.py (the project's other, better-built SQLite store)
-- enables foreign_keys and synchronous=FULL; this store previously enabled
-- neither. Without foreign_keys=ON, the FOREIGN KEY declarations below on
-- shots.job_id and attempts.shot_id were silently unenforced (SQLite's
-- default), so an orphaned shot/attempt row was not actually prevented by
-- schema, only by call-site discipline. Without synchronous=FULL, WAL mode
-- defaults to synchronous=NORMAL, which can lose the most recent commit(s)
-- across an OS crash or power loss -- acceptable for a cache, not for the
-- record of what was actually submitted to ComfyUI. A full swap to
-- production_store.py's schema was considered and rejected: that store has
-- no concept of jobs, multi-stage DAGs, leases, qa_evidence, or discovery
-- state, which this execution path genuinely needs, so retiring it in
-- favor of production_store.py isn't a like-for-like option. This instead
-- imports production_store.py's two durability PRAGMAs directly, which is
-- the concrete "discipline" gap the audit actually pointed at.
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    registry_digest TEXT NOT NULL,
    created REAL NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shots (
    shot_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(job_id)
);
CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    shot_id TEXT NOT NULL,
    implementation_id TEXT NOT NULL,
    profile_id TEXT,
    registry_digest TEXT NOT NULL,
    lease_generation INTEGER,
    status TEXT NOT NULL,
    prompt_id TEXT,
    extra_json TEXT,
    created REAL NOT NULL,
    updated REAL NOT NULL,
    FOREIGN KEY(shot_id) REFERENCES shots(shot_id)
);
CREATE TABLE IF NOT EXISTS stages (
    attempt_id TEXT NOT NULL,
    stage_id TEXT NOT NULL,
    status TEXT NOT NULL,
    depends_on TEXT NOT NULL,
    family_key TEXT,
    PRIMARY KEY(attempt_id, stage_id)
);
CREATE TABLE IF NOT EXISTS artifacts (
    sha256 TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    attempt_id TEXT,
    path TEXT
);
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    created REAL NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discovery (
    digest TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    capability TEXT,
    updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS qa_evidence (
    evidence_id TEXT PRIMARY KEY,
    job_id TEXT,
    attempt_id TEXT NOT NULL,
    image_sha256 TEXT NOT NULL,
    profile_id TEXT,
    rubric_sha256 TEXT,
    policy_id TEXT,
    scores_json TEXT NOT NULL,
    qwen_json TEXT,
    wd14_json TEXT,
    prompt_sha256 TEXT,
    seed INTEGER,
    timing_s REAL,
    peak_gpu_mib REAL,
    retry_reason TEXT,
    status TEXT NOT NULL,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS qa_experiments (
    experiment_id TEXT PRIMARY KEY,
    parent_prompt_sha256 TEXT,
    variant_index INTEGER,
    variant_hash TEXT,
    seed INTEGER,
    scores_json TEXT,
    held_out_outcome TEXT,
    label TEXT,
    created REAL NOT NULL
);
"""


def connect(layout: GvdLayout) -> sqlite3.Connection:
    layout.ensure()
    conn = sqlite3.connect(str(layout.sqlite))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def freeze_job(conn: sqlite3.Connection, *, project_id: str, registry_digest: str) -> str:
    job_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO jobs(job_id, project_id, registry_digest, created, status) VALUES (?,?,?,?,?)",
        (job_id, project_id, registry_digest, time.time(), "PLANNED"),
    )
    conn.commit()
    return job_id


def add_shot(conn: sqlite3.Connection, *, job_id: str, shot_id: str, manifest: dict[str, Any]) -> None:
    """Insert or refresh a shot row, keyed globally by shot_id.

    Fix 2026-09-23 (readiness-audit finding 1.4): shot_id is a global
    PRIMARY KEY and freeze_job() mints a brand-new job_id on every
    execute_tool() call, so an unconditional INSERT here raised a SQLite
    UNIQUE constraint error the moment the same shot (e.g. C001) was
    replanned or resubmitted after a crash -- even once, let alone as part
    of routine recovery. Re-planning the same shot is a legitimate,
    expected operation (crash recovery, an operator re-running a shot), so
    this now upserts: the shot's job_id/manifest/status are refreshed to
    reflect the newest planning attempt instead of crashing.
    """
    conn.execute(
        """INSERT INTO shots(shot_id, job_id, manifest_json, status)
           VALUES (?,?,?,?)
           ON CONFLICT(shot_id) DO UPDATE SET
               job_id=excluded.job_id,
               manifest_json=excluded.manifest_json,
               status=excluded.status""",
        (shot_id, job_id, json.dumps(manifest), "PLANNED"),
    )
    conn.commit()


def add_attempt(
    conn: sqlite3.Connection,
    *,
    shot_id: str,
    implementation_id: str,
    registry_digest: str,
    profile_id: str | None,
    lease_generation: int | None,
    extra: dict[str, Any] | None = None,
) -> str:
    attempt_id = uuid.uuid4().hex
    now = time.time()
    conn.execute(
        """INSERT INTO attempts(attempt_id, shot_id, implementation_id, profile_id,
           registry_digest, lease_generation, status, extra_json, created, updated)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            attempt_id, shot_id, implementation_id, profile_id, registry_digest,
            lease_generation, "PLANNED", json.dumps(extra or {}), now, now,
        ),
    )
    conn.commit()
    return attempt_id


def set_attempt_status(conn: sqlite3.Connection, attempt_id: str, status: str, **fields: Any) -> None:
    cols = ["status=?", "updated=?"]
    args: list[Any] = [status, time.time()]
    for key, value in fields.items():
        cols.append(f"{key}=?")
        args.append(value)
    args.append(attempt_id)
    conn.execute(f"UPDATE attempts SET {', '.join(cols)} WHERE attempt_id=?", args)
    conn.commit()


def record_prompt_id(conn: sqlite3.Connection, attempt_id: str, prompt_id: str) -> None:
    """Commit SUBMITTING before HTTP; persist prompt_id after queue response."""
    set_attempt_status(conn, attempt_id, "QUEUED", prompt_id=prompt_id)


def find_attempt_by_prompt(conn: sqlite3.Connection, prompt_id: str) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM attempts WHERE prompt_id=?", (prompt_id,))
    return cur.fetchone()


def find_open_attempt(conn: sqlite3.Connection, shot_id: str, implementation_id: str) -> sqlite3.Row | None:
    # Fix 2026-09-23 (readiness-audit finding 1.4): RETRY_PENDING (set by
    # executor.submit_stage() on an ambiguous-timeout ExecutorError, before
    # re-raising) was not in this status set, so an attempt left in
    # RETRY_PENDING by a crash between the /prompt POST and prompt_id
    # persistence was invisible here and could be silently resubmitted,
    # risking a duplicate render.
    cur = conn.execute(
        """SELECT * FROM attempts WHERE shot_id=? AND implementation_id=?
           AND status IN ('PLANNED','SUBMITTING','QUEUED','RUNNING','RETRY_PENDING')
           ORDER BY created DESC LIMIT 1""",
        (shot_id, implementation_id),
    )
    return cur.fetchone()


def add_stage(conn: sqlite3.Connection, attempt_id: str, stage_id: str, depends_on: list[str], family_key: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO stages(attempt_id, stage_id, status, depends_on, family_key) VALUES (?,?,?,?,?)",
        (attempt_id, stage_id, "WAITING_DEPENDENCIES", json.dumps(depends_on), family_key),
    )
    conn.commit()


def set_stage_status(conn: sqlite3.Connection, attempt_id: str, stage_id: str, status: str) -> None:
    conn.execute(
        "UPDATE stages SET status=? WHERE attempt_id=? AND stage_id=?",
        (status, attempt_id, stage_id),
    )
    conn.commit()


def ready_stages(conn: sqlite3.Connection, attempt_id: str) -> list[sqlite3.Row]:
    stages = list(conn.execute("SELECT * FROM stages WHERE attempt_id=?", (attempt_id,)))
    accepted = {row["stage_id"] for row in stages if row["status"] == "SELECTED"}
    ready = []
    for row in stages:
        if row["status"] not in {"WAITING_DEPENDENCIES", "READY"}:
            continue
        deps = json.loads(row["depends_on"] or "[]")
        if set(deps) <= accepted:
            ready.append(row)
    return ready


def emit(conn: sqlite3.Connection, kind: str, payload: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO events(event_id, created, kind, payload) VALUES (?,?,?,?)",
        (uuid.uuid4().hex, time.time(), kind, json.dumps(payload)),
    )
    conn.commit()


def mark_discovery(conn: sqlite3.Connection, digest: str, state: str, capability: str | None = None) -> None:
    conn.execute(
        """INSERT INTO discovery(digest, state, capability, updated) VALUES (?,?,?,?)
           ON CONFLICT(digest) DO UPDATE SET state=excluded.state, updated=excluded.updated""",
        (digest, state, capability, time.time()),
    )
    conn.commit()


def pending_discovery(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM discovery WHERE state='validation_pending'"))
