# Local Agent — a local ChatGPT Desktop equivalent

## Product goal

The primary goal is a **functional local copy of ChatGPT Desktop**, not merely a
project-status bot. It should feel like a general desktop assistant first:
persistent conversations, strong everyday answers, native tool use, files,
images, audio, video, web research, memory, interruption/regeneration, and
polished desktop startup. Equal Shares knowledge, render coordination and its
non-negotiable evidence/thermal guards are the specialist layer on top.

Ordinary writing, brainstorming, explanations, coding, and general questions do
not load the film-production handbook. ComfyUI, rendering, prompting, clips,
and video work are ordinary by default. Only explicit Equal Shares, MiniMax H3,
an Equal Shares clip ID, or an Equal Shares file/path activates specialist
context. Image, video, and audio models remain sensory tools; they are not used
as the main conversation model.

Runtime guard, 2026-09-01: stale specialist history is not enough to activate
that context. If the current operator message is about PowerInfer, files,
coding, general writing, phone control, memory, or any other non-specialist
task, the agent must not answer as if an H3/ComfyUI/Equal Shares render is in
progress. `agent.py` now blocks specialist project tools before execution on
unrelated turns and discards one stale specialist reply/tool path before
retrying the actual request.

Large creative/storyboard **prompt packs** (e.g. a 102-clip Backrooms audition
pack), 2026-09-07: classified as `CAP_CREATIVE`, not `CAP_IMAGE`. The harness
saves the full source under `runtime/managed_tasks/<conversation_id>/`, chunks
clips, writes per-clip outputs, and resumes on continue/proceed. It does **not**
start Comfy/`render_story_image*` from the pack paste alone — only after an
explicit short-turn render ask. Tools: `ingest_prompt_pack`,
`export_prompt_pack_outputs`, `prompt_pack_status`.

Reviewed frame-first packs, 2026-09-07 r97: start/end/video sections merge by
clip and field; empty prompts cannot count as exported. Revisions are fingerprinted
and retain previous outputs. The explicitly reviewed Backrooms pack applies its
editor overrides to effective inputs while retaining the source text unchanged.
"Render" (including "redner") resolves to the saved first SDXL review anchor;
subsequent checks reuse its launch receipt. Exported means prompt files written,
not images rendered or a film complete. See CHANGELOG/2026-09-07d_reviewed_prompt_pack_execution.md.

Source citation, 2026-09-02: factual claims must name their evidence source.
Tool results carry explicit source metadata — `[https://…]` for fetched URLs,
`[File: …]` for file reads, `[Source: persistent memory]` for memory, and
`docs: …` for document search. Large tool outputs pruned to artifact pointers
still carry the source label so provenance survives context compaction. The
model's system prompt includes a `# Source citation` contract; the post-tool
follow-up message requires citing the source or labelling unsupported claims
as "unverified".

Each new conversation starts with a **Model for this chat** picker. The selected
model is written into that conversation and the picker locks after the first
message. Reopening, continuing, or regenerating the chat uses the same model.
The compute selector may still move that model between CPU and GPU when it is
installed on both tiers. A GPU-only pinned model refuses safely if the GPU is
reserved by a render. The one explicit resilience exception is the configured
Huihui 14B reasoning model: while the GPU is idle, a context above 16,000
estimated tokens or a 14B OOM/5xx/timeout switches that turn to its paired 8B
GPU fallback. It unloads the 14B first; it never accepts CPU layer offload.

### Optional gpt-oss-20b-heretic chat

The new-chat picker always shows **gpt-oss-20b-heretic (opt-in, GPU only)**.
Before it is installed the entry is disabled and says **Install required**. It
is the exact `gpt-oss-20b-heretic` Ollama model built from Bartowski's
`p-e-w_gpt-oss-20b-heretic-Q4_K_M.gguf`, not a substitute model. Install it
only when wanted:

```powershell
python local_agent\setup_gpt_oss_20b_heretic.py --create
```

The installer verifies the GGUF SHA-256, writes an 8,192-token Modelfile, and
imports it on the private GPU Ollama host `127.0.0.1:11434`. The normal launcher
never downloads, creates, preloads, or selects it. Once installed, select it
before the first message of a new chat. It stays pinned to that chat, uses the
GPU only, and refuses while ComfyUI or another GPU owner is active; it never
falls back to CPU layers or silently becomes the 8B model.

### Optional PowerInfer chat (`powerinfer-local`)

The new-chat picker always shows **powerinfer-local**. It is not an Ollama
tag. When both backends listen it is labelled **opt-in, PowerInfer, GPU,
text-only**; when either is down it stays visible but disabled
(**opt-in, PowerInfer — not running**). Select it only before the first
message of a new chat. It stays pinned, uses the GPU only, and refuses
while ComfyUI or another foreign GPU owner is active; it never falls back
to CPU layers or silently becomes Huihui 8B.

The router only **detects** whether two loopback processes are already
reachable. It does not start or stop them:

| Process | Default | File |
|---|---|---|
| OpenAI proxy | `127.0.0.1:8091` | `powerinfer_openai_proxy.py` |
| `server.exe` | `127.0.0.1:8080` | built PowerInfer server, not the GUI launcher |

If the row is unavailable, read the picker hint and run
`python local_agent\router.py` for the exact reason (proxy down, server
down, or GPU busy). Native tool schemas are not sent on this pin
(text-only), and `apply_hop_profile()` swaps the model-facing system
prompt to a short no-tools framing (no execution-first instructions or
tool names) while keeping the usual project/memory context. The launcher
never downloads, creates, preloads, or selects a PowerInfer model.

This is the **picker contract**, verified in the 2026-08-29/30 router
tests. It is not a production chat backend yet, and no model is in the
production registry. ReluLLaMA-7B mechanical calibration finished and then
failed the quality packet (not eligible). TurboSparse-Mistral projected
abliteration is parked at
`A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`
only — do not use the earlier non-`b` directory. Predictors for that edited
tree have **not** been rebuilt; no quality benchmark has been run. Do not
begin predictor generation from it even if a new pair file exists: it was
itself edited from only eight synthetic pairs. A new immutable approved-pair
edit is required first. Do not dump, train, convert, or bench that new edit
until its approved pairs are recorded and the GPU gate is freshly approved.
Its tokenizer is verified checkpoint ChatML
(`151dcbed9fbd8f6f020e6c12f8cf7c848c1edfc6f7138648b922282e77d6e2ea`), not
the generic Mistral `[INST]` syntax. The strict two-turn JSON tool-call gate is
prepared under `tools/powerinfer/`, but no PowerInfer model may enter this
picker until conversion, the gate, and human review all pass.
Do not pin `powerinfer-local` live until an accepted sparse bundle exists.

**Coding mode** is a picker choice for any installed coder (default
`huihui_ai/qwen2.5-coder-abliterate:14b`, overridable with
`EQUAL_SHARES_CODING_MODEL`). It pins that model and swaps in a test-driven
coding system prompt. Routing is unchanged: GPU when the card is idle, CPU
fallback when a render owns it. A 14B coder on CPU is slow — the status badge
says so. The launcher does **not** pull the coder on every start; pass
`-EnsureCodingModel` or set `EQUAL_SHARES_ENSURE_CODING_MODEL=1`. Honest
ceiling: a strong local junior/mid coder, not a frontier model. Route hard
multi-file work elsewhere.

