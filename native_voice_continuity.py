#!/usr/bin/env python3
"""Native per-character MiniMax voice continuity (no F5/Fish substitution)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

CANONICAL = "CANONICAL"
CANDIDATE = "CANDIDATE"
REJECTED = "REJECTED"

DDL = """
CREATE TABLE IF NOT EXISTS voice_candidates (
  candidate_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  character_id TEXT NOT NULL,
  bootstrap_shot_id TEXT NOT NULL,
  bootstrap_attempt_id TEXT NOT NULL,
  source_audio_hash TEXT NOT NULL,
  segment_start_sample INTEGER NOT NULL,
  segment_end_sample INTEGER NOT NULL,
  reference_audio_path TEXT NOT NULL,
  reference_audio_hash TEXT NOT NULL,
  exact_reference_transcript TEXT NOT NULL,
  selection_status TEXT NOT NULL,
  qa_evidence_json TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS voice_canonical (
  job_id TEXT NOT NULL,
  character_id TEXT NOT NULL,
  voice_version TEXT NOT NULL,
  bootstrap_shot_id TEXT NOT NULL,
  bootstrap_attempt_id TEXT NOT NULL,
  source_audio_hash TEXT NOT NULL,
  segment_start_sample INTEGER NOT NULL,
  segment_end_sample INTEGER NOT NULL,
  reference_audio_path TEXT NOT NULL,
  reference_audio_hash TEXT NOT NULL,
  exact_reference_transcript TEXT NOT NULL,
  selection_status TEXT NOT NULL,
  qa_evidence_json TEXT,
  candidate_id TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (job_id, character_id, voice_version)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_voice_canonical_one_active
  ON voice_canonical(job_id, character_id) WHERE selection_status="CANONICAL";
CREATE INDEX IF NOT EXISTS idx_voice_cand_job_char ON voice_candidates(job_id, character_id);
"""


class NativeVoiceError(RuntimeError):
    pass


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def ensure_voice_schema(db: sqlite3.Connection) -> None:
    db.executescript(DDL)


@dataclass
class CanonicalVoiceRecord:
    job_id: str
    character_id: str
    voice_version: str
    bootstrap_shot_id: str
    bootstrap_attempt_id: str
    source_audio_hash: str
    segment_start_sample: int
    segment_end_sample: int
    reference_audio_path: str
    reference_audio_hash: str
    exact_reference_transcript: str
    selection_status: str
    qa_evidence: dict[str, Any] = field(default_factory=dict)
    candidate_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def first_qualifying_speaking_shots(
    shot_dialogue: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, str]:
    """Return character_id -> first shot_id where they speak (per-character, not global C001)."""
    first: dict[str, str] = {}
    for shot_id in sorted(shot_dialogue.keys()):
        for line in shot_dialogue[shot_id] or []:
            cid = str(line.get("speaker_id") or line.get("character_id") or "").strip()
            text = str(line.get("text") or "").strip()
            if not cid or not text:
                continue
            if cid not in first:
                first[cid] = str(shot_id)
    return first


def bootstrap_dependencies(
    shot_dialogue: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, list[str]]:
    """shot_id -> list of character_ids that must already have canonical voices before this shot."""
    first = first_qualifying_speaking_shots(shot_dialogue)
    bootstrap_shot_for = {cid: sid for cid, sid in first.items()}
    deps: dict[str, list[str]] = {}
    for shot_id, lines in shot_dialogue.items():
        need: list[str] = []
        for line in lines or []:
            cid = str(line.get("speaker_id") or line.get("character_id") or "").strip()
            text = str(line.get("text") or "").strip()
            if not cid or not text:
                continue
            boot = bootstrap_shot_for.get(cid)
            if boot and boot != shot_id:
                if cid not in need:
                    need.append(cid)
        deps[str(shot_id)] = need
    return deps


def assert_not_global_c001_voice(character_id: str, reference_audio_path: str) -> None:
    """Hard rule: non-C001 characters must not reuse a C001_master_voice file."""
    cid = str(character_id).strip()
    name = Path(reference_audio_path).name.lower()
    if cid.upper() not in {"C001", "001", "1"} and "c001_master_voice" in name:
        raise NativeVoiceError(
            f"character {cid} cannot use shared C001_master_voice; bootstrap that character independently"
        )


def reject_extraction_if_unusable(
    *,
    speaker_attribution_ok: bool,
    overlapping_dialogue: bool,
    unusable_noise: bool,
    leaked_music: bool,
    transcript_matches_script: bool,
) -> list[str]:
    reasons: list[str] = []
    if not speaker_attribution_ok:
        reasons.append("ambiguous_speaker_attribution")
    if overlapping_dialogue:
        reasons.append("overlapping_dialogue")
    if unusable_noise:
        reasons.append("unusable_noise")
    if leaked_music:
        reasons.append("leaked_music")
    if not transcript_matches_script:
        reasons.append("transcript_mismatch")
    return reasons


def register_candidate(
    db: sqlite3.Connection,
    *,
    candidate_id: str,
    job_id: str,
    character_id: str,
    bootstrap_shot_id: str,
    bootstrap_attempt_id: str,
    source_audio_path: Path | str,
    segment_start_sample: int,
    segment_end_sample: int,
    reference_audio_path: Path | str,
    exact_reference_transcript: str,
    qa_evidence: Mapping[str, Any] | None = None,
    selection_status: str = CANDIDATE,
) -> dict[str, Any]:
    ensure_voice_schema(db)
    assert_not_global_c001_voice(character_id, str(reference_audio_path))
    if segment_end_sample <= segment_start_sample:
        raise NativeVoiceError("segment_end_sample must be > segment_start_sample")
    src_hash = sha256_file(source_audio_path)
    ref_hash = sha256_file(reference_audio_path)
    transcript = str(exact_reference_transcript or "").strip()
    if not transcript:
        raise NativeVoiceError("exact_reference_transcript required (no filler speech)")
    db.execute(
        "INSERT OR REPLACE INTO voice_candidates(\
            candidate_id, job_id, character_id, bootstrap_shot_id, bootstrap_attempt_id,\
            source_audio_hash, segment_start_sample, segment_end_sample,\
            reference_audio_path, reference_audio_hash, exact_reference_transcript,\
            selection_status, qa_evidence_json, created_at\
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            candidate_id, job_id, character_id, bootstrap_shot_id, bootstrap_attempt_id,
            src_hash, int(segment_start_sample), int(segment_end_sample),
            str(reference_audio_path), ref_hash, transcript,
            selection_status, json.dumps(dict(qa_evidence or {}), sort_keys=True), _now(),
        ),
    )
    return {
        "candidate_id": candidate_id,
        "reference_audio_hash": ref_hash,
        "source_audio_hash": src_hash,
        "selection_status": selection_status,
    }


def promote_canonical(
    db: sqlite3.Connection,
    *,
    job_id: str,
    character_id: str,
    candidate_id: str,
    voice_version: str = "v1",
    allow_replace: bool = False,
) -> CanonicalVoiceRecord:
    """Promote a candidate to immutable canonical. Default: refuse overwrite."""
    ensure_voice_schema(db)
    row = db.execute(
        "SELECT * FROM voice_candidates WHERE candidate_id=?", (candidate_id,)
    ).fetchone()
    if row is None:
        raise NativeVoiceError(f"unknown candidate {candidate_id}")
    if row["job_id"] != job_id or row["character_id"] != character_id:
        raise NativeVoiceError("candidate job/character mismatch")
    if row["selection_status"] == REJECTED:
        raise NativeVoiceError("rejected candidate cannot become canonical")

    existing = db.execute(
        "SELECT voice_version, reference_audio_hash FROM voice_canonical\
         WHERE job_id=? AND character_id=? AND selection_status=?",
        (job_id, character_id, CANONICAL),
    ).fetchone()
    if existing and not allow_replace:
        if existing["reference_audio_hash"] != row["reference_audio_hash"]:
            raise NativeVoiceError(
                "canonical voice already set; refusing recursive replace with later take"
            )
        # idempotent same hash
        voice_version = existing["voice_version"]

    rec = CanonicalVoiceRecord(
        job_id=job_id,
        character_id=character_id,
        voice_version=voice_version,
        bootstrap_shot_id=row["bootstrap_shot_id"],
        bootstrap_attempt_id=row["bootstrap_attempt_id"],
        source_audio_hash=row["source_audio_hash"],
        segment_start_sample=int(row["segment_start_sample"]),
        segment_end_sample=int(row["segment_end_sample"]),
        reference_audio_path=row["reference_audio_path"],
        reference_audio_hash=row["reference_audio_hash"],
        exact_reference_transcript=row["exact_reference_transcript"],
        selection_status=CANONICAL,
        qa_evidence=json.loads(row["qa_evidence_json"] or "{}"),
        candidate_id=candidate_id,
    )
    db.execute(
        "INSERT OR REPLACE INTO voice_canonical(\
            job_id, character_id, voice_version, bootstrap_shot_id, bootstrap_attempt_id,\
            source_audio_hash, segment_start_sample, segment_end_sample,\
            reference_audio_path, reference_audio_hash, exact_reference_transcript,\
            selection_status, qa_evidence_json, candidate_id, created_at\
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            rec.job_id, rec.character_id, rec.voice_version, rec.bootstrap_shot_id,
            rec.bootstrap_attempt_id, rec.source_audio_hash, rec.segment_start_sample,
            rec.segment_end_sample, rec.reference_audio_path, rec.reference_audio_hash,
            rec.exact_reference_transcript, rec.selection_status,
            json.dumps(rec.qa_evidence, sort_keys=True), rec.candidate_id, _now(),
        ),
    )
    db.execute(
        "UPDATE voice_candidates SET selection_status=? WHERE candidate_id=?",
        (CANONICAL, candidate_id),
    )
    return rec


def get_canonical_voice(
    db: sqlite3.Connection, *,
    job_id: str,
    character_id: str,
) -> CanonicalVoiceRecord | None:
    ensure_voice_schema(db)
    row = db.execute(
        "SELECT * FROM voice_canonical WHERE job_id=? AND character_id=? AND selection_status=?\
         ORDER BY created_at DESC LIMIT 1",
        (job_id, character_id, CANONICAL),
    ).fetchone()
    if row is None:
        return None
    return CanonicalVoiceRecord(
        job_id=row["job_id"],
        character_id=row["character_id"],
        voice_version=row["voice_version"],
        bootstrap_shot_id=row["bootstrap_shot_id"],
        bootstrap_attempt_id=row["bootstrap_attempt_id"],
        source_audio_hash=row["source_audio_hash"],
        segment_start_sample=int(row["segment_start_sample"]),
        segment_end_sample=int(row["segment_end_sample"]),
        reference_audio_path=row["reference_audio_path"],
        reference_audio_hash=row["reference_audio_hash"],
        exact_reference_transcript=row["exact_reference_transcript"],
        selection_status=row["selection_status"],
        qa_evidence=json.loads(row["qa_evidence_json"] or "{}"),
        candidate_id=row["candidate_id"],
    )


def require_canonical_voices_for_shot(
    db: sqlite3.Connection,
    *,
    job_id: str,
    shot_id: str,
    dialogue_lines: Iterable[Mapping[str, Any]],
    shot_dialogue_index: Mapping[str, Iterable[Mapping[str, Any]]] | None = None,
) -> list[CanonicalVoiceRecord]:
    """Block dependent shots when a required character has no canonical voice.

    Bootstrap shots (first speaking appearance) are allowed without prior canonical.
    """
    first = {}
    if shot_dialogue_index is not None:
        first = first_qualifying_speaking_shots(shot_dialogue_index)
    needed: list[str] = []
    for line in dialogue_lines or []:
        cid = str(line.get("speaker_id") or line.get("character_id") or "").strip()
        text = str(line.get("text") or "").strip()
        if cid and text and cid not in needed:
            needed.append(cid)
    out: list[CanonicalVoiceRecord] = []
    missing: list[str] = []
    for cid in needed:
        if first.get(cid) == shot_id:
            # this shot is the bootstrap; no prior canonical required
            continue
        rec = get_canonical_voice(db, job_id=job_id, character_id=cid)
        if rec is None:
            missing.append(cid)
        else:
            out.append(rec)
    if missing:
        raise NativeVoiceError(
            f"shot {shot_id} blocked; missing canonical MiniMax voices for: {missing}"
        )
    return out


def assert_projects_isolated(job_a: str, job_b: str) -> None:
    if str(job_a) == str(job_b):
        raise NativeVoiceError("expected distinct job ids for isolation check")


def forbid_tts_fallback(backend: str | None, *,
                       native_required: bool = True) -> None:
    b = str(backend or "").strip().lower()
    if native_required and b in {"f5", "f5-tts", "fish", "fish_audio", "fish-audio"}:
        raise NativeVoiceError(
            f"backend {backend!r} cannot silently replace native MiniMax voice conditioning"
        )
