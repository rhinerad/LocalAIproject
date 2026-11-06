# 2026-09-26f — GVD router "ask, don't guess" verified and closed: the honest-failure statuses now end the chat turn with a fixed, specific question; before this the operator saw the model's narration ("rendering has started") over a blocked route

Roadmap prompt Phase 2c (roadmap B.7). Code and tests only: no GPU, no
ComfyUI, no render, no chat file. Id claimed once with
`scripts/next_changelog_id.py`. The motion-transfer session was rendering
pass24 (finished 02:10) and then CPU-scoring identity; nothing of its was
touched.

## 1. Trace: what reached the operator before

- `gvd_tool_router/planner.py::plan_shot` returns
  `{"status": "needs_manifest_review", "reason_codes": ["NEEDS_MANIFEST_REVIEW"], "note": "unknown interpretation; refusing to pick the fastest tool"}`
  when no interpretation matches; `router.py::route` returns
  `needs_manifest_review` (low-confidence hard requirement) or `blocked`
  (validation reasons; `NO_COMPATIBLE_TOOL` + `UNAVAILABLE_CAPABILITY` with a
  `rejection_log` whose per-row reasons carry `RESOURCE_BLOCKED`,
  `PROFILE_REQUIRED`, `unknown_vram`, `operator_approval_required`,
  `missing_capabilities:…`); `service.py::route_shot` adds
  `missing_capabilities` / `blocked_candidates` (25q); `execute_tool` wraps
  the decision under `decision`, and adds its own `ENGINE_FALLBACK_WAN`
  (26b), `QA_GATE_BLOCKED`, and lease-contention `RESOURCE_BLOCKED` blocks.
- `gvd_tool_router/tools.py` returns each as `json.dumps(..., indent=2)`.
- `agent.py`: `grep -n "NEEDS_MANIFEST_REVIEW\|needs_manifest_review\|PROFILE_REQUIRED\|NO_COMPATIBLE_TOOL\|RESOURCE_BLOCKED\|UNAVAILABLE_CAPABILITY\|operator_notice" agent.py`
  → **0 hits** before this change. The JSON went to the model as one
  `role: tool` message through `_tool_result_for_context` (pruned to
  `MAX_TOOL_RESULT_CONTEXT_CHARS`, so a long `blocked_candidates` list was
  cut), and the model's next free-text turn was the reply. None of the
  fixed-reply guards (`_blocked_specialist_scope_reply`, batch-folder,
  write_file, current-chat-render) covered GVD tools; GVD tools are also not
  in `_SPECIALIST_PROJECT_TOOLS`, so no scope guard intercepted them either.

Replayed on the committed `agent.py` (`git show HEAD:local_agent/agent.py`,
loaded beside the live one) with a fake model stream that makes the tool
call and then narrates, and the **real** planner/router output as the tool
result (`runtime/roadmap_20260926/replay_before_after_26f.py`, log and JSON
beside it):

| turn | tool result (real) | BEFORE: reply the operator got | after |
|---|---|---|---|
| "make a video that is nice" → `gvd_plan_shot` | `needs_manifest_review` / `NEEDS_MANIFEST_REVIEW` | "I planned the shot and will render it now with the fastest available tool; the video will be ready in a few minutes." (== model narration) | fixed question, below |
| "continue the last shot for 4 seconds" → `gvd_route_shot` S02 continuous, no start frame | `blocked` / `continuous_requires_start_or_context` | "Continuing the shot now from the previous frame." (== narration) | "No video tool was chosen or run for S02 (gvd_route_shot returned blocked). Nothing was rendered, queued, downloaded or installed. A continuous take needs a start frame or a context video to continue from. Which file? I will not pick an option for you." |
| "copy the motion of this clip onto Kent" → `gvd_route_shot` S03 `hard_requirements: [motion_reference]`, seed catalog | `blocked` / `NO_COMPATIBLE_TOOL`, `UNAVAILABLE_CAPABILITY`, `missing: fast_action, motion_reference`, 6 candidates | "Using the Wan Animate pipeline for this; rendering has started." (== narration) | "… No active tool offers: fast_action, motion_reference. Cataloged implementations that could supply it, none active: animatediff_sdxl_pose_ipadapter_unvalidated (disabled; …); fasth3_v1_t2va_unvalidated (…); fasth3_v2_unvalidated (…); ltx23_unvalidated (…); wan21_vace_1_3b_unvalidated (…); wan22_animate_14b_unvalidated (…). Approve enabling or installing one of them (each still needs its weights, a pinned template and a measured VRAM profile before it can run), or change the request so it no longer needs fast_action, motion_reference. I will not pick an option for you." |

`before_equals_model_narration: true` on all three. The ambiguous-request
"after" reply is: "No video tool was chosen or run for this shot
(gvd_plan_shot returned needs_manifest_review). Nothing was rendered,
queued, downloaded or installed. I could not tell what kind of shot this
is, so I did not guess the fastest tool. Which one is it: (a) a continuous
take that continues a start frame or an earlier clip, (b) a morph or
montage between prompts, (c) a scene with a named character who must stay
the same, or (d) an independent action clip? Also give the length in
seconds and the frame size if not 4 s at 1280x720. I will not pick an
option for you."

## 2. Change (`local_agent/agent.py`, CRLF kept; `_edit_agent_gvd_ask_26f.py` 6 anchors, `_edit_agent_gvd_ask_26f_shot_hint.py` 6 anchors, one byte-exact `cands[:4]`→`[:6]`)

