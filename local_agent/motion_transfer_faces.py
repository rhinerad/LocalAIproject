#!/usr/bin/env python3
"""InsightFace helper for render_video_from_reference (2026-09-26).

Runs in the ComfyUI venv (the only interpreter with ``insightface``), CPU only, and
never downloads: it refuses unless the buffalo_l pack is already on disk. Prints one
JSON object on stdout.

  crop  --image IN --out OUT.png
        Largest face -> square crop (1.75 x the face box's longer side, centred on the
        box, shifted inside the image) -> 448x448 PNG. With no face: centre square crop,
        ``face_found: false``.
  faces --frames F1.png [F2.png ...]
        Per frame, every face as normalised [x1, y1, x2, y2, det_score].
  score --ref IMAGE --frames F1.png [...] [--rank N --people P]
        ArcFace cosine between the reference's largest face and the target face in each
        frame (P > 1: the face at left-to-right rank N; otherwise the largest face).

The embedding family is the one FaceID is conditioned on, so ``score`` is not an
independent judge (CHANGELOG 2026-09-26g).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

COMFY_ROOT = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI")
INSIGHTFACE_ROOT = COMFY_ROOT / "models" / "insightface"
PACK = INSIGHTFACE_ROOT / "models" / "buffalo_l"
CROP_SCALE = 1.75
CROP_SIZE = 448


def _app():
    if not (PACK / "det_10g.onnx").is_file() or not (PACK / "w600k_r50.onnx").is_file():
        raise SystemExit(json.dumps({"error": f"buffalo_l not on disk at {PACK}; refusing to download"}))
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name="buffalo_l", root=str(INSIGHTFACE_ROOT), providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=0, det_size=(640, 640))
    return app


def _bgr(path: str):
    import numpy as np
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"))[:, :, ::-1].copy()


def square_crop_box(bbox, width: int, height: int, scale: float = CROP_SCALE) -> tuple[int, int, int, int]:
    """Square box around ``bbox`` (x1, y1, x2, y2), side = scale * longer side, kept in the image."""
    x1, y1, x2, y2 = (float(v) for v in bbox)
    side = int(round(max(x2 - x1, y2 - y1) * scale))
    side = max(16, min(side, width, height))
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    left = int(round(cx - side / 2.0))
    top = int(round(cy - side / 2.0))
    left = max(0, min(left, width - side))
    top = max(0, min(top, height - side))
    return left, top, left + side, top + side


def cmd_crop(args) -> dict:
    from PIL import Image
    img = Image.open(args.image).convert("RGB")
    width, height = img.size
    faces = _app().get(_bgr(args.image))
    out = {"image": args.image, "width": width, "height": height, "faces": len(faces)}
    if faces:
        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        box = square_crop_box(face.bbox, width, height)
        out.update({"face_found": True, "det_score": round(float(face.det_score), 3),
                    "face_bbox": [round(float(v), 1) for v in face.bbox]})
    else:
        side = min(width, height)
        left, top = (width - side) // 2, (height - side) // 2
        box = (left, top, left + side, top + side)
        out["face_found"] = False
    img.crop(box).resize((CROP_SIZE, CROP_SIZE), Image.LANCZOS).save(args.out)
    out.update({"crop_box": list(box), "out": args.out, "size": CROP_SIZE})
    return out


def cmd_faces(args) -> dict:
    app = _app()
    frames = []
    for path in args.frames:
        img = _bgr(path)
        h, w = img.shape[:2]
        faces = [[round(float(f.bbox[0]) / w, 4), round(float(f.bbox[1]) / h, 4),
                  round(float(f.bbox[2]) / w, 4), round(float(f.bbox[3]) / h, 4),
                  round(float(f.det_score), 3)] for f in app.get(img)]
        frames.append({"frame": path, "faces": sorted(faces, key=lambda b: b[0])})
    return {"frames": frames}


def cmd_score(args) -> dict:
    import numpy as np
    app = _app()
    ref_faces = app.get(_bgr(args.ref))
    if not ref_faces:
        return {"available": False, "reason": "no face in the reference image"}
    ref = max(ref_faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])).normed_embedding
    per, missing = [], []
    for i, path in enumerate(args.frames, 1):
        faces = sorted(app.get(_bgr(path)), key=lambda f: f.bbox[0])
        if not faces:
            missing.append(i)
            continue
        if args.people > 1:
            if args.rank >= len(faces):
                missing.append(i)
                continue
            face = faces[args.rank]
        else:
            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        per.append([i, round(float(np.dot(face.normed_embedding, ref)), 3)])
    vals = [s for _, s in per]
    return {"available": True, "metric": "ArcFace cosine (buffalo_l w600k_r50) vs the character still",
            "caveat": "same embedding family FaceID is conditioned on; not an independent judge",
            "detected": len(per), "frames": len(args.frames), "missing_frames": missing,
            "mean": round(float(np.mean(vals)), 3) if vals else None,
            "min": round(float(np.min(vals)), 3) if vals else None, "per_frame": per}


def _frames_arg(p: argparse.ArgumentParser) -> None:
    # Long clips: 180 absolute paths overflow the Windows command line (WinError 206,
    # CHANGELOG 2026-09-26k), so a list file (one path per line) is accepted too.
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--frames", nargs="+")
    g.add_argument("--frames-file")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crop")
    c.add_argument("--image", required=True)
    c.add_argument("--out", required=True)
    f = sub.add_parser("faces")
    _frames_arg(f)
    s = sub.add_parser("score")
    s.add_argument("--ref", required=True)
    _frames_arg(s)
    s.add_argument("--rank", type=int, default=0)
    s.add_argument("--people", type=int, default=1)
    args = ap.parse_args(argv)
    if getattr(args, "frames_file", None):
        args.frames = [ln.strip() for ln in Path(args.frames_file).read_text(encoding="utf-8").splitlines()
                       if ln.strip()]
    result = {"crop": cmd_crop, "faces": cmd_faces, "score": cmd_score}[args.cmd](args)
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
