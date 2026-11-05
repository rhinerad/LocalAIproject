#!/usr/bin/env python3
"""Build voice AUDITION packs — pick each character's voice before locking it.

THE PROBLEM THIS SOLVES
-----------------------
A voice master is cut from a rendered take. If that take speaks gibberish, the
master is gibberish, and every clip referencing it inherits a broken voice. Only
the Narrator has an approved master (`narrator_omni_master_v2_source`); the other
17 characters' masters were cut from takes nobody has listened to.

So the order has to be: **audition first, lock second, then render the pass.**

WHAT AN AUDITION IS
-------------------
For each character, N takes of their single best line, rendered with **no audio
reference at all** — because there is no voice to match yet. H3 invents a voice
from the prompt each time, the operator listens, picks the take they like, and
that take becomes the master.

This is the one place in the project where varying the seed is the point.

WHY NO `<Audio N>`
------------------
Referencing a master you have not approved is circular: it locks in the voice you
are trying to choose. The audition prompt therefore has no `<Audio N>` in
`subject_definitions` and no audio line in `retention_analysis` — but it does
carry an explicit voice DESCRIPTION so H3 has something to aim at.

LINE SELECTION
--------------
The character's longest line in a clip where they are the sole speaker, so the
audition is that voice and nothing else. Where no solo clip exists, their longest
line anywhere, with the prompt naming only them.

DURATION
--------
Fitted at the pace measured from the 14 known-good clips (2.5 w/s, median 2.75),
snapped to the 17k+5 grid. See docs/GOLDEN_REFERENCE/.

TWO DIFFERENT KNOBS, AND THEY FIX DIFFERENT THINGS
--------------------------------------------------
An audition can fail in two unrelated ways, and reaching for the wrong knob is
why this has been slow.

  **Wrong voice** — right words, but the timbre, age, or accent is not the
  character. Fix: **change the seed.** A different seed is a different invented
  voice. This is the only place in the project where re-rolling is the point.

  **Wrong words** — gibberish, slurring, mispronunciation. Fix: **walk the
  duration ladder**, per the operator's rule of 2026-08-18: base, +1, -1, +2,
  -2, +3, -3. Words per second is fixed by the script and the duration; the seed
  cannot change it, so re-rolling only buys a different flavour of the same
  problem. See work/duration_ladder.py.

So each pack ships three seeds at the base length to choose the voice, plus that
character's own precomputed ladder to walk if the voice is right but the words
are not. Change one knob at a time.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import duration_ladder

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"

WORDS_PER_SEC = 2.5
LEAD_IN = 0.6
TAIL_MARGIN = 1.5
MIN_SECONDS = 4.0
TAKES_PER_CHARACTER = 3

# A voice needs describing when there is no reference to point at. Kept short and
# physical -- age, weight, pace -- rather than emotional adjectives.
VOICE_BRIEF = {
    "Kent": "a man in his late forties, warm mid-range voice, unhurried, slightly weary",
    "Avery": "a man in his fifties, smooth professional baritone, controlled and even",
    "Doris": "an elderly woman, light and papery, gentle, unhurried",
    "Doris recording": "an elderly woman heard through a small speaker, thin and slightly compressed",
    "Ryann Sally": "a woman in her thirties, bright clear mid-range, brisk and articulate",
    "Faith White": "a woman in her forties, measured and pastoral, low and steady",
    "Volunteer": "a young adult, friendly and quick, light energetic delivery",
    "Housing representative": "a woman in her forties, procedural and polite, flat official cadence",
    "Terminal voice": "a synthetic public-address voice, even, no emotion, machine-clean",
    "Congregation member": "a middle-aged voice from a seated crowd, ordinary and unpolished",
    "Male Visitor One": "a man in his fifties, polite and formal, careful diction",
    "Male Visitor Two": "a man in his forties, politely insistent, slightly higher and quicker",
    "Wealthy commuter": "a man in his fifties, confident and clipped, faintly condescending",
    "Unhoused man": "a man in his fifties, rough-edged and warm, unhurried",
    "Council member": "a man in his sixties, dry administrative delivery, low and slow",
    "Crew lead": "a man in his forties, blunt and practical, outdoor voice",
    "Aid worker": "a woman in her thirties, calm and capable, even pace",
    "Narrator": "a man in his late fifties, lean dry authoritative delivery, measured",
}


def slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def speaker_of(line: str) -> str:
    head = line.split("“")[0].split('"')[0]
    return re.split(r"[,:]", head)[0].strip()


def quote_of(line: str) -> str:
    m = re.search(r"[“\"]([^”\"]*)[”\"]", line)
    return m.group(1).strip() if m else ""


def frames_for(seconds: float) -> int:
    base = max(5, round(seconds * 24))
    return base + (5 - (base % 17)) % 17


def ladder_rows(seconds: float) -> list[dict]:
    """This character's retry ladder. Uncapped: an audition is a standalone
    render, so there is no scripted picture length it has to fit inside."""
    return duration_ladder.ladder(seconds)


def audition_prompt(name: str, clip: dict, text: str, solo: bool) -> str:
    brief = VOICE_BRIEF.get(name, "an adult speaking naturally")
    setting = "a plain interior with no other people visible"
    return f"""subject_definitions:
