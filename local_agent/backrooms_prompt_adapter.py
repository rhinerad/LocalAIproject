"""Apply the operator's reviewed Backrooms control layer to render inputs.

The source Markdown stays immutable; raw prompts accompany effective prompts.
Only the explicitly named reviewed pack uses this adapter.

Flux EDITOR OVERRIDES (Rule 0) beat SDXL labels/LoRA in body text.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

STILL_SDXL = (
    "Static SDXL reference still for image-to-video, authentic 1990s consumer camcorder recording, "
    "4:3 composition, sharp readable pose, stable anatomy and perspective, mild analog softness, "
    "restrained color, realistic texture, natural practical lighting. "
)
STILL_FLUX = (
    "Static Flux reference still for image-to-video, authentic 1990s consumer camcorder recording, "
    "4:3 composition, sharp readable pose, stable anatomy and perspective, mild analog softness, "
    "restrained color, realistic texture, natural practical lighting. "
)
ACTOR = (
    "Same male sitcom actor, late 20s, average build, expressive ordinary face, short messy dark-brown hair, "
    "faint five-o'clock shadow, olive-green overshirt over a faded gray T-shirt, dark straight-leg jeans, "
    "worn white sneakers, cheap digital watch on the left wrist. "
)
ENTITY = (
    "Same very tall, extremely thin humanoid entity, approximately 2.2 meters tall, matte charcoal-black "
    "surface, long arms, narrow shoulders, slightly oversized head, indistinct facial features. "
    "Its behavior can be friendly but its anatomy and uncanny appearance remain unchanged. "
)
APARTMENT = (
    "Ordinary apartment living room, taped audition mark, chair with script pages, warm household lamp, "
    "flat ceiling light, ordinary walls and believable clutter. Fixed tripod-mounted camcorder viewpoint; "
    "the camcorder body, lens, tripod and operator are completely outside the frame. "
)
BACKROOMS = (
    "Level 0 Backrooms, sickly yellow patterned wallpaper, damp brown-beige carpet, low acoustic ceiling tiles, "
    "rectangular fluorescent fixtures, repetitive office openings, subtle water damage. "
    "View through the actor's handheld camcorder from his physical position; the camcorder body, lens and operator are completely outside the frame. "
)
NEGATIVE = (
    "motion blur, action smear, outside camera, visible recording camera, drone, gimbal, reverse angle, selfie, "
    "third-person observer, extra limbs, fused fingers, melted hands, face change, costume change, duplicate actor, "
    "duplicate entity, floating objects, disappearing objects, warped perspective, crawling wallpaper, "
    "duplicated ceiling lights, impossible shadows, unstable geometry, texture swimming, frame tearing, "
    "accidental jump cut, random room change, subtitles, captions, watermark, logo, readable text, "
    "glossy digital cinema, cartoon style, excessive fog, gore, blood"
)
LORA = "BacHal_(Background)_(SDXL)_(AD).safetensors"
_SDXL_WEIGHT_RE = re.compile(r"\([^)]+:\d+(?:\.\d+)?\)")

# Still prompts must be static poses. Convert actor/entity motion verbs that
# media_accuracy_gate rejects into frozen pose language (EDITED rule #1).
_MOTION_STATIC = [
    (re.compile(r"\b(Actor|Entity)\s+turns?\s+the\s+camera\b", re.I), r"Camera aimed"),
    (re.compile(r"\b(Actor|Entity)\s+turns?\s+toward\b", re.I), r"\1 facing"),
    (re.compile(r"\b(Actor|Entity)\s+turns?\s+away\s+from\b", re.I), r"\1 facing away from"),
    (re.compile(r"\b(Actor|Entity)\s+turns?\s+forward\b", re.I), r"\1 facing forward"),
    (re.compile(r"\b(Actor|Entity)\s+turns?\s+and\s+runs?\b", re.I), r"\1 mid-run retreating,"),
    (re.compile(r"\b(Actor|Entity)\s+turns?\b", re.I), r"\1 facing"),
    (re.compile(r"\b(Actor|Entity)\s+leans?\b", re.I), r"\1 leaning"),
    (re.compile(r"\b(Actor|Entity)\s+walks?\s+toward\b", re.I), r"\1 closer to"),
    (re.compile(r"\b(Actor|Entity)\s+walks?\s+past\b", re.I), r"\1 beside"),
    (re.compile(r"\b(Actor|Entity)\s+walks?\b", re.I), r"\1 standing near"),
    (re.compile(r"\b(Actor|Entity)\s+runs?\s+around\b", re.I), r"\1 mid-run around"),
    (re.compile(r"\b(Actor|Entity)\s+runs?\s+through\b", re.I), r"\1 mid-run through"),
    (re.compile(r"\b(Actor|Entity)\s+runs?\s+back\b", re.I), r"\1 mid-run back"),
    (re.compile(r"\b(Actor|Entity)\s+runs?\b", re.I), r"\1 mid-run"),
    (re.compile(r"\b(Actor|Entity)\s+approaches?\b", re.I), r"\1 near"),
    (re.compile(r"\b(Actor|Entity)\s+moves?\s+one\s+step\b", re.I), r"\1 positioned one step"),
    (re.compile(r"\b(Actor|Entity)\s+moves?\b", re.I), r"\1 positioned"),
    (re.compile(r"\b(Actor|Entity)\s+waves?\b", re.I), r"\1 with one hand raised"),
    (re.compile(r"\b(Actor|Entity)\s+spins?\b", re.I), r"\1 mid-spin"),
    (re.compile(r"\b(Actor|Entity)\s+jerks?\b", re.I), r"\1 mid-jerk with"),
    (re.compile(r"\b(Actor|Entity)\s+presses?\b", re.I), r"\1 pressing"),
    (re.compile(r"\b(Actor|Entity)\s+points?\b", re.I), r"\1 pointing"),
    (re.compile(r"\b(Actor|Entity)\s+reaches?\b", re.I), r"\1 reaching"),
    (re.compile(r"\b(Actor|Entity)\s+holds?\b", re.I), r"\1 holding"),
    (re.compile(r"\b(Actor|Entity)\s+raises?\b", re.I), r"\1 with raised"),
    (re.compile(r"\b(Actor|Entity)\s+smiles?\b", re.I), r"\1 smiling"),
    (re.compile(r"\b(Actor|Entity)\s+falls?\b", re.I), r"\1 mid-fall"),
]


def staticize_still_shot(shot: str) -> str:
    """Rewrite motion verbs into static pose language for stills."""
    out = str(shot or "")
    for pattern, repl in _MOTION_STATIC:
        out = pattern.sub(repl, out)
    return out


def detect_flux_override(source: str) -> bool:
    raw = str(source or "")
    if "### 0. Flux" in raw:
        return True
    if re.search(r"(?i)still-image\s+generator\s+is\s+Flux", raw):
        return True
    if re.search(r"(?i)\bFlux\s+Frames\s+First\b", raw) and "## EDITOR OVERRIDES" in raw:
        return True
    return False


def _strip_sdxl_weight_syntax(text: str) -> str:
    return _SDXL_WEIGHT_RE.sub(lambda m: m.group(0).strip("()").split(":")[0], text)


def _resolve_use_flux(source: str, settings: Mapping[str, Any] | None) -> bool:
    if settings:
        backend = str(settings.get("still_backend") or settings.get("model_profile") or "").lower()
        if backend == "flux":
            return True
        if settings.get("reject_sdxl"):
            return True
        if settings.get("source_has_flux_override"):
            return True
    return detect_flux_override(source)


def apply(clips, source, settings: Mapping[str, Any] | None = None):
    raw = str(source or "")
    # FULLY MERGED packs already use "### Cxxx — START/LAST FRAME IMAGE" sections.
    # This rewriter looks for an older anchor sentence that those sections do not
    # contain, and raising here used to discard the whole paste.
    if "FULLY MERGED" in raw or "CAMERA-LOGIC CORRECTED" in raw:
        return clips
    if not ("## EDITOR OVERRIDES" in raw and "Backrooms Sitcom" in raw):
        return clips
    use_flux = _resolve_use_flux(source, settings)
    still_prefix = STILL_FLUX if use_flux else STILL_SDXL
    override_resolution = (
        "EDITOR OVERRIDES Rule 0 Flux: still_backend=flux beats SDXL labels/LoRA "
        "in body text; no BacHal_ SDXL LoRA; natural-language prompts only."
        if use_flux
        else "No Flux override detected; legacy RealVisXL/SDXL path retained."
    )
    for index, clip in enumerate(clips):
        number = int(clip["id"][1:])
        clip["editor_overrides_applied"] = True
        clip["model_profile"] = "realpro_flux" if use_flux else "realvisxl"
        clip["aspect_ratio"] = "4:3"
        clip["override_resolution"] = override_resolution
        # Still-review metadata for this (pre-FULLY-MERGED) pack format, read by
        # the still-QA modules. NOT a render-continuity input: batch_run_backrooms_gvd
        # takes clip-to-clip chaining decisions from work/scene_reasoner.py only
        # (and this adapter returns early for the FULLY MERGED pack it renders).
        clip["references"] = {
            "start": "generate_initial_anchor" if index == 0 else f"{clips[index-1]['id']}_approved_last_frame",
            "last": f"{clip['id']}_approved_last_frame",
            "video_requires_still_review": True,
        }
        for field in ("start_frame", "last_frame"):
            original = clip[field]
            clip["source_" + field] = original
            anchor = "The viewer is seeing through the character's camcorder."
            if anchor not in original:
                raise ValueError(f"{clip['id']}: reviewed adapter cannot locate shot composition in {field}")
            shot = original.split(anchor, 1)[1].strip()
            # Keep the unique shot sentence that follows the shared LoRA
            # boilerplate. Cutting at "For every SDXL still" collapsed many
            # frames into the same generic room.
            lora_end = re.search(r"Do not apply this LoRA.*?Backrooms\.\s*", shot, re.I | re.S)
            if lora_end:
                shot = shot[lora_end.end() :]
            # Also strip the SDXL LoRA instruction paragraph when Flux.
            if use_flux:
                shot = re.sub(
                    r"For every SDXL still image.*?unless the frame has already entered the Backrooms\.\s*",
                    "",
                    shot,
                    flags=re.I | re.S,
                )
            shot = shot.split("Preserve all character identity", 1)[0].strip()
            if use_flux:
                shot = _strip_sdxl_weight_syntax(shot)
            # C015 spans the fall: its opening is still the apartment, ending is carpet.
            inside = number >= 16 or (number == 15 and field == "last_frame")
            environment = BACKROOMS if inside else APARTMENT
            identity = (
                ACTOR
                if number <= 14 or re.search(r"\b(actor|hand|arm|watch|sneaker)\b", shot, re.I)
                else ""
            )
            entity = (
                ENTITY
                if re.search(r"\b(entity|humanoid)\b", shot, re.I) and inside
                else ""
            )
            # The physical camera records the scene; it is not an object filmed externally.
            shot = re.sub(r"camcorder on tripod,?\s*", "", shot, flags=re.I)
            clip[field] = still_prefix + environment + identity + entity + staticize_still_shot(shot)
            clip[field + "_negative"] = NEGATIVE + (
                ", yellow wallpaper, damp carpet, entity, supernatural distortion"
                if not inside
                else ", apartment furniture"
            )
            # Never attach SDXL LoRA when Flux.
            if use_flux:
                clip[field + "_lora"] = None
            else:
                clip[field + "_lora"] = {"name": LORA, "strength": 0.5} if inside else None
        original_video = clip["video_prompt"]
        clip["source_video_prompt"] = original_video
        alignment = original_video.split("\n", 1)[0]
        if "Beginning from Picture 1," not in original_video:
            raise ValueError(f"{clip['id']}: reviewed adapter cannot locate video action")
        action = (
            original_video.split("Beginning from Picture 1,", 1)[1]
            .split("The action develops continuously", 1)[0]
            .strip()
        )
        camera = (
            "Fixed tripod-mounted camcorder view."
            if number <= 14
            else "View through the actor's physical handheld camcorder."
        )
        take = (
            "The explicitly planned brief static cut occurs here."
            if number == 69
            else "One continuous physical take, no unplanned cut."
        )
        sound = (
            "Apartment room tone, mild tape hiss, breath, clothing and only sounds caused by the action."
            if number <= 14
            else "Built-in camcorder microphone: fluorescent hum, tape hiss, breath, footsteps, handling noise and sounds caused by the action."
        )
        clip["video_prompt"] = (
            alignment
            + "\n\nintegrated_multimodal_description: [Shot 1] "
            + camera
            + " "
            + take
            + " "
            + action
            + " Preserve actor identity, clothing, entity anatomy, room geometry and screen direction. "
            "Natural acceleration and deceleration; settle into Picture 2 during the final 1.5 seconds. "
            "Keep that endpoint stable for the next clip. No visible camera, camcorder body, lens, tripod or operator; "
            "no outside camera, teleportation, morphing, geometry flicker or invented props."
            + "\n\noverall_soundscape: "
            + sound
            + "\n\nnon_diegetic_music: N/A"
        )
    return clips
