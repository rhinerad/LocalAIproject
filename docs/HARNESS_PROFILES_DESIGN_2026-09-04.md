# Model-aware harness profiles — design (2026-09-04)

Scoping only. No harness code was changed for this document.
Parent analysis: `docs/FARM_EFFICIENCY_EVALUATION_2026-09-04.md` Finding 1
(sharpened). Ticket: `TODO.md` Phase 2, "Farm efficiency, ticket 2".
Routing signal this keys off: `CHANGELOG/2026-09-04i_capability_model_routing.md`
+ live verify `CHANGELOG/2026-09-04k_capability_routing_live_verify.md`.

This is the check-the-design-before-building pass. Small-model tool-selection
regressions are the known failure mode. Do not start implementation until
this design is accepted.

## 1. What this is

When `router.decide("auto", prompt=...)` sends a turn to a **CPU-served or
farm-served** model, the harness switches to a reduced tool surface and a
more directive loop. When the same `decide()` returns a **GPU-resident**
model, today's full schema and free-form hop loop stay as they are.

The switch trigger is the existing `router.Decision`. No new signal.

Two profiles:

| Profile | When | Tool surface sent to the model | Loop |
|---|---|---|---|
| `gpu` | `Decision.tier == "gpu"` (including the GPU-resident 8B fallback and the DeepSeek/Coder 14B pair) | today's `tools.schemas()` — all registered tools, `PROJECT_ONLY_TOOLS` still filtered | free-form native tool calls, current `action_resolver` intents |
| `cpu` | `Decision.tier in {"cpu", "farm"}` or `Decision.backend == "farm"` | three meta-tools (`list_tools` / `describe_tool` / `call_tool`) wrapping the same registry | same hop loop, plus a CPU-only resolver bias (below) |

`lightweight_turn` (empty schemas, tiny prompt) and PowerInfer
(`tools=None`) are unchanged third paths. They are not this ticket.

## 2. Live inventory (measured 2026-09-04, this session)

`local_agent/tools.py::TOOLS` (line 1936) and `schemas()` (line 2679):

| Quantity | Value |
|---|---|
| Registered tools | **67** (eval doc said ~65; live count is 67) |
| `schemas()` | 67 |
| `schemas(include_project=False)` | 54 (`PROJECT_ONLY_TOOLS` = 13) |
| Schema JSON | 40,511 chars / 39.6 KB |
| Description text only | 13,790 chars |

Long descriptions that dominate the budget (unchanged observation from the
eval): `plan_story_image`, `render_story_image`, `schedule_phone_messages`,
plus the seven `comfy_*` wrappers.

Precedent, read from upstream not paraphrased: comfyui-mcp `--compact` /
`COMFYUI_MCP_TOOL_MODE=compact` registers exactly three meta-tools, keeps
the real catalog behind them, and is documented as the right trade for
small local models. Default remains the full surface. Forgiving quirks:
`args` may be an object **or** a JSON string; aliases `tool_name` /
`arguments` accepted; validation errors return the expected schema.
Source: https://comfyui-mcp.artokun.io/docs/local-llms.md

`MAX_TOOL_HOPS = 6` (counts model turns). A naive `list → describe → call`
chain spends 3 of those 6 before any real work. That hop budget is why the
meta-tool shape has to be slightly richer than names-only (see §5).

## 3. Switch trigger — read `Decision`, do not invent a flag

`router.Decision` already carries everything needed
(`router.py` ~406–413):

```text
tier:    "gpu" | "cpu" | "farm"
backend: "ollama" | "powerinfer" | "farm"   (default "ollama")
host, model, gpu_busy, reason, detail
```

Proposed helper (new, tiny, in `tools.py` or a new `harness_profile.py` —
prefer `tools.py` so schema + profile stay in one place):

```python
def profile_for(decision) -> str:
    """'cpu' compact or 'gpu' full. PowerInfer callers never reach this."""
    backend = getattr(decision, "backend", "ollama")
    tier = getattr(decision, "tier", "gpu")
    if backend == "farm" or tier in ("cpu", "farm"):
        return "cpu"
    return "gpu"
```