- `_GVD_ROUTER_TOOLS` = gvd_plan_shot, gvd_route_shot, execute_narrative_scene,
  execute_continuous_take, execute_montage_morph, execute_fast_action.
- `_gvd_ask_payload(parsed)`: finds the ask-status part of a result
  (top-level; `execute_*`'s nested `decision`; `gvd_plan_shot`'s nested
  `route`, carrying the manifest along).
- `_gvd_router_question(tool, parsed, shot_hint)`: the fixed text, built
  **only** from the result's fields, one clause per code:
  `NEEDS_MANIFEST_REVIEW` (three variants: unknown interpretation → the
  four-way question; low-confidence hard requirement → names the
  requirement and its confidence; unreadable manifest → names the parse
  error), each `validate_manifest` reason (start/context file, prompt
  keyframes, character + reference image, id, duration, size, fps),
  `unknown_requested_engine:<x>`, `ENGINE_FALLBACK_WAN` (quotes the 26b
  `operator_notice` and the three ways forward), `QA_GATE_BLOCKED`,
  `NO_COMPATIBLE_TOOL` / `UNAVAILABLE_CAPABILITY` (missing capabilities +
  up to six catalog candidates with status and `disabled_reason`, or "say if
  you want a workflow discovery search"), `RESOURCE_BLOCKED` from the
  rejection log (names the rows; free the GPU or approve the override) or
  from a lease (wait or stop it), `PROFILE_REQUIRED` / `unknown_vram`
  (measure first, `apply_profile.py`), `operator_approval_required`. Every
  reply opens "No video tool was chosen or run for <shot> (<tool> returned
  <status>). Nothing was rendered, queued, downloaded or installed." and
  closes "I will not pick an option for you." A `RouteDecision` has no shot
  id, so `gvd_route_shot` questions take it from the call's own `manifest`
  argument (`_gvd_shot_hint`).
- `_gvd_router_questions(executed, plans)`: applies only when **every**
  call in the hop was a GVD router tool, none errored, and at least one is
  in ask-status; a selected call in the same hop is named as unaffected. Any
  other tool in the hop leaves the normal path alone (the model then has a
  real result to stand on), as does an `ERROR:` result (existing
  repeated-failure path).
- Hop loop: after the specialist-scope block and before the batch-folder
  guard, `gvd_question` ends the turn with `emit("note", "gvd router:
  honest-failure status returned as a fixed clarifying question; nothing was
  rendered or queued")`, `agentic_state.finish_turn`, and
  `_trace_return(..., gvd_router_question=True)` — the same shape as 25p's
  guards. No model prose after it.
- Selected/planned results with an `operator_notice` (Wan chosen as a
  resource fallback, 26b) are collected per turn (`gvd_notices_pending`) and
  `_append_gvd_notices` adds "Router notice: <verbatim>" to the final reply
  unless the reply already contains it. Not applied on the hop-limit or
  empty-completion reply paths (those fixed replies carry no router text).

## 3. Tests — new `local_agent/test_gvd_router_chat_surfacing.py` (LF), 24 tests

Shapes are real router output where the seed catalog can produce them:
`plan_narrative("make it nice")` (planner review), `route_shot` with a
low-confidence hard requirement (router review), continuous without start
frame, unknown engine, `motion_reference` on the seed catalog (six
candidates), a plain independent shot on the seed catalog (`fast_action`
missing — `required_capabilities()` adds the mode capability, which the
first draft of the tests did not expect), `route()` with an activated seed
row at 1,000 MiB free (`RESOURCE_BLOCKED`), with a vendor-evidence profile
(`PROFILE_REQUIRED`), with `requires_operator_approval`, and the
`execute_tool` nested-decision wrap. The two literal `service.py` blocks
(`ENGINE_FALLBACK_WAN`, `QA_GATE_BLOCKED`) and a lease string are dict
copies. Hop aggregation: non-router tool → None; `ERROR:` → None; selected +
asked → both named; notice appended once and not when present. Four
`agent.answer()` tests with the 25p fake-stream pattern: ambiguous request
→ the fixed question, model's "will render … ready in a few minutes" absent,
note emitted, tool called once; missing start frame → "Which file?";
selected route with a fallback notice → model reply kept **and** "Router
notice: …" appended; selected route without notice → model reply unchanged.

- `python -m unittest test_gvd_router_chat_surfacing` → **24/24 OK** (55.9 s).
- `python -m unittest test_native_tool_calling` → **118/118 OK** (31.5 s),
  run twice (after each agent edit). Logs: `runtime/roadmap_20260926/tests_26f_*.log`.

## 4. Files

- `local_agent/agent.py` (CRLF, 0 bare LF before and after; 3 anchored
  scripts kept under `runtime/roadmap_20260926/`).
- `local_agent/test_gvd_router_chat_surfacing.py` (new).
- `runtime/roadmap_20260926/replay_before_after_26f.{py,log,json}`.
- `TODO.md` (CRLF): new section "GVD router 'ask, don't guess' reaches the
  chat — 2026-09-26f" with the two open follow-ups below.

## Not done / follow-ups

- The running GUI `server.py` still has the old `agent.py` loaded; the
  change reaches live chats after a restart (same situation as 24a/25p).
- `plan_video_from_reference` is not in `_GVD_ROUTER_TOOLS`: its result is
  a feasibility report with a nested `gvd_route`, already written for the
  operator (25q), and its "download or accept installed-only" decision was
  taken in 26d; left as is.
- Notices on the hop-limit / empty-completion paths (rare) are not appended.
- Verification here is unit tests plus the HEAD-vs-tree replay with a fake
  model stream; no live model turn was run.
