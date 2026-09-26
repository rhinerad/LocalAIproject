#!/usr/bin/env python3
"""Managed creative/storyboard prompt-pack tasks.

Large multi-clip packs (e.g. Backrooms 102-clip audition packs) are not
immediate Comfy still-render jobs. This module:

  1. Detects prompt-pack intent (distinct from short CAP_IMAGE still sheets)
  2. Persists the full operator source under runtime/managed_tasks/<cid>/
  3. Parses clips into durable chunk files
  4. Tracks export progress so continue/proceed resumes after compaction
  5. Writes real per-clip output files (not instructions or placeholders)
  6. Keeps render tools gated until the operator explicitly asks to render

Authority for tool execution remains in tools.py / agent.py. This module
never starts ComfyUI, never loads weights, and never touches Equal Shares.
"""
from __future__ import annotations

import json
import hashlib
import importlib.util
import logging
import re
import sys
import time
from pathlib import Path

from atomic_io import atomic_write_text

HERE = Path(__file__).resolve().parent
DIR = HERE / "runtime" / "managed_tasks"
_CID_RE = re.compile(r"[A-Za-z0-9_-]{4,40}$")
_BACKROOMS_COMPILE_PATH = HERE.parent / "backrooms_compile.py"
_LOG = logging.getLogger(__name__)

_compile_module = None
_compile_error: str | None = None


def _load_backrooms_compile():
    """Return the project-root backrooms_compile module, or None.

    It lives one directory above local_agent/, which is not on sys.path in the
    agent process, so a plain import raised ModuleNotFoundError and every pack
    silently fell back to realvisxl. Load it by path and restore sys.path
    afterwards (the module prepends the project root on import).
    """
    global _compile_module, _compile_error
    if _compile_module is not None or _compile_error is not None:
        return _compile_module
    saved_path = list(sys.path)
    try:
        existing = sys.modules.get("backrooms_compile")
        if existing is not None:
            _compile_module = existing
        else:
            spec = importlib.util.spec_from_file_location(
                "backrooms_compile", _BACKROOMS_COMPILE_PATH)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load {_BACKROOMS_COMPILE_PATH}")
            module = importlib.util.module_from_spec(spec)
            sys.modules["backrooms_compile"] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop("backrooms_compile", None)
                raise
            _compile_module = module
    except Exception as exc:
        _compile_error = f"{type(exc).__name__}: {exc}"
        _LOG.warning("backrooms_compile unavailable (%s); EDITOR OVERRIDES "
                     "enforcement falls back to marker detection", _compile_error)
    finally:
        sys.path[:] = saved_path
    return _compile_module


def _compiled_settings(raw: str) -> dict | None:
    module = _load_backrooms_compile()
    if module is None:
        return None
    return module.compile_job_settings(raw).to_dict()


def _source_demands_flux(raw: str) -> bool:
    """Marker check used when backrooms_compile cannot be loaded."""
    return (
        "## EDITOR OVERRIDES" in raw
        or "### 0. Flux" in raw
        or bool(re.search(r"(?i)still-image\s+generator\s+is\s+Flux", raw))
    )

# Clip headers like "#### C001, 0:00-0:10" (line-start OR inline after spaces).
# Some pastes flatten the pack to a few long lines with "  #### C001  " separators.
_CLIP_HEADER_RE = re.compile(
    r"#{2,4}\s*(C\d{2,4})\b",
    re.I,
)
_START_FRAME_RE = re.compile(r"(?i)\bStart\s+Frame\s*:\s*")
_LAST_FRAME_RE = re.compile(r"(?i)\bLast\s+Frame\s*:\s*")
_VIDEO_PROMPT_RE = re.compile(r"(?i)\bVideo\s+Prompt\s*:\s*")
_FIELD_STOP_RE = re.compile(
    r"(?i)(?:\bStart\s+Frame\s*:|\bLast\s+Frame\s*:|\bVideo\s+Prompt\s*:|"
    r"#{2,4}\s*C\d{2,4}\b|\n\s*##\s+)"
)
_PACK_TITLE_RE = re.compile(
    r"\b(?:prompt\s+pack|storyboard\s+pack|audition\s+prompt\s+pack|"
    r"clip\s+prompt\s+pack)\b",
    re.I,
)
_CLIP_COUNT_RE = re.compile(
    r"\b(\d{2,4})\s*clips?\b|\btarget\s+length\s*:\s*\d+\s*minutes?",
    re.I,
)
_EXPLICIT_RENDER_RE = re.compile(
    r"\b(?:render(?:ing)?|comfy(?:ui)?|generate\s+(?:the\s+)?"
    r"(?:stills?|images?|pngs?|photos?)|start\s+(?:the\s+)?"
    r"(?:image\s+)?(?:batch|render)|queue\s+(?:the\s+)?stills?)\b",
    re.I,
)
_PLACEHOLDER_PROMPT_RE = re.compile(
    r"^\s*(?:apple|banana|test|placeholder|lorem\s+ipsum|asdf|foo|bar|"
    r"example\s+prompt|default\s+image)\s*$",
    re.I,
)
_FOLLOW_UP_RE = re.compile(
    r"^\s*(?:continue|proceed|keep\s+going|go\s+ahead|next|resume|"
    r"finish(?:\s+it)?|keep\s+at\s+it)\b",
    re.I,
)


