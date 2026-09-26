"""Immutable Backrooms 102-clip pipeline rules lock (FLUX stills + MiniMax 192)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_PACK = ROOT / "Backrooms_Sitcom_Audition_Prompt_Pack_MERGED_FINAL.md"
LOCK_PATH = HERE / "runtime" / "gvd_backrooms_batch" / "PIPELINE_RULES_LOCK.json"
RULES_VERSION = "2026-09-18.v1"
DURATION_FRAMES = 192

FALLBACK_UNIVERSAL_NEGATIVE = (
    "No subtitles, captions, logos, watermark, readable text, extra limbs, duplicate people, "
    "face changes, costume changes, melted hands, fused fingers, warped limbs, floating objects, "
    "disappearing objects, duplicate camera, duplicate entity, flickering geometry, texture swimming, "
    "crawling wallpaper patterns, unstable lighting, frame tearing, broken perspective, impossible shadows, "
    "random room changes, accidental jump cuts, cartoon style, glossy commercial lighting, clean digital cinema, "
    "smooth gimbal movement, fantasy architecture, excessive fog, gore, blood, exaggerated monster face."
)

_WEIGHTED_TOKEN_RE = re.compile(r"\(([^:()]{1,80}):\s*[-+]?\d+(?:\.\d+)?\)")
_SDXL_LABEL_RE = re.compile(
    r"\b(?:SDXL|Stable[\s-]?Diffusion\s*XL|realvisxl|juggernaut\s*xl|pony\s*xl)\b",
    re.I,
)
_PLACEHOLDER_NEG_RE = re.compile(
    r"see\s+universal\s+negative|universal\s+negative\s+prompt\s+above",
    re.I,
)

APARTMENT_CUE = (
    "Mundane apartment living room on a tripod-mounted consumer camcorder (Mode A). "
)
LEVEL0_CUE = (
    "Level 0 Backrooms: sickly yellow wallpaper, damp carpet, fluorescent hum; "
    "diegetic handheld camcorder POV lock (Mode B+). "
)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def extract_universal_negative(pack_text: str | None = None, pack_path: Path | None = None) -> str:
    text = pack_text
    if text is None:
        path = Path(pack_path or DEFAULT_PACK)
        text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
    patterns = [
        r"Universal negative prompt[^\n]*:\s*\n+(No .+?)(?:\n\n|\n\*\*|\n---|\Z)",
        r"Universal negative prompt\s*\(append to every still and video prompt\):\s*(.+?)(?:\n\nUniversal|\n\*\*Universal|\n---|\Z)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I | re.S)
        if m:
            neg = " ".join(m.group(1).strip().split())
            neg = neg.lstrip("* ").strip()
            if neg.lower().startswith("no ") and "extra limbs" in neg.lower() and len(neg) > 80:
                return neg
    return FALLBACK_UNIVERSAL_NEGATIVE


def clip_num(cid: str) -> int | None:
    m = re.match(r"^C(\d{1,4})$", str(cid or "").strip().upper())
    if not m:
        return None
    return int(m.group(1))


def env_band(n: int | None) -> str:
    if n is None:
        return "unknown"
    if 1 <= n <= 14:
        return "apartment_tripod"
    if n == 15:
        return "fall"
    if n >= 16:
        return "level0_handheld"
    return "unknown"


def scrub_prompt(text: str) -> str:
    s = str(text or "")
    s = _WEIGHTED_TOKEN_RE.sub(r"\1", s)
    s = _SDXL_LABEL_RE.sub("", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def ensure_universal_negative(neg: str, universal: str) -> str:
    n = (neg or "").strip()
    if not n or _PLACEHOLDER_NEG_RE.search(n):
        return universal
    # Append universal artifact exclusions if missing key markers
    low = n.lower()
    if "extra limbs" not in low:
        return (n.rstrip(" .,;") + ". " + universal).strip()
    if "clean digital cinema" not in low and "digital cinema" not in low:
        return (n.rstrip(" .,;") + ". " + universal).strip()
    return n


def _is_literal(clip: dict) -> bool:
    return bool(clip.get("bypass_director") or clip.get("literal_prompt"))


def apply_immutable_rules(clip: dict, *, universal_negative: str | None = None) -> dict:
    """Return a shallow-copied clip with immutable editor rules applied."""
    out = dict(clip or {})
    uni = universal_negative or extract_universal_negative()
    cid = str(out.get("id") or "").upper()
    n = clip_num(cid)
    band = env_band(n)
    literal = _is_literal(out)

    for key in ("start_frame", "start_prompt", "video_prompt", "last_frame"):
        if key in out and out[key] is not None:
            out[key] = scrub_prompt(str(out[key]))

    # Negatives: start_frame_negative / negative_prompt / video negatives
    for key in ("negative_prompt", "start_frame_negative", "video_prompt_negative", "last_frame_negative"):
        if key in out or key == "negative_prompt":
            out[key] = ensure_universal_negative(str(out.get(key) or ""), uni)

    if not literal:
        start = str(out.get("start_prompt") or out.get("start_frame") or "")
        video = str(out.get("video_prompt") or "")
        if band == "apartment_tripod":
            if "apartment" not in start.lower() and "tripod" not in start.lower():
                start = (APARTMENT_CUE + start).strip()
            if "apartment" not in video.lower() and "tripod" not in video.lower():
                video = (APARTMENT_CUE + video).strip()
        elif band == "level0_handheld":
            need = ("yellow" not in start.lower()) and ("level 0" not in start.lower())
            if need:
                start = (LEVEL0_CUE + start).strip()
            need_v = ("yellow" not in video.lower()) and ("level 0" not in video.lower()) and ("handheld" not in video.lower())
            if need_v:
                video = (LEVEL0_CUE + video).strip()
        if "start_prompt" in out or out.get("start_frame"):
            if "start_prompt" in out:
                out["start_prompt"] = start
            if "start_frame" in out:
                out["start_frame"] = start
        if "video_prompt" in out:
            out["video_prompt"] = video

    out["rules_version"] = RULES_VERSION
    out["duration_frames"] = DURATION_FRAMES
    out["env_band"] = band
    out["_universal_negative"] = uni
    return out


def write_rules_lock(pack_path: Path | None = None) -> Path:
    pack = Path(pack_path or DEFAULT_PACK)
    uni = extract_universal_negative(pack_path=pack)
    payload = {
        "rules_version": RULES_VERSION,
        "written_at": _now(),
        "pack": str(pack.resolve()) if pack.is_file() else str(pack),
        "immutable_rules": [
            "FLUX.1 (FP8) stills first; natural-language image descriptions only (no weighted tokens, no SDXL labels).",
            "Env: C001-C014 mundane apartment living-room tripod camcorder; C015 FALL; C016+ Level 0 handheld/propped diegetic camcorder.",
            "MiniMax H3 motion handoff with duration_frames/length hard-forced to 192 (8s @ 24fps).",
            "Universal negative prompt appended to all still/video negatives (artifact exclusions).",
        ],
        "duration_frames": DURATION_FRAMES,
        "universal_negative": uni,
    }
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOCK_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LOCK_PATH)
    return LOCK_PATH


if __name__ == "__main__":
    p = write_rules_lock()
    print(f"wrote {p}")
    print(extract_universal_negative()[:120])