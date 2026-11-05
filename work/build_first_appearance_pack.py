#!/usr/bin/env python3
"""Build a per-character "first appearance" pack for Omni-Reference voice bootstrap.

Purpose
-------
Before any Omni-Reference render can lock a character's voice, that character
needs a voice-identity master. Under the 2026-08-14 rule, a master may only come
from the character's **first qualifying actual story soundtrack** -- not from
invented VOX filler. So the operator needs, per character, everything required
to render that one clip by hand:

    FIRST_APPEARANCE/<NN>_<Character>/
        README.md              what to render, the lines, the acceptance test
        prompt.txt             the audio-pass prompt, ready to paste
        first_frame.png        the opening anchor
        last_frame.png         the closing anchor, when the clip has one
        identity/              the master reference images for this character

"First appearance" means the earliest clip in sequence order where the character
**speaks**. A character standing silently in an earlier shot is useless for a
voice master, so silent appearances are ignored.

Characters are numbered by that clip's position in the film, so working through
the folders in name order also walks the story in order -- and the earliest
folders unblock the most downstream clips.

Nothing is deleted or overwritten in the project tree; this only reads.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"

# Identity reference images, by character. Anything not listed falls back to the
# ensemble sheet, which shows the five principals left to right.
IDENTITY = {
    "Kent": ["alex_vale_master_v1.png", "ensemble_cast_master_v1.png"],
    "Narrator": ["narrator_master_v1.png"],
    "Avery": ["ensemble_cast_master_v1.png"],
    "Doris": ["ensemble_cast_master_v1.png"],
    "Doris recording": ["ensemble_cast_master_v1.png"],
    "Ryann Sally": ["ensemble_cast_master_v1.png"],
    "Faith White": ["ensemble_cast_master_v1.png"],
    "Male Visitor One": ["visitor_one_seated_master_v1.png", "opening_cast_master_v1.png"],
    "Male Visitor Two": ["visitor_two_standing_master_v1.png", "opening_cast_master_v1.png"],
}
FALLBACK_IDENTITY = ["ensemble_cast_master_v1.png"]

# A master wants this much clean speech. Below it, expect to re-roll.
TARGET_SPEECH_SECONDS = 6.0


def speaker_of(line: str) -> str:
    head = line.split("“")[0].split('"')[0]
    return re.split(r"[,:]", head)[0].strip()


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def quote_of(line: str) -> str:
    m = re.search(r"[“\"]([^”\"]*)[”\"]", line)
    return m.group(1).strip() if m else ""


def build(out_root: Path, force: bool) -> int:
    cfg = json.loads((EQ / "story_config.json").read_text(encoding="utf8"))
    clips = cfg["clips"]

    try:
        vmap = json.loads((EQ / "omni_voice_master_map.json").read_text(encoding="utf8"))
        have_master = {
            name: r for name, r in vmap.get("references", {}).items()
            if r.get("ref_wav") and (EQ / r["ref_wav"]).exists()
        }
    except Exception:
        have_master = {}

    # earliest speaking clip per character
    first: dict[str, dict] = {}
    for order, clip in enumerate(clips):
        for d in clip.get("dialogue_timing") or []:
            name = speaker_of(d["line"])
            if name and name not in first:
                first[name] = {"clip": clip, "order": order}

    out_root.mkdir(parents=True, exist_ok=True)
    index = []

    for name, rec in sorted(first.items(), key=lambda kv: kv[1]["order"]):
        clip = rec["clip"]
        cid = clip["id"]
        lines = [d for d in clip["dialogue_timing"] if speaker_of(d["line"]) == name]
        others = sorted({speaker_of(d["line"]) for d in clip["dialogue_timing"]} - {name})
        spoken = sum(float(d["end"]) - float(d["start"]) for d in lines)

        folder = out_root / f"{rec['order']+1:03d}_{slug(name)}"
        if folder.exists() and not force:
            pass
        folder.mkdir(parents=True, exist_ok=True)

        # prompt
        src_prompt = EQ / "prompts_audio_pass" / f"{cid}.txt"
        prompt_text = ""
        if src_prompt.exists():
            prompt_text = src_prompt.read_text(encoding="utf8")
            shutil.copy2(src_prompt, folder / "prompt.txt")
        else:
            prompt_text = clip.get("prompt", "")
            (folder / "prompt.txt").write_text(prompt_text, encoding="utf8")

        # anchors
        anchors = []
        for field, label in (("first_frame", "first_frame"), ("last_frame", "last_frame")):
            rel = clip.get(field)
            if not rel:
                continue
            src = EQ / rel
            if src.exists():
                shutil.copy2(src, folder / f"{label}{src.suffix}")
                anchors.append((label, rel))

        # identity sheets
        ident = folder / "identity"
        ident.mkdir(exist_ok=True)
        copied_ident = []
        for fn in IDENTITY.get(name, FALLBACK_IDENTITY):
            src = EQ / "references" / fn
            if src.exists():
                shutil.copy2(src, ident / fn)
                copied_ident.append(fn)

        master = have_master.get(name)
        # A file on disk is not an approved master. Eight of the eighteen are
        # provisional bootstraps still awaiting a listen, and those are exactly
        # the ones this pack exists to replace.
        provisional = bool(master) and (
            master.get("provisional") or master.get("requires_ear_review")
        )
        if not master:
            status = "NEEDS MASTER — none exists"
        elif provisional:
            status = "PROVISIONAL — render this clip and replace it"
        else:
            status = "APPROVED — no action needed"

        readme = [
            f"# {name} — first speaking appearance",
            "",
            f"**Clip `{cid}`** — position {rec['order']+1} of {len(clips)} · {clip.get('scene','')}",
            "",
            f"- Duration **{clip.get('duration')} s**, **{clip.get('frames')} frames**",
            f"- Scripted speech for {name}: **{spoken:.1f} s** across {len(lines)} line(s)",
            f"- Other speakers in this clip: **{', '.join(others) if others else 'none — solo'}**",
            f"- Voice master status: **{status}**",
        ]
        if master:
            readme.append(f"  - current: `{master.get('ref_wav')}` ({master.get('seconds','?')} s)")
            if provisional:
                readme.append("  - flagged `provisional` / `requires_ear_review` — not trustworthy yet")
        readme += [
            "",
            "## Render settings",
            "",
            "| | |",
            "|---|---|",
            "| Checkpoint | `minimax_h3_ref2va_pruned_nvfp4.safetensors` (non-Turbo) |",
            "| Node | `MiniMaxH3ReferenceToVideo` |",
            "| Megapixels | **0.2** — this is an audio render, picture is disposable |",
            "| Aspect / multiple | 16:9 (Widescreen) / 32 |",
            "| Steps | 20, `res_multistep` / `simple`, denoise 1.0 |",
            f"| Length | {clip.get('frames')} frames @ 24 fps, 8-bit |",
            "| `ref_image_size` | `match` |",
            "",
            "## The lines",
            "",
        ]
        for d in lines:
            readme.append(f'- **[{d["start"]}–{d["end"]} s]** "{quote_of(d["line"])}"')
        if others:
            readme += [
                "",
                f"> This clip is **not solo** — {', '.join(others)} also speak. Cut the "
                "master only from a window where nobody else is talking.",
            ]
        readme += [
            "",
            "## Files here",
            "",
            "- `prompt.txt` — paste into the prompt box unchanged",
        ]
        for label, rel in anchors:
            readme.append(f"- `{label}` — from `{rel}`")
        if not anchors:
            readme.append("- *(no anchor frame in the config for this clip)*")
        if copied_ident:
            readme.append(f"- `identity/` — {', '.join(copied_ident)}")
        readme += [
            "",
            "## Accepting the take",
            "",
            "Judge on **audio only**. The 0.2 MP picture will look bad; ignore it.",
            "",
            "1. The words are the scripted words above.",
            "2. They land inside the assigned window.",
            "3. **One voice, one dry layer** — no quieter duplicate, echo, whisper, "
            "chorus, or alternate take underneath. This is the failure that has "
            "blocked the project.",
            "4. No invented music or score.",
            "",
            f"Then cut the master from one **contiguous** speaking passage — never "
            f"stitched — targeting **{TARGET_SPEECH_SECONDS:.0f}+ seconds**. Verify with:",
            "",
            "```",
            "python work\\speech_density.py <the-cut.wav>",
            "```",
            "",
            "Good is **>=6 s of speech at >=70% density**. Save as "
            f"`outputs/equal_shares/voices/{slug(name).lower()}/omni_master_vN.wav` — "
            "a new version, never overwriting an existing master.",
        ]
        (folder / "README.md").write_text("\n".join(readme) + "\n", encoding="utf8")

        index.append({
            "order": rec["order"] + 1,
            "character": name,
            "folder": folder.name,
            "clip": cid,
            "scene": clip.get("scene"),
            "duration": clip.get("duration"),
            "frames": clip.get("frames"),
            "scripted_speech_seconds": round(spoken, 1),
            "solo": not others,
            "other_speakers": others,
            "has_master": bool(master),
            "provisional": provisional,
            "needs_work": (not master) or provisional,
            "current_master": (master or {}).get("ref_wav"),
        })

    (out_root / "index.json").write_text(json.dumps(index, indent=2), encoding="utf8")

    need = [e for e in index if e["needs_work"]]
    solo = [e for e in index if e["solo"]]
    lines = [
        "# First appearance packs — voice bootstrap order",
        "",
        "One folder per character, holding the earliest clip in which they **speak**,",
        "with its prompt, anchor frames and identity sheets. Render these at **0.2 MP**",
        "to harvest each character's voice-identity master before the main soundtrack",
        "pass needs it.",
        "",
        "Folders are numbered by position in the film, so working in name order walks",
        "the story in order.",
        "",
        f"**{len(index)} characters · {len(solo)} solo clips · {len(need)} still need a real master**",
        "",
        "| # | Character | Clip | Speech | Solo | Master |",
        "|---|---|---|---|---|---|",
    ]
    for e in index:
        lines.append(
            f'| {e["order"]} | {e["character"]} | `{e["clip"]}` | '
            f'{e["scripted_speech_seconds"]} s | {"yes" if e["solo"] else "no — " + ", ".join(e["other_speakers"])} | '
            f'{"approved" if not e["needs_work"] else "**PROVISIONAL — do this**"} |'
        )
    lines += [
        "",
        "## Rules that apply to every one of these",
        "",
        "- **0.2 MP, non-Turbo, 20 steps.** These are audio renders; picture is disposable.",
        "- **Actual scripted dialogue only.** Invented VOX or filler lines are prohibited.",
        "- **One contiguous passage from one take.** Never concatenate two passages —",
        "  that teaches an average of two deliveries, which is the drift the master exists",
        "  to prevent.",
        "- **Judge by ear.** The recogniser cannot decode H3's synthetic voice; an empty",
        "  transcript means unknown, never perfect.",
        "- **Listen for a doubled vocal layer.** A quieter second voice under the take is",
        "  the specific fault that has blocked this project.",
        "- **Never overwrite a master.** Save `omni_master_v2.wav`, `_v3`, and so on.",
        "",
        "## Where a clip is not solo",
        "",
        "Some characters first speak in a scene with others. Those are marked above.",
        "Cut the master only from a window where nobody else is talking, and if no such",
        "window exists in the take, re-roll rather than accept a blended reference.",
    ]
    (out_root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf8")

    print(f"{len(index)} character packs written to {out_root}")
    print(f"  solo clips        : {len(solo)}")
    print(f"  provisional/missing masters : {len(need)}")
    for e in need:
        print(f'     {e["order"]:3d} {e["character"]:24s} {e["clip"]:5s} '
              f'{e["scripted_speech_seconds"]:4.1f}s '
              f'{"solo" if e["solo"] else "with " + ", ".join(e["other_speakers"])}')
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="destination folder")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    return build(Path(args.out), args.force)


if __name__ == "__main__":
    raise SystemExit(main())