“Local copy” means capability and interaction parity where this workstation can
provide it; it does not mean pretending an unavailable local model can see,
hear, transcribe, browse or reason at cloud-model quality. Missing capabilities
must remain visible and honest, and no model or dependency is downloaded without
explicit approval.

No cloud AI accounts or cloud model calls. The optional local URL fetch and web
search tools use the workstation's existing internet connection only when the
operator asks for a link or a search; they never download a model or dependency.

```powershell
.\local_agent\START_LOCAL_AGENT_GUI.ps1
```

Starts both Ollama tiers, refreshes the knowledge pack from live project state,
and opens the app at `http://127.0.0.1:8760`.

### LoRA workflow launchers

`local_agent\LORA_WORKFLOW_SHORTCUTS\` contains one double-click launcher for
each saved ComfyUI graph that was verified to expose LoRA controls. The
launchers open the original source workflow in Comfy Desktop; they never copy
or modify a workflow, queue a job, or start a render. See that folder's
`WORKFLOWS.md` for the exact LoRA-loader nodes in each graph.

---

## It moves between the GPU and the CPU on its own

| GPU | what runs | why |
|---|---|---|
| **idle** | the big model, on the card | fast, better answers |
| **busy** | a small model, on CPU | the render is untouched |

When installed, the Huihui reasoning pair is preferred on an idle GPU:
`huihui_ai/qwen3-abliterated:14b` →
`huihui_ai/qwen3-abliterated:8b`. The 8B route occurs predictively above the
configured context limit and reactively after a recoverable 14B server failure.
Both requests use full GPU placement; the fallback is not CPU offload.

The `qwen3vl_32b_minimax_h3_*` file named in render documentation is a
**ComfyUI MiniMax H3 text encoder**, not a local-agent chat model. Separately,
the local agent did use `huihui_ai/qwen3-vl-abliterated:32b` as a 20 GB
vision/action model on 2026-08-23. That historical action path was intentionally
replaced on 2026-08-24 by the operator-requested Qwen2.5-VL Caption V4 GGUF
and matching projector because the 32B VLM could CPU-offload. The current
Ollama model list does not advertise that historical 32B tag; it must not be
silently substituted or restored without an explicit operator decision.

Checked **before every reply**, so a render that starts mid-conversation moves
the next answer to CPU without you doing anything. The tier is shown in the
sidebar and on each reply.

### GPU permission gateway

The sidebar has a **GPU permission** control. It defaults to **Ask every time**:
before the local agent loads a chat model onto an otherwise idle GPU, it creates
one visible card that the operator can approve once or deny. **Allow local
agent** permits its future model loads; **Block local agent** keeps its work on
CPU. A batch-render launch is also a fresh GPU owner and must receive its own
one-shot approval. The card also shows the router's observed VRAM/process evidence and known
controls: yield resident Ollama models, cancel media work, and stop ComfyUI.

Pending GPU permission cards do **not** expire. They remain until approved or
denied, while approval itself remains one-shot and bound to that exact workload
key. Repeated approval clicks are safe and report the original decision instead
of treating it as an expired request.

This is an application gateway, not an unsafe task-manager replacement. It can
prevent and release local-agent workloads and expose ComfyUI/Ollama state; it
does not kill arbitrary Windows PIDs it cannot verify as one of those workloads.

### Direct text-file edits

When the desktop operator directly asks the agent to create or edit a normal
text file—including `.ini`, `.cfg`, `.json`, `.bat`, and `.vbs`—that request is
the authorization. `write_file` completes it without a redundant sidebar card.
Protected project records remain refused, remote identities still need their
explicit `write_file` capability, and binary byte patches retain the separate
exact-byte approval gate.

### Execution-first replies

For a direct request to check, fix, validate, create, edit, save, start, stop,
or otherwise carry out a safe task, the agent should use an available tool and
then report the result. It should not hand the desktop operator a command for
work it can perform itself. If the first model reply is recognizably
instructional and no tool has been attempted, the loop makes one bounded
execution-first retry that tells the model to select the appropriate tool.

This is deliberately one retry, not an autonomous background loop. The agent
still reports a concrete blocker when it lacks a needed input, capability, or
external service, and it retains separate safeguards for protected files,
binary edits, GPU ownership, phone identities, downloads, and renders.

### JSONL repair and exact-path continuity

When a current task's JSONL validation reports a parsing error and the desktop
operator says to fix it, the agent reuses the exact failed-validator path. It
can convert only a top-level JSON array of objects into one JSON object per
line, then immediately validates that same file again. It cannot invent
records, alter record values, approve the result, or begin model, predictor,
GPU, render, or registry work. Exact recent tool paths are retained in the
per-chat task checkpoint so transcript compaction cannot replace them with an
ellipsis, a documentation example, or a guessed location.

The desktop server also carries the last few compact tool receipts from the
same saved chat into its next request. These are facts from the agent's own
previous tools, not fresh instructions and not cross-chat recall. This lets a
follow-up after a server restart reuse a validated local path without exposing
unrelated conversations. Since 2026-09-01, those receipts keep structured
fields such as `path`, `valid`, `reason`, and `records` in addition to the
short human summary. Older truncated receipts are still scanned for exact
`.jsonl` paths, so a long Windows path is not lost merely because the visible
summary was shortened.

### Action-resolution layer

Direct operator requests for known, safe actions are classified and dispatched
before the model drafts any prose. `action_resolver.classify()` inspects the
current message and same-chat tool evidence, then returns an `ActionPlan` with
an ordered list of `(tool_name, args)` steps — or `None` to fall through to the
normal model turn. `agent._execute_plan()` runs those steps through `tools.call()`
so every existing guard (protected-file, phone identity, GPU gateway, render
preflight) remains active.

Five intents are handled deterministically, in priority order:

| Intent | Trigger | Evidence required |
|---|---|---|
| `comfyui_stop` | "stop / kill / abort the render" | none — safety action |
| `jsonl_repair` | "fix it / fix the formatting error" | pending failed calibration path |
| `calibration_continue` | "continue with the approved JSON" | pending calibration path, non-render turn |
| `list_dir` | "show / list / browse … folder / files" | alias match or explicit path token |
| `read_file` | "read / open / view … file" | explicit path token |

Evidence-required intents (`jsonl_repair`, `calibration_continue`) will not fire
unless `_pending_failed_calibration_path()` returns a non-None path from same-chat
tool receipts. This prevents the resolver from guessing on ambiguous messages and
lets the normal model turn handle requests where no concrete path is known.

Adding a new intent: add a pattern constant, add a classify branch in priority
order, and add a regression test in `test_action_resolver.py`.

### Guarded binary / hex edits

Binary files are not treated as text. `inspect_binary` shows a bounded byte range
as hexadecimal plus ASCII without changing the file. `apply_hex_patch` can make
only a fixed-length, in-place replacement after the agent has inspected the
current bytes and the operator approves that exact path, byte offset, old bytes,
new bytes, and whole-file checksum in the File edit card. The bytes and checksum
are rechecked immediately before writing, so an intervening file change is
refused. It cannot create a file, insert/delete bytes, patch more than 4096 bytes
at once, or edit any Equal Shares evidence/protected record. Remote identities
remain default-denied for this write capability.

It does not merely avoid *starting* on the GPU while busy — when it detects a
render it **actively evicts its own GPU model** (`keep_alive: 0`) before
answering on CPU. A 14B model is 9–10 GB of VRAM; yielding late is the same as
not yielding.

### Experimental GPU KV-cache mode

The normal launcher uses Ollama's baseline cache mode. After comparing guarded
reports for this exact machine, a deliberate candidate launch is available:

```powershell
.\local_agent\START_LOCAL_AGENT_GUI.ps1 -GpuKvCache flash_q8
```

That launch configures **only the GPU** Ollama server with Flash Attention and
`q8_0` KV cache. It does not touch the CPU server, does not start a render, and
is not the default. Stop the current GPU Ollama service first so the launcher
can create it with the selected mode; do this only when ComfyUI is stopped and
the render owner is released. Keep it only if matching 14B benchmark reports
show sufficient VRAM benefit with a correct response and acceptable speed.

**Three independent busy signals, any one is enough:**

1. `runtime/render_queue_owner.json` names a live PID — the project's own lock,
   which catches the window between claiming the queue and the backend loading
2. port **8188** is listening — a ComfyUI backend is up, including a manual one
3. `nvidia-smi` shows VRAM above 2500 MB or a foreign compute process

**It fails safe.** If `nvidia-smi` cannot run at all, the GPU is treated as busy.
An unknown GPU state is never permission to use it. Forcing GPU in the dropdown
is refused while a render is running — you can force CPU, never force a conflict.

### ComfyUI MCP tools (`comfyui-mcp`)

Optional sidecar, not a chat-client npm dependency. `local_agent/mcp_client.py`
spawns `npx -y comfyui-mcp` once (Node >= 22), keeps it alive, and serializes
JSON-RPC on stdio so ThreadPoolExecutor calls cannot interleave. The child env
always sets:

| Variable | Value |
|---|---|
| `COMFYUI_PATH` | `A:\Users\rhine\ComfyUI-Shared` (data/base: models, input, output, Equal Shares evidence) |
| `COMFYUI_CODE_PATH` | `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI` (split install: `main.py` / `.venv`) |
| `COMFYUI_URL` | `http://127.0.0.1:8188` |

