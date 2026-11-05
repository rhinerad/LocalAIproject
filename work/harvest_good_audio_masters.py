#!/usr/bin/env python3
"""Harvest voice references from the operator's hand-made good-audio takes.

WHAT THIS FOLDER IS
-------------------
`A:\\Users\\rhine\\ComfyUI-Shared\\output\\video\\good audio\\` holds takes the
operator rendered by hand and confirmed by ear: correct words, one dry voice, no
doubling. They were rendered at SPEECH length, not scene length. They are the
best audio this project has produced and they are the source for voice
references.

WHAT IS ACTUALLY IN IT — verified 2026-08-18, not assumed
---------------------------------------------------------
Each MP4 carries its full API graph (`ffprobe -show_entries format_tags=prompt`).
Every take was identified from its own embedded prompt and matched to
`story_config.json` by dialogue text. All 16 matched at 100% string similarity.

    2.mp4   -> 00A      6_.mp4  -> 00E      12.mp4 -> 00L
    3-1.mp4 -> 00C      7-.mp4  -> 00F      13.mp4 -> 00M
    4_`.mp4 -> 00D      8-.mp4  -> 00G      14.mp4 -> 00N
    5-.mp4  -> 00D2     9-.mp4  -> 00I      15.mp4 -> 00O
    10-.mp4 -> 00J      11.mp4  -> 00K
    16_dummyclip / 17.mp4 -> no dialogue

**The important finding: 14 of the 14 speaking takes are the NARRATOR.** This is
the opening narration run, 00A through 00O, with 00B and 00H skipped — which is
the gap the operator remembered. Two takes carry a second voice as well:

    00D  (4_`.mp4)   Narrator + Male Visitor One
    00D2 (5-.mp4)    Narrator + Male Visitor One + Male Visitor Two

So this folder can supply **three** voices at most: Narrator, Male Visitor One,
Male Visitor Two. It cannot supply Kent, Avery, Doris, Ryann, Faith, or any of
the other eleven — none of them speaks anywhere in it. Those still need the
audition pass.

THE LEADING ARTIFACT
--------------------
The operator reports an 'hmpf' at the head of almost every take. Measured: **12
of 16** open with a short burst at t=0.02 s lasting 0.08-0.38 s, peaking between
-11 and -27 dBFS, followed by 0.2-1.2 s of room tone before the first real word.
The other four (`2`, `12`, `13`, `16_dummyclip`) have no such burst.

This script does NOT cut a flat one second. A flat cut would take 0.62 s of real
speech off `6_.mp4`, whose trim point is 0.38 s, and would leave 0.60 s of the
artifact in `11.mp4`, whose trim point is 1.60 s. Instead each file is measured
and trimmed to just before its first sustained speech run, keeping 80 ms of air.

Why it matters more for a reference than for a take: an `<Audio N>` reference is
timbre conditioning. A non-speech vocal burst inside it is a characteristic H3
can reproduce, and this project has already shipped one voice master that was
road noise.

RULES OBSERVED
--------------
- **Never stitched.** Each master is one contiguous passage from one take, per
  CLAUDE.md. Concatenating appearances is prohibited.
- **Never overwritten.** Output is a versioned sibling; an existing file with the
  same name aborts the write.
- **Nothing deleted.** Sources are read-only; every trimmed take is preserved
  alongside the chosen master.
- **Nothing accepted.** This script selects candidates mechanically and marks
  them `pending_ear_review`. It cannot hear.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
try:
    import soundfile as sf
except ModuleNotFoundError:  # metadata/audio analysis still works without WAV writing
    sf = None

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
DEFAULT_SRC = Path(r"A:\Users\rhine\ComfyUI-Shared\output\video\good audio")

SR = 24000                  # masters are written at 24 kHz mono
HOP = 0.02                  # envelope frame, seconds
LOUD_OVER_FLOOR_DB = 12     # a frame is "loud" this far above the noise floor
BRIDGE_GAP = 0.25           # gaps shorter than this are inter-word, not silence
AIR_BEFORE = 0.08           # keep this much room tone before the first word
ARTIFACT_MAX_LEN = 0.60     # a leading run longer than this is speech, not a burst
ARTIFACT_MAX_START = 0.15   # ...and it has to start at the very top
ARTIFACT_MIN_GAP = 0.20     # ...and be followed by real silence
TARGET_SECONDS = 6.0        # the reliability target for a master


# ---------------------------------------------------------------- identification

def embedded_graph(mp4: Path) -> dict | None:
    """The API graph ComfyUI embeds in every MP4. Ground truth, not a guess."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=prompt",
         "-of", "json", str(mp4)], capture_output=True, text=True)
    try:
        return json.loads(json.loads(r.stdout)["format"]["tags"]["prompt"])
    except Exception:
        return None


