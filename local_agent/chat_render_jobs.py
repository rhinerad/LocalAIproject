#!/usr/bin/env python3
"""Turn the latest complete prompt set and referenced assets in one chat into a job.

This closes the gap between a conversational prompt-writing workflow and the
fixed generic batch runner.  It deliberately copies source files into a fresh,
timestamped job directory: original uploads and reference clips are never moved,
renamed, or overwritten.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
JOBS = HERE / "render_jobs"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
_PATH_RE = re.compile(r"[A-Za-z]:\\[^\r\n<>\"|?*]+")
_LOCAL_PATH_RE = re.compile(r"^local path:\s*(.+?)\s*$", re.M | re.I)
_PROMPT_BLOCK_RE = re.compile(
    r"```[^\n]*\n(?P<body>subject_definitions:\s*.*?)(?:\n```)", re.I | re.S)


class ChatRenderError(RuntimeError):
    pass


def _natural_key(path: Path) -> list[object]:
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", path.name)]


def _existing_path(value: str) -> Path | None:
    # A pasted Windows path in prose often ends before two spaces and the next
    # sentence (the original chat uses exactly that form). Preserve ordinary
    # single spaces inside valid Windows folder names.
    cleaned = re.split(r"\s{2,}", value.strip(), maxsplit=1)[0]
    cleaned = cleaned.strip("`'\"").rstrip(".,;:")
    try:
        path = Path(cleaned)
    except (TypeError, ValueError):
        return None
    return path if path.exists() else None


def _latest_prompt_blocks(messages: list[dict]) -> tuple[list[str], int]:
    """Use the newest assistant response containing complete H3-style blocks."""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("role") != "assistant":
            continue
        blocks = [match.group("body").strip()
                  for match in _PROMPT_BLOCK_RE.finditer(str(message.get("content", "")))]
        if blocks:
            return blocks, index
    raise ChatRenderError("this chat has no complete fenced H3 prompt set to render")


def _normalise_legacy_prompt(text: str) -> str:
    """Map the chat's former zero-based notation to native H3 reference tags."""
    text = re.sub(r"<Image\s+0>", "<Picture 1>", text, flags=re.I)
    text = re.sub(r"<Image\s+1>", "<Picture 2>", text, flags=re.I)
    text = re.sub(r"<Image\s+2>", "<Picture 3>", text, flags=re.I)
    # The batch runner owns the one-based Video 1 binding and injects its motion
    # retention text. Remove old arbitrary per-prompt video tags, which cannot
    # correspond to the one video socket the installed node actually exposes.
    text = re.sub(r"\s*,?\s*<Video\s+\d+>\s*\([^\n)]*\)", "", text, flags=re.I)
    text = re.sub(r"<Video\s+\d+>", "motion reference", text, flags=re.I)

    # Old local-agent outputs used picture tags without declarations. The native
    # validator requires them in subject_definitions. Add only missing entries;
    # do not rewrite creative content.
    declared = {int(value) for value in re.findall(r"<Picture\s+(\d+)>", text.split("summary:", 1)[0], re.I)}
    used = {int(value) for value in re.findall(r"<Picture\s+(\d+)>", text, re.I)}
    missing = sorted(used - declared)
    if missing:
        lines = []
        labels = {1: "character appearance reference", 2: "setting reference", 3: "additional appearance reference"}
        for number in missing:
            lines.append(f"  <Picture {number}> is the {labels.get(number, 'appearance reference')}.")
        marker = "\nsummary:"
        if marker not in text:
            raise ChatRenderError("a captured prompt is missing summary:")
        text = text.replace(marker, "\n" + "\n".join(lines) + marker, 1)
    return text.strip() + "\n"


