# Prompt-pack GUI production (Backrooms EDITED)

## Goal

From the desktop local-agent GUI, ingest the reviewed EDITED prompt pack and
complete **all unique SDXL start/last stills**, then **all Minimax FLF2V clip
videos**, with durable resume on 16GB VRAM.

## Exact source

`A:\Users\rhine\Documents\Codex\2026-09-07\i-w\outputs\backrooms_sitcom_prompt_pack_EDITED.md`

Do not use older/wrong stills from aborted packs.

## Steps (matches the live `/api/send` path)

1. Confirm agent revision is `2026-09-07-prompt-pack-full-production-r98`
   (`GET http://127.0.0.1:8760/api/status`).
2. Open a **new chat**.
3. Paste the full EDITED markdown, **or** send the absolute path above.
4. Send: `complete images and videos`
   - Aliases: `generate all stills then videos`, `full production`,
     `render images and videos`.
5. Approve the GPU gateway sidebar prompt if shown (one approval covers the
   long-running supervisor).
6. Leave it running. Optionally send `continue` later to poll/resume.
7. Outputs:
   - Progress: `local_agent/runtime/managed_tasks/<cid>/production_progress.json`
   - Log: `.../production.log`
   - Stills: `.../revisions/<sha>/outputs/media/stills/`
   - Videos: `.../revisions/<sha>/outputs/media/videos/`

## What not to do

- Do not stop at export-only (`Render allowed: False`).
- Do not use short `render` if you want the full film — that only does the C001
  review anchor.
- Do not divert to Equal Shares / H3 tools.