def graph_facts(g: dict) -> dict:
    """Pull the facts out of one graph.

    BUG FIXED 2026-08-18: this used to read the prompt ONLY from
    `PrimitiveStringMultiline` nodes. Some graphs put the prompt inline on the
    sampler node's own `prompt` input instead, and `17.mp4` is one of them — so
    this function returned an empty prompt for it, and the harvest reported
    "17.mp4, no dialogue". That was wrong: 17.mp4 is clip 01B with two spoken
    lines. Any node input literally named `prompt` is now considered too.
    """
    prompt, nominal, seed, audio_ref = "", None, None, None
    for node in g.values():
        ct, ins = node.get("class_type"), node.get("inputs", {})
        inline = ins.get("prompt")
        if isinstance(inline, str) and len(inline) > len(prompt):
            prompt = inline
        if ct == "PrimitiveStringMultiline" and len(str(ins.get("value", ""))) > len(prompt):
            prompt = ins["value"]
        elif ct == "PrimitiveFloat":
            nominal = ins.get("value")
        elif ct == "RandomNoise":
            seed = ins.get("noise_seed")
        elif ct == "VHS_LoadVideoPath":
            audio_ref = str(ins.get("video", "")).strip('"')
        elif ct == "LoadAudio":
            audio_ref = ins.get("audio")
    return {
        "prompt": prompt,
        "nominal_seconds": nominal,
        "seed": seed,
        "audio_reference": audio_ref,
        "starts_with_subject_definitions": prompt.startswith("subject_definitions:"),
        "dialogue": [" ".join(x.split())
                     for x in re.findall(r"<d>\[English\]\s*(.*?)</d>", prompt, re.S)],
    }


def script_lines() -> list[tuple[str, str, str]]:
    cfg = json.loads((EQ / "story_config.json").read_text(encoding="utf8"))
    out = []
    for c in cfg["clips"]:
        for d in c.get("dialogue_timing") or []:
            m = re.search(r"[\u201c\"]([^\u201d\"]*)[\u201d\"]", d["line"])
            if not m:
                continue
            head = d["line"].split("\u201c")[0].split('"')[0]
            out.append((c["id"], re.split(r"[,:]", head)[0].strip(),
                        " ".join(m.group(1).split())))
    return out


def identify(facts: dict, lines: list) -> dict:
    """Match each spoken line to the script. Never trust filename order."""
    hits = []
    for text in facts["dialogue"]:
        best = max(lines, key=lambda L: difflib.SequenceMatcher(
            None, L[2][:90], text[:90]).ratio())
        ratio = difflib.SequenceMatcher(None, best[2][:90], text[:90]).ratio()
        hits.append({"clip": best[0], "speaker": best[1],
                     "confidence": round(ratio, 3), "text": text})
    return {"clip": hits[0]["clip"] if hits else None,
            "speakers": [h["speaker"] for h in hits], "matches": hits}


# ------------------------------------------------------------------- audio work

def load_mono(mp4: Path, sr: int = SR) -> np.ndarray:
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp4), "-vn", "-ac", "1",
         "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype="float32")


def speech_runs(a: np.ndarray, sr: int = SR) -> list[tuple[float, float]]:
    hop = int(HOP * sr)
    if len(a) < hop * 2:
        return []
    fr = np.array([20 * np.log10(max(1e-6, float(np.sqrt((a[i:i + hop] ** 2).mean()))))
                   for i in range(0, len(a) - hop, hop)])
    loud = fr > np.percentile(fr, 10) + LOUD_OVER_FLOOR_DB
    runs, i = [], 0
    while i < len(loud):
        if loud[i]:
            j = i
            while j + 1 < len(loud) and loud[j + 1]:
                j += 1
            runs.append((i * HOP, (j + 1) * HOP))
            i = j + 1
        else:
            i += 1
    merged: list[list[float]] = []
    for s, e in runs:
        if merged and s - merged[-1][1] < BRIDGE_GAP:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


