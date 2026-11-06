# Claude Code / Codex prompt — uncensored image + reference + storyboard generator

Paste into your coding agent. Run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). This builds the project's stated core goal:
**feed a story in → get a character-locked storyboard of reference images out**,
with a **reference-image overview for approval before mass generation**, wired into
the existing MiniMax H3 video pipeline.

Read first: `local_agent/README.md`, `CLAUDE.md`, `README.md`,
`work/batch_render_folder.py`, `work/render_single_pass.py` (or the current single-
render path), `work/thermal_guard.py`, `docs/reference/MINIMAX_PROMPT_GUIDE_ref.md`,
and how `outputs/equal_shares/runtime/render_queue_owner.json` is claimed. Internet
is available (downloads allowed). **Do not touch `outputs/equal_shares/**`** — image
output lives in its own tree.

## Target stack (decided; confirm availability in Phase 0)

- **Workhorse base (bulk storyboard):** a photoreal **SDXL** checkpoint —
  **RealVisXL V5.0** or **Juggernaut XL (Ragnarok)**. Fast (~4–6 s/1024px), ~8 GB,
  uncensored-friendly, best identity ecosystem.
- **Hero-frame tier (max realism):** **Chroma1-HD** (FLUX-family, Apache, no safety
  alignment) or **FLUX.1-dev GGUF Q8**, ~12–13 GB.
- **Identity (looks like a real person, consistently):**
  - **Personal LoRA** trained via the installed **`kohya_ss`** — the accuracy/
    consistency backbone for recurring characters.
  - **InstantID + IPAdapter-FaceID** on SDXL (you already have `insightface`,
    `photomaker`, `reactor`) for zero-training drop-ins from one photo.
  - **PuLID** (`ComfyUI-PuLID-Flux-Chroma`) for the Chroma/FLUX tier.
- **Realism polish:** a Detail-Tweaker / skin LoRA (SDXL) or XLabs RealismLoRA (Flux).

## Hard rules (hold across every phase)

- **One GPU owner, ever.** This pipeline claims/respects the same render lock as the
  H3 pipeline (`render_queue_owner.json` + port 8188). It must never generate while
  an Equal Shares render or the audio pass owns the card, and it must yield the same
  way. Reuse `thermal_guard`.