def _task_dir(cid: str) -> Path:
    if not _CID_RE.fullmatch(str(cid or "")):
        raise ValueError(f"bad conversation id {cid!r}")
    return DIR / str(cid)


def is_prompt_pack(text: str | None) -> bool:
    """True for large creative/storyboard packs, not short still sheets."""
    raw = str(text or "")
    if len(raw) < 1500:
        return False
    plain_starts = len(re.findall(r"(?m)^C\d{2,4}\s*[—–-]\s*START FRAME IMAGE", raw))
    if plain_starts >= _plain_header_threshold(raw):
        return True
    clip_headers = _CLIP_HEADER_RE.findall(raw)
    start_frames = _START_FRAME_RE.findall(raw)
    video_prompts = _VIDEO_PROMPT_RE.findall(raw)
    titled = bool(_PACK_TITLE_RE.search(raw))
    count_hint = _CLIP_COUNT_RE.search(raw)
    hinted_n = int(count_hint.group(1)) if count_hint and count_hint.group(1) else 0

    if titled and (len(clip_headers) >= 4 or len(start_frames) >= 4):
        return True
    if len(clip_headers) >= 12 or len(start_frames) >= 12:
        return True
    if (
        len(raw) >= 12000
        and len(start_frames) >= 6
        and len(video_prompts) >= 4
    ):
        return True
    if hinted_n >= 40 and len(start_frames) >= 4 and titled:
        return True
    return False


def is_follow_up(text: str | None) -> bool:
    return bool(_FOLLOW_UP_RE.search(str(text or "")))


def wants_explicit_render(text: str | None) -> bool:
    """True only for a short current-turn render ask — not pack assembly prose."""
    raw = str(text or "")
    if re.fullmatch(r"\s*redner(?:\s+it)?[.!]?\s*", raw, re.I):
        return True
    # Full stills+videos ask may wrap a pack paste; defer to production helper.
    try:
        import prompt_pack_production
        if prompt_pack_production.wants_full_production(raw):
            return True
    except Exception:
        pass
    # Large packs embed lines like "Generate the stills first..."; that is pack
    # content, not an operator instruction to start Comfy on this turn.
    if is_prompt_pack(raw) or len(raw) > 4000:
        return False
    return bool(_EXPLICIT_RENDER_RE.search(raw))


def is_placeholder_prompt(text: str | None) -> bool:
    return bool(_PLACEHOLDER_PROMPT_RE.match(str(text or "").strip()))


def _progress_path(cid: str) -> Path:
    return _task_dir(cid) / "progress.json"


def load_progress(cid: str) -> dict | None:
    try:
        path = _progress_path(cid)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _save_progress(cid: str, progress: dict) -> dict:
    progress["updated"] = time.time()
    path = _progress_path(cid)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(progress, indent=2, ensure_ascii=False))
    return progress


def _field_value(body: str, marker_re: re.Pattern[str]) -> str:
    """Return text after a field marker until the next field/header/section."""
    match = marker_re.search(body)
    if not match:
        return ""
    rest = body[match.end():]
    stop = _FIELD_STOP_RE.search(rest)
    value = rest[:stop.start()] if stop else rest
    return " ".join(value.split()).strip()



_PLAIN_FRAME_HEADER_RE = re.compile(
    r"(?m)^(C\d{2,4})\s*[—–-]\s*(START FRAME IMAGE|LAST FRAME IMAGE|VIDEO(?:\s+PROMPT)?)\b[^\n]*",
    re.I,
)


def _has_merged_title(raw: str) -> bool:
    return "FULLY MERGED" in raw or "CAMERA-LOGIC CORRECTED" in raw