Seven named tools wrap comfyui-mcp groups — there is no raw "call any MCP tool"
passthrough: `comfy_generate`, `comfy_workflow`, `comfy_assets`, `comfy_models`,
`comfy_nodes`, `comfy_system`, `comfy_process`. None are concurrency-safe.
`comfy_process` and `comfy_nodes` are project-only. `comfy_process`
(`restart_comfyui`) refuses if `work/thermal_guard.py`'s live GPU sample is
over `START_MAX_C` / `EMERGENCY_C`, or if the stage supervisor, batch runner,
or image renderer currently owns the process (`router.queue_owner()` plus the
same live-PID checks `start_batch_render` uses). `comfy_generate`, model
deletes, and node installs append `local_agent/runtime/comfy_mcp_audit.jsonl`.
`generate_image` action `image` ignores `filename_prefix` (MCP hardcodes
SaveImage to `ComfyUI`); live-verify/probe scripts use
`mcp_test_output.py` so files land in `ComfyUI-Shared/output/mcp_test/`.
Do not run these at the same time as this project's own render dispatch.

### Opt-in loop engineering

The local agent has a deliberately narrow maintenance-loop controller. It is
**disabled by default**, has no automatic scheduler, and can only run one named
read-only regression check at a time. It cannot call chat tools, modify files,
download, load a model, browse, or start/stop ComfyUI. A failed check stops the
goal and creates an operator-review record; it never retries by repairing its
own code.

Use it only for an explicit verification objective:

```powershell
python .\local_agent\loop_controller.py discover
python .\local_agent\loop_controller.py create --title "Local regression" --objective "Verify the general assistant safeguards." --check general_scope --check native_tool_calls
python .\local_agent\loop_controller.py set-enabled true
python .\local_agent\loop_controller.py run-once <goal-id>
python .\local_agent\loop_controller.py set-enabled false
python .\local_agent\loop_evaluation.py
python .\local_agent\loop_metrics.py
```

Each `run-once` invocation performs one fixed check and stops. Durable state is
kept under `local_agent/runtime/loop_engineering/` with redacted audit records;
the web status endpoint exposes a summary but provides no way to enable or run
the controller. See `local_agent/UPGRADE/22_loop_engineering.md` for the staged
roadmap and non-negotiable safety boundaries.

After a check fails and produces an operator-review record, an explicitly
requested repair proposal can be made with a complete replacement-content file:

```powershell
python .\local_agent\loop_controller.py propose-repair <goal-id> --check general_scope --path .\local_agent\README.md --content-file .\candidate_readme.md
```

This returns a unified diff and records only its fingerprint. It never writes
the target. Applying a resulting change is still a separate normal local-agent
file-edit request, and configuration/executable files still require the exact
one-shot sidebar approval.

## What it is

| | |
|---|---|
| Interface | a chat app in your browser, bound to `127.0.0.1` only |
| Models | configured abliterated pair: Huihui Qwen3 14B on idle GPU; Huihui Qwen3 8B on CPU whenever a render owns the GPU |
| Dependencies | core GUI: **none**; optional Sideband bridge: pinned local RNS/LXMF wheels |
| Network | core GUI: none; optional phone bridge: LXMF/Reticulum over the local Wi-Fi/LAN subnet |
| Chats | persist across restarts, one JSON file each |

It talks like any assistant — plain English in, plain English out. It answers
ordinary questions too, not just project ones. It knows the proven settings, the
prompt format, the one-off speaker rule, the duration ladder, what is blocked and
what runs next, and it can act: read state, inspect a clip, validate prompts,
regenerate derived files, prepare a guarded render plan, and—on an explicit
desktop request—start that approved general render. Remote phone sessions remain
default-denied for renders.

## Desktop features

Conversation sidebar with new / rename / delete · history that survives restarts
· **Stop** mid-generation · **Regenerate** · **Copy** · attachments (text, code,
images, audio and video; 75 MB each) · tier selector · live GPU/CPU indicator.

### Cross-chat continuity

For a substantive new request, the agent locally searches compact excerpts from
other saved desktop chats and supplies only the most relevant prior context.
The activity trace says how many chats were reused. This reduces repeated setup
and rediscovery, but prior chat text is never proof: current files, project
state, and actions still require a live tool check. The search remains on this
workstation and does not send chat archives anywhere.

### Context budget and durable learning

Tool results larger than 2,400 characters are retained only in a local
fingerprinted artifact under `runtime/artifacts/`; the next model hop receives
a compact pointer instead of the full raw output. This keeps multi-step chats
usable without discarding the local audit record.

When the exact CPU-only `llama3.1:8b` model is installed on port 11435, older
turns are summarized into a strict structured continuity record and post-turn
memory extraction may save only stable, non-sensitive preferences, hardware,
workflow, or project facts. Both operations use `num_gpu: 0` and unload after
the call. Until that model is installed, the agent keeps its deterministic
continuity summary and does not auto-write memories.

Install that exact CPU-only helper through the normal launcher when desired:

```powershell
.\local_agent\START_LOCAL_AGENT_GUI.ps1 -EnsureContextModel
```

