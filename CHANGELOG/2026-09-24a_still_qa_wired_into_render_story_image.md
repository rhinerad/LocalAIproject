# 2026-09-24a — real still-QA wired into `render_story_image(_batch)`; `flux_still_batch.py` QA import regression fixed

## Why

Operator chat `1d4a42d3b5834081`: a `render_story_image_batch` still (a plain
empty living room) was followed, in later turns that made **no tool call**,
by a fabricated "the QA process confirmed… now marked as SELECTED" narrative,
including for a "Fall & Arrival" second image that was never rendered (that
turn's batch call was refused by the stale-specialist-project guard). The
chat still path had zero QA; the model had no data and invented a verdict.
The repo *does* have a working still QA (`creative_still_qa.py`), it was just
not reachable from this tool path.

## Part 0 — `flux_still_batch.py` QA call was broken (two latent bugs)

`import creative_still_qa as csqa` (still in `flux_still_batch.py.bak_people`)
was later rewritten to
`from creative_still_qa import empty_pov_prompt_boost, infer_visibility_expectation as csqa`.

1. `auto_approve(creative=True, prompt=…)` called `csqa.creative_approve(...)`
   on the *function* → `AttributeError: 'function' object has no attribute
   'creative_approve'` on every call (confirmed by loading the pre-fix file).
2. The same rewrite left the name `infer_visibility_expectation` **unbound**,
   so the empty-POV prompt/negative hardening (`_exp = infer_visibility_expectation(...)`
   near line 390) raised `NameError`, was swallowed by its `try/except`, and
   printed `WARN empty_pov_prompt_boost failed` — that hardening has silently
   never run since.

Fix: import line → `from creative_still_qa import empty_pov_prompt_boost, infer_visibility_expectation`;
call → `creative_still_qa.creative_approve(...)`. Exactly two lines differ from
backup `flux_still_batch.py.bak_csqafix_20260924` (CRLF preserved).

Verified on real stills (`ComfyUI-Shared/input/astra_backrooms_stills`) with
their compiled prompts, anchors and clip dicts: `auto_approve` now returns real
`(ok, reasons, report)` tuples — C001_last reject (room 0.251 / clothing 0.392 /
SFace 0.291; the known-bad frame), C002_last reject (SFace 0.177), C005_start
pass, C017_last reject (`unexpected_person_in_empty_pov` top_conf 0.863).
Pre-fix module: `AttributeError`, and `hasattr(module, "infer_visibility_expectation") == False`.

## Part 1 — `creative_still_qa` in the chat still path

`render_story_image` only *spawns* `work/image_render.py` and returns before a
PNG exists, so QA cannot run inside it. The output file first becomes known in
`story_image_job_status` (state=complete), which `await_story_image_job` and
`render_story_image_batch` both go through — so QA hooks there and covers both
the single-render and the batch path.

**`local_agent/tools.py`** (backup `tools.py.bak_stillqa_20260924`):

- `story_image_job_status` → on `state == "complete"` attaches `qa` =
  `_story_still_qa_cached(manifest)`: runs
  `creative_still_qa.creative_approve(png, prompt=<manifest prompt>, anchor=<see below>, clip=None, kind="last")`.
  Record: `checker, advisory, scope, anchor, verdict (pass|fail|error|not_run), ok, reject_reasons, report`.
  Cached at `outputs/stories/<story>/still_qa/<manifest stem>.json` (outside
  `manifests/`, so image_render's `image_*.json` glob never sees it);
  re-run if the anchor changed; errors/not_run are never cached and never
  reported as a pass.
- `render_story_image_batch`: `completed[i]["qa"]`, the stills passed to
  `present_story_stills_for_review` carry `qa`, new `qa_summary`, and
  `next_step` requires the reply to state each verdict as recorded.
- `present_story_stills_for_review`: returns `qa_summary`; note carries the same rule.
- `approve_story_stills`: records each story's last approved output in
  `work/runtime/story_qa_anchors.json` (keyed by `image_render._safe_segment(story)`),
  returned as `qa_anchors_recorded`.

**Decisions**

- *Anchor*: last **operator-approved** still for the story (never merely the
  last generated one); none yet → `anchor=None` (compare_stills then skips only
  the continuity comparisons).
- *clip/kind*: `clip=None, kind="last"`. `compare_stills` reads `clip` only for
  `camera_mode`/`visibility_mode` overrides and `require_room_continuity`;
  `kind` is accepted but unused by `infer_visibility_expectation`. The chat
  path has no clip register, so there is nothing real to pass.
- *Advisory, not blocking*: a failed still is still presented, labelled with
  its reasons; the human review gate is unchanged. A hard stop for clear cases
  (e.g. unexpected face in an empty-POV prompt) is an operator decision not
  taken here.

**Scope limit — measured, stated in every QA record.** `creative_still_qa`
checks people/face presence against what the prompt implies, plus continuity
against an anchor. It does **not** check that the environment matches the
prompt. Real run on the operator's bad image
(`renders/fd51e60dfcda49ef8ac0fa8c9b1c860f_00001_.png`):

| prompt | verdict |
|---|---|
| its own manifest prompt (first sentence only, no actor) | pass |
| full scene-1 prompt (actor on the mark) | **fail** `expected_actor_visible_but_no_face_detected` |
| C015 "Fall & Arrival" empty-POV Backrooms prompt | pass |
| same + approved scene-1 still as anchor | pass |

So this catches "actor described, empty room rendered" but not "Backrooms
described, apartment rendered". Also found: that image's manifest prompt was
truncated to the scene-1 prompt's first sentence before it reached the tool —
QA can only judge against the prompt it is given.

## `local_agent/agent.py` — stills false-claim guard (backup `agent.py.bak_stillqa_20260924`)

- The guard only fired when a stills tool ran **in the same hop**
  (`stills_pending_operator_review` is reset every hop). The observed
  fabrication happened in follow-up turns with no tool call, so it could not
  have fired. `_stills_claim_correction` now also reads the chat's persisted
  review state (`tools.story_stills_review_status`).
- Split into `_STILLS_FALSE_SELECTION_RE` (SELECTED / approved / meets required
  standards — always false while pending) and `_STILLS_QA_PASS_CLAIM_RE`
  (false unless every pending still's recorded QA verdict is pass; added
  "passed all … checks", the turn-5 phrasing). Original patterns unchanged.
- Correction text no longer claims "there is no automated QA": it cites the
  recorded per-still verdicts and the QA scope, or says no QA verdict was
  recorded (stills presented before this change). `_STILLS_FALSE_APPROVAL_RE`
  removed (no remaining users).

## Tests

- `local_agent/test_story_stills_batch_review.py` — new `StoryStillQATests`
  (7): creative_approve called with manifest prompt/anchor=None/clip=None/kind="last"
  and cached; batch → `completed[i].qa` → review state + `qa_summary`; QA crash
  → `error` never pass, not cached; missing file → `not_run`; approval sets the
  anchor and the next QA uses it; **real unmocked QA** on the operator's actual
  empty-room image vs the scene-1 prompt → fail with
  `expected_actor_visible_but_no_face_detected`, carried into the review state;
  real QA on an actor image with an empty-corridor prompt → fail (`empty_pov`).
- `local_agent/test_native_tool_calling.py` — 3 new: follow-up turn with no
  tool call is corrected with the recorded FAIL verdict; follow-up with no QA
  record says so; a truthful report of a recorded pass is left alone. The
  existing fabricated-SELECTED and true-approval tests still pass unchanged.
- `python -m unittest test_native_tool_calling test_story_stills_batch_review test_render_media_announce`
  → 147 tests OK.

## Live verification

Real GPU run, 2026-09-24 01:09–01:20 (GPU gate mode `allow`, GPU idle 34 °C,
port 8188 free before and released after): `tools.render_story_image_batch`
called directly with the new code (not through the GUI server), one
`realpro_flux` job, story `stillqa-live-verify-20260924`, the full scene-1
prompt, seed 424242. 682 s end to end (Flux text-encoder load on CPU dominated;
"Prompt executed in 00:10:18").

- `completed[0].qa` = verdict **pass**, `ok: true`, `reject_reasons: []`,
  `anchor: null`, mode `actor_visible`, `candidate_face_count: 1`,
  prompt_source `manifest image_918f29f3-….json`. Image inspected: the actor is
  in frame, so the pass is correct.
- `qa_summary.counts = {"pass": 1}`; review state
  `work/runtime/story_stills_review/stillqa-live-verify-20260924.json` is
  `pending_review` with `stills[0].qa.verdict == "pass"`; QA cached at
  `outputs/stories/stillqa-live-verify-20260924/still_qa/`.
- Full result: `live_jobs/stillqa_live_verify_20260924.json`.

**Not verified:** the GUI/chat surface. The running `server.py` predates this
change, so no chat turn has used it yet.

## What refused the "Fall & Arrival" render (turn 3) — still live

Not preflight, port 8188, or GPU-busy. It was the agent's own specialist-scope
guard (`agent.py` `run_one`: `name in _SPECIALIST_PROJECT_TOOLS and not
specialist_scope` → "ERROR: stale specialist-project tool selection blocked").
Replayed read-only against the real chat with current code:
`_requests_specialist_project_context("looks good proceed") == False`,
`_pending_specialist_continuation(history) == False` — so that turn would
still be blocked today. After the block, the scope-retry path re-prompts the
model, whose final turn-3 reply ("I will generate the images using the Flux
model… Let me proceed") promised work that never ran; nothing told the
operator the render was refused. The new stills guard does not touch that
reply (it matches no QA/selection claim); it does now correct turns 5 and 7
(persisted review state: `pending_review`, 1 still, `approved_at: null` —
"looks good proceed" never reached `approve_story_stills` either).

Operator decisions 2026-09-24: QA stays advisory; no `:11436` environment
check for now; prompt truncation is the next item (running as a separate
session). Server restart: the old `server.py` (pid 56652, port 8760) could not
be stopped from this session (permission classifier); the launcher reuses a
running server whose `app_revision` matches, so it must be closed first.

## Not done / follow-ups

- The running agent GUI server (`server.py`, started 00:50) still has the old
  code loaded; it needs a restart before chat turns use this.
- Environment/scene mismatch is not detected by this QA layer (see table).
- Upstream prompt truncation (first sentence only) not investigated here.