def _plain_header_threshold(raw: str) -> int:
    """Plain 'C001 — START FRAME IMAGE' lines needed to treat text as a pack.

    The title phrase is only a hint: pastes that lose it (and their '###'
    marks) still carry a dozen plain frame headers, which random prose does
    not. With the title, a handful of headers is enough.
    """
    return 4 if _has_merged_title(raw) else 12


def _plain_start_count(matches: list[re.Match[str]]) -> int:
    """START FRAME headers only, so the threshold counts clips, not sections."""
    return sum(1 for m in matches if "START" in m.group(2).upper())


def _parse_fully_merged_plain(raw: str) -> list[dict] | None:
    """Parse packs whose clip headers are plain 'C001 — START FRAME IMAGE' lines."""
    matches = list(_PLAIN_FRAME_HEADER_RE.finditer(raw))
    if _plain_start_count(matches) < _plain_header_threshold(raw):
        return None
    grouped: dict[str, dict] = {}
    controls = raw[:matches[0].start()].strip()
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        heading = match.group(0).strip()
        body = raw[match.end():end].strip()
        clip_id = match.group(1).upper()
        kind = match.group(2).upper()
        record = grouped.setdefault(clip_id, {
            "id": clip_id,
            "header": heading,
            "start_frame": "",
            "last_frame": "",
            "video_prompt": "",
            "body": "",
            "production_instructions": controls,
            "camera_mode": None,
        })
        mode_m = re.search(r"Camera Mode:\s*([A-Za-z]+)", heading, re.I)
        if mode_m:
            record["camera_mode"] = mode_m.group(1).upper()
        if "START FRAME" in kind:
            field = "start_frame"
        elif "LAST FRAME" in kind:
            field = "last_frame"
        else:
            field = "video_prompt"
        if field == "video_prompt":
            # Prefer MiniMax block when present; otherwise take full body until next header.
            marker = re.search(r"(?im)^(?:MiniMax first-last-frame prompt:|integrated_multimodal_description:|Positive prompt:)\s*", body)
            if marker and "minimax" in marker.group(0).lower():
                value = body[marker.end():].strip()
            elif marker and "integrated" in marker.group(0).lower():
                value = body[marker.start():].strip()
            else:
                # Common FULLY MERGED shape: prose after Filename/Model target lines.
                value = body
                # Drop leading metadata lines.
                value = re.sub(r"(?im)^Filename:.*\n?", "", value)
                value = re.sub(r"(?im)^Model target:.*\n?", "", value)
                value = value.strip()
            value = re.split(r"(?m)^(?:SECTION\s+\d+|C\d{2,4}\s*[—–-])", value, maxsplit=1)[0].strip()
        else:
            marker = re.search(r"(?im)^Positive prompt:\s*", body)
            value = body[marker.end():].strip() if marker else ""
            value = re.split(
                r"(?im)^Negative prompt:|^Continuity anchors:|^Filename:|^C\d{2,4}\s*[—–-]|^SECTION\s+\d+",
                value,
                maxsplit=1,
            )[0].strip()
            negative = re.search(
                r"(?ims)^Negative prompt:\s*(.*?)(?=^Continuity anchors:|^C\d{2,4}\s*[—–-]|^SECTION\s+\d+|\Z)",
                body,
            )
            record[field + "_negative"] = negative.group(1).strip() if negative else ""
        record[field] = value
        record["body"] += heading + "\n" + body + "\n\n"
        if not record.get("header") or field == "start_frame":
            record["header"] = heading
    import backrooms_fully_merged_adapter
    settings = _compiled_settings(raw)
    clips = backrooms_fully_merged_adapter.apply(list(grouped.values()), raw, settings=settings)
    return _enrich_compiled_fields(clips, raw, settings)


_APPENDIX_MARKERS = (
    "\n## APPENDIX",
    "\n### Character Bible",
    "\n## Dialogue Tone",
    "\n## Generation Notes",
    "\n## Story Rules",
)
_APPENDIX_HEADING_RE = re.compile(
    r"(?is)\s+#{2,3}\s*(?:APPENDIX|Character Bible|Dialogue Tone|Generation Notes|Story Rules)\b",
)


def _clip_header_starts(raw: str) -> list[int]:
    """Offsets of markdown (### C001) and plain (C001 — START FRAME) clip headers."""
    starts = [match.start() for match in _CLIP_HEADER_RE.finditer(raw)]
    starts.extend(match.start() for match in _PLAIN_FRAME_HEADER_RE.finditer(raw))
    return starts


