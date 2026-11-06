# 2026-09-07b — Managed prompt-pack tasks (Backrooms / large storyboard packs)

Date: 2026-09-07. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-07b**.

## Failure evidence

Chat `be96946279cf480d` (2026-09-07 ~16:01 ET): operator pasted
`# Backrooms Sitcom Audition Prompt Pack` (~50k chars, 102 clips / 17 minutes).

Live route telemetry:
- `capability=image` via `_IMAGE_GEN_SIGNAL` (`Start Frame` / `Generate…`)
- `profile=gpu_image` → only `IMAGE_DIRECT_TOOLS` (no `write_file`)
- Tools called: `fetch_url` ×3 (wikidot), `search_docs`, then
  `render_story_image_batch` with **2** invented jobs (C001) → failure/pending
- Final assistant text was render-status boilerplate; full pack never persisted
- `agentic_state` goal truncated to 900 chars; plan steps were nonsense splits
  of pack prose; `status=blocked`

## Root cause

1. Large creative/storyboard **prompt packs** were classified as `CAP_IMAGE`
   and forced onto the render-only `gpu_image` tool profile.
2. Durable task state (`agentic_state`) truncated the source and did not save
   a full pack artifact, so compaction/continue could not resume the real pack.
3. No deterministic ingest/export path — the model attempted immediate still
   renders instead of writing machine-checkable clip files.

## Fix (extend existing task harness; no parallel system)

1. **`local_agent/managed_prompt_pack.py`** — detect packs (including flattened
   newline-collapsed pastes), persist `source.md`, parse clips, chunked export
   to `outputs/`, durable `progress.json`, continue/resume, placeholder refusal,
   render gate (assembly notes inside a pack do **not** unlock Comfy).
2. **`router.py`** — `CAP_CREATIVE` + `prompt_pack_intent()` checked before
   `image_generation_intent`; keeps large packs off `gpu_image` / farm.
3. **`agentic_state.py`** — on pack paste, ingest full source, set `kind=prompt_pack`,
   expose exact paths in `prompt_block`; broaden continue (`proceed` / `keep going`).
4. **`action_resolver.py`** — deterministic `prompt_pack_ingest_export` /
   `prompt_pack_continue` ActionPlans (ingest + export; never render).
5. **`tools.py`** — `ingest_prompt_pack`, `export_prompt_pack_outputs`,
   `prompt_pack_status`; `call()` blocks `render_story_image*` while pack is
   dry-run/export unless explicitly unlocked.
6. **`agent.py`** — skip optional planner for packs; summarize ActionPlan results.

## Tests

```
python -m unittest local_agent.test_managed_prompt_pack
```

9/9 OK, covering classifier, 102-clip chunk persist, continue after compaction,
source path recovery, real output files, placeholder refusal, dry-run render
block, reload survival, flattened inline paste.

Dry-run on the real attachment (no Comfy start): 102 clips parsed/exported;
`allow_render=false`; render tools return dry-run ERROR.

## Files

- `local_agent/managed_prompt_pack.py` (new)
- `local_agent/router.py`
- `local_agent/agentic_state.py`
- `local_agent/action_resolver.py`
- `local_agent/tools.py`
- `local_agent/agent.py`
- `local_agent/test_managed_prompt_pack.py` (new)
- `local_agent/server.py` (`APP_REVISION`)
- `local_agent/START_LOCAL_AGENT_GUI.ps1`
- `TODO.md`, `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-06.md`
- this changelog

## Revision

`APP_REVISION=2026-09-07-managed-prompt-pack-r96`

**Did not restart** live agent / did not run `START_LOCAL_AGENT_GUI.ps1`
(operator may still be on r95). Restart required to load r96.

## Safety

No Equal Shares/H3 work. No model-weight/predictor edits. No evidence overwrite.
Verification used temp dirs + dry-run gate only; image render owner remained released.
