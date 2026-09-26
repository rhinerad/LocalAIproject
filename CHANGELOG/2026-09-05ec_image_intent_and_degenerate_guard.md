# 2026-09-05ec — Image-intent routing + degenerate-output / render-owner guards

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05ec**.

`APP_REVISION`: `2026-09-05-image-intent-r84`.

Sibling of `2026-09-05dw` (empty 8B completion on the 8-clip START/LAST
brief). Same misclassification of a long still-frame script as
`CAP_LOGIC`, different live shape: a 14-beat photoreal brief ran on GPU
8B under **predictive context-length protection** and streamed a
degenerate numbered list instead of finishing stills.

## Transcript (not retyped)

`local_agent/chats/27b9fcc7bfad4490.json` (newest by mtime). Pinned
`huihui_ai/qwen3-abliterated:14b`. First user message starts:

```
AGENT TASK: still frames only. Photoreal live-action. Two adult women
from my reference sheets.
```

PRE01–PRE14 + PRE14B/C stills, `pre01_start.png` … `pre14c.png`. Last
stored route: GPU / 8B / ctx 32768 / `capability=logic` /
`GPU free — predictive context-length protection` /
`estimated_prompt_tokens=21056` / threshold 16000. Assistant
`content` is `""`. Activity: hop 0 planned ~30 `plan_story_image`
graphs, hop 1 started one `render_story_image` (pid 19820) then the
rest were refused (`another image render owns the backend`), hops 2–5
retried different story names against that owner, hop 6 hit the 6-hop
limit with no visible answer.

Operator-visible 112 blank numbered items + empty fences were streamed
on the 8B hops (`emit("token")`) and not stored as final content.

## 1. Predictive context-length protection is a real gate, not a leak

Unlike dw's stale `media_vram_pressure.json` (fixed in parallel as
`2026-09-05eb`), this demotion is `_adaptive_gpu_model`: live
`estimate_context_tokens(msgs, tool_schemas)` vs
`PRIMARY_SAFE_PROMPT_TOKENS` (16000). After hop 0 stuffed dozens of
pruned plan results into the transcript, 21056 > 16000 is a plausible
count, not a leftover file. The gate then unloads 14B and loads 8B at
`num_ctx=32768`.

It is a working safeguard against 14B KV overflow. On this class of
turn it is the wrong trade: 14B's VRAM ctx ceiling is 33976, so 21k
fits, and 8B degenerates.

No TTL was added to this path. Image-intent turns skip the 14B→8B
predictive fallback and keep PRIMARY (media-pressure and gpu_busy
still apply).

## 2. CAP_LOGIC from length, never an image-tool class

Same as dw: `classify_capability` ran `_CODE_SIGNAL`, then
`difficulty.needs_escalation` (`len>=700` **or** two difficulty
signals). This brief is thousands of characters and has **zero**
difficulty-signal hits, so it became `CAP_LOGIC`. On a **pinned**
Huihui chat that stamp does not swap in DeepSeek (`want_capability_gpu`
requires unpinned or a DeepSeek/Coder pin). Unpinned `auto_farm` would
have sent it to DeepSeek instead of tools, and treating it as
`CAP_TOOL` would farm-route a 16-still Comfy job to Mac Qwythos — the
reason dw refused a keyword→`CAP_TOOL` patch.

Fix: `image_generation_intent()` (still-frames / START+LAST /
`pre##_start.png` / “generate … image” / photoreal stills). Checked
**before** length escalation. Returns new `CAP_IMAGE`:

- not `CAP_LOGIC` (no DeepSeek)
- not `CAP_TOOL` (no Qwythos farm, no `gpu_core` catalog strip)
- unpinned and pinned Huihui stay on GPU PRIMARY with the full schema
- long image turns skip predictive 8B demotion

A Comfy **enqueue** whose graph filename contains `txt2img` is still
`CAP_TOOL` (case 4 regression). Bare `analyze_image` / “attached
image” is not generation.

## 3. Degenerate 8B output and hop-loop gaps

No repetition guard existed for this shape. Empty completion only
fires on **zero** visible text and **zero** tool_calls. Hop-limit with
empty `reply` stored `""`. `REPEATED_FAILURE_LIMIT` requires identical
(name, args); different `story` values against the same backend-owner
error burned hops 1–5.

Fixes in `agent.py`:

- `_is_degenerate_completion`: ≥8 blank numbered items (or empty
  fences) with almost no real prose → treat as empty, retry once, then
  `_EMPTY_COMPLETION_REPLY`. A real numbered brief with per-line prompts
  does not match.
- Hop-limit with no visible answer stores `_HOP_LIMIT_EMPTY_REPLY`
  instead of `""`.
- Any `render_story_image` result containing `another image render
  owns the backend` ends the turn this hop (after the successful
  start, if any) and tells the operator to poll
  `story_image_job_status` before the next still.

## Tests

```
python -m unittest local_agent.test_capability_routing local_agent.test_router_switching local_agent.test_native_tool_calling -q
python local_agent/test_difficulty.py
```

184 + 2 passed. Includes: long still-frame script → `CAP_IMAGE` even
when pinned Huihui; unpinned long script does not farm and keeps 14B
at 21k estimated tokens; non-image long context still demotes 14B→8B;
txt2img **filename** enqueue stays `CAP_TOOL`; 112-item empty list
retries then empty-completion reply; hop-limit empty answer is not
blank; one started render + owner refusal stops at hop 0.

## Not changed

- `media_vram_pressure.json` TTL (eb, parallel).
- Desktop attachment instruction still says `analyze_image` vs
  `see_image` (noted in dw; not this failure).
- No live GPU model load in this pass.

## Files

- `local_agent/router.py`
- `local_agent/agent.py`
- `local_agent/server.py` (`APP_REVISION`)
- `local_agent/test_capability_routing.py`
- `local_agent/test_router_switching.py`
- `local_agent/test_native_tool_calling.py`
- `CHANGELOG/2026-09-05ec_image_intent_and_degenerate_guard.md`
- `TODO.md`
