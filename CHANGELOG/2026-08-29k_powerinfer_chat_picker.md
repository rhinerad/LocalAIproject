# 2026-08-29 — PowerInfer as a normal local-agent chat-picker backend

## What changed

- Design: `docs/POWERINFER_CHAT_PICKER_DESIGN_2026-08-29.md`. The router is
  still an Ollama CPU/GPU handoff, not a multi-engine registry. PowerInfer
  joins the picker the same way `gpt-oss-20b-heretic` does: always visible,
  GPU-only, never an automatic default, never a silent Huihui/CPU substitute.
- `local_agent/router.py`
  - `chat_models()` always appends `POWERINFER_MODEL_ALIAS` (default
    `powerinfer-local`) with `backend: "powerinfer"`.
  - `available` is true only when both the OpenAI proxy (`127.0.0.1:8091`)
    and `server.exe` (`POWERINFER_BACKEND_URL`, default `http://127.0.0.1:8080`)
    accept a 0.4s loopback TCP probe. A down backend cannot hang a status poll.
  - `decide(model="powerinfer-local")` returns `host=POWERINFER_PROXY_HOST`
    and `backend="powerinfer"`, or `model is None` with an explicit reason
    (proxy down, server down, ComfyUI/foreign GPU owner). It does not start
    `server.exe` or the proxy.
  - `gpu_busy()` treats a configured PowerInfer `server.exe` as this agent's
    GPU occupant: ordinary Ollama auto-chat yields to CPU; a PowerInfer pin
    is allowed to talk to the already-running proxy. Queue owner and port
    8188 still win.
- `local_agent/powerinfer_client.py` — OpenAI `/v1/chat/completions` client
  for that host. Flattens tool-role history to text. Does not send native
  tool schemas. The proxy contract is unchanged.
- `local_agent/ollama_client.py` — `chat` / `chat_stream` dispatch to that
  client when `host == POWERINFER_PROXY_HOST`, so planner and other callers
  do not post `/api/chat` at the proxy.
- `local_agent/agent.py` — a PowerInfer pin does not request an Ollama GPU
  load, does not run the extra planner hop, and does not send native tools.

## Why

The OpenAI proxy was built and tested but was not in the GUI picker, so the
operator still had to call it by hand. The existing picker already had a
pattern for an opt-in GPU choice that may be unusable (Heretic). PowerInfer
is that shape plus a different HTTP contract. Auto-starting `server.exe`
from the router was rejected: the proxy is specified not to spawn that
process, the production pipeline owns lifecycle, and another session is
using those files live.

## The evidence

From `local_agent/`:

```
python test_router_switching.py -v
Ran 36 tests in 8.071s
OK

python test_router_status_busy.py -v
Ran 3 tests in 0.416s
OK

python test_powerinfer_chat_route.py -v
Ran 5 tests in 0.001s
OK

python test_powerinfer_openai_proxy.py -v
Ran 5 tests in 0.000s
OK

python -m py_compile router.py ollama_client.py agent.py powerinfer_client.py
python test_native_tool_calling.py -v
Ran 28 tests in 13.314s
OK
```

New coverage includes: picker row visible-but-disabled when down; selectable
when both ports listen; ComfyUI-busy refusal without Ollama substitution;
clear proxy-down reason that states the router does not start the process;
PowerInfer-on-GPU forces Ollama auto-chat to CPU; a PowerInfer pin uses the
proxy host when PowerInfer already owns the card; tool-role flattening;
`chat_stream` dispatch away from `/api/chat`; unreachable proxy raises
`OllamaUnavailable` without hanging.

## What was verified after

Offline unit tests above. No `server.exe`, proxy, model load, GPU inference,
or live GUI pin was started in this session (the PowerInfer pipeline is
owned by another session; `tools/powerinfer/run_pipeline.ps1`,
`pipeline_lib.py`, `vault.py`, and `init_vault.py` were not touched).

## What is still unverified

- Live picker against a real proxy + `server.exe` pair.
- Token streaming and first-token latency on an accepted sparse bundle.
- Tool quality via the legacy `TOOL:` text fallback (native tools are not
  sent; the proxy still rejects tool roles).
- On-demand start of `server.exe` + proxy. That remains an operator step,
  documented in the design note. The architecture can detect a missing
  backend; it does not own PowerInfer process lifecycle.
