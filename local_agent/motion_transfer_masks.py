#!/usr/bin/env python3
"""Per-frame character selection and masks from DWPose keypoints.

Replaces the two clip-specific hacks of the 2026-09-25/26 proof of concept
(docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md §6e/§6f): the static
left-half IP-Adapter attention mask and the "leftmost face" detail-pass
filter both fit only one clip's blocking.  Here the character is chosen from
the reference clip's own DWPose people (a selector such as leftmost /
largest / index), tracked frame to frame by body centre, and turned into:

- one 8-bit mask PNG per frame (white = the character's body region, padded)
  for ``VHS_LoadImagesPath`` → ``ImageToMask`` → ``IPAdapterAdvanced.attn_mask``
  (IP-Adapter applies a mask batch per frame under AnimateDiff);
- a union mask over all frames;
- a face-selection rule for the Impact detail pass: an ``ImpactSEGSOrderedFilter``
  setting when the character's head is unambiguously the leftmost / rightmost
  / topmost / bottommost head in every frame it shares with someone, the
  largest face when it is alone, else "intersect the SEGS with the union
  mask" (``ImpactSegsAndMask``).

Input is the JSON written by controlnet_aux's ``SavePoseKpsAsJsonFile``: a
list per frame of ``{"people": [{"pose_keypoints_2d": [x, y, c, ...]}],
"canvas_width", "canvas_height"}`` (OpenPose body-18 order; a missing point
is ``0, 0, 0``; coordinates may be pixel or normalised).  Pure Python + PIL;
no GPU, no ComfyUI.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw

# OpenPose body-18 indices.
NOSE, NECK = 0, 1
R_SHOULDER, L_SHOULDER = 2, 5
R_EYE, L_EYE, R_EAR, L_EAR = 14, 15, 16, 17
HEAD_POINTS = (NOSE, R_EYE, L_EYE, R_EAR, L_EAR)

SELECTORS = ("largest", "leftmost", "rightmost", "index", "nearest")


class MaskError(ValueError):
    pass


@dataclass
class Person:
    index: int                      # position in the frame's ``people`` list
    points: list[tuple[float, float] | None]   # pixel coordinates in the canvas
    canvas: tuple[int, int]         # (width, height)

    @property
    def visible(self) -> list[tuple[float, float]]:
        return [p for p in self.points if p is not None]

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        xs = [p[0] for p in self.visible]
        ys = [p[1] for p in self.visible]
        return (min(xs), min(ys), max(xs), max(ys))

    @property
    def height(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return max(y2 - y1, x2 - x1)

    @property
    def centre(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @property
    def head(self) -> tuple[float, float] | None:
        pts = [self.points[i] for i in HEAD_POINTS if i < len(self.points) and self.points[i]]
        if pts:
            return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        if NECK < len(self.points) and self.points[NECK]:
            return self.points[NECK]
        return None


@dataclass
class FrameTrack:
    frame: int
    person: Person | None          # None = the character was not found this frame
    carried: bool = False          # mask carried from the previous frame


@dataclass
class Prepared:
    selector: dict[str, Any]
    selected_index: int
    frames: int
    found: int
    carried: int
    size: tuple[int, int]
    mask_paths: list[str] = field(default_factory=list)
    mask_sha256: list[str] = field(default_factory=list)
    union_mask_path: str | None = None
    union_mask_sha256: str | None = None
    face_rule: dict[str, Any] = field(default_factory=dict)
    people_per_frame: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector, "selected_index": self.selected_index,
            "frames": self.frames, "found": self.found, "carried": self.carried,
            "size": list(self.size), "mask_paths": self.mask_paths,
            "mask_sha256": self.mask_sha256, "union_mask_path": self.union_mask_path,
            "union_mask_sha256": self.union_mask_sha256, "face_rule": self.face_rule,
            "people_per_frame": self.people_per_frame,
        }


def load_pose_frames(source: str | Path | list) -> list[dict[str, Any]]:
    if isinstance(source, list):
        frames = source
    else:
        frames = json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(frames, list) or not frames:
        raise MaskError("pose JSON must be a non-empty list of frames")
    for i, frame in enumerate(frames):
        if not isinstance(frame, dict) or "people" not in frame:
            raise MaskError(f"frame {i} has no 'people'")
        if not frame.get("canvas_width") or not frame.get("canvas_height"):
            raise MaskError(f"frame {i} has no canvas size")
    return frames


def _points(raw: Iterable[float], canvas: tuple[int, int]) -> list[tuple[float, float] | None]:
    vals = [float(v) for v in (raw or [])]
    pts: list[tuple[float, float] | None] = []
    triples = [vals[i:i + 3] for i in range(0, len(vals) - len(vals) % 3, 3)]
    if not triples:
        return pts
    present = [(x, y) for x, y, c in triples if c > 0]
    normalised = bool(present) and all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in present)
    w, h = canvas
    for x, y, c in triples:
        if c <= 0:
            pts.append(None)
        elif normalised:
            pts.append((x * w, y * h))
        else:
            pts.append((x, y))
    return pts


def frame_people(frame: dict[str, Any], *, min_height_frac: float = 0.15) -> list[Person]:
    """People with body keypoints, dropping tiny skeletons (a photo on a
    nightstand read as a person, §6) below ``min_height_frac`` of the canvas."""
    canvas = (int(frame["canvas_width"]), int(frame["canvas_height"]))
    out: list[Person] = []
    for idx, person in enumerate(frame.get("people") or []):
        pts = _points(person.get("pose_keypoints_2d") or [], canvas)
        p = Person(idx, pts, canvas)
        if len(p.visible) < 3:
            continue
        if p.height < min_height_frac * canvas[1]:
            continue
        out.append(p)
    return out


def select_person(people: list[Person], selector: dict[str, Any] | None) -> Person | None:
    spec = dict(selector or {})
    by = str(spec.get("by") or "largest").lower()
    if by not in SELECTORS:
        raise MaskError(f"selector.by must be one of {SELECTORS}, not {by!r}")
    if not people:
        return None
    if by == "largest":
        return max(people, key=lambda p: p.height)
    if by == "leftmost":
        return min(people, key=lambda p: p.centre[0])
    if by == "rightmost":
        return max(people, key=lambda p: p.centre[0])
    if by == "index":
        want = int(spec.get("index", 0))
        for p in people:
            if p.index == want:
                return p
        return None
    point = spec.get("point") or [0.5, 0.5]
    w, h = people[0].canvas
    tx, ty = float(point[0]) * w, float(point[1]) * h
    return min(people, key=lambda p: math.hypot(p.centre[0] - tx, p.centre[1] - ty))


def track_person(frames: list[dict[str, Any]], selector: dict[str, Any] | None, *,
                 min_height_frac: float = 0.15, max_jump_frac: float = 0.25,
                 ) -> tuple[list[FrameTrack], list[list[Person]]]:
    """Choose the character in the first frame that has people, then follow
    the nearest body centre frame to frame.  A frame with no plausible match
    carries the previous person (marked ``carried``)."""
    per_frame = [frame_people(f, min_height_frac=min_height_frac) for f in frames]
    track: list[FrameTrack] = []
    current: Person | None = None
    for i, people in enumerate(per_frame):
        if current is None:
            chosen = select_person(people, selector)
            track.append(FrameTrack(i, chosen, carried=False))
            current = chosen
            continue
        w, h = current.canvas
        limit = max_jump_frac * math.hypot(w, h)
        best: Person | None = None
        best_d = None
        for p in people:
            d = math.hypot(p.centre[0] - current.centre[0], p.centre[1] - current.centre[1])
            if d <= limit and (best_d is None or d < best_d):
                best, best_d = p, d
        if best is None:
            track.append(FrameTrack(i, current, carried=True))
        else:
            track.append(FrameTrack(i, best, carried=False))
            current = best
    return track, per_frame


def body_mask(person: Person, size: tuple[int, int], *, pad_frac: float = 0.12,
              head_pad_frac: float = 0.55) -> Image.Image:
    """White body region on black at ``size``: the padded keypoint box plus a
    head disc so the face is inside the mask even when only the nose/eyes are
    detected."""
    W, H = size
    cw, ch = person.canvas
    sx, sy = W / float(cw), H / float(ch)
    img = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(img)
    x1, y1, x2, y2 = person.bbox
    pad = pad_frac * max(x2 - x1, y2 - y1)
    draw.rectangle([(x1 - pad) * sx, (y1 - pad) * sy, (x2 + pad) * sx, (y2 + pad) * sy], fill=255)
    head = person.head
    if head is not None:
        shoulders = [person.points[i] for i in (R_SHOULDER, L_SHOULDER)
                     if i < len(person.points) and person.points[i]]
        if len(shoulders) == 2:
            radius = head_pad_frac * math.hypot(shoulders[0][0] - shoulders[1][0],
                                                shoulders[0][1] - shoulders[1][1])
        else:
            radius = head_pad_frac * 0.25 * person.height
        radius = max(radius, 0.04 * max(cw, ch))
        draw.ellipse([(head[0] - radius) * sx, (head[1] - radius) * sy,
                      (head[0] + radius) * sx, (head[1] + radius) * sy], fill=255)
    return img


def face_rule(track: list[FrameTrack], per_frame: list[list[Person]], *,
              margin_frac: float = 0.05) -> dict[str, Any]:
    """Which Impact filter isolates the character's face in the detail pass.

    Returns ``{"mode": "ordered", "target": "x1"|"y1"|"area", "order": bool,
    "take_count": 1, "why": ...}`` (order False = ascending, as
    ImpactSEGSOrderedFilter reads it) or ``{"mode": "union_mask", ...}``."""
    shared = 0
    left = right = top = bottom = True
    for ft in track:
        if ft.person is None or ft.carried:
            continue
        head = ft.person.head
        if head is None:
            continue
        w, h = ft.person.canvas
        others = [p for p in per_frame[ft.frame] if p.index != ft.person.index and p.head]
        if not others:
            continue
        shared += 1
        mx, my = margin_frac * w, margin_frac * h
        left &= all(head[0] < o.head[0] - mx for o in others)
        right &= all(head[0] > o.head[0] + mx for o in others)
        top &= all(head[1] < o.head[1] - my for o in others)
        bottom &= all(head[1] > o.head[1] + my for o in others)
    if shared == 0:
        return {"mode": "ordered", "target": "area", "order": True, "take_count": 1,
                "why": "the character never shares a frame with another person; largest face"}
    for ok, target, order, word in ((left, "x1", False, "leftmost"),
                                    (right, "x1", True, "rightmost"),
                                    (top, "y1", False, "topmost"),
                                    (bottom, "y1", True, "bottommost")):
        if ok:
            return {"mode": "ordered", "target": target, "order": order, "take_count": 1,
                    "why": f"the character's head is the {word} head in all {shared} shared frames"}
    return {"mode": "union_mask",
            "why": f"no single ordering isolates the character's head across {shared} shared frames; "
                   "SEGS are intersected with the union body mask instead"}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def prepare(pose_json: str | Path | list, out_dir: str | Path, *, size: tuple[int, int],
            selector: dict[str, Any] | None = None, min_height_frac: float = 0.15,
            max_jump_frac: float = 0.25, pad_frac: float = 0.12) -> Prepared:
    """Write ``mask_00001.png`` … and ``union_mask.png`` under ``out_dir`` and
    return the record a manifest needs.  Raises MaskError when no person
    matches the selector in any frame."""
    frames = load_pose_frames(pose_json)
    track, per_frame = track_person(frames, selector, min_height_frac=min_height_frac,
                                    max_jump_frac=max_jump_frac)
    first = next((ft for ft in track if ft.person is not None), None)
    if first is None:
        raise MaskError("no person matches the selector in any frame "
                        f"(people per frame: {[len(p) for p in per_frame]})")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    W, H = int(size[0]), int(size[1])
    union = Image.new("L", (W, H), 0)
    rec = Prepared(selector=dict(selector or {"by": "largest"}), selected_index=first.person.index,
                   frames=len(frames), found=0, carried=0, size=(W, H),
                   people_per_frame=[len(p) for p in per_frame])
    last_mask: Image.Image | None = None
    for ft in track:
        if ft.person is None:
            mask = last_mask or Image.new("L", (W, H), 0)
            rec.carried += 1
        else:
            mask = body_mask(ft.person, (W, H), pad_frac=pad_frac)
            if ft.carried:
                rec.carried += 1
            else:
                rec.found += 1
        last_mask = mask
        path = out / f"mask_{ft.frame + 1:05d}.png"
        mask.save(path)
        rec.mask_paths.append(str(path))
        rec.mask_sha256.append(_sha(path))
        union = _union(union, mask)
    # The union goes in its own folder so VHS_LoadImagesPath over ``out_dir``
    # (or over ``union/``) loads exactly one kind of mask.
    (out / "union").mkdir(exist_ok=True)
    upath = out / "union" / "union_mask.png"
    union.save(upath)
    rec.union_mask_path = str(upath)
    rec.union_mask_sha256 = _sha(upath)
    rec.face_rule = face_rule(track, per_frame)
    return rec


def _union(a: Image.Image, b: Image.Image) -> Image.Image:
    from PIL import ImageChops
    return ImageChops.lighter(a, b)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pose_json")
    ap.add_argument("out_dir")
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--by", default="largest", choices=SELECTORS)
    ap.add_argument("--index", type=int, default=0)
    args = ap.parse_args(argv)
    try:
        rec = prepare(args.pose_json, args.out_dir, size=(args.width, args.height),
                      selector={"by": args.by, "index": args.index})
    except MaskError as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(rec.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
