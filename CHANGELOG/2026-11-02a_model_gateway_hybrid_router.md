# 2026-11-02a — `model_gateway/`: local-first hybrid router (Ollama tiers + optional Anthropic tier) built as a fourth `Decision.backend`, no new port

Operator brief (task handoff "Design a Unified Model Gateway & Hybrid Router"):
audit how LLM calls are wired, compare a LiteLLM proxy with native middleware,
then prototype. Phase 1/2 were reviewed and the operator chose **Option B**
(native, inside the existing router seam) with six decisions recorded below.
Id claimed once with `scripts/next_changelog_id.py`. Branch
`claude/jolly-dirac-9impbq` was reset onto `claude/zealous-johnson-g4xoz1`
(`7fddcab`) because `main` and the designated branch held only a README.

## Operator decisions (2026-11-02)

1. Build on `zealous-johnson`, push to `jolly-dirac`; keep routing logic in
   `model_gateway/` with minimal hooks in `router.py`.
2. Install the official `anthropic` SDK (~15 MB) — the one new dependency.
   Provider must also accept a custom local base URL for proxy testing.
3. `claude-opus-5-5` heavy tier; `claude-sonnet-5-5` for busy-GPU turns.
4. Compactor, memory extractor, planner stay strictly local. Cloud only for
   unpinned heavy-logic turns, unpinned busy-GPU turns, explicit pins.
5. Amend `local_agent/README.md` to a "Local-First Hybrid Architecture" rule.
6. On cloud failure, automatic local fallback with a note surfaced on that turn.

## 1. Audit findings that shaped the design (read-only, scratch worktree)

- Two Ollama servers: GPU 11434, CPU-only 11435 (`num_gpu 0`, 4 threads).
  Compaction, memory extraction and plan JSON already pin 11435 with
  `keep_alive:"0"` — the "keep these local" goal was a guardrail, not work.
- `router.decide()` already classifies turns (`difficulty.needs_escalation` →
  `CAP_LOGIC`) and `Decision.backend` already abstracts `ollama | powerinfer |
  farm`; `ollama_client` already branches on host for PowerInfer.
- VRAM loads happen only when a body reaches `11434/api/chat`; every other
  VRAM-touching call is a `keep_alive:0` eviction. So a cloud Decision
  returned before `prepare_gpu_model` / `_finish_gpu_ollama` and never handed
  to an Ollama request cannot collide with ComfyUI.
- Tool schemas are OpenAI-shaped and clean (85 tools; only `enum`/`minItems`).
  The one real translation problem: Ollama tool calls carry no id and the
  agent appends each tool result as its own `role:"tool"` message.
- Standing rule "No cloud AI accounts or cloud model calls"
  (`local_agent/README.md:142`) conflicted with the task → decision 5.
- LiteLLM rejected: it speaks OpenAI chat-completions, so `ollama_client.py`
  would have to be rewritten and `num_gpu` / `num_ctx` / `keep_alive` / `think`
  would move from per-turn router control into YAML. Goal 2 (CLI tooling on
  local models) needs no gateway at all: Ollama ≥ 0.14 serves `/v1/messages`.

## 2. What was built

