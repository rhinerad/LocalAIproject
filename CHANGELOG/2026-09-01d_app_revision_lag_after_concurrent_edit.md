# 2026-09-01 — APP_REVISION lag after a concurrent agent's profile changes

## Scope

Handoff check only, no image-generator tuning. Per the operator's instruction
to hand off image-generator tuning to the other (ChatGPT/Codex) agent and to
check repo/handoff state before starting new work, I read
`docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-01.md` and the recent `CHANGELOG/`
entries, then verified my own three same-day image fixes (t2i denoise force,
hi-res fix, CLI UTF-8 crash fix) survived that agent's concurrent edits to
`work/image_render.py` and `local_agent/tools.py`.

## What was found

- `work/image_render.py` and `local_agent/tools.py` were modified by the other
  agent at ~2026-09-01 02:21-02:22, after all my edits (last at ~01:03), adding
  a `profile` parameter for three mutually exclusive image model paths
  (`realvisxl` / `alicemix_sd15` / `realpro_flux`).
- All three of my fixes are intact: `apply_hires` now reads
  `hires_fix and mode == "t2i" and profile != "alicemix_sd15"` (my condition
  extended, not removed), `PYTHONUTF8` is still forced in `render_story_image`'s
  subprocess env, and the `mode == "t2i"` denoise-force branch is still present.
- `local_agent/server.py` was **not** touched by that edit, and
  `APP_REVISION` was still `2026-09-01-cli-utf8-r70` — unchanged since before
  the other agent's 02:21 edits.

## Why that is a real (if narrow) gap

The launcher's self-repair mechanism
(`START_LOCAL_AGENT_GUI.ps1`'s `Test-AgentReady`) decides whether to kill and
restart the already-running Python process by comparing `APP_REVISION` against
`$ExpectedAgentRevision`. Python does not hot-reload; if the process was
already running before 02:21 and nothing bumps this string, the live process
keeps the old `tools.py`/`image_render.py` in memory and the new profile
system silently does not take effect until some unrelated restart happens to
occur. This is a gap in the revision-bump discipline this file's own rules
established, not a defect in the other agent's profile work itself.

## Fix

Bumped `APP_REVISION` to `2026-09-01-profile-reload-r71` in `server.py` and
`$ExpectedAgentRevision` to the same value in `START_LOCAL_AGENT_GUI.ps1`,
keeping them in lockstep. No image-generation logic was touched.

## Verification

`python -m pytest local_agent/test_launcher_revision.py` passes, confirming
the two strings match. This only guarantees the *next* launch of
`START_LOCAL_AGENT_GUI.ps1` will detect the stale process and restart it; it
does not itself restart anything (I cannot type into the terminal that runs
it — that requires the operator, or the operator's own restart action).
