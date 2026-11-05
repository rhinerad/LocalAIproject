#!/usr/bin/env python3
"""Stage 1 -- rewrite every dialogue clip into the proven ref2va audio-pass prompt.

WHY THIS EXISTS
---------------
The generation saved as ComfyUI_00108.png (2026-08-13 00:02) produced accurate,
on-time, non-gibberish speech. Its prompt differs from the 124 story prompts in
four specific ways, and those four differences are the whole recipe:

  1. A REFERENCE JOBS block at the very top gives every reference an explicit
     job -- ref_audio_0 is voice only, ref_image_0 is the opening composition.
  2. SHOT LIST and DIALOGUE TIMING is ONE section. The spoken words sit inside
     the timed beat that contains them.
  3. The speaker and their on/off-screen status are named in the same sentence
     as the quote: 'the narrator says off screen "..."'.
  4. There is no second copy of the dialogue anywhere -- no DIALOGUE section, no
     AUDIO LOCK. The model receives each line exactly once.

The story prompts instead said "Narration phrase 1 of the assigned line plays
over" in the beat and put the real words in a separate DIALOGUE block. That is
indirection: the model has to work out which words belong to which second. This
script removes the indirection.

Nothing here touches story_config.json. Stage 1 output is a parallel set of
prompts under prompts_audio_pass/ plus audio_pass_config.json.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
OUT_PROMPTS = EQ / "prompts_audio_pass_omni_v1"
OUT_CONFIG = EQ / "audio_pass_config_omni_v1.json"
MASTER_MAP = EQ / "omni_voice_master_map.json"

# Stage 1 renders exist only to harvest a voice track. Picture quality is
# irrelevant; 0.2 MP is the value proven by ComfyUI_00108. Do not go below this
# without testing -- untested territory, and a collapsed latent may take the
# audio down with it.
STAGE1_MEGAPIXELS = 0.2
STAGE1_STEPS = 20

BEAT_RE = re.compile(r"^\[\s*([\d.]+)\s*-\s*([\d.]+)\s*s?\s*\]\s*(.*)$")
DLG_RE = re.compile(
    r"^\[\s*([\d.]+)\s*s?\s*-\s*([\d.]+)\s*s?\s*\]\s*(.+?)\s*,\s*([A-Z\- ]+?)\s*:\s*(.+)$"
)
QUOTE_RE = re.compile(r"[“\"]([^”\"]*)[”\"]")

# Sections that carry a second copy of the dialogue. They get deleted; their
# content is folded into the beats.
#
# There are two prompt variants in the tree and both must be handled:
#   * 16 clips (the 00-series) carry a DIALOGUE block with the literal quotes.
#   * 62 clips carry a DIALOGUE TIMING block that says "speaks the line assigned
#     to this window in the audio lock below" -- the words live only in the
#     AUDIO LOCK the runner appends at render time.
# Neither is trustworthy as a source of words. story_config's structured
# `dialogue_timing` is, so that is what this script reads.
DROP_SECTIONS = {"SPEAKERS IN THIS SHOT", "DIALOGUE", "DIALOGUE TIMING", "AUDIO LOCK"}

SPEAKER_STATUS_RE = re.compile(
    r"^(?P<name>[A-Z][A-Za-z .'\-]+?)\s*[—-]\s*(?P<status>[A-Z][A-Z\- ]*[A-Z])\b"
)

STATUS_PHRASE = {
    "ON-SCREEN": "on screen",
    "OFF-SCREEN": "off screen",
    "ON-SCREEN THEN OFF": "on screen at first, then off screen",
    "OFF-SCREEN THEN ON": "off screen at first, then on screen",
    "DEVICE VOICE": "from the device, with no person in frame speaking",
}

MOUTH_LOCK = (
    "Nobody in frame speaks except where SHOT LIST and DIALOGUE TIMING assigns a "
    "line. Every other mouth is completely closed in every frame: no muttering, no "
    "mouthed words, no lip movement, no silent conversation."
)

REFERENCE_AUDIO_ISOLATION_LOCK = (
    "Each numbered audio reference above is an identity anchor only. Match that speaker's "
    "voice identity, timbre, pitch, accent, and natural cadence. Generate one new, "
    "dry foreground performance of only the quoted script. The master recording "
    "itself is completely inaudible: never replay, copy, overlay, echo, whisper, "
    "shadow, chorus, harmonize, or leak its words, breaths, or room tone."
)

NARRATOR_SINGLE_LAYER_LOCK = (
    "VOCAL MIX — SINGLE NARRATOR PERFORMANCE ONLY\n"
    "The Narrator is exactly one dry, centered, foreground voice with one timbre, "
    "one cadence, and one performance. Never produce a second Narrator, a quieter "
    "duplicate, backing speech, a whispered copy, an alternate take, chorus, doubling, "
    "delay, echo, or a speech-shaped reverb layer. The soundtrack contains only the "
    "new scripted Narrator performance; the reference recording itself is completely "
    "inaudible. Natural ambience may remain underneath but contains no voices."
)


def parse_sections(text: str) -> list[tuple[str, list[str]]]:
    """Split a prompt into (HEADER, lines) pairs. Preamble gets header ''."""
    out: list[tuple[str, list[str]]] = []
    cur_name, cur_lines = "", []
    for line in text.splitlines():
        stripped = line.strip()
        is_header = (
            stripped
            and stripped == stripped.upper()
            and re.fullmatch(r"[A-Z][A-Z /&']*[A-Z]", stripped) is not None
            and len(stripped) <= 40
        )
        if is_header:
            out.append((cur_name, cur_lines))
            cur_name, cur_lines = stripped, []
        else:
            cur_lines.append(line)
    out.append((cur_name, cur_lines))
    return out


def parse_status_map(sections: list[tuple[str, list[str]]]) -> dict[str, str]:
    """Read on/off-screen status out of the SPEAKERS IN THIS SHOT block.

    That block is the only place screen status is recorded, and it exists on all
    78 dialogue clips. It was written by work/apply_speaker_attribution.py, where
    the status is *asserted*, not derived -- so a wrong status here means the map
    in that script is wrong, not this parser.
    """
    out: dict[str, str] = {}
    for name, lines in sections:
        if name != "SPEAKERS IN THIS SHOT":
            continue
        for raw in lines:
            m = SPEAKER_STATUS_RE.match(raw.strip())
            if m:
                out[m.group("name").strip()] = m.group("status").strip()
    return out


def parse_dialogue(clip: dict, status_map: dict[str, str]) -> list[dict]:
    """Structured dialogue straight from story_config, not from prompt prose.

    story_config's `dialogue_timing` is authoritative for words and windows.
    The prompt body is not: on 62 of 78 clips it deliberately omits the words.
    """
    found = []
    for d in clip.get("dialogue_timing") or []:
        line = d["line"]
        head = line.split("“")[0].split('"')[0]
        speaker = re.split(r"[,:]", head)[0].strip()
        q = QUOTE_RE.search(line)
        if not q or not q.group(1).strip():
            continue
        found.append(
            {
                "start": float(d["start"]),
                "end": float(d["end"]),
                "speaker": speaker,
                "status": status_map.get(speaker, "ON-SCREEN"),
                "text": q.group(1).strip(),
            }
        )
    found.sort(key=lambda x: x["start"])
    return found


def split_quote(text: str, parts: int) -> list[str]:
    """Break a quote into at most `parts` fragments, on clause boundaries.

    The working prompt split its line as '"Kent is at an inflection point,"' /
    '"that some call midlife"'. Commas and sentence ends are the natural seams;
    splitting mid-clause would read as two separate utterances.

    Returns fewer than `parts` fragments when the line has no more seams than
    that. The caller must cope with a short list -- forcing a split would cut
    mid-clause, and forcing a single fragment would compress a 7-second line
    into a 3-second beat.
    """
    if parts <= 1:
        return [text]
    pieces = [p for p in re.split(r"(?<=[,.;:!?])\s+", text) if p.strip()]
    parts = min(parts, len(pieces))
    if parts <= 1:
        return [text]
    per = len(pieces) / parts
    out, i = [], 0.0
    for n in range(parts):
        j = len(pieces) if n == parts - 1 else int(round(i + per))
        chunk = " ".join(pieces[int(round(i)):j]).strip()
        if chunk:
            out.append(chunk)
        i += per
    return out or [text]


INDIRECTION_PATTERNS = [
    r"\s*Narration phrase \d+ of the assigned line plays over\.?\s*",
    r"\s*(The [A-Za-z ]+ )?(speaks|is speaking) the assigned line\.?\s*",
    r"\s*speaks the line assigned to this window in the audio lock below\.?\s*",
    r"\s*(delivers|says) the line assigned to this window\.?\s*",
]


def dequote_prose(body: str) -> str:
    """Remove quotation marks from stage direction.

    Project rule: quotation marks mean speech and only speech. A quoted string
    with no named speaker gets assigned to the nearest person in the beat, so a
    stage direction like 'his expression cools on the word "but"' can be
    performed as dialogue. 00M did exactly this.
    """
    return re.sub(r'[“"]([^”"]{1,40})[”"]', r"\1", body)


def strip_indirection(body: str, speaker: str) -> str:
    """Remove every phrase that points at words held somewhere else.

    Also removes a bare '<Name> speaks.' -- once the words are quoted in the
    same sentence, that clause is a second copy of one instruction, and the
    model has to reconcile the two.
    """
    for pat in INDIRECTION_PATTERNS:
        body = re.sub(pat, " ", body, flags=re.I)
    body = re.sub(
        r"\s*%s\s+(speaks|is speaking|talks)\s*\.\s*" % re.escape(speaker), " ", body
    )
    return re.sub(r"\s{2,}", " ", body).strip()


def ends_sentence(s: str) -> bool:
    """True if s already closes a sentence, ignoring a trailing quote mark."""
    return s.rstrip('"”\'').rstrip().endswith((".", "!", "?", "…", "—"))


def say(d: dict, fragment: str, first: bool) -> str:
    """One sentence carrying speaker, screen status and the words.

    Terminal punctuation is not doubled: '"...compliment.".' reads as two
    sentences and is exactly the kind of redundancy that costs a take.
    """
    where = STATUS_PHRASE.get(d["status"], d["status"].lower())
    verb = f"says {where}" if first else "continues"
    sentence = f'{d["speaker"]} {verb} "{fragment}"'
    return sentence if ends_sentence(fragment) else sentence + "."


def fold_dialogue_into_beats(beat_lines: list[str], dialogue: list[dict]) -> list[str]:
    """Put every spoken line once in its exact authoritative time window.

    A story line can span several smaller action beats. Splitting only on
    punctuation used to compress an unsplittable sentence into the first small
    beat (for example, 00D's 1-5 second narration landed entirely in 1-2.5).
    Stage 1 exists to make the soundtrack, so exact dialogue timing wins: when
    no action beat has the same boundaries, add one explicit overlapping
    dialogue beat for the full structured window. The surrounding action beats
    remain, but their old indirect speech placeholders are removed.
    """
    beats = []
    for raw in beat_lines:
        m = BEAT_RE.match(raw.strip())
        beats.append(
            {
                "raw": raw,
                "start": float(m.group(1)),
                "end": float(m.group(2)),
                "text": dequote_prose(m.group(3)),
            }
            if m
            else {"raw": dequote_prose(raw), "start": None, "end": None, "text": None}
        )

    for d in dialogue:
        covered = [
            b for b in beats
            if b["start"] is not None and b["end"] > d["start"] and b["start"] < d["end"]
        ]
        if not covered:
            # No beat covers it; append a beat of its own so the words still
            # carry a time range. Silent dialogue is worse than an extra beat.
            beats.append(
                {
                    "raw": None,
                    "start": d["start"],
                    "end": d["end"],
                    "text": say(d, d["text"], True),
                    "injected": True,
                }
            )
            continue

        # Every covered beat loses the old indirection. Leaving "Narration
        # phrase 2 of the assigned line plays over" next to the exact quote is a
        # contradiction, and contradiction after an edit is a known cause of
        # rejected takes.
        for b in covered:
            b["text"] = strip_indirection(b["text"] or "", d["speaker"])

        exact = next(
            (
                b for b in covered
                if abs(b["start"] - d["start"]) < 1e-6
                and abs(b["end"] - d["end"]) < 1e-6
            ),
            None,
        )
        said = say(d, d["text"], True)
        if exact is not None:
            body = exact["text"] or ""
            exact["text"] = (said + " " + body).strip() if body else said
        else:
            beats.append(
                {
                    "raw": None,
                    "start": d["start"],
                    "end": d["end"],
                    "text": said,
                    "injected": True,
                }
            )

    beats = [b for b in beats if b["start"] is not None or (b["raw"] or "").strip()]
    beats.sort(key=lambda b: (b["start"] is None, b["start"] if b["start"] is not None else 0))

    out = []
    for b in beats:
        if b["start"] is None:
            out.append(b["raw"])
            continue
        a = f"{b['start']:g}"
        z = f"{b['end']:g}"
        out.append(f"[{a}-{z} s] {b['text']}")
    return out


def reference_block(speakers: list[str], vmap: dict,
                    has_last_frame: bool = False) -> list[str]:
    """The block that gives every reference an explicit job."""
    lines = ["REFERENCE JOBS"]
    ref_index = 0
    for name in speakers:
        ref = vmap.get("references", {}).get(name)
        if not ref:
            continue
        lines.append(
            f"<Audio {ref_index + 1}> is the fixed master voice for {name}. "
            f"Whenever {name} speaks, use the same voice identity, timbre, pitch, "
            f"accent, and natural cadence as <Audio {ref_index + 1}>. Take no words "
            f"or background sound from the reference."
        )
        ref_index += 1
    if ref_index:
        lines.append(REFERENCE_AUDIO_ISOLATION_LOCK)
    lines.append(
        "<Picture 1> is the exact opening composition. Begin on it precisely."
    )
    if has_last_frame:
        lines.append(
            "<Picture 2> is the exact closing composition. Arrive on it naturally "
            "at the end without a cut, morph, or unrelated reframe."
        )
    return lines


def build_one(clip: dict, prompt_text: str, vmap: dict) -> tuple[str, list[str]]:
    sections = parse_sections(prompt_text)
    status_map = parse_status_map(sections)
    dialogue = parse_dialogue(clip, status_map)
    if not dialogue:
        return "", []

    speakers: list[str] = []
    for d in dialogue:
        if d["speaker"] not in speakers:
            speakers.append(d["speaker"])

    out: list[str] = ["One continuous unbroken take.", ""]
    out += reference_block(speakers, vmap, bool(clip.get("last_frame")))
    out.append("")
    if "Narrator" in speakers:
        out.append(NARRATOR_SINGLE_LAYER_LOCK)
        out.append("")

    for name, lines in sections:
        if name in DROP_SECTIONS:
            continue
        if name == "":
            continue  # original preamble replaced above
        if name == "SHOT LIST":
            body = [
                ln for ln in lines
                if ln.strip()
                and not ln.strip().startswith("Narration timing below")
                and "Nobody in frame speaks except" not in ln
                and "Spoken words appear only inside" not in ln
            ]
            out.append("SHOT LIST and DIALOGUE TIMING")
            out += fold_dialogue_into_beats(body, dialogue)
            out.append("")
            out.append(MOUTH_LOCK)
            out.append("")
            continue
        if name == "REFERENCES":
            continue  # folded into REFERENCE JOBS
        out.append(name)
        body = [
            ln for ln in lines
            if "Spoken words appear only inside" not in ln
            and not (
                dialogue
                and re.search(
                    r"\b(?:nobody|no one|no character)\s+speaks(?:\s+to\s+anybody)?\b",
                    ln,
                    flags=re.I,
                )
            )
        ]
        while body and not body[-1].strip():
            body.pop()
        out += body
        out.append("")

    text = "\n".join(out).rstrip() + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, speakers


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt-dir", default=None,
                    help="where the current per-clip .txt prompts live")
    ap.add_argument("--check", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    cfg = json.loads((EQ / "story_config.json").read_text(encoding="utf8"))
    if not MASTER_MAP.is_file():
        raise SystemExit(
            f"missing immutable Omni-Reference voice map: {MASTER_MAP}; "
            "run work/prepare_omni_voice_masters.py first"
        )
    vmap = json.loads(MASTER_MAP.read_text(encoding="utf8"))

    prompt_dir = Path(args.prompt_dir) if args.prompt_dir else None
    if prompt_dir and not prompt_dir.exists():
        print(f"prompt dir not found: {prompt_dir}")
        return 2

    OUT_PROMPTS.mkdir(parents=True, exist_ok=True)
    entries, skipped, warnings = [], [], []

    for clip in cfg["clips"]:
        cid = clip["id"]
        if not (clip.get("dialogue_timing") or []):
            skipped.append(cid)
            continue

        src = None
        if prompt_dir and (prompt_dir / f"{cid}.txt").exists():
            src = (prompt_dir / f"{cid}.txt").read_text(encoding="utf8")
        else:
            src = clip.get("prompt", "")
        text, speakers = build_one(clip, src, vmap)
        if not text:
            warnings.append(f"{cid}: no parsable DIALOGUE block, left alone")
            continue

        refs = []
        for name in speakers:
            r = vmap.get("references", {}).get(name)
            if not r or not r.get("eligible"):
                warnings.append(f"{cid}: no eligible 5-10 second master voice for {name}")
                continue
            refs.append({
                "index": len(refs),
                "character": name,
                "wav": r["ref_wav"],
                "source_clip": r["source_clip"],
                "speech_seconds": r["speech_seconds"],
                "thin": r.get("thin", False),
                "provisional": r.get("provisional", False),
                "requires_ear_review": r.get("requires_ear_review", False),
                "sha256": r.get("sha256"),
                "immutable_master": True,
            })

        if not args.check:
            (OUT_PROMPTS / f"{cid}.txt").write_text(text, encoding="utf8")

        entries.append({
            "id": cid,
            "scene": clip.get("scene"),
            "duration": clip.get("duration"),
            "frames": clip.get("frames"),
            "first_frame": clip.get("first_frame"),
            "last_frame": clip.get("last_frame"),
            "force_last_frame": bool(clip.get("force_last_frame")),
            "speakers": speakers,
            "ref_audios": refs,
            "prompt_file": f"prompts_audio_pass_omni_v1/{cid}.txt",
            "dialogue_lines": len(clip["dialogue_timing"]),
        })

    payload = {
        "stage": "1 - Omni-Reference voice-lock audio pass",
        "purpose": "generate exact, consistent, on-time speech with immutable per-character master voices",
        "voice_lock_policy": {
            "same_exact_master_file_every_clip": True,
            "master_map": str(MASTER_MAP.relative_to(EQ)).replace("\\", "/"),
            "prompt_reference_grammar": "<Audio 1> / <Picture 1>",
            "voice_references_only": True,
            "sound_and_music_references_in_this_pass": False,
            "max_audio_references": 3,
        },
        "workflow_profile": "ref2va",
        "unet": "minimax_h3_ref2va_pruned_nvfp4.safetensors",
        "node": "MiniMaxH3ReferenceToVideo",
        "ref_image_input": "ref_images.ref_image_0",
        "ref_audio_input_pattern": "ref_audios.ref_audio_{n} (workflow socket only; prompts use <Audio n+1>)",
        "ref_image_size": "match",
        "megapixels": STAGE1_MEGAPIXELS,
        "aspect_ratio": "16:9 (Widescreen)",
        "resolution_multiple": 32,
        "steps": STAGE1_STEPS,
        "sampler": "res_multistep",
        "scheduler": "simple",
        "denoise": 1.0,
        "fps": 24,
        "bit_depth": 8,
        "frame_count_mode": cfg.get("frame_count_mode"),
        "proof": "ComfyUI_00108.png / MiniMax_H3_00002_.mp4, 2026-08-13 00:02",
        "clips": entries,
        "no_dialogue_skipped": skipped,
        "warnings": warnings,
    }
    if not args.check:
        OUT_CONFIG.write_text(json.dumps(payload, indent=2), encoding="utf8")

    multi = [e for e in entries if len(e["speakers"]) > 1]
    print(f"dialogue clips rewritten : {len(entries)}")
    print(f"clips with no dialogue    : {len(skipped)}")
    print(f"clips needing 2+ ref_audio: {len(multi)}")
    if multi:
        for e in multi[:15]:
            print(f"   {e['id']:5s} {', '.join(e['speakers'])}")
        if len(multi) > 15:
            print(f"   ... and {len(multi)-15} more")
    if warnings:
        print("\nwarnings:")
        for w in warnings:
            print("  " + w)
    if not args.check:
        print(f"\nwrote {OUT_PROMPTS}")
        print(f"wrote {OUT_CONFIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
