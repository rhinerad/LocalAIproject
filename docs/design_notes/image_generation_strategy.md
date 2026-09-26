# Design note — uncensored image generation, identity, and storyboard strategy

_Authored 2026-08-24. Rationale behind UPGRADE 13 (image + storyboard generator) and
19 (NSFW vision model). Target hardware: RTX 5080, 16 GB VRAM. Consent boundary:
identity/likeness tools are for the operator's own likeness or a consenting adult only._

## The two separable decisions

Realism of the pixels (the **base model**) and accuracy of a specific person's likeness
(the **identity method**) are independent. You choose one of each.

## Base model tiers that fit 16 GB

| Tier | Model | Notes |
|---|---|---|
| Workhorse (bulk storyboard) | SDXL photoreal — **RealVisXL V5** or **Juggernaut XL (Ragnarok)** | ~8 GB, 4–6 s/img, uncensored-friendly, deepest identity ecosystem, least new downloading. |
| Hero frames (max realism) | **Chroma1-HD** (FLUX-family, Apache, no safety alignment) or **FLUX.1-dev GGUF Q8** | ~12–13 GB, 20–30 s/img. |
| Draft/speed | **Z-Image Turbo** | ~6–8 GB, 2–3 s/img; verify uncensored status. |

Avoid llama.cpp-RPC / model-splitting for images; discrete per-tier models are faster
and stabler.

## Identity — the real lever for "make it look like me"

- **Personal LoRA** (train via the installed `kohya_ss`, ~20–30 varied photos) — most
  accurate and consistent likeness across a whole storyboard. The backbone.
- **InstantID + IPAdapter-FaceID** (SDXL) — zero-training, one photo, mature; the repo
  already has `insightface` / `photomaker` / `reactor`.
- **PuLID** (`ComfyUI-PuLID-Flux-Chroma`) — the equivalent on the Chroma/FLUX tier.

Rule of thumb: **base model decides realism, the LoRA decides likeness.** For a
storyboard full of consistent hyperreal "you", the LoRA is non-negotiable.

## Recommended pick

SDXL photoreal workhorse + a personal LoRA + InstantID drop-ins for the bulk;
Chroma+PuLID for hero reference sheets. Fastest, best hardware fit, least new download.

## How it plugs into the pipeline (UPGRADE 13)

story → local agent (abliterated reasoning model) decomposes to characters + shot list
→ generate character reference sheets → **STOP for operator approval (the project's
"reference overview before generations" rule)** → generate numbered storyboard frames
with identity + composition locked → output in the exact `batch_render_folder` job
layout so frames feed the MiniMax H3 video pipeline directly → Qwen2.5-VL watcher QCs
each frame (right characters? face matches sheet? artifacts?) with retry / human-review.

Reuse the one-GPU-owner lock, thermal guard, and the queue/watcher — image generation is
just another GPU workload that must yield to a render and respect VRAM arbitration.