def _drop_trailing_appendix(raw: str) -> str:
    """Remove a pack appendix that follows the clips.

    Markers are only considered after the last real clip header. A leading
    EDITOR OVERRIDES preamble that mentions Character Bible / Story Rules /
    APPENDIX must not truncate the document before those headers. When no clip
    header is visible yet, leave the text intact.
    """
    starts = _clip_header_starts(raw)
    if not starts:
        return raw
    footer_search_start = max(starts)
    cut: int | None = None
    for marker in _APPENDIX_MARKERS:
        pos = raw.find(marker, footer_search_start)
        if pos >= 0 and (cut is None or pos < cut):
            cut = pos
    footer = _APPENDIX_HEADING_RE.search(raw[footer_search_start:])
    if footer:
        pos = footer_search_start + footer.start()
        if cut is None or pos < cut:
            cut = pos
    if cut is None or cut <= min(starts):
        return raw
    trimmed = raw[:cut].rstrip()
    if not _clip_header_starts(trimmed):
        return raw
    return trimmed


def parse_clips(text: str) -> list[dict]:
    """Split a pack into ordered clip records from #### Cxxx headers."""
    raw = _drop_trailing_appendix(str(text or ""))
    plain = _parse_fully_merged_plain(raw)
    if plain is not None:
        return plain
    matches = list(_CLIP_HEADER_RE.finditer(raw))
    # Frame-first packs repeat each clip in three separate sections. Merge
    # those sections by field; replacing by clip ID loses both image prompts.
    if re.search(r"(?im)^#{2,4}\s*C\d+\s*[—–-]\s*START FRAME IMAGE", raw):
        grouped: dict[str, dict] = {}
        controls = raw[:matches[0].start()].strip() if matches else ""
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
            section = raw[match.end():end].strip()
            heading, _, body = section.partition("\n")
            record = grouped.setdefault(match.group(1).upper(), {
                "id": match.group(1).upper(), "header": match.group(0).strip(),
                "start_frame": "", "last_frame": "", "video_prompt": "",
                "body": "", "production_instructions": controls,
            })
            if "START FRAME IMAGE" in heading.upper():
                field = "start_frame"
            elif "LAST FRAME IMAGE" in heading.upper():
                field = "last_frame"
            elif "VIDEO PROMPT" in heading.upper():
                field = "video_prompt"
            else:
                continue
            if field == "video_prompt":
                marker = re.search(r"(?im)^MiniMax first-last-frame prompt:\s*", body)
                value = body[marker.end():].strip() if marker else ""
                value = re.split(r"(?m)^##\s+", value, maxsplit=1)[0].strip()
            else:
                marker = re.search(r"(?im)^Positive prompt:\s*", body)
                value = body[marker.end():].strip() if marker else ""
                value = re.split(r"(?im)^Negative prompt:|^Continuity anchors:|^##\s+", value, maxsplit=1)[0].strip()
                negative = re.search(r"(?ims)^Negative prompt:\s*(.*?)(?=^Continuity anchors:|^##\s+|\Z)", body)
                record[field + "_negative"] = negative.group(1).strip() if negative else ""
            record[field] = value
            record["body"] += match.group(0) + section + "\n\n"
        if grouped:
            import backrooms_prompt_adapter
            settings = _compiled_settings(raw)
            if settings is None and _source_demands_flux(raw):
                settings = {"still_backend": "flux", "reject_sdxl": True}
            clips = backrooms_prompt_adapter.apply(list(grouped.values()), raw, settings=settings)
            return _enrich_compiled_fields(clips, raw, settings)
    clips: list[dict] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        clip_id = match.group(1).upper()
        # Revised second-half headers may redefine C069+; keep the last body.
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        record = {
            "id": clip_id,
            "header": match.group(0).strip(),
            "start_frame": _field_value(body, _START_FRAME_RE),
            "last_frame": _field_value(body, _LAST_FRAME_RE),
            "video_prompt": _field_value(body, _VIDEO_PROMPT_RE),
            "body": body,
        }
        if clip_id in seen:
            # Replace earlier definition (revised ending supersedes).
            for i, existing in enumerate(clips):
                if existing["id"] == clip_id:
                    clips[i] = record
                    break
        else:
            seen.add(clip_id)
            clips.append(record)
    return _enrich_compiled_fields(clips, raw, _compiled_settings(raw))



