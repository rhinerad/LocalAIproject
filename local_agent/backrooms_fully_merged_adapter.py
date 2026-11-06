"""Post-process FULLY MERGED camera-logic pack clips after plain-header parse.

Source Markdown stays immutable. Expands universal negatives/anchors, binds
BacHal env LoRA for Mode B/C (C016+), staticizes still motion verbs, and
records camera_mode for downstream QA.
"""
from __future__ import annotations
import re
from pathlib import Path

from backrooms_prompt_adapter import staticize_still_shot

LORA_NAME = "BacHal_(Background)_(SDXL)_(AD).safetensors"
LORA_PATH_HINT = r"A:\Users\rhine\ComfyUI-Shared\models\loras\BacHal_(Background)*(SDXL)*(AD).safetensors"

_UNI_NEG_RE = re.compile(
    r"Universal negative prompt \(append to every still and video prompt\):\s*(.+?)(?=\nUniversal continuity|\nUniversal overall|\nSECTION|\Z)",
    re.I | re.S,
)
_UNI_CONT_RE = re.compile(
    r"Universal continuity anchors \(append to every still\):\s*(.+?)(?=\nUniversal overall|\nSECTION|\Z)",
    re.I | re.S,
)
_MODE_RE = re.compile(r"Camera Mode:\s*([A-Za-z]+)", re.I)
_LORA_LINE_RE = re.compile(r"Required Backrooms SDXL LoRA:\s*(.+)", re.I)
_CLIP_NUM = re.compile(r"^C(\d+)$", re.I)


def _collapse(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def _extract_universals(source: str) -> tuple[str, str]:
    neg = _UNI_NEG_RE.search(source or "")
    cont = _UNI_CONT_RE.search(source or "")
    return (
        _collapse(neg.group(1) if neg else ""),
        _collapse(cont.group(1) if cont else ""),
    )


def _mode_from_heading(heading: str, clip_id: str) -> str:
    m = _MODE_RE.search(heading or "")
    if m:
        return m.group(1).upper()
    n = int(_CLIP_NUM.match(clip_id).group(1)) if _CLIP_NUM.match(clip_id or "") else 0
    if n <= 14:
        return "A"
    if n == 15:
        return "FALL"
    if n <= 62:
        return "B"
    return "C"


def _use_flux(source: str, settings=None) -> bool:
    if settings:
        backend = str(settings.get("still_backend") or settings.get("model_profile") or "").lower()
        if backend == "flux" or settings.get("reject_sdxl") or settings.get("source_has_flux_override"):
            return True
    raw = source or ""
    if "### 0. Flux" in raw or re.search(r"(?i)still-image\s+generator\s+is\s+Flux", raw):
        return True
    return False


def apply(clips: list[dict], source: str, settings=None) -> list[dict]:
    if "FULLY MERGED" not in (source or "") and "CAMERA-LOGIC CORRECTED" not in (source or ""):
        return clips
    uni_neg, uni_cont = _extract_universals(source)
    if not uni_neg:
        raise ValueError("FULLY MERGED pack missing Universal negative prompt block")
    use_flux = _use_flux(source, settings)
    override_resolution = (
        "EDITOR OVERRIDES Rule 0 Flux: still_backend=flux beats SDXL labels/LoRA in body text."
        if use_flux else
        "No Flux override; RealVisXL/SDXL path retained for FULLY MERGED pack."
    )
    out = []
    for clip in clips:
        clip = dict(clip)
        cid = str(clip.get("id") or "").upper()
        n = int(cid[1:]) if cid[1:].isdigit() else 0
        mode = clip.get("camera_mode") or _mode_from_heading(clip.get("header") or "", cid)
        clip["camera_mode"] = mode
        clip["model_profile"] = "realpro_flux" if use_flux else "realvisxl"
        clip["aspect_ratio"] = "4:3"
        clip["override_resolution"] = override_resolution
        clip["fully_merged_applied"] = True
        for field in ("start_frame", "last_frame"):
            raw = str(clip.get(field) or "")
            clip["source_" + field] = raw
            # Strip pack metadata lines that belong outside the positive prompt body.
            body = raw
            lora_m = _LORA_LINE_RE.search(body)
            if lora_m:
                # Keep instructional LoRA prose but bind concrete filename for render.
                pass
            # Remove "Required Backrooms SDXL LoRA: <path>" line path noise for gate,
            # keep the following env-helper sentence.
            body = re.sub(
                r"Required Backrooms SDXL LoRA:\s*.+\n?",
                f"Required Backrooms SDXL LoRA: {LORA_NAME}. ",
                body,
                count=1,
                flags=re.I,
            )
            body = staticize_still_shot(body)
            if uni_cont and uni_cont.lower() not in body.lower():
                body = (body.rstrip() + " " + uni_cont).strip()
            # Gate-friendly environment cues without rewriting camera mode locks.
            if n <= 14 or (n == 15 and field == "start_frame"):
                if "apartment" not in body.lower():
                    body += " Ordinary apartment living room audition space."
            else:
                if "backrooms" not in body.lower() and "yellow wallpaper" not in body.lower():
                    if n == 15 and field == "last_frame":
                        body += " Transitional fall into yellow Level 0 Backrooms blur."
                    else:
                        body += " Level 0 Backrooms yellow wallpaper environment."
            clip[field] = body
            neg = str(clip.get(field + "_negative") or "")
            if not neg or "see universal" in neg.lower():
                neg = uni_neg
            elif uni_neg and uni_neg.lower() not in neg.lower():
                neg = (neg.rstrip(" .") + ". " + uni_neg).strip()
            clip[field + "_negative"] = neg
            use_lora = (n >= 16) and not use_flux
            clip[field + "_lora"] = (
                {"name": LORA_NAME, "strength": 0.5, "path_hint": LORA_PATH_HINT}
                if use_lora else None
            )
            if use_flux:
                # Remove SDXL LoRA path noise from body for Flux natural language.
                body_clean = re.sub(
                    r"Required Backrooms SDXL LoRA:\s*.+",
                    "Flux environment description only; no SDXL LoRA.",
                    str(clip.get(field) or ""),
                    count=1,
                    flags=re.I,
                )
                clip[field] = body_clean
        video = str(clip.get("video_prompt") or "")
        clip["source_video_prompt"] = video
        if uni_neg and "see universal" in (clip.get("video_negative") or "").lower():
            clip["video_negative"] = uni_neg
        elif not clip.get("video_negative"):
            clip["video_negative"] = uni_neg
        out.append(clip)
    return out