Mapped onto today's live `decide("auto")` outcomes (2026-09-04k):

| Live decision | Profile |
|---|---|
| farm / Qwythos (`CAP_TOOL`, farm reachable) | `cpu` |
| gpu / DeepSeek or Josiefied Coder (`CAP_LOGIC` / `CAP_CODE`, GPU free) | `gpu` |
| cpu / Huihui 8B (`CAP_CODE`/`CAP_LOGIC` refused because :8188 / thermal / queue_owner) | `cpu` |
| gpu / Huihui 14B (legacy auto, no capability override) | `gpu` |
| gpu / Huihui 8B GPU-resident fallback (`fallback_after_primary_failure`) | `gpu` — still GPU-resident, full schema |
| prefer=`cpu` (operator or pending `gpu_gate`) | `cpu` |
| PowerInfer | not this ticket (`stream_tools = None` already) |

Do **not** key off `classify_capability() == CAP_TOOL` alone. An unpinned
tool turn with the farm down falls through to the ordinary GPU/CPU auto
path; if the GPU is free that is a 14B with the full schema, which is
correct.

### 3.1 When in `answer()` the profile is chosen

Today `tool_schemas = tools.schemas(...)` is built **once**, before the hop
loop (`agent.py` ~1287), and `router.decide()` runs **inside** every hop
(~1522), including a `skip_farm=True` retry if Qwythos returns None
(~1537). `gpu_gate` can also force `effective_prefer = "cpu"` on that hop
(~1511).

So the profile can change hop-to-hop. That is intended:

- Hop 0 farm (compact) → Qwythos returns `call_tool` → host executes it
  locally via `run_one()` → hop 1 re-decides. If hop 1 is GPU 14B, send
  the full schema for that hop.
- Hop 0 GPU 14B, then a render claims the card, hop 1 CPU 8B: switch to
  compact for hop 1.

Implementation rule: **recompute `tool_schemas` from that hop's Decision
after farm-fallback, before `chat_stream` / `try_qwythos_on_farm`.** Do
not freeze the profile at the start of `answer()`. The pre-loop
`tool_schemas` used for `estimate_context_tokens` can stay full (a
slightly pessimistic token estimate is safe).

`try_qwythos_on_farm(msgs, tools=tool_schemas)` already forwards whatever
list the host built (`farm_offload.py` ~264–286;
`worker_farm/tasks.py::_qwythos_evaluate` passes `envelope["tools"]`
straight to `ollama_client.chat`). No Mac-side schema logic. Compact vs
full is a host decision.

## 4. Meta-tool wrapper — concrete API

Do **not** add `list_tools` / `describe_tool` / `call_tool` to `TOOLS`.
`test_all_schemas_and_enums` asserts `len(tools.TOOLS) == len(schemas())`
and `set(tools.TOOLS) == schema names`. Default `schemas()` must keep
returning the 67-tool GPU surface.

Virtual tools, dispatched inside `tools.call` before the `name not in
TOOLS` error (`tools.py` ~2714):

```text
META_TOOL_NAMES = ("list_tools", "describe_tool", "call_tool")
```

### `schemas(*, include_project=True, profile="gpu")`

- `profile="gpu"` (default): identical to today's list. Never includes
  the three meta names.
- `profile="cpu"`: exactly three OpenAI-style function schemas, still
  honouring `include_project` for what the catalog *contains*, not for
  which meta-tools are advertised.

CPU schemas (parameter names match comfyui-mcp so Qwythos / 8B can reuse
the published compact convention):

**`list_tools`**

```json
{
  "type": "object",
  "properties": {
    "category": {"type": "string", "description": "Optional group filter"},
    "search":   {"type": "string", "description": "Optional substring over name+summary"}
  }
}
```

Return a token-light catalog: name + one-line summary, grouped. One-line
summary = first sentence of the existing `TOOLS` description, truncated
to ~160 chars. Groups (stable, derived from the comment headers already
in `TOOLS`):

```text
project, memory, batch, comfy, file, web, story_image, storyboard,
sonic_pi, sensory
```

