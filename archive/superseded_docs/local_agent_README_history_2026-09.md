# local_agent/README.md — dated sections archived 2026-11-06

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
