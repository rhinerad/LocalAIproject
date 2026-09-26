# Build spec: wire the real still-QA system into `render_story_image`/`render_story_image_batch`, and fix a live bug in the pipeline that's supposed to have it already

**For:** a Claude Code session (Opus 5.5 at `xhigh`, or Fable 5.1 at `high`/`xhigh`) working in `COMFYUI_STORY_HANDOFF_2026-08-09`. This is real cross-file wiring plus one confirmed regression fix — Opus 5.5 tier.

## Background — read this first, it's the whole reason this doc exists

The operator asked why a bad still (a plain empty room, not the described "Fall & Arrival" scene) got waved through with a completely fabricated "QA process confirmed... now marked as SELECTED" narrative. My first answer was wrong: I said there is no automated still-QA anywhere in this codebase. The operator correctly pushed back — **there is** a real, working still-QA system here. I was wrong to miss it, and this doc is the fix for what I found once I looked properly.

There are, in fact, **three separate pieces**, and the whole problem is that they don't talk to each other:

1. **`creative_still_qa.py`** (repo root) — a self-contained, CPU/local, prompt-aware check. Given a candidate PNG, a prompt, an optional "anchor" (a previously-approved still to compare continuity against), and optional `clip`/`kind` metadata, it runs face detection (YuNet), person detection (YOLO), face-identity comparison (SFace), and room/background continuity (HSV histogram correlation), fail-closed by design (e.g. "prompt says nobody should be visible, but a face showed up" → reject; "room/wallpaper drifted too far from the anchor" → reject). Entry point: `creative_approve(path, *, prompt, anchor=None, clip=None, kind="last") -> (ok: bool, reject_reasons: list[str], report: dict)`, which wraps `compare_stills(...)`. Needs local ONNX model files already present on disk at `models/opencv_face/face_detection_yunet_2023mar.onnx`, `models/opencv_face/face_recognition_sface_2021dec.onnx`, `models/opencv_person/yolov8n.{pt,onnx}` — no server, no GPU, no network call. This is the cheap, fast layer.

2. **`local_agent/gvd_qa/pipeline.py::run_persisted_still_qa` / `evaluate_persisted_candidate`**, reached through `local_agent/gvd_qa/local_client.py::cpu_local_client` — a heavier layer that adds CLIP scoring, WD14 tagging, ImageReward, and a "Caption V4" VLM check (a local server expected on `127.0.0.1:11436`). This is invoked by `local_agent/gvd_qa/i2v_gate.py::apply_qa_gate()`, which is called from `batch_run_backrooms_gvd.py`'s `gate_before_video_submit()` — **a real gate that was only added 2026-09-23 (yesterday relative to today, per its own changelog citing "readiness-audit finding 1.1")** — and it fail-closed refuses to submit a clip for I2V/video generation unless there's an accepted still-QA receipt (`accepted.json`). This is the layer with real evidence of working: a changelog entry shows it catching a real bad image (`br24_C017`, wrong wall color) and writing `blocked.json`.

3. **`render_story_image` / `render_story_image_batch`** (`local_agent/tools.py`, backed by `work/image_render.py`) — the tool the chat-based agent actually used to generate the bad "Fall & Arrival" image. **Confirmed: this path has zero QA awareness.** `work/image_render.py` has no mention of "qa" anywhere; `local_agent/tools.py` doesn't call into either of the two QA layers above at any point in this path. It renders, saves a PNG, and marks it pending human review — nothing ever scores it.

So: real QA exists, it's proven to catch exactly this class of bug, and it's completely disconnected from the tool actually used day-to-day in chat. That's the gap to close.

## Part 0 — a real, separate bug: `flux_still_batch.py`'s own QA call is currently broken

While tracing this, I found that even pipeline #1 above, in its *other* caller, has a live bug. `flux_still_batch.py` imports:

```python
import creative_still_qa
from creative_still_qa import empty_pov_prompt_boost, infer_visibility_expectation as csqa
```

...then in `auto_approve()` (around line 220) calls:

```python
ok_c, creasons, crep = csqa.creative_approve(
    path, prompt=prompt, anchor=anchor, clip=clip, kind=kind
)
```

`csqa` is bound to the **function** `infer_visibility_expectation`, not the `creative_still_qa` module (which was separately imported under its own unaliased name on the line above). I confirmed directly (`python3 -c "..."`) that `infer_visibility_expectation` has no `.creative_approve` attribute — calling this raises `AttributeError` immediately, every time `auto_approve()` is called with `creative=True` and a non-empty `prompt` (the normal case). This means `flux_still_batch.py`'s own inline auto-approve step is currently non-functional and would crash rather than approve or reject.

This doesn't contradict the changelog evidence of `br24_C017` being correctly blocked — that evidence almost certainly went through pipeline #2 (`evaluate_persisted_candidate`/`cpu_local_client`, called via the smoke-test scripts or the I2V gate directly), not through this `auto_approve()`/`creative_approve()` call site. But it means this specific call site — the one meant to gate `flux_still_batch.py`'s own generation loop in real time — has probably never actually run successfully, or broke at some point after that changelog entry.

**Fix:** change `csqa.creative_approve(...)` to `creative_still_qa.creative_approve(...)` (the module is already imported under that name two lines above — simplest fix, one line). Then actually exercise `auto_approve()` with `creative=True` and a real prompt/candidate image to confirm it now runs to completion instead of raising. This is a small, mechanical, high-confidence fix — do it first, it's a five-minute detour before the real work below.

## Part 1 — wire `creative_still_qa.creative_approve` into `render_story_image` / `render_story_image_batch`

