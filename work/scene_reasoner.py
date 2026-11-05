#!/usr/bin/env python3
"""Resident-LLM shot/scene reasoning: decide model/LoRA and continuity before any GPU render.

Before a still or video shot renders, the resident chat model reads the shot's
prompt text plus this story's recorded shot history, and decides:

  * which still model_profile (and, for stills, which LoRA if any) best
    completes this specific prompt, instead of the operator having to name a
    model profile explicitly, and instead of a single hardcoded "Backrooms
    LoRA only on SDXL" rule;
  * whether this shot continues the immediately preceding scene (chain the
    actual last rendered frame/video) or needs a fresh reference image
    (a scene change, or a character returning after being offscreen, so a
    generated reference protects against character drift).

The decision is recorded to a durable per-story JSONL log, then the resident
model is unloaded (mirroring local_agent/router.py's existing
evict_gpu_residents GPU-eviction discipline) before the caller is allowed to
start a ComfyUI render. A low-confidence or ambiguous read of the prompt never
picks an option silently: it blocks and returns a question for the operator
instead ("Block and ask", per operator instruction).

This module never starts a render and never touches ComfyUI. It only reads
project state (character library, prior decisions) and calls the local
resident chat model through the same Ollama HTTP interface other modules in
this project already use directly (see local_agent/router.py's unload()).
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "outputs" / "stories"
CHARACTER_LIBRARY = STORIES / "character_library.json"
LOCAL_AGENT_DIR = ROOT / "local_agent"

OLLAMA_HOST = "127.0.0.1:11434"
DEFAULT_REASONING_MODEL = "huihui_ai/qwen3-abliterated:8b"
CONFIDENCE_FLOOR = 0.6
HISTORY_DEFAULT_LIMIT = 8
# Optional per-row shot context a caller may include in an explicit history.
HISTORY_CONTEXT_KEYS: tuple[str, ...] = ("camera_mode", "speakers", "shot_summary")

# Kept in sync by hand with work/image_render.py's MODEL_PROFILES keys. That
# module is the single source of truth for what a still render will actually
# accept; this list only has to match its *keys*, not its render defaults.
STILL_MODEL_PROFILES: tuple[str, ...] = (
    "realvisxl", "realpro_flux", "alicemix_sd15", "realisticvision_sd15",
)

CONTINUITY_MODES = ("independent", "identity", "continuous", "morph")
CONTINUITY_SOURCES = ("context_video", "reference_image", "none")

# Environment LoRAs are a short, hand-maintained list (unlike character LoRAs,
# which come from the operator-registered character_library.json). Extend
# this when a new environment gets a dedicated LoRA.
ENVIRONMENT_LORAS: dict[str, dict[str, Any]] = {
    "backrooms": {
        "name": "BacHal_(Background)_(SDXL)_(AD).safetensors",
        "use_when": "SDXL stills set inside the Level 0 Backrooms yellow-wallpaper environment",
        "compatible_profiles": ("realvisxl",),
    },
}


class SceneReasonerError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slug(value: object, label: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value).strip()).strip("-_")
    if not clean or clean in {".", ".."}:
        raise SceneReasonerError(f"{label} must contain letters or numbers")
    return clean[:80]


def _story_dir(story: str) -> Path:
    return STORIES / _slug(story, "story")


def _decision_log_path(story: str) -> Path:
    return _story_dir(story) / "shot_decisions.jsonl"


def load_shot_history(story: str, *, limit: int = HISTORY_DEFAULT_LIMIT) -> list[dict]:
    """Return this story's most recent recorded decisions, oldest first.

    Never raises: a missing or corrupt log is simply "no history yet" — the
    reasoning step must still be able to run for a story's very first shot.
    """
    path = _decision_log_path(story)
    if not path.is_file():
        return []
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows[-max(0, int(limit)):]


def _character_loras() -> list[dict[str, Any]]:
    if not CHARACTER_LIBRARY.is_file():
        return []
    try:
        data = json.loads(CHARACTER_LIBRARY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("characters") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if isinstance(row, dict) and row.get("name"):
            out.append({
                "character": row.get("name"),
                "trigger_word": row.get("trigger_word"),
                "lora_filename": row.get("lora_filename"),
            })
    return out


def available_options() -> dict[str, Any]:
    """Enumerate the model/LoRA choices the reasoning step may pick between."""
    return {
        "still_model_profiles": list(STILL_MODEL_PROFILES),
        "environment_loras": ENVIRONMENT_LORAS,
        "character_loras": _character_loras(),
    }


def _build_prompt(
    story: str,
    shot_id: str,
    prompt_text: str,
    is_video_shot: bool,
    history: list[dict],
    options: dict[str, Any],
) -> str:
    history_lines = []
    for row in history[-HISTORY_DEFAULT_LIMIT:]:
        line = {
            "shot_id": row.get("shot_id"),
            "still_model_profile": row.get("still_model_profile"),
            "loras": row.get("loras"),
            "continuity_mode": row.get("continuity_mode"),
            "continuity_source": row.get("continuity_source"),
            "reference_character_ids": row.get("reference_character_ids"),
            "reasoning": row.get("reasoning"),
        }
        # Caller-supplied shot context (see decide_shot(history=...)). Without
        # it the model is asked whether a character "last appeared earlier
        # than the immediately preceding shot" while seeing only prior
        # decisions, never what those shots contained.
        for key in HISTORY_CONTEXT_KEYS:
            if row.get(key) not in (None, "", []):
                line[key] = row.get(key)
        history_lines.append(json.dumps(line, sort_keys=True))
    history_block = "\n".join(history_lines) if history_lines else "(no prior shots recorded for this story yet)"
    return f"""You are the resident planning model for a local, fully offline image/video
