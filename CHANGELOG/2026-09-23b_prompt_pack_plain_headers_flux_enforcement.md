# 2026-09-23b — prompt-pack plain headers, Flux override actually enforced

Trigger: chat `a051127dca4b4a25`, 18:07. An 837,724-char paste (EDITOR
OVERRIDES preamble + 102 clips) failed `ingest_prompt_pack` with "No clip
prompts were parsed". The paste was never saved (only empty `clips/` and
`outputs/`), and `managed_prompt_pack.py` was edited at 19:08, after the
failure. So the exact failing input and code cannot be replayed. The error
proves zero `##`–`####` `C\d+` headers matched and the plain-header parser
did not run. Plain `C001 — START FRAME IMAGE` headers with no FULLY MERGED
title fit that. It is the most likely shape, not a proven one.

## Code

- `local_agent/managed_prompt_pack.py`
  - Plain-header parser and `is_prompt_pack` no longer require the
    `FULLY MERGED` / `CAMERA-LOGIC CORRECTED` title. Threshold is START FRAME
    headers: 12 without the title, 4 with it. Before, the whole-regex count
    included LAST/VIDEO headers, so "12 matches" meant 4 clips.
  - `backrooms_compile` is loaded by file path from the project root. The old
    `from backrooms_compile import …` raised `ModuleNotFoundError` on every
    Python version, because `local_agent/` is not the root. A bare `except`
    swallowed it, so no ingested clip ever got `model_profile`, and
    `initial_frame_job` fell back to realvisxl even for "Flux, not SDXL"
    packs. The loader restores `sys.path`, because the module prepends the
    project root on import.
  - Flux is forced only when the source asks for it (`## EDITOR OVERRIDES`,
    `### 0. Flux`, "still-image generator is Flux"). `JobSettings` defaults to
    Flux, but packs without overrides keep their production behavior
    (unset → realvisxl). If the compile module cannot load, the marker
    fallback still sets flux, and every clip carries `compile_fallback`.
  - A failed ingest writes `failed_ingest_<sha>.diagnostics.json`: regex
    counts, branch, sample clip-id lines, head/tail 200 chars, compile-load
    status. The summary is appended to the error text.
  - `progress.json` records `model_profiles` counts.
- `backrooms_compile.py`: regex pulled out of the f-string. It was a
  SyntaxError on 3.10. On 3.12 the `\\s` inside it was a literal backslash, so
  the `## APPENDIX` alternative never matched.
- `local_agent/tools.py`: `ingest_prompt_pack` and a completed
  `export_prompt_pack_outputs` return `operator_message`, for example "N clips
  exported and ready … Say 'render it' to start stills+video production."
  The model is told to relay it and not end the turn silently. The render
  gate and the GPU gate are unchanged.

## Evidence

- `test_managed_prompt_pack`, `test_prompt_pack_production`,
  `test_prompt_pack_sections`: 34/34 OK on 3.12.10 and on uv CPython 3.10.20.
  12 new tests cover the untitled plain-header shape, `model_profile == "flux"`
  on all clips, no flux without overrides, the fallback label, `sys.path`
  hygiene, the diagnostics file, and operator_message.
- The new parse and Flux tests fail against the pre-change module
  (`managed_prompt_pack.py.bak_pack_parse_20260923T194818`).
- Sanity check on 3.12: bare MERGED_FINAL → 102 clips, `{unset(realvisxl): 102}`.
  With the EDITOR OVERRIDES preamble → `{flux: 102}`. Before: `None`.
- `verify_backrooms_compile_offline.py`: `failures: []`.

## Not verified

- The actual 837,724-char paste was not re-run, because it does not exist on
  disk. Re-paste it; on failure the new diagnostics file shows the shape.
- No render was run. Per CLAUDE.md, nothing about the render path is verified.

Backups: `*.bak_pack_parse_20260923T194818` next to each edited file.
