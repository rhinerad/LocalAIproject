# Claude Code / Codex prompt — swap the vision model to Qwen2.5-VL NSFW-caption (GGUF+mmproj)

Paste into your coding agent. Run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). Read `local_agent/capabilities.py`,
`local_agent/media_tools.py`, `local_agent/Modelfile.qwen3-vl-abliterated`, and (for
the diffusion part) the image pipeline from UPGRADE 13 first. **Stdlib only; server on
127.0.0.1; do not touch `outputs/equal_shares/**`.** Internet is available.

## What this changes (and what it does NOT)

The watcher's vision model is selected in `capabilities.vision_model()` from
`VISION_PREFERENCES`, and loaded through **Ollama** as a GGUF + mmproj imported via a
Modelfile (the pattern already used for `qwen3-vl-abliterated:8b-q8_0`). This prompt
**re-points that selection** to an uncensored Qwen2.5-VL caption model. It does **not**
rewrite the tiering, queue, or arbitration logic (UPGRADE 09/15) — only the model
identity, the Modelfile, and the config hints. Keep the fallback chain intact.

The **diffusion** model below is a *separate subsystem* (ComfyUI, safetensors) used only
by the image pipeline (UPGRADE 13). Do not conflate it with the Ollama VLM.

## Task 0 — verify the exact repos/files BEFORE downloading (mandatory)

These community NSFW repos rename and re-quantize often, so do not hard-code from
memory. Confirm on Hugging Face and record what actually exists in
`local_agent/UPGRADE/notes/nsfw_vision_model.md`:

- VLM GGUF repo, in priority order: `mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V3-GGUF`,
  then a `V4` or `…-abliterated` variant if present. Record the exact repo id, the
  chosen quant file (prefer **Q4_K_M** — ~4.7 GB, leaves the most VRAM headroom, which
  directly helps the deadlock work in UPGRADE 15), and the **matching mmproj** file
  (`mmproj-model-f16.gguf` or a version/quant-matched `*mmproj*.gguf`). The mmproj MUST
  come from the same repo/version as the base GGUF — a mismatched projector silently
  breaks vision.
- Diffusion repo: `starsfriday/Qwen-Image-NSFW` → the safetensors file name
  (e.g. `qwen_image_nsfw.safetensors`) and what base it expects.

If a stated repo/file is gone, pick the nearest current equivalent and **note the
substitution** — do not invent a filename.

## Task 1 — import the VLM into Ollama

Add `local_agent/Modelfile.qwen25-vl-nsfw` (mirror the existing qwen3-vl Modelfile):

    FROM <path>\Qwen2.5-VL-7B-NSFW-Caption-V3.Q4_K_M.gguf
    FROM <path>\<matching-mmproj>.gguf        # second FROM = the vision projector (required)

Download both files into one directory (under `ComfyUI-Shared\models\LLM\GGUF\...` to
match where the current GGUFs live), then:

    ollama create qwen25-vl-nsfw:7b-q4 -f local_agent\Modelfile.qwen25-vl-nsfw
    ollama show   qwen25-vl-nsfw:7b-q4        # capabilities MUST list: vision

If `ollama show` does not list `vision`, the mmproj was not picked up — fix the second
FROM before proceeding. **Verify the Qwen2.5-VL chat template is applied** (Ollama
usually embeds it; if replies are malformed, add the correct `TEMPLATE`/system format
for Qwen2.5-VL to the Modelfile — its image-token/system-role format differs from
Qwen3-VL).

## Task 2 — point the watcher at it

In `capabilities.py`, put the new tag at the front of `VISION_PREFERENCES` (keep the
qwen3-vl tags as later fallbacks so nothing breaks if the import is absent):

    VISION_PREFERENCES = [
        "qwen25-vl-nsfw:7b-q4",
        "qwen3-vl-abliterated:8b-q8_0",
        "huihui_ai/qwen3-vl-abliterated:8b-instruct-q8_0",
        ...
    ]

Update `vision_tiers()` (from UPGRADE 09) so its primary tier is the new model with the
correct VRAM need (~6 GB: Q4_K_M weights + f16 mmproj). Update the `capability("vision")`
install/size hints and the `EQUAL_SHARES_VISION_MODEL` override docs to the new model.
The selection still requires the tag to advertise `vision` — unchanged.

## Task 3 — gated NSFW diffusion (only if the image pipeline exists)

If UPGRADE 13's image pipeline is present (`work/image_render.py`), register
`Qwen-Image-NSFW` as a selectable diffusion checkpoint in its model inventory, loaded
**only when the diffusion path is actually called** — never at import/startup. Place the
safetensors in `ComfyUI-Shared\models\diffusion_models\` (or `checkpoints\` per its
type) and build the graph from the live ComfyUI `/object_info`. If the image pipeline is
NOT yet built, just record the repo/file in the notes doc for 13 to pick up — do not add
a half-wired loader.

## Task 4 — update dependency checks / setup docs

Update any download scripts, capability hints, or setup guides that name the old vision
model so they reference the new HF repo + companion mmproj requirement. Grep the repo
for the old tag and fix stale references (README, START_* docs, comments).

## Verify (show commands/output)

- `python local_agent/test_media_analysis.py` and `test_native_tool_calling.py` still
  green (the two vision selection tests must still pass with the new preference list).
- `capabilities.vision_model()` returns the new tag when it is installed and advertises
  vision; falls back correctly when it is not.
- `validate_h3_prompt.py` still 124/124.
- Live (needs the real box — mark unverified): `ollama show` lists vision for the new
  model; a `see_image` call returns a caption; the diffusion model loads only when the
  image pipeline invokes it.

## Record it

`CHANGELOG/<today>_vision_model_nsfw_swap.md` — the verified repo/file names (from Task
0), the Modelfile, the preference change, VRAM figure, and what stayed unverified. Add
its row to `CHANGELOG/README.md`; update `local_agent/README.md` (new Modelfile + model)
and the vision-watcher note. State plainly that only the model identity changed; the
tiering/queue/arbitration logic is untouched.