- **Reference overview before mass generation** (the project's founding requirement):
  character reference sheets are generated and **presented for operator approval
  first**; full storyboard generation only proceeds on approval.
- **Consent boundary:** identity/likeness tools are for the operator's own likeness or
  a consenting adult only — never a minor, never a non-consenting real person. Put a
  one-line gate in the character-ingest step stating this; do not build face tooling
  that targets arbitrary scraped faces.
- Never delete a source photo, a generated frame, a reference sheet, or a manifest.
- Every phase ends with a `CHANGELOG/` entry (what/why/evidence/verified/unverified).

## Phase 0 — inventory + install plan (STOP gate)

Do not download gigabytes before the operator approves. Produce
`work/notes/image_stack_inventory.md`:

1. Query the live ComfyUI at `127.0.0.1:8188` `/object_info` and list which relevant
   nodes exist: KSampler/samplers, **ControlNet**, **IPAdapter** (FaceID), **InstantID**,
   **PuLID** (Flux/Chroma), img2img/VAE-encode, LoRA loader, GGUF/UNET loaders.
2. List installed models in `ComfyUI-Shared/models`: `checkpoints/`, `loras/`,
   `controlnet/`, `ipadapter/`, `insightface/` (need `antelopev2` for InstantID),
   `pulid/`, `clip_vision/`, `unet|diffusion_models/`, `vae/`.
3. From the gaps, list exact downloads with sizes and target folders: the chosen SDXL
   photoreal checkpoint, InstantID (its ControlNet + ip-adapter + antelopev2),
   IPAdapter-FaceID models, Chroma1-HD (or FLUX Q8 + its clip/t5/vae), PuLID-Flux-Chroma
   node + weights, a realism LoRA. Note which custom nodes must be `git clone`d.
4. Confirm VRAM budget: SDXL + ControlNet + InstantID fits ~10–12 GB; Chroma/FLUX Q8 +
   PuLID is ~14–15 GB (won't run beside a video render — the lock handles that).

**STOP and report the plan before downloading.**

## Phase 1 — the image render core

`work/image_render.py`: a ComfyUI-API driver, analogous to the H3 single-pass render,
that submits an image graph and returns the saved PNG(s).

- Modes: **text→image**, **reference img→img** (VAE-encode an input photo + denoise),
  and **identity-conditioned** (LoRA and/or InstantID/IPAdapter for SDXL; PuLID for
  Chroma). One function, tier-selectable (`--tier workhorse|hero`).
- Claims `render_queue_owner.json`, runs under `thermal_guard`, refuses to start beside
  another backend. Deterministic seed handling + a per-image manifest (prompt, model,
  identity source, seed, controlnet, output path).
- Output tree: `outputs/stories/<story>/…` — never under `outputs/equal_shares/`.
- Build graphs from the live `/object_info` (do not hard-code node internals); validate
  the graph and **stop-and-report** if a required node/socket is missing, the way
  `batch_render_folder` does.

Verify: `--plan`/dry-run builds a valid graph; one real text→image and one
reference→image generation succeed (attach the outputs); manifest written.

## Phase 2 — personal LoRA training helper (kohya_ss)

`work/train_character_lora.py` (or a documented runbook) that drives the installed
`kohya_ss`:

- Input: a folder of ~20–30 varied photos of a character (the operator, by default).
- Auto-caption (BLIP/existing tagger), sensible SDXL LoRA training config for a 16 GB
  card, output a named LoRA into `ComfyUI-Shared/models/loras/characters/<name>.safetensors`.
- Register the character in `outputs/stories/character_library.json` — name, trigger
  word, LoRA path, and a reference photo — so the storyboard generator can look it up.
- Respect the one-GPU-owner rule (training is a long GPU job → claim the lock, or run
  only when idle).

Verify: a small smoke-run reaches training start (or documents the exact command +
config if a full train is too long for the session); the character library entry is
written.

## Phase 3 — story → storyboard (the headline feature)

`work/storyboard_from_story.py`:

1. **Decompose** the input story/script with the local agent's abliterated reasoning
   model (`huihui_ai/qwen3-abliterated:14b`, via the existing agent/router path — reuse
   it, don't re-implement) into: a **character list** (name, description, which need a
   real-person identity source) and an ordered **shot list** (scene, shot id, characters
   present, setting, lighting, action, camera/composition). Persist as JSON.
2. **Character reference sheets:** for each character generate a small sheet (front /
   3-4 / profile, neutral + key expressions) using the identity source — a registered
   LoRA, or InstantID/PuLID from a supplied photo. Save to `outputs/stories/<story>/refs/`.
3. **REFERENCE OVERVIEW → STOP for approval.** Present all character sheets (a contact
   sheet or the GUI) and wait. The operator approves, regenerates a character, or swaps
   a photo. **No storyboard frames are generated until approval.** This is the project's
   founding rule — enforce it, do not auto-proceed.
4. **Storyboard frames:** on approval, generate one keyframe per shot with identity
   locked (same LoRA/adapter) and composition guided (ControlNet pose/depth where a
   reference or sketch is given). Number them in the **exact job layout
   `batch_render_folder.py` consumes** (numbered prompts + `img0/ img1/…` reference
   slots), so the storyboard feeds the H3 video renderer directly.
5. Write a storyboard manifest linking each frame to its shot, characters, and seed.

Verify: on a short 3–4 shot test story, the decomposition, ref sheets, the approval
gate (must block), and numbered frame output all work; the output folder is a valid
`batch_render_folder` job (run its `--plan` against it).

## Phase 4 — automatic QC with the vision watcher

Close the loop with the abliterated **Qwen3-VL** watcher already in the tree:

- After each frame, call the vision path to check: are the intended characters present,
  does the face match the character's reference sheet, is the composition/shot sane, any
  obvious artifacts. Return a pass/flag + reason.
- Flagged frames get a bounded retry (new seed / ladder), then a `human_review_needed`
  item — mirror the audio pass's validate→review→retry discipline. Never silently accept.

Verify: QC runs on the test frames and correctly flags a deliberately wrong one.

## Record it

A `CHANGELOG/` entry per phase (or one comprehensive entry) with the inventory, the
chosen models + measured VRAM, and sample outputs referenced. Add `image_render.py`,
`train_character_lora.py`, `storyboard_from_story.py`, and the character library to
`README.md`'s implementation map. Note plainly what is verified live vs unverified.

## Sequence note to the operator

Phase 0 (inventory + approve downloads) and Phase 1 (single-image render on the SDXL
workhorse) give a working uncensored image + reference-img generator fast. The personal
LoRA (Phase 2) and the full story→storyboard automation (Phase 3–4) build on that. Do
them in order; each phase is independently useful and independently reversible.
