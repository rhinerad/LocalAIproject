"""Guard the prompt text against corruption between the sheet and the model.

WHERE THE RISK ACTUALLY IS
    The automation does not paste anything. minimax_story_runner.py reads
    story_config.json and substitutes the text directly into the API graph, so
    nothing can be added or transformed in transit.

    The manual path does paste, and that is where seven of twenty-four runs on
    2026-08-10 arrived wrapped in quotation marks -- CSV quote-escaping surviving a
    copy out of the raw file. Because the prompt also says "spoken words appear only
    inside quotation marks", that told the model the entire prompt was a spoken line.

WHAT THIS DOES
    check    scan every prompt in story_config.json for the known corruptions
    fix      normalise them in place, with a timestamped backup first
    clean    normalise a single .txt or a folder of them (the prompts\\ files)
    verify   compare what ComfyUI actually received -- read back out of the PNG
             metadata it writes beside every generation -- against what the config
             says it should have been, and show the difference

USAGE
    python work\\prompt_integrity.py check
    python work\\prompt_integrity.py fix
    python work\\prompt_integrity.py clean --path prompts
    python work\\prompt_integrity.py verify --since 2026-08-10T18:00
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import glob
import json
import os
import re
import shutil
import sys
import unicodedata

EQ = os.path.join("outputs", "equal_shares")
CONFIG = os.path.join(EQ, "story_config.json")
SHARED_OUT = r"A:\Users\rhine\ComfyUI-Shared\output"

# Characters that survive a paste and change meaning or tokenisation.
ZERO_WIDTH = "\u200b\u200c\u200d\u2060\ufeff"
NBSP = "\u00a0\u2007\u202f"


def issues(text: str) -> list[str]:
    found = []
    if text != text.strip():
        found.append("leading/trailing whitespace")
    t = text.strip()
    if len(t) > 1 and t[0] == '"' and t[-1] == '"':
        found.append("whole prompt wrapped in quotation marks")
    if t.startswith("'"):
        found.append("leading apostrophe (spreadsheet text marker)")
    if '""' in t:
        found.append("doubled quotes from CSV escaping")
    if any(c in t for c in ZERO_WIDTH):
        found.append("zero-width or BOM characters")
    if any(c in t for c in NBSP):
        found.append("non-breaking spaces")
    if "\r" in t:
        found.append("CRLF line endings")
    if "\t" in t:
        found.append("tab characters")
    if re.search(r"[ \t]+\n", t):
        found.append("trailing spaces at line ends")
    if re.search(r"\n{3,}", t):
        found.append("3+ consecutive blank lines")
    return found


def sanitize(text: str) -> str:
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    for c in ZERO_WIDTH:
        t = t.replace(c, "")
    for c in NBSP:
        t = t.replace(c, " ")
    t = t.replace("\t", " ")
    t = t.strip()
    if t.startswith("'"):
        t = t[1:]
    # CSV escaping: a fully wrapped field, with inner quotes doubled
    if len(t) > 1 and t[0] == '"' and t[-1] == '"':
        inner = t[1:-1]
        if '""' in inner or '"' not in inner:
            inner = inner.replace('""', '"')
        t = inner.strip()
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ ]{2,}", " ", t)
    return t.strip()


def load_config():
    with open(CONFIG, encoding="utf-8-sig") as fh:
        return json.load(fh)


def cmd_check(args):
    cfg = load_config()
    bad = 0
    for c in cfg["clips"]:
        found = issues(c.get("prompt", ""))
        if found:
            bad += 1
            print(f"  {c['id']:6} {'; '.join(found)}")
    print(f"\n{len(cfg['clips'])} prompts checked, {bad} with issues")
    if not bad:
        print("clean")
    return 1 if bad else 0


def cmd_fix(args):
    cfg = load_config()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = CONFIG.replace(".json", f".BACKUP_{stamp}.json")
    shutil.copy2(CONFIG, backup)
    changed = []
    for c in cfg["clips"]:
        old = c.get("prompt", "")
        new = sanitize(old)
        if new != old:
            c["prompt"] = new
            changed.append(c["id"])
    with open(CONFIG, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
    print(f"backup: {backup}")
    print(f"normalised {len(changed)} prompt(s)" + (": " + " ".join(changed) if changed else ""))
    print("re-run the runner's --check pass before generating")
    return 0


def cmd_clean(args):
    paths = []
    if os.path.isdir(args.path):
        paths = sorted(glob.glob(os.path.join(args.path, "*.txt")))
    elif os.path.exists(args.path):
        paths = [args.path]
    if not paths:
        print(f"nothing to clean at {args.path}", file=sys.stderr)
        return 2
    changed = 0
    for p in paths:
        old = open(p, encoding="utf-8-sig").read()
        new = sanitize(old)
        # a single trailing newline is how these files are written; not a defect
        if new != old.rstrip("\n"):
            open(p, "w", encoding="utf-8").write(new + "\n")
            changed += 1
            print(f"  cleaned {os.path.basename(p)}: {'; '.join(issues(old)) or 'normalised'}")
    print(f"{len(paths)} file(s) checked, {changed} cleaned")
    return 0


def cmd_verify(args):
    """Compare what ComfyUI received against what the config says."""
    try:
        from PIL import Image
    except ImportError:
        print("verify needs pillow", file=sys.stderr)
        return 2

    cfg = load_config()
    by_pair, by_id = {}, {c["id"]: c for c in cfg["clips"]}
    for c in cfg["clips"]:
        f, l = c.get("first_frame"), c.get("last_frame")
        if f and l:
            key = (os.path.splitext(os.path.basename(f.replace("\\", "/")))[0],
                   os.path.splitext(os.path.basename(l.replace("\\", "/")))[0])
            by_pair[key] = c["id"]

    cutoff = dt.datetime.fromisoformat(args.since).timestamp() if args.since else 0
    checked = drifted = 0
    for png in sorted(glob.glob(os.path.join(args.shared_output, "ComfyUI_*.png"))):
        if os.path.getmtime(png) < cutoff:
            continue
        try:
            g = json.loads(Image.open(png).info.get("prompt", "{}"))
        except Exception:
            continue
        h3 = [v["inputs"] for v in g.values()
              if isinstance(v, dict) and v.get("class_type") == "MiniMaxH3ImageToVideo"]
        li = [os.path.splitext(v["inputs"]["image"])[0].split("__")[-1] for v in g.values()
              if isinstance(v, dict) and v.get("class_type") == "LoadImage"]
        if not h3 or not isinstance(h3[0].get("prompt"), str):
            continue
        sent = h3[0]["prompt"]
        cid = by_pair.get(tuple(li))
        checked += 1
        probs = issues(sent)
        if probs:
            drifted += 1
            print(f"{os.path.basename(png):<22} {cid or '?':<6} {'; '.join(probs)}")
            if cid and args.diff:
                want = by_id[cid]["prompt"]
                got = sanitize(sent)
                if want != got:
                    for line in list(difflib.unified_diff(
                            want.splitlines(), got.splitlines(),
                            "config", "submitted", lineterm="", n=1))[:20]:
                        print("   ", line)
    print(f"\n{checked} submitted prompt(s) checked, {drifted} corrupted in transit")
    if drifted:
        print("Fix: copy from prompts\\<clip>.txt, not from the raw CSV.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("fix").set_defaults(fn=cmd_fix)
    c = sub.add_parser("clean")
    c.add_argument("--path", default="prompts")
    c.set_defaults(fn=cmd_clean)
    v = sub.add_parser("verify")
    v.add_argument("--shared-output", default=SHARED_OUT)
    v.add_argument("--since", default=None)
    v.add_argument("--diff", action="store_true", help="show line differences")
    v.set_defaults(fn=cmd_verify)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