def _enrich_compiled_fields(clips: list[dict], source: str, settings: dict | None) -> list[dict]:
    """Attach dialogue_lines / required_audio / duration / aspect after parse."""
    module = _load_backrooms_compile()
    if module is None:
        flux = _source_demands_flux(source) or (
            isinstance(settings, dict) and settings.get("still_backend") == "flux")
        for clip in clips:
            # Visible in every clip JSON so a degraded compile is never silent.
            clip["compile_fallback"] = _compile_error or "backrooms_compile unavailable"
            if flux:
                clip["model_profile"] = "flux"
            clip.setdefault("aspect_ratio", "4:3")
            clip.setdefault("duration_seconds", 10.0)
            vp = str(clip.get("source_video_prompt") or clip.get("video_prompt") or "")
            import re as _re
            lines = []
            for m in _re.finditer(r"<d>\[English\]\s*(.*?)\s*</d>", vp, _re.I | _re.S):
                pre = vp[max(0, m.start() - 80): m.start()]
                speaker = "ENTITY" if _re.search(r"\bentity\b", pre, _re.I) else "ACTOR"
                exact = " ".join(m.group(1).split()).strip()
                lines.append({
                    "speaker_id": speaker, "speaker": speaker,
                    "exact_text": exact, "text": exact,
                    "improvisation_permitted": False, "order": len(lines),
                })
            clip["dialogue_lines"] = lines
            clip["required_audio"] = bool(lines)
        return clips
    settings_obj = module.compile_job_settings(source)
    if isinstance(settings, dict):
        for key, value in settings.items():
            if hasattr(settings_obj, key):
                setattr(settings_obj, key, value)
    if not _source_demands_flux(source):
        # JobSettings defaults to Flux for the Backrooms compile CLI. A pack
        # with no EDITOR OVERRIDES / Flux rule keeps the model it had before
        # this module could load backrooms_compile (unset -> realvisxl).
        settings_obj.still_backend = "unspecified"
        settings_obj.reject_sdxl = False
    errors: list[str] = []
    return [module.enrich_clip(c, settings_obj, compile_errors=errors) for c in clips]


def compile_pack(path: str | Path) -> dict:
    """Optional helper: compile a pack path into settings + enriched clips."""
    module = _load_backrooms_compile()
    if module is None:
        raise RuntimeError(f"backrooms_compile unavailable: {_compile_error}")
    return module.compile_pack(path)


def parse_diagnostics(text: str) -> dict:
    """Why parse_clips() did or did not find clips, from the text alone.

    Stored next to failed ingests so the next unrecognised pack shape can be
    diagnosed from the artifact instead of reverse-engineered from a ledger.
    """
    raw = str(text or "")
    searched = _drop_trailing_appendix(raw)
    plain_matches = list(_PLAIN_FRAME_HEADER_RE.finditer(searched))
    plain = len(plain_matches)
    plain_starts = _plain_start_count(plain_matches)
    markdown = len(_CLIP_HEADER_RE.findall(searched))
    frame_first = len(re.findall(
        r"(?im)^#{2,4}\s*C\d+\s*[—–-]\s*START FRAME IMAGE", searched))
    if plain_starts >= _plain_header_threshold(searched):
        branch = "plain_frame_headers"
    elif frame_first:
        branch = "markdown_frame_first"
    elif markdown:
        branch = "markdown_clip_headers"
    else:
        branch = "none"
    loose = re.findall(r"(?im)^[^\n]{0,12}?\bC\d{2,4}\b[^\n]{0,60}", searched)
    return {
        "chars": len(raw),
        "chars_after_appendix_trim": len(searched),
        "branch": branch,
        "is_prompt_pack": is_prompt_pack(raw),
        "merged_title_present": _has_merged_title(searched),
        "plain_header_threshold": _plain_header_threshold(searched),
        "counts": {
            "plain_frame_headers": plain,
            "plain_start_frame_headers": plain_starts,
            "markdown_clip_headers": markdown,
            "markdown_frame_first_headers": frame_first,
            "start_frame_fields": len(_START_FRAME_RE.findall(searched)),
            "last_frame_fields": len(_LAST_FRAME_RE.findall(searched)),
            "video_prompt_fields": len(_VIDEO_PROMPT_RE.findall(searched)),
            "lines_mentioning_clip_ids": len(loose),
        },
        # Real header lines as they appear, to show the shape nothing matched.
        "sample_clip_id_lines": [line.strip()[:120] for line in loose[:5]],
        "editor_overrides_present": "## EDITOR OVERRIDES" in raw,
        "flux_required": _source_demands_flux(raw),
        "backrooms_compile_loaded": _load_backrooms_compile() is not None,
        "backrooms_compile_error": _compile_error,
        "head": searched[:200],
        "tail": searched[-200:],
    }