generation pipeline. You are reading ONE shot's prompt before any GPU render
starts. Decide how to render it best, and whether it continues the previous
scene. You are NOT generating an image or video yourself.

Story: {story}
Shot id: {shot_id}
This shot is a video shot: {bool(is_video_shot)}

Shot prompt text (verbatim):
---
{prompt_text.strip()}
---

Recent prior shots in this story, oldest first (JSON lines; empty if none):
{history_block}

Available still model profiles (choose at most one, or null if this is not a
still or the default is clearly fine): {json.dumps(options["still_model_profiles"])}

Available environment LoRAs (name, when to use, which profiles they work
with): {json.dumps(options["environment_loras"], sort_keys=True)}

Available registered character LoRAs (character, trigger word, filename):
{json.dumps(options["character_loras"], sort_keys=True)}

Continuity rules for video shots:
  - "continuity_source": "context_video" means chain the ACTUAL last rendered
    frame/video of the immediately preceding shot as this shot's starting
    point, because the scene has not changed and no character needs a fresh
    reference.
  - "continuity_source": "reference_image" means use a freshly generated (or
    registered) reference image instead of chaining video, because either the
    scene changed, or a character appears in this shot who last appeared
    earlier than the immediately preceding shot (so chaining the last frame
    would risk that character's drifted/wrong appearance). List that
    character's id(s) in "reference_character_ids".
  - "continuity_source": "none" means this is not a continuity-sensitive shot
    (e.g. an independent still).

Respond with ONLY one JSON object, no prose, no markdown fences, matching
exactly this shape:
{{
  "still_model_profile": "<one of the listed profiles, or null>",
  "loras": [{{"name": "<lora filename>", "reason": "<short reason>"}}],
  "continuity_mode": "<independent|identity|continuous|morph, or null if not a video shot>",
  "continuity_source": "<context_video|reference_image|none>",
  "continuity_reason": "<short reason for the continuity_source choice>",
  "reference_character_ids": ["<character id>", "..."],
  "confidence": <number 0.0 to 1.0, your honest confidence in this decision>,
  "needs_operator_input": <true if you are not confident enough to decide safely>,
  "question_for_operator": "<a specific question, required if needs_operator_input is true, empty string otherwise>",
  "reasoning": "<one or two sentences explaining the decision, for the audit log>"
}}

If the prompt is ambiguous about which model, LoRA, or continuity choice fits
best, set "needs_operator_input": true and ask a specific question rather than
guessing. Do not invent a model profile, LoRA filename, or character id that
was not listed above.
"""


def _call_ollama(prompt: str, model: str, *, host: str = OLLAMA_HOST, timeout: float = 120.0) -> str:
    req = urllib.request.Request(
        f"http://{host}/api/generate",
        data=json.dumps({
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2},
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SceneReasonerError(f"resident model call failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SceneReasonerError(f"resident model returned a non-JSON HTTP body: {exc}") from exc
    text = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise SceneReasonerError("resident model returned no text")
    return text


def _parse_decision(raw: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Strictly validate the model's JSON. Never silently defaults a field:

    anything unparseable, missing, or out of the allowed set forces
    needs_operator_input=True instead of picking a value on the model's
    behalf.

    Fix 2026-09-23 (readiness-audit finding 1.5): ``loras`` entries and
    ``reference_character_ids`` were previously accepted as-is (only the
    container type was checked), so an invented LoRA filename or a
    nonexistent character id passed straight through -- including at a
    high model-reported confidence, since neither triggered
    ``forced_operator_input``. Both are now checked against the real
    registries (``available_options()``, the same ones offered to the
    model in its prompt) and any entry that doesn't match forces operator
    review instead of being silently accepted or silently dropped.
    """
    if options is None:
        options = available_options()
    valid_lora_names: set[str] = set()
    env_loras = options.get("environment_loras") if isinstance(options, dict) else None
    if isinstance(env_loras, dict):
        for env in env_loras.values():
            if isinstance(env, dict) and env.get("name"):
                valid_lora_names.add(str(env["name"]))
    valid_character_ids: set[str] = set()
    char_loras = options.get("character_loras") if isinstance(options, dict) else None
    if isinstance(char_loras, list):
        for entry in char_loras:
            if not isinstance(entry, dict):
                continue
            if entry.get("lora_filename"):
                valid_lora_names.add(str(entry["lora_filename"]))
            if entry.get("character"):
                valid_character_ids.add(str(entry["character"]))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "confidence": 0.0,
            "needs_operator_input": True,
            "question_for_operator": (
                "The reasoning model did not return valid JSON; please choose "
                "the model profile/LoRA and continuity for this shot manually."
            ),
            "reasoning": f"unparseable response: {exc}",
            "still_model_profile": None,
            "loras": [],
            "continuity_mode": None,
            "continuity_source": "none",
            "continuity_reason": "",
            "reference_character_ids": [],
            "parse_error": True,
        }
    if not isinstance(data, dict):
        data = {}

    forced_operator_input = False

    try:
        confidence = float(data.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
        forced_operator_input = True
    confidence = max(0.0, min(1.0, confidence))

    still_profile = data.get("still_model_profile")
    if still_profile is not None and still_profile not in STILL_MODEL_PROFILES:
        still_profile = None
        forced_operator_input = True

    continuity_mode = data.get("continuity_mode")
    if continuity_mode is not None and continuity_mode not in CONTINUITY_MODES:
        continuity_mode = None
        forced_operator_input = True

    continuity_source = data.get("continuity_source")
    if continuity_source not in CONTINUITY_SOURCES:
        continuity_source = "none"
        forced_operator_input = True

    loras_raw = data.get("loras")
    loras: list[dict[str, Any]] = []
    if isinstance(loras_raw, list):
        for entry in loras_raw:
            name = entry.get("name") if isinstance(entry, dict) else None
            if not name or str(name) not in valid_lora_names:
                # Invented or unregistered LoRA filename: drop it and force
                # a human to confirm rather than passing it through to a
                # renderer that will fail (or silently ignore it) on an
                # unknown LoRA path.
                forced_operator_input = True
                continue
            loras.append({"name": str(name), "reason": str(entry.get("reason") or "").strip()})
    else:
        forced_operator_input = True

    reference_character_ids_raw = data.get("reference_character_ids")
    reference_character_ids: list[str] = []
    if isinstance(reference_character_ids_raw, list):
        for cid in reference_character_ids_raw:
            cid_str = str(cid)
            if cid_str not in valid_character_ids:
                # Nonexistent character id: same reasoning as an invented
                # LoRA above -- do not silently keep a reference to a
                # character the library doesn't know about.
                forced_operator_input = True
                continue
            reference_character_ids.append(cid_str)
    else:
        forced_operator_input = True

    needs_input = bool(data.get("needs_operator_input")) or forced_operator_input or confidence < CONFIDENCE_FLOOR
    question = str(data.get("question_for_operator") or "").strip()
    if needs_input and not question:
        question = (
            "The reasoning model was not confident enough to decide "
            "automatically for this shot; please confirm the model profile/"
            "LoRA and continuity source yourself."
        )

    return {
        "confidence": confidence,
        "needs_operator_input": needs_input,
        "question_for_operator": question if needs_input else "",
        "reasoning": str(data.get("reasoning") or "").strip(),
        "still_model_profile": still_profile,
        "loras": loras,
        "continuity_mode": continuity_mode,
        "continuity_source": continuity_source,
        "continuity_reason": str(data.get("continuity_reason") or "").strip(),
        "reference_character_ids": reference_character_ids,
        "parse_error": False,
    }


def _default_complete(prompt: str, model: str) -> str:
    return _call_ollama(prompt, model)


def decide_shot(
    *,
    story: str,
    shot_id: str,
    prompt_text: str,
    is_video_shot: bool = False,
    model: str = DEFAULT_REASONING_MODEL,
    complete: Callable[[str, str], str] | None = None,
    history_limit: int = HISTORY_DEFAULT_LIMIT,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Ask the resident model to decide. Does not record or evict anything.

    ``history`` (oldest first) replaces the story's recorded decision log as
    the model's view of prior shots. A caller that knows the true shot order
    (e.g. a prompt pack) should pass it: the append-only log reflects the
    order decisions were *made*, which diverges from story order on resume,
    --force re-runs, or repeated shadow passes.
    """
    if not str(prompt_text or "").strip():
        raise SceneReasonerError("prompt_text is required")
    story_slug = _slug(story, "story")
    shot = str(shot_id or "").strip()
    if not shot:
        raise SceneReasonerError("shot_id is required")
    if history is None:
        history = load_shot_history(story_slug, limit=history_limit)
    else:
        history = [row for row in history if isinstance(row, dict)][-max(0, int(history_limit)):]
    options = available_options()
    built_prompt = _build_prompt(story_slug, shot, prompt_text, is_video_shot, history, options)
    caller = complete or _default_complete
    raw = caller(built_prompt, model)
    decision = _parse_decision(raw, options)
    decision["shot_id"] = shot
    decision["story"] = story_slug
    decision["model_used_for_reasoning"] = model
    decision["decided_at"] = _now()
    decision["is_video_shot"] = bool(is_video_shot)
    return decision


def record_decision(decision: dict[str, Any]) -> Path:
    story = decision.get("story")
    if not story:
        raise SceneReasonerError("decision['story'] is required to record")
    path = _decision_log_path(str(story))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(decision, sort_keys=True) + "\n")
    return path


def evict_reasoning_model() -> dict[str, Any]:
    """Unload every resident GPU chat model, verified via /api/ps.

    Reuses local_agent/router.py's evict_gpu_residents() — the project's
    existing, already-verified GPU-eviction discipline — rather than
    reimplementing unload/verify here. A failure to import or evict is
    returned, never swallowed, so a caller can see the GPU was not actually
    freed before treating a render as safe to start.
    """
    local_agent_dir = str(LOCAL_AGENT_DIR)
    if local_agent_dir not in sys.path:
        sys.path.insert(0, local_agent_dir)
    try:
        import router  # local_agent/router.py
    except Exception as exc:  # pragma: no cover - environment-dependent
        return {"attempted": [], "remaining": None, "verified": False,
                "reason": f"could not import local_agent.router: {exc}"}
    try:
        return router.evict_gpu_residents()
    except Exception as exc:  # pragma: no cover - environment-dependent
        return {"attempted": [], "remaining": None, "verified": False,
                "reason": f"evict_gpu_residents raised: {exc}"}


def _eviction_note(eviction: dict[str, Any] | None, skip_eviction: bool) -> str:
    """Describe what actually happened to the resident model, honestly.

    Fix 2026-09-23 (readiness-audit finding 1.5): the caller-facing note
    previously read "...The reasoning model was unloaded..." unconditionally
    whenever the decision wasn't blocked -- it was never conditioned on
    eviction["verified"], so a failed or unverified eviction was reported
    with the exact same reassuring text as a verified one. This makes the
    wording depend on what evict_reasoning_model() actually reported.
    """
    if skip_eviction:
        return "eviction was skipped by the caller"
    if isinstance(eviction, dict) and eviction.get("verified"):
        return "the reasoning model was unloaded and verified clear of GPU residents"
    reason = ""
    if isinstance(eviction, dict) and eviction.get("reason"):
        reason = f" ({eviction['reason']})"
    return (
        "eviction could NOT be verified" + reason + " -- the GPU may still "
        "hold the reasoning model resident; do not assume it is safe to "
        "start a render until this is confirmed cleared"
    )


def reason_about_shot(
    *,
    story: str,
    shot_id: str,
    prompt_text: str,
    is_video_shot: bool = False,
    model: str = DEFAULT_REASONING_MODEL,
    complete: Callable[[str, str], str] | None = None,
    skip_eviction: bool = False,
    history: list[dict] | None = None,
) -> dict[str, Any]:
    """Decide, then record (only if not blocked), then always unload.

    Never starts a render. When the decision needs operator input, nothing is
    recorded and the caller must not treat this shot as cleared to render;
    the GPU is still evicted either way so a paused, awaiting-operator shot
    does not hold VRAM hostage.

    Fix 2026-09-23 (readiness-audit finding 1.5): decide_shot() (which makes
    the actual network call to the resident model) previously ran outside
    any try/finally, so a raised SceneReasonerError (e.g. a network failure
    mid-call) skipped evict_reasoning_model() entirely, leaving the model
    resident on the GPU. Eviction now always runs -- successful decision,
    blocked decision, or raised exception alike -- unless the caller
    explicitly opted out with skip_eviction.
    """
    decision: dict[str, Any] | None = None
    blocked = False
    log_path: Path | None = None
    eviction: dict[str, Any] | None = None
    try:
        decision = decide_shot(
            story=story, shot_id=shot_id, prompt_text=prompt_text,
            is_video_shot=is_video_shot, model=model, complete=complete,
            history=history,
        )
        blocked = bool(decision["needs_operator_input"])
        if not blocked:
            log_path = record_decision(decision)
    finally:
        if not skip_eviction:
            eviction = evict_reasoning_model()
    # decision is only None here if decide_shot (or record_decision) raised;
    # the finally above has already run eviction, and the exception is now
    # propagating past this function -- nothing below executes in that case.
    eviction_note = _eviction_note(eviction, skip_eviction)
    return {
        "status": "blocked_awaiting_operator" if blocked else "decided",
        "decision": decision,
        "recorded": not blocked,
        "decision_log": str(log_path) if log_path else None,
        "eviction": eviction,
        "note": (
            "Blocked: the reasoning model asked a question instead of "
            "guessing. Nothing was recorded; this shot is not cleared to "
            "render. GPU status: " + eviction_note + "."
            if blocked else
            "Decision recorded. GPU status: " + eviction_note + ". "
            "Confirm the GPU is actually clear before starting any render."
        ),
    }