def analyse(a: np.ndarray, sr: int = SR) -> dict:
    """Find the leading burst, if any, and where the real speech starts."""
    runs = speech_runs(a, sr)
    artifact = None
    body = runs
    if (runs and runs[0][0] < ARTIFACT_MAX_START
            and runs[0][1] - runs[0][0] < ARTIFACT_MAX_LEN
            and len(runs) > 1 and runs[1][0] - runs[0][1] > ARTIFACT_MIN_GAP):
        artifact, body = runs[0], runs[1:]
    trim = max(0.0, (body[0][0] if body else 0.0) - AIR_BEFORE)
    peak = None
    if artifact:
        seg = a[int(artifact[0] * sr):int(artifact[1] * sr)]
        if len(seg):
            peak = round(float(20 * np.log10(max(1e-6, np.abs(seg).max()))), 1)
    longest = max((e - s for s, e in body), default=0.0)
    return {
        "leading_artifact": [round(x, 3) for x in artifact] if artifact else None,
        "leading_artifact_peak_dbfs": peak,
        "trim_seconds": round(trim, 3),
        "speech_runs_after_trim": [(round(s - trim, 2), round(e - trim, 2)) for s, e in body],
        "speech_seconds": round(sum(e - s for s, e in body), 2),
        "longest_contiguous": round(longest, 2),
    }


# ----------------------------------------------------------------------- output

def write_wav(path: Path, a: np.ndarray, sr: int = SR, *, allow_overwrite=False) -> None:
    if sf is None:
        raise RuntimeError("soundfile is required to write harvested WAV masters")
    if path.exists() and not allow_overwrite:
        raise FileExistsError(
            f"{path} exists. Masters are versioned siblings, never overwritten "
            f"(CLAUDE.md). Bump the version instead.")
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, a, sr, subtype="PCM_16")


