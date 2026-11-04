# model_gateway — plan-only cloud assist for the local agent

**The cloud writes plans only; the local model executes.** The gateway never
answers a turn and never calls a tool. For a heavy prompt it asks a cloud
planning model (default `claude-opus-5-5`) for a numbered text plan, and the
local Ollama model runs the whole turn with that plan in context. With
`MODEL_GATEWAY_CLOUD` unset nothing ever leaves the box and every turn routes
exactly as before.

Second iteration of the 2026-11-02 prototype (`CHANGELOG/2026-11-02a`): the
earlier cloud *answer* tiers (`tier-cloud-heavy` / `tier-cloud-fast`, picker
pins, cloud dispatch in `ollama_client`) are removed. See
`CHANGELOG/2026-11-04a` for the change and its evidence.

## The picture

`router.decide()` is still the taxi dispatcher in front of one parking spot
(the 16 GB of VRAM) and still picks the GPU cab (`127.0.0.1:11434`) or the CPU
cab (`127.0.0.1:11435`). The cloud is now a dispatcher's phone-a-friend: for a
hard fare it rings the planning model, writes the route it suggests on a
sticky note, and hands that note to the local cab. The friend never drives.

```
agent.py ──► router.decide(prompt) ──► local Decision (gpu | cpu | farm), unchanged
                 │   gpu_busy() probes (read-only)
                 │   classify_capability() → logic?  ──► detail["needs_cloud_plan"] = True
                 ▼
agent.py: if needs_cloud_plan → model_gateway.request_plan(prompt, summary, tool_names)
                 │                         one non-streaming call, tools=None, ≤1500 tokens
                 ▼
     msgs.insert(1, system: "Plan from planning model (follow, adapt if a step fails) …")
                 ▼
     local Ollama model executes the turn (tools, answers, everything) as before
```

## When a plan is requested

| condition | source |
|---|---|
| `MODEL_GATEWAY_CLOUD=1` and a credential is present | `config.py` |
| the turn has a prompt (interactive), `prefer != "cpu"` | `policy.wants_cloud_plan` |
| `classify_capability(prompt) == "logic"` (`difficulty.needs_escalation`) | `router.py` |
| the caller did not pass `allow_cloud=False` (planner, helpers never do) | `router.decide` |

Pinned local models still qualify (planning is additive). Tool, code, image
and creative turns never ask for a plan. Busy-GPU turns are routed to the CPU
tier exactly as before; the plan flag does not change that.

## What the cloud sees and returns

* System prompt: *"Return a numbered step-by-step plan for a local agent with
  these tools: &lt;names&gt;. Do not perform the task. No code longer than
  needed to specify a step."*
* User content: the operator prompt (≤12k chars) plus a compact summary made
  only of the assistant's own earlier replies (≤2k chars). No system prompt,
  no tool results, no attachments, no inlined file contents beyond what the
  operator prompt already holds.
* `tools=None`, no `tool_choice`, `max_tokens` = `MODEL_GATEWAY_PLAN_MAX_TOKENS`
  (default 1500), effort `MODEL_GATEWAY_PLAN_EFFORT` (default `high`).
* Returns the text, or `None` on any failure (`offline`, `timeout`, `auth`,
  `rate_limit`, `server`, `refusal`, `bad_request`, empty). It never raises
  into the agent. Any tool-call block a proxy might echo is ignored and logged.

The agent then emits `note: cloud plan received` or `note: cloud plan
unavailable; continuing locally`, and the turn's `route` event carries
`detail.plan_source = "cloud" | "none"`. `router.status()["model_gateway"]`
shows `plans`, `fallbacks`, `last_plan` (chars, tokens, tool_calls) and
`last_fallback`.

## Files