def validate_clips(clips: list[dict]) -> None:
    """A count is not completeness: every clip needs three actual prompts."""
    if not clips:
        raise ValueError("No clip prompts were parsed; nothing has been completed")
    for clip in clips:
        for field in ("start_frame", "last_frame", "video_prompt"):
            value = str(clip.get(field) or "").strip()
            if not value or is_placeholder_prompt(value) or re.fullmatch(r"`?[^\n]+\.(?:png|jpg|jpeg)`?(?: Uses)?", value, re.I):
                raise ValueError(f"incomplete {field} for {clip['id']}; supply the actual prompt, not a filename")


def source_path(cid: str) -> Path:
    return _task_dir(cid) / "source.md"


def output_dir(cid: str) -> Path:
    return _task_dir(cid) / "outputs"


def ingest(
    cid: str,
    text: str | None = None,
    *,
    allow_render: bool | None = None,
    title: str | None = None,
) -> dict:
    """Persist full source, parse clips, initialise durable progress."""
    existing = load_progress(cid)
    raw = str(text or "")
    if not raw.strip():
        # Resume path: reload previously saved source.
        sp = source_path(cid)
        if not sp.is_file():
            raise ValueError(
                "no prompt-pack source text and no saved source.md for this chat")
        raw = sp.read_text(encoding="utf-8")
    if not is_prompt_pack(raw) and not (existing and existing.get("kind") == "prompt_pack"):
        # Allow re-ingest of an already-managed pack even if detection is picky
        # on a truncated continue message; first ingest must look like a pack.
        if not existing:
            raise ValueError("text is not a managed creative/storyboard prompt pack")

    task = _task_dir(cid)
    task.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    revision = task / "revisions" / digest if existing and existing.get("source_sha256") != digest else task
    if existing and existing.get("source_sha256") == digest:
        revision = Path(existing["clips_dir"]).parent
    clips_dir = revision / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    out = revision / "outputs"
    out.mkdir(parents=True, exist_ok=True)

    # Keep the operator paste even when parsing fails. The task ledger only
    # stores a short preview, which cannot reconstruct a pack that dies in
    # validate_clips(). Snapshot a previous source.md before replacing it.
    previous = source_path(cid)
    if previous.is_file():
        old = previous.read_text(encoding="utf-8")
        if old != raw:
            snapshot = task / ("source." + hashlib.sha256(old.encode("utf-8")).hexdigest() + ".md")
            if not snapshot.exists():
                atomic_write_text(snapshot, old)
    atomic_write_text(previous, raw)
    try:
        clips = parse_clips(raw)
        validate_clips(clips)
    except Exception as exc:
        failed = task / f"failed_ingest_{digest}.md"
        if not failed.exists():
            atomic_write_text(failed, raw)
        try:
            diag = parse_diagnostics(raw)
            diag["error"] = f"{type(exc).__name__}: {exc}"
            diag_path = task / f"failed_ingest_{digest}.diagnostics.json"
            atomic_write_text(diag_path, json.dumps(diag, indent=2, ensure_ascii=False))
        except Exception:
            raise exc
        counts = diag["counts"]
        raise ValueError(
            f"{exc} [parser branch={diag['branch']}; "
            f"plain_frame_headers={counts['plain_frame_headers']} "
            f"(START {counts['plain_start_frame_headers']}, "
            f"need {diag['plain_header_threshold']}), "
            f"markdown_clip_headers={counts['markdown_clip_headers']}, "
            f"start_frame_fields={counts['start_frame_fields']}; "
            f"diagnostics: {diag_path}]"
        ) from exc
    for clip in clips:
        clip_path = clips_dir / f"{clip['id']}.json"
        atomic_write_text(clip_path, json.dumps(clip, indent=2, ensure_ascii=False))

    render_flag = bool(allow_render) if allow_render is not None else wants_explicit_render(raw)
    # Preserve an earlier explicit render unlock across continue messages.
    if existing and existing.get("allow_render") and allow_render is not False:
        render_flag = True

    progress = {
        "version": 1,
        "source_sha256": digest,
        "kind": "prompt_pack",
        "conversation_id": cid,
        "title": title or (existing.get("title") if existing else None) or _guess_title(raw),
        "status": "exporting",
        "mode": "export",
        "allow_render": render_flag,
        "source_path": str(source_path(cid)),
        "clips_dir": str(clips_dir),
        "output_dir": str(out),
        "progress_path": str(_progress_path(cid)),
        "clip_ids": [c["id"] for c in clips],
        "clip_count": len(clips),
        "model_profiles": _model_profile_counts(clips),
        "exported_ids": list(existing.get("exported_ids", [])) if existing else [],
        "next_index": int(existing.get("next_index", 0)) if existing else 0,
        "created": existing.get("created", time.time()) if existing else time.time(),
    }
    # If clip set changed (new paste), reset export cursor but keep allow_render.
    if existing and (existing.get("clip_ids") != progress["clip_ids"] or existing.get("source_sha256") != digest):
        progress["exported_ids"] = []
        progress["next_index"] = 0
        progress["status"] = "exporting"
    return _save_progress(cid, progress)


