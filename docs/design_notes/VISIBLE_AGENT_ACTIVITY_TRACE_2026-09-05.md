# Design: visible agent activity trace in the chat UI

| Field | Value |
|---|---|
| **Document** | User-facing execution trace in `static/index.html` |
| **Date** | 2026-09-05 |
| **Status** | Scope only — do not build from this pass |
| **TODO** | `TODO.md` “Visible agent activity trace” |
| **Sibling** | `local_agent/tracing.py` SQLite spans (`grok-design-doc-a1c90b30` / `CHANGELOG/2026-09-05l`) |
| **Out of scope here** | Phoenix/Langfuse, hidden chain-of-thought, `tracing.py` schema, inline media cards (separate TODO) |

This is the implementable spec for the chat-UI item. Same evidence bar as the
tracing scoping pass: live call sites, not `HARNESS_OPTIMIZATION.md`
pseudo-code.

---

## Overview

The operator already sees *something* while a turn runs: an `agent · GPU ·
{model}` who-line, a collapsible “Working…” list, and per-tool `.act` cards.
That is not a ChatGPT/Claude-style execution trace. Most of the typed
lifecycle the TODO names (`planning`, `tool_call`, `tool_result`,
`verification`, `waiting_for_permission`, `complete`, `blocked`) is either
already on the wire under different `kind`s, or is computed in `agent.answer`
and never sent.

**Orange’s `tracing.py` PR 2 does not block this.** Tracing is a durable
investigator log (`traces.db`, redact, never fail the turn). This item is a
live, operator-visible surface on the existing SSE `on_event` callback. The
tracing design’s own non-goals say so: “Replacing GUI events…” is out of
scope there, and “A GUI trace viewer in this design” is an explicit non-goal
(`grok-design-doc-a1c90b30` Goals/Non-goals). Decision 2 of that review
**forbids** putting `trace_id` on the `route` SSE event (would be
transport-visible and require `APP_REVISION`). Do not couple the two.

---

## What the operator sees today (live)

All of this is `local_agent/static/index.html` + `server.py` `push()`.

| Surface | Code | What it actually is |
|---|---|---|
| Who-line `agent · GPU · {model} · ctx …` | `index.html` `stream()` on `kind==='route'` (~507–514); `bubble()` who-node (~189–192) | Last `Decision.as_dict()` of the hop. `r.tier.toUpperCase()` — **farm becomes the string `FARM`**, not “GPU”. Chat-list badge is dumber: `last_tier==='gpu'?'GPU':'CPU'` (`loadChats` ~334–335), so a farm turn is labelled **CPU** after refresh. |
| `details.trace` “Working…” | `startTrace` / `trace` / `finishTrace` (~198–217) | In-memory `<ol>` of labels. Collapses to “Completed — show work trace” on `done`/`error`/stream end. **Not stored.** `openChat` (~392–395) only `render(m.content)`. |
| Tool `.act` cards | `kind==='tool'` then `tool_result` (~517–521) | Card is created with **args JSON at announce time**, result `<pre>` appended later. Announce happens **before** `tools.call` (`agent.py` ~1940–1969: “announce all of them immediately”). Intention and observation share one card; the UI has no “pending vs done” class. |
| `note` cards | `kind==='note'` (~525) | GPU-gate pending, farm fallback, compaction, “task plan prepared: …”, empty-completion, hop-limit. Free text, not typed. |
| `queued` card | `server.py` `push` synthesizes `queued` from `tool_result` JSON with `queued: true` (~551–562); GUI ~522–524 | Media/GPU-busy jobs. |
| Story-image thumbs | `addStoryImagePreviews` (~446+) | Only `story_image_job_status` / `render_story_image`. Separate TODO for general inline media. |
| GPU/file-edit **sidebar** | `/api/gpu_gateway`, `/api/file_edit_gateway`; `gpu_gate.request` from `_request_chat_gpu_gate` (`agent.py` ~1296–1313) | Pending permission is a **sidebar poll**, plus a `note`. No SSE `waiting_for_permission`. |

SSE envelope (`server.py` ~528–567): every callback is
`{"kind": kind, "data": data}` flushed immediately. Kinds the GUI handles:
`conversation`, `route`, `progress`, `token`, `tool`, `tool_result`,
`queued`, `note`, `error`, `done`. Anything else is ignored.

`learning.record` (`learning.py` ~31–33) only hashes failure categories; it
is not a UI ledger.

---

## Data that already exists (not shown, or shown poorly)

### On the wire this turn

