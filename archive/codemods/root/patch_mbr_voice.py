from pathlib import Path
import sys
root = Path(sys.argv[1])
path = root / "master_batch_runner.py"
text = path.read_text(encoding="utf-8")
if "native_voice_continuity" in text and "require_canonical_voices_for_shot" in text:
    print("already wired")
    raise SystemExit(0)

boot = '''
try:
    import native_voice_continuity as _nvc
    _HAS_NATIVE_VOICE = True
except Exception:  # pragma: no cover
    _HAS_NATIVE_VOICE = False

'''
# insert after production_store import block if present, else after imports
if "import production_store" in text or "from production_store" in text:
    # append after first production_store related import section end — simplest: after RUNNER_VERSION if exists
    if "RUNNER_VERSION" in text:
        text = text.replace(
            "RUNNER_VERSION",
            "RUNNER_VERSION",
            1,
        )
    # insert near top after future annotations / imports: find first blank line after imports
    lines = text.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines[:80]):
        if line.startswith("import ") or line.startswith("from ") or line.startswith("#!/") or line.startswith('"""') or line.startswith("from __future__"):
            insert_at = i + 1
    # find end of import block
    i = 0
    while i < len(lines) and (lines[i].startswith("#") or lines[i].startswith("\"\"\"") or lines[i].startswith("from __future__") or lines[i].strip()=="" or lines[i].startswith("import ") or lines[i].startswith("from ") or lines[i].startswith("#!")):
        # crude: stop after we've seen imports and hit a non-import non-empty non-doc
        i += 1
        if i > 5 and lines[i-1].strip() == "" and not (lines[i].startswith("import ") or lines[i].startswith("from ")):
            break
    # better approach: after `_HAS_STORE` definition if any
    joined = "".join(lines)
    if "_HAS_STORE" in joined:
        text = joined.replace(
            "_HAS_STORE = True",
            "_HAS_STORE = True\n" + boot + "_HAS_NATIVE_VOICE = _HAS_NATIVE_VOICE  # noqa: F405",
            1,
        )
        # that may be wrong if HAS_STORE false branch — do cleaner:
        text = path.read_text(encoding="utf-8")

# Cleaner: append helper function and call site
helper = '''

def enforce_native_voice_gate(*, db, job_id: str, clip_id: str, clip: dict, all_clips_dialogue: dict | None = None) -> None:
    """Fail closed for dependent shots missing canonical MiniMax voices.

    Enabled when db is present and clip audio mode is native / dialogue-bearing.
    """
    if not _HAS_NATIVE_VOICE or db is None:
        return
    mode = str(clip.get("audio_mode") or clip.get("shot_audio_mode") or "").lower()
    dialogue = clip_dialogue_payload(clip) if "clip_dialogue_payload" in globals() else (clip.get("dialogue") or [])
    if not dialogue and mode not in {"native_h3_audio", "visible_dialogue", "narration_over_picture"}:
        return
    lines = dialogue if isinstance(dialogue, list) else []
    # normalize
    norm = []
    for item in lines:
        if isinstance(item, dict):
            norm.append(item)
        elif isinstance(item, str) and item.strip():
            norm.append({"speaker_id": "UNKNOWN", "text": item})
    if not norm:
        return
    _nvc.require_canonical_voices_for_shot(
        db,
        job_id=str(job_id),
        shot_id=str(clip_id),
        dialogue_lines=norm,
        shot_dialogue_index=all_clips_dialogue,
    )

'''

# Ensure import
if "import native_voice_continuity as _nvc" not in text:
    # place after sys.path / root setup if any
    anchor = "import production_store as ps"
    if anchor in text:
        text = text.replace(anchor, anchor + "\ntry:\n    import native_voice_continuity as _nvc\n    _HAS_NATIVE_VOICE = True\nexcept Exception:\n    _HAS_NATIVE_VOICE = False\n", 1)
    else:
        text = "try:\n    import native_voice_continuity as _nvc\n    _HAS_NATIVE_VOICE = True\nexcept Exception:\n    _HAS_NATIVE_VOICE = False\n\n" + text

if "def enforce_native_voice_gate" not in text:
    # insert before def run_clip
    text = text.replace("\ndef run_clip(", "\n" + helper + "\ndef run_clip(", 1)

call = '''
    # Native MiniMax voice continuity gate (per-character canonical refs).
    if db is not None:
        job_key = str(getattr(args, "job_id", None) or task_dir.name)
        try:
            enforce_native_voice_gate(db=db, job_id=job_key, clip_id=clip_id, clip=clip)
        except Exception as _voice_exc:
            print(f"[voice-gate] {clip_id}: {_voice_exc}", flush=True)
            mark_clip(progress, clip_id, state="BLOCKED_VOICE", error=str(_voice_exc))
            return False
'''

if "[voice-gate]" not in text:
    # after db = getattr...
    needle = "db = getattr(args, \"_production_db\", None)\n"
    if needle in text:
        text = text.replace(needle, needle + call, 1)
    else:
        raise SystemExit("could not find db getattr hook")

path.write_text(text, encoding="utf-8")
print("wired master_batch_runner native voice gate")