def _model_profile_counts(clips: list[dict]) -> dict[str, int]:
    """Still model per clip; missing means initial_frame_job's realvisxl default."""
    counts: dict[str, int] = {}
    for clip in clips:
        key = str(clip.get("model_profile") or "unset(realvisxl)")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _guess_title(text: str) -> str:
    for line in str(text or "").splitlines():
        clean = line.strip().lstrip("#").strip()
        if clean:
            return clean[:160]
    return "prompt_pack"


def export_chunk(cid: str, *, chunk_size: int = 24) -> dict:
    """Write the next chunk of per-clip output files; resume-safe."""
    progress = load_progress(cid)
    if not progress:
        raise ValueError("no managed prompt-pack task for this chat; ingest first")
    clips_dir = Path(progress["clips_dir"])
    out = Path(progress["output_dir"])
    out.mkdir(parents=True, exist_ok=True)
    clip_ids = list(progress.get("clip_ids") or [])
    start = int(progress.get("next_index") or 0)
    end = min(len(clip_ids), start + max(1, int(chunk_size)))
    written: list[dict] = []
    for index in range(start, end):
        clip_id = clip_ids[index]
        clip_path = clips_dir / f"{clip_id}.json"
        if not clip_path.is_file():
            raise ValueError(f"missing parsed clip file {clip_path}")
        clip = json.loads(clip_path.read_text(encoding="utf-8"))
        validate_clips([clip])
        for field in ("start_frame", "last_frame", "video_prompt"):
            if is_placeholder_prompt(clip.get(field)):
                raise ValueError(
                    f"refusing placeholder {field} for {clip_id}: {clip.get(field)!r}")
        md_name = f"{clip_id}.md"
        md_path = out / md_name
        body = (
            f"# {clip_id}\n\n"
            f"## Production instructions (editor overrides take priority)\n{clip.get('production_instructions', '')}\n\n"
            f"{clip.get('header', '')}\n\n"
            f"## Start Frame\n{clip.get('start_frame', '')}\n\n"
            f"## Last Frame\n{clip.get('last_frame', '')}\n\n"
            f"## Video Prompt\n{clip.get('video_prompt', '')}\n\n"
            f"## Full Body\n{clip.get('body', '')}\n"
        )
        atomic_write_text(md_path, body)
        json_out = out / f"{clip_id}.json"
        atomic_write_text(json_out, json.dumps(clip, indent=2, ensure_ascii=False))
        written.append({
            "id": clip_id,
            "md": str(md_path),
            "json": str(json_out),
        })
    exported = list(progress.get("exported_ids") or [])
    for item in written:
        if item["id"] not in exported:
            exported.append(item["id"])
    progress["exported_ids"] = exported
    progress["next_index"] = end
    progress["last_chunk"] = {
        "from_index": start,
        "to_index": end,
        "written": written,
    }
    if end >= len(clip_ids):
        progress["status"] = "exported"
        progress["mode"] = "exported"
        # Index of all outputs for operators / continue.
        index = {
            "clip_count": len(clip_ids),
            "clips": exported,
            "source_path": progress.get("source_path"),
            "output_dir": str(out),
        }
        atomic_write_text(out / "INDEX.json", json.dumps(index, indent=2, ensure_ascii=False))
    else:
        progress["status"] = "exporting"
        progress["mode"] = "export"
    _save_progress(cid, progress)
    return {
        "conversation_id": cid,
        "status": progress["status"],
        "clip_count": len(clip_ids),
        "exported_count": len(exported),
        "next_index": progress["next_index"],
        "remaining": max(0, len(clip_ids) - end),
        "source_path": progress.get("source_path"),
        "output_dir": str(out),
        "progress_path": progress.get("progress_path"),
        "allow_render": bool(progress.get("allow_render")),
        "written": written,
        "mode": progress.get("mode"),
    }


def export_all(cid: str, *, chunk_size: int = 24) -> dict:
    """Export every remaining clip, chunking for durable progress."""
    last: dict = {}
    while True:
        last = export_chunk(cid, chunk_size=chunk_size)
        if last.get("remaining", 0) <= 0:
            return last