<Subject 1> is {name}, {brief}. They are the only person in this shot.
<Subject 2> is the location of this shot: {setting}.
<Picture 1> is the first frame of [Shot 1].

summary:
[keyframe completion] The target video is one continuous shot in which
<Subject 1> (S1) stands alone in <Subject 2> and speaks one line directly. The
shot begins exactly on <Picture 1>. No audio reference is supplied; the voice is
generated from the description above.

retention_analysis:
<Subject 1> (appears in [Shot 1]): fully_preserved - {name}'s face, hair, and clothing are identical in the last frame to the first.
<Subject 2> (appears in [Shot 1]): fully_preserved - every fixture stays in its established position for the whole shot.
<Picture 1> ([Shot 1] first frame): fully_preserved - the shot matches this composition exactly.

detailed_description:
The target video is live-action cinematic realism, evenly lit, with no stylisation.
[Shot 1] The shot begins from <Picture 1>. The camera holds a static shot for the entire shot and there is no cut. Exactly one person is in frame for the whole shot: {name}. Nobody else appears, enters, or is visible in any doorway, window, mirror, or reflection.
{name} (S1) stands still, hands at their sides, and speaks directly to camera in the voice of {brief}, saying: <d>[English] {text}</d> They close their mouth and say nothing further for the rest of the shot.
There is only one spoken line in this entire shot. When it is finished — however early in the shot that falls — every voice stops. Nobody speaks, mutters, hums, sighs, or makes any vocal sound for the whole remainder of the shot, and the shot plays out on room tone alone. No extra words are invented to fill the remaining time.
Nobody enters or leaves frame, no person is duplicated, and no face, hairstyle, facial hair, or item of clothing changes between the first frame and the last. No lettering, signage, labels, captions, subtitles, watermarks, or logos appear on any surface. No hand, finger, face, or limb is distorted or deformed.

overall_soundscape:
Quiet natural indoor room tone continues evenly throughout the shot. Most of this shot has no speech in it at all, and silence is correct wherever no line is assigned. Never more than one voice at a time: no second voice, no quieter duplicate, no echo, no reverb tail, no whisper, no chorus, and no backing vocal under the speaker. Once the line is finished the voice stops and only room tone continues to the final frame.

