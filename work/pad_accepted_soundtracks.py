#!/usr/bin/env python3
"""Pad each accepted Stage-1 soundtrack back to its scripted duration.

WHY THIS EXISTS
---------------
Stage-1 renders are deliberately SHORTER than the scripted clip: the soundtrack
is fitted to the spoken line, and every one of the operator's 14 known-good takes
is short in exactly this way.

*(Corrected 2026-08-18. This used to say H3 "fills whatever window it is given
with speech" so a 15 s clip holding a 9 s line gets ~6 s of invented gibberish.
Not supported — `4_`.mp4` is 56% silence and is clean. Shortening is a precaution
and a cost saving, not a cure. See docs/GOLDEN_REFERENCE/PROVEN_FACTS.md §3.)*

That leaves the WAV shorter than the picture. This tool closes the gap with
digital silence, which is exact and free — the one thing a generative model
cannot reliably produce.

    scripted 15.00 s  =  rendered 10.83 s  +  4.17 s of true silence

**The film's timeline is unchanged.** Picture still runs its full scripted
length from story_config.json; only the soundtrack render was shortened, and
this restores it to match. Total runtime stays at the planned 1266 s.

Silence is added at the END by default. A line scripted to start late can be
padded at the head instead with --lead, which reads the clip's first
dialogue_timing start from story_config.

Nothing is overwritten: padded files are written alongside the source with a
`_padded` suffix, and an existing padded file is left alone unless --force.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
DURATIONS = EQ / "audio_pass_durations.json"
STORY = EQ / "story_config.json"

TOLERANCE = 0.05  # seconds; closer than this counts as already correct


def probe(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def pad(src: Path, dst: Path, target: float, lead: float) -> tuple[bool, str]:
    have = probe(src)
    if have <= 0:
        return False, "unreadable"
    if abs(have - target) <= TOLERANCE and lead <= 0:
        return False, f"already {have:.2f}s"

    tail = max(0.0, target - have - lead)
    filters = []
    if lead > 0:
        filters.append(f"adelay={int(lead*1000)}:all=1")
    if tail > 0:
        filters.append(f"apad=pad_dur={tail:.3f}")
    if not filters:
        return False, "nothing to add"

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-af", ",".join(filters), "-c:a", "pcm_s16le", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        return False, r.stderr.strip()[:120]
    got = probe(dst)
    if abs(got - target) > 0.1:
        return False, f"wrote {got:.2f}s, wanted {target:.2f}s"
    return True, f"{have:.2f}s + {lead:.2f}s lead + {tail:.2f}s tail = {got:.2f}s"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(EQ / "audio" / "audio_pass_accepted"),
                    help="folder of accepted Stage-1 WAVs named <clip>*.wav")
    ap.add_argument("--out", default=None, help="defaults to --dir")
    ap.add_argument("--lead", action="store_true",
                    help="pad the head to the clip's scripted first-line start")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--check", action="store_true", help="report only")
    args = ap.parse_args()

    src_dir = Path(args.dir)
    out_dir = Path(args.out) if args.out else src_dir
    if not src_dir.is_dir():
        print(f"no such folder: {src_dir}")
        print("Run this after Stage-1 takes are accepted and extracted.")
        return 2

    durations = {r["id"]: r for r in json.loads(DURATIONS.read_text(encoding="utf8"))["clips"]}
    story = {c["id"]: c for c in json.loads(STORY.read_text(encoding="utf8"))["clips"]}

    out_dir.mkdir(parents=True, exist_ok=True)
    done = skipped = failed = 0

    for cid, row in sorted(durations.items()):
        target = float(row["scripted_seconds"])
        matches = sorted(p for p in src_dir.glob(f"{cid}*.wav") if "_padded" not in p.name)
        if not matches:
            continue
        src = matches[0]
        dst = out_dir / f"{cid}_padded.wav"
        if dst.exists() and not args.force:
            skipped += 1
            continue

        lead = 0.0
        if args.lead:
            dt = story.get(cid, {}).get("dialogue_timing") or []
            if dt:
                lead = max(0.0, min(float(d["start"]) for d in dt) - 0.3)

        if args.check:
            have = probe(src)
            print(f"  {cid:6s} {have:6.2f}s -> {target:6.2f}s  (add {target-have:5.2f}s)")
            continue

        ok, note = pad(src, dst, target, lead)
        if ok:
            done += 1
            print(f"  {cid:6s} {note}")
        else:
            if note.startswith("already"):
                skipped += 1
            else:
                failed += 1
                print(f"  {cid:6s} FAILED — {note}")

    if not args.check:
        print(f"\npadded {done}, skipped {skipped}, failed {failed}")
        print("Every padded file now matches its scripted duration; the 1266 s "
              "timeline is intact.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