`PROJECT_ONLY_TOOLS` omitted when `include_project=False`. Same visibility
as GPU `schemas()` — do not also filter by phone `ToolContext.permits()`.
GPU models already *see* tools they cannot call; compact must not become
stricter, or tests/behavior diverge.

**`describe_tool`**

```json
{
  "type": "object",
  "properties": {
    "name":  {"type": "string"},
    "names": {"type": "array", "items": {"type": "string"}}
  }
}
```

Accept `name` or `names` (cap 3). Return that tool's full description +
`_SCHEMAS` JSON. Unknown / project-only-hidden names: `ERROR:` with the
list of visible names, not an exception.

Cap-3 exists because `MAX_TOOL_HOPS = 6`. One describe hop can arm three
`call_tool`s.

**`call_tool`**

```json
{
  "type": "object",
  "required": ["name"],
  "properties": {
    "name":      {"type": "string"},
    "tool_name": {"type": "string"},
    "args":      {"description": "object or JSON string"},
    "arguments": {"description": "alias of args"}
  }
}
```

Resolution order: `name` or `tool_name`; `args` or `arguments`; if the
value is a string, `json.loads` it. Then **one** call:

```python
return tools.call(inner_name, inner_args, context=context)
```

No second permission path. `tools.call` already checks existence,
`ToolContext.permits()`, trusted identity injection, `remote_security.audit_tool()`,
and converts exceptions to `ERROR:`. `call_tool` of a hidden project-only
name still hits that chokepoint and fails the same way a GPU model calling
it would.

### 4.1 Hop-loop unwrap

`agent.py::run_one()` (~1729) must unwrap `call_tool` *before* the
specialist / batch / `__conversation_id` guards, so those guards see the
inner name:

```text
if name == "call_tool":
    inner_name, inner_args = tools.parse_call_tool_args(args)
    # then run the existing run_one body with inner_name, inner_args
```

If we only unwrap inside `tools.call`, `run_one` would skip the
`start_current_chat_render` conversation-id bind and the
`_SPECIALIST_PROJECT_TOOLS` / `_BATCH_RENDER_TOOLS` blocks — those key off
the outer name `call_tool`. That is a real hole. Unwrap in `run_one`.

Direct real tool names remain legal on the CPU profile. Compact *advertises*
three tools; the dispatcher still accepts the 67. Reasons:

1. Qwythos / 8B may emit a remembered real name instead of `call_tool`.
2. Existing `test_native_tool_calling.py` tests inject real names via
   mocked `chat_stream` while `_Route` defaults to `tier="cpu"` (see §8).
3. `action_resolver` / `_execute_plan` already call real names.

`list_tools` and `describe_tool` are pure reads → add to
`CONCURRENCY_SAFE_TOOLS`. `call_tool` is **not** concurrency-safe as a
name; after unwrap, use the inner name's membership.

Stuck-call guard (`recent_tool_attempts`): hash the *inner* `(name, args)`
for `call_tool`, otherwise the model can loop `call_tool` with a changing
wrapper and a fixed inner call, or the opposite.

Legacy `TOOL: name {json}` fallback stays. On the CPU profile it is a
feature (small models that cannot native-call still have a path).

## 5. CPU prompt profile

Today `system_prompt()` (~569) is built once before routing and is the
verbose GPU prompt (`CONVERSATION_RULES` plus optional coding/project
prefixes). After the hop's Decision, if profile is `cpu` and this is not
a `lightweight_turn`, replace `msgs[0]` (the system message) with a short
directive. Do not rebuild memory / project prefixes on every hop unless
the profile actually flipped.

CPU system rules, in this order, short:

1. You are a local desktop assistant. Reply in English.
2. Tools: only `list_tools`, `describe_tool`, `call_tool` are in your
   schema. To use a real tool: `call_tool` with `name` + `args`. You may
   skip `list_tools` if you already know the name; call `describe_tool`
   before the first `call_tool` of a name you have not used this turn.
3. Do not invent tool names. If `call_tool` returns `ERROR`, read it and
   either describe or pick a different name. Do not tell the operator to
   run a command you can run.
