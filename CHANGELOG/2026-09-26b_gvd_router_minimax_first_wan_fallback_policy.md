# 2026-09-26b — GVD tool router: MiniMax-first engine policy, Wan only by request or as an announced last resort

Offline code work in `local_agent/gvd_tool_router/` plus one whitelist
description string in `local_agent/tools.py`. No render was started, no
ComfyUI call was made, no registry or catalog JSON on disk was rewritten, no
model was downloaded. The only GPU-adjacent action was a read of the existing
`runtime/gvd_tool_router/registry/active.json` and
`inventory/environment_lock.json`.

Operator policy being enforced: **MiniMax is the default video engine. Wan may
be selected only when (a) the operator's own request explicitly names Wan, or
(b) no MiniMax implementation fits the shot and Wan is the only compatible
implementation left — and (b) must be surfaced to the operator, not just
logged.**

## 1. Legacy Backrooms pipeline — confirmed MiniMax-only, not touched

- `batch_run_backrooms_gvd.py` (repo root): the only "Wan" strings are two
  comments saying not to invent Wan/FLUX CFG for the distilled H3 path. No
  Wan graph builder, no Wan node, no fallback.
- `local_agent/dspy_orchestrator.py`: `build_wan_graph()` raises
  `RuntimeError("build_wan_graph is retired…")`; `generate_wan_clip()` is a
  deprecated alias that calls `generate_minimax_clip()`. The remaining "wan"
  hits are docstrings, the `GVD_WAN_TIMEOUT_S` env name (reused as the
  MiniMax track timeout), and a scoring heuristic on error text.
- `test_dspy_orchestrator.py::test_build_wan_graph_is_retired` already pins
  the retirement. Nothing in that path was changed.

## 2. Where MiniMax-vs-Wan is decided now

`gvd_tool_router/router.py::route()` → inner `consider()`:

1. `engine_family(impl)` classifies every catalog row as `"minimax"`,
   `"wan"` or `"other"` from `limits["engine_family"]` if stated, else from
   `implementation_id` + each stage `model_family_key` (MiniMax H3 and the
   FastH3 distillations are one family; `wan22_*`, `wan21_*`,
   `wan_tile_video`, `wan22_animate`, `wan21_vace` are the other; LTX,
   AnimateDiff, IP-Adapter, SDXL, LongCat are neutral).
2. `engine_tier(impl, manifest.requested_engine)` gives the sort tier.
   Default: MiniMax 0, other 1, Wan 2. With `requested_engine == "wan"`:
   Wan 0, everything else 1.
3. Viable candidates sort by `(tier, -score, implementation_id)`. Before this
   change they sorted by `(-score, implementation_id)` only — there was no
   engine concept anywhere in `route()`.
4. `engine_policy(winner)` annotates the `RouteDecision`:

   | winner | `requested_engine` | `engine_selection` | `reason_codes` | `operator_notice` |
   |---|---|---|---|---|
   | MiniMax / other | none | `default` | `()` | none |
   | Wan | `"wan"` | `explicit_request` | `ENGINE_EXPLICIT_WAN` | "Wan selected … because the operator's request explicitly named Wan" |
   | Wan | none | `fallback` | `ENGINE_FALLBACK_WAN` + `minimax_unfit:<id>:<reasons>` per rejected MiniMax row, or `minimax_absent` | "MiniMax didn't fit, used Wan instead (<id>), because … Wan was the only compatible implementation left … confirm before rendering." |
   | MiniMax / other | `"wan"` | `requested_engine_unavailable` | `REQUESTED_ENGINE_UNAVAILABLE:wan` + `wan_unfit:<id>:<reasons>` | "The operator requested Wan but it could not be used (…); selected <id> instead." |

   The fallback and explicit paths are therefore distinguishable by
   `engine_selection`, by reason code, and by notice text.

Manifest hook: a dedicated `ShotManifest.requested_engine: str | None` field
(schema.py), read by `shot_from_dict` (lower-cased, empty → None). It was
chosen over `hard_requirements` because `required_capabilities()` treats every
`hard_requirements` entry as a capability name, and over `priorities` because
those are numeric quality floors. An unknown value (e.g. `"sora"`) makes
`validate_manifest()` emit `unknown_requested_engine:<x>` and `route()`
returns `blocked` instead of guessing.