def render_allowed(cid: str, operator_text: str | None = None) -> tuple[bool, str]:
    """Whether render_story_image* may run for this chat's pack task."""
    progress = load_progress(cid)
    if not progress or progress.get("kind") != "prompt_pack":
        return True, "no active prompt-pack gate"
    if operator_text and wants_explicit_render(operator_text):
        progress["allow_render"] = True
        progress["mode"] = "render_unlocked"
        _save_progress(cid, progress)
        return True, "operator explicitly requested rendering"
    if progress.get("allow_render"):
        return True, "prompt-pack render previously unlocked"
    return False, (
        "managed prompt-pack task is in dry-run/export mode; "
        "export clip files first. Rendering stays blocked until the operator "
        "explicitly asks to render stills/images (not implied by the pack paste alone)."
    )


def active_source_path(cid: str) -> str | None:
    progress = load_progress(cid)
    if not progress:
        return None
    path = progress.get("source_path")
    return str(path) if path else None


def prompt_block(cid: str) -> str:
    """Compact trusted pack state for the model after compaction."""
    progress = load_progress(cid)
    if not progress or progress.get("kind") != "prompt_pack":
        return ""
    return (
        "Trusted managed prompt-pack task (operator-visible).\n"
        f"Title: {progress.get('title', '')}\n"
        f"Status: {progress.get('status')}  mode={progress.get('mode')}\n"
        f"Clips: {len(progress.get('exported_ids') or [])} / "
        f"{progress.get('clip_count', 0)} exported\n"
        f"Source file: {progress.get('source_path')}\n"
        f"Output folder: {progress.get('output_dir')}\n"
        f"Progress file: {progress.get('progress_path')}\n"
        f"Render allowed: {bool(progress.get('allow_render'))}\n"
        "Do not invent placeholder prompts (apple/test/default). "
        "Do not call Equal Shares/H3 tools. "
        "Do not call render_story_image* unless Render allowed is true. "
        "On continue/proceed, resume from progress (do not ask the operator to re-paste)."
    )


def has_incomplete_export(cid: str) -> bool:
    progress = load_progress(cid)
    if not progress or progress.get("kind") != "prompt_pack":
        return False
    return int(progress.get("next_index") or 0) < int(progress.get("clip_count") or 0)


def initial_frame_job(cid: str) -> dict:
    """Build the first review anchor from persisted, complete prompt data."""
    progress = load_progress(cid)
    if not progress or has_incomplete_export(cid):
        raise ValueError("Finish exporting the prompt pack before rendering its review anchor")
    clip_id = progress['clip_ids'][0]
    clip = json.loads((Path(progress['clips_dir']) / (clip_id + '.json')).read_text(encoding='utf-8'))
    validate_clips([clip])
    job = {
        'story': f"pack_{cid}_{progress.get('source_sha256', 'legacy')[:8]}_{clip_id.lower()}_start",
        'prompt': clip['start_frame'], 'negative': clip.get('start_frame_negative', ''),
        'model_profile': clip.get('model_profile', 'realvisxl'),
        'width': 1024, 'height': 768, 'seed': 1,
    }
    if clip.get('editor_overrides_applied'):
        job['prompt'] = ('(Wide full-body composition, entire actor visible from head to both shoes:1.25), '
                         '(taped X performance mark on the floor directly beneath his shoes:1.25), '
                         'generous visible floor below his feet, camera several meters away. '
                         '(Faded medium-gray T-shirt under open olive-green overshirt:1.25), '
                         'dark straight-leg jeans, worn white sneakers, both hands visible at his sides, '
                         'digital watch on left wrist. ' + job['prompt'])
        job['negative'] += ', cropped feet, cropped legs, close-up portrait, hands in pockets, white T-shirt, light blue jeans'
    return job


def anchor_receipt_path(cid: str) -> Path:
    progress = load_progress(cid)
    return Path(progress['output_dir']).parent / 'review_anchor_receipt.json'


def record_anchor_receipt(cid: str, result: str) -> None:
    try:
        data = json.loads(result)
    except (ValueError, TypeError):
        return
    if data.get('started') and data.get('pid'):
        receipt = anchor_receipt_path(cid)
        if receipt.exists():
            previous = receipt.read_text(encoding='utf-8')
            snapshot = receipt.with_name('review_anchor_receipt.' + hashlib.sha256(previous.encode()).hexdigest() + '.json')
            if not snapshot.exists():
                atomic_write_text(snapshot, previous)
        atomic_write_text(anchor_receipt_path(cid), json.dumps(data, indent=2))