### Difficult-task planning assist

The selected 8B abliterated chat model remains the chat model for its
conversation.  For a request that is clearly multi-step or technically
complex, the agent may request a **one-time 14B abliterated planning assist**
before it acts.  That assist is subject to the same GPU permission gateway and
is skipped whenever the GPU is owned, the chat is CPU-only, or the planner
cannot provide a valid inert checklist.  The checklist is context, not proof:
every file, state, and action still needs live tool evidence.

The media status panel separates **pending** jobs from jobs already running.
**Clear pending media queue** never deletes uploads, results, or evidence: it
moves only pending JSON job records to `local_agent/media_queue/cancelled/`,
including their original request and a cancellation timestamp. A job already
running is intentionally left alone. Identical pending/processing requests are
coalesced so the same attachment cannot be transcribed twice.

The **Queue** pill opens a live dropdown.  It shows every running or pending
media job, its queued duration, progress, priority, and the concrete reason it
is waiting (render ownership, VRAM, CPU transcription, or its queue position).
Each row has a cooperative **Cancel** control.  Pending work moves to
`media_queue/cancelled/` with its evidence record intact; processing work is
flagged and stops only at the next safe media boundary.  The local-only endpoint
is `POST /api/media_queue/cancel` with `{"id": "..."}` and only accepts media
queue ids; it cannot affect ComfyUI renders.

Direct media requests are marked **interactive** and take priority over old
background batches (FIFO inside each tier). If a render starts during a
multi-frame video analysis, the watcher stops at the next safe frame/batch
boundary, returns that same job to pending with a pre-emption record, releases
the VLM, and lets the render win. It never writes a partial result as complete.

An explicit request to complete a normal file-editing task authorizes the agent
to read, edit, and verify the text file in that task. It does not stop at a
preview or require a second confirmation. Ask to review a unified diff first if
you want preview-first behavior for a particular change. The protected
manifest/evidence files remain unavailable to both actions.

## External dataset evaluation

External datasets are not placed directly into live retrieval. Broad instruction,
web, and code corpora do not teach the agent new capabilities when merely
embedded; they can instead distract it from current tool evidence. The accepted
use is a human-reviewed offline evaluation source.

`stage_ultrafeedback_eval.py` plans or, only with `--execute`, streams a bounded
sample of `HuggingFaceH4/ultrafeedback_binarized` preference pairs into
`dataset_eval_staging/pending/`. Those records retain source and MIT-license
metadata and are **not** embedded in Chroma. A reviewer must turn a useful,
anonymized record into a concrete `operator_eval.py` case before it can affect
reliability measurements.

Deleted chats move to `chats/_deleted/` rather than being unlinked — a chat can
hold the only written record of a decision.

## Feedback and curated examples

Feedback is private by default. A normal rating stores only a SHA-256 fingerprint
of the request, the rating, and any rule you deliberately supplied; it does not
store the chat transcript. The optional `full_sanitized` mode is reserved for
operator-approved future training-data curation and strips local paths, email
addresses, and common credentials before the record is encrypted. Records are
AES-256-GCM envelopes written only when the local chat and GPU are idle. The
encryption key is protected with the current Windows user's DPAPI; a headless
service account with no user profile must supply its own 32-byte base64
`LOCAL_AGENT_FEEDBACK_KEY` rather than falling back to plaintext.

External examples are never fed directly into memory or retrieval. They first
go in `local_agent/exemplar_staging/pending/` with source and license metadata.
The operator can inspect them with `python local_agent/exemplar_curator.py
--interactive` or the local-only review API, then approve, edit-and-approve, or
reject. Pending and rejected examples never reach retrieval. An approved record
is embedded locally with `nomic-embed-text` through the CPU-only Ollama server
and stored in the local Chroma database; it uses four CPU threads, `num_gpu: 0`,
and unloads immediately afterward. Semantic duplicate checks compare a staged
candidate only with that approved collection. The chat can inject at most two
provenance-labelled approved examples, under an 800-token cap. The local linter
rejects malformed workflows, Midjourney parameters, short video prompts, exact
duplicates, and semantic duplicates above 0.90. Low-performing approved examples
are reversibly archived, never deleted.

The retrieval component is pinned in
`local_agent/requirements-exemplar-retrieval.txt`. It consists of ChromaDB and
the local `nomic-embed-text` Ollama model; neither provides cloud retrieval or
downloads external examples.

## Operator evaluation cases

The agent never turns ordinary chats into a benchmark. To assess tool choice,
grounding, recovery, or planning with a real model, first write an **anonymized**
case JSON file and stage it deliberately:

```powershell
python local_agent\operator_eval.py stage case.json
python local_agent\operator_eval.py approve <case-id>
python local_agent\operator_eval.py score <case-id> captured_answer.txt --tool search_docs
```

Cases with absolute paths or email addresses are refused. Approval is a local
pending-to-approved move; scoring evaluates only the tool names and phrases the
operator specified. It does not run a model, access a conversation, or start a
render, so it is safe to use as a review gate before a separately requested
live evaluation.

## The thermal cap

The CPU tier runs on four of sixteen logical processors, matching
`work/run_open_interpreter_handoff.py`. `CLAUDE.md` makes that cap and the ban on
a second concurrent local model the CPU safeguards, because Windows exposes no
usable package-temperature sensor on this machine. **Do not raise it.**

Interactive chat uses a modest five-minute Ollama retention window. Internal
planning and queued Ollama vision calls use zero retention, while the dedicated
llama.cpp VLM is released as soon as its media batch drains. This prevents a
background task from quietly holding VRAM after its result is delivered.

## Why there is nothing to install

You are on a phone hotspot and the standing rule is to state the size before
downloading anything. So: no Electron, no Tauri, no FastAPI, no Flask, no npm, no
`requests`, no `ollama` package. `http.server` and `urllib` from the standard
library, plus one self-contained HTML file.

The only thing that must already be on disk is Ollama. The chat client itself
**never pulls** a model during a request. The desktop launcher performs one
explicit startup check for its configured CPU model
(`huihui_ai/qwen3-abliterated:8b`, or `EQUAL_SHARES_CPU_CHAT_MODEL` when set):
if it is missing, it pulls that one model before the GUI opens. This makes the
CPU fallback usable from a cold start without allowing arbitrary chat requests
to trigger downloads. Only explicitly abliterated models are chat choices; a
stock model is never used as a compatibility fallback. Two extra picker rows
are opt-in and never automatic fallbacks: the GPU-only Ollama model
`gpt-oss-20b-heretic` (installed only by its dedicated script), and
`powerinfer-local` (not an Ollama pull; the launcher never starts its proxy
or `server.exe`).

---

## The honest part: what a 14B CPU model can and cannot do

It is not me. Pretending otherwise would waste your time, so here is the split.

**It is good at:** answering "where are we", looking up a clip, explaining a rule
and why it exists, reading state, choosing which script to run, and catching
itself when it is about to break a rule.

**It is not good at:** writing correct code, reasoning across the whole tree, or
producing a 4,600-character prompt with every reference tag numbered right.

So the architecture puts the model where it is safe:

```
     you ──▶ model ──▶ picks a TOOL ──▶ deterministic Python does the work
                                    ──▶ result ──▶ model explains it
```

