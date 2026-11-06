# 2026-09-07d — Reviewed prompt-pack parsing and real execution

Operator request: preserve the other editor's Backrooms revisions and fix the local
agent so the supplied task can execute, not merely produce instructions.

## Evidence and cause

Chat `f8f7f70e364d40c0` reported 102 exported clips. Its original saved C001 JSON
actually had a filename as start_frame and an empty video_prompt. The parser
replaced repeated clip IDs wholesale, although the new layout separated start,
last and video sections. Empty strings were not rejected. The follow-up `redner`
fell through to a specialist current-chat render tool and was refused.

## Changes

- managed_prompt_pack.py joins frame-first sections by field, checks real content,
  carries editor controls, fingerprints revisions, preserves prior source/outputs,
  resets export progress when content changes without changing clip IDs.
- backrooms_prompt_adapter.py applies the expressly supplied reviewed Backrooms
  controls to effective inputs; raw shot prompts are retained as source_* fields.
  C001–C014 stay apartment/LoRA-free, stills omit the old movement prefix, and
  approved last-to-next-start references are explicit. The source document is unchanged.
- action_resolver.py resolves render/redner for a managed pack to its saved first
  SDXL review anchor. A recorded launch is polled, not launched twice. Continue
  consults that receipt. agent.py stops a deterministic plan at a tool error so
  failed replacement ingest cannot export stale data.
- image_render.py and tools.py expose an optional installed SDXL LoRA, checked
  against local model paths/live node choices. Both model and CLIP consumers use
  it; VAE stays original. Flux/SD1.5 cannot silently use this SDXL option.
- Server and launcher revision r97; live server restarted with reviewed-pack fixes.

## Verification so far

4 section/routing regressions, 9 existing managed-pack tests, 12 image-graph tests,
19 image tool tests passed. Live GUI /api/send accepted the exact revised document
and produced 102 complete records (204 still prompts, 102 video prompts). Verified
editor controls, opening separation, reference chaining, and unchanged source SHA256.

Live evidence:
`work/runtime/reviewed_pack_acceptance_1788824125045594800.json` (export)
`work/runtime/reviewed_pack_acceptance_1788824138839364800.json` (real anchor launch).
The local agent launched C001 start with SDXL, 1024x768, seed 1 using its own guarded
render tool. Launch is not visual acceptance or finished production.

## Current scope and remaining gate

Exact input: `A:\Users\rhine\Documents\Codex\2026-09-07\i-w\outputs\backrooms_sitcom_prompt_pack_EDITED.md`.
Source SHA256: `c0dd4f6e0845482bfd400b58e0eab46b2a39055969cd74a95bc5c2f67b767cd6`.
Current outputs are the revisions/<source_sha256>/outputs directory under
`local_agent/runtime/managed_tasks/f8f7f70e364d40c0/`.

The operator's source requires still approval before video. No video or final film
completion is claimed. The first anchor is under live verification; subsequent
continuity/reference conditioning and the full production sequence remain work.
Do not reuse the old Flux ad-hoc batch script: it can interrupt foreign backends
and uses the wrong image profile for this reviewed SDXL task.