Planner path (planner.py): `requested_engine_from_text()` sets
`requested_engine = "wan"` only for a verb of choice next to the word
("use wan", "try wan", "switch to wan", "render it with wan", "on Wan 2.2",
"wan for this one", "wan instead"). A bare "wan" (English word) is not a
request; negations ("don't use wan", "no wan", "not wan") win. Engine words
never rescue an otherwise unreadable request — the `needs_manifest_review`
check runs first. `user_manifest["requested_engine"]` still overrides. The
planner's return now includes `requested_engine`.

Operator-facing surfacing (service.py):

- `route_shot()` → `to_plain(decision)` now carries `engine`,
  `engine_selection`, `operator_notice` automatically; `gvd_route_shot`
  and `gvd_plan_shot` (via `plan_narrative`) return them unchanged.
- `execute_tool()`: a `fallback` decision with `live=False` returns the
  planned DAG **with the notice attached**; with `live=True` it is
  **blocked** (`ENGINE_FALLBACK_WAN`, `operator_acknowledgement_required`,
  notice, and a note naming the three ways forward) unless the raw manifest
  dict carries `operator_acknowledged_wan_fallback: true`, in which case an
  `operator_acknowledged_wan_fallback` store event is emitted and the result
  carries the notice. `explicit_request` never hits this gate. This reuses
  the raw-dict-flag pattern of `operator_approved_i2v` /
  `operator_approved_resource_override`; the 2026-09-25q
  `_blocked_capability_report` plumbing (blocked routes) is untouched and
  still attaches on `blocked`.

## 3. `requires_operator_approval` — what it actually did before, and now

Traced before changing anything (the trace in the request was correct):

- `router._select_profile()` used it only as
  `if operator_approval and impl.limits.get("requires_operator_approval")`
  → headroom 512 MiB instead of 2,048. With `operator_approval=False` the
  flag was never read.
- `schema.can_activate()` does not reference it.
- `switch.switch_to()` lowers headroom on `operator_approval` alone and never
  reads the flag.
- `service.execute_tool()` called `route()` **without** passing
  `operator_approval` at all, so an approved manifest could route via
  `route_shot()` but the same approval was dropped on the execute path.

Net: the flag gated nothing. It only *widened* admission when approval was
already present; with enough free VRAM (not this 16 GiB card, but any larger
one) the row would have been selected with no approval. The name says
"requires"; the 2026-09-22i intent was "this row may only be admitted with an
explicit operator approval". It is kept, with that meaning made real:

- `router._compatible()` rejects a flagged row with
  `operator_approval_required` whenever `operator_approval` is False,
  regardless of free memory. With approval the existing 512 MiB headroom rule
  still applies.
- `execute_tool()` now reads `operator_approved_resource_override` from the
  raw dict and passes it to `route()`, matching `route_shot()`.
- `catalog_seed.py`: comment above the `fasth3_v2_unvalidated` row stating
  the enforced semantics. No data change; the on-disk registry digest
  `c495262e…` is unchanged.

Read-only check against the live registry (route() with a synthetic
15,831 MiB free inventory): `fasth3_v2_unvalidated` is rejected
`operator_approval_required` without approval and selected with it.

## 4. Files changed

- `local_agent/gvd_tool_router/schema.py` — `ShotManifest.requested_engine`;
  `RouteDecision.engine / engine_selection / operator_notice`; `_engine()`.
- `local_agent/gvd_tool_router/router.py` — engine constants,
  `engine_family()`, `engine_tier()`, tiered sort, `engine_policy()`,
  `unfit()`, `operator_approval_required`, `unknown_requested_engine` review.
- `local_agent/gvd_tool_router/planner.py` — `_WAN_REQUEST`, `_WAN_NEGATED`,
  `requested_engine_from_text()`, manifest field population.
