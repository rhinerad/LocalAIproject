# model_gateway — local-first hybrid router (Ollama tiers + optional Anthropic tier)

Proof of concept from the 2026-11-02 audit (`CHANGELOG/2026-11-02a_…`). It adds
one more backend to the existing dispatcher in `local_agent/router.py` instead
of a separate proxy process: there is **no new port**, and with
`MODEL_GATEWAY_CLOUD` unset every turn routes exactly as before.

## The picture

`router.decide()` is a taxi dispatcher in front of one parking spot (the 16 GB of
VRAM). It already chooses between the GPU cab (`127.0.0.1:11434`), the CPU cab
(`127.0.0.1:11435`), PowerInfer and the Mac farm. This package gives the
dispatcher one more phone number: a long-distance carrier that never needs the
parking spot.

```
agent.py ──► router.decide(prompt) ──► Decision(tier, host, model, backend)
                 │   gpu_busy() probes (read-only)            │
                 │   classify_capability() → tool/logic/code  │
                 │   model_gateway.policy.choose_cloud_tier() │
                 ▼                                            ▼
      backend="ollama"  → ollama_client → /api/chat on 11434 / 11435
      backend="anthropic" → ollama_client → model_gateway.dispatch → anthropic SDK
                                              (events → str / ToolCall / StreamEnd)
```

## Tier map (approved 2026-11-02)

| alias | target | who goes here | guard |
|---|---|---|---|
| `tier-local-cpu` | Ollama 11435 (`num_gpu 0`, 4 threads) | compactor, memory extractor, planner, busy-GPU chat when cloud is off | unchanged; **never** cloud-eligible |
| `tier-local-gpu` | Ollama 11434 (Huihui 14B/8B, coder, DeepSeek) | default interactive turns while the GPU is idle | existing `gpu_busy()`, thermal, GPU gate |
| `tier-cloud-heavy` | `claude-opus-5-5`, effort `high` | unpinned **logic** turns (`difficulty.needs_escalation`), `cloud-heavy` pin, any `claude-*` pin | `MODEL_GATEWAY_CLOUD=1` + `ANTHROPIC_API_KEY` |
| `tier-cloud-fast` | `claude-sonnet-5-5`, effort `medium` | unpinned **tool/code** turns while ComfyUI holds the GPU (port 8188 / queue owner / foreign VRAM), `cloud-fast` pin | same, plus `MODEL_GATEWAY_BUSY_TIER=1` |

Never cloud: `prefer == "cpu"`, callers that pass no prompt (title helpers,
background workers), callers that pass `allow_cloud=False` (planner), pinned
local models, image/creative turns (they drive local media tools), and every
module that pins `CPU_HOST` directly (`context_compactor.py`,
`memory_extractor.py`).

## VRAM safety

A local model loads only when a body reaches `11434/api/chat`. The cloud
Decision is returned from `decide()` before `prepare_gpu_model()` /
`_finish_gpu_ollama()` run and is dispatched by `ollama_client` without building
an Ollama request, so a cloud turn cannot collide with ComfyUI. When the GPU is
busy the cloud route still calls `evict_gpu_residents()` (the same
yield-to-render rule the CPU hand-off uses) so the agent's own resident 14B
leaves the card. `test_router_hooks.py` asserts both.

## Offline / failure behaviour (decision 6)

Any gateway failure (`offline`, `timeout`, `auth`, `rate_limit`, `server`,
`refusal`, `bad_request`) is raised as `OllamaModelFailure` with a
`gateway_kind`. The agent's existing one-retry path calls
`router.fallback_after_primary_failure()`, which now re-decides locally with
`allow_cloud=False`, puts `detail["fallback_note"]` on the local Decision, and
the agent emits that note on the turn. The gateway also logs a warning
(`local_agent.model_gateway`) and `router.status()["model_gateway"]` carries
`last_fallback` / `fallbacks` for the status badge.

## Files

| file | role |
|---|---|
| `config.py` | env → `GatewayConfig`; tier aliases; `model_gateway/.env` loader (non-overriding) |
| `policy.py` | pure `choose_cloud_tier()`; no I/O |
| `translate.py` | Ollama ⇄ Messages API shapes (system lift, tool schemas, tool-call id minting, tool-result coalescing, `format` → `output_config`, usage → telemetry) |
| `adapters/anthropic_backend.py` | official SDK; streaming; typed-error mapping; one retry when a replayed thinking block is rejected |
| `adapters/base.py`, `adapters/__init__.py` | adapter contract + registry (add a vendor here) |
| `dispatch.py` | host-prefix → adapter; fallback bookkeeping; `status_snapshot()` |
| `events.py` | `TextDelta` / `ToolCalls` / `Done` / `CloudUnavailable` |
| `preflight.py`, `start_gateway.ps1`, `start_gateway.sh` | read-only preflight; prints the Claude Code env block |
| `test_gateway.py` | live A/B/C verification against real servers |
| `test_translate.py`, `test_policy.py`, `test_adapter_mock.py`, `test_router_hooks.py` | offline tests (61) |
| `env.example`, `requirements.txt` | configuration template; the one approved dependency |

