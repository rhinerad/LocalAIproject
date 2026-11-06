# Plan: getting the ComfyUI story pipeline the rest of the way to end-to-end, and what to hand Fable

Written after directly verifying the two most recent Scene Start Image renders against real evidence (tool_evidence, media_artifacts, manifests, still_qa reports, and the PNGs themselves) — not from chat narration. This doc has two parts: (1) what the verification found, since it changes the priority list, and (2) a prioritized set of handoff-ready tasks.

## Part 1 — verification result (context for the priorities below)

**Both recent images are real, and the chat did not hallucinate this time.** In `local_agent/chats/149209bf6e4b42ce.json`, the two "successfully generated" claims (messages 1 and 5) were made at 2026-09-25T00:35:04Z and 00:54:51Z — 67 and 100 seconds *after* the real render manifests were written (00:33:57.56Z and 00:53:11.34Z). Both messages carry real `tool_evidence` (a `render_story_image_batch` result with `failure_count: 0`) and real `media_artifacts` with sha256 hashes that match the actual PNGs on disk byte-for-byte. Files, if you want to look yourself:

- `outputs/stories/_comfy_output/stories/Scene-Start-Image-1/renders/c20b90e3071d4af5bb97d9516eda4b4b_00001_.png` — strong match to its prompt.
- `outputs/stories/_comfy_output/stories/Scene-Start-Image-2/renders/843e8e4fd118463683d2f1f2f19352dd_00001_.png` — a real image, but a partial match (see below).

The earlier, genuinely-fabricated "successfully generated" claim that `CHANGELOG/2026-09-24y` documented ("No such image exists") was from an earlier attempt, before these real renders landed. It's real, but it's stale — resolved by the time these two images were made. So: the hallucination pattern is confirmed real and worth continuing to guard against, but the *specific* thing you were just looking at is not a hallucination — it's just that the pipeline has produced two batches of output under similar names across multiple attempts today, which makes it easy to lose track of which claim corresponds to which file.

**Still-QA is wired in and running for real now** (confirms `2026-09-24a` landed). Both images have a `still_qa` report on disk (`outputs/stories/Scene-Start-Image-*/still_qa/image_<id>.json`) and both got a real `"verdict": "pass"`. But Image 2's pass is misleading, and it's misleading for a specific, structural reason:

