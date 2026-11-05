from pathlib import Path
p = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent\managed_prompt_pack.py")
t = p.read_text(encoding="utf-8")

# Replace clip header / field regexes to allow inline (double-space separated) packs
old = '''# Clip headers like "#### C001, 0:00-0:10" or "### C069, 11:30-11:40"
_CLIP_HEADER_RE = re.compile(
    r"(?m)^#{2,4}\\s*(C\\d{2,4})\\b[^\\n]*$",
    re.I,
)
_START_FRAME_RE = re.compile(r"(?im)^\\s*Start\\s+Frame\\s*:\\s*(.+)$")
_LAST_FRAME_RE = re.compile(r"(?im)^\\s*Last\\s+Frame\\s*:\\s*(.+)$")
_VIDEO_PROMPT_RE = re.compile(r"(?im)^\\s*Video\\s+Prompt\\s*:\\s*(.+)$")'''

new = '''# Clip headers like "#### C001, 0:00-0:10" (line-start OR inline after spaces).
# Some pastes flatten the pack to a few long lines with "  #### C001  " separators.
_CLIP_HEADER_RE = re.compile(
    r"(?:(?m)^|[ \\t]{2,})#{2,4}\\s*(C\\d{2,4})\\b",
    re.I,
)
_START_FRAME_RE = re.compile(r"(?i)\\bStart\\s+Frame\\s*:\\s*")
_LAST_FRAME_RE = re.compile(r"(?i)\\bLast\\s+Frame\\s*:\\s*")
_VIDEO_PROMPT_RE = re.compile(r"(?i)\\bVideo\\s+Prompt\\s*:\\s*")
_FIELD_STOP_RE = re.compile(
    r"(?i)(?:\\bStart\\s+Frame\\s*:|\\bLast\\s+Frame\\s*:|\\bVideo\\s+Prompt\\s*:|"
    r"(?:(?m)^|[ \\t]{2,})#{2,4}\\s*C\\d{2,4}\\b|\\n\\s*##\\s+)"
)'''

if old not in t:
    raise SystemExit("regex block not found")
t = t.replace(old, new, 1)

# Replace parse_clips body to extract fields with stop markers
old_parse = '''def parse_clips(text: str) -> list[dict]:
    """Split a pack into ordered clip records from #### Cxxx headers."""
    raw = str(text or "")
    matches = list(_CLIP_HEADER_RE.finditer(raw))
    clips: list[dict] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        clip_id = match.group(1).upper()
        # Revised second-half headers may redefine C069+; keep the last body.
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()
        start_m = _START_FRAME_RE.search(body)
        last_m = _LAST_FRAME_RE.search(body)
        video_m = _VIDEO_PROMPT_RE.search(body)
        record = {
            "id": clip_id,
            "header": match.group(0).strip(),
            "start_frame": (start_m.group(1).strip() if start_m else ""),
            "last_frame": (last_m.group(1).strip() if last_m else ""),
            "video_prompt": (video_m.group(1).strip() if video_m else ""),
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
    return clips'''

new_parse = '''def _field_value(body: str, marker_re: re.Pattern[str]) -> str:
    """Return text after a field marker until the next field/header/section."""
    match = marker_re.search(body)
    if not match:
        return ""
    rest = body[match.end():]
    stop = _FIELD_STOP_RE.search(rest)
    value = rest[:stop.start()] if stop else rest
    return " ".join(value.split()).strip()


def parse_clips(text: str) -> list[dict]:
    """Split a pack into ordered clip records from #### Cxxx headers."""
    raw = str(text or "")
    matches = list(_CLIP_HEADER_RE.finditer(raw))
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
    return clips'''

if old_parse not in t:
    raise SystemExit("parse_clips not found")
t = t.replace(old_parse, new_parse, 1)

# Also fix is_prompt_pack to count Start Frame without line anchors
old_det = '''    clip_headers = _CLIP_HEADER_RE.findall(raw)
    start_frames = _START_FRAME_RE.findall(raw)
    video_prompts = _VIDEO_PROMPT_RE.findall(raw)'''
new_det = '''    clip_headers = _CLIP_HEADER_RE.findall(raw)
    start_frames = _START_FRAME_RE.findall(raw)
    video_prompts = _VIDEO_PROMPT_RE.findall(raw)'''
# findall on marker-only regex returns empty strings list - len still works
# Actually marker-only re.findall returns list of empty matches? For pattern with no groups, findall returns full matches.
# _START_FRAME_RE has no capture group now - findall returns list of matched marker strings. Good.

p.write_text(t, encoding="utf-8")
print("updated parsers")