**The model chooses; the project's own Python produces.** Prompts come from
`build_native_r2v_prompts.py`, voice classification from
`classify_voice_requirements.py`, ladder rungs from `duration_ladder.py` — the
same code that produced the current 124 prompts.

The one place the model writes something is `draft_prompt()`, and that output is
run through `validate_h3_prompt.py` before you ever see it, with every failure
listed and the deterministic fallback named.

## The safety net

`validate_h3_prompt.py` is the most important file here. It encodes every rule
this project learned from a failed render, and it is measured, not assumed:

- passes **124/124** of the current known-good prompts — no false positives
- catches **9/9** deliberately broken ones: prepended header, split `<d>` block,
  delivery prose after `</d>`, missing section, sections reordered, beat
  brackets, wrong `<Audio N>` count, undeclared tag, missing `[English]`

Nothing the model writes reaches a render without passing it.

*(Building it caught me out twice, which is the point. My first version flagged
the correct mouth-close clause as a fault and failed 12 of 124 good prompts —
the seventh checker in this project to measure the wrong thing. My second scanned
only `detailed_description` for beat brackets and missed one in
`subject_definitions`.)*

## File and web access

The agent can read and write files and access the internet, the same way
ChatGPT Desktop does. Ask it in plain language:

- *"Read my notes at C:\Users\rhine\Desktop\notes.txt"* → `read_file`
- *"Save this to work/my_script.py"* → `write_file`
- *"Run this Python snippet and fix the error"* → `run_code` (sandbox only)
- *"List what's in the outputs folder"* → `list_dir`
- *"Look up how to use MiniMax H3"* → `web_search`
- *"Research this with sources and citations"* → `deep_research`
- *"Fetch https://example.com and summarize it"* → `fetch_url`

`web_search` uses the selected **search backend**. Default is DuckDuckGo
(`EQUAL_SHARES_SEARCH_BACKEND=duckduckgo`, no key). Structured `{title,url,snippet}`
results are formatted as text for back-compat. To swap in Brave, Serper, Tavily,
or xAI later: implement the ~20-line `SearchBackend` class already stubbed in
`search_backend.py`, set `EQUAL_SHARES_SEARCH_BACKEND` and
`EQUAL_SHARES_SEARCH_API_KEY`. The deep-research loop does not change.

`deep_research` plans sub-queries, fetches several pages via `fetch_url`, and
returns JSON `{question, answer, sources, sub_queries, rounds_used, backend, notes}`
with URL citations. Caps: 4 rounds, 12 sources, 90 seconds. It is token-heavy and
routes through the existing GPU/CPU router — it will not force the 14B onto a
card a render owns. Prefer it when the GPU is free; use `web_search` for a
single lookup. Fetched page text is untrusted evidence, never executable
instructions. A citation URL not among the fetched sources is removed before the
answer reaches the chat.

Tool cards and their result cards are the live proof of local work. The server
also retains concise per-turn tool-result metadata with the assistant message,
without saving tool arguments. The assistant must not claim an action was
completed unless a permitted tool returned evidence for that action. It refuses
paywall, login, license, activation, and other access-control bypass requests;
it does not modify third-party software to obtain restricted access.

`write_file` refuses to overwrite protected project records (manifests, audit
files). Everything else is writable. Internet access requires a connection — the
tool reports the error cleanly if offline.

`run_code` is the only code-execution surface. Each call gets an isolated
`local_agent/sandbox/run_<id>/` directory. On Windows the interpreter starts
at low integrity inside a job that allows one process and caps memory, so it
cannot write a normal user file and cannot start a child interpreter. Python
may read its own install so imports work; other reads are refused in-process.
Node's permission model allows filesystem access only in that run directory
and refuses child processes. Python sockets are disabled in-process.
`allow_network` is refused. This Node build has no network permission flag,
so a JavaScript process can still open a socket; it cannot write outside the
run directory or start another program. Parent secrets
are not copied into the child environment. A hard timeout (30 s default, cap
120 s) kills the job. A `path` outside `sandbox/` is refused, including
anything under `outputs/equal_shares/`. CPU only (`CUDA_VISIBLE_DEVICES=-1`).
Desktop-only; phone identities are default-denied.
`write_candidate_tool` still cannot run or replace project code — copy a
candidate into the sandbox to try it. Sandbox run dirs may be pruned; nothing
outside `local_agent/sandbox/` is touched.

When a message includes a public `http://` or `https://` URL, the app fetches the
page before the model replies and shows the result as an action card. A fetched
page is not placed into persistent memory automatically; say **“remember that…”**
with the specific fact you want to keep.

## What it cannot do

- **Start an unguarded render.** A desktop chat can start only the fixed
  preflighted general batch-render action from a supplied real job folder, or
  build from the current chat's complete validated prompt set. It still refuses
  Equal Shares, phone-originated, duplicate-backend, or failed-preflight
  renders. One ComfyUI, ever.
- **Delete anything.** The reset tool is deliberately not exposed.
- **Run arbitrary commands.** Every action is a named entry with fixed argv.
  The only live interpreter is `run_code`, and it is walled to
  `local_agent/sandbox/run_<id>/`. Tested: unknown tools, path traversal in a
  clip id, arbitrary doc reads, injected shell strings, a path outside the
  sandbox, and a script that opens a project file are all refused.
- **Invent missing senses.** The configured `qwen25-vl-nsfw-caption:v4-q4_k_m` model genuinely analyzes
images and video frames. Video analysis defaults to an exact observation at each
second plus an adjacent-frame action comparison, so a 5–8 second reference has
a prompt-ready visual-state and motion-beat timeline rather than one vague clip
summary. The dense `extract_video_actions` path gives the VLM an exact labelled
frame/time table and returns an explicit coverage report; a skipped label stays
a reported evidence gap, never an invented action. Ask for `half_second` detail
or `fps: 2` only when the extra analysis time is worth it. FFmpeg measures audio and
  extracts video metadata. The existing ComfyUI Whisper-tiny checkpoint now
  transcribes English speech offline on four CPU threads. Its cold import can
  take longer than 30 seconds on this install, so the capability probe uses a
  longer bounded timeout before deciding transcription is unavailable. Speaker matching and
  general sound-event/music recognition remain unavailable; the app says so
  instead of guessing. A visual analysis never claims what audio contains.

---

## Files