| Fact | Where it is now | Gap vs TODO |
|---|---|---|
| Routing tier / host / model / reason / backend | `emit("route", json.dumps(route.as_dict() + ctx fields))` `agent.py` ~1748–1756, ~1834–1838. `Decision` fields: `tier`, `host`, `model`, `gpu_busy`, `reason`, `detail`, `backend` (`router.py` ~416–449). | Who-line uses `tier` + `model` + ctx only. `reason`, `backend`, `gpu_busy`, `detail` are dropped. |
| `detail["capability"]` | Set in `decide()` when a capability class applied (`router.py` ~1418–1419: `detail["capability"] = capability` ∈ `{tool, logic, code}`). Travels inside `as_dict()` → `route` SSE. | GUI never reads `r.detail`. |
| Farm vs local | `backend=="farm"` on that same `route` event; farm miss is a `note` (`agent.py` ~1744–1747). | Farm **call happens before** `emit("route")` (`try_qwythos_on_farm` ~1725–1752). During a 45 s Mac load the only GUI text is the client-side `trace('Request received locally')`. |
| Progress labels | `emit("progress", {stage, label})` stages `review`, `decide`, `write`, `tool`, `evidence` (`agent.py` ~1753–1756, 1786–1788, 1816–1818, 1965–1968, 2202–2205). GUI `trace(label)` (~515). | Not the TODO enum. No hop index. Labels are generic (“Deciding the next safe action”). |
| Tool name + args | `emit("tool", {tool, args})` after unwrapping `call_tool` (`agent.py` ~1955–1969). | Args are raw JSON in the card — secrets/paths unredacted on the desktop SSE (desktop is loopback; still the pruning boundary for persistence). |
| Tool result (truncated) | `emit("tool_result", result[:4000])` (~2023). Server also builds `_tool_evidence` summaries 240 chars (`server.py` ~543–565) with `outcome` error-vs-result, optional `path` / `file_changed` / `queued`. | Evidence list is **not** sent as its own event; it is stuffed onto `store.append(..., meta={"tool_evidence": ...})` after the turn (~621–623). |
| Short task plan | `planner.propose` → `agentic_state.apply_proposed_plan` → `emit("note", "task plan prepared: " + titles)` (`agent.py` ~1416–1423). Durable JSON under `runtime/agentic_tasks/{cid}.json` (`agentic_state.py`). | Typed `planning` event does not exist. Plan is a `note`. Hidden 14B propose is skipped when GPU busy (~1413–1415) — UI silent. |
| GPU permission pending | `_request_chat_gpu_gate` `note` (~1307–1312) + sidebar. Turn continues on CPU (`effective_prefer = "cpu"`). | Not `waiting_for_permission`; the turn is **not** paused for the card. |
| File-edit permission | `file_edit_gate.request` inside tools; snapshot poll. | Same: no SSE kind. |
| Hop index | `for hop in range(MAX_TOOL_HOPS + 1)` (`agent.py` ~1657), `MAX_TOOL_HOPS = 6` (~54). | **Never emitted.** |
| StreamEnd telemetry | Stashed `stream_end = piece` (~1810–1813) “for tracing PR 3”. Not SSE. | Token/duration on the bubble would need a new kind or a `progress` field. Tracing PR 3 is the investigator copy; UI can ignore it. |
| Action-resolver short-circuit | `_execute_plan` returns without a hop (`agent.py` ~1477–1481). Still emits `tool` / `tool_result` from that helper (~804–932, 1505–1569). | No `route` event on that path → who-line stays `agent`. |

### Durable after refresh

| Store | Contents | GUI restore |
|---|---|---|
| `chats/{id}.json` assistant row | `content`, optional `tool_evidence`, `retrieved_exemplar_ids` (`store.append` meta) | `openChat` renders **content only**. `tool_evidence` is replayed to the **model** as a system fact blob (`server.py` ~585–608), not to the operator. |
| `last_tier` | Last `route.tier` (`server.py` ~628–629) | Chat list GPU/CPU badge; farm → CPU. |
| `runtime/agentic_tasks/{cid}.json` | goal, plan steps pending/blocked, observations | Injected into the model via `prompt_block`; never fetched by `index.html`. |
| `traces.db` | Does not exist until Orange PR 2 | Must not be the restore path for v1. |

The tracing design already recorded this: “GUI `emit` … Lost when the
browser tab closes” / “`store.py` chat JSON — Final assistant text”.

---

## Intention vs observed action (must not lie)

Live bug-shaped behavior, not a future risk:

1. `emit("tool")` fires when the hop **plans** the call, before `run_one`
   (`agent.py` ~1940–1969). The GUI labels it “Using local tool” (`index.html`
   ~519). That is an intention.
2. `tool_result` is the observation. `ERROR:` / `REFUSED` prefix is the
   failure signal (`server.py` ~548).
3. `planner` / `agentic_state` steps are checklists, not proof
   (`agentic_state.py` docstring: “cannot execute an action”).
4. `progress.stage=="write"` + `token` is drafting, not a completed answer
   until `kind==='done'`.

v1 UI must keep two states on each tool card (`announced` / `result|error`)
and must not promote plan titles to “did X”.

---

## What would need new plumbing

Split so v1 can ship without Orange PR 2/3.

### A — GUI-only (no `APP_REVISION` if kinds unchanged)

Use existing `route` / `progress` / `tool` / `tool_result` / `note` /
`queued` / `done`.

- Render `r.backend`, `r.reason`, `r.detail.capability`, `r.gpu_busy` on
  the who-line or a routing chip.
