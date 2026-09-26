# 2026-09-01k — Action-resolution layer (`action_resolver.py`)

## What changed

### New file: `local_agent/action_resolver.py`

A current-turn classification layer that resolves direct operator requests into
deterministic tool plans before the model generates prose. The public interface:

```python
@dataclass
class ActionPlan:
    intent: str
    steps: list[tuple[str, dict]]

def classify(
    latest_user: str,
    history: list[dict],
    cid: str,
    *,
    pending_calibration_path_fn: Callable[[list[dict], str], "str | None"],
    specialist_scope: bool,
) -> "ActionPlan | None":
```

`classify()` returns an `ActionPlan` when the request maps unambiguously to a
known safe tool, or `None` to fall through to the normal model turn.

Five intents are handled, in priority order (first match wins):

| Priority | Intent | Trigger pattern | Evidence required |
|---|---|---|---|
| 1 | `comfyui_stop` | "stop/kill/abort the render" | none — safety action |
| 2 | `jsonl_repair` | "fix it / fix the formatting error" | pending failed calibration path |
| 3 | `calibration_continue` | "continue with the approved JSON" | pending calibration path, non-render turn |
| 4 | `list_dir` | "show/list/browse … folder/files" | alias or explicit path token |
| 5 | `read_file` | "read/open/view … file" | explicit path token |

The module is deliberately independent of `agent.py` (no circular imports). The
`pending_calibration_path_fn` callable is passed in from `agent.py` rather than
imported, keeping the resolver importable and testable in isolation.

Short-name folder aliases (`"prompts folder"`, `"native prompts"`, `"the prompts"`,
`"equal shares"`) resolve to exact repo-relative paths without guessing.

### Modified: `local_agent/agent.py`

- Added `import action_resolver` after `import planner`.
- Added `_execute_plan(plan, cid, tool_context, emit) -> str` that runs each step
  through `tools.call()` (all guards preserved), observes evidence via
  `agentic_state.observe_tool()`, and formats a summary for `jsonl_repair` or
  returns the last tool result otherwise.
- In `answer()`: moved `specialist_scope` computation before the two former inline
  branches; removed the JSONL-repair block and the ComfyUI-stop block; replaced
  both with a single resolver call:

  ```python
  specialist_scope = _requests_specialist_project_context(latest_user)
  _plan = action_resolver.classify(
      latest_user, history, cid,
      pending_calibration_path_fn=_pending_failed_calibration_path,
      specialist_scope=specialist_scope,
  )
  if _plan:
      _final = _execute_plan(_plan, cid, tool_context, emit)
      if cid:
          agentic_state.finish_turn(cid, _final)
      return _final
  ```

### New file: `local_agent/test_action_resolver.py`

29 tests split across two classes:

- `ClassifyUnitTests` (23): tests `action_resolver.classify()` in isolation,
  covering all five intents, all five reported failure patterns, evidence-required
  guard (returns None without path evidence), specialist_scope restriction for
  `calibration_continue`, empty/greeting input, and folder aliases.
- `AgentAnswerIntegrationTests` (6): tests through `agent.answer()` with
  `tools.call` and `oll.chat_stream` patched; verifies the five reported failure
  patterns end-to-end and confirms ordinary questions still reach the model.

### Modified: `local_agent/server.py`

`APP_REVISION` bumped to `2026-09-01-action-resolver-r76`.

### Modified: `local_agent/START_LOCAL_AGENT_GUI.ps1`

`$ExpectedAgentRevision` updated to `'2026-09-01-action-resolver-r76'`.

---

## Regression evidence

```
python -m py_compile local_agent\agent.py local_agent\action_resolver.py
→ (no output — both compile cleanly)

python local_agent\test_action_resolver.py
→ Ran 29 tests in 0.247s — OK

python local_agent\test_native_tool_calling.py
→ Ran 57 tests in 7.668s — OK
```

All five reported failure patterns now have named regression tests:

| Reported failure | Test |
|---|---|
| "you were supposed to fix it. Why didn't you?" | `test_you_were_supposed_to_fix_it_classified_as_jsonl_repair` (unit) + `test_failure1_emphatic_fix_request_calls_repair_tool` (integration) |
| "continue with the PowerInfer project using the JSON I approved" | `test_continue_powerinfer_with_evidence_classified` + `test_failure2_continue_powerinfer_calls_calibration_not_batch` |
| `start_current_chat_render` when no H3 prompt exists | `test_start_render_returns_none` + `test_failure3_start_render_no_h3_prompts_returns_deterministic_refusal` |
| "show me the folder with the prompts" | `test_show_prompts_folder_classified_as_list_dir` + `test_failure4_show_prompts_folder_calls_list_dir` |
| "fix the formatting error" | `test_fix_formatting_error_classified_as_jsonl_repair` + `test_failure5_fix_formatting_error_calls_repair_and_validate` |

---

## What requests are now handled deterministically

- Any "stop/kill/abort the [current] [batch] render/ComfyUI" message.
- Any "fix / repair / correct / reformat it / this / file / jsonl / the formatting
  error" message when a prior turn reported a failed calibration path.
- Any "continue / proceed / use the approved JSON / calibration" message (outside
  a render-specialist turn) when a prior turn reported a calibration path.
- Any "show / list / browse / open … folder / directory / files" message when a
  known alias or explicit path token is present.
- Any "read / open / view … file" message when an explicit path token is present.

## What remains model-driven

Everything else: vague requests, multi-step planning, Equal Shares/H3 work,
image generation, web research, general questions, coding, memory, phone
scheduling, and any message that matches a trigger but lacks the required
same-chat evidence. The model still selects and calls tools on those turns
through the existing `tools=` native function-calling path.

---

No GPU, render, ComfyUI, PowerInfer, model load, or any process was started.
