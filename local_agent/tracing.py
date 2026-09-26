#!/usr/bin/env python3
"""Stdlib SQLite span logger. Leaf module: no agent/router/tools imports.

One file (``knowledge/traces.db``), WAL, per-write connection, ``BEGIN
IMMEDIATE`` — the same conventions as ``worker_farm/job_registry.py``.
OTel/OpenInference-shaped column names so a later exporter is a translator.

``start_ts`` / ``end_ts`` are epoch **seconds** (Python ``time.time()``).
A Phase B exporter multiplies by 1e9.

Kill switch: ``LOCAL_AGENT_TRACING=0`` (unset = on), same polarity as
``EQUAL_SHARES_COMFY_TIMESHARE``. Tracing never raises into the caller.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, NamedTuple

HERE = Path(__file__).resolve().parent
DEFAULT_DB = HERE / "knowledge" / "traces.db"
SUMMARY_LIMIT = 800
ERROR_LIMIT = 500
SCHEMA_VERSION = "1"
LOG = logging.getLogger("local_agent.tracing")

KINDS = frozenset({
    "turn", "hop", "route", "reason", "tool", "retrieval", "compact", "action",
})
_OI_KIND = {
    "turn": "AGENT",
    "hop": "CHAIN",
    "route": "CHAIN",
    "reason": "LLM",
    "tool": "TOOL",
    "retrieval": "RETRIEVER",
    "compact": "CHAIN",
    "action": "CHAIN",
}
_DEFAULT_NAME = {
    "turn": "agent.answer",
    "hop": "hop",
    "route": "router.decide",
    "reason": "ollama.chat_stream",
    "tool": "tool",
    "retrieval": "retrieval",
    "compact": "trim_context",
    "action": "action_resolver",
}
_REDACT_ARG_KEYS = ("path", "clip", "action", "name")

_BROKEN = False
_closed_turns = 0
_tls = threading.local()
_WAL_LOCK = threading.Lock()
_WAL_RETRIES = 50
_WAL_RETRY_SLEEP = 0.02

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS spans (
    trace_id        TEXT NOT NULL,
    span_id         TEXT NOT NULL,
    parent_span_id  TEXT,
    kind            TEXT NOT NULL,
    name            TEXT NOT NULL,
    start_ts        REAL NOT NULL,
    end_ts          REAL,
    input_summary   TEXT,
    output_summary  TEXT,
    tokens_in       INTEGER,
    tokens_out      INTEGER,
    model           TEXT,
    tier            TEXT,
    error           TEXT,
    conversation_id TEXT,
    hop_index       INTEGER,
    status_code     TEXT NOT NULL DEFAULT 'UNSET',
    attributes      TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (trace_id, span_id),
    CHECK (kind IN (
        'turn','hop','route','reason','tool','retrieval','compact','action'
    ))
);
CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id, start_ts);
CREATE INDEX IF NOT EXISTS idx_spans_conv  ON spans(conversation_id, start_ts);
CREATE INDEX IF NOT EXISTS idx_spans_kind  ON spans(kind, name, start_ts);
CREATE INDEX IF NOT EXISTS idx_spans_error ON spans(error) WHERE error IS NOT NULL;
CREATE TABLE IF NOT EXISTS span_refs (
    trace_id     TEXT NOT NULL,
    span_id      TEXT NOT NULL,
    ref_kind     TEXT NOT NULL,
    ref_target   TEXT NOT NULL,
    ref_offset   INTEGER,
    ref_ts       REAL,
    ref_extra    TEXT,
    PRIMARY KEY (trace_id, span_id, ref_kind, ref_target),
    FOREIGN KEY (trace_id, span_id) REFERENCES spans(trace_id, span_id)
        ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_refs_kind ON span_refs(ref_kind, ref_ts);
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class ToolArgSummary(NamedTuple):
    text: str
    arg_keys: list[str]
    arg_sha256: str
    arg_json_bytes: int


def enabled() -> bool:
    """Re-reads env every call so ``patch.dict`` works without a stale cache.

    ``LOCAL_AGENT_TRACING=0`` always wins. Unset is on in production. The
    unit suite does not write ``knowledge/traces.db`` unless a test sets
    ``LOCAL_AGENT_TRACES_DB`` (opt-in temp file).
    """
    if _BROKEN:
        return False
    if os.environ.get("LOCAL_AGENT_TRACING", "1").strip() == "0":
        return False
    if os.environ.get("LOCAL_AGENT_TRACES_DB", "").strip():
        return True
    if "unittest" in sys.modules or "pytest" in sys.modules:
        return False
    return True


def db_path() -> Path:
    override = os.environ.get("LOCAL_AGENT_TRACES_DB", "").strip()
    if override:
        return Path(override)
    return DEFAULT_DB


def reset_for_tests() -> None:
    """Clear process-local failure state and the thread-local span stack."""
    global _BROKEN, _closed_turns
    _BROKEN = False
    _closed_turns = 0
    _tls.stack = []


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_id() -> str:
    return uuid.uuid4().hex[:16]


def current_span() -> "Span | DummySpan | None":
    stack = _stack()
    return stack[-1] if stack else None


def summarize_text(kind: str, text: object) -> str:
    """Truncate/hash. Never calls ``artifacts.store``."""
    value = str(text or "")
    if "artifact_id=" in value:
        return value
    if len(value) <= SUMMARY_LIMIT:
        return value
    digest = hashlib.sha1(value.encode("utf8", "replace")).hexdigest()
    return (
        f"{value[:SUMMARY_LIMIT]}… [truncated kind={kind}; "
        f"sha1={digest}; original_chars={len(value)}]"
    )


def summarize_tool_args(args: dict | None) -> ToolArgSummary:
    """Same field set as ``remote_security._redact_args``; do not import it."""
    payload = args if isinstance(args, dict) else {}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    encoded = raw.encode("utf8")
    keys = sorted(str(k) for k in payload)
    digest = hashlib.sha256(encoded).hexdigest()
    parts = [f"keys={keys}", f"sha256={digest}", f"json_bytes={len(encoded)}"]
    for key in _REDACT_ARG_KEYS:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)):
            parts.append(f"{key}={str(value)[:260]}")
    return ToolArgSummary(
        text="; ".join(parts),
        arg_keys=keys,
        arg_sha256=digest,
        arg_json_bytes=len(encoded),
    )


def record_decision(span: "Span | DummySpan | None", route, *,
                    skip_farm: bool = False,
                    profile: str | None = None) -> None:
    """Allow-listed Decision fields only. Never ``as_dict()`` / ``detail``."""
    if span is None or getattr(span, "dummy", False):
        return
    try:
        span.tier = getattr(route, "tier", None)
        span.model = getattr(route, "model", None)
        span.set("host", getattr(route, "host", None))
        span.set("backend", getattr(route, "backend", None))
        span.set("gpu_busy", getattr(route, "gpu_busy", None))
        span.set("reason", getattr(route, "reason", None))
        span.set("skip_farm", bool(skip_farm))
        if profile is not None:
            span.set("profile", profile)
        detail = getattr(route, "detail", None)
        if not isinstance(detail, dict):
            return
        if "capability" in detail:
            span.set("capability", detail.get("capability"))
        timeshare = detail.get("timeshare")
        if not isinstance(timeshare, dict):
            return
        if "path" in timeshare:
            span.set("timeshare.path", timeshare.get("path"))
        if "outcome" in timeshare:
            span.set("timeshare.outcome", timeshare.get("outcome"))
        clear = timeshare.get("clear_vram")
        if isinstance(clear, dict) and "ok" in clear:
            span.set("timeshare.clear_vram.ok", clear.get("ok"))
    except Exception:
        _warn("record_decision failed")


@contextmanager
def span(kind: str, name: str | None = None, **fields) -> Iterator["Span | DummySpan"]:
    """Start a span. Never raises to the caller (except the traced body)."""
    dummy = DummySpan()
    if not enabled() or kind not in KINDS:
        _stack().append(dummy)
        try:
            yield dummy
        finally:
            _pop(dummy)
        return

    opened: Span | None = None
    try:
        opened = Span._start(kind, name, fields)
        _stack().append(opened)
    except Exception as exc:
        _mark_broken(exc)
        _warn("span insert failed")
        _stack().append(dummy)
        try:
            yield dummy
        finally:
            _pop(dummy)
        return

    try:
        yield opened
    except Exception as body_exc:
        try:
            if not opened.error:
                opened.error = str(body_exc)[:ERROR_LIMIT]
            opened._flush("ERROR")
        except Exception:
            _mark_broken()
            _warn("span flush failed after body error")
        _pop(opened)
        raise
    else:
        try:
            status = "ERROR" if opened.error else "OK"
            opened._flush(status)
        except Exception as exc:
            _mark_broken(exc)
            _warn("span flush failed")
        _pop(opened)


def _maybe_prune() -> None:
    """Run ``prune()`` every 100 closed turns. Never between hop INSERT and generate."""
    global _closed_turns
    if not enabled():
        return
    _closed_turns += 1
    if _closed_turns % 100 != 0:
        return
    prune()


def prune(max_age_days: int = 14, max_spans: int = 50_000) -> dict:
    """Best-effort whole-trace retention. Never VACUUM. Never unlinks the DB."""
    if not enabled():
        return {}
    path = db_path()
    if not path.is_file():
        return {"deleted_spans": 0, "remaining_spans": 0}
    try:
        with _connection(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            before = conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
            cutoff = time.time() - max(0, max_age_days) * 86400
            conn.execute(
                """DELETE FROM spans WHERE trace_id IN (
                       SELECT trace_id FROM spans
                       WHERE kind='turn' AND start_ts < ?
                   )""",
                (cutoff,),
            )
            remaining = conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0]
            if remaining > max_spans:
                target = max(0, (max_spans * 4) // 5)
                while remaining > target:
                    row = conn.execute(
                        """SELECT trace_id FROM spans WHERE kind='turn'
                           ORDER BY start_ts ASC LIMIT 1"""
                    ).fetchone()
                    if not row:
                        conn.execute("DELETE FROM spans")
                        remaining = 0
                        break
                    conn.execute(
                        "DELETE FROM spans WHERE trace_id=?", (row[0],))
                    remaining = conn.execute(
                        "SELECT COUNT(*) FROM spans").fetchone()[0]
            conn.execute("COMMIT")
            return {
                "deleted_spans": int(before) - int(remaining),
                "remaining_spans": int(remaining),
            }
    except Exception as exc:
        _mark_broken(exc)
        _warn("prune failed")
        return {}


def fetch_trace(trace_id: str) -> list[dict]:
    return _fetch_spans("trace_id = ?", (trace_id,))


def fetch_turn(conversation_id: str, *, since: float | None = None) -> list[dict]:
    if since is None:
        return _fetch_spans("conversation_id = ?", (conversation_id,))
    return _fetch_spans(
        "conversation_id = ? AND start_ts >= ?", (conversation_id, since))


class DummySpan:
    """No-op span. Setters never touch SQLite."""
    dummy = True

    def __init__(self):
        self.span_id = None
        self.trace_id = None
        self.parent_span_id = None
        self.kind = None
        self.name = None
        self.tokens_in = None
        self.tokens_out = None
        self.model = None
        self.tier = None
        self.error = None
        self.input_summary = None
        self.output_summary = None
        self.hop_index = None
        self.conversation_id = None

    def set(self, key: str, value: object) -> None:
        return None

    def link(self, ref_kind: str, *, target: str,
             offset: int | None = None, ts: float | None = None,
             extra: dict | None = None) -> None:
        return None


class Span:
    dummy = False

    def __init__(self):
        self.trace_id = ""
        self.span_id = ""
        self.parent_span_id = None
        self.kind = ""
        self.name = ""
        self.start_ts = 0.0
        self.tokens_in = None
        self.tokens_out = None
        self.model = None
        self.tier = None
        self.error = None
        self.input_summary = None
        self.output_summary = None
        self.hop_index = None
        self.conversation_id = None
        self._attrs: dict = {}
        self._pending_refs: list[dict] = []

    @classmethod
    def _start(cls, kind: str, name: str | None, fields: dict) -> "Span":
        parent_obj = fields.pop("parent", None)
        parent_span_id = fields.pop("parent_span_id", None)
        parent = parent_obj if isinstance(parent_obj, Span) else _real_parent()
        if parent_span_id is None and parent is not None:
            parent_span_id = parent.span_id
        sp = cls()
        sp.kind = kind
        sp.name = name or _DEFAULT_NAME.get(kind, kind)
        sp.span_id = new_span_id()
        sp.trace_id = fields.pop("trace_id", None) or (
            parent.trace_id if parent is not None else new_trace_id())
        sp.parent_span_id = parent_span_id
        sp.conversation_id = fields.pop("conversation_id", None)
        if sp.conversation_id is None and parent is not None:
            sp.conversation_id = parent.conversation_id
        sp.hop_index = fields.pop("hop_index", None)
        if sp.hop_index is None and parent is not None:
            sp.hop_index = parent.hop_index
        sp.model = fields.pop("model", None)
        sp.tier = fields.pop("tier", None)
        sp.tokens_in = fields.pop("tokens_in", None)
        sp.tokens_out = fields.pop("tokens_out", None)
        sp.input_summary = fields.pop("input_summary", None)
        sp.output_summary = fields.pop("output_summary", None)
        sp.start_ts = time.time()
        sp._attrs["openinference.span.kind"] = _OI_KIND.get(kind, "CHAIN")
        for key, value in fields.items():
            sp.set(key, value)
        sp._insert()
        return sp

    def set(self, key: str, value: object) -> None:
        self._attrs[str(key)] = _jsonable(value)

    def link(self, ref_kind: str, *, target: str,
             offset: int | None = None, ts: float | None = None,
             extra: dict | None = None) -> None:
        """Append to an in-memory list. Never SQLite. Never raises."""
        try:
            if not target:
                return
            flat: dict = {}
            if isinstance(extra, dict):
                for key, value in extra.items():
                    if isinstance(value, (dict, list, tuple)):
                        continue
                    flat[str(key)] = _jsonable(value)
            self._pending_refs.append({
                "ref_kind": str(ref_kind),
                "ref_target": str(target),
                "ref_offset": None if offset is None else int(offset),
                "ref_ts": None if ts is None else float(ts),
                "ref_extra": json.dumps(flat, ensure_ascii=False) if extra is not None else None,
            })
        except Exception:
            return None

    def _insert(self) -> None:
        path = db_path()
        with _connection(path) as conn:
            _ensure_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """INSERT INTO spans (
                    trace_id, span_id, parent_span_id, kind, name, start_ts,
                    end_ts, input_summary, output_summary, tokens_in, tokens_out,
                    model, tier, error, conversation_id, hop_index, status_code,
                    attributes
                ) VALUES (?,?,?,?,?,?,NULL,?,?,?,?,?,?,?,?,?,'UNSET',?)""",
                (
                    self.trace_id, self.span_id, self.parent_span_id, self.kind,
                    self.name, self.start_ts, self.input_summary,
                    self.output_summary, self.tokens_in, self.tokens_out,
                    self.model, self.tier,
                    None if self.error is None else str(self.error)[:ERROR_LIMIT],
                    self.conversation_id, self.hop_index,
                    json.dumps(self._attrs, ensure_ascii=False),
                ),
            )
            conn.execute("COMMIT")

    def _flush(self, status_code: str) -> None:
        error = None if self.error is None else str(self.error)[:ERROR_LIMIT]
        attrs = json.dumps(self._attrs, ensure_ascii=False)
        path = db_path()
        with _connection(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """UPDATE spans SET
                    end_ts=?, input_summary=?, output_summary=?, tokens_in=?,
                    tokens_out=?, model=?, tier=?, error=?, hop_index=?,
                    conversation_id=?, status_code=?, attributes=?
                   WHERE trace_id=? AND span_id=?""",
                (
                    time.time(), self.input_summary, self.output_summary,
                    self.tokens_in, self.tokens_out, self.model, self.tier,
                    error, self.hop_index, self.conversation_id, status_code,
                    attrs, self.trace_id, self.span_id,
                ),
            )
            for ref in self._pending_refs:
                conn.execute(
                    """INSERT OR REPLACE INTO span_refs (
                        trace_id, span_id, ref_kind, ref_target,
                        ref_offset, ref_ts, ref_extra
                    ) VALUES (?,?,?,?,?,?,?)""",
                    (
                        self.trace_id, self.span_id, ref["ref_kind"],
                        ref["ref_target"], ref["ref_offset"], ref["ref_ts"],
                        ref["ref_extra"],
                    ),
                )
            conn.execute("COMMIT")
        self._pending_refs.clear()


def _stack() -> list:
    stack = getattr(_tls, "stack", None)
    if stack is None:
        _tls.stack = []
        stack = _tls.stack
    return stack


def _pop(item) -> None:
    stack = _stack()
    if stack and stack[-1] is item:
        stack.pop()
        return
    try:
        stack.remove(item)
    except ValueError:
        return


def _real_parent() -> Span | None:
    for item in reversed(_stack()):
        if isinstance(item, Span) and not item.dummy:
            return item
    return None


def _jsonable(value: object):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in list(value)[:32]]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in list(value.items())[:32]}
    return str(value)[:500]


def _warn(message: str) -> None:
    LOG.warning(message, exc_info=True)


def _mark_broken(exc: BaseException | None = None) -> None:
    global _BROKEN
    if exc is None or isinstance(exc, sqlite3.DatabaseError):
        _BROKEN = True


def _enable_wal(conn: sqlite3.Connection) -> None:
    """Switch to WAL without tripping the first-open race.

    Converting a fresh DB to WAL needs an exclusive lock and SQLite reports
    "database is locked" immediately instead of honouring the busy timeout,
    which used to mark tracing broken when two threads opened a new DB at
    once. Serialize it in-process; retry briefly for another process.
    """
    with _WAL_LOCK:
        for attempt in range(_WAL_RETRIES):
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                return
            except sqlite3.OperationalError as exc:
                text = str(exc).lower()
                if attempt == _WAL_RETRIES - 1 or (
                        "locked" not in text and "busy" not in text):
                    raise
                time.sleep(_WAL_RETRY_SLEEP)


@contextmanager
def _connection(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    try:
        _enable_wal(conn)
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_CREATE_SQL)
    conn.execute(
        "INSERT OR IGNORE INTO schema_meta(key, value) VALUES (?, ?)",
        ("schema_version", SCHEMA_VERSION),
    )


def _fetch_spans(where: str, params: tuple) -> list[dict]:
    path = db_path()
    if not path.is_file():
        return []
    try:
        with _connection(path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM spans WHERE {where} ORDER BY start_ts, span_id",
                params,
            ).fetchall()
            refs = conn.execute(
                f"""SELECT * FROM span_refs WHERE (trace_id, span_id) IN (
                        SELECT trace_id, span_id FROM spans WHERE {where}
                    )""",
                params,
            ).fetchall()
        by_span: dict[tuple, list] = {}
        for ref in refs:
            item = dict(ref)
            if item.get("ref_extra"):
                try:
                    item["ref_extra"] = json.loads(item["ref_extra"])
                except json.JSONDecodeError:
                    pass
            by_span.setdefault((item["trace_id"], item["span_id"]), []).append(item)
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["attributes"] = json.loads(item.get("attributes") or "{}")
            except json.JSONDecodeError:
                item["attributes"] = {}
            item["refs"] = by_span.get((item["trace_id"], item["span_id"]), [])
            out.append(item)
        return out
    except Exception:
        _warn("fetch failed")
        return []
