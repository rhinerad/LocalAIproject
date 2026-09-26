from pathlib import Path

root = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
qa = root / "creative_still_qa.py"
text = qa.read_text(encoding="utf-8")
bak = qa.with_suffix(".py.bak_people")
if not bak.exists():
    bak.write_text(text, encoding="utf-8")

helper = r'''
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

'''

needle = "FACE_CENTER_MAX_SHIFT = 0.28  # fraction of frame diagonal\n"
if "def _detect_people" not in text:
    if needle not in text:
        raise SystemExit("needle missing for helper insert")
    text = text.replace(needle, needle + "\n" + helper)

old_empty = """    # Empty-of-people expectation (post-fall handheld rule)
    if exp.expect_empty_of_people:
        if faces_c:
            reasons.append(f\"unexpected_face_in_empty_pov count={len(faces_c)}\")
"""

new_empty = """    # Empty-of-people expectation (post-fall handheld rule)
    if exp.expect_empty_of_people:
        people_c = _detect_people(cand)
        people_hits = [h for h in people_c if h.get(\"conf\", 0) > 0 and \"error\" not in h]
        metrics[\"candidate_person_count\"] = len(people_hits)
        metrics[\"candidate_person_top_conf\"] = max((h[\"conf\"] for h in people_hits), default=0.0)
        metrics[\"candidate_person_sources\"] = [h.get(\"source\") for h in people_hits[:8]]
        if faces_c:
            reasons.append(f\"unexpected_face_in_empty_pov count={len(faces_c)}\")
        if people_hits:
            top = max(people_hits, key=lambda h: h[\"conf\"])
            reasons.append(
                f\"unexpected_person_in_empty_pov count={len(people_hits)} \"
                f\"top_conf={top['conf']:.3f} source={top.get('source')}\"
            )
"""

if "unexpected_person_in_empty_pov" not in text:
    if old_empty not in text:
        raise SystemExit("empty branch needle missing")
    text = text.replace(old_empty, new_empty)

qa.write_text(text, encoding="utf-8")
print("creative_still_qa.py patched", qa.stat().st_size)

batch = root / "flux_still_batch.py"
bt = batch.read_text(encoding="utf-8")
bb = batch.with_suffix(".py.bak_people")
if not bb.exists():
    bb.write_text(bt, encoding="utf-8")

if "empty_pov_prompt_boost" not in bt:
    if "from creative_still_qa import creative_approve" in bt:
        bt = bt.replace(
            "from creative_still_qa import creative_approve",
            "from creative_still_qa import creative_approve, empty_pov_prompt_boost, infer_visibility_expectation",
        )
    elif "import creative_still_qa" in bt:
        bt = bt.replace(
            "import creative_still_qa",
            "import creative_still_qa\nfrom creative_still_qa import empty_pov_prompt_boost, infer_visibility_expectation",
        )
    else:
        bt = "from creative_still_qa import empty_pov_prompt_boost, infer_visibility_expectation\n" + bt

boost_snip = """
            # Harden empty-POV generations: force vacant language + strong no-people negatives.
            try:
                _exp = infer_visibility_expectation(prompt=prompt, clip=c, kind=kind)
                if _exp.expect_empty_of_people:
                    prompt, _neg_boost = empty_pov_prompt_boost(prompt)
                    negative = ((negative + \", \") if negative else \"\") + _neg_boost
            except Exception as _e:
                print(f\"WARN empty_pov_prompt_boost failed: {_e}\", flush=True)
"""

if "empty_pov_prompt_boost(prompt)" not in bt:
    marker = "rec = render_one("
    if marker not in bt:
        raise SystemExit("render_one marker missing")
    bt = bt.replace(marker, boost_snip + "\n" + marker, 1)

batch.write_text(bt, encoding="utf-8")
print("flux_still_batch.py patched")