| File | |
|---|---|
| `START_LOCAL_AGENT_GUI.ps1` | the launcher — start here |
| `router.py` | GPU/CPU decision, busy detection, model eviction |
| `server.py` | stdlib HTTP server, SSE streaming, `127.0.0.1:8760` |
| `static/index.html` | the whole interface, one file |
| `agent.py` | the loop: message → route → model → tool → answer |
| `action_resolver.py` | current-turn action-resolution layer; classifies direct requests into deterministic tool plans before the model turn |
| `store.py` | conversation persistence |
| `tools.py` | the whitelist of allowed actions |
| `sandbox_runner.py` | isolated `run_code` execution (run dirs under `sandbox/`) |
| `ollama_client.py` | Ollama client, per-turn host selection |
| `powerinfer_client.py` | OpenAI `/v1/chat/completions` client used when a chat is pinned to PowerInfer |
| `powerinfer_openai_proxy.py` | loopback OpenAI adapter to `server.exe` (`127.0.0.1:8091`); not started by the launcher |
| `lxmf_agent.py` | opt-in stock-Sideband/LXMF transport bridge |
| `remote_security.py` | identity pairing, remote capabilities and audit |
| `START_SIDEBAND_BRIDGE.ps1` | starts/repairs the local app, then runs the LXMF peer |
| `capabilities.py` | detects installed vision, FFmpeg, transcription and speaker-analysis support |
| `media_tools.py` | guarded native image, audio and video analysis |
| `retrieval.py` | BM25 index over the doc tree; `search_docs` tool uses it |
| `build_knowledge_pack.py` | compiles the Equal Shares specialist reference and rebuilds the retrieval index |
| `knowledge/EQUAL_SHARES_REFERENCE.md` | generated project-only reference; injected only for explicit Equal Shares work |
| `knowledge/retrieval_index.json` | generated — BM25 chunk index (auto-rebuilt on each launch) |
| `validate_h3_prompt.py` | the safety net |
| `test_native_tool_calling.py` | stdlib regression suite for native function calling (57 tests) |
| `test_action_resolver.py` | unit + integration tests for the action-resolution layer (29 tests) |
| `test_media_analysis.py` | deterministic media capability, audio and embedded-video regression checks |
| `test_router_switching.py` | deterministic CPU/GPU handoff and resident-model eviction checks |
| `test_lxmf_bridge.py` | mocked pairing, remote denial/audit, persistence and chunking checks |
| `Modelfile.equal-shares` | `ollama create equal-shares -f` — local, no download |
| `Modelfile.qwen25-vl-nsfw-caption` | compatibility record of the explicit two-file Qwen2.5-VL Caption V4 import; the agent uses CUDA llama.cpp because current Ollama rejects this GGUF |
| `setup_qwen25_vl_caption.ps1` | opt-in 5.33 GB V4 model/Q8_0-projector download; never runs automatically |

## Vision model setup

The image and video tools use the locally imported
the explicit V4 GGUF pair from
`mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF`, kept together under
`A:\Users\rhine\ComfyUI-Shared\models\LLM\GGUF\mradermacher\Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF`:

- `Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf` — about 4.68 GB
- `Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf` — about 0.70 GB

When you are ready to make that approximately 5.33 GB download, run once:

```powershell
.\local_agent\setup_qwen25_vl_caption.ps1 -Download
```

The script refuses to overwrite an existing usable model file. The media
watcher—not the desktop launcher—starts a private CUDA llama.cpp server on
`127.0.0.1:11436` with both paths explicitly supplied **only for an actual
queued image/video batch**, then releases it when the batch drains. Ordinary
startup and ordinary text chat never load the vision model. Current Ollama rejects this GGUF's compatibility
metadata, so it remains the CPU/GPU reasoning runtime rather than the VLM
runtime. The vision client sends an OpenAI-compatible structured image turn
with separate system and user roles; it does **not** paste raw image-token
markup into prompts because llama.cpp applies the model's native Qwen2.5-VL
template itself.

`starsfriday/Qwen-Image-NSFW` is an optional diffusion LoRA, not a vision
caption model. The agent records its expected checkpoint location as
`ComfyUI-Shared\models\diffusion_models\qwen_image_nsfw.safetensors`, but never
loads or downloads it at startup. It can only be loaded by a future explicit
image-generation/diffusion action.

## Media GPU arbitration

The watcher is the only component that starts or releases the Qwen2.5-VL
runtime. When no render owns the GPU, `router.plan_vision_vram()` applies this
order: coexist with idle chat when a tier fits; otherwise yield the resident
14B chat model toward its 8B fallback; otherwise evict idle chat; then drain
the pending vision/video batch and release the VLM. A streaming chat is never
interrupted, and a render always wins. **Clear pending media queue** remains
intentionally narrow: it preserves cancelled records and never deletes uploads,
results, or evidence.

## Storyboard image planning

`work/image_render.py` is the new general still-image graph planner. It builds
and validates core ComfyUI text-to-image or reference image-to-image graphs from
the live node catalogue. `--plan` is read-only and never loads a checkpoint.
The execution route requires explicit model-load authorization, launches only
its own temporary core-node backend, refuses an existing ComfyUI backend or
render owner, and will keep all generated work
under `outputs/stories/`. Its current photoreal workhorse is the checksum-verified
`RealVisXL_V5.0_fp16.safetensors`; it is not a chat, vision-analysis, or H3 model.
The agent can prepare a **read-only** storyboard-still image plan for that exact
checkpoint. A plan has no model load, GPU action, file write, or output image;
actual image generation remains an explicitly approved isolated-renderer action.

`work/character_library.py` provides the next identity foundation: a no-GPU
training planner and an adult-consent-gated character registry. It does not run
kohya_ss, download identity models, or start LoRA training. A real identity
workflow remains a separate approval gate.

`work/storyboard_from_story.py` persists the general storyboard's character and
shot plan with a hard reference-sheet approval gate. It cannot release a frame
plan until every listed character has a recorded sheet and the operator confirms
the overview. It never invokes an LLM, a model, ComfyUI, or a renderer.
Desktop chat tools expose that same pending-review → sheets → explicit approval
→ read-only frame-plan sequence. Phone identities are default-denied for its
state-changing steps.

## Keeping it current

The Equal Shares reference is **generated from the project's own state files**,
never hand-written, because a hand-written brief drifts and drift is what caused
the 2026-08-17 fault. The launcher rebuilds it on every start, but ordinary
chats do not receive it. After any Equal Shares state change:

```powershell
python local_agent\build_knowledge_pack.py
```

## Android / Sideband — Tier A workstation bridge

Phase 1 is built. A stock Sideband app can use the workstation as an LXMF peer;
HTTP still binds only `127.0.0.1`, and the bridge is opt-in rather than started by
the normal desktop launcher. The workstation's persistent LXMF address is:

```text
2adc394dd3e580e4965aa88aa7b67cc4
```

On the phone, copy its own Sideband LXMF address. Pair that address on the
workstation (32 hexadecimal characters), then start the bridge:

```powershell
python local_agent\remote_security.py add PHONE_LXMF_ADDRESS --name "My phone"
.\local_agent\START_SIDEBAND_BRIDGE.ps1
```

In stock Sideband, add or discover the workstation address above and send it a
message. `START_SIDEBAND_BRIDGE.ps1` uses the workstation's active Wi-Fi adapter
through Reticulum AutoInterface; the phone and workstation should be on the same
Wi-Fi/LAN, with AutoInterface enabled in Sideband. HTTP remains restricted to
`127.0.0.1` and is never exposed to the LAN. On its first Wi-Fi launch, Windows
asks once for administrator confirmation to add a local-subnet-only
UDP rule for Reticulum discovery ports 29716/29717 and data port 42671. The rule also
allows IPv6 link-local (`fe80::/10`) traffic, which AutoInterface uses only on the
current Wi-Fi link. The first accepted phone turn creates
a normal persistent local-agent conversation, with every message marked
`source: phone`; the same chat file remains readable by the desktop GUI.

