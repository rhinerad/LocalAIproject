#!/usr/bin/env python3
"""Transactional SQLite job / attempt store (P1-A).

Adapted from ref_outputs/pipeline_reference.py. Authoritative for attempt
lifecycle; progress.json remains an export/view when runners sync to it.

No ComfyUI / GPU / network. Offline-safe.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

ATTEMPT_STATES = frozenset({
    "PLANNED", "READY", "DRY_RUN", "SUBMITTING", "RUNNING", "RENDERED",
    "TECHNICAL_QA", "CONTENT_QA", "SELECTED",
    "RETRY_PENDING",
    "FAILED_SUBMIT", "FAILED_RENDER", "FAILED_TECHNICAL_QA",
    "FAILED_CONTENT_QA", "FAILED_ADMISSION", "CANCELLED", "INVALIDATED",
})

# Pipeline / progress states used by resume harness (may mirror attempt.state).
PIPELINE_RESUME_SKIP_STATES = frozenset({"SELECTED"})
PIPELINE_RESUME_CONTINUE_STATES = frozenset({
    "PLANNED", "READY", "DRY_RUN", "SUBMITTING", "RUNNING", "RENDERED",
    "TECHNICAL_QA", "CONTENT_QA", "QA_PENDING", "RETRY_PENDING",
    "FAILED_SUBMIT", "FAILED_RENDER", "FAILED_TECHNICAL_QA",
    "FAILED_CONTENT_QA", "FAILED_ADMISSION", "CANCELLED", "INVALIDATED",
})

DDL = """
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS shots (
  shot_id TEXT PRIMARY KEY,
  revision INTEGER NOT NULL DEFAULT 0,
  selected_attempt_id TEXT,
  state TEXT NOT NULL DEFAULT 'PLANNED',
  parent_shot_id TEXT,
  continuity_mode TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
  attempt_id TEXT PRIMARY KEY,
  shot_id TEXT NOT NULL REFERENCES shots(shot_id),
  input_hash TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'PLANNED',
  artifact_path TEXT,
  artifact_sha256 TEXT,
  technical_pass INTEGER NOT NULL DEFAULT 0,
  visual_pass INTEGER NOT NULL DEFAULT 0,
  audio_pass INTEGER NOT NULL DEFAULT 0,
  required_audio INTEGER NOT NULL DEFAULT 0,
  parent_attempt_id TEXT,
  revision_at_create INTEGER NOT NULL DEFAULT 0,
  meta_json TEXT,
  created_at TEXT,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_attempts_shot ON attempts(shot_id);
CREATE INDEX IF NOT EXISTS idx_attempts_state ON attempts(state);
CREATE INDEX IF NOT EXISTS idx_shots_parent ON shots(parent_shot_id);
"""


def digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def connect(db_path: Path | str, *, memory: bool = False) -> sqlite3.Connection:
    if memory or str(db_path) == ":memory:":
        conn = sqlite3.connect(":memory:", isolation_level=None)
    else:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.executescript(DDL)
    return conn


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_shot(
    db: sqlite3.Connection,
    shot_id: str,
    *,
    parent_shot_id: str | None = None,
    continuity_mode: str | None = None,
) -> None:
    row = db.execute("SELECT shot_id FROM shots WHERE shot_id=?", (shot_id,)).fetchone()
    if row:
        return
    db.execute(
        "INSERT INTO shots(shot_id, revision, state, parent_shot_id, continuity_mode, updated_at) "
        "VALUES (?, 0, 'PLANNED', ?, ?, ?)",
        (shot_id, parent_shot_id, continuity_mode, _now()),
    )


def create_attempt(
    db: sqlite3.Connection,
    *,
    shot_id: str,
    input_payload: dict,
    attempt_id: str | None = None,
    parent_attempt_id: str | None = None,
    required_audio: bool = False,
    meta: dict | None = None,
    state: str = "READY",
) -> str:
    """Create attempt row with input_hash BEFORE submit."""
    if state not in ATTEMPT_STATES:
        raise ValueError(f"unknown attempt state: {state}")
    ensure_shot(db, shot_id)
    shot = db.execute("SELECT revision FROM shots WHERE shot_id=?", (shot_id,)).fetchone()
    aid = attempt_id or f"att_{uuid.uuid4().hex[:16]}"
    ih = digest(input_payload)
    now = _now()
    db.execute(
        "INSERT INTO attempts("
        "attempt_id, shot_id, input_hash, state, required_audio, "
        "parent_attempt_id, revision_at_create, meta_json, created_at, updated_at"
        ") VALUES (?,?,?,?,?,?,?,?,?,?)",
        (aid, shot_id, ih, state, 1 if required_audio else 0,
         parent_attempt_id, int(shot["revision"]),
         json.dumps(meta or {}, ensure_ascii=False), now, now),
    )
    db.execute(
        "UPDATE shots SET state=?, updated_at=? WHERE shot_id=?",
        (state if state != "SELECTED" else "PLANNED", now, shot_id),
    )
    return aid


def set_attempt_state(
    db: sqlite3.Connection,
    attempt_id: str,
    state: str,
    *,
    artifact_path: str | None = None,
    artifact_sha256: str | None = None,
) -> None:
    if state not in ATTEMPT_STATES:
        raise ValueError(f"unknown attempt state: {state}")
    cols = ["state=?", "updated_at=?"]
    vals: list[Any] = [state, _now()]
    if artifact_path is not None:
        cols.append("artifact_path=?")
        vals.append(artifact_path)
    if artifact_sha256 is not None:
        cols.append("artifact_sha256=?")
        vals.append(artifact_sha256)
    vals.append(attempt_id)
    changed = db.execute(
        f"UPDATE attempts SET {', '.join(cols)} WHERE attempt_id=?", vals
    ).rowcount
    if changed != 1:
        raise KeyError(f"attempt not found: {attempt_id}")
    row = db.execute(
        "SELECT shot_id FROM attempts WHERE attempt_id=?", (attempt_id,)
    ).fetchone()
    if row:
        db.execute(
            "UPDATE shots SET state=?, updated_at=? WHERE shot_id=?",
            (state, _now(), row["shot_id"]),
        )


def mark_qa_flags(
    db: sqlite3.Connection,
    attempt_id: str,
    *,
    technical_pass: bool | None = None,
    visual_pass: bool | None = None,
    audio_pass: bool | None = None,
) -> None:
    sets: list[str] = ["updated_at=?"]
    vals: list[Any] = [_now()]
    if technical_pass is not None:
        sets.append("technical_pass=?")
        vals.append(1 if technical_pass else 0)
    if visual_pass is not None:
        sets.append("visual_pass=?")
        vals.append(1 if visual_pass else 0)
    if audio_pass is not None:
        sets.append("audio_pass=?")
        vals.append(1 if audio_pass else 0)
    vals.append(attempt_id)
    db.execute(f"UPDATE attempts SET {', '.join(sets)} WHERE attempt_id=?", vals)


def select_attempt(
    db: sqlite3.Connection,
    shot_id: str,
    revision: int,
    attempt_id: str,
    *,
    invalidate_descendants: bool = True,
) -> None:
    """Atomically promote a validated candidate using revision fencing."""
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute(
            "SELECT shot_id, artifact_sha256, technical_pass, visual_pass, "
            "audio_pass, required_audio, state FROM attempts WHERE attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if (
            not row
            or row["shot_id"] != shot_id
            or not row["artifact_sha256"]
            or not row["technical_pass"]
            or not row["visual_pass"]
            or (row["required_audio"] and not row["audio_pass"])
        ):
            raise ValueError("attempt has not passed required gates")
        changed = db.execute(
            "UPDATE shots SET selected_attempt_id=?, state='SELECTED', "
            "revision=revision+1, updated_at=? "
            "WHERE shot_id=? AND revision=?",
            (attempt_id, _now(), shot_id, revision),
        ).rowcount
        if changed != 1:
            raise RuntimeError("stale worker revision")
        db.execute(
            "UPDATE attempts SET state='SELECTED', updated_at=? WHERE attempt_id=?",
            (_now(), attempt_id),
        )
        if invalidate_descendants:
            _invalidate_descendants_locked(db, shot_id)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _invalidate_descendants_locked(db: sqlite3.Connection, parent_shot_id: str) -> int:
    kids = db.execute(
        "SELECT shot_id FROM shots WHERE parent_shot_id=?", (parent_shot_id,)
    ).fetchall()
    n = 0
    for kid in kids:
        sid = kid["shot_id"]
        db.execute(
            "UPDATE shots SET selected_attempt_id=NULL, state='INVALIDATED', "
            "revision=revision+1, updated_at=? WHERE shot_id=?",
            (_now(), sid),
        )
        cur = db.execute(
            "UPDATE attempts SET state='INVALIDATED', updated_at=? "
            "WHERE shot_id=? AND state NOT IN ('FAILED_SUBMIT','FAILED_RENDER',"
            "'FAILED_TECHNICAL_QA','FAILED_CONTENT_QA','FAILED_ADMISSION','CANCELLED')",
            (_now(), sid),
        )
        n += cur.rowcount
        n += _invalidate_descendants_locked(db, sid)
    prior = db.execute(
        "SELECT attempt_id FROM attempts WHERE shot_id=?", (parent_shot_id,)
    ).fetchall()
    prior_ids = {r["attempt_id"] for r in prior}
    if prior_ids:
        placeholders = ",".join("?" * len(prior_ids))
        cur = db.execute(
            f"UPDATE attempts SET state='INVALIDATED', updated_at=? "
            f"WHERE parent_attempt_id IN ({placeholders}) "
            f"AND state NOT IN ('SELECTED','FAILED_SUBMIT','FAILED_RENDER',"
            f"'FAILED_TECHNICAL_QA','FAILED_CONTENT_QA','FAILED_ADMISSION','CANCELLED')",
            [_now(), *prior_ids],
        )
        n += cur.rowcount
    return n


def invalidate_descendants(db: sqlite3.Connection, parent_shot_id: str) -> int:
    db.execute("BEGIN IMMEDIATE")
    try:
        n = _invalidate_descendants_locked(db, parent_shot_id)
        db.commit()
        return n
    except BaseException:
        db.rollback()
        raise


def get_selected_attempt(db: sqlite3.Connection, shot_id: str) -> sqlite3.Row | None:
    shot = db.execute(
        "SELECT selected_attempt_id, state FROM shots WHERE shot_id=?", (shot_id,)
    ).fetchone()
    if not shot or not shot["selected_attempt_id"]:
        return None
    if str(shot["state"]).upper() != "SELECTED":
        return None
    return db.execute(
        "SELECT * FROM attempts WHERE attempt_id=? AND state='SELECTED'",
        (shot["selected_attempt_id"],),
    ).fetchone()


def get_selected_artifact_path(db: sqlite3.Connection, shot_id: str) -> str | None:
    row = get_selected_attempt(db, shot_id)
    if not row:
        return None
    return row["artifact_path"]


def export_progress_view(
    db: sqlite3.Connection,
    shot_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Export a progress.json-compatible view (SQLite remains authoritative)."""
    if shot_ids is None:
        rows = db.execute("SELECT * FROM shots ORDER BY shot_id").fetchall()
    else:
        ids = list(shot_ids)
        if not ids:
            return {"clips": {}, "source": "production_store"}
        placeholders = ",".join("?" * len(ids))
        rows = db.execute(
            f"SELECT * FROM shots WHERE shot_id IN ({placeholders}) ORDER BY shot_id",
            ids,
        ).fetchall()
    clips: dict[str, Any] = {}
    for shot in rows:
        sid = shot["shot_id"]
        att = None
        if shot["selected_attempt_id"]:
            att = db.execute(
                "SELECT * FROM attempts WHERE attempt_id=?",
                (shot["selected_attempt_id"],),
            ).fetchone()
        latest = db.execute(
            "SELECT * FROM attempts WHERE shot_id=? ORDER BY created_at DESC LIMIT 1",
            (sid,),
        ).fetchone()
        use = att or latest
        clips[sid] = {
            "pipeline_state": shot["state"],
            "status": str(shot["state"] or "").lower(),
            "revision": shot["revision"],
            "selected_attempt_id": shot["selected_attempt_id"],
            "video_path": (use["artifact_path"] if use else None),
            "verified": bool(att and shot["state"] == "SELECTED"),
            "attempt_id": (use["attempt_id"] if use else None),
            "input_hash": (use["input_hash"] if use else None),
        }
    return {"source": "production_store", "updated": _now(), "clips": clips}


# --- GPU lease / prompt reconcile helpers (P1-D; Comfy client stubbable) ---

class GpuLeaseError(RuntimeError):
    """Admission or lease contract failure — always blocking."""


class VramAdmissionError(GpuLeaseError):
    """VRAM prepare / admission failed; must not continue to submit."""


def cancel_and_reconcile_prompt(
    client: Any,
    *,
    prompt_id: str | None,
    attempt_id: str | None = None,
) -> dict[str, Any]:
    """Cancel in-flight prompt then reconcile queue/history before lease release."""
    trace: dict[str, Any] = {
        "attempt_id": attempt_id,
        "prompt_id": prompt_id,
        "cancelled": False,
        "reconciled": False,
        "stubs": [],
    }
    if prompt_id and hasattr(client, "cancel_prompt"):
        client.cancel_prompt(prompt_id)
        trace["cancelled"] = True
    elif hasattr(client, "interrupt"):
        client.interrupt()
        trace["cancelled"] = True
    else:
        trace["stubs"].append("cancel_prompt")

    if hasattr(client, "reconcile"):
        client.reconcile(prompt_id=prompt_id)
        trace["reconciled"] = True
    elif hasattr(client, "wait_idle"):
        client.wait_idle()
        trace["reconciled"] = True
    else:
        trace["stubs"].append("reconcile")
    return trace


def release_gpu_lease(
    client: Any,
    *,
    prompt_id: str | None = None,
    attempt_id: str | None = None,
    reason: str = "attempt finally",
) -> dict[str, Any]:
    """Owned-attempt finally: cancel/reconcile THEN release GPU lease."""
    trace = cancel_and_reconcile_prompt(
        client, prompt_id=prompt_id, attempt_id=attempt_id
    )
    trace["reason"] = reason
    trace["lease_released"] = False
    if hasattr(client, "release_lease"):
        client.release_lease(reason=reason)
        trace["lease_released"] = True
    elif hasattr(client, "release_after_comfyui"):
        client.release_after_comfyui(reason=reason)
        trace["lease_released"] = True
    else:
        freed = free_vram_safe(client, unload_models=True, free_memory=True)
        trace["lease_released"] = bool(freed.get("ok"))
        trace["free_vram"] = freed
    return trace


def free_vram_safe(
    api: Any,
    *,
    unload_models: bool = True,
    free_memory: bool = True,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Call free_vram / comfy_free_memory with the correct keyword contract."""
    out: dict[str, Any] = {"ok": False, "method": None, "error": None}
    if api is None:
        out["error"] = "no api"
        return out
    try:
        if hasattr(api, "comfy_free_memory"):
            api.comfy_free_memory(
                unload_models=unload_models,
                free_memory=free_memory,
                update_state=True,
            )
            out.update(ok=True, method="comfy_free_memory")
            return out
        if hasattr(api, "free_vram"):
            import inspect
            try:
                sig = inspect.signature(api.free_vram)
            except (TypeError, ValueError):
                sig = None
            if base_url is not None:
                api.free_vram(
                    base_url,
                    unload_models=unload_models,
                    free_memory=free_memory,
                )
            elif sig is not None and any(
                p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                and p.name in {"url", "base_url", "comfy_url"}
                for p in sig.parameters.values()
            ):
                raise TypeError(
                    "free_vram requires base_url=...; refusing wrong kwargs/positionals"
                )
            else:
                api.free_vram(
                    unload_models=unload_models,
                    free_memory=free_memory,
                )
            out.update(ok=True, method="free_vram")
            return out
        out["error"] = "no free_vram method"
    except Exception as exc:
        out["error"] = str(exc)
    return out


def prepare_vram_or_raise(prepare_fn: Any, *, reason: str) -> None:
    """Admission failure is blocking — never swallow and continue."""
    try:
        prepare_fn(reason=reason)
    except VramAdmissionError:
        raise
    except Exception as exc:
        raise VramAdmissionError(f"VRAM admission failed ({reason}): {exc}") from exc



# --- Continuity / asset / dialogue helpers (audit §5 + §10 wiring) ----------

def merge_attempt_meta(
    db: sqlite3.Connection,
    attempt_id: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Merge keys into attempts.meta_json (boundary, dialogue, voice assets)."""
    row = db.execute(
        "SELECT meta_json FROM attempts WHERE attempt_id=?", (attempt_id,)
    ).fetchone()
    if not row:
        raise KeyError(f"attempt not found: {attempt_id}")
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except json.JSONDecodeError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    meta.update(patch)
    db.execute(
        "UPDATE attempts SET meta_json=?, updated_at=? WHERE attempt_id=?",
        (json.dumps(meta, ensure_ascii=False), _now(), attempt_id),
    )
    return meta


def record_boundary_on_attempt(
    db: sqlite3.Connection,
    attempt_id: str,
    *,
    frame_index: int,
    png_path: str,
    content_hash: str,
    source_artifact: str,
    extracted_before_vhs: bool = True,
    extracted_before_subtitles: bool = True,
) -> dict[str, Any]:
    """Persist clean-render boundary metadata on the attempt row."""
    if not extracted_before_vhs or not extracted_before_subtitles:
        raise ValueError("boundary must come from clean render before VHS/subtitles")
    boundary = {
        "frame_index": int(frame_index),
        "png_path": str(png_path),
        "content_hash": str(content_hash),
        "source_artifact": str(source_artifact),
        "extracted_before_vhs": True,
        "extracted_before_subtitles": True,
    }
    return merge_attempt_meta(db, attempt_id, {"boundary": boundary})


def get_attempt_boundary(db: sqlite3.Connection, attempt_id: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT meta_json FROM attempts WHERE attempt_id=?", (attempt_id,)
    ).fetchone()
    if not row:
        return None
    try:
        meta = json.loads(row["meta_json"] or "{}")
    except json.JSONDecodeError:
        return None
    b = meta.get("boundary") if isinstance(meta, dict) else None
    return b if isinstance(b, dict) else None


def store_shot_dialogue(
    db: sqlite3.Connection,
    attempt_id: str,
    dialogue_lines: list[dict[str, Any]],
    *,
    audio_mode: str | None = None,
    voice_asset_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Store speaker_id + exact text dialogue separately from voice assets."""
    normalized: list[dict[str, Any]] = []
    for item in dialogue_lines or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        speaker = str(
            item.get("speaker_id") or item.get("speaker") or "unknown"
        ).strip() or "unknown"
        normalized.append({
            "speaker_id": speaker,
            "text": text,
            "voice_asset_id": item.get("voice_asset_id"),
        })
    patch: dict[str, Any] = {"dialogue_lines": normalized}
    if audio_mode is not None:
        patch["audio_mode"] = str(audio_mode)
    if voice_asset_ids is not None:
        patch["voice_asset_ids"] = list(voice_asset_ids)
    return merge_attempt_meta(db, attempt_id, patch)


def get_selected_boundary(
    db: sqlite3.Connection, shot_id: str
) -> dict[str, Any] | None:
    """Boundary for the SELECTED attempt of a shot (continuity parent lookup)."""
    sel = get_selected_attempt(db, shot_id)
    if not sel:
        return None
    return get_attempt_boundary(db, sel["attempt_id"])



# --- Resume / QA / uncertain-submit helpers (continuity failure harness) ---

def resume_should_skip_attempt(state: str | None, *, verified: bool = False) -> bool:
    """True only when SELECTED (QA-verified). RENDERED / QA_PENDING must NOT skip."""
    s = str(state or "").upper()
    if s == "SELECTED":
        return True
    if s in {"QA_PENDING", "RENDERED", "RETRY_PENDING", "TECHNICAL_QA", "CONTENT_QA",
             "SUBMITTING", "RUNNING", "READY", "PLANNED", "DRY_RUN"}:
        return False
    if verified and s == "SELECTED":
        return True
    return False


def mark_technical_qa(
    db: sqlite3.Connection,
    attempt_id: str,
    *,
    passed: bool,
    reason: str | None = None,
) -> str:
    """Apply technical QA. Fail → RETRY_PENDING (not SELECTED). Pass → TECHNICAL_QA done."""
    mark_qa_flags(db, attempt_id, technical_pass=passed)
    if passed:
        set_attempt_state(db, attempt_id, "TECHNICAL_QA")
        if reason:
            merge_attempt_meta(db, attempt_id, {"technical_qa_reason": reason})
        return "TECHNICAL_QA"
    set_attempt_state(db, attempt_id, "RETRY_PENDING")
    merge_attempt_meta(
        db,
        attempt_id,
        {
            "technical_qa_pass": False,
            "technical_qa_reason": reason or "technical_qa_failed",
            "pipeline_state": "RETRY_PENDING",
        },
    )
    return "RETRY_PENDING"


def reconcile_submitting_without_prompt_id(
    *,
    attempt_id: str,
    attempt_state: str,
    prompt_id: str | None,
    queue_prompt_ids: Iterable[str] | None = None,
    history_prompt_ids: Iterable[str] | None = None,
    enqueue_fn: Any | None = None,
) -> dict[str, Any]:
    """Logic-level: SUBMITTING with no prompt_id must NOT duplicate-enqueue.

    Returns a decision dict. Does not call Comfy; enqueue_fn is only invoked
    when reconcile proves the prompt is absent from queue AND history AND
    an explicit safe re-submit is requested (default: never auto-enqueue).
    """
    state = str(attempt_state or "").upper()
    queued = {str(x) for x in (queue_prompt_ids or []) if x}
    history = {str(x) for x in (history_prompt_ids or []) if x}
    decision: dict[str, Any] = {
        "attempt_id": attempt_id,
        "state": state,
        "prompt_id": prompt_id,
        "action": "noop",
        "enqueued": False,
        "duplicate_enqueue_prevented": False,
        "reason": "",
    }
    if state != "SUBMITTING":
        decision["action"] = "noop"
        decision["reason"] = f"state={state} not SUBMITTING"
        return decision

    if prompt_id:
        pid = str(prompt_id)
        if pid in queued or pid in history:
            decision["action"] = "reconcile_existing"
            decision["reason"] = "prompt_id found in queue/history; do not enqueue"
            decision["duplicate_enqueue_prevented"] = True
            return decision
        decision["action"] = "wait_or_poll"
        decision["reason"] = "prompt_id known but not yet in queue/history"
        return decision

    # Uncertain: SUBMITTING without prompt_id — never duplicate-enqueue.
    decision["action"] = "reconcile_uncertain"
    decision["reason"] = (
        "SUBMITTING without prompt_id: reconcile queue/history only; "
        "do not enqueue a second prompt"
    )
    decision["duplicate_enqueue_prevented"] = True
    # Explicitly do NOT call enqueue_fn on the uncertain path.
    if enqueue_fn is not None:
        # Guard: calling would be a bug; record that we refused.
        decision["enqueue_fn_refused"] = True
    return decision



def self_test() -> None:
    with connect(":memory:", memory=True) as db:
        ensure_shot(db, "s1")
        aid = create_attempt(
            db, shot_id="s1", input_payload={"prompt": "x", "frames": 124},
            required_audio=True,
        )
        set_attempt_state(db, aid, "RUNNING")
        set_attempt_state(
            db, aid, "RENDERED",
            artifact_path="/tmp/a.mp4", artifact_sha256="deadbeef",
        )
        mark_qa_flags(db, aid, technical_pass=True, visual_pass=True)
        try:
            select_attempt(db, "s1", 0, aid)
            raise AssertionError("missing audio accepted")
        except ValueError:
            pass
        mark_qa_flags(db, aid, audio_pass=True)
        select_attempt(db, "s1", 0, aid)
        try:
            select_attempt(db, "s1", 0, aid)
            raise AssertionError("stale revision accepted")
        except RuntimeError:
            pass
        ensure_shot(db, "s2", parent_shot_id="s1")
        child = create_attempt(
            db, shot_id="s2", input_payload={"prompt": "y"}, parent_attempt_id=aid,
        )
        n = invalidate_descendants(db, "s1")
        assert n >= 1
        st = db.execute(
            "SELECT state FROM attempts WHERE attempt_id=?", (child,)
        ).fetchone()["state"]
        assert st == "INVALIDATED"
        view = export_progress_view(db)
        assert view["clips"]["s1"]["verified"] is True

    class Stub:
        def __init__(self):
            self.ops = []
        def cancel_prompt(self, pid):
            self.ops.append(("cancel", pid))
        def reconcile(self, prompt_id=None):
            self.ops.append(("reconcile", prompt_id))
        def release_lease(self, reason=""):
            self.ops.append(("release", reason))

    s = Stub()
    tr = release_gpu_lease(s, prompt_id="p1", attempt_id="a1")
    assert tr["cancelled"] and tr["reconciled"] and tr["lease_released"]
    print("PASS: production_store self_test")


if __name__ == "__main__":
    self_test()