4. Never claim an action happened without a tool result this turn.
5. Never mention tool names to the operator.
6. Keep the existing specialist-scope boundary paragraph when it is
   already inserted.

Do **not** paste `CONVERSATION_RULES`'s per-tool essays (`start_batch_render`,
Sonic Pi, storyboard, PowerInfer JSONL, …) into the CPU prompt. Those
essays exist to steer a 14B that can see 67 schemas. On compact they
recreate the token cost we just removed, and they name tools the model
cannot see in its schema.

Coding-mode (`router.is_coding_model(model)`): Coder-14B is GPU-profile
only. CPU fallback of a code turn (Comfy :8188 refused the swap) still
gets the compact CPU prompt, **plus** the existing four-step `run_code`
debug loop from `CODING_RULES`, because that loop is how the 8B is
supposed to behave. Do not send the rest of `CODING_RULES`'s tool-name
catalog.

## 6. Leaning harder on `action_resolver.py`

`classify()` already runs for every non-lightweight turn, before the
model, on both GPU and CPU (`agent.py` ~1335). Five intents, first match
wins: `comfyui_stop`, `jsonl_repair`, `calibration_continue`, `list_dir`,
`read_file`. All guards still go through `tools.call`.

That global pre-resolution stays. GPU does not lose it.

"Lean harder" on the CPU profile is **additive and gated**, not a rewrite
of `classify()`'s current five. Two layers, in order:

### 6.1 Layer A — v1, no new intents (ship with the meta-tool PR)

After `classify()` returns `None`, if the hop profile is `cpu` **and**
`_ACTION_REQUEST_RE` matches the user text, inject one system sentence
before the model runs:

> This is an action request. You have not used a tool yet. Call
> `list_tools` or `call_tool` this turn. Do not answer with instructions
> for the operator.

This is the existing execution-first retry (`agent.py` ~1659) pulled
*forward* so the CPU model does not burn hop 0 on prose. The current
retry still exists as a backstop.

Do **not** expand regex intents in the same PR as the meta-tool wrapper.
The architecture audit (`docs/design_notes/architecture_audit_2026-08-27.md`
§1) already named "patch the description, add a regex escape hatch"
as the thing that does not scale. Combining a new classifier with a new
schema surface in one change makes a tool-selection regression
undiagnosable.

### 6.2 Layer B — follow-up PR, extra CPU-only intents, each with a test

`classify(..., profile="gpu"|"cpu")`. Extra branches run only when
`profile=="cpu"`, after the existing five, still evidence-or-path
required, still `None` on ambiguity:

| Intent | Trigger (high precision) | Plan |
|---|---|---|
| `web_search` | explicit "search the web / look up / google" and no URL | `web_search` |
| `capabilities` | "what can you see/hear/transcribe" / "what tools do you have" | `capabilities` |
| `list_memory` | "what do you remember" / "list remembered facts" | `list_memory` |

Do **not** add `write_file`, `run_code`, `start_batch_render`, or
`render_story_image` as CPU-only regexes. Those are the cases the
resolver was extracted to *stop* guessing.

Chicken-and-egg: `classify()` currently runs before `decide()`. For
Layer B, compute profile from a `decide()` call *before* `classify()`,
and reuse that Decision on hop 0 unless `gpu_gate` / farm-fallback
changes it. `ensure_gpu_evicted` on that early call must match hop 0
(`True` for a real turn). Status polling stays `ensure_gpu_evicted=False`.

Layer A does not need the early `decide()`: the execution-first sentence
can wait until hop 0's Decision, which is the first model call anyway.

## 7. What this must not do

- Must not change default `tools.schemas()` (GPU / direct callers /
  `test_all_schemas_and_enums`).
- Must not register meta-tools in `TOOLS`.
- Must not bypass `tools.call` for inner tools.
- Must not filter the compact catalog by phone identity more strictly
  than GPU schemas.
- Must not send compact schemas to a GPU-resident 8B fallback.
- Must not send full schemas to Qwythos "because 9B is bigger than 8B".
  Farm is the compact path; that is the point of the ticket.
