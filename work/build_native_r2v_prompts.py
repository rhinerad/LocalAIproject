#!/usr/bin/env python3
"""Rewrite all 124 clip prompts into MiniMax H3's NATIVE full-reference format.

WHY
---
The project's prompts have never used the format H3 was trained on. The official
guides are:

  base  https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md
  ref   https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md

Five differences, and the first one is probably the doubled-voice bug:

1. **`retention_analysis` is a required section** that declares, per reference,
   whether the model should COPY it or merely REFERENCE it. The audio markers
   are `fully_copy`, `partially_copy`, `reference`, `weak_reference`. The project
   never emitted this section, so nothing ever told H3 that the voice master was
   a timbre reference rather than a source to copy. A partial copy of the master
   laid under freshly generated speech is exactly the reported symptom. The guide
   also states outright: "When only timbre, rhythm, emotion, or delivery is
   referenced, do not carry the original dialogue from the reference audio into
   the target video."

2. **Dialogue is `<d>[English] ...</d>`**, not quotation marks. Quotes are
   reserved for text visibly rendered on screen.

3. **`[Shot N]` marks a CUT, not a beat.** A continuous take is a single
   `[Shot 1]` with no timestamp; timing inside it is expressed in prose. The
   project's `[0-1 s]` bracket notation is not the model's grammar.

4. **Speakers carry stable IDs** `(S1)`, `(S2)`, numbered by order of first
   vocal event, reused everywhere. Off-screen lines use the exact phrase
   `says in an off-screen voiceover` and must be followed by a statement that
   the on-screen character's lips stay closed.

5. **Six named sections** in fixed order: subject_definitions, summary,
   retention_analysis, detailed_description, overall_soundscape,
   non_diegetic_music.

Camera motion also has a controlled vocabulary -- Static Shot, Push In, Pan
Left, Truck Right, Pedestal Down, Tracking Shot and so on -- optionally
qualified by amplitude (`with small amplitude`) and speed (`at slow speed`).

Writes to outputs/equal_shares/prompts_native_r2v/. Existing prompt sets are
left untouched.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
OUT = EQ / "prompts_native_r2v"

BEAT_RE = re.compile(r"^\[\s*([\d.]+)\s*-\s*([\d.]+)\s*s?\s*\]\s*(.*)$")
QUOTE_RE = re.compile(r"[“\"]([^”\"]*)[”\"]")

# Motion phrasing from the base guide's camera table. Detected from the existing
# CAMERA block so the native vocabulary replaces free prose.
CAMERA_PATTERNS = [
    (r"locked[- ]off|static|does not move|never changes|tripod", "holds a static shot"),
    (r"descen|cranes? down|drops down|pedestal down", "pedestals down with large amplitude at slow speed"),
    (r"rise|cranes? up|pedestal up", "pedestals up with large amplitude at slow speed"),
    (r"push(es)? in|moves? (forward|closer)|closes on|dolly in", "pushes in with small amplitude at slow speed"),
    (r"pull(s)? (out|back)|dolly out|withdraw", "pulls out with small amplitude at slow speed"),
    (r"pans? (left|right)|pan across", "pans right with small amplitude at slow speed"),
    (r"truck|tracks? (left|right)|slides? sideways", "trucks right with small amplitude at slow speed"),
    (r"tilt", "tilts up with small amplitude at slow speed"),
    (r"follow|tracking", "holds a tracking shot"),
    (r"arc", "moves in an arc shot with small amplitude at slow speed"),
]

STATUS_ONSCREEN = {"ON-SCREEN", "ON-SCREEN THEN OFF"}
STATUS_OFFSCREEN = {"OFF-SCREEN", "OFF-SCREEN THEN ON", "DEVICE VOICE"}


def speaker_of(line: str) -> str:
    head = line.split("“")[0].split('"')[0]
    return re.split(r"[,:]", head)[0].strip()


def quote_of(line: str) -> str:
    m = QUOTE_RE.search(line)
    return m.group(1).strip() if m else ""


def delivery_of(line: str) -> str:
    """'Narrator, measured and ominously curious: "..."' -> 'measured and ominously curious'."""
    head = line.split("“")[0].split('"')[0]
    parts = re.split(r"[,:]", head)
    if len(parts) > 1:
        d = parts[1].strip().rstrip(":").strip()
        return d if d and len(d) < 80 else ""
    return ""


KNOWN_HEADERS = {
    "SHOT LIST and DIALOGUE TIMING", "SHOT LIST", "DIALOGUE TIMING", "DIALOGUE",
    "SPEAKERS IN THIS SHOT", "REFERENCE JOBS", "REFERENCES", "CAMERA", "CAST",
    "IDENTITY", "SET", "SET AND PROPS", "LOOK", "LIGHTING", "AUDIO", "DO NOT",
    "CAST - EXACT COUNT", "CAST — EXACT COUNT",
    "IDENTITY - HOLD THESE EXACTLY", "IDENTITY — HOLD THESE EXACTLY",
}


def parse_sections(text: str) -> dict[str, str]:
    """Split a prompt into sections.

    Headers are either fully capitalised or one of KNOWN_HEADERS. The explicit
    list matters: "SHOT LIST and DIALOGUE TIMING" carries a lowercase "and", so
    an all-caps test alone silently swallows every beat in the file -- which is
    exactly how a first run of this script produced 124 prompts with no dialogue.
    """
    out: dict[str, list[str]] = {}
    cur = "_preamble"
    for line in text.splitlines():
        s = line.strip()
        is_header = s in KNOWN_HEADERS or (
            bool(s) and s == s.upper()
            and re.fullmatch(r"[A-Z][A-Z /&'—-]*[A-Z]", s) is not None
            and len(s) <= 40
        )
        if is_header:
            cur = s
            out.setdefault(cur, [])
        else:
            out.setdefault(cur, []).append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def camera_phrase(camera_text: str) -> str:
    low = camera_text.lower()
    for pat, phrase in CAMERA_PATTERNS:
        if re.search(pat, low):
            return phrase
    return "holds a static shot"


def style_sentence(sections: dict[str, str]) -> str:
    look = sections.get("LOOK", "") or sections.get("LIGHTING", "")
    low = look.lower()
    if "black-and-white" in low or "black and white" in low or "monochrome" in low:
        return ("The target video is live-action in black-and-white 1960s anthology-television "
                "realism, flat and evenly lit with no colour anywhere in frame.")
    return ("The target video is live-action cinematic realism in full colour, evenly lit, "
            "with no stylisation.")


def build_speaker_ids(clip: dict) -> dict[str, str]:
    ids: dict[str, str] = {}
    for d in sorted(clip.get("dialogue_timing") or [], key=lambda x: float(x["start"])):
        name = speaker_of(d["line"])
        if name and name not in ids:
            ids[name] = f"S{len(ids)+1}"
    return ids


def status_map(sections: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    block = sections.get("SPEAKERS IN THIS SHOT", "")
    for raw in block.splitlines():
        m = re.match(r"^([A-Z][A-Za-z .'\-]+?)\s*[—-]\s*([A-Z][A-Z\- ]*[A-Z])\b", raw.strip())
        if m:
            out[m.group(1).strip()] = m.group(2).strip()
    return out


def pronoun_for(name: str, sections: dict[str, str]) -> str:
    """he / she / they, read from the character's own identity clause."""
    clause = identity_line(name, sections).lower()
    if re.search(r"\bshe\b|\bher\b|\bwoman\b|\bwomen\b", clause):
        return "she"
    if re.search(r"\bhe\b|\bhis\b|\bhim\b|\bman\b|\bmen\b", clause):
        return "he"
    return "they"


