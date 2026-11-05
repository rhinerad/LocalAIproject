"""Build a character LoRA training set from approved frames and accepted renders.

This is the dataset half of character-LoRA work -- the part that decides whether
training succeeds. It takes videos and stills the character appears in, finds the
face in each, crops head-and-shoulders, discards near-duplicates and anything too
small to be useful, upscales to a square training size, and writes a caption file
per image with your trigger word.

It deliberately does NOT train anything. Training happens in ai-toolkit; see
docs\\LORA_TRAINING_RUNBOOK.md.

WHY THE SIZE FILTER MATTERS
    In the wide shots the Narrator's head is about 22 px. Those frames carry no
    identity information and will actively poison a LoRA by teaching it a blurred
    average. --min-face-px throws them out. Default 90 px in the source image.

USAGE
    python work\\build_lora_dataset.py --name narrator --trigger ohwx_narrator ^
        --sources "outputs\\equal_shares\\frames\\scene_000\\boundary_narrator_close_v3.png" ^
                  "outputs\\equal_shares\\frames\\scene_000\\boundary_00_v2.png" ^
                  "A:\\Users\\rhine\\ComfyUI-Shared\\output\\story\\00A" ^
                  "A:\\Users\\rhine\\ComfyUI-Shared\\output\\story\\00B"

    python work\\build_lora_dataset.py --name narrator --trigger ohwx_narrator ^
        --sources ... --caption "ohwx_narrator, a man in his late fifties in a dark 1960s suit"

Output lands in outputs\\equal_shares\\lora_datasets\\<name>\\ as image/caption pairs
plus a contact sheet so you can cull before training.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
import tempfile

try:
    import cv2
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("requires opencv-python, numpy and pillow")

OUT_ROOT = os.path.join("outputs", "equal_shares", "lora_datasets")
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}

CASCADE = cv2.CascadeClassifier(
    os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))


def expand(sources):
    """Accept files, directories and globs; return a flat list of media paths."""
    out = []
    for s in sources:
        if os.path.isdir(s):
            for root, _, files in os.walk(s):
                out += [os.path.join(root, f) for f in files]
        else:
            out += glob.glob(s) or ([s] if os.path.exists(s) else [])
    keep = [p for p in out if os.path.splitext(p)[1].lower() in VIDEO_EXT | IMAGE_EXT]
    return sorted(set(keep))


def frames_from_video(path, interval, tmp):
    stem = hashlib.md5(path.encode()).hexdigest()[:8]
    pattern = os.path.join(tmp, f"{stem}_%04d.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path,
                    "-vf", f"fps=1/{interval}", pattern], check=False)
    return sorted(glob.glob(os.path.join(tmp, f"{stem}_*.png")))


def biggest_face(bgr, min_px):
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    grey = cv2.equalizeHist(grey)
    faces = CASCADE.detectMultiScale(grey, scaleFactor=1.1, minNeighbors=6,
                                     minSize=(min_px, min_px))
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def crop_head_shoulders(bgr, face, pad, size):
    h, w = bgr.shape[:2]
    x, y, fw, fh = face
    cx, cy = x + fw / 2, y + fh / 2
    half = fw * pad / 2
    cy -= fh * 0.10                      # bias down slightly: keep chin and collar
    x0, y0 = int(max(cx - half, 0)), int(max(cy - half, 0))
    x1, y1 = int(min(cx + half, w)), int(min(cy + half, h))
    side = min(x1 - x0, y1 - y0)
    if side < 32:
        return None
    crop = bgr[y0:y0 + side, x0:x0 + side]
    return cv2.resize(crop, (size, size), interpolation=cv2.INTER_LANCZOS4)


def signature(bgr):
    small = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (16, 16))
    return small.astype(np.float32)


def too_similar(sig, seen, threshold):
    return any(float(np.abs(sig - s).mean()) < threshold for s in seen)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="dataset folder name, e.g. narrator")
    ap.add_argument("--trigger", required=True, help="trigger word, e.g. ohwx_narrator")
    ap.add_argument("--sources", nargs="+", required=True)
    ap.add_argument("--caption", default=None,
                    help="caption body after the trigger word; a default is used if omitted")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between video samples")
    ap.add_argument("--min-face-px", type=int, default=90,
                    help="ignore faces smaller than this in the SOURCE image")
    ap.add_argument("--pad", type=float, default=3.2,
                    help="crop width as a multiple of face width")
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--dedupe", type=float, default=6.0,
                    help="mean grey difference below this counts as a duplicate")
    ap.add_argument("--max", type=int, default=40, help="stop after this many kept crops")
    ap.add_argument("--out-root", default=OUT_ROOT)
    args = ap.parse_args()

    media = expand(args.sources)
    if not media:
        print("no media found for those sources", file=sys.stderr)
        return 2
    outdir = os.path.join(args.out_root, args.name)
    os.makedirs(outdir, exist_ok=True)

    caption = args.caption or f"{args.trigger}, cinematic photo of the same person"
    if not caption.startswith(args.trigger):
        caption = f"{args.trigger}, {caption}"

    seen, kept, records = [], 0, []
    skipped_small = skipped_dupe = skipped_noface = 0

    with tempfile.TemporaryDirectory() as tmp:
        for path in media:
            ext = os.path.splitext(path)[1].lower()
            frames = frames_from_video(path, args.interval, tmp) if ext in VIDEO_EXT else [path]
            for fr in frames:
                if kept >= args.max:
                    break
                bgr = cv2.imread(fr)
                if bgr is None:
                    continue
                face = biggest_face(bgr, args.min_face_px)
                if face is None:
                    skipped_noface += 1
                    continue
                crop = crop_head_shoulders(bgr, face, args.pad, args.size)
                if crop is None:
                    skipped_small += 1
                    continue
                sig = signature(crop)
                if too_similar(sig, seen, args.dedupe):
                    skipped_dupe += 1
                    continue
                seen.append(sig)
                stem = f"{args.name}_{kept:03d}"
                cv2.imwrite(os.path.join(outdir, stem + ".png"), crop)
                with open(os.path.join(outdir, stem + ".txt"), "w", encoding="utf-8") as fh:
                    fh.write(caption + "\n")
                records.append(dict(file=stem + ".png", source=path,
                                    face_px=int(face[2]), frame=os.path.basename(fr)))
                kept += 1

    if not kept:
        print("nothing kept - try lowering --min-face-px", file=sys.stderr)
        return 1

    # contact sheet for culling
    cols = 6
    rows = (kept + cols - 1) // cols
    thumb = 220
    sheet = Image.new("RGB", (cols * thumb, rows * thumb), (20, 20, 20))
    for i, r in enumerate(records):
        im = Image.open(os.path.join(outdir, r["file"])).resize((thumb, thumb))
        sheet.paste(im, ((i % cols) * thumb, (i // cols) * thumb))
    sheet.save(os.path.join(outdir, "_contact_sheet.jpg"), quality=88)

    json.dump(dict(name=args.name, trigger=args.trigger, caption=caption,
                   kept=kept, records=records,
                   settings=vars(args)),
              open(os.path.join(outdir, "dataset_manifest.json"), "w"), indent=2)

    print(f"kept {kept} crops in {outdir}")
    print(f"  skipped: {skipped_noface} no face, {skipped_small} too small, {skipped_dupe} duplicates")
    print(f"  trigger word: {args.trigger}")
    print(f"  caption:      {caption}")
    print(f"\nOpen _contact_sheet.jpg and DELETE any crop that is not the right person,")
    print(f"is blurred, or is mid-blink. Delete the matching .txt with it. Quality beats")
    print(f"quantity - 15 clean crops train better than 40 with five wrong faces.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