- Must not auto-`git revert` or otherwise implement Finding 2.
- Must not offload `run_code` (Finding 3).
- Must not bump Mac Celery concurrency (ticket 1, separate).

## 8. Regression surface — exact tests, live baseline

The 2026-09-04 eval said 57 + 29. That count is **stale**. Live this
session, **before any harness change**:

```text
python local_agent/test_native_tool_calling.py -v
  Ran 65 tests in 5.994s
  OK

python local_agent/test_action_resolver.py -v
  Ran 29 tests in 0.127s
  OK
```

Host: DuranGamingPC. Interpreter: the session `python`. No GPU load, no
Ollama call, no farm submit, no ComfyUI start. These suites are mocked
where they touch those boundaries.

After implementation, **both suites must still be 65/65 and 29/29**
before any new test is allowed to raise the counts. New tests are
additive.

### 8.1 `test_native_tool_calling.py` — all 65, why they matter

These are not "run the file" in the abstract. The compact wrapper can
break specific ones. Grouped by failure mode:

**Schema contract (must keep GPU default identical)**

- `test_all_schemas_and_enums` — `len(TOOLS)==len(schemas())`, enums on
  `run_build` / `propose_gpu` / `read_doc`, general chat still sees
  `validate_powerinfer_calibration`.
- `test_chat_passes_tools` — `oll.chat(..., tools=schemas())` forwards
  the list by identity. Default `schemas()` must remain the full list.

**Hop loop still executes real names (compact must not require
`call_tool` for dispatch)**

- `test_multiple_calls_one_hop_and_named_results`
- `test_concurrency_safe_tools_run_in_parallel_within_one_hop`
- `test_unsafe_tool_stays_sequential_even_alongside_a_safe_one`
- `test_parallel_tool_results_keep_original_call_order_in_the_transcript`
- `test_read_only_followup_reuses_one_gpu_snapshot`
- `test_oversized_tool_result_is_an_artifact_pointer_in_next_hop`
- `test_read_artifact_pages_through_a_pruned_tool_result`
- `test_legacy_fallback_logs_and_runs`
- `test_malformed_legacy_json_never_runs_tool`

**Stuck / hop-limit (inner-name hashing for `call_tool`)**

- `test_repeated_identical_failing_tool_call_stops_the_loop_early`
- `test_failing_tool_call_with_varying_arguments_is_not_treated_as_stuck`
- `test_failing_tool_call_that_then_succeeds_is_not_treated_as_stuck`
- `test_varying_exception_args_sig_hits_max_tool_hops_instead_of_hanging`

**Exception paths (`run_one` unwrap must not re-raise)**

- `test_main_thread_tool_exception_in_mixed_hop_is_caught_not_raised`
- `test_main_thread_tool_exception_in_single_tool_hop_is_caught_not_raised`
- `test_execute_plan_tool_exception_is_caught_not_raised`
- `test_execute_plan_second_step_still_runs_after_first_raises`
- `test_url_prefetch_tool_exception_is_caught_not_raised`
- `test_start_current_chat_render_shortcut_exception_is_caught_not_raised`
- `test_sonic_pi_ensure_exception_is_caught_not_raised`

**Action-resolver integration (CPU extra-intent work must not disturb)**

- `test_fix_it_reuses_failed_calibration_path_and_revalidates_it`
- `test_fix_it_recovers_path_from_saved_same_chat_tool_evidence`
- `test_fix_it_recovers_path_from_truncated_saved_tool_evidence`

**Deterministic shortcuts / guards that sit beside the model loop**

- `test_exact_start_render_bypasses_model_folder_guessing`
- `test_missing_current_chat_prompt_set_never_falls_back_to_other_folder`
- `test_vague_render_request_cannot_authorize_batch_folder_tool`
- `test_powerinfer_json_request_cannot_trigger_stale_batch_plan`
- `test_stale_h3_render_reply_is_discarded_on_unrelated_turn`
- `test_stale_h3_render_tool_is_blocked_on_unrelated_turn`
- `test_access_bypass_*` (3)
- `test_unverified_action_claim_is_not_returned_as_completed_work`
- `test_future_intent_is_not_treated_as_a_false_completion_claim`
- `test_action_request_retries_once_for_tool_use_before_returning_instructions`
  — Layer A (§6.1) changes when this retry fires; the test must still
  pass (one retry, then prose). If Layer A consumes the retry, update
  this test in the same PR, do not silently drop the assertion.

