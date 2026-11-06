# PowerInfer chat-picker plug-in — design note

Read before the code. This is how PowerInfer joins the existing local-agent
chat picker; it is not a new backend framework.

## What the router actually is today

`local_agent/router.py` is **not** a registry of inference engines. It is an
Ollama CPU/GPU handoff:

- Two Ollama hosts: GPU `127.0.0.1:11434`, CPU `127.0.0.1:11435`.
- `chat_models()` lists installed Ollama tags plus one opt-in GPU-only
  exception (`gpt-oss-20b-heretic`).
- `decide()` returns a `Decision(tier, host, model, …)` that `agent.py` always
  feeds to `ollama_client` (`/api/chat`).
- `llama_cpp_client.py` is a **vision** path (`capabilities.ensure_qwen25_vl_runtime`),
  not a chat-picker backend.
- There is no remote-chat backend. “Remote” in this tree is Sideband/phone
  transport, not a second LLM provider.

So the picker already chooses **which Ollama model** to pin. It does not
choose **which process** answers.

## Existing pattern for “this choice may be unusable”

The Heretic entry is the pattern to copy, not a new one:

- Always visible in `chat_models()`, including while the GPU is busy.
- `available: false` until the exact local artifact exists.
- GUI disables the option (`setup_hint` / `unavailable_reason`).
- New chats cannot pin it while unavailable (`server._valid_chat_model`).
- `decide()` returns `model is None` with an explicit reason. It never
  silently substitutes Huihui 8B / CPU Ollama.
- The router **does not start** the missing process. Setup is operator-side
  (`setup_gpt_oss_20b_heretic.py --create`).

PowerInfer is the same *product* shape (opt-in, GPU, may be down) but it is
**not** an Ollama tag. Treating it as one would send `/api/chat` to the
wrong server.

## How PowerInfer plugs in

1. **Picker.** A second Heretic-style row after the existing opt-in models:
   `name = POWERINFER_MODEL_ALIAS` (default `powerinfer-local`),
   `gpu_only: true`, `backend: "powerinfer"`. Always listed. `available`
   is true only when **both** the OpenAI proxy (`127.0.0.1:8091`) and
   PowerInfer `server.exe` (`POWERINFER_BACKEND_URL`, default
   `http://127.0.0.1:8080`) accept a short loopback probe. Timeouts match
   `up()` / `comfy_listening()` so a down backend cannot hang status polls.

2. **Routing.** `decide(model="powerinfer-local")` is a dedicated branch
   next to `is_gpu_only_opt_in_model`, **not** an extra Ollama preference.
   A runnable decision uses `host=127.0.0.1:8091`, `backend="powerinfer"`.
   A non-runnable decision keeps the chat pinned and explains:
   proxy down, `server.exe` down, or GPU owned by ComfyUI / a foreign
   compute process. No Ollama/CPU substitution.

3. **GPU ownership.** `gpu_busy()` today treats any non-Ollama compute
   process as a render. Live `server.exe` would otherwise make **every**
   PowerInfer turn look busy and refuse itself. Mirror the resident-Ollama
   exception: when the configured PowerInfer backend is the process on the
   card, Ollama auto-chat still yields to CPU, but a PowerInfer-pinned chat
   is allowed to talk to the already-running proxy. ComfyUI port 8188 and
   `render_queue_owner.json` still win.

4. **Transport.** `ollama_client.chat` / `chat_stream` dispatch on
   `host == POWERINFER_PROXY_HOST` to a small OpenAI-compat client that
   posts `/v1/chat/completions` (the proxy contract is unchanged). Native
   tool schemas are not sent (the proxy rejects tools). Legacy `TOOL:`
   parsing in `agent.py` remains. Tool-role history is flattened to
   alternating text roles so the Llama-2 renderer is not fed `role=tool`.

5. **GPU gateway.** A PowerInfer pin must not request an Ollama GPU load.
   If the proxy/`server.exe` pair is not up, the turn fails with a setup
   hint. That is the Heretic “not installed” path, not a new supervisor.

## Deliberate non-feature: on-demand start

`capabilities.ensure_qwen25_vl_runtime()` starts `llama-server.exe` for a
**media** job after VRAM planning. That is not a chat-picker pattern, and
it is the wrong place to copy for PowerInfer:

- `powerinfer_openai_proxy.py` is specified **not** to start/stop
  `server.exe`. Wiring auto-start into `decide()` would violate that
  contract from the caller side.
- A real start needs a production-registry bundle, GPU-gateway grant,
  VRAM budget, and thread/context flags. Those live in the PowerInfer
  pipeline, which another session is running; this change must not
  touch `tools/powerinfer/run_pipeline.ps1`, `pipeline_lib.py`,
  `vault.py`, or `init_vault.py`.
- Starting `server.exe` from a status poll or first token would race
  ComfyUI and the live pipeline.

If PowerInfer is down, the picker shows it disabled and `decide()` says
so. The operator starts `server.exe` and the proxy themselves, then the
same picker row becomes selectable. That is the gap: **the router can
detect a missing backend cleanly; it cannot own PowerInfer process
lifecycle without a new supervisor, and this change will not invent one.**