Unless an operator explicitly pins a model to that paired phone identity, each
phone message uses the same live automatic GPU/CPU policy as a desktop message.
If the first message arrives while ComfyUI owns the GPU, the bridge may create
the saved chat with the CPU fallback as its display model, but it does **not**
make that fallback permanent: a later message rechecks GPU ownership and uses
the normal GPU reasoning model when it is available. A phone status that says
"temporary CPU fallback while ComfyUI reserves the GPU" describes that current
turn only.

For a paired phone, the exact request `cancel the active phone schedule` is
handled immediately by the bridge. It cancels only active schedules belonging
to that verified phone identity through the normal scheduler tool boundary; if
there is nothing active, it says so. Other scheduling requests remain ordinary
tool-calling agent turns.

Phone identities can chat and use read/sensory tools by default. File writes,
code execution (`run_code`), builds, memory changes and render proposals are
denied unless the desktop grants that exact tool to that exact identity:

```powershell
python local_agent\remote_security.py list
python local_agent\remote_security.py grant PHONE_LXMF_ADDRESS write_file
python local_agent\remote_security.py deny PHONE_LXMF_ADDRESS write_file
python local_agent\remote_security.py revoke PHONE_LXMF_ADDRESS
```

The checked-in Wi-Fi profile is `local_agent/rns_wifi/config`. It uses both the
active Ethernet and Wi-Fi adapters, because this workstation is wired while the
phone is on Wi-Fi. If the phone's **Announce Stream** remains empty after a
minute, use Sideband's **☰ → Preferences → Connectivity → Connect via TCP**
toggle and enter host **192.168.50.208**, port **4242**. Restart Sideband's RNS
service (or restart the app if that button is absent). That is a local-subnet-only
Reticulum fallback for routers that isolate Wi-Fi multicast; it does not expose
the web GUI, which remains at `127.0.0.1`. If Windows replaces an adapter and
its internal identifier changes, update the matching `devices` entry before
restarting the bridge.

On this workstation the first live phone connection was verified through the
more restrictive `Equal Shares Sideband LXMF Phone 192.168.50.80` firewall rule:
only that phone address can reach TCP 4242. The launcher recognizes that rule
and will not ask to broaden it. If the phone receives a new Wi-Fi address,
apply `local_agent/APPLY_SIDEBAND_PHONE_FIREWALL.ps1` as administrator after
updating its `$PhoneIp` value; do not replace it with an open LAN or HTTP rule.

### Away from home: paired LoRa nodes

The intended primary remote route is the paired **ESP32 LoRa V3** boards: one
Bluetooth-connected to the phone and one Bluetooth-connected to the workstation.
Bluetooth is the host-to-radio link; Reticulum/LXMF messages travel over LoRa.
Before enabling that route, verify that both boards actually run compatible
**RNode firmware** and have matching legal radio settings (frequency, bandwidth,
spreading factor, coding rate, and any network name/passphrase). Those values
must be read from the physical nodes and configured deliberately; this bridge
does not guess or overwrite radio settings. The Wi-Fi/TCP route above remains a
nearby-house fallback only.

The desktop GUI can start only the fixed guarded general batch-render action after
an explicit operator request and a valid non-Equal-Shares job-folder preflight.
For a folderless "render it" request, it can instead prepare a fresh job from the
same chat's latest complete prompts, earlier attached character/setting images,
and earlier source-video chunks; the immutable job copy is placed under
`local_agent/render_jobs/` and goes through the same validation and launch gate.
Phone rendering is **default-deny**, even for paired identities. A desktop
operator may explicitly grant one exact paired identity only
`start_current_chat_render`; that lets the authenticated phone request the
same chat-derived general render without exposing HTTP or granting broad file,
build, or stop privileges. It still requires an explicit render request, the
normal non-Equal-Shares job validation, queue/port/thermal preflight, and the
global GPU gateway must not be set to **Block**. Revoke it at any time with:

```powershell
python local_agent\remote_security.py deny <phone-lxmf-identity> start_current_chat_render
```

Every remote tool attempt, including unknown and denied calls, is appended with redacted arguments to
`local_agent/runtime/lxmf/remote_tool_audit.jsonl`. Pairing changes have their own
append-only audit. Refused first-contact attempts record only the verified sender
delivery address and request ID in `runtime/lxmf/unpaired_attempts.jsonl`, never
the untrusted message content; an operator must still explicitly pair it. The
Phase 0 design is preserved in
[`UPGRADE/notes/sideband_agent_stack.md`](UPGRADE/notes/sideband_agent_stack.md).

### If a render needs to be stopped

The desktop sidebar has a red **Stop ComfyUI render** control. It asks for a
confirmation, sends ComfyUI an interrupt first, then stops only the active batch
runner and positively identified local ComfyUI processes. It releases the batch
queue lock when that runner is no longer live. It does **not** delete, move, or
alter prompts, uploads, source media, partial renders, or Ollama/local-agent
processes. If ComfyUI was launched elevated, Windows will show its normal UAC
consent prompt so the same fixed stop helper can finish the job; it never
inherits arbitrary model-provided commands. The same fixed action is available
to a desktop chat with `stop render` or `kill ComfyUI`; phone identities are
always denied it.

### Phone media now

The bridge accepts media from the **paired** Sideband contact using the stock
Sideband attachment controls. It writes a new immutable copy beneath
`local_agent/uploads/lxmf/<request-id>/`; chat JSON contains only the resulting
local path and metadata, never binary media. The agent is directed to use its
existing local sensory tools before answering:

- **Photo / image:** select an image attachment, or use Android's Share action
  from the camera/gallery into Sideband. The workstation uses `see_image`.
- **Voice message:** use Sideband's microphone attachment. The workstation
  measures it, then uses local Whisper when speech is present.
- **Video or other file:** choose **File Attachment**. `.mp4`, `.mov`, `.mkv`,
  `.webm`, and related formats route to the video tools; audio/image extensions
  route to their corresponding tools.

The attachment must be no larger than 75 MB. A phone attachment does not grant
write, build, memory, or render privileges, and an unpaired sender is refused
before any attachment is written. Received-file audit rows retain only timestamp,
identity, file metadata, and SHA-256 in
`runtime/lxmf/attachment_audit.jsonl`.

While a phone request runs, Sideband receives short status messages for the
selected workstation tier and each local tool, then the final answer. Raw token
streaming, tool arguments, tool results, file paths, and partial reasoning are
never sent as status messages.

If a media tool safely queues instead of taking the GPU, Sideband first receives
the queue acknowledgement. When its durable media job finishes, the bridge sends
the completed caption, transcript, or action log back to the same active paired
phone chat exactly once. The return path is authenticated from the phone request
at the tool-dispatch boundary; it never turns a media attachment into a write,
build, or render permission.

The official Sideband source is present at `local_agent/vendor_sideband` under
its CC BY-NC-SA license as the base for the local derivative APK. Stock Sideband
already supplies secure file/image/microphone delivery, so no Android model or
cloud service is required for the first media workflow. The local fork now adds
an Android-only **Capture Camera Image** attachment action: it asks for camera
permission only when selected, then sends the result through the ordinary
Sideband image path. The source overlay is checked, but no Android toolchain or
APK has been built yet. See `SIDEBAND_TIER_B_BUILD.md` for the required build
and phone acceptance steps.

## Terminal instead of GUI

```powershell
python local_agent\agent.py
```

## General still-image model choices