**Hallucinated completion / write integrity**

- `test_plan_story_image_hallucinated_completion_is_corrected`
- `test_render_story_image_hallucinated_completion_before_job_finishes_is_corrected`
- `test_story_image_job_status_still_running_hallucination_is_corrected`
- `test_story_image_job_status_complete_is_not_touched`
- `test_real_completion_claim_after_a_genuine_write_is_not_touched`
- `test_failed_file_write_cannot_be_reported_as_created`

**Tool registry / guards (dispatch chokepoint)**

- `test_guard_rails`
- `test_propose_file_diff_is_registered_non_destructive_and_guarded`
- `test_hex_editor_is_exact_approved_and_protects_evidence`
- `test_powerinfer_calibration_intake_is_cpu_only_and_does_not_unlock_work`
- `test_repair_jsonl_format_converts_only_a_top_level_object_array`
- `test_batch_tools_refuse_documentation_placeholder`
- `test_start_batch_render_is_fixed_and_preflighted`
- `test_start_batch_render_is_remote_default_deny`
- `test_explicitly_granted_phone_render_uses_authenticated_capability`
- `test_granted_phone_render_still_obeys_global_gpu_block`
- `test_current_chat_render_preserves_trusted_phone_identity`
- `test_current_chat_render_id_is_server_bound`
- `test_gpu_permission_cards_do_not_expire_and_repeated_decision_is_safe`
- `test_explicit_chat_text_edit_does_not_need_second_sidebar_approval`

**Routing / runtime that must stay GPU-profile when Decision is gpu**

- `test_primary_oom_retries_once_on_paired_fallback` — fallback Decision
  is GPU 8B → full schema, not compact.
- `test_plain_text_chat_never_starts_vision_runtime`
- `test_thinking_markup_is_never_visible`
- `test_stop_path`
- `test_persistence_attachment_shape_and_regenerate_primitive`
- `test_ad_hoc_turn_never_searches_prior_chats_without_identity`
- `test_chat_passes_explicit_keep_alive`
- `test_chat_passes_json_schema_format`

### 8.2 `test_action_resolver.py` — all 29

22 `ClassifyUnitTests` (direct `classify()`, no model) + 7
`AgentAnswerIntegrationTests`.

Classify unit tests prove the five intents and the `None` fallthrough
(greetings, ordinary questions, empty, start-render, missing path /
missing evidence, specialist-scope block on calibration). Integration
tests prove `_execute_plan` still goes through `tools.call` (including
the protected-file guard) and that ordinary questions still hit the
model.

Layer A must not make `test_ordinary_question_still_uses_model` start
calling `list_tools`. `_ACTION_REQUEST_RE` is the gate.

Layer B extra intents each need a new classify unit + an integration
test, same shape as failure 4/5. Not in the v1 PR.

### 8.3 Hazard: `_Route` defaults to `tier="cpu"`

`test_native_tool_calling.py::_Route.__init__` (`tier="cpu"`, no
`backend`). `test_action_resolver.py::_make_route()` is the same
(`tier="cpu", backend="ollama"`). Almost every `agent.answer()` test
patches `router.decide` with that.

Once `answer()` keys schemas off `Decision.tier`, **those tests will
exercise the compact profile**, not the GPU one they were written under.
They should still pass if §4.1 (direct names still dispatch) holds.
They will **not** prove the GPU profile still sends 67 tools.

Required new tests in the v1 PR (additive, after the 65+29 still pass):

1. `test_schemas_default_is_full_registry` — already covered by
   `test_all_schemas_and_enums`; keep it.
2. `test_schemas_cpu_profile_is_exactly_three_meta_tools` — names
   `{list_tools, describe_tool, call_tool}`, none of the 67.