def identity_line(name: str, sections: dict[str, str]) -> str:
    """Pull this character's clause out of the IDENTITY block."""
    ident = (sections.get("IDENTITY", "")
             or sections.get("IDENTITY - HOLD THESE EXACTLY", "")
             or sections.get("IDENTITY — HOLD THESE EXACTLY", ""))
    chunks = re.split(r"(?<=[.;])\s+", ident)
    keep: list[str] = []
    for i, chunk in enumerate(chunks):
        if name.lower() in chunk.lower():
            keep.append(chunk.strip())
            # a description usually runs on past the naming sentence
            for nxt in chunks[i + 1:]:
                if re.match(r"^(The |[A-Z][a-z]+ [A-Z])", nxt.strip()) or "Every face" in nxt:
                    break
                keep.append(nxt.strip())
            break
    text = " ".join(keep).strip().rstrip(".")
    if ":" in text:
        text = text.split(":", 1)[1].strip()
    return text


def beats_to_prose(sections: dict[str, str], clip: dict, ids: dict[str, str],
                   smap: dict[str, str], subj: dict[str, str],
                   audio_tag: dict[str, int] | None = None) -> str:
    """Fold the timed beats into one continuous-shot narration.

    `audio_tag` maps a speaker to the `<Audio N>` number actually assigned in
    subject_definitions, or omits them entirely when they have no reference (a
    one-off speaker). It must be the caller's numbering: tags follow connection
    order, so recomputing it here from speaker position reintroduces the
    off-by-one fixed on 2026-08-18.
    """
    audio_tag = audio_tag or {}
    body = sections.get("SHOT LIST and DIALOGUE TIMING") or sections.get("SHOT LIST") or ""
    beats = []
    for raw in body.splitlines():
        m = BEAT_RE.match(raw.strip())
        if m:
            beats.append((float(m.group(1)), float(m.group(2)), m.group(3).strip()))
    if not beats:
        return ""

    # how many lines each speaker has, so "nothing further" is only ever
    # attached to their last one
    total_lines: dict[str, int] = {}
    for d in clip.get("dialogue_timing") or []:
        nm = speaker_of(d["line"])
        if nm:
            total_lines[nm] = total_lines.get(nm, 0) + 1
    emitted: dict[str, int] = {}

    said: set[str] = set()
    out: list[str] = []
    for start, end, text in beats:
        # lift any quoted dialogue out of the beat and re-emit it natively
        parts: list[str] = []
        rest = text
        for m in list(QUOTE_RE.finditer(text)):
            frag = m.group(1).strip()
            pre = rest[: rest.find(m.group(0))] if m.group(0) in rest else ""
            who = None
            mm = re.search(r"([A-Z][A-Za-z .'\-]+?)\s+(?:says|continues)", pre)
            if mm:
                who = mm.group(1).strip()
            if who is None:
                for nm in ids:
                    if nm.lower() in pre.lower():
                        who = nm
                        break
            if who is None:
                continue
            sid = ids.get(who, "S1")
            label = subj.get(who)
            tag = f"{label} ({sid})" if label else f"{who} ({sid})"
            off = smap.get(who, "ON-SCREEN") in STATUS_OFFSCREEN

            first = who not in said
            said.add(who)
            intro = ""
            if first:
                dl = delivery_of(
                    next((d["line"] for d in clip["dialogue_timing"]
                          if speaker_of(d["line"]) == who), "")
                )
                voice = f", in a {dl} delivery" if dl else ""
                # Use the tag actually assigned above, not the speaker's position.
                # A one-off speaker has no tag and is simply described, not
                # referenced -- see the audio-reference block for the measurement.
                t = audio_tag.get(who)
                intro = ((f"using the voice timbre referenced from <Audio {t}>{voice}, ")
                         if t else (f"{voice.lstrip(', ')}, " if voice else ""))
            # The official examples always close the speaker's mouth in the
            # clause immediately after </d>:
            #   "...<d>[English] Hey! Watch your dog!</d> She closes her lips..."
            #   "...<d>[English] He just likes cookies more than me.</d> He closes
            #    his mouth into an apologetic smile..."
            # Anything describing voice or delivery AFTER the tag reads as speech
            # still in progress, and H3 fills the remaining time with invented
            # syllables. Delivery goes before the tag; the mouth closes after it.
            pro = pronoun_for(who, sections)
            poss = {"he": "his", "she": "her", "they": "their"}[pro]
            plural = pro == "they"
            verb = "close" if plural else "closes"
            say_v = "say" if plural else "says"
            be_v = "are" if plural else "is"
            emitted[who] = emitted.get(who, 0) + 1
            is_last = emitted[who] >= total_lines.get(who, 1)
            close = f" {pro.capitalize()} {verb} {poss} mouth"
            close += (f" and {say_v} nothing further for the rest of the shot."
                      if is_last else f" and {be_v} silent until {poss} next line.")
            if off:
                parts.append(
                    f"{tag} {intro}says in an off-screen voiceover: "
                    f"<d>[English] {frag}</d> while every visible mouth in frame "
                    f"remains completely closed, and no one speaks again afterwards."
                )
            else:
                parts.append(f"{tag} {intro}says: <d>[English] {frag}</d>{close}")
            rest = rest.replace(m.group(0), "")

        # strip the now-duplicated speech attributions from the action text
        action = QUOTE_RE.sub("", text)
        # Remove any clause that describes the speaker's voice or delivery. Left
        # in place after </d> these read as "still talking" and produce a tail of
        # gibberish once the scripted words run out.
        action = re.sub(
            r"[^.;]*\b(delivery|intonation|cadence|inflection|tone of voice|"
            r"holds the (question|line|word)|voice (cools|warms|drops|rises|hardens|softens))"
            r"\b[^.;]*[.;]?", "", action, flags=re.I)
        action = re.sub(r"\b[A-Z][A-Za-z .'\-]*\s+(says|continues)\s+(on screen|off screen|"
                        r"on screen at first, then off screen|off screen at first, then on screen|"
                        r"from the device[^.]*)?\.?", "", action)
        action = re.sub(r"\s{2,}", " ", action).strip(" .;,")

        seg = " ".join(p for p in parts if p)
        if action:
            seg = (seg + " " + action + ".") if seg else (action + ".")
        if seg:
            out.append(seg.strip())

    return " ".join(out)