The guarded still-image tools have two explicit profiles. `realvisxl` remains
the default complete SDXL checkpoint. `realpro_flux` is the operator-provided
Flux **UNet-only** model at
`A:\Users\rhine\Downloads\realProV3_realProV3Unet.safetensors`; it is loaded
only with Flux `clip_l.safetensors`, `t5xxl_fp16.safetensors`, and
`ae.safetensors`. It is text-to-image only for now and must never be loaded as
an SD 1.5 checkpoint.

Example tool argument: `"model_profile": "realpro_flux"`.

`alicemix_sd15` is a separate complete SD 1.5 checkpoint at
`A:\Users\rhine\Downloads\realAlicemixV1_v10.safetensors`, **not** a LoRA
for RealVisXL. Its recorded baseline is 30 steps, DPM++ 2M Karras, CFG 11, and
the supplied detailed-light/RAW prompt terms. The documented
`realesrgan-x4minus` upscaler and negative embeddings are not installed, so
the renderer does not silently substitute them; its first profile is base-pass
only until those exact assets are supplied.

## Regression tests

Stdlib only, no Ollama needed. Run after any change to `agent.py`, `tools.py`,
`ollama_client.py`, or `store.py`:

```powershell
python local_agent\test_native_tool_calling.py
```

Expect the current suite to pass. They cover the tool schemas and enums, `tools=`
forwarding, multiple tool calls in one hop, the legacy `TOOL:` fallback, the
guard rails, conversation persistence, GPU-snapshot reuse after read-only tool
calls, the execution-first retry, and the stop path. This is the automated form of the manual checks in
`CHANGELOG/2026-08-19_native_function_calling.md`.

For the bounded full local-agent sweep and the required isolated worker-farm
command, use `docs/LOCAL_AGENT_REGRESSION_RUNBOOK.md`.

## If something is wrong

| Symptom | Cause |
|---|---|
| "ollama not running" | run the launcher; check `local_agent\ollama_cpu.err.log` |
| Always on CPU, never GPU | expected if `nvidia-smi` is not on PATH — it fails safe. Run `python local_agent\router.py` to see which signal is firing |
| "has no models" | run the launcher; it verifies the configured Huihui Qwen3 abliterated CPU 8B model before opening the GUI |
| PowerInfer row disabled | proxy `127.0.0.1:8091` or `server.exe` on `127.0.0.1:8080` not listening. The router does not start them. Read the picker hint or `python local_agent\router.py` |
| Replies are slow | expected. 14B on four CPU threads is a few tokens a second; that is the cost of leaving the GPU alone |
| It invents a fact | verify the selected model advertises Ollama's `tools` capability. If it does, rebuild the knowledge pack; models without it use the legacy fallback |
| Replies are poor | use the configured Huihui Qwen3 abliterated pair; 14B is preferred when the GPU is idle and 8B is the CPU-safe fallback. Do not substitute a non-abliterated model in the agent configuration. |

## First live run — what was verified (2026-08-19)

Run against a real Ollama, real GPU (RTX 5080), real project data.

**Verified:**

- `nvidia-smi` parsing confirmed against real output: GPU = RTX 5080, 16303 MB
  total, 387 MB idle / 5704 MB with ComfyUI loaded. Both readings parsed
  correctly with `--query-gpu=memory.used --format=csv,noheader,nounits`.
- **Port 8188** busy signal: ComfyUI running → GPU correctly flagged BUSY.
- **Queue-owner PID** busy signal: wrote live PID, confirmed `gpu_busy()` returned
  True with correct process name; dead PID did not trigger it.
- **nvidia-smi VRAM** busy signal: 5704 MB > 2500 MB threshold → BUSY.
- **Browser false-positive fixed:** `nvidia-smi --query-compute-apps` lists Brave
  Browser as a compute process on Windows WDDM. Without the fix this would have
  kept the GPU permanently marked busy. `_BROWSER_NAMES` filter resolves it.
- **GPU model evicted** when routing to CPU: route event showed
  `"unloaded_gpu_model": "qwen2.5-coder:14b"` in the first live conversation.
- **Stop** mid-generation: message halted at 44 chars, `[stopped]` appended, saved.
- **Regenerate**: re-ran correctly from same user message.
- **Attachments**: file content inlined and model read it correctly.
- **New chat / persist / rename / delete**: all working; deleted chats in
  `chats/_deleted/`.
- **Guard rails** (5/5): unknown tool, path traversal clip id, `/etc/passwd` doc,
  `rm -rf /` build action, unknown GPU action — all refused.
- **Prompts**: 124/124 still valid after all code changes.
- **Voice classification**: 18 speakers = 10 recurring + 8 one-off, unchanged.
- **draft_prompt**: validator correctly caught missing `<Audio 1>` in model draft;
  `safe_to_use: false`, fallback named.
- **Legacy tool calls**: the old text protocol remains only as a parsing
  compatibility path for a model response that explicitly uses it. It is not a
  recommended model-selection path.

**Current model policy (supersedes the 2026-08-19 recommendation):** The default
reasoning pair is `huihui_ai/qwen3-abliterated:14b` on the idle GPU and
`huihui_ai/qwen3-abliterated:8b` on CPU while ComfyUI owns the GPU. Separate
opt-in picker rows, never automatic fallbacks: the exact GPU-only
`gpt-oss-20b-heretic` imported by its dedicated installer, and
`powerinfer-local` (GPU-only, text-only; picker contract only until an
accepted sparse model exists). Native function schemas are passed on every
Ollama turn; a PowerInfer pin does not send them. The exact Qwen2.5-VL
Caption V4 GGUF pair is a lazy media tool, never a chat model.

**One gap remaining — live idle-GPU checks:**
ComfyUI is currently active, so neither the idle-GPU 14B route nor a live
Qwen2.5-VL caption has been exercised in this session. Do not stop a render to
test them. Once the GPU is naturally free, run the documented guarded checks.
# Media production accuracy

Reviewed prompt-pack stills pass through `media_accuracy_gate.py` before they
can feed the video phase. The gate is deterministic (file decode, minimum size,
4:3 framing, non-blank pixels, and prompt-control assertions) and records hashes
and reasons in production progress. Mechanical success is not semantic success
or approval. The production worker records semantic_check: not_run and leaves
stills unapproved until the exact Qwen2.5-VL Caption V4 lazy llama.cpp review
provides a hash-bound verdict. No substitute vision model is allowed.

The worker accepts only its unique result receipt, never stdout JSON or an old
PNG scan. Each media attempt and QA/failure record has a new directory; ledger
history is preserved. Explicit operator approvals are versioned under the task's
approvals/<source_sha256>/ directory. record_explicit_approval refuses incomplete
semantic QA; a request for full production is not still approval.

Video jobs bind physical approved paths and SHA-256 hashes. Clip N's approved last
still is clip N+1's first reference. Both are copied to unique backend input names
and rehashed. The production adapter requires a live 4:3 ResolutionSelector choice.

start_supervisor also starts an independent watchdog. After 1200 seconds without
progress or owned log activity, it snapshots the ledger, owner, last 100 log lines,
and startup diagnostics, records failure, and prevents another attempt. It never
kills an unknown process. acknowledge_watchdog requires a recorded diagnosis,
a dead supervisor/backend, and a free port before allowing a later retry.
See docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-15.md for current evidence and limits.