- Image 2 is missing one of three prompted "fused" objects (no skateboard visible at all — only the guitar and flannel shirt are), the "melted into the wall like wax" effect the prompt calls for reads as ordinary wall-mounted objects, and — most importantly — **the actor in Image 2 does not look like the same person as the actor in Image 1** (heavier build, different hair) despite both supposedly being the same character, "Leo."
- The still_qa report's own `scope` field says exactly why it passed anyway: *"does NOT check that the scene, setting, objects, or lighting match the prompt text"* — so the missing skateboard and weak effect were never going to be caught by this layer, by design.
- More importantly, `"anchor": null` in both reports. The continuity check (which specifically would compare Image 2's actor against a previously-approved reference for the same character) never ran, because no anchor exists — `work/runtime/story_qa_anchors.json` still doesn't exist on disk. This is exactly the gap flagged as unresolved in the still-QA wiring handoff doc from earlier today; it's now confirmed live and responsible for a real miss, not just a theoretical risk.

**The still-QA regression I found and flagged in `CHANGELOG/2026-09-24u` is still unfixed**, confirmed by re-running the tests just now: `python3 -m unittest test_story_stills_batch_review.StoryStillQATests` still fails the same 4 tests it did earlier today. In the failure-path scenarios these tests cover (QA raising an error, or a real prompt-driven rejection), the pipeline reports `"not_run"` instead of `"error"`/`"fail"` — meaning in those specific scenarios the safety net can silently say nothing happened instead of surfacing a real problem. The two production reports above happened to hit the success path cleanly, so this didn't bite this time, but it's a live gap on the failure path.

**Already fixed, no action needed:** the startup-deadline race (`24y`), the `/history` polling timeout (`24w`), and the manifest `requested` vs. actually-used settings mismatch (`24x` — this explains the `RealVisXL`/`realProV3` discrepancy visible in some manifests; already resolved, the manifest now records what the graph actually used).

## Part 2 — prioritized next steps

### 1. Anchor registry for chat-driven story stills (highest leverage, most scoped)

This is the single fix most likely to catch what just slipped through. Without it, still-QA's continuity check can never run for the chat path (`render_story_image`/`render_story_image_batch`), no matter how many more stills get generated — it structurally has nothing to compare against.

What it needs: a small JSON store (e.g. `work/runtime/story_qa_anchors.json`, keyed by `story`) updated inside `approve_story_stills` when the operator actually approves a still, so the *next* still for that story gets checked against the last human-approved one, not just checked in isolation. The original wiring handoff doc (`wire-still-qa-into-render-story-image.md`, already in this repo's root) has the exact call signature and behavior to match (`flux_still_batch.py`'s own `approved` dict is the existing pattern to mirror). This is a well-scoped, mechanical build — good Fable `high` task.

### 2. Fix the still-QA "not_run" masking on the failure path

Confirmed still broken right now (4 failing tests in `local_agent/test_story_stills_batch_review.py::StoryStillQATests`, unchanged since this morning). This is a safety-net bug: when QA genuinely errors or genuinely rejects, the pipeline should say so, not silently report `not_run`. Root cause not yet diagnosed by anyone — worth a real investigation (likely an output-path lookup change from one of today's many other same-day edits to `tools.py`), not a blind patch. Good Fable `high`/`xhigh` diagnostic task — the four failing test names and the original regression note are already in `CHANGELOG/2026-09-24u_face_detail_realpro_flux_fast_fail.md`'s "Found, not fixed" section.

### 3. Decide whether still-QA should ever check prompt-content match, not just face/continuity

This is a product decision, not a bug — worth deciding before more work goes into item 1/2. Right now, by design, nothing checks "does this image contain what the prompt described" (the missing-skateboard problem). The heavier CLIP/WD14/Caption-V4 layer that already does something like this exists (`local_agent/gvd_qa/pipeline.py`, used at the video-submission gate) but was deliberately *not* duplicated at still-render time in the original wiring work, to avoid a `:11436` server dependency and latency at a point where a human was expected to review anyway. Given that a real miss just happened at the human-review stage too (the mismatch wasn't obvious enough to flag on a quick look), it's worth deciding: keep still-QA narrow and rely on the operator noticing, or extend it. This is a "you decide, then hand it to Fable to build" item, not something to hand off blind.

### 4. Outstanding judge-related decisions from `24q`/`24r`

Carried over from earlier in the project (not reverified this window, so treat as needing a fresh look before handing off): the curriculum-bar decision, the zero-score-ranking decision, the flicker-misread-as-cut false-fail pattern, and a `repeat_penalty` gap in the GVD judge. These are operator decisions more than pure engineering tasks — worth a quick re-read of `CHANGELOG/2026-09-24q_gvd_judge_fault_checks_and_labeled_eval.md` and `2026-09-24r_gvd_judge_heldout_and_frame_count.md` to refresh what's actually still open before deciding what (if anything) to hand off here.

### 5. Minor: story-name path inconsistency

Not urgent, but worth a quick look: the `media_artifacts` entries recorded in chat (e.g. `manifest_relpath: "outputs/stories/Scene Start Image 1/manifests/..."`, with a space) don't match the real on-disk directory name (`Scene-Start-Image-1`, hyphenated). The files were still found correctly by sha256/prompt_id in this check, so it's not blocking anything today, but if anything ever does an exact-path lookup using the recorded `manifest_relpath` rather than resolving it, it would fail silently. Worth a five-minute check of where that field gets written versus where the sanitized directory name gets decided.

## Recommended Fable handoff order

1. Item 1 (anchor registry) — ready to hand off now, as-is, using the existing wiring doc.
2. Item 2 (not_run masking) — ready to hand off now as a diagnostic + fix task.
3. Item 3 — needs your decision first, then hand off.
4. Item 4 — needs a 10-minute re-read on your end (or mine, next session) before it's hand-off-ready.
5. Item 5 — cheap enough to fold into whichever of 1/2 lands first, as a "also check this" note.

Both of today's earlier handoff docs from this session (the still-QA wiring spec and the startup-deadline race fix) were independently picked up and correctly acted on by other Claude Code sessions working this repo today — the same format should work again for items 1 and 2 above.
