# 2026-09-01 — fixed the real cause of hazy/washed-out generated images

## What happened

Two real end-to-end renders completed successfully (first genuine images out
of `render_story_image`), but both came back hazy, washed-out, and missing
significant prompt detail — the operator called it "the worst quality."

## Root cause

The chat model called `render_story_image` with `"mode":"t2i","denoise":0.55`
explicitly set on both requests. `t2i` starts sampling from a pure-noise
`EmptyLatentImage` — `denoise` tells `KSampler` how much of that noise to
actually remove. At 0.55, roughly half the noise was deliberately left in
the final image. That is exactly the haze/fog visible in both renders; it
was never a model-quality problem.

`0.55` is a real, correct value — but only for `i2i` (image-to-image), where
it controls how much of a *reference* image's detail survives versus being
redrawn. `plan_story_image`/`render_story_image`'s own default logic already
knew this (`0.55 if mode == "i2i" else 1.0`), but that default is only a
fallback for when the caller omits the field — nothing stopped a caller
(including the model's own tool-call arguments, as happened here) from
explicitly overriding it with a value that makes no sense for `t2i`.

## What changed

**`work/image_render.py`, `build_graph()`:** after validating the passed
`denoise`, the mode is checked and `denoise` is forcibly set to `1.0`
whenever `mode == "t2i"`, unconditionally overriding whatever was passed.
This is defense in depth at the one shared function both `plan_story_image`
and `render_story_image` call, rather than a check added at each call site —
closes the bug regardless of what any future caller (model tool-call
arguments, a new tool, a CLI invocation) tries to pass.

Also added, in the same file:
- `DEFAULT_NEGATIVE` — a broadened default negative prompt (the old one was
  four terms: "blurry, low quality, distorted anatomy, text, watermark").
  The new one adds explicit haze/fog/washed-out/overexposed terms (a second,
  independent layer against the same defect class) plus standard
  photorealistic-human failure modes: hand/finger anatomy, plastic/airbrushed
  skin, oversaturation, and non-photographic styles (cartoon/anime/cgi/
  illustration/painting) that have no place in a "photoreal" request.
- `DEFAULT_STEPS = 35` (up from 28) — modest bump for more detail; the
  dominant cost in a render is ComfyUI backend cold-start (~3 min budgeted),
  not sampling, so seven extra steps at 1024x1024 is a small fraction of
  total wall-clock time.

**`local_agent/tools.py`:** `plan_story_image` and `render_story_image` now
read their negative-prompt and steps defaults from
`image_render.DEFAULT_NEGATIVE` / `image_render.DEFAULT_STEPS` instead of
each hardcoding its own copy of the old, shorter literals (there were two
independent copies of the same negative-prompt string before this).

**`local_agent/server.py` / `START_LOCAL_AGENT_GUI.ps1`:** bumped
`APP_REVISION` to `2026-09-01-t2i-denoise-fix-r68` (kept in lockstep, per
`test_launcher_revision.py`) so the next launcher run picks this up.

## What was verified

- `python3 -m py_compile work/image_render.py local_agent/tools.py
  local_agent/server.py` — clean.
- New tests in `test_story_image_plan.py`:
  `test_t2i_ignores_a_caller_supplied_low_denoise` (the exact reproduction —
  passes `denoise: 0.55` with `mode: t2i`, asserts the built graph's
  `KSampler.denoise` is `1.0` regardless), `test_i2i_denoise_is_still_
  respected` (negative control — i2i denoise passes through unchanged), and
  `test_default_negative_and_steps_come_from_image_render` (confirms the
  single-source-of-truth wiring, not just that *some* default exists).
- Updated `test_render_story_image.py`'s `_FakeImageRender` test double to
  expose `DEFAULT_NEGATIVE`/`DEFAULT_STEPS`, since `render_story_image` now
  reads them at call time.
- Full regression sweep: `test_launcher_revision`, `test_story_image_reveal`
  (12), `test_story_image_plan` (8), `test_render_story_image` (18),
  `test_native_tool_calling` (43), `test_router_switching` (41),
  `test_subtask_dispatch` (8), `test_retrieval_relevance` (4) — 135 tests
  total, 0 failures, 0 errors.
- Confirmed by direct file inspection (not assumed) that the two real
  renders which prompted this fix both had `"denoise": 0.55` baked into
  their saved manifests under `mode: "t2i"` — this is not a hypothesis, it's
  what actually ran.

## What is still unverified

Not yet confirmed against a real render with the fix applied — the operator
needs to restart the local agent (revision bump above) and request another
image to confirm the haze is actually gone and not just theoretically fixed.