def build_clip(clip: dict, src_text: str, masters: dict,
               needs_master: dict | None = None) -> str | None:
    needs_master = needs_master or {}
    cid = clip["id"]
    sections = parse_sections(src_text)
    ids = build_speaker_ids(clip)
    smap = status_map(sections)

    subj: dict[str, str] = {}
    defs: list[str] = []
    n = 0
    for name in ids:
        n += 1
        subj[name] = f"<Subject {n}>"
        idl = identity_line(name, sections)
        src_img = " in <Picture 1>" if clip.get("first_frame") else ""
        defs.append(
            f"<Subject {n}> is {name}{src_img}"
            + (f", {idl}" if idl else "")
            + "."
        )

    set_text = (sections.get("SET") or sections.get("SET AND PROPS") or "").strip()
    if set_text:
        n += 1
        set_label = f"<Subject {n}>"
        first_sentence = re.split(r"(?<=[.])\s+", set_text)[0].rstrip(".")
        defs.append(f"{set_label} is the location of this shot: {first_sentence}.")
    else:
        set_label = None

    pics = []
    if clip.get("first_frame"):
        defs.append("<Picture 1> is the first frame of [Shot 1].")
        pics.append(("<Picture 1>", "[Shot 1] first frame"))
    if clip.get("last_frame"):
        defs.append("<Picture 2> is the final frame of [Shot 1].")
        pics.append(("<Picture 2>", "[Shot 1] final frame"))

    # --- audio references ---------------------------------------------------
    #
    # TWO FIXES HERE, 2026-08-18. Both matter.
    #
    # 1. THE ONE-OFF RULE. A character who speaks in only one clip gets NO
    #    <Audio N>, even if a provisional master file happens to exist on disk.
    #    There is nothing for them to be consistent with, so the reference buys
    #    nothing and costs a slot out of H3's three. Classification comes from
    #    work/classify_voice_requirements.py; never recount speakers here.
    #
    # 2. AN OFF-BY-ONE THAT WAS ALREADY LIVE. This block used to number tags by
    #    the speaker's position in the clip (`enumerate(ids)`) while `continue`-ing
    #    past speakers with no master. Reference tags follow CONNECTION ORDER, so
    #    if the first speaker had no master the second was declared <Audio 2> and
    #    wired into ref_audio_0 -- the prompt describing a reference that is not
    #    there, and mis-attributing the one that is.
    #
    #    Measured before the fix: 4 mis-numbered tags across 27E, 28C and 00D2.
    #    27E declared <Audio 1/2/3> for Council member, Kent and Ryann Sally; under
    #    the one-off rule only Kent and Ryann get references, so the correct tags
    #    are <Audio 1> and <Audio 2>. Tags are now assigned sequentially in the
    #    order the sockets are filled.
    audios = []
    audio_tag: dict[str, int] = {}
    for name in ids:
        if not needs_master.get(name, True):
            continue                       # one-off speaker: no reference at all
        if not masters.get(name):
            continue                       # recurring but no master yet
        i = len(audios) + 1                # sequential, == ref_audio_{i-1}
        audio_tag[name] = i
        defs.append(
            f"<Audio {i}> is the voice-timbre reference for {subj[name]} ({ids[name]}), "
            f"containing a single dry spoken English vocal layer."
        )
        audios.append((i, name))

    # --- summary -----------------------------------------------------------
    task = []
    if pics:
        task.append("keyframe completion")
    if audios:
        task.append("audio reference")
    if not task:
        task.append("reference generation")
    who = ", ".join(f"{subj[n2]} ({ids[n2]})" for n2 in ids) or "the people in frame"
    summary = (
        f"[{' + '.join(task)}] The target video is one continuous shot in which {who} "
        f"{'appear' if len(ids) != 1 else 'appears'}"
        + (f" in {set_label}" if set_label else "")
        + (". The shot begins exactly on <Picture 1>" if clip.get("first_frame") else ".")
        + (" and ends on <Picture 2>." if clip.get("last_frame") else "." if clip.get("first_frame") else "")
        + (f" {' and '.join(f'<Audio {i}>' for i, _ in audios)} "
           f"{'supply' if len(audios) > 1 else 'supplies'} voice timbre only and "
           f"{'are' if len(audios) > 1 else 'is'} never audible in the target video."
           if audios else "")
    )

    # --- retention analysis -------------------------------------------------
    ret: list[str] = []
    for name in ids:
        ret.append(
            f"{subj[name]} (appears in [Shot 1]): fully_preserved - {name}'s face, hair, "
            f"and clothing are identical in the last frame to the first."
        )
    if set_label:
        ret.append(
            f"{set_label} (appears in [Shot 1]): fully_preserved - every fixture and prop "
            f"stays in its established position for the whole shot."
        )
    for lbl, role in pics:
        ret.append(f"{lbl} ({role}): fully_preserved - the shot matches this composition exactly.")
    for i, name in audios:
        ret.append(
            f"<Audio {i}>: reference - {ids[name]} follows <Audio {i}>'s voice timbre, pitch, "
            f"accent, and delivery without copying the original signal; none of its words, "
            f"breaths, or room tone appear in the target video."
        )

    # --- detailed description ----------------------------------------------
    cam = camera_phrase(sections.get("CAMERA", ""))
    cast = (sections.get("CAST") or sections.get("CAST - EXACT COUNT")
            or sections.get("CAST — EXACT COUNT") or "").strip()
    cast_sentence = re.split(r"(?<=[.])\s+", cast)[0] if cast else ""
    prose = beats_to_prose(sections, clip, ids, smap, subj, audio_tag)

    dd = [style_sentence(sections)]
    open_line = "[Shot 1] The shot begins from <Picture 1>. " if clip.get("first_frame") else "[Shot 1] "
    open_line += f"The camera {cam} for the entire shot and there is no cut."
    if cast_sentence:
        open_line += " " + cast_sentence
    dd.append(open_line)
    if prose:
        dd.append(prose)
    if clip.get("last_frame"):
        dd.append("The shot ends on <Picture 2>, matching its composition exactly.")
    if ids:
        last_end = max(float(d["end"]) for d in clip["dialogue_timing"])
        total = float(clip.get("duration") or 0)
        tail = max(0.0, total - last_end)
        _n = [subj[n2] for n2 in ids]
        names = _n[0] if len(_n) == 1 else " and ".join([", ".join(_n[:-1]), _n[-1]])
        n_lines = len(clip["dialogue_timing"])
        WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
        count = WORD.get(n_lines, str(n_lines))
        dd.append(
            (f"There is only {count} spoken line in this entire shot, "
             if n_lines == 1 else
             f"There are only {count} spoken lines in this entire shot, ")
            + f"and {names} deliver{'s' if len(ids) == 1 else ''} "
            f"{'it' if n_lines == 1 else 'them'} at an unhurried natural "
            f"pace. When the last line is finished — however early in the shot that falls — "
            f"every voice stops. Nobody speaks, mutters, hums, sighs, or makes any vocal sound "
            f"for the whole remainder of the shot"
            + (f", roughly the final {tail:.0f} seconds," if tail >= 1.5 else "")
            + " and the shot plays out on room tone alone. No extra words are invented to fill "
              "the remaining time."
        )
    dd.append(
        "Nobody enters or leaves frame, no person is duplicated, and no face, hairstyle, "
        "facial hair, or item of clothing changes between the first frame and the last. "
        "No lettering, signage, labels, captions, subtitles, watermarks, or logos appear on "
        "any surface. No hand, finger, face, or limb is distorted or deformed."
    )

    # --- soundscape ---------------------------------------------------------
    soundscape = (
        "Quiet natural location room tone continues evenly throughout the shot, with only "
        "the physical action sounds the described movements would make. "
    )
    if ids:
        soundscape += (
            "Most of this shot has no speech in it at all, and silence is correct wherever "
            "no line is assigned. Never more than one voice at a time: no second voice, no "
            "quieter duplicate, no echo, no reverb tail, no whisper, no chorus, and no "
            "backing vocal under the speaker. Once the assigned lines are finished the "
            "voices stop and only room tone continues to the final frame."
        )
    else:
        soundscape += "No one speaks at any point in this shot."

    parts = [
        "subject_definitions:",
        "\n".join(defs) if defs else "N/A",
        "",
        "summary:",
        summary,
        "",
        "retention_analysis:",
        "\n".join(ret) if ret else "N/A",
        "",
        "detailed_description:",
        "\n".join(dd),
        "",
        "overall_soundscape:",
        soundscape,
        "",
        "non_diegetic_music:",
        "N/A",
    ]
    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    cfg = json.loads((EQ / "story_config.json").read_text(encoding="utf8"))
    try:
        vmap = json.loads((EQ / "omni_voice_master_map.json").read_text(encoding="utf8"))
        masters = vmap.get("references", {})
    except Exception:
        masters = {}

    # The one-off rule (operator, 2026-08-18). A character who speaks in a single
    # clip gets no <Audio N>, even when a provisional master exists on disk --
    # several one-offs do have one, and using it wastes a slot out of H3's three
    # and conditions a voice nothing needs to match.
    req_path = EQ / "voice_requirements.json"
    if not req_path.is_file():
        raise SystemExit("run work/classify_voice_requirements.py first — "
                         "voice_requirements.json is missing")
    req = json.loads(req_path.read_text(encoding="utf8"))
    needs_master = {n: c["needs_voice_master"] for n, c in req["characters"].items()}
    one_off = sorted(n for n, v in needs_master.items() if not v)

    OUT.mkdir(parents=True, exist_ok=True)
    written, skipped, no_master = 0, [], set()

    for clip in cfg["clips"]:
        cid = clip["id"]
        src = None
        for cand in (EQ / "prompts_audio_pass" / f"{cid}.txt",
                     EQ / "prompts_no_dialogue" / f"{cid}.txt"):
            if cand.exists():
                src = cand.read_text(encoding="utf8")
                break
        if src is None:
            src = clip.get("prompt", "")
        if not src.strip():
            skipped.append(cid)
            continue

        for d in clip.get("dialogue_timing") or []:
            nm = speaker_of(d["line"])
            # Only a RECURRING speaker missing a master is a problem. A one-off
            # is supposed to have none.
            if nm and nm not in masters and needs_master.get(nm, True):
                no_master.add(nm)

        text = build_clip(clip, src, masters, needs_master)
        if not args.check:
            (OUT / f"{cid}.txt").write_text(text, encoding="utf8")
        written += 1

    print(f"native R2V prompts written : {written}")
    if skipped:
        print(f"skipped (no source prompt) : {len(skipped)} {skipped[:8]}")
    print(f"one-off speakers, no <Audio N> : {len(one_off)}  {one_off}")
    if no_master:
        print(f"RECURRING speakers still missing a master: {sorted(no_master)}")
    if not args.check:
        print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