Hooks outside this directory (kept deliberately small):

* `local_agent/router.py` — `Decision.backend` gains `"anthropic"`;
  `_gateway()` lazy import; `_maybe_cloud_decision()` called once inside
  `decide()`; `_cloud_fallback_decision()` from `fallback_after_primary_failure()`;
  picker rows in `chat_models()`; `model_gateway` block in `status()`;
  new `allow_cloud` keyword on `decide()`.
* `local_agent/ollama_client.py` — `_is_cloud_host()` branch in `chat()` and
  `chat_stream()` (mirrors the PowerInfer branch).
* `local_agent/agent.py` — the fallback note reads `detail["fallback_note"]`.
* `local_agent/planner.py` — `decide(..., allow_cloud=False)`.

## Setup

```powershell
pip install -r model_gateway\requirements.txt          # anthropic SDK (~15 MB, approved)
Copy-Item model_gateway\env.example model_gateway\.env  # then set ANTHROPIC_API_KEY, MODEL_GATEWAY_CLOUD=1
.\model_gateway\start_gateway.ps1 -CloudCheck           # read-only preflight + one 8-token round trip
.\local_agent\START_LOCAL_AGENT_GUI.ps1                 # normal launcher; picker now shows cloud-heavy / cloud-fast
```

Offline tests (no servers, no key):

```powershell
python -m unittest discover -s model_gateway -t . -p "test_*.py"   # -t . keeps package imports intact
```

Live verification (needs the CPU Ollama tier; the cloud checks need the key):

```powershell
python model_gateway\test_gateway.py
```

## Translation notes (what the adapter changes on the wire)

* `temperature`, `top_p`, `repeat_penalty`, `num_*`, `keep_alive`, `think` are
  dropped. Sampling parameters are rejected on the current API version and
  thinking is governed by `output_config.effort`.
* Ollama tool calls carry no id; ids are minted deterministically and the
  provider's own ids are kept once a cloud hop has produced them. All tool
  results of one assistant turn are sent as one user message of `tool_result`
  blocks (the API otherwise stops making parallel calls).
* The assistant turn still awaiting its tool results is replayed from the raw
  provider blocks (thinking included); earlier turns are replayed as text and
  `tool_use` only. If the API rejects a replayed block (history edited), the
  adapter retries once without it.
* Mid-conversation `system` messages (the agent's "planning assist") become
  `[Operator note]` user text so the transcript stays append-only.
* `format=<schema>` → `output_config.format` (json_schema); `format="json"` → a
  system note.
* `usage` is mapped onto Ollama's `eval_count` / `prompt_eval_count` so tracing
  spans and the token ledger keep working; cache hits are under
  `telemetry["gateway"]`.

## Local proxy testing (decision 2 note)

`MODEL_GATEWAY_BASE_URL` (or the SDK's own `ANTHROPIC_BASE_URL`) points the
same adapter at any Anthropic-compatible server, for example Ollama's
`/v1/messages` on `http://127.0.0.1:11435`. For a non-Anthropic host the
adapter stops sending `effort` and cache markers and uses a placeholder key;
set the tier models to Ollama tags. Note that this path **does** load a local
model, so it is for adapter testing, not for the VRAM-free cloud tier.

## Claude Code against local models (goal 2)

No gateway is involved: Ollama ≥ 0.14 serves `/v1/messages` itself.

```powershell
$env:ANTHROPIC_BASE_URL   = "http://127.0.0.1:11435"   # CPU tier; use 11434 only when 8188 is closed
$env:ANTHROPIC_AUTH_TOKEN = "ollama"                   # accepted, not validated
$env:ANTHROPIC_MODEL      = "josiefied-qwen2.5-coder-14b:q4_k_m"
claude
```

`tool_choice` and `count_tokens` are not supported on Ollama's endpoint, and
pointing at 11434 loads that model into VRAM, so run the preflight first.

## Known limits of the prototype

* Vision turns (user `images`) are translated but the policy never routes them
  to the cloud; local media tooling owns them.
* No server-side refusal fallback: a `refusal` stop reason falls back locally
  like any other failure (`MODEL_GATEWAY_SERVER_FALLBACK` is reserved).
* The agent's context trimming edits history client-side; on an account with
  the preserved-thinking check enforced this costs one retry per edited hop
  (handled) and the dropped reasoning for that hop.
* Status polling calls `load_config()` each time; it is a few dict reads plus
  an optional `.env` stat, not a network call.