def next_version(folder: Path, stem: str) -> Path:
    n = 1
    while (folder / f"{stem}_v{n}.wav").exists():
        n += 1
    return folder / f"{stem}_v{n}.wav"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(DEFAULT_SRC), help="the good-audio folder")
    ap.add_argument("--out", default=str(EQ / "voices" / "_good_audio_trimmed"),
                    help="where the trimmed takes are written for review")
    ap.add_argument("--write-masters", action="store_true",
                    help="also cut and write the selected voice masters")
    ap.add_argument("--report", default=str(EQ / "good_audio_harvest.json"))
    args = ap.parse_args()

    src = Path(args.src)
    if not src.is_dir():
        print(f"no such folder: {src}", file=sys.stderr)
        return 2

    lines = script_lines()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    for mp4 in sorted(src.glob("*.mp4")):
        g = embedded_graph(mp4)
        if g is None:
            rows.append({"file": mp4.name, "error": "no embedded graph"})
            continue
        facts = graph_facts(g)
        ident = identify(facts, lines)
        a = load_mono(mp4)
        meas = analyse(a)
        trimmed = a[int(meas["trim_seconds"] * SR):]

        stem = f'{ident["clip"] or "nodialogue"}__{mp4.stem}'
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", stem)
        dest = out_dir / f"{safe}.trimmed.wav"
        write_wav(dest, trimmed, allow_overwrite=True)   # derived, regenerable

        rows.append({
            "file": mp4.name, "clip": ident["clip"], "speakers": ident["speakers"],
            "matches": ident["matches"],
            "source_seconds": round(len(a) / SR, 3),
            "nominal_seconds": facts["nominal_seconds"],
            "seed": facts["seed"],
            "audio_reference": facts["audio_reference"],
            "prompt_starts_correctly": facts["starts_with_subject_definitions"],
            "trimmed_file": str(dest),
            "trimmed_seconds": round(len(trimmed) / SR, 3),
            **meas,
        })

    # ---- master selection: one contiguous passage, one take, never stitched
    #
    # "Contiguous passage" means first word to last word INSIDE ONE TAKE, with
    # the natural pauses left in. The pauses are part of the performance and
    # cutting them out would be stitching, which CLAUDE.md prohibits. What is
    # prohibited is joining passages from different takes or appearances.
    #
    # Selection is by the longest such passage among the takes where the target
    # is the ONLY speaker, so no other voice can leak into the reference.
    masters = []
    solo = [r for r in rows if r.get("speakers") and set(r["speakers"]) == {"Narrator"}]
    for r in solo:
        runs = r["speech_runs_after_trim"]
        r["_span"] = round(runs[-1][1] - runs[0][0], 2) if runs else 0.0
        r["_density"] = round(r["speech_seconds"] / r["_span"], 3) if r["_span"] else 0.0
    if solo:
        # longest passage, then densest — a long passage that is mostly silence
        # is a worse reference than a shorter continuous one
        best = max(solo, key=lambda r: (r["_span"], r["_density"]))
        a = np.asarray(sf.read(best["trimmed_file"])[0], dtype="float32")
        runs = best["speech_runs_after_trim"]
        s, e = (runs[0][0], runs[-1][1]) if runs else (0.0, len(a) / SR)
        seg = a[int(max(0, s - AIR_BEFORE) * SR):int(min(len(a) / SR, e + AIR_BEFORE) * SR)]
        masters.append({
            "character": "Narrator", "slug": "narrator",
            "source": best["file"], "clip": best["clip"],
            "passage": [round(s, 2), round(e, 2)],
            "seconds": round(len(seg) / SR, 2),
            "speech_density": best["_density"],
            "short_master": len(seg) / SR < TARGET_SECONDS,
            "contiguous_single_take": True,
            "status": "pending_ear_review",
            "audio": seg,
        })

    # ---- the two male visitors: CANDIDATES ONLY, not masters
    #
    # Their lines sit inside takes where the Narrator also speaks (00D, 00D2),
    # so isolating them means deciding which run belongs to whom. The scripted
    # dialogue_timing cannot be used for that: these takes were rendered at
    # speech length, not scene length, so the script's timestamps do not map
    # onto them. The Narrator speaks first in both, so the trailing runs are the
    # visitors -- but that is inference, and this script cannot hear. They are
    # written to the review folder clearly labelled and are NOT installed as
    # masters.
    candidates = []
    for r in rows:
        extra = [s for s in (r.get("speakers") or []) if s != "Narrator"]
        if not extra:
            continue
        a = np.asarray(sf.read(r["trimmed_file"])[0], dtype="float32")
        runs = r["speech_runs_after_trim"]
        for i, s_name in enumerate(reversed(sorted(set(extra)))):
            k = len(runs) - 1 - i
            if k <= 0:
                continue
            s, e = runs[k]
            seg = a[int(max(0, s - 0.05) * SR):int(min(len(a) / SR, e + 0.05) * SR)]
            slug = re.sub(r"[^a-z0-9]+", "_", s_name.lower()).strip("_")
            dest = out_dir / f'CANDIDATE_{slug}__{r["clip"]}__run{k}.wav'
            write_wav(dest, seg, allow_overwrite=True)
            candidates.append({
                "character": s_name, "slug": slug, "clip": r["clip"],
                "source": r["file"], "window": [round(s, 2), round(e, 2)],
                "seconds": round(len(seg) / SR, 2), "file": str(dest),
                "status": "unverified_candidate",
                "why_not_a_master": (
                    "speaker attribution is inferred from dialogue order inside a "
                    "multi-speaker take, not measured; needs an ear before use"),
            })

    for m in masters:
        folder = EQ / "voices" / m["slug"]
        m["path"] = str(next_version(folder, "omni_master_goodaudio"))
        if args.write_masters:
            write_wav(Path(m["path"]), m.pop("audio"))
        else:
            m.pop("audio")

    report = {
        "generated": "work/harvest_good_audio_masters.py",
        "source_folder": str(src),
        "identification_method": (
            "the API graph embedded in each MP4, matched to story_config.json by "
            "dialogue text; filename order was NOT trusted"),
        "takes": rows,
        "masters": masters,
        "unverified_candidates": candidates,
        "characters_this_folder_can_supply": sorted(
            {s for r in rows for s in r.get("speakers", [])}),
        "caveat": (
            "Mechanical selection only. Nothing here is accepted; every master is "
            "pending_ear_review. This folder contains no audio for any character "
            "outside the opening narration."),
    }
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf8")

    print(f'{"file":30s}{"clip":7}{"artifact":>13}{"trim":>7}{"speech":>8}{"longest":>9}  speakers')
    print("-" * 104)
    for r in rows:
        if r.get("error"):
            print(f'{r["file"]:30s}{r["error"]}')
            continue
        art = (f'{r["leading_artifact"][0]:.2f}-{r["leading_artifact"][1]:.2f}'
               if r["leading_artifact"] else "none")
        print(f'{r["file"]:30s}{str(r["clip"] or "-"):7}{art:>13}{r["trim_seconds"]:7.2f}'
              f'{r["speech_seconds"]:8.2f}{r["longest_contiguous"]:9.2f}  '
              f'{", ".join(r["speakers"]) or "(none)"}')
    n = sum(1 for r in rows if r.get("leading_artifact"))
    print(f'\n{n} of {len(rows)} takes carry the leading burst')
    print(f'characters available here: {", ".join(report["characters_this_folder_can_supply"])}')
    for m in masters:
        print(f'master  {m["character"]:16s} {m["seconds"]:5.2f}s '
              f'({m["speech_density"]:.0%} speech) from {m["source"]} ({m["clip"]})  '
              f'{"SHORT " if m["short_master"] else ""}-> {m["path"]}'
              + ("" if args.write_masters else "   [dry run, use --write-masters]"))
    for c in candidates:
        print(f'CANDIDATE (unverified, needs an ear)  {c["character"]:18s} '
              f'{c["seconds"]:5.2f}s from {c["source"]} ({c["clip"]})')
    print(f'report -> {args.report}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
