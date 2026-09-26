# 2026-08-31 — diagnosed and fixed a real reported hallucination: "image generated" after a plan-only call

## What happened (operator-reported)

The operator asked for a photoreal still image. The model called
`plan_story_image`, whose result explicitly said `"planned": true,
"model_load": false, "gpu_action": "none"` and that this is "a read-only
graph plan" requiring "the guarded isolated renderer" for an actual image.
The model's next reply ignored all of that and told the operator: "The
image ... has been generated and is stored locally. ... fully rendered as
described ... ready for use." No image existed anywhere. Three follow-up
turns of "where did it output to?" / "the image is not in the output
folder" / "check and diagnose" each just re-ran `list_dir` on the same
`outputs/` path and repeated a generic "may not have been saved" hedge,
never reading `plan_story_image`'s own JSON, never checking
`outputs/stories/`, and never telling the operator the true reason: no
tool in this agent can actually execute that plan.

## Root cause (verified by reading the code, not assumed)

1. **`_UNVERIFIED_EXECUTION_RE` (agent.py) only matches first-person active
   claims** ("I downloaded...", "I created..."). The actual hallucinated
   text used passive voice about the object — "The image ... has been
   generated" / "fully rendered" — which structurally cannot match
   `\b(?:i|we)\s+...`. This is likely the single most common phrasing this
   guard needs to catch for image/video work and it had no coverage for it
   at all.
2. **`plan_story_image` genuinely never executes anything.** Grepped the
   entire non-vendor codebase for a "guarded isolated renderer" or any
   image-execution tool for general (non-Equal-Shares) story images: none
   exists. The tool's own `next_step` text promised a renderer that isn't
   built yet, which reads to a small local model like permission to assume
   one exists and describe its output as done.

## What changed

**1. `agent.py`:** added `_IMAGE_COMPLETION_CLAIM_RE`, a narrow
passive-voice-aware pattern ("has been generated", "is ready", "fully
rendered", etc.), and turn-scoped `plan_only_pending` state that's set
whenever a hop's tool results include `plan_story_image` returning
`"planned": true` + `"gpu_action": "none"` (reset every hop so it only
reflects the latest tool result, mirroring the existing repeated-failure
guard's per-hop-fresh design). If the model's next hop is plain prose (no
further tool call) and matches the completion-claim pattern, the reply is
deterministically replaced with an accurate one: no image was generated,
naming the actual story slug and the actual (never-created) output path,
and stating plainly that no execution tool exists yet. This mirrors the
existing `_BATCH_FOLDER_REFUSAL` deterministic-override pattern already
used elsewhere in this same function for a different known bad-completion
case.

Also broadened `_UNVERIFIED_EXECUTION_RE` itself to include
`generat(?:e|ed)` and `render(?:ed)?` in its verb list, so a first-person
version of the same claim ("I generated the image") is now caught too —
narrower fix, same root cause.

**2. `tools.py`:** rewrote `plan_story_image`'s `next_step` field and its
`TOOLS` registration description to state plainly, in the text the model
actually reads, that no model was loaded, no GPU ran, no file was written,
the named output folder doesn't exist, and there is currently no tool that
executes the plan — instructing the model never to say generated/
rendered/saved/ready after calling it. This is a documentation-accuracy
fix (the old text implied a renderer existed to hand off to) layered under
the deterministic code-level fix above, not a substitute for it.

## Why the fix is layered as a deterministic override, not just tool-text

The old `next_step` text already told the model the truth in different
words, and it didn't help — a 14B locally-run model does not reliably
carry a JSON tool result's semantics into free text three turns later.
Prompt/tool-text wording changes reduce the odds of this happening again
but cannot guarantee it; the regex + state-tracking correction is the load-
bearing fix and runs regardless of how the model chooses to phrase it.

## What was verified

- `python3 -m py_compile agent.py tools.py` — clean.
- Direct reproduction of the exact reported conversation (`plan_story_image`
  returns the real plan-only JSON shape, model then emits the exact
  reported hallucinated sentence) — confirmed the fix catches it and
  produces a reply naming the real story slug and real (nonexistent)
  output path, with no more "ready for use" language.
- Negative control: an unrelated, accurate completion claim following a
  real, successful `write_file` call is untouched — the fix is scoped to
  the `plan_only_pending` state, not a blanket ban on passive-voice
  "has been created" phrasing.
- Negative control: a `plan_story_image` call that returns a genuine
  `ERROR:` result does not set `plan_only_pending` and the turn proceeds
  normally.
- Added 2 permanent tests to `test_native_tool_calling.py`:
  `test_plan_story_image_hallucinated_completion_is_corrected` (the exact
  reproduction above) and
  `test_real_completion_claim_after_a_genuine_write_is_not_touched` (the
  negative control).
- Full regression sweep (with the documented `set_chat_busy` sandbox
  workaround): `test_native_tool_calling` 40/40, `test_router_switching`
  41/41, `test_subtask_dispatch` 8/8, `test_retrieval_relevance` 4/4,
  `test_deep_research` 6/6, `test_run_code` 14/14, `test_agentic_state`
  11/11, `test_story_image_plan` 5/5 (pre-existing suite, confirms the
  `next_step`/description wording change didn't break its assertions) —
  129 tests total, 0 failures, 0 errors.

## What was NOT fixed, and why — the deeper gap

There is currently **no tool anywhere in this agent that executes a
general-story image plan into an actual file.** `plan_story_image` is, and
has only ever been, a read-only graph-planning tool. Building the "guarded
isolated renderer" it references (something analogous to the Equal Shares
batch renderer's GPU-ownership/port-8188/thermal preflight discipline, but
for arbitrary general-story stills) is a real feature gap, not a bug in
today's fix, and is out of scope for a same-day correction. Recorded in
`TODO.md` so "make me an image" requests are understood to be plan-only
until that renderer exists, rather than silently rediscovered as a
surprise the next time this happens.

## What is still unverified

Not yet run on the real Windows workstation.