| file | role |
|---|---|
| `config.py` | env → `GatewayConfig` (`plan` tier only); `model_gateway/.env` loader (non-overriding) |
| `policy.py` | pure `wants_cloud_plan()`; no I/O |
| `planning.py` | `request_plan()` and `build_plan_messages()`; the only cloud call the agent makes |
| `translate.py` | Ollama ⇄ Messages API shapes; `sanitize_schema()` clamps array `minItems`/`maxItems` the API rejects |
| `adapters/anthropic_backend.py` | official SDK; `complete()` (non-streaming, used for plans) and `stream()`; typed-error mapping |
| `adapters/base.py`, `adapters/__init__.py` | adapter contract + registry |
| `dispatch.py` | bookkeeping (`note_plan`, `note_fallback`, `status_snapshot`) |
| `events.py` | `Completion` / `TextDelta` / `ToolCalls` / `Done` / `CloudUnavailable` |
| `preflight.py`, `start_gateway.ps1`, `start_gateway.sh` | read-only preflight; `-CloudCheck` makes one ~8-token call to the planning model |
| `test_gateway.py` | live A (local) / B (plan) / C (local tools) verification |
| `test_translate.py`, `test_policy.py`, `test_adapter_mock.py`, `test_router_hooks.py` | offline tests (64) |
| `env.example`, `requirements.txt` | configuration template; the one approved dependency |

Hooks outside this directory (kept deliberately small):

* `local_agent/router.py` — `_gateway()` lazy import; `_mark_cloud_plan()`
  called once inside `decide()` (sets `detail["needs_cloud_plan"]`); `status()`
  carries a `model_gateway` block; `decide(..., allow_cloud=True)` keyword.
* `local_agent/agent.py` — `_request_cloud_plan()` runs once per turn right
  after the hop-0 route is decided; inserts the plan as a system message.
* `local_agent/planner.py` — `propose(..., guidance=...)` folds advisory text
  into the local planning prompt; still `allow_cloud=False`.
* `local_agent/ollama_client.py` — no gateway code any more.

## Setup

```powershell
pip install -r model_gateway\requirements.txt          # anthropic SDK (~15 MB, approved)
Copy-Item model_gateway\env.example model_gateway\.env  # then set ANTHROPIC_API_KEY, MODEL_GATEWAY_CLOUD=1
.\model_gateway\start_gateway.ps1 -CloudCheck           # read-only preflight + one tiny planning-model call
.\local_agent\START_LOCAL_AGENT_GUI.ps1                 # normal launcher; nothing new in the picker
```

Offline tests (no servers, no key):

```powershell
python -m unittest discover -s model_gateway -t . -p "test_*.py"   # -t . keeps package imports intact
```

Live verification (needs the CPU Ollama tier; section B needs the key):

```powershell
python model_gateway\test_gateway.py
```

## Local proxy testing

`MODEL_GATEWAY_BASE_URL` (or the SDK's own `ANTHROPIC_BASE_URL`) points the
adapter at any Anthropic-compatible server, for example Ollama's
`/v1/messages` on `http://127.0.0.1:11435`. For a non-Anthropic host the
adapter stops sending `effort` and cache markers and uses a placeholder key;
set `MODEL_GATEWAY_PLAN_MODEL` to an Ollama tag. That path loads a local
model, so it is for adapter testing only.

## Claude Code against local models

No gateway is involved: Ollama ≥ 0.14 serves `/v1/messages` itself.

```powershell
$env:ANTHROPIC_BASE_URL   = "http://127.0.0.1:11435"   # CPU tier; use 11434 only when 8188 is closed
$env:ANTHROPIC_AUTH_TOKEN = "ollama"                   # accepted, not validated
$env:ANTHROPIC_MODEL      = "josiefied-qwen2.5-coder-14b:q4_k_m"
claude
```

`tool_choice` and `count_tokens` are not supported on Ollama's endpoint, and
pointing at 11434 loads that model into VRAM, so run the preflight first.

## Known limits

* The plan is advice. The injected system message says so, and the local
  model still needs a live tool result before anything counts as done.
* One plan per turn, requested at hop 0; later hops reuse it as context.
* Context trimming can drop the injected plan on very long turns like any
  other early system note.
* The adapter's `stream()` path is retained for future use and tests; nothing
  in the agent calls it.
