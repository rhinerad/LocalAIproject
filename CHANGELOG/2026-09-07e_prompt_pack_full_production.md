# 2026-09-07e — Prompt-pack full production (stills then videos)

## Problem

r97 correctly parsed the reviewed EDITED Backrooms pack and exported 102 complete
clip records, but a GUI paste alone stayed in dry-run (`allow_render=False`).
A short `render` only launched the C001 start review anchor. The operator need —
complete images then Minimax FLF2V videos for the whole pack — was not reachable
from a normal desktop send without debugger-only hacks.

## Cause

- `wants_explicit_render` intentionally returns false for large pack pastes.
- ActionPlan `prompt_pack_ingest_export` never unlocked render or started media.
- No agent tool drove the proven FLF2V runner after stills.

## Changes (r98)

- `prompt_pack_production.py`: detect `complete images and videos` (and aliases),
  build unique still/video jobs from saved clip JSON, durable
  `production_progress.json`, spawn resume-safe supervisor.
- `work/run_prompt_pack_production.py`: SDXL/realvisxl stills via `image_render.py`
  (LoRA when clip requires it), VRAM flush, then Minimax FLF2V via
  `render_single_pass.build_fl2va_workflow`. Resume skips completed artifacts.
- `action_resolver.py`: pack paste + production ask, or short production ask on an
  already-exported chat, routes to `run_prompt_pack_production`. Path-to-EDITED.md
  is accepted. Short `render` remains the single review-anchor path.
- `tools.py` / `agent.py`: new tool + operator-facing summary; status includes
  production phase counts.
- Revision `2026-09-07-prompt-pack-full-production-r98`.

## Operator GUI path (proven)

1. New chat in the desktop GUI (or fresh conversation via `/api/new`).
2. Paste the EDITED pack **or** send its path, then send:
   `complete images and videos`
   (or paste a one-line wrapper above the pack: `complete images and videos`).
3. Agent exports if needed, unlocks `allow_render`, starts background supervisor.
4. Say `continue` to poll/resume. Watch
   `local_agent/runtime/managed_tasks/<cid>/production_progress.json` and
   `.../outputs/media/{stills,videos}/`.

Exact pack:
`A:\Users\rhine\Documents\Codex\2026-09-07\i-w\outputs\backrooms_sitcom_prompt_pack_EDITED.md`

## Notes

- Model profile follows the reviewed pack adapter: **realvisxl (SDXL)**, not the
  older Flux VHS ad-hoc batch. Backrooms SDXL LoRA applies post-fall only.
- 102 clips is long; do not declare done until production.status=complete.
- Equal Shares diversion remains forbidden.