def _paths_before(messages: list[dict], end_index: int) -> tuple[list[Path], list[Path]]:
    images: list[Path] = []
    video_dirs: list[Path] = []
    seen_images: set[Path] = set()
    seen_dirs: set[Path] = set()
    for message in messages[:end_index + 1]:
        content = str(message.get("content", ""))
        for raw in _LOCAL_PATH_RE.findall(content):
            path = _existing_path(raw)
            if path and path.is_file() and path.suffix.lower() in IMAGE_EXTS and path not in seen_images:
                images.append(path)
                seen_images.add(path)
        for raw in _PATH_RE.findall(content):
            path = _existing_path(raw)
            if path and path.is_dir() and path not in seen_dirs:
                direct_videos = [p for p in path.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
                if direct_videos:
                    video_dirs.append(path)
                    seen_dirs.add(path)
    return images, video_dirs


def prepare_from_chat(conversation_id: str, *, jobs: Path = JOBS) -> dict:
    """Create one non-overwriting batch job from the latest complete chat prompt set."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,40}", str(conversation_id or "")):
        raise ChatRenderError("a valid desktop conversation is required")
    import store
    conv = store.load(conversation_id)
    if not conv:
        raise ChatRenderError("the current conversation could not be loaded")
    messages = list(conv.get("messages") or [])
    blocks, source_index = _latest_prompt_blocks(messages)
    images, video_dirs = _paths_before(messages, source_index)
    if len(images) < 2:
        raise ChatRenderError("the prompt set needs two earlier attached images (character and setting)")
    if not video_dirs:
        raise ChatRenderError("the chat contains no earlier source-video chunk folder")
    videos = sorted((p for p in video_dirs[0].iterdir()
                     if p.is_file() and p.suffix.lower() in VIDEO_EXTS), key=_natural_key)
    if len(videos) < len(blocks):
        raise ChatRenderError(f"the source-video folder has {len(videos)} clips for {len(blocks)} prompts")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    job = jobs / conversation_id / f"render_{stamp}"
    suffix = 2
    while job.exists():
        job = jobs / conversation_id / f"render_{stamp}_{suffix:02d}"
        suffix += 1
    prompts_dir = job / "prompts"
    video_dir = job / "video_refs"
    img0_dir = job / "img0"
    img1_dir = job / "img1"
    for directory in (prompts_dir, video_dir, img0_dir, img1_dir):
        directory.mkdir(parents=True, exist_ok=False)

    # Keep only complete drafts that satisfy the same validator the runner will
    # use after it injects the real `<Video 1>` motion lock. A model response can
    # be cut off mid-code-fence; one incomplete trailing draft must not prevent
    # the preceding valid prompts from being rendered.
    sys_path = str(ROOT / "work")
    import sys
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from batch_render_folder import assemble_prompt
    from validate_h3_prompt import validate
    normalised: list[str] = []
    skipped: list[dict] = []
    for index, block in enumerate(blocks, 1):
        prompt = _normalise_legacy_prompt(block)
        report = validate(assemble_prompt(prompt, 2, True), f"chat_prompt_{index:04d}")
        if report.ok:
            normalised.append(prompt)
        else:
            skipped.append({"prompt": index, "errors": report.errors})
    if not normalised:
        raise ChatRenderError("the latest chat prompt set has no complete valid prompts")
    for index, prompt in enumerate(normalised, 1):
        (prompts_dir / f"{index:04d}.txt").write_text(prompt, encoding="utf8")
    shutil.copy2(images[0], img0_dir / ("character" + images[0].suffix.lower()))
    shutil.copy2(images[1], img1_dir / ("setting" + images[1].suffix.lower()))
    for index, video in enumerate(videos[:len(normalised)], 1):
        shutil.copy2(video, video_dir / f"{index:04d}{video.suffix.lower()}")

    provenance = {
        "conversation_id": conversation_id,
        "prompt_message_index": source_index,
        "prompt_count": len(normalised),
        "skipped_incomplete_or_invalid_prompts": skipped,
        "character_image": str(images[0]),
        "setting_image": str(images[1]),
        "video_source_folder": str(video_dirs[0]),
        "video_count": len(normalised),
        "created_at": time.time(),
        "immutable_sources": True,
    }
    (job / "chat_render_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf8")
    return {"job_folder": str(job), "prompt_count": len(normalised), "provenance": provenance}