3. `test_gpu_decision_sends_full_schemas_to_chat_stream` — patch
   `decide` with `tier="gpu"` and spy `chat_stream(..., tools=)`.
4. `test_cpu_decision_sends_meta_schemas_to_chat_stream` — same spy,
   `tier="cpu"`.
5. `test_farm_decision_sends_meta_schemas_to_qwythos` — spy
   `farm_offload.try_qwythos_on_farm(..., tools=)`.
6. `test_call_tool_unwraps_and_hits_tools_call` — mocked inner
   `read_file`; assert `tools.call("read_file", ...)`.
7. `test_call_tool_does_not_bypass_protected_file_guard`.
8. `test_call_tool_specialist_guard_sees_inner_name` — compact must
   not launder `batch_plan` past `_BATCH_RENDER_TOOLS`.
9. `test_list_tools_omits_project_only_when_include_project_false`.
10. `test_describe_tool_unknown_name_is_error_not_raise`.
11. `test_primary_oom_fallback_stays_gpu_profile` — extend or sibling
    of the existing OOM test; spy tools= on the second attempt.

### 8.4 Adjacent suites, not this ticket's gate, but re-run if
`router.py` / `farm_offload.py` are touched

The v1 PR should **not** need to touch those files if profile_for()
lives in `tools.py` / `agent.py`. If it does:

- `test_capability_routing.py` (16, 2026-09-04i)
- `test_router_switching.py` (42)
- `test_farm_offload.py` (44)

Do not treat them as the tool-selection gate. They do not exercise
`schemas()` or `action_resolver`.

## 9. Suggested implementation order (after this design is accepted)

One PR for v1. Do not mix Layer B.

1. Keep `schemas()` default identical. Add `profile=` and the three
   virtual handlers. Unit-test 2, 6, 7, 9, 10 from §8.3 first — they
   do not need `agent.py`.
2. `run_one` unwrap + concurrency + stuck-guard inner-name hashing.
   Tests 6–8, 11.
3. Hop-loop: after Decision (and farm fallback), set
   `tool_schemas = tools.schemas(include_project=..., profile=profile_for(route))`.
   CPU system-prompt swap. Tests 3–5.
4. Layer A execution-first sentence on CPU action requests. Re-run
   `test_action_request_retries_once_*` and
   `test_ordinary_question_still_uses_model`.
5. Re-run the full 65 + 29. Then add the new tests. Changelog. Stop.

Rollback: if Qwythos live tool-selection is worse with pure compact than
with the 67-tool list, the first mitigation is **not** "add more regex".
It is advertising a small `CORE_DIRECT_TOOLS` allowlist *alongside* the
three meta-tools (candidate: `list_dir`, `read_file`, `web_search`,
`fetch_url`, `capabilities`, `run_code` — the high-frequency general
tools). That hybrid is an explicit v1.1, not v1. comfyui-mcp itself
stayed at pure 3.

## 10. Open questions for the operator (do not guess in v1)

1. Accept pure 3-meta-tool compact for v1, with CORE_DIRECT as the
   documented rollback? (Recommended: yes.)
2. Layer B extra intents in a second PR? (Recommended: yes, after a
   live Qwythos turn using compact, not before.)
3. Per-hop profile flip vs freeze-for-the-turn? (Recommended: per-hop,
   §3.1. Freeze would leave a GPU 14B stuck on compact after a farm
   hop 0.)

## 11. Baseline receipt

```text
date:            2026-09-04
tree:            COMFYUI_STORY_HANDOFF_2026-08-09
command:         python local_agent/test_native_tool_calling.py -v
result:          Ran 65 tests in 5.994s  OK
command:         python local_agent/test_action_resolver.py -v
result:          Ran 29 tests in 0.127s  OK
TOOLS live:      67
schemas() JSON:  40511 chars
code changed:    none (this file + changelog + TODO pointer only)
```

After the v1 PR, re-run those two commands and paste the new times next
to this receipt. A pass count below 65 or 29 is a stop, not a "mostly
green" ship.
