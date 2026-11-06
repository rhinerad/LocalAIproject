# 2026-09-24aa — still-QA continuity anchor for chat stills: chat-scoped fallback, provenance, first live anchored comparison

## Why

Operator chat `149209bf6e4b42ce`: "Scene Start Image 2" showed a visibly different
actor from "Scene Start Image 1" for the same character (Leo), and still QA passed
it. Both QA records (`outputs/stories/Scene-Start-Image-{1,2}/still_qa/`) say
`"anchor": null`, so the room/clothing/face continuity checks never ran.
`work/runtime/story_qa_anchors.json` did not exist.

Checked offline, read-only, with the real checker: Image 2 against Image 1 as
anchor → **fail** `face_identity_sface=0.124<0.35` (plus `room_drift 0.149`,
`clothing_drift 0.195`; the scene legitimately moved from the apartment to a
Backrooms corridor). The checker would have caught the actor swap; it was never
given the anchor.

## What was actually missing (differs from the task brief)

The story-keyed registry the brief asks for **already existed** since
`2026-09-24a`: `approve_story_stills` → `_record_story_qa_anchors` writes
`work/runtime/story_qa_anchors.json`, `_story_still_qa` reads it. It never fired
for two reasons, both confirmed in the live state:

1. **No operator approval ever reached `approve_story_stills`.** Every review
   state in `work/runtime/story_stills_review/` is `pending_review`,
   `approved_at: null` (the chat `149209bf…` state holds only Image 2; Image 1's
   pending state was overwritten when Image 2 was presented). Only
   `approve_story_stills` writes anchors, by design (last *human-approved*, never
   last generated), so the file was never created.
2. **The chat labelled one character's stills with one story slug per image**
   (`Scene Start Image 1`, `Scene Start Image 2`). A registry keyed by
   `_safe_segment(story)` can never link those, even after an approval.

So this entry does not rebuild the registry; it closes the two gaps above and
proves the whole loop live.

## Changes — `local_agent/tools.py` (backup `tools.py.bak_qaanchor_20260924`)

- **Chat-scoped fallback anchor.** `_record_story_qa_anchors` also records the
  last still approved in the chat under a reserved `"_conversations"` section
  (`{chat id: {path, story, approved_at}}`; story slugs cannot start with `_`, so
  no collision). New `_story_qa_anchor_lookup(story, conversation_id)` resolves
  story slug first, then the chat's last approval; `_story_qa_anchor(story,
  conversation_id="")` keeps its old signature. Missing / corrupt / wrong-shaped
  registry, or a recorded file that is gone → no anchor, never an exception.
- **Conversation id threaded to the QA call:** `render_story_image_batch` →
  `await_story_image_job` → `story_image_job_status` → `_story_still_qa_cached`
  → `_story_still_qa` (all optional, default `""`). `story_image_job_status` and
  `await_story_image_job` added to `_CONVERSATION_BOUND_TOOLS` so the dispatcher
  injects `__conversation_id` for direct chat polls too.
- **Provenance in every QA record:** `anchor_source` (`story` | `conversation`
  | null), `anchor_story`, `anchor_approved_at`, `anchor_note` (plain-language:
  first still / same-story anchor / chat fallback). `_STORY_STILL_QA_SCOPE`
  mentions the chat fallback and that a deliberate location change lowers room
  continuity.
- **Tool schema:** the `story` parameter of `render_story_image` and
  `render_story_image_batch` now says to reuse one slug for every still of a
  story/character, never one per image, and why.
- Not touched: the QA verdict logic, caching, advisory (non-blocking) behaviour,
  face_detail / model_profile validation, `creative_still_qa.py`.

## Tests — `local_agent/test_story_stills_batch_review.py` (backup `.bak_qaanchor_20260924`)

Six new `StoryStillQATests` (existing 2026-09-24a anchor test unchanged):

- batch for a story with a prior approval → `creative_approve(..., anchor=<approved png>)`,
  record `anchor_source="story"`, anchor reaches the persisted review state;
- first still (no registry) → `anchor=None`, `verdict=pass`, no `error`, registry
  still not created by generation alone;
- approval writes the registry (story entry + `_conversations` entry), a later
  approval replaces it, approving a still whose file is gone records nothing and
  does not fail approval;
- per-image labels (`Scene Start Image 1` approved, `Scene Start Image 2`
  rendered, same chat) → anchor = Image 1, `anchor_source="conversation"`; a
  different chat gets no anchor;
- story anchor wins over chat fallback;
- corrupt JSON / list / wrong-shaped entries / dangling paths → `anchor=None`,
  QA still runs and passes.

`python -m unittest test_story_stills_batch_review` → 28 OK;
`test_native_tool_calling test_render_media_announce` → 142 OK.

## Live verification (real GPU, 2026-09-24 21:31–21:43 local)

Driver: `tools.present_story_stills_for_review` → `tools.approve_story_stills`
(chat `stillqa-anchor-live-20260925`) on the real 2026-09-24a still
`46665ea1…_00001_.png` for story `stillqa-live-verify-20260924`, then
`tools.render_story_image_batch` for the **same story**, same scene-1 prompt,
seed 424243, `realpro_flux`. Waited for the operator's own Scene-Start-Image-2
re-render (pid 50740) to release port 8188 first; gate mode `allow`; backend
released after. 720 s end to end. Result:
`live_jobs/stillqa_anchor_live_verify_20260925.json` (+ `.log`).

- Approval wrote `work/runtime/story_qa_anchors.json` (story entry and
  `_conversations` entry, `approved_at 2026-09-25T01:31:06Z`).
- New still `e721076e…_00001_.png`; QA record
  `outputs/stories/stillqa-live-verify-20260924/still_qa/image_97a51365-….json`:
  `anchor` = the approved still, `anchor_source: "story"`, **verdict fail**,
  `reject_reasons: ["room_drift corr=0.439<0.55", "face_identity_sface=0.206<0.35"]`,
  metrics `anchor_face_count 1`, `candidate_face_count 1`, `room_hist_corr 0.439`,
  `clothing_hist_corr 0.544`, `face_hist_corr 0.598`, `face_sface_cosine 0.206`,
  `face_center_shift 0.048`.
- Both images inspected: the verdict is right. Different actor (face, hair,
  build), different room (hardwood floor, black leather couch, red wall vs. the
  carpeted beige room), same wardrobe (olive overshirt, gray tee, dark jeans —
  the clothing correlation is the one continuity metric that passed).

This is the first chat-path still ever QA'd against a real anchor.

## Not done / follow-ups

- **The running GUI `server.py` (pid 11684, started 20:19 local) has the
  2026-09-24a code loaded, not this.** Chat turns will keep producing
  `anchor: null` until it is restarted (not done from this session).
- Approval still depends on the model calling `approve_story_stills` after the
  operator's "looks good"; the live chat never did. That gate is unchanged here.
- `present_story_stills_for_review` overwrites the chat's single review state,
  so presenting still 2 discards still 1's pending record; an operator who
  approves after seeing both only records still 2.
- The chat fallback is deliberately advisory: two unrelated stories in one chat
  will produce a continuity fail with `anchor_source: "conversation"` and an
  explanatory `anchor_note`; the operator can disregard it. A same-scene room
  check across a deliberate location change likewise reads as `room_drift`.
- The test chat's review state
  `work/runtime/story_stills_review/stillqa-anchor-live-20260925.json` is left
  `pending_review` as evidence; the registry entry for
  `stillqa-live-verify-20260924` is the real approved still and can stay.
