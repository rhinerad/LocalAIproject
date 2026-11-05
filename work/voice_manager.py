"""Voice cloning and human-in-the-loop approval for Equal Shares.

PURPOSE
    Give every speaking character one consistent voice for the whole film, by
    cloning from audio the pipeline itself produced, with a mandatory human
    approval gate before any cloned voice is used downstream.

WHY THE DESIGN DEVIATES FROM "ONE FIRST-APPEARANCE CLIP PER CHARACTER"
    The MiniMax clone endpoint requires a reference sample of at least 10
    seconds. Measured against this script:

         6 of 18 characters  have one take that clears 10 s on its own
        12 of 18             do not, including 8 whose entire film dialogue is
                             shorter than 10 s (Male Visitor Two has 2.0 s)

    A sample must come from a SINGLE take: H3 re-derives a voice on every clip,
    so concatenating takes would splice two different-sounding performances and
    teach the clone an average of both. Characters without one long enough take
    get a throwaway VOX clip -- them speaking filler for fifteen seconds, using
    their own approved anchor frame -- which becomes their reference sample and
    is never part of the edit.

STATE
    All persistent state lives under outputs/equal_shares/:
        voices/<character>/reference_sample.wav   concatenated, normalised
        voices/<character>/sources/*.wav          the per-clip pieces
        runtime/voice_approval_gate.json          the approval gate
        runtime/render_priority.json              clips to render first

    render_queue_owner.json is deliberately NOT touched. That file is the
    single-owner mutex for the GPU; overloading it with queue ordering would
    couple two unrelated concerns and risk the one lock that prevents two
    backends running at once.

USAGE
    python work/voice_manager.py plan
    python work/voice_manager.py extract --character Narrator
    python work/voice_manager.py extract --all
    python work/voice_manager.py review
    python work/voice_manager.py approve --character Narrator
    python work/voice_manager.py approve --all
    python work/voice_manager.py reroll --character Kent --reason "too nasal"
    python work/voice_manager.py gate
    python work/voice_manager.py clone --character Narrator
    python work/voice_manager.py synthesize --clip 02B
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from typing import Any

# --------------------------------------------------------------------------- paths

PROJECT = os.path.join("outputs", "equal_shares")
CONFIG = os.path.join(PROJECT, "story_config.json")
MANIFEST = os.path.join(PROJECT, "manifest.json")
VOICES = os.path.join(PROJECT, "voices")
RUNTIME = os.path.join(PROJECT, "runtime")
GATE = os.path.join(RUNTIME, "voice_approval_gate.json")
PRIORITY = os.path.join(RUNTIME, "render_priority.json")
DIALOGUE_MANIFEST = os.path.join(PROJECT, "audio", "dialogue_manifest.json")
STORY_ROOT = "A:/Users/rhine/ComfyUI-Shared/output/story"

MIN_SAMPLE_SECONDS = 10.0     # MiniMax clone API floor
MAX_SAMPLE_SECONDS = 300.0    # MiniMax clone API ceiling
TARGET_SAMPLE_SECONDS = 25.0  # comfortably above the floor without bloat
SAMPLE_RATE = 44100

CLONE_URL = "https://api.minimax.io/v1/voice_clone"
UPLOAD_URL = "https://api.minimax.io/v1/files/upload"
TTS_URL = "https://api.minimax.io/v1/t2a_v2"
CLONE_MODEL = "speech-2.6-hd"


# --------------------------------------------------------------------------- helpers

def _read_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def _write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).strip("_").lower()


def _basename(path: str) -> str:
    """Manifest paths are Windows-style; split on both separators."""
    return path.replace("\\", "/").rstrip("/").split("/")[-1]


def speaker_of(line: str) -> str:
    """'Faith White, calm, looking at Kent: "..."' -> 'Faith White'."""
    return line.split(":")[0].split(",")[0].strip()


# --------------------------------------------------------------------------- planning

def get_first_speaker_clips(story_manifest: str = CONFIG) -> dict[str, dict]:
    """Map each character to the first clip in story order where they speak.

    Returns {character: {clip_id, sequence_order, start, end, seconds, line}}.
    """
    config = _read_json(story_manifest)
    if not config:
        raise FileNotFoundError(f"story config not found: {story_manifest}")

    first: dict[str, dict] = {}
    for clip in sorted(config["clips"], key=lambda c: c["sequence_order"]):
        for timing in clip.get("dialogue_timing") or []:
            name = speaker_of(timing["line"])
            if name in first:
                continue
            first[name] = {
                "clip_id": clip["id"],
                "sequence_order": clip["sequence_order"],
                "start": float(timing["start"]),
                "end": float(timing["end"]),
                "seconds": float(timing["end"]) - float(timing["start"]),
                "line": timing["line"],
            }
    return first


def get_sample_budget(story_manifest: str = CONFIG,
                      target: float = TARGET_SAMPLE_SECONDS) -> dict[str, dict]:
    """Plan how to reach a compliant reference sample for every character.

    Classification:
        single_clip   first speaking clip alone clears MIN_SAMPLE_SECONDS
        needs_concat  several clips must be concatenated to clear it
        insufficient  the whole film does not contain enough speech
    """
    config = _read_json(story_manifest)
    segments: dict[str, list[dict]] = {}
    for clip in sorted(config["clips"], key=lambda c: c["sequence_order"]):
        for timing in clip.get("dialogue_timing") or []:
            name = speaker_of(timing["line"])
            segments.setdefault(name, []).append({
                "clip_id": clip["id"],
                "sequence_order": clip["sequence_order"],
                "start": float(timing["start"]),
                "end": float(timing["end"]),
                "seconds": float(timing["end"]) - float(timing["start"]),
            })

    plan: dict[str, dict] = {}
    for name, segs in segments.items():
        total = sum(s["seconds"] for s in segs)

        # Prefer ONE clip whenever a single clip clears the floor. H3 re-derives a
        # voice per clip, so concatenating takes can splice two different-sounding
        # performances into the reference and teach the clone an average of both.
        # Fewer sources is better, even at the cost of a shorter sample.
        # A reference sample must come from ONE take. H3 re-derives a voice on
        # every clip, so concatenating two takes splices two different-sounding
        # performances and teaches the clone an average of both. If no single
        # take clears the floor, render a throwaway VOX clip for that character
        # long enough to carry the whole sample by itself.
        longest = max(segs, key=lambda s: s["seconds"])
        if longest["seconds"] >= MIN_SAMPLE_SECONDS:
            strategy, chosen = "single_clip", [longest]
        else:
            strategy, chosen = "sample_clip_required", []
        acc = sum(s["seconds"] for s in chosen)

        plan[name] = {
            "strategy": strategy,
            "total_dialogue_seconds": round(total, 2),
            "sample_seconds": round(acc, 2),
            "segments": chosen,
            "required_clips": sorted({s["clip_id"] for s in chosen},
                                     key=lambda cid: next(x["sequence_order"]
                                                          for x in chosen if x["clip_id"] == cid)),
            "line_count": len(segs),
        }
    return plan


def write_priority_queue(plan: dict[str, dict] | None = None,
                         path: str = PRIORITY) -> list[str]:
    """Clips that must render before anything else, in story order.

    The supervisor should consult this file when choosing its next clip. It is
    intentionally separate from render_queue_owner.json, which is the GPU mutex.
    """
    plan = plan or get_sample_budget()

    # Phase 1: throwaway VOX clips for characters with too little film dialogue.
    # Phase 2: the real clips whose audio becomes everyone else's sample.
    # Everything else waits until the voice gate is open.
    vox = [f"{SAMPLE_CLIP_PREFIX}{_slug(n).upper()}"
           for n, e in plan.items() if e["strategy"] == "sample_clip_required"]
    needed: dict[str, int] = {}
    for name, entry in plan.items():
        for seg in entry["segments"]:
            needed.setdefault(seg["clip_id"], seg["sequence_order"])
    story = [cid for cid, _ in sorted(needed.items(), key=lambda kv: kv[1])]
    ordered = sorted(vox) + story

    _write_json(path, {
        "generated_at": _now(),
        "purpose": ("clips that must render before any others, so every character has a "
                    "voice reference sample and cloning can begin"),
        "consumed_by": "work/render_until_complete.py",
        "phase_1_voice_sample_clips": sorted(vox),
        "phase_2_story_clips": story,
        "clips": ordered,
        "note": ("Phase 1 clips are specified in voice_sample_clips.json and are NOT part "
                 "of the edit. Phase 2 clips are real story clips whose audio doubles as "
                 "the voice reference."),
    })
    return ordered


# --------------------------------------------------------------------------- voice-sample clips

SAMPLE_CLIP_SECONDS = 15.0
SAMPLE_CLIP_PREFIX = "VOX_"
SAMPLE_CLIP_SPEC = os.path.join(PROJECT, "voice_sample_clips.json")

# Neutral, in-register filler. Long enough to yield well over ten seconds of
# continuous speech, and deliberately generic so nothing here can be mistaken
# for film dialogue if a clip leaks into the edit.
FILLER_LINES = {
    "default": (
        "Good morning. I hope the day is treating you kindly so far. "
        "There is always more to do than there are hours to do it in, "
        "but we manage, and we look after one another as best we can. "
        "If you need anything at all, you only have to ask, and someone will help."
    ),
    "Terminal voice": (
        "Welcome. Your request has been received and recorded. "
        "Processing your entry now. Please wait while the system confirms your details. "
        "Thank you for your patience. Your transaction is complete. "
        "Have a pleasant day, and remember that every contribution is valued equally."
    ),
}


def generate_sample_clip_specs(plan: dict | None = None,
                               seconds: float = SAMPLE_CLIP_SECONDS,
                               path: str = SAMPLE_CLIP_SPEC) -> list[dict]:
    """Emit throwaway clip specs so short-dialogue characters can be cloned.

    A character with 2 s of dialogue in the whole film can never produce a
    compliant reference sample from the film itself. The fix is to render an
    extra clip of them speaking filler for fifteen seconds, purely to harvest a
    voice sample. These clips are never part of the edit.

    They reuse the character's own first-appearance anchor frame so the face,
    wardrobe and room are the ones already approved.
    """
    plan = plan or get_sample_budget()
    first = get_first_speaker_clips()
    config = _read_json(CONFIG)
    by_id = {c["id"]: c for c in config["clips"]}

    specs = []
    for name, entry in plan.items():
        if entry["strategy"] != "sample_clip_required":
            continue
        source_clip = by_id[first[name]["clip_id"]]
        text = FILLER_LINES.get(name, FILLER_LINES["default"])
        clip_id = f"{SAMPLE_CLIP_PREFIX}{_slug(name).upper()}"
        base = max(5, round(seconds * 24))
        frames = base + (5 - (base % 17)) % 17
        specs.append({
            "id": clip_id,
            "character": name,
            "purpose": "voice reference sample only - never part of the edit",
            "duration": seconds,
            "frames": frames,
            "fps": 24,
            "first_frame": source_clip["first_frame"],
            # Single anchor on purpose. A closing frame would force the take to
            # arrive at a specific pose, which fights thirteen seconds of talking.
            "last_frame": None,
            "seed": 900000 + abs(hash(name)) % 90000,
            "dialogue_timing": [{"start": 1.0, "end": seconds - 1.0,
                                 "line": f"{name}, plain and unhurried: “{text}”"}],
            "prompt": _sample_clip_prompt(name, seconds, source_clip),
            "audio": ("Quiet natural room ambience only. No music, song, score, "
                      "underscore, sting, motif, or transition cue."),
        })

    _write_json(path, {
        "generated_at": _now(),
        "purpose": ("throwaway clips rendered only to harvest a >=10s voice reference "
                    "for characters whose film dialogue is too short to clone from"),
        "never_add_to": ["story_config.json clips array", "manifest.json", "the assembled edit"],
        "output_prefix": "story/VOX_<CHARACTER>/",
        "clips": specs,
    })
    return specs


def _sample_clip_prompt(name: str, seconds: float, source_clip: dict) -> str:
    """A minimal prompt: one person, locked camera, talking to camera."""
    return "\n".join([
        "One continuous unbroken take.",
        "",
        "CAMERA",
        "Locked-off camera. The framing never changes. No pan, tilt, zoom, push, or "
        "reframe. Do not cut.",
        "",
        "REFERENCES",
        "Image 1 is the sole anchor. Hold this framing and this person throughout; there "
        "is no closing frame to reach.",
        "",
        "CAST",
        f"Exactly one person is in this shot for its entire duration: {name}. No one "
        "else appears, enters, or is visible in the background at any time.",
        "",
        "IDENTITY",
        f"{name} keeps the exact face, hair and clothing shown in the opening frame, "
        "identical in the last frame to the first.",
        "",
        "SHOT LIST",
        f"[0-1 s] Held. {name} is still, facing camera, mouth closed.",
        f"[1-{seconds - 1:g} s] {name} speaks the line assigned below, steadily and at an "
        "even pace, facing camera. Small natural head movement only. No gestures, no "
        "walking, no turning away. Mouth movement matches speech throughout.",
        f"[{seconds - 1:g}-{seconds:g} s] Held. Speech ends and the mouth closes.",
        "",
        "DIALOGUE",
        f"{name} is the only person who speaks. The line assigned to this clip is "
        "delivered once, continuously, in the window given.",
        "",
        "DO NOT",
        "Do not cut, dissolve, morph, or change camera angle.",
        "Do not add a person or let anyone enter frame.",
        "Do not change the face, hairstyle, or clothing between the first and last frame.",
        "Do not render text of any kind on any surface.",
        "Do not distort or deform hands, fingers, faces, or limbs.",
        "Do not stop speaking before the end of the assigned window.",
    ])


# --------------------------------------------------------------------------- audio

def _ffprobe_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def extract_reference_audio(video_path: str, output_wav_path: str,
                            start: float | None = None,
                            end: float | None = None,
                            sample_rate: int = SAMPLE_RATE) -> str:
    """Extract a normalised mono WAV from a video, optionally a time window.

    Two-pass EBU R128 loudness normalisation is deliberate: the clone endpoint
    is sensitive to level, and H3's output level varies between clips.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(video_path)
    os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)

    command = ["ffmpeg", "-v", "error", "-y"]
    if start is not None:
        command += ["-ss", f"{max(start - 0.15, 0):.3f}"]
    command += ["-i", video_path]
    if end is not None and start is not None:
        command += ["-t", f"{(end - start) + 0.30:.3f}"]
    command += [
        "-vn",
        "-af", "loudnorm=I=-19:TP=-1.5:LRA=11,highpass=f=70,afftdn=nf=-25",
        "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le",
        output_wav_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(output_wav_path):
        raise RuntimeError(f"ffmpeg failed for {video_path}: {result.stderr.strip()[:400]}")
    return output_wav_path


def _concat_wavs(paths: list[str], output_path: str) -> str:
    """Join WAVs losslessly. They already share format from extraction."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    listfile = output_path + ".txt"
    with open(listfile, "w", encoding="utf-8") as fh:
        for p in paths:
            fh.write(f"file '{os.path.abspath(p)}'\n")
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", listfile, "-c", "copy", output_path],
        capture_output=True, text=True)
    try:
        os.remove(listfile)
    except OSError:
        pass
    if result.returncode != 0:
        raise RuntimeError(f"concat failed: {result.stderr.strip()[:400]}")
    return output_path


def build_reference_sample(character: str, plan: dict | None = None,
                           manifest_path: str = MANIFEST) -> dict:
    """Extract every planned segment for a character and join them."""
    plan = plan or get_sample_budget()
    entry = plan.get(character)
    if entry is None:
        raise KeyError(f"unknown character: {character}")
    if entry["strategy"] == "sample_clip_required":
        slug = _slug(character)
        vox_id = f"{SAMPLE_CLIP_PREFIX}{slug.upper()}"
        vox_dir = os.path.join(STORY_ROOT, vox_id)
        if not os.path.isdir(vox_dir):
            raise ValueError(
                f"{character} has only {entry['total_dialogue_seconds']}s of dialogue in the "
                f"whole film; the clone API needs {MIN_SAMPLE_SECONDS}s. Keep the Kokoro voice.")
        videos = sorted(
            [os.path.join(vox_dir, f) for f in os.listdir(vox_dir)
             if f.startswith("attempt_") and f.endswith(".mp4")],
            key=os.path.getmtime,
        )
        if not videos:
            raise ValueError(
                f"{character}: VOX directory {vox_dir} exists but contains no mp4 files")
        video = videos[-1]
        sample = os.path.join(VOICES, slug, "reference_sample.wav")
        src_dir = os.path.join(VOICES, slug, "sources")
        os.makedirs(src_dir, exist_ok=True)
        extract_reference_audio(video, sample)
        seconds = _ffprobe_duration(sample)
        return {
            "character": character,
            "sample_path": sample.replace("\\", "/"),
            "sample_seconds": round(seconds, 2),
            "source_clips": [vox_id],
            "meets_api_minimum": seconds >= MIN_SAMPLE_SECONDS,
            "extracted_at": _now(),
        }

    manifest = _read_json(manifest_path, {"clips": {}})["clips"]
    slug = _slug(character)
    src_dir = os.path.join(VOICES, slug, "sources")
    pieces, missing = [], []

    for seg in entry["segments"]:
        record = manifest.get(seg["clip_id"], {})
        source = record.get("comfy_source")
        if not source:
            missing.append(seg["clip_id"])
            continue
        video = source if os.path.exists(source) else os.path.join(
            STORY_ROOT, seg["clip_id"], _basename(source))
        if not os.path.exists(video):
            missing.append(seg["clip_id"])
            continue
        out = os.path.join(src_dir, f"{seg['clip_id']}_{seg['start']:g}-{seg['end']:g}.wav")
        extract_reference_audio(video, out, seg["start"], seg["end"])
        pieces.append(out)

    if missing:
        raise RuntimeError(
            f"{character}: these clips are not rendered yet, so no audio exists: {', '.join(missing)}")

    sample = os.path.join(VOICES, slug, "reference_sample.wav")
    if len(pieces) == 1:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", pieces[0], "-c", "copy", sample],
                       check=True)
    else:
        _concat_wavs(pieces, sample)

    seconds = _ffprobe_duration(sample)
    return {
        "character": character,
        "sample_path": sample.replace("\\", "/"),
        "sample_seconds": round(seconds, 2),
        "source_clips": entry["required_clips"],
        "meets_api_minimum": seconds >= MIN_SAMPLE_SECONDS,
        "extracted_at": _now(),
    }


# --------------------------------------------------------------------------- gate

def init_gate(force: bool = False, path: str = GATE) -> dict:
    """Create the approval gate from the plan, preserving existing decisions."""
    plan = get_sample_budget()
    first = get_first_speaker_clips()
    existing = _read_json(path, {}).get("characters", {}) if not force else {}
    kokoro = {s["speaker"]: s.get("voice") for s in
              _read_json(DIALOGUE_MANIFEST, {"segments": []})["segments"]}

    characters = {}
    for name, entry in sorted(plan.items(), key=lambda kv: first[kv[0]]["sequence_order"]):
        prior = existing.get(name, {})
        characters[name] = {
            "character": name,
            "first_speaking_clip": first[name]["clip_id"],
            "first_appearance_seconds": round(first[name]["seconds"], 2),
            "strategy": entry["strategy"],
            "source_clips": ([f"{SAMPLE_CLIP_PREFIX}{_slug(name).upper()}"]
                             if entry["strategy"] == "sample_clip_required"
                             else entry["required_clips"]),
            "planned_sample_seconds": entry["sample_seconds"],
            "total_dialogue_seconds": entry["total_dialogue_seconds"],
            "sample_path": prior.get("sample_path",
                                     os.path.join(VOICES, _slug(name),
                                                  "reference_sample.wav").replace("\\", "/")),
            "sample_seconds": prior.get("sample_seconds"),
            "extracted_at": prior.get("extracted_at"),
            "approved": prior.get("approved", False),
            "needs_reroll": prior.get("needs_reroll", False),
            "status": prior.get("status", "blocked" if entry["strategy"] == "insufficient" else "pending"),
            "fallback_voice": kokoro.get(name),
            "reviewer_note": prior.get("reviewer_note", ""),
            "reviewed_at": prior.get("reviewed_at"),
            "cloned_voice_id": prior.get("cloned_voice_id"),
        }

    payload = {
        "schema_version": 1,
        "generated_at": _now(),
        "api_minimum_seconds": MIN_SAMPLE_SECONDS,
        "gate_open": False,
        "policy": ("Downstream dialogue generation is blocked until every character here is "
                   "approved. Characters whose strategy is 'sample_clip_required' are approved "
                   "against a throwaway VOX clip rendered solely to harvest their voice; that "
                   "clip is never part of the edit."),
        "characters": characters,
    }
    payload["gate_open"] = _gate_open(payload)
    _write_json(path, payload)
    return payload


def _gate_open(payload: dict) -> bool:
    for entry in payload["characters"].values():
        if entry["status"] == "blocked":
            continue          # permanently routed to Kokoro; not a blocker
        if not entry["approved"] or entry["needs_reroll"]:
            return False
    return True


def check_approval_gate(path: str = GATE) -> tuple[bool, list[str]]:
    """Read-only. Returns (is_open, blocking_reasons).

    Downstream generation must call this and refuse to proceed when it is closed.
    """
    payload = _read_json(path)
    if payload is None:
        return False, ["voice_approval_gate.json does not exist; run: voice_manager.py plan"]

    reasons = []
    for name, entry in payload["characters"].items():
        if entry["status"] == "blocked":
            continue
        if entry["needs_reroll"]:
            reasons.append(f"{name}: flagged for re-roll ({entry.get('reviewer_note') or 'no reason given'})")
        elif not entry["approved"]:
            if not entry.get("sample_seconds"):
                reasons.append(f"{name}: no reference sample extracted yet")
            else:
                reasons.append(f"{name}: awaiting human approval")
    return (not reasons), reasons


def set_status(character: str, approved: bool | None = None,
               needs_reroll: bool | None = None, note: str = "",
               path: str = GATE) -> dict:
    payload = _read_json(path)
    if payload is None:
        raise FileNotFoundError("run: voice_manager.py plan")
    if character not in payload["characters"]:
        raise KeyError(character)
    entry = payload["characters"][character]
    if entry["status"] == "blocked":
        raise ValueError(f"{character} is routed to Kokoro and cannot be approved")
    if approved is not None:
        entry["approved"] = approved
        entry["status"] = "approved" if approved else "pending"
    if needs_reroll is not None:
        entry["needs_reroll"] = needs_reroll
        if needs_reroll:
            entry["approved"] = False
            entry["status"] = "needs_reroll"
    if note:
        entry["reviewer_note"] = note
    entry["reviewed_at"] = _now()
    payload["gate_open"] = _gate_open(payload)
    _write_json(path, payload)
    return entry


# --------------------------------------------------------------------------- MiniMax API

def _api_key() -> str:
    key = os.environ.get("MINIMAX_API_KEY")
    if not key:
        sys.exit("set MINIMAX_API_KEY in the environment; never hard-code it")
    return key


def upload_reference(sample_path: str, group_id: str | None = None) -> str:
    """Upload a WAV and return the file_id the clone endpoint needs."""
    import requests  # imported lazily so planning works without the dependency

    seconds = _ffprobe_duration(sample_path)
    if seconds < MIN_SAMPLE_SECONDS:
        raise ValueError(f"{sample_path} is {seconds:.1f}s; the API requires {MIN_SAMPLE_SECONDS}s")
    if seconds > MAX_SAMPLE_SECONDS:
        raise ValueError(f"{sample_path} is {seconds:.1f}s; the API allows {MAX_SAMPLE_SECONDS}s")
    if os.path.getsize(sample_path) > 20 * 1024 * 1024:
        raise ValueError(f"{sample_path} exceeds the 20 MB upload limit")

    group = group_id or os.environ.get("MINIMAX_GROUP_ID", "")
    with open(sample_path, "rb") as fh:
        response = requests.post(
            UPLOAD_URL,
            params={"GroupId": group} if group else None,
            headers={"Authorization": f"Bearer {_api_key()}"},
            data={"purpose": "voice_clone"},
            files={"file": (os.path.basename(sample_path), fh, "audio/wav")},
            timeout=120,
        )
    response.raise_for_status()
    payload = response.json()
    file_id = (payload.get("file") or {}).get("file_id") or payload.get("file_id")
    if not file_id:
        raise RuntimeError(f"no file_id in upload response: {payload}")
    return str(file_id)


def clone_voice(character: str, path: str = GATE, model: str = CLONE_MODEL) -> str:
    """Clone an approved reference sample and record the voice_id on the gate."""
    import requests

    is_open, reasons = check_approval_gate(path)
    payload = _read_json(path)
    entry = payload["characters"][character]
    if not entry["approved"]:
        raise PermissionError(f"{character} is not approved yet; approve before cloning")

    file_id = upload_reference(entry["sample_path"])
    voice_id = f"equalshares_{_slug(character)}"
    response = requests.post(
        CLONE_URL,
        headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"},
        json={"file_id": file_id, "voice_id": voice_id, "model": model},
        timeout=180,
    )
    response.raise_for_status()

    entry["cloned_voice_id"] = voice_id
    entry["cloned_at"] = _now()
    entry["clone_model"] = model
    _write_json(path, payload)
    return voice_id


def synthesize_line(text: str, voice_id: str, output_path: str,
                    model: str = CLONE_MODEL, speed: float = 1.0) -> str:
    """Render one line of dialogue with a cloned voice."""
    import requests

    response = requests.post(
        TTS_URL,
        headers={"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"},
        json={
            "model": model,
            "text": text,
            "stream": False,
            "voice_setting": {"voice_id": voice_id, "speed": speed,
                              "vol": 1.0, "pitch": 0},
            "audio_setting": {"sample_rate": SAMPLE_RATE, "bitrate": 128000,
                              "format": "wav", "channel": 1},
        },
        timeout=180,
    )
    response.raise_for_status()
    payload = response.json()
    audio_hex = (payload.get("data") or {}).get("audio")
    if not audio_hex:
        raise RuntimeError(f"no audio in response: {str(payload)[:300]}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as fh:
        fh.write(bytes.fromhex(audio_hex))
    return output_path


# --------------------------------------------------------------------------- CLI

def cmd_plan(args):
    plan = get_sample_budget()
    first = get_first_speaker_clips()
    print(f"{'character':<24}{'1st clip':<9}{'1st s':>7}{'total s':>9}  strategy / clips needed")
    for name in sorted(plan, key=lambda n: first[n]["sequence_order"]):
        e = plan[name]
        detail = (f"render {SAMPLE_CLIP_PREFIX}{_slug(name).upper()}"
                  if e["strategy"] == "sample_clip_required"
                  else " + ".join(e["required_clips"]))
        cid = first[name]["clip_id"]
        secs = first[name]["seconds"]
        print(f"  {name:<23}{cid:<9}{secs:>7.1f}"
              f"{e['total_dialogue_seconds']:>9.1f}  {e['strategy']}: {detail}")
    specs = generate_sample_clip_specs(plan)
    queue = write_priority_queue(plan)
    payload = init_gate()
    blocked = []
    vox = [c["id"] for c in specs]
    print(f"\nPHASE 1 - voice sample clips to render ({len(vox)}):")
    print("  " + " ".join(vox))
    print(f"\nPHASE 2 - story clips whose audio doubles as a sample ({len(queue) - len(vox)}):")
    print("  " + " ".join(queue[len(vox):]))
    print(f"\nwrote {SAMPLE_CLIP_SPEC}")
    print(f"wrote {PRIORITY}")
    print(f"wrote {GATE}")
    print("\nNothing downstream may generate until every character above is approved.")
    return 0


def cmd_extract(args):
    plan = get_sample_budget()
    targets = ([args.character] if args.character
               else [n for n in plan])
    payload = _read_json(GATE) or init_gate()
    ok = fail = 0
    for name in targets:
        try:
            result = build_reference_sample(name, plan)
        except Exception as exc:
            print(f"  {name:<22} SKIP  {exc}")
            fail += 1
            continue
        entry = payload["characters"][name]
        entry.update(sample_path=result["sample_path"],
                     sample_seconds=result["sample_seconds"],
                     extracted_at=result["extracted_at"])
        if not result["meets_api_minimum"]:
            entry["reviewer_note"] = (f"sample is {result['sample_seconds']}s, "
                                      f"below the {MIN_SAMPLE_SECONDS}s API minimum")
        print(f"  {name:<22} {result['sample_seconds']:>6.1f}s  {result['sample_path']}")
        ok += 1
    payload["gate_open"] = _gate_open(payload)
    _write_json(GATE, payload)
    print(f"\n{ok} extracted, {fail} skipped")
    return 0


def cmd_review(args):
    payload = _read_json(GATE)
    if payload is None:
        print("no gate; run: voice_manager.py plan", file=sys.stderr)
        return 2
    print(f"{'character':<24}{'status':<14}{'sample':>8}  path")
    for name, e in payload["characters"].items():
        secs = f"{e['sample_seconds']:.1f}s" if e.get("sample_seconds") else "-"
        print(f"  {name:<22}{e['status']:<14}{secs:>8}  "
              f"{e['sample_path'] if e['status'] != 'blocked' else 'Kokoro: ' + str(e['fallback_voice'])}")
    is_open, reasons = check_approval_gate()
    print(f"\ngate: {'OPEN' if is_open else 'CLOSED'}")
    for r in reasons:
        print(f"  - {r}")
    return 0


def cmd_approve(args):
    payload = _read_json(GATE)
    names = ([args.character] if args.character
             else [n for n, e in payload["characters"].items() if e["status"] != "blocked"])
    for name in names:
        try:
            entry = set_status(name, approved=True, needs_reroll=False, note=args.note)
            print(f"  approved {name} ({entry.get('sample_seconds')}s)")
        except Exception as exc:
            print(f"  {name}: {exc}")
    is_open, reasons = check_approval_gate()
    print(f"\ngate: {'OPEN' if is_open else 'CLOSED'}")
    for r in reasons:
        print(f"  - {r}")
    return 0


def cmd_reroll(args):
    entry = set_status(args.character, needs_reroll=True, note=args.reason)
    print(f"{args.character} flagged for re-roll: {args.reason}")
    print(f"re-render and re-review: {' '.join(entry['source_clips'])}")
    print("then: voice_manager.py extract --character " + args.character)
    return 0


def cmd_gate(args):
    is_open, reasons = check_approval_gate()
    print("OPEN" if is_open else "CLOSED")
    for r in reasons:
        print(f"  - {r}")
    return 0 if is_open else 1


def cmd_clone(args):
    voice_id = clone_voice(args.character)
    print(f"cloned {args.character} -> voice_id {voice_id}")
    return 0


def main() -> int:
    print(
        "DISABLED by user on 2026-08-14: the VOX/filler and external voice-clone "
        "workflow is historical and must not run. Use build_voice_reference_map.py "
        "followed by render_audio_pass.py --bootstrap-missing-voices."
    )
    return 4

    # Historical implementation retained below as evidence. It is intentionally
    # unreachable so an obsolete handoff command cannot create filler dialogue.
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("plan", help="plan samples, write priority queue and gate").set_defaults(fn=cmd_plan)

    p = sub.add_parser("extract", help="extract reference samples from rendered clips")
    p.add_argument("--character")
    p.add_argument("--all", action="store_true")
    p.set_defaults(fn=cmd_extract)

    sub.add_parser("review", help="show the gate").set_defaults(fn=cmd_review)

    p = sub.add_parser("approve")
    p.add_argument("--character")
    p.add_argument("--all", action="store_true")
    p.add_argument("--note", default="")
    p.set_defaults(fn=cmd_approve)

    p = sub.add_parser("reroll")
    p.add_argument("--character", required=True)
    p.add_argument("--reason", default="")
    p.set_defaults(fn=cmd_reroll)

    sub.add_parser("gate", help="exit 0 if open, 1 if closed").set_defaults(fn=cmd_gate)

    p = sub.add_parser("clone")
    p.add_argument("--character", required=True)
    p.set_defaults(fn=cmd_clone)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