- `local_agent/gvd_tool_router/service.py` — `execute_tool()` approval
  pass-through, Wan-fallback acknowledgement gate, engine report on planned
  and live results.
- `local_agent/gvd_tool_router/catalog_seed.py` — comment only.
- `local_agent/tools.py` — `gvd_route_shot` whitelist description mentions
  `requested_engine` and the engine annotations (string only; whitelist
  membership unchanged).
- `local_agent/test_gvd_tool_router.py` — the four `selected()` route stubs
  accept `**_route_kwargs` so the new `operator_approval=` keyword passes.
- New `local_agent/test_gvd_engine_policy.py` — 25 tests.

All edits were applied by an exact-once anchored patch script (kept outside
the tree) that refuses to write if any anchor is missing or duplicated, since
the motion-transfer agent applies its own anchored edits to the same
`schema.py` / `router.py` / `service.py` / `catalog_seed.py`
(`local_agent/runtime/motion_transfer_20260925/_edit_*.py`). Every anchor
matched once; no motion-transfer text was moved.

## 5. Tests

`python -m unittest test_gvd_engine_policy test_gvd_tool_router
test_motion_transfer_plan` — **92/92 OK** (79.6 s; 25 new + 67 existing).

New coverage, as requested:

- both MiniMax and Wan viable, Wan scoring higher on every axis → MiniMax,
  `default`, no notice;
- MiniMax `RESOURCE_BLOCKED`, Wan fits → Wan, `fallback`,
  `ENGINE_FALLBACK_WAN`, `minimax_unfit:…RESOURCE_BLOCKED`, notice;
- no MiniMax row at all → Wan, `fallback`, `minimax_absent`, notice;
- MiniMax unfit but a neutral family (LongCat) fits → the neutral row, not
  Wan;
- explicit `requested_engine="wan"` with MiniMax fitting → Wan,
  `explicit_request`, `ENGINE_EXPLICIT_WAN`, no fallback code;
- explicit Wan that cannot fit → MiniMax with
  `REQUESTED_ENGINE_UNAVAILABLE:wan`;
- neither fits → unchanged `blocked` / `NO_COMPATIBLE_TOOL` /
  `UNAVAILABLE_CAPABILITY`, engine fields None, `discovery_requested`;
- unknown engine value → `blocked`;
- `requires_operator_approval`: rejected without approval even with free
  VRAM, selected with approval, unflagged LTX wins without approval;
- planner phrasings (five positive, four negative/bare, engine-words-only →
  review, user_manifest override);
- `execute_tool`: planned DAG carries the notice; live fallback blocked with
  no `submit_stage` call; acknowledged live fallback submits; explicit Wan
  request is not gated.

## 6. Read-only behaviour against the live registry (no render)

`active.json` digest `c495262e…` has **no active MiniMax H3 row for
`execute_continuous_take`** (only `wan22_i2v_q4_high`, `wan22_i2v_q4_dual`,
`wan22_i2v_8step`; `minimax_h3_fl2va/ref2va` are still `disabled`). So with
enough free VRAM a continuous take now routes to Wan **with**
`ENGINE_FALLBACK_WAN` / `minimax_absent` and the notice, where before it
routed to Wan silently. With `requested_engine: "wan"` it reports
`ENGINE_EXPLICIT_WAN`. At the recorded 10,870 MiB free every video row is
`RESOURCE_BLOCKED` and the decision is the pre-existing `blocked`.

## Not changed / notes

- Legacy `dspy_orchestrator.py` / `batch_run_backrooms_gvd.py`: read only.
- No on-disk catalog/registry JSON, no promotion, no `apply_profile.py`.
- `execute_tool()`'s hardcoded 12,000 MiB inventory is unchanged.
- `python scripts/next_changelog_id.py` was run twice this session; it
  durably claims each id, so `CHANGELOG/.id_claims/2026-09-26c` is a stray
  claim by this session. Left in place (gaps are never refilled); the next
  caller gets `d`.
- Verification here means unit tests plus a read-only `route()` call over the
  live registry. No workflow was embedded in a render, so in this tree's
  sense the change is **not render-verified** and does not claim to be.