- Fix chat-list `last_tier` for `farm`.
- Style tool cards as pending until `tool_result`; show error vs result.
- Map `progress.stage` onto the TODO verbs (`decide`→planning-ish,
  `tool`→tool_call, `evidence`→verification-lite, `write`→drafting).
- Restore last-turn `tool_evidence` from `/api/chat` JSON in `openChat`
  (already on disk; GUI ignores it).

No hop index, no elapsed timer, no plan card, no permission SSE. Still a
visible upgrade.

### B — Small SSE extras (transport-visible → bump `APP_REVISION`)

`APP_REVISION` is `"2026-09-01-action-resolver-r76"` (`server.py` ~55).
Bump when the wire changes, same rule as tracing decision 2.

| Extra | Why |
|---|---|
| `hop` on `route` and `progress` | Index exists in the loop and is not sent. |
| `emit("route")` **before** `try_qwythos_on_farm` (or a `progress` “farm Qwythos”) | Closes the 45 s silent load. Reorder in `agent.py`; farm path currently emits route only after the Celery wait. |
| Typed `planning` from `planner.propose` / `agentic_state` plan | Replace the `note` string. Mark `source: "proposal"` so it is not execution. |
| Typed `waiting_for_permission` from `_request_chat_gpu_gate` / `file_edit_gate` | Sidebar remains source of truth; SSE is a banner. Do not claim the turn is blocked if CPU fallback already proceeded. |
| Persist `activity` array on the assistant message | Mirror `_tool_evidence`: server `push` already sees every kind; copy a redacted list into `store.append` meta. `openChat` restores cards. |

Do **not** add `trace_id` to SSE. That is Orange’s decision 2.

### C — Do not do for v1

- Read `traces.db` from the browser (PR 2 unwired; PR 3 is `agent.answer`
  instrumentation for investigators).
- New `kind`s that duplicate `tool` / `tool_result` (`tool_call` rename is
  cosmetic; keep the live names).
- Elapsed-time server clock: the client can timestamp `route`/`tool`/`done`
  locally for the live turn; restore does not need it.
- Hidden thinking / `StreamEnd.thinking_chars` in the UI (tracing PR 3
  copies those onto a reason span; the hop loop already refuses to
  stringify `StreamEnd` into the reply — `CHANGELOG/2026-09-05m`).
- Citations as a new event: the hop already instructs the model to cite
  tool results in prose (`agent.py` ~2206–2211). Parse-from-prose is
  unreliable; v1 can highlight `tool_evidence.path` instead.

---

## Dependency on Orange tracing (explicit)

| Tracing PR | Blocks UI v1? | Why |
|---|---|---|
| PR 1 `StreamEnd` | **No** | Landed (`2026-09-05m`). Hop loop ignores non-`str`. UI never needed the trailer. |
| PR 2 `tracing.py` core, unwired | **No** | SQLite module with no `agent.answer` hooks. GUI does not import it. |
| PR 3 instrument `agent.answer` | **No** for v1 A/B | Would *also* see hops/tools/routes, as a side-channel for grepping later. Live SSE is already that stream. Optional later: “open trace” for operators — still not v1. |
| Decision 2 (`trace_id` off SSE) | **Constraint** | UI must not add it. |

Shared discipline (copy, do not import tracing to get it): redact like
`artifacts.prune_large_text` / `remote_security` arg redaction before
persisting activity; never store thinking text; never fail the turn if a
card fails to render.

---

## Suggested PR cut (when authorized to build)

1. **GUI A** — who-line + farm badge + pending/error tool cards + restore
   `tool_evidence`. No new SSE kinds. Tests: js-free python tests for
   `store`/`push` evidence shape already exist; add GUI-contract tests that
   parse `_tool_evidence` the way `openChat` will. `APP_REVISION` unchanged
   if the wire is unchanged.
2. **Emit reorder + hop field** — `route`/`progress` before farm wait;
   `hop` int. `APP_REVISION` bump. Tests on `agent.answer` `on_event` log
   (same style as `test_native_tool_calling`).
3. **Persist `activity` meta + `planning` / permission banner.** Still no
   `traces.db`. Acceptance from the TODO: multi-tool hop, failed tool,
   GPU-gate note, queued media, refresh restore, no-secret in stored
   activity (args truncated/redacted).

---

## Acceptance mapped to live code

| TODO acceptance | Live hook |
|---|---|
| Native multi-tool turn | `plans` announced then `run_one` sequential/parallel (`agent.py` ~1987–2023) |
| Failed tool | `tool_result` `ERROR:` / `REFUSED` |
| Approval wait | `note` + `/api/gpu_gateway` / `file_edit_gate`; turn may already be on CPU |
| Streamed media job | `queued` SSE + queue poll |
| Chat refresh | today **fails**; needs A restore or B `activity` meta |
| No-secret-leak | desktop SSE is loopback; persisted activity must follow `_tool_evidence` 240-char / key allow-list (`server.py` ~556–558), not raw `tool` args |

Unverified here: whether any existing unittest asserts the exact GUI who-line
string. Treat GUI contract tests as new work, not as already covered.
