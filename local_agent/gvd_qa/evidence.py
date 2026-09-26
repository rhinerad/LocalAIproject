"""Immutable QA evidence rows. Scores are insert-only."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

EVIDENCE_SCHEMA = """
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


def connect_evidence(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(EVIDENCE_SCHEMA)
    return conn


def insert_evidence(conn: sqlite3.Connection, *, job_id: str, verdict: dict[str, Any],
                    rubric_sha256: str, prompt_sha256: str | None = None,
                    peak_gpu_mib: float | None = None, timing_s: float | None = None) -> str:
    evidence_id = uuid.uuid4().hex
    status = "accepted" if verdict.get("accepted") else "rejected"
    if verdict.get("reasons"):
        retry_reason = ",".join(verdict["reasons"])
    else:
        retry_reason = None
    conn.execute(
        "INSERT INTO qa_evidence (evidence_id, job_id, attempt_id, image_sha256, "
        "profile_id, rubric_sha256, policy_id, scores_json, qwen_json, wd14_json, "
        "prompt_sha256, seed, timing_s, peak_gpu_mib, retry_reason, status, created) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            evidence_id, job_id, verdict.get("attempt_id"), verdict.get("image_sha256"),
            verdict.get("policy_id"), rubric_sha256, verdict.get("policy_id"),
            json.dumps(verdict.get("scores") or {}),
            json.dumps(verdict.get("qwen_checks")) if verdict.get("qwen_checks") is not None else None,
            json.dumps(verdict.get("wd14_traits") or {}),
            prompt_sha256, verdict.get("seed"), timing_s, peak_gpu_mib,
            retry_reason, status, time.time(),
        ),
    )
    conn.commit()
    return evidence_id


def insert_experiment(conn: sqlite3.Connection, row: dict[str, Any]) -> str:
    experiment_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO qa_experiments (experiment_id, parent_prompt_sha256, variant_index, "
        "variant_hash, seed, scores_json, held_out_outcome, label, created) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            experiment_id, row.get("parent_prompt_sha256"), row.get("variant_index"),
            row.get("variant_hash"), row.get("seed"),
            json.dumps(row.get("scores") or {}), row.get("held_out_outcome"),
            row.get("label"), time.time(),
        ),
    )
    conn.commit()
    return experiment_id


def read_evidence(conn: sqlite3.Connection, attempt_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM qa_evidence WHERE attempt_id = ? ORDER BY created",
        (attempt_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def experiment_rows(conn: sqlite3.Connection) -> Iterator[dict[str, Any]]:
    for row in conn.execute("SELECT * FROM qa_experiments ORDER BY created"):
        yield dict(row)
