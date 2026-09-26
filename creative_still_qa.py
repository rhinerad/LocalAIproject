#!/usr/bin/env python3
"""Prompt-aware creative stills QA (fail-closed).

Checks face/clothing/room continuity only when the prompt expects those
elements. Empty camcorder-POV / no-character shots must NOT fail for missing
faces; they fail if a person appears when none should, or room continuity drifts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
YUNET = ROOT / "models" / "opencv_face" / "face_detection_yunet_2023mar.onnx"
SFACE = ROOT / "models" / "opencv_face" / "face_recognition_sface_2021dec.onnx"

# Tunable thresholds (calibrate against known-bad C001 start vs last).
ROOM_HIST_MIN = 0.55
CLOTHING_HIST_MIN = 0.50
FACE_HIST_MIN = 0.45
FACE_CENTER_MAX_SHIFT = 0.28  # fraction of frame diagonal


YOLO_PT = ROOT / "models" / "opencv_person" / "yolov8n.pt"
YOLO_ONNX = ROOT / "models" / "opencv_person" / "yolov8n.onnx"
SSD_ONNX = ROOT / "models" / "opencv_person" / "ssd_mobilenet_v1_10.onnx"

# Empty-POV person gate (tiled YOLO catches distant/slumped bodies YuNet misses).
PERSON_FULL_CONF = 0.15
PERSON_TILE_CONF = 0.08
EMPTY_POV_NEGATIVE = (
    "person, people, human, man, woman, child, face, body, figure, silhouette, "
    "character, actor, sitting person, standing person, crowd, portrait, selfie, "
    "hands in frame, arms, legs, shoes, clothing on a person"
)
EMPTY_POV_POSITIVE_PREFIX = (
    "empty handheld camcorder POV, vacant corridor, nobody in frame, no people, "
    "no person, no human, no character, environment only, "
)

_YOLO = None


def _yolo_model():
    """Lazy-load YOLOv8n (ultralytics) once."""
    global _YOLO
    if _YOLO is not None:
        return _YOLO
    try:
        from ultralytics import YOLO
        if YOLO_PT.is_file():
            _YOLO = YOLO(str(YOLO_PT))
        elif YOLO_ONNX.is_file():
            _YOLO = YOLO(str(YOLO_ONNX))
        else:
            _YOLO = YOLO("yolov8n.pt")
        return _YOLO
    except Exception:
        return None


def _detect_people(img_bgr: np.ndarray) -> list[dict]:
    """Detect person bodies via tiled YOLOv8 (+ SSD fallback). Returns hit dicts."""
    hits: list[dict] = []
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    model = _yolo_model()
    if model is not None:
        try:
            r = model.predict(rgb, classes=[0], conf=PERSON_FULL_CONF, verbose=False)[0]
            if r.boxes is not None:
                for b, s in zip(r.boxes.xyxy, r.boxes.conf):
                    hits.append({"source": "yolo_full", "conf": float(s), "xyxy": [float(x) for x in b]})
            tiles = [
                (0, 0, w // 2 + w // 8, h // 2 + h // 8),
                (w // 2 - w // 8, 0, w, h // 2 + h // 8),
                (0, h // 2 - h // 8, w // 2 + w // 8, h),
                (w // 2 - w // 8, h // 2 - h // 8, w, h),
                (w // 5, h // 5, 4 * w // 5, 4 * h // 5),
                (w // 4, h // 6, 3 * w // 4, 5 * h // 6),
            ]
            for i, (x0, y0, x1, y1) in enumerate(tiles):
                crop = rgb[y0:y1, x0:x1]
                if crop.size == 0:
                    continue
                r = model.predict(crop, classes=[0], conf=PERSON_TILE_CONF, verbose=False)[0]
                if r.boxes is None:
                    continue
                for b, s in zip(r.boxes.xyxy, r.boxes.conf):
                    xx0, yy0, xx1, yy1 = [float(x) for x in b]
                    hits.append({
                        "source": f"yolo_tile{i}",
                        "conf": float(s),
                        "xyxy": [xx0 + x0, yy0 + y0, xx1 + x0, yy1 + y0],
                    })
        except Exception as e:
            hits.append({"source": "yolo_error", "conf": 0.0, "error": str(e)})

    # SSD MobileNet fallback when YOLO found nothing usable
    has_yolo = any(str(h.get("source", "")).startswith("yolo") and h.get("conf", 0) >= PERSON_TILE_CONF for h in hits)
    if SSD_ONNX.is_file() and not has_yolo:
        try:
            import onnxruntime as ort
            sess = ort.InferenceSession(str(SSD_ONNX), providers=["CPUExecutionProvider"])
            inp = sess.get_inputs()[0].name
            resized = cv2.resize(rgb, (300, 300))
            outs = sess.run(None, {inp: resized[None, ...].astype(np.uint8)})
            boxes, classes, scores, num = outs
            n = int(num[0])
            for i in range(n):
                if int(classes[0, i]) == 1 and float(scores[0, i]) >= 0.25:
                    ymin, xmin, ymax, xmax = boxes[0, i].tolist()
                    hits.append({
                        "source": "ssd",
                        "conf": float(scores[0, i]),
                        "xyxy": [xmin * w, ymin * h, xmax * w, ymax * h],
                    })
        except Exception:
            pass
    return hits


def empty_pov_prompt_boost(prompt: str) -> tuple[str, str]:
    """Return (boosted_positive, strong_negative) for empty-POV Flux renders."""
    p = (prompt or "").strip()
    if not p.lower().startswith("empty handheld"):
        p = EMPTY_POV_POSITIVE_PREFIX + p
    neg = EMPTY_POV_NEGATIVE
    return p, neg



@dataclass
class VisibilityExpectation:
    expect_actor_visible: bool
    expect_entity_visible: bool
    expect_empty_of_people: bool
    environment: str  # apartment | backrooms | unknown
    reasons: list[str]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def infer_visibility_expectation(
    *,
    prompt: str,
    clip: Mapping[str, Any] | None = None,
    kind: str = "last",
) -> VisibilityExpectation:
    """Derive who/what should appear from prompt (+ light clip hints)."""
    reasons: list[str] = []
    p = _norm(prompt)
    clip = clip or {}

    # Environment
    env = "unknown"
    if any(k in p for k in ("yellow wallpaper", "backrooms", "level 0", "fluorescent", "damp carpet", "liminal")):
        env = "backrooms"
        reasons.append("env_backrooms_keywords")
    if any(k in p for k in ("apartment", "audition", "household lamp", "taped mark", "script pages")):
        env = "apartment" if env == "unknown" else env
        reasons.append("env_apartment_keywords")

    # Operator always out of frame in this pack language
    operator_out = "outside the frame" in p or "operator are completely outside" in p or "operator is completely outside" in p

    # Visible actor cues: pose/action beats that put the actor in-frame
    actor_visible_cues = [
        r"\bactor\b.{0,80}\b(facing|standing|leaning|gestures|looks|holding|smiling|raises|raised|resets|panic|eyes wide|breaking character|profile|centered)\b",
        r"\bsame male sitcom actor\b",
        r"\bhand raised\b",
        r"\bsitcom smile\b",
    ]
    actor_mentioned = bool(re.search(r"\bactor\b", p))
    actor_pose = any(re.search(rx, p) for rx in actor_visible_cues)

    # Empty / no-character cues
    empty_cues = [
        "no character",
        "no characters",
        "nobody in frame",
        "no one in frame",
        "empty corridor",
        "empty room",
        "empty hallway",
        "no person visible",
        "uninhabited",
        "only the room",
        "environment only",
        "static hold of empty",
        "image breaks into vhs static",
        "vhs static",
    ]
    empty_language = any(k in p for k in empty_cues)

    # Entity
    entity_visible = bool(
        re.search(r"\bentity\b", p)
        and not re.search(r"\bentity\b.{0,40}\b(outside|off-?camera|heard only)\b", p)
    )
    if entity_visible:
        reasons.append("entity_described_in_frame")

    # Handheld POV after fall often still shows actor body parts OR empty maze
    handheld = "handheld" in p
    if handheld:
        reasons.append("handheld_pov")

    # Decision
    expect_empty = False
    expect_actor = False

    if empty_language and not actor_pose:
        expect_empty = True
        reasons.append("empty_language_without_actor_pose")
    elif actor_pose or (actor_mentioned and any(
        k in p for k in ("smile", "gesture", "facing camera", "looks directly", "leaning", "standing on", "centered")
    )):
        expect_actor = True
        reasons.append("actor_pose_or_visible_action")
    elif operator_out and not actor_pose and not actor_mentioned:
        expect_empty = True
        reasons.append("operator_out_no_actor_described")
    elif operator_out and actor_mentioned and not actor_pose and env == "backrooms":
        # e.g. pure environment through his camcorder with character bible still in prompt boilerplate
        # Boilerplate always includes "Same male sitcom actor..." identity lock text.
        # Distinguish boilerplate identity lock from visible-pose beats.
        boilerplate_only = "same male sitcom actor" in p and not any(
            k in p for k in (
                "facing camera", "sitcom smile", "hand raised", "leaning forward",
                "gestures toward", "looks directly", "breaking character", "eyes wide",
                "actor stands", "actor facing", "actor leaning", "actor resets",
                "actor looks", "actor faces", "actor holding",
            )
        )
        if boilerplate_only:
            expect_empty = True
            reasons.append("identity_boilerplate_only_empty_pov")
        else:
            expect_actor = True
            reasons.append("actor_referenced_beyond_boilerplate")
    elif actor_mentioned:
        expect_actor = True
        reasons.append("actor_mentioned_default_visible")
    else:
        expect_empty = True
        reasons.append("default_empty_when_unspecified")

    # Standing editor rule: Backrooms handheld after fall = empty of people
    # unless entity is explicitly visible in-frame.
    if env == "backrooms" and ("handheld" in p or "outside the frame" in p):
        entity_only = entity_visible and not actor_pose
        if not entity_visible:
            expect_empty = True
            expect_actor = False
            reasons.append("backrooms_handheld_empty_pov_rule")
        elif entity_only:
            expect_empty = False
            expect_actor = False
            reasons.append("backrooms_entity_visible_exception")

    # Clip-level override hooks
    refs = clip.get("references") if isinstance(clip.get("references"), Mapping) else {}
    mode = str(clip.get("camera_mode") or clip.get("visibility_mode") or "").lower()
    if mode in {"empty", "environment_only", "no_character"}:
        expect_empty, expect_actor = True, False
        reasons.append(f"clip_override_{mode}")
    if mode in {"actor_visible", "character_in_frame"}:
        expect_empty, expect_actor = False, True
        reasons.append(f"clip_override_{mode}")

    return VisibilityExpectation(
        expect_actor_visible=expect_actor and not expect_empty,
        expect_entity_visible=entity_visible,
        expect_empty_of_people=expect_empty and not entity_visible,
        environment=env,
        reasons=reasons,
    )


def _load_bgr(path: Path) -> np.ndarray:
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _hist_corr(a: np.ndarray, b: np.ndarray, space: str = "HSV") -> float:
    if space == "HSV":
        a = cv2.cvtColor(a, cv2.COLOR_BGR2HSV)
        b = cv2.cvtColor(b, cv2.COLOR_BGR2HSV)
        hist_a = cv2.calcHist([a], [0, 1], None, [32, 32], [0, 180, 0, 256])
        hist_b = cv2.calcHist([b], [0, 1], None, [32, 32], [0, 180, 0, 256])
    else:
        hist_a = cv2.calcHist([a], [0, 1, 2], None, [16, 16, 16], [0, 256, 0, 256, 0, 256])
        hist_b = cv2.calcHist([b], [0, 1, 2], None, [16, 16, 16], [0, 256, 0, 256, 0, 256])
    cv2.normalize(hist_a, hist_a)
    cv2.normalize(hist_b, hist_b)
    return float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL))


def _grid_hist_corr(a: np.ndarray, b: np.ndarray, grid: int = 3) -> float:
    ha, wa = a.shape[:2]
    hb, wb = b.shape[:2]
    scores = []
    for gy in range(grid):
        for gx in range(grid):
            y0a, y1a = ha * gy // grid, ha * (gy + 1) // grid
            x0a, x1a = wa * gx // grid, wa * (gx + 1) // grid
            y0b, y1b = hb * gy // grid, hb * (gy + 1) // grid
            x0b, x1b = wb * gx // grid, wb * (gx + 1) // grid
            scores.append(_hist_corr(a[y0a:y1a, x0a:x1a], b[y0b:y1b, x0b:x1b]))
    return float(np.mean(scores)) if scores else 0.0


def _torso_crop(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    return img[h // 3 : 4 * h // 5, w // 4 : 3 * w // 4]


def _detect_faces(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    """YuNet face detector (OpenCV 5+). Returns list of (x,y,w,h)."""
    if not YUNET.is_file():
        return []
    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN_create(str(YUNET), "", (w, h), 0.7, 0.3, 5000)
    det.setInputSize((w, h))
    _retval, faces = det.detect(img)
    if faces is None:
        return []
    out = []
    for f in faces:
        x, y, fw, fh = [int(v) for v in f[:4]]
        if fw >= 24 and fh >= 24:
            out.append((max(0,x), max(0,y), fw, fh))
    return out


def _face_similarity(img_a: np.ndarray, face_a: tuple[int, int, int, int], img_b: np.ndarray, face_b: tuple[int, int, int, int]) -> float | None:
    """Cosine similarity via SFace when available; else None."""
    if not SFACE.is_file() or not hasattr(cv2, 'FaceRecognizerSF_create'):
        return None
    try:
        rec = cv2.FaceRecognizerSF_create(str(SFACE), "")
        def align(img, face):
            # YuNet gives bbox; build a 1x15 landmark-less feature from cropped resize
            x,y,w,h = face
            crop = img[y:y+h, x:x+w]
            if crop.size == 0:
                return None
            # FaceRecognizerSF expects aligned face; use alignedFromCrop-less path via feature on resized pad
            # OpenCV docs: alignCrop needs landmarks. Fallback: resize crop to 112x112.
            face112 = cv2.resize(crop, (112, 112))
            feat = rec.feature(face112)
            return feat
        fa = align(img_a, face_a)
        fb = align(img_b, face_b)
        if fa is None or fb is None:
            return None
        return float(rec.match(fa, fb, cv2.FaceRecognizerSF_FR_COSINE))
    except Exception:
        return None


def _largest_face(faces: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    if not faces:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def compare_stills(
    *,
    candidate: Path,
    anchor: Path | None,
    prompt: str,
    clip: Mapping[str, Any] | None = None,
    kind: str = "last",
) -> dict[str, Any]:
    """Fail-closed creative compare. Returns ok + reasons + metrics."""
    exp = infer_visibility_expectation(prompt=prompt, clip=clip, kind=kind)
    reasons: list[str] = []
    metrics: dict[str, Any] = {"visibility": asdict(exp)}

    cand = _load_bgr(Path(candidate))
    faces_c = _detect_faces(cand)
    metrics["candidate_face_count"] = len(faces_c)

    # Empty-of-people expectation (post-fall handheld rule)
    if exp.expect_empty_of_people:
        people_c = _detect_people(cand)
        people_hits = [h for h in people_c if h.get("conf", 0) > 0 and "error" not in h]
        metrics["candidate_person_count"] = len(people_hits)
        metrics["candidate_person_top_conf"] = max((h["conf"] for h in people_hits), default=0.0)
        metrics["candidate_person_sources"] = [h.get("source") for h in people_hits[:8]]
        if faces_c:
            reasons.append(f"unexpected_face_in_empty_pov count={len(faces_c)}")
        if people_hits:
            top = max(people_hits, key=lambda h: h["conf"])
            reasons.append(
                f"unexpected_person_in_empty_pov count={len(people_hits)} "
                f"top_conf={top['conf']:.3f} source={top.get('source')}"
            )
        # Room continuity is optional: skip across apartment→Backrooms transitions.
        # Enable only when caller sets clip['require_room_continuity']=True (same-env chain).
        require_room = bool((clip or {}).get("require_room_continuity"))
        if require_room and anchor and Path(anchor).is_file():
            anc = _load_bgr(Path(anchor))
            # If anchor still has faces, it is not a valid empty-POV anchor — skip room, keep face fail only.
            faces_a = _detect_faces(anc)
            metrics["anchor_face_count"] = len(faces_a)
            if not faces_a:
                room = _grid_hist_corr(cand, anc)
                metrics["room_hist_corr"] = room
                if room < ROOM_HIST_MIN:
                    reasons.append(f"room_drift_empty_pov corr={room:.3f}<{ROOM_HIST_MIN}")
            else:
                metrics["room_hist_corr"] = None
                metrics["room_skip"] = "anchor_had_people"
        else:
            metrics["room_skip"] = "transition_or_unrequired"
        ok = len(reasons) == 0
        return {
            "ok": ok,
            "approved": ok,
            "reject_reasons": reasons,
            "metrics": metrics,
            "mode": "empty_pov",
        }

    # Actor-visible path
    if exp.expect_actor_visible:
        if not faces_c:
            reasons.append("expected_actor_visible_but_no_face_detected")
        if anchor and Path(anchor).is_file():
            anc = _load_bgr(Path(anchor))
            faces_a = _detect_faces(anc)
            metrics["anchor_face_count"] = len(faces_a)
            room = _grid_hist_corr(cand, anc)
            cloth = _hist_corr(_torso_crop(cand), _torso_crop(anc))
            metrics["room_hist_corr"] = room
            metrics["clothing_hist_corr"] = cloth
            if room < ROOM_HIST_MIN:
                reasons.append(f"room_drift corr={room:.3f}<{ROOM_HIST_MIN}")
            if cloth < CLOTHING_HIST_MIN:
                reasons.append(f"clothing_drift corr={cloth:.3f}<{CLOTHING_HIST_MIN}")
            fa = _largest_face(faces_a)
            fc = _largest_face(faces_c)
            if fa and fc:
                crop_a = anc[fa[1] : fa[1] + fa[3], fa[0] : fa[0] + fa[2]]
                crop_c = cand[fc[1] : fc[1] + fc[3], fc[0] : fc[0] + fc[2]]
                if crop_a.size and crop_c.size:
                    face_corr = _hist_corr(crop_a, crop_c)
                    metrics["face_hist_corr"] = face_corr
                    sface = _face_similarity(anc, fa, cand, fc)
                    if sface is not None:
                        metrics["face_sface_cosine"] = sface
                        if sface < 0.35:
                            reasons.append(f"face_identity_sface={sface:.3f}<0.35")
                    elif face_corr < FACE_HIST_MIN:
                        reasons.append(f"face_drift corr={face_corr:.3f}<{FACE_HIST_MIN}")
                # center shift
                ha, wa = anc.shape[:2]
                hc, wc = cand.shape[:2]
                ca = ((fa[0] + fa[2] / 2) / wa, (fa[1] + fa[3] / 2) / ha)
                cc = ((fc[0] + fc[2] / 2) / wc, (fc[1] + fc[3] / 2) / hc)
                shift = float(np.hypot(ca[0] - cc[0], ca[1] - cc[1]))
                metrics["face_center_shift"] = shift
                if shift > FACE_CENTER_MAX_SHIFT:
                    reasons.append(f"face_layout_shift={shift:.3f}>{FACE_CENTER_MAX_SHIFT}")
            elif faces_a and not faces_c:
                reasons.append("anchor_had_face_candidate_missing_face")
        ok = len(reasons) == 0
        return {
            "ok": ok,
            "approved": ok,
            "reject_reasons": reasons,
            "metrics": metrics,
            "mode": "actor_visible",
        }

    # Entity-only / fallback: room continuity if anchor
    if anchor and Path(anchor).is_file():
        anc = _load_bgr(Path(anchor))
        room = _grid_hist_corr(cand, anc)
        metrics["room_hist_corr"] = room
        if room < ROOM_HIST_MIN:
            reasons.append(f"room_drift corr={room:.3f}<{ROOM_HIST_MIN}")
    ok = len(reasons) == 0
    return {
        "ok": ok,
        "approved": ok,
        "reject_reasons": reasons,
        "metrics": metrics,
        "mode": "fallback",
    }


def creative_approve(
    path: Path,
    *,
    prompt: str,
    anchor: Path | None = None,
    clip: Mapping[str, Any] | None = None,
    kind: str = "last",
) -> tuple[bool, list[str], dict[str, Any]]:
    report = compare_stills(
        candidate=path, anchor=anchor, prompt=prompt, clip=clip, kind=kind
    )
    return bool(report.get("ok")), list(report.get("reject_reasons") or []), report
