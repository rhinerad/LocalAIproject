# 2026-09-01 — hi-res fix pass to address crossed eyes / weak prompt detail

## What the operator reported

After the denoise-haze fix, a render came back clean but still noticeably
off: "the characters eyes are crossed" and the wardrobe/pose details from
the prompt were largely ignored. Operator asked for the closest achievable
match to "very realistic and close to the prompt as much as possible."

## Diagnosis

Two full-body adult figures rendered side by side into a single 1024x1024
frame leaves each face occupying a small fraction of total pixels — well
inside the regime where SDXL checkpoints (including RealVisXL) are known to
produce crossed/misaligned eyes and other small-feature breakdown, because
the model has too few pixels per face to resolve eye geometry correctly in
one pass. This is a resolution/pipeline limitation, not a prompt-wording
problem or a broken checkpoint.

Separately, the prompt-adherence gap (missing wardrobe/pose specifics) is
consistent with SDXL's text encoder blending a long single-paragraph prompt
that packs scene description, two characters' full appearance, and pose
notes together — specific details compete with a lot of other tokens for
representation and are often the first thing dropped.

## What changed

**`work/image_render.py`, `build_graph()`:** added an automatic second pass
for `t2i` (the standard "hi-res fix" technique): the first pass's latent is
upscaled (`LatentUpscaleBy`, `bislerp`, `DEFAULT_HIRES_SCALE = 1.5`) and run
through a second, shorter `KSampler` pass (`DEFAULT_HIRES_STEPS = 20`,
`DEFAULT_HIRES_DENOISE = 0.5`, same seed/positive/negative/sampler/
scheduler) before `VAEDecode`. This gives the model far more effective
pixels per face to resolve before the image is finalized — the standard fix
for exactly this class of small-feature artifact. Applied automatically
whenever `mode == "t2i"`; left off for `i2i`, whose denoise semantics are
different and wasn't in scope for this report. Exposed as an overridable
`hires_fix: bool = True` parameter (CLI: `--no-hires-fix` to disable, for a
faster low-detail draft).

`validate_nodes()`'s `REQUIRED_T2I` now also checks `LatentUpscaleBy` is
present in the live ComfyUI's `/object_info` (it is a stock/core node,
expected on any real install) so a plan/execute call fails clearly rather
than partway through if it's somehow missing.

`DEFAULT_NEGATIVE` extended with explicit terms for the reported defect:
`cross-eyed, crossed eyes, walleye, strabismus, misaligned eyes,
asymmetrical pupils, lazy eye` — a second, independent layer alongside the
resolution fix above, since a negative-prompt term and a resolution fix
address the same failure mode through different mechanisms and are not
mutually exclusive.

**`local_agent/tools.py`:** `plan_story_image` and `render_story_image` both
read/forward a `hires_fix` argument (default `True`), and `render_story_image`
forwards `--no-hires-fix` to the CLI subprocess when disabled. Updated the
`plan_story_image` tool description to give the calling model concrete
prompt-writing guidance for multi-subject scenes: front-load each subject's
single most distinguishing detail in that subject's own clause (rather than
burying it mid-paragraph), and prefer a taller resolution (e.g. 896x1152)
over a 1024x1024 square for full-body multi-person compositions, since a
taller frame gives more pixels per face for the same total resolution.
This is prompt-writing guidance for the model, not a hard-coded default —
width/height remain caller-supplied.

**`local_agent/server.py` / `START_LOCAL_AGENT_GUI.ps1`:** bumped
`APP_REVISION` to `2026-09-01-hires-fix-r69`.

## What was verified

- `python3 -m py_compile work/image_render.py local_agent/tools.py
  local_agent/server.py` — clean.
- Standalone script exercising `image_render.parse_args`/`build_graph`
  directly (no mocks): `--no-hires-fix` correctly flips `args.hires_fix` to
  `False`; the default graph contains `LatentUpscaleBy` at node `9` reading
  the first pass's latent, a second `KSampler` at node `10` reading node
  `9`'s output with `denoise < 1.0`, and `VAEDecode` reading node `10`'s
  output (not node `5`'s) — confirming the hi-res pass is actually wired
  into the final image, not just built and left unused; with
  `hires_fix=False`, nodes `9`/`10` are absent entirely and `VAEDecode`
  reads node `5` directly.
- New tests in `test_story_image_plan.py`:
  `test_t2i_applies_hires_fix_by_default`,
  `test_hires_fix_can_be_disabled`, `test_i2i_never_gets_hires_fix`,
  `test_negative_prompt_names_the_reported_crossed_eyes_defect`.
- New tests in `test_render_story_image.py`:
  `test_hires_fix_false_is_forwarded_to_the_cli` and an assertion added to
  the existing successful-launch test that `--no-hires-fix` is absent by
  default.
- Full regression sweep: `test_launcher_revision`, `test_story_image_reveal`
  (12), `test_story_image_plan` (12), `test_render_story_image` (20),
  `test_native_tool_calling` (43), `test_router_switching` (41),
  `test_subtask_dispatch` (8), `test_retrieval_relevance` (4) — 140 tests
  total, 0 failures, 0 errors.

## What is still unverified

Not yet run against a real ComfyUI backend. The hi-res pass roughly doubles
sampling time per render (first pass at `DEFAULT_STEPS=35` plus a second
pass at `DEFAULT_HIRES_STEPS=20` on an upscaled latent) — still expected to
land well under the operator's 4-minute bar given backend cold-start
dominates total wall-clock time, but this is an expectation, not a
measurement. The operator needs to restart the local agent (revision bump
above) and request another render to confirm both the crossed-eyes fix and
the timing hold up in practice, and to judge whether the prompt-adherence
guidance actually changes how future prompts get written.