This is the actual ask. Use pipeline #1 (`creative_still_qa.creative_approve`), not pipeline #2 — it's local-only, fast, has no server dependency, and is exactly the right weight for "run this automatically after every chat-triggered still render." Don't try to also wire in the CLIP/WD14/Caption-V4 layer here; that's already correctly positioned as the video-submission gate, and duplicating it at still-render time adds a `:11436` server dependency and real latency for no clear benefit at this stage — a person is about to look at the image anyway.

**Where to hook it in:** `render_story_image` (`local_agent/tools.py:2119`) has `story`, `prompt`, and `mode` in scope already by the time the render completes (read the full function — it threads these through to `image_render.execute(...)` or equivalent). After the render succeeds and the output PNG path is known (before or as part of building the result JSON that `render_story_image_batch` later aggregates into `completed[i]`), call:

```python
import creative_still_qa
ok, reject_reasons, qa_report = creative_still_qa.creative_approve(
    output_path, prompt=prompt, anchor=<see below>, clip=<see below>, kind="last",
)
```

Attach `{"ok": ok, "reject_reasons": reject_reasons, "report": qa_report}` into the per-job result dict, so it flows through `render_story_image_batch`'s `completed[i]` entries and into whatever `present_story_stills_for_review` receives as `stills`. That's the critical part: **the human-review payload and the chat agent's own narration should be built from this real QA report**, not left to the model to describe from nothing (which is exactly how the "processed through the QA pipeline... SELECTED" hallucination happened last time — there was no data to ground the claim in, so the model invented some).

**The anchor problem — this needs a real decision, don't guess:** `creative_approve` takes an optional `anchor` (a previously-approved still to check room/identity continuity against). `flux_still_batch.py` resolves this from its own `approved` registry, keyed by clip id (see its lines ~365-383 — it looks up the previous clip's approved "last" frame, or a fixed `C001_start.png` for the very first shot). The chat-driven `render_story_image`/`render_story_image_batch` path has **no equivalent registry** — it only knows `story` (a free-text label) and `prompt`, no clip-id/sequence concept. Before wiring this in, decide and implement one of:
- Track "last operator-approved still for this story" in a small JSON file (e.g. `work/runtime/story_qa_anchors.json`, keyed by `story`), updated inside `approve_story_stills` when the operator actually approves — so continuity checks compare against the last *human-approved* image, not the last *generated* one.
- Or, if no anchor exists yet for a story (first still), pass `anchor=None` — `compare_stills` already handles that gracefully (it just skips the continuity-vs-anchor checks and still runs the person/face/empty-POV checks, per `infer_visibility_expectation`).

Don't invent a `clip`/`kind` value either — check what `compare_stills`/`infer_visibility_expectation` actually do with `clip` (a `Mapping[str, Any] | None`) and `kind` (default `"last"`) before deciding whether the chat path has anything meaningful to pass, or whether `clip=None, kind="last"` is the right default here (probably is, for freeform prompts with no clip register).

**Failure mode — advisory or blocking?** This path already has a real, working human-approval gate (`present_story_stills_for_review` → operator says "looks good" in chat → `approve_story_stills`). Recommend: don't hard-block a failed QA still from being *shown* to the operator (they may still want to see it and decide themselves — e.g. a false positive on the continuity check). Instead, make the QA report part of what's presented, and make sure the chat agent's own reply is required to state QA's actual verdict plainly (pass/fail + reasons) rather than staying silent or inventing a verdict. If you want a hard stop for clearly-broken cases (e.g. `expect_empty_of_people` violated by an unexpected face), that's a legitimate stricter option — ask the operator's preference before deciding this, since it changes the interaction model (silent-fail-and-retry vs. always-show-with-a-warning-label).

## Testing

- Unit test `creative_still_qa.creative_approve` is actually called with the right arguments after a successful `render_story_image` — mock the render/backend, assert the QA report shape lands in the tool's returned JSON.
- A regression test mirroring the operator's actual failure: feed a candidate image that legitimately fails `compare_stills` (wrong room / unexpected face) through the wired-up path and confirm the result's `ok`/`reject_reasons` reflect that, and that `present_story_stills_for_review`'s payload carries it through.
- Live verification: run one real `render_story_image_batch` call end to end and confirm a QA report is actually attached to the completed job in the GUI/chat, not just in a unit test.
- Also verify the Part 0 fix (`flux_still_batch.py`) separately: run `auto_approve()` on a real candidate + prompt and confirm it no longer raises `AttributeError`, and returns a real `(ok, reasons, report)` tuple.

## A wording follow-up in `local_agent/agent.py`, only if you end up in this file anyway

Not required for this task, but flagging since it's directly related: `local_agent/agent.py` has a guard (`_STILLS_FALSE_APPROVAL_RE` / `stills_pending_operator_review`, added this week to stop the exact "fabricated SELECTED/QA-pass" hallucination the operator hit) whose correction message currently says *"There is no automated QA/selection step for story stills in this pipeline."* That's now known to be an overstatement — there is one, it's just not reachable through this specific tool path (which is exactly what Part 1 above fixes). If Part 1 lands, that message should be revisited — either drop the blanket "there is no QA" claim in favor of describing the real QA report now attached to the result, or narrow the wording to something like "no QA verdict has been recorded for this image" so it stays accurate whether or not QA ran. Search for `_STILLS_FALSE_APPROVAL_RE` to find the exact spot.

## Gotcha (recorded every time this bites — recording it again)

An unscoped `grep -r` / `find` across `local_agent` without excluding `local_agent/vendor` reliably times out — that subtree has restricted-permission directories that hang a recursive walk even with output post-filtered. Scope every search explicitly (`grep -rn "<pattern>" local_agent --include="*.py" -- --exclude-dir=vendor`, or target specific files/dirs) rather than a bare recursive search.
