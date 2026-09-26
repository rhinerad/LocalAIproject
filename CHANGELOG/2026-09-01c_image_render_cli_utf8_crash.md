# 2026-09-01 — fixed a UnicodeEncodeError crash in image_render.py's own status print

## What happened

The hi-res fix (`2026-09-01b`) was confirmed on a real render — the image
was genuinely produced and looked significantly better, with the reported
crossed-eyes defect gone. But the job log showed `image_render.py` itself
crashed with `UnicodeEncodeError: 'charmap' codec can't encode character
'则' ... character maps to <undefined>` right at the very end.

## Diagnosis

The saved manifest's `prompt` field contained a stray non-Latin character —
`则` (a CJK character) — embedded mid-word inside "hourglass" ("hour" +
`则`). This is very likely a token-corruption artifact from the calling
14B local chat model when it constructed the `render_story_image` tool-call
arguments, not something introduced by this pipeline. Regardless of origin,
`image_render.py`'s own final status print
(`print(json.dumps(record, ..., ensure_ascii=False))`) crashed because
Python's stdout on Windows defaults to the console codepage (cp1252) even
when redirected to a log file, unless UTF-8 mode is explicitly forced —
and cp1252 cannot represent `则`.

**This crash was cosmetic, not a render failure.** The manifest write two
lines earlier (`.write_text(json.dumps(record, indent=2), encoding="utf-8")`)
already uses an explicit UTF-8 encoder and completed successfully before the
crash, and the `finally` block (backend stop + owner-lock release) always
runs regardless of the exception. The image was real and the job's state
was left clean. The only casualty was the informational stdout print, which
nothing currently reads anyway (`render_story_image`'s log file is not
parsed — `story_image_job_status` reads the manifest file directly). Still
a real bug worth fixing: it leaves a traceback and nonzero exit code in
every job's log whenever a prompt contains anything outside cp1252 — plain
accented characters, emoji, or other non-Latin text a legitimate future
prompt might use, not just glitch-token corruption.

## What changed

**`local_agent/tools.py`, `render_story_image()`:** the `subprocess.Popen`
call that launches `image_render.py --execute` now passes `env` with
`PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8` forced, exactly mirroring what
`image_render.py`'s own `_start_owned_backend()` already does for the
ComfyUI backend subprocess it launches internally (that fix — for the same
class of Windows console encoding problem — predates this session; see the
comment already in that function). This was the one Popen call in the image
pipeline that hadn't received the same treatment.

## What was verified

- `python3 -m py_compile tools.py` — clean.
- New assertion added to
  `test_successful_launch_starts_a_background_process_and_never_blocks`
  confirming the launched subprocess's `env` has `PYTHONUTF8=1` and
  `PYTHONIOENCODING=utf-8`.
- Full regression sweep: `test_render_story_image` (19),
  `test_story_image_plan` (12), `test_native_tool_calling` (43),
  `test_router_switching` (41) — 115 tests, 0 failures, 0 errors.
- `APP_REVISION` bumped to `2026-09-01-cli-utf8-r70` (kept in lockstep with
  the launcher; `test_launcher_revision` passes).

## What is still unverified

Not yet reproduced with an actual non-Latin character sent through the live
agent after this fix — the next real render (with any prompt) will show
whether the crash is gone from the log, but there's no specific reason to
force another glitch-token prompt just to test it; the fix is a direct,
well-understood match for the exact traceback observed.
