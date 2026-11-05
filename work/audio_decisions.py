"""Per-clip audio decisions: keep the H3 audio, or strip it and use the Kokoro track.

The project was built to discard every H3 audio track and mix one pre-rendered
dialogue timeline instead, because a fixed Kokoro voice per character cannot
drift. H3 re-derives a voice from the prompt on every clip, so its voices drift
the same way its faces do.

This adds the other half: keep H3 audio on the clips where it sounds good, and
fall back to Kokoro on the clips where it does not, decided per clip after review.

Nothing is decided at render time. The runner keeps writing silent assembly
copies and the raws keep their original audio, so a decision can be changed at
any point without regenerating anything.

DECISIONS
    keep     use the clip's own H3 audio in the master
    replace  strip it and take that span from EQUAL_SHARES_DIALOGUE_TIMELINE.wav
    (unset)  falls back to the configured default, which starts as "replace"

USAGE
    python work\\audio_decisions.py list
    python work\\audio_decisions.py set --keep 00D 00E --replace 00A 00B
    python work\\audio_decisions.py set --default keep
    python work\\audio_decisions.py build
    python work\\audio_decisions.py build --output audio\\MY_MIX.wav

`build` writes a hybrid dialogue timeline the length of the edit. Point
assemble_story.py at that file instead of EQUAL_SHARES_DIALOGUE_TIMELINE.wav to
use it; the score is mixed separately and is unaffected.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import wave

EQ = os.path.join("outputs", "equal_shares")
CONFIG = os.path.join(EQ, "story_config.json")
MANIFEST = os.path.join(EQ, "manifest.json")
AUDIT = os.path.join(EQ, "audio_audit.json")
KOKORO = os.path.join(EQ, "audio", "EQUAL_SHARES_DIALOGUE_TIMELINE.wav")
DEFAULT_OUT = os.path.join(EQ, "audio", "EQUAL_SHARES_HYBRID_DIALOGUE.wav")
STORY_ROOT = r"A:\Users\rhine\ComfyUI-Shared\output\story"

RATE, CHANNELS, WIDTH = 48000, 2, 2


def load_json(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8-sig") as fh:
        return json.load(fh)


def basename(p):
    return p.replace("\\", "/").rstrip("/").split("/")[-1]


def timeline(config):
    """Clip id -> (start, edit_duration), from cumulative edit_duration.
    This is the same basis the Kokoro timeline was laid to; it sums to 1266 s."""
    out, t = {}, 0.0
    for c in sorted(config["clips"], key=lambda x: x["sequence_order"]):
        ed = float(c.get("edit_duration", c["duration"]))
        out[c["id"]] = (t, ed)
        t += ed
    return out, t


def load_audit():
    return load_json(AUDIT, {"default": "replace", "clips": {}})


def save_audit(a):
    os.makedirs(os.path.dirname(AUDIT), exist_ok=True)
    with open(AUDIT, "w", encoding="utf-8") as fh:
        json.dump(a, fh, indent=2, ensure_ascii=False)


def decision_for(audit, cid):
    return audit["clips"].get(cid, {}).get("decision", audit.get("default", "replace"))


def cmd_list(args):
    cfg, audit = load_json(CONFIG), load_audit()
    man = load_json(MANIFEST, {"clips": {}})["clips"]
    tl, total = timeline(cfg)
    keep = rep = 0
    print(f"default = {audit.get('default')}   ({total:g}s edit)")
    print(f"{'clip':7}{'decision':10}{'start':>9}{'len':>7}  rendered  note")
    for c in sorted(cfg["clips"], key=lambda x: x["sequence_order"]):
        cid = c["id"]
        d = decision_for(audit, cid)
        rec = audit["clips"].get(cid, {})
        s, ln = tl[cid]
        keep += d == "keep"
        rep += d == "replace"
        print(f"{cid:7}{d:10}{s:9.2f}{ln:7.2f}  {'yes' if cid in man else 'no ':8}  {rec.get('reason','')}")
    print(f"\nkeep {keep} | replace {rep}")
    return 0


def cmd_set(args):
    audit = load_audit()
    if args.default:
        audit["default"] = args.default
        print(f"default -> {args.default}")
    for cid in args.keep or []:
        audit["clips"].setdefault(cid, {}).update(decision="keep", reason=args.reason or "")
    for cid in args.replace or []:
        audit["clips"].setdefault(cid, {}).update(decision="replace", reason=args.reason or "")
    for cid in args.clear or []:
        audit["clips"].pop(cid, None)
    save_audit(audit)
    if args.keep:
        print("keep    :", " ".join(args.keep))
    if args.replace:
        print("replace :", " ".join(args.replace))
    if args.clear:
        print("cleared :", " ".join(args.clear))
    print(f"written to {AUDIT}")
    return 0


def extract(src, start, dur, out, from_video):
    """Pull `dur` seconds of 48k stereo PCM out of src, starting at `start`."""
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if from_video:
        cmd += ["-i", src, "-vn"]
    else:
        cmd += ["-ss", f"{start:.3f}", "-i", src]
    cmd += ["-t", f"{dur:.3f}", "-ac", str(CHANNELS), "-ar", str(RATE),
            "-c:a", "pcm_s16le",
            "-af", f"apad=whole_dur={dur:.3f}", out]
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def has_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=codec_type", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    return "audio" in r.stdout


def cmd_build(args):
    cfg, audit = load_json(CONFIG), load_audit()
    man = load_json(MANIFEST, {"clips": {}})["clips"]
    tl, total = timeline(cfg)
    if not os.path.exists(KOKORO):
        print(f"missing {KOKORO}", file=sys.stderr)
        return 2

    tmp = os.path.join(EQ, "audio", "_hybrid_parts")
    os.makedirs(tmp, exist_ok=True)
    parts, kept, replaced, forced = [], 0, 0, []

    for c in sorted(cfg["clips"], key=lambda x: x["sequence_order"]):
        cid = c["id"]
        start, dur = tl[cid]
        d = decision_for(audit, cid)
        part = os.path.join(tmp, f"{cid}.wav")

        src = None
        if d == "keep":
            raw = man.get(cid, {}).get("comfy_source")
            if raw:
                p = raw if os.path.exists(raw) else os.path.join(args.story_root, cid, basename(raw))
                if os.path.exists(p) and has_audio(p):
                    src = p
            if src is None:
                forced.append(cid)
                d = "replace"

        if d == "keep":
            ok = extract(src, 0.0, dur, part, from_video=True)
        else:
            ok = extract(KOKORO, start, dur, part, from_video=False)
        if not ok:
            print(f"{cid}: extraction failed", file=sys.stderr)
            return 1
        parts.append(part)
        kept += d == "keep"
        replaced += d == "replace"

    out = args.output or DEFAULT_OUT
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with wave.open(out, "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(WIDTH)
        w.setframerate(RATE)
        for p in parts:
            with wave.open(p, "rb") as r:
                w.writeframes(r.readframes(r.getnframes()))

    with wave.open(out, "rb") as r:
        got = r.getnframes() / r.getframerate()

    if not args.keep_parts:
        for p in parts:
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass

    print(f"wrote {out}")
    print(f"  {got:.2f}s built, {total:.2f}s expected, drift {got-total:+.3f}s")
    print(f"  kept H3 audio on {kept} clip(s), used Kokoro on {replaced}")
    if forced:
        print(f"  forced to Kokoro (no rendered audio yet): {' '.join(forced)}")
    print("\nTo use it, point the dialogue path in assemble_story.py at this file.")
    print("The score is mixed separately and is unaffected.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    s = sub.add_parser("set")
    s.add_argument("--keep", nargs="*")
    s.add_argument("--replace", nargs="*")
    s.add_argument("--clear", nargs="*")
    s.add_argument("--default", choices=["keep", "replace"])
    s.add_argument("--reason", default="")
    s.set_defaults(fn=cmd_set)
    b = sub.add_parser("build")
    b.add_argument("--output")
    b.add_argument("--story-root", default=STORY_ROOT)
    b.set_defaults(fn=cmd_build)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
