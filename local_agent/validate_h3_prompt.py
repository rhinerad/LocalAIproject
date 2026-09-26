#!/usr/bin/env python3
"""Strict validator for a MiniMax H3 native R2V prompt.

WHY THIS FILE IS THE MOST IMPORTANT ONE IN local_agent/
-------------------------------------------------------
A CPU-sized local model will produce prompts that are *nearly* right. Nearly
right is exactly what has cost this project the most: a prepended header on 124
prompts, a split `<d>` block, delivery prose after the closing tag, an `<Audio 2>`
wired into socket 0. Every one of those looked fine to a reader.

So the local agent is built on one rule: **the model may draft, but nothing
reaches a render until it passes this validator.** If it fails, the deterministic
generator's output is used instead. The LLM is never trusted, only checked.

Every rule below traces to a measurement in
`docs/GOLDEN_REFERENCE/PROVEN_FACTS.md` or to a render that failed.

USAGE
    python local_agent\\validate_h3_prompt.py <file.txt> [--expect-audio N]
    python local_agent\\validate_h3_prompt.py --dir outputs\\equal_shares\\prompts_native_r2v
    python local_agent\\validate_h3_prompt.py <file> --json

Exit 0 = valid. Exit 1 = has errors. Warnings alone do not fail.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SECTIONS = [
    "subject_definitions:",
    "summary:",
    "retention_analysis:",
    "detailed_description:",
    "overall_soundscape:",
    "non_diegetic_music:",
]

AUDIO_MARKERS = {"fully_copy", "partially_copy", "reference", "weak_reference"}

# Text that has been observed wrapping a generated prompt and corrupting it.
BANNED_PREFIXES = [
    "AUDIO-FIRST REFERENCE JOBS",
    "AUDIO-FIRST TARGET",
    "STRICT AUDIO RETRY",
    "REFERENCE JOBS",
    "One continuous unbroken take",
]


class Report:
    def __init__(self, name: str) -> None:
        self.name = name
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, code: str, msg: str) -> None:
        self.errors.append(f"{code}: {msg}")

    def warn(self, code: str, msg: str) -> None:
        self.warnings.append(f"{code}: {msg}")

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"file": self.name, "valid": self.ok,
                "errors": self.errors, "warnings": self.warnings}


def validate(text: str, name: str = "<prompt>", expect_audio: int | None = None) -> Report:
    r = Report(name)
    body = text.rstrip()

    # ---- 1. nothing above subject_definitions --------------------------------
    # 15/15 known-good renders begin here with nothing before it. The prepended
    # header of 2026-08-17 is the single most expensive fault in this project.
    if not body.startswith("subject_definitions:"):
        head = body[:60].replace("\n", " / ")
        r.err("E01", f"must begin exactly with 'subject_definitions:' — starts {head!r}")
    for bad in BANNED_PREFIXES:
        if bad in body[:400] and not body.startswith("subject_definitions:"):
            r.err("E02", f"contains banned wrapper text {bad!r}")

    # ---- 2. all six sections, in order, once each ----------------------------
    positions = []
    for s in SECTIONS:
        hits = [m.start() for m in re.finditer(rf"^{re.escape(s)}\s*$", body, re.M)]
        if not hits:
            r.err("E03", f"missing required section '{s}'")
        elif len(hits) > 1:
            r.err("E04", f"section '{s}' appears {len(hits)} times; must appear once")
        else:
            positions.append((s, hits[0]))
    if len(positions) == len(SECTIONS):
        order = [s for s, _ in sorted(positions, key=lambda x: x[1])]
        if order != SECTIONS:
            r.err("E05", f"sections out of order: {' -> '.join(x.rstrip(':') for x in order)}")

    def section(nameL: str) -> str:
        m = re.search(rf"^{re.escape(nameL)}\s*$(.*?)(?=^\w+:\s*$|\Z)", body, re.M | re.S)
        return m.group(1).strip() if m else ""

    defs = section("subject_definitions:")
    ret = section("retention_analysis:")
    desc = section("detailed_description:")
    sound = section("overall_soundscape:")
    music = section("non_diegetic_music:")

    # ---- 3. dialogue ---------------------------------------------------------
    d_blocks = re.findall(r"<d>(.*?)</d>", body, re.S)
    for i, d in enumerate(d_blocks, 1):
        if not d.lstrip().startswith("[English]"):
            r.err("E06", f"<d> block {i} does not open with '[English] '")
        if "<d>" in d or "</d>" in d:
            r.err("E07", f"<d> block {i} is nested or unterminated")
    if body.count("<d>") != body.count("</d>"):
        r.err("E08", f"unbalanced dialogue tags: {body.count('<d>')} <d> vs {body.count('</d>')} </d>")

    # One scripted line, one <d> block. A line split across two blocks puts
    # gibberish at the seam — measured on 00B, where a hand-written prompt broke
    # a sentence in two and the render produced ~1 s of noise at exactly that
    # point. A GENUINE second line always has a speaker introduction between the
    # blocks ("<Subject 2> (S2) ... says:"), so a short gap with no speaker
    # marker is a split line rather than a new one.
    for m in re.finditer(r"</d>(.*?)<d>", body, re.S):
        gap = m.group(1)
        if len(gap.strip()) < 25 or not re.search(r"\(S\d+\)|says|asks|replies", gap):
            r.err("E17", f"two <d> blocks separated by only {len(gap.strip())} characters "
                         f"with no speaker introduction — this is one line split in two, "
                         f"which puts gibberish at the seam. Gap: {gap.strip()[:50]!r}")

    # Quotation marks mean ON-SCREEN LETTERING, not speech. A quoted string
    # inside detailed_description is how the project used to write dialogue and
    # is the format H3 was NOT trained on.
    for q in re.findall(r"[“\"]([^”\"\n]{12,})[”\"]", desc):
        r.warn("W01", f"quoted text in detailed_description reads as on-screen "
                      f"lettering, not speech: {q[:50]!r}")

    # Delivery prose after </d> reads as speech still in progress — measured on
    # 00B, which produced a tail of gibberish until this was moved before the tag.
    #
    # BUT the PRESCRIBED clause immediately after </d> is the mouth close, and it
    # contains the word "says": "He closes his mouth and says nothing further for
    # the rest of the shot." A first version of this check flagged that as a
    # fault and failed 12 of the project's 124 correct prompts. That is the same
    # class of error as the checker that failed 68 files by searching for a
    # singular verb, and the validator that rejected a known-good take. Strip the
    # sanctioned silence clauses first, then look for genuine delivery prose.
    SANCTIONED = re.compile(
        r"(clos(?:e|es|ed|ing)\s+(?:his|her|their|the)\s+(?:mouth|lips)"
        r"|says?\s+nothing\s+further"
        r"|is\s+silent\s+until"
        r"|are\s+silent\s+until"
        r"|no\s+further\s+words)", re.I)
    for m in re.finditer(r"</d>\s*([^<]{0,160})", body):
        tail = SANCTIONED.sub("", m.group(1))
        if re.search(r"\b(delivery|voice|tone|timbre|continues? to speak|keeps? speaking"
                     r"|goes on to say|adds)\b", tail, re.I):
            r.err("E09", f"delivery/voice prose appears AFTER </d> — reads as speech "
                         f"still in progress: {tail.strip()[:70]!r}")

    # ---- 4. reference tags ---------------------------------------------------
    def tags(kind: str, where: str) -> list[int]:
        return sorted({int(x) for x in re.findall(rf"<{kind} (\d+)>", where)})

    for kind in ("Subject", "Picture", "Audio"):
        declared = tags(kind, defs)
        used = tags(kind, body)
        if declared and declared != list(range(1, len(declared) + 1)):
            r.err("E10", f"<{kind} N> numbering not contiguous from 1 in "
                         f"subject_definitions: {declared}")
        undeclared = [n for n in used if n not in declared]
        if undeclared:
            r.err("E11", f"<{kind} {undeclared}> used but never declared in "
                         f"subject_definitions")

    audio_declared = tags("Audio", defs)
    if expect_audio is not None and len(audio_declared) != expect_audio:
        r.err("E12", f"declares {len(audio_declared)} <Audio N> but {expect_audio} "
                     f"reference(s) will be wired. Tags follow CONNECTION ORDER; a "
                     f"mismatch mis-attributes every voice in the clip.")

    # ---- 5. retention_analysis ----------------------------------------------
    # The section that fixed the doubled voice. Every audio reference needs a
    # line, and for a timbre master the marker is always `reference`.
    for n in audio_declared:
        line = next((l for l in ret.splitlines() if l.strip().startswith(f"<Audio {n}>")), None)
        if line is None:
            r.err("E13", f"<Audio {n}> has no retention_analysis line. Without it "
                         f"nothing tells H3 the master is a reference rather than a "
                         f"source to copy — this is the doubled-voice bug.")
            continue
        marker = next((m for m in AUDIO_MARKERS if re.search(rf"\b{m}\b", line)), None)
        if marker is None:
            r.err("E14", f"<Audio {n}> retention line declares no marker; expected "
                         f"one of {sorted(AUDIO_MARKERS)}")
        elif marker != "reference":
            r.warn("W02", f"<Audio {n}> marked '{marker}'. A voice-timbre master is "
                          f"always 'reference'; copy markers reproduce the original "
                          f"words.")
    for n in tags("Subject", defs) + tags("Picture", defs):
        pass  # visible-content markers vary legitimately; not enforced

    # ---- 6. house rules ------------------------------------------------------
    if music and music.strip() != "N/A":
        r.warn("W03", "non_diegetic_music is not 'N/A'. The continuous score is added "
                      "at assembly for this film.")
    # Scan the WHOLE prompt, not just detailed_description. A first version
    # checked only that section and missed a beat bracket sitting in
    # subject_definitions, where "<Picture 1> is the first frame of [Shot 1]"
    # lives — the exact place a stray timestamp is most likely to be pasted.
    if re.search(r"\[\s*\d+(\.\d+)?\s*-\s*\d+(\.\d+)?\s*s?\s*\]", body):
        r.err("E15", "beat brackets like '[0-1 s]' are not H3 grammar. A continuous "
                     "take is one [Shot 1] with timing expressed in prose.")
    shots = sorted({int(x) for x in re.findall(r"\[Shot (\d+)\]", body)})
    if shots and shots != list(range(1, len(shots) + 1)):
        r.err("E16", f"[Shot N] numbering not contiguous from 1: {shots}")
    if d_blocks and not sound.strip():
        r.warn("W04", "overall_soundscape is empty on a clip that has dialogue")

    # A speaker who never gets their mouth closed after their final line tends to
    # keep talking — two of the guide's three examples close the mouth explicitly.
    if d_blocks and not re.search(r"close[sd]?\s+(their|his|her)\s+(mouth|lips)", body, re.I):
        r.warn("W05", "no 'closes their mouth' clause after any line")

    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?")
    ap.add_argument("--dir")
    ap.add_argument("--expect-audio", type=int, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    targets: list[Path] = []
    if args.dir:
        targets = sorted(Path(args.dir).glob("*.txt"))
    elif args.path:
        targets = [Path(args.path)]
    else:
        ap.error("give a file or --dir")

    reports = [validate(p.read_text(encoding="utf8"), p.name, args.expect_audio)
               for p in targets if p.is_file()]

    if args.json:
        print(json.dumps([r.as_dict() for r in reports], indent=2))
    else:
        bad = [r for r in reports if not r.ok]
        warn_only = [r for r in reports if r.ok and r.warnings]
        for r in bad:
            print(f"INVALID  {r.name}")
            for e in r.errors:
                print(f"    {e}")
            for w in r.warnings:
                print(f"    (warn) {w}")
        if len(reports) > 1:
            print(f"\n{len(reports) - len(bad)}/{len(reports)} valid"
                  + (f", {len(warn_only)} with warnings" if warn_only else ""))
        elif reports and reports[0].ok:
            print(f"VALID    {reports[0].name}")
            for w in reports[0].warnings:
                print(f"    (warn) {w}")
    return 1 if any(not r.ok for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
