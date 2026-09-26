# 2026-09-26h — Wan 2.2 Animate 14B fp8 weights downloaded with operator approval (18,401,760,586 B, sha256 verified against the Hub LFS oid); nothing loaded, no template, no profile, catalog row still disabled

Executes the download half of operator decision 1 in `2026-09-26d` ("Also
approve Wan 2.2 Animate (~17 GB)", chat, 2026-09-26). Id claimed once with
`scripts/next_changelog_id.py` (`26g` was taken by the motion-transfer
session's FaceID entry meanwhile). No GPU, no ComfyUI call, no model load,
no render.

## Approval

Asked in chat with the file, source, size and destination stated (the
Phase-1 question quoted "~17 GB Wan 2.2 Animate download"); the operator
chose it. The exact bytes were then read from the Hub tree API before
transfer. The optional relight LoRA (`LoRAs/Wan22_relight/WanAnimate_relight_lora_fp16.safetensors`,
1,436,672,440 B, `Kijai/WanVideo_comfy`) was **not** downloaded: the
approval named the Animate model; the LoRA is listed in `26d` as optional
and stays a separate ask.

## What was fetched (`local_agent/runtime/roadmap_20260926/download_wan22_animate_26g.py`; log `download_wan22_animate_26g.log`; state `download_wan22_animate_26g.json`)

| item | value |
|---|---|
| source | `https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors` |
| destination | `A:\Users\rhine\ComfyUI-Shared\models\diffusion_models\Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors` |
| bytes (Hub tree API = on disk) | 18,401,760,586 |
| sha256 (Hub LFS oid = computed after rename) | `2936b31473a967e7a429a6646bba60e7862d0938e178b58b2a140f391dd5b8e6` |
| transfer | 02:18:00 → 02:30:14, 64 MiB ranged chunks appended to a `.part` sibling, 18–32 MiB/s, 0 chunk errors, 0 retries |
| render-aware pauses | 0 (`paused:` never logged; port 8188 was closed and `vram_owner.json` idle throughout — the motion-transfer session had finished pass24 at 02:10 and was CPU-scoring) |
| rename | only after size match; verify pass read the final file (02:30:14 → 02:32:04) |
| A: free before | 10,495 GiB |

Why this file and not `_v2`: the repo README says the `_v2` scaled files
exist for **native** ComfyUI workflows (fp8 face-encoder layers); for
`ComfyUI-WanVideoWrapper` (installed, commit `ee71d5c4` 2026-09-15, has
`WanVideoAnimateEmbeds`) the initial e4m3fn file is the one to use, as
`docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md` §3c already named.

The downloader is generic in shape (chunked, resumable, checks port 8188 +
`vram_owner.json` before every chunk and sleeps 30 s while a render owns
the GPU, `.part` → rename → sha256) and is kept as the record; it hard-codes
this one file on purpose.

## What this does **not** change

- `gvd_tool_router/catalog_seed.py` row `wan22_animate_14b_unvalidated`
  stays `disabled`; its `disabled_reason` still says the weights are
  missing (~17 GB). That text is now stale on the "missing file" half but
  correct on the rest: no pinned API template, no measured local VRAM
  profile, no validation render, no promotion (doc §7). **Not edited
  here**: the motion-transfer session applies its own anchored edits to
  that file and the doc (26a/26g `_edit_*_text.py`, mtime-checked); left
  to that session or the operator to avoid crossing edits. Recorded as a
  TODO line.
- `docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md` §3c "not on disk"
  table: same, not edited.
- Nothing was loaded into ComfyUI; the router will not select this row
  until it is promoted through `apply_profile.py` with a real measured
  profile, which is Phase 3 work.

## Files

- `TODO.md` (CRLF): the 26d "Run that download only while…" line closed
  with this evidence; one new open line for the stale seed-row text.
- This file; the three `download_wan22_animate_26g.*` artefacts.