`model_gateway/` (new, stdlib except the adapter's lazy SDK import):
`config.py` (env → `GatewayConfig`, tier aliases, non-overriding
`model_gateway/.env` loader), `policy.py` (pure `choose_cloud_tier`),
`translate.py` (system lift; tool schema rename; deterministic tool-use id
minting; N `role:tool` → one user message of `tool_result` blocks; raw-block
replay for the turn awaiting results; `format` → `output_config.format`;
usage → Ollama telemetry keys), `adapters/anthropic_backend.py` (official SDK,
`messages.stream`, typed-error → `CloudUnavailable(kind)`, one retry without
cached thinking blocks on a 400 naming them, custom `base_url` support),
`adapters/base.py` + registry, `dispatch.py` (host prefix `anthropic://` →
adapter; fallback bookkeeping; `status_snapshot()`), `events.py`,
`preflight.py` + `start_gateway.ps1/.sh` (read-only preflight, prints the
Claude Code env block), `test_gateway.py` (live A/B/C), four offline test
files, `env.example`, `requirements.txt`, `README.md`.

Hooks (kept small, each marked in-source):

- `local_agent/router.py`: `Decision.backend` comment + `options()` branch for
  `"anthropic"`; `_gateway()` lazy import (repo root on `sys.path`);
  `_maybe_cloud_decision()` called once in `decide()` after the PowerInfer /
  GPU-only pin checks and before farm/GPU selection (busy GPU → the same
  `evict_gpu_residents()` yield the CPU path performs); new keyword
  `decide(..., allow_cloud=True)`; `fallback_after_primary_failure()` now
  handles `backend == "anthropic"` via `_cloud_fallback_decision()` (local
  re-decide with `allow_cloud=False`, `detail["fallback_note"]`); picker rows
  from `model_gateway.picker_entries()` in `chat_models()`; `status()` gains
  `"model_gateway"`.
- `local_agent/ollama_client.py`: `_is_cloud_host()` + `_cloud_chat_stream()`;
  branches at the top of `chat()` and `chat_stream()` mirroring the PowerInfer
  branch; gateway failures re-raised as `OllamaModelFailure` with
  `gateway_kind` so the agent's existing single retry performs the fallback.
- `local_agent/agent.py`: the fallback note now reads `detail["fallback_note"]`
  (one line; the 14B→8B wording is the default).
- `local_agent/planner.py`: `router.decide(prefer, model=model, allow_cloud=False)`.
- `local_agent/README.md`: the no-cloud paragraph replaced by the local-first
  hybrid rule (decision 5).

Nothing in `context_compactor.py`, `memory_extractor.py`, ComfyUI workflows,
`.env`, or any render path was touched. `.env` is git-ignored and was never read;
`model_gateway/.env.example` is named `env.example` because the repo's Claude
Code deny rule covers `.env.*`.

## 3. Evidence

Offline (this Linux session, Python 3.13, anthropic 2.4.0 over
`httpx2.MockTransport`; no network, no key):

    python -m unittest model_gateway.test_translate model_gateway.test_policy \
        model_gateway.test_adapter_mock model_gateway.test_router_hooks
    Ran 61 tests … OK

Covered: schema/tool/id/result translation; policy matrix (logic→heavy,
busy tool/code→fast, idle tool→local, image/creative→local, prefer=cpu→local,
no-prompt→local, pins, refusals when disabled/no key, `allow_cloud=False`);
real SDK SSE parsing incl. `tool_use` accumulation, refusal, connection error,
401/429/503/404 kinds, thinking-400 retry, cooperative stop, custom base URL;
router hooks: cloud Decision with `prepare_gpu_model` never called, busy-GPU
cloud route calls `evict_gpu_residents` once, status poll does not evict,
cloud-disabled keeps legacy routing, planner passes `allow_cloud=False`,
fallback Decision carries the note, picker rows only when enabled, status has
no key leak, `ollama_client` cloud branch yields `str`/`ToolCall`/`StreamEnd`
and never opens a local HTTP connection.

End-to-end through the real stack (no mocks inside the tree): a throwaway
`/v1/messages` SSE server on `127.0.0.1:4567` (scratch, not committed) with
`MODEL_GATEWAY_CLOUD=1 MODEL_GATEWAY_BASE_URL=http://127.0.0.1:4567`:

    python model_gateway/test_gateway.py --skip-local
    [PASS] B decide picks anthropic: claude-opus-5-5 (tier-cloud-heavy)
    [PASS] B cloud stream: claude-opus-5-5 0.9s in=40 out=8 stop=end_turn
    [PASS] B no /api/chat to GPU host: []
    [PASS] B GPU /api/ps unchanged
    [PASS] C cloud tool call: get_weather({"city": "Lisbon", "unit": "celsius"})
    [PASS] C cloud json schema: {"goal": …, "steps": […], "needs_operator_decision": false}
    summary: OK (6 pass, 0 fail, 0 skip)

That exercises `router.decide` → `ollama_client.chat_stream` →
`model_gateway.dispatch` → `anthropic` SDK → HTTP, and the GPU-host guard.

Existing suites, modified tree vs untouched baseline — identical results:
`test_router_switching`, `test_router_status_busy`, `test_router_comfy_timeshare`,
`test_capability_routing`, `test_context_compactor`, `test_auto_farm_routing`
(172 run; the same 4 pre-existing failures on both trees:
`test_coding_mode_selects_coding_model_when_gpu_idle`,
`test_unknown_coding_model_falls_back_cleanly`,
`test_huihui_names_only_server_exe_8080_no_free`,
`test_powerinfer_pin_names_only_server_exe_already_claimed` — Windows-path /
PowerInfer-process assumptions, not touched here); `test_ollama_chat_telemetry`
19 OK, `test_ollama_context_options` 1 OK, `test_planner` 3 OK,
`test_memory_extractor` 3 OK, `test_compaction_prefetch` 38 OK,
`test_agent_timeshare_gpu_gate` 5 OK.

## 4. Unverified

- **No live cloud call was made.** `test_gateway.py` checks B/C-cloud need the
  workstation, `MODEL_GATEWAY_CLOUD=1` and a real key; the `--cloud-check`
  preflight sends one ~8-token request. Not run from this session (no key, no
  Ollama). The SSE shapes the mock replays follow the SDK's own types, but a
  real `claude-opus-5-5` / `claude-sonnet-5-5` round trip is still owed.
- Not run on Windows / the GUI. `START_LOCAL_AGENT_GUI.ps1` is unchanged; the
  picker shows `cloud-heavy` / `cloud-fast` only when the switch is on.
- Prompt-cache hit rates with the agent's volatile system prompt (memory
  block) are unmeasured; `telemetry["gateway"]["cache_read_input_tokens"]` is
  where to look.
- Vision turns are translated but deliberately never routed to the cloud.