non_diegetic_music:
N/A
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--include-narrator", action="store_true",
                    help="the Narrator is already approved; skipped unless asked")
    args = ap.parse_args()

    cfg = json.loads((EQ / "story_config.json").read_text(encoding="utf8"))
    clips = cfg["clips"]

    # every candidate line per character, with whether that clip is solo
    cand: dict[str, list[dict]] = {}
    for order, clip in enumerate(clips):
        timing = clip.get("dialogue_timing") or []
        if not timing:
            continue
        here = {speaker_of(d["line"]) for d in timing}
        for d in timing:
            name = speaker_of(d["line"])
            text = quote_of(d["line"])
            if not name or not text:
                continue
            cand.setdefault(name, []).append({
                "clip": clip, "order": order, "text": text,
                "words": len(re.findall(r"\S+", text)),
                "solo": len(here) == 1,
            })

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    index = []

    # Only characters who actually need a master get an audition.
    #
    # Operator rule, 2026-08-18: a character who speaks in only ONE clip needs no
    # voice master and no <Audio N> — there is nothing for them to be consistent
    # with. Auditioning them would be renders spent choosing a voice that gets
    # thrown away. work/classify_voice_requirements.py owns the classification;
    # do not recount speakers here.
    req_path = EQ / "voice_requirements.json"
    if not req_path.is_file():
        raise SystemExit("run work/classify_voice_requirements.py first — "
                         "voice_requirements.json is missing")
    req = json.loads(req_path.read_text(encoding="utf8"))
    needs_master = {n for n, c in req["characters"].items() if c["needs_voice_master"]}
    skipped_one_off = []

    for name, options in sorted(cand.items(), key=lambda kv: -max(o["words"] for o in kv[1])):
        if name == "Narrator" and not args.include_narrator:
            continue
        if name not in needs_master:
            skipped_one_off.append(name)
            continue
        # prefer a solo clip, then the longest line
        options.sort(key=lambda o: (not o["solo"], -o["words"]))
        pick = options[0]
        clip = pick["clip"]

        secs = max(MIN_SECONDS, LEAD_IN + pick["words"] / WORDS_PER_SEC + TAIL_MARGIN)
        frames = frames_for(secs)
        rungs = ladder_rows(frames / 24)

        folder = out_root / slug(name)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "prompt.txt").write_text(
            audition_prompt(name, clip, pick["text"], pick["solo"]), encoding="utf8")

        rel = clip.get("first_frame")
        if rel and (EQ / rel).is_file():
            shutil.copy2(EQ / rel, folder / f"first_frame{Path(rel).suffix}")

        (folder / "README.md").write_text("\n".join([
            f"# {name} — voice audition",
            "",
            f"**Render {TAKES_PER_CHARACTER} takes at the duration below, changing ONLY",
            "the seed.** Listen, pick one, and that take becomes this character's master.",
            "",
            "If a take has the **right voice but bad words** — gibberish, slurring, a",
            "mispronunciation — do **not** re-roll the seed. Keep that seed and walk the",
            "duration ladder at the bottom of this file.",
            "",
            "| | |",
            "|---|---|",
            f"| Line | \"{pick['text']}\" |",
            f"| Words | {pick['words']} |",
            f"| Duration | **{frames/24:.2f} s = {frames} frames** (ladder rung 0) |",
            f"| Source clip | `{clip['id']}` ({'solo' if pick['solo'] else 'not solo — prompt names only this character'}) |",
            "| Megapixels | **0.2** |",
            "| Steps / sampler | 20, `res_multistep` / `simple`, denoise 1.0 |",
            "| fps / depth | 24 / 8-bit |",
            "| `ref_image_size` | `match` |",
            "| `ref_images.ref_image_0` | `first_frame` in this folder |",
            "| **`ref_audios.ref_audio_0`** | **LEAVE DISCONNECTED** |",
            "",
            "## Why no audio reference",
            "",
            "You are choosing this voice, not matching one. Wiring an unapproved",
            "master would lock in the voice you are trying to replace. Leave the",
            "audio socket empty and let H3 invent from the description in the prompt.",
            "",
            "## Paste the prompt exactly",
            "",
            "`prompt.txt` starts with `subject_definitions:`. **Nothing goes above",
            "that line.** A prepended header is what corrupted the last autopilot",
            "pass — see `docs/GOLDEN_REFERENCE/README.md`.",
            "",
            "## Picking",
            "",
            "Judge on audio only; the 0.2 MP picture will look bad. You want:",
            "",
            "- the right character for the part",
            "- **real words, not gibberish**",
            "- one dry voice, no doubled layer or echo",
            "- no invented speech after the line ends",
            "",
            "Save the winner as",
            f"`outputs/equal_shares/voices/{slug(name).lower()}/omni_master_v2.wav`",
            "(or `_v3`… — never overwrite), then run",
            "`python work\\sync_omni_audio_config.py`.",
            "",
            "## Duration ladder — for bad WORDS, not a bad voice",
            "",
            "Words per second is set by the line and the duration. The seed cannot",
            "change it, which is why re-rolling a mispronunciation just produces a",
            "different mispronunciation. Move the window instead: hold the seed, take",
            "the next row, re-render. Stop at the first row that speaks cleanly.",
            "",
            "| try | rung | nominal | frames | actual | w/s |",
            "|---|---|---|---|---|---|",
        ] + [
            f'| {i} | {r["rung"]} | {r["nominal_seconds"]:.0f} s | **{r["frames"]}** | '
            f'{r["seconds"]:.3f} s | {pick["words"]/r["seconds"]:.2f} |'
            for i, r in enumerate(rungs, 1)
        ] + [
            "",
            "The 17-frame block grid means a nominal one-second step lands 0.71–1.42 s",
            "away. The rungs are always distinct and always in order; they are simply",
            "not exactly a second apart.",
        ]) + "\n", encoding="utf8")

        index.append({
            "character": name, "slug": slug(name), "folder": folder.name,
            "line": pick["text"], "words": pick["words"],
            "seconds": round(frames / 24, 3), "frames": frames,
            "source_clip": clip["id"], "solo_clip": pick["solo"],
            "takes_to_render": TAKES_PER_CHARACTER,
            "seed_policy": "vary across the 3 takes; hold fixed while walking the ladder",
            "duration_ladder": rungs,
        })

    (out_root / "index.json").write_text(json.dumps(index, indent=2), encoding="utf8")

    total = sum(e["takes_to_render"] for e in index)
    lines = [
        "# Voice auditions — only the characters who actually need a master",
        "",
        "Only the **Narrator** is approved, from `narrator_omni_master_v2_source`.",
        "Every other master was cut from a take nobody listened to, and several are",
        "gibberish — which then poisons every clip that references them.",
        "",
        f"**{len(index)} characters · {TAKES_PER_CHARACTER} takes each · {total} renders**",
        f"at 0.2 MP, roughly {total * 5 / 60:.1f} hours.",
        "",
        f"## {len(skipped_one_off)} characters are deliberately NOT here",
        "",
        "A character who speaks in only **one** clip needs no voice master: there is",
        "nothing for them to be consistent with. Their voice is whatever that single",
        "render produces and it cannot contradict itself. Auditioning them would be",
        "renders spent choosing a voice that gets thrown away.",
        "",
        "Skipped: " + ", ".join(f"**{n}**" for n in sorted(skipped_one_off)) + ".",
        "",
        "Those clips get **no `<Audio N>` at all**. Four of them have no recurring",
        "speaker either and leave the reference path entirely, rendering on plain",
        "`MiniMaxH3ImageToVideo`: `01B`, `20B`, `22B`, `30B`. See",
        "`outputs/equal_shares/voice_requirements.json`.",
        "",
        "| # | Character | Line | Words | Duration | From |",
        "|---|---|---|---|---|---|",
    ]
    for i, e in enumerate(index, 1):
        snippet = e["line"][:44] + ("…" if len(e["line"]) > 44 else "")
        lines.append(f'| {i} | **{e["character"]}** | {snippet} | {e["words"]} | '
                     f'{e["seconds"]:.2f}s / {e["frames"]}f | `{e["source_clip"]}`'
                     f'{"" if e["solo_clip"] else " (not solo)"} |')
    lines += [
        "",
        "## The rules that make these come out clean",
        "",
        "1. **No audio reference.** Leave `ref_audios.ref_audio_0` disconnected.",
        "   You are choosing the voice, not matching one.",
        "2. **Paste `prompt.txt` exactly.** It begins `subject_definitions:` and",
        "   nothing may go above that line.",
        "3. **Vary only the seed** between the three takes.",
        "4. **Start at the stated frame count.** It is fitted to the line at the pace",
        "   measured from your 14 good clips.",
        "",
        "## When a take is wrong, change ONE knob",
        "",
        "| What is wrong | Knob | Why |",
        "|---|---|---|",
        "| Wrong voice — words are fine, but the timbre, age or accent is not the character | **Seed** | A different seed is a different invented voice. |",
        "| Wrong words — gibberish, slurring, a mispronunciation | **Duration ladder** | Words per second is fixed by the line and the window. The seed cannot change it, so re-rolling only buys a different flavour of the same problem. |",
        "",
        "The ladder is your rule: **base, +1, −1, +2, −2, +3, −3.** Each pack's",
        "README has its own precomputed table, since the 17-frame block grid means a",
        "nominal second is really 0.71–1.42 s. Hold the seed while walking it.",
        "",
        "```",
        "python work\\duration_ladder.py --seconds 10      <- any base length",
        "python work\\duration_ladder.py --clip 00B        <- a story clip's ladder",
        "```",
        "",
        "## After picking",
        "",
        "```",
        "outputs/equal_shares/voices/<slug>/omni_master_v2.wav     <- the winner",
        "python work\\sync_omni_audio_config.py                     <- wire it up",
        "python work\\speech_density.py <the-cut.wav>               <- confirm",
        "```",
        "",
        "Cut the master from **one contiguous speaking passage from one take** —",
        "never stitched. Then the full soundtrack pass can start.",
    ]
    (out_root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf8")

    print(f"{len(index)} audition packs -> {out_root}")
    print(f"{total} renders at 0.2 MP")
    for e in index[:6]:
        print(f'   {e["character"]:24s} {e["words"]:3d}w  {e["seconds"]:5.2f}s  '
              f'{e["frames"]:3d}f  from {e["source_clip"]}'
              f'{"" if e["solo_clip"] else "  (not solo)"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
