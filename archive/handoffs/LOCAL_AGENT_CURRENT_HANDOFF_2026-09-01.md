# Local Agent current handoff — 2026-09-01

## Read order

1. `CLAUDE.md` — binding safety, evidence, thermal, and paused-render rules.
2. This handoff — current general-agent state.
3. `local_agent/README.md` — product/runtime architecture.
4. `TODO.md` — authoritative execution queue.
5. `CHANGELOG/README.md` — same-session evidence.

## Current state

Equal Shares remains a preserved, paused specialist profile. Do not resume its
audio pipeline, launch a Stage-1 render, or alter evidence/manifests. The active
product is the local general-purpose assistant.

### Native tool-loop responsiveness

Read-only tools returned together from one native tool-call hop now share the
same bounded GPU-status snapshot for their immediate follow-up model turn.
Any tool outside the reviewed read-only allowlist forces a fresh GPU check.
Cross-chat retrieval runs only for an identified conversation, preventing an
ad-hoc request from paying latency or inheriting unrelated chat context. The
native-tool suite (45 tests), router suite (41 tests), and 124-prompt H3
validator all passed after this change.

### Current-chat render recovery

If `start_current_chat_render` reports that the current chat has no complete
fenced H3 prompt set, the agent now stops with a deterministic recovery message.
It will not let the model substitute the repository root, a different folder,
or prompts from another chat. The operator must add the complete H3 prompt set
to the current chat before retrying. The native-tool suite passed 46 tests after
this regression fix; no renderer was started by the test.

### Current-turn scope and task identity

Batch-render tools now require an explicit batch-render request in the current
operator message. Old render context cannot turn PowerInfer/calibration JSON
work into a `batch_plan` or `batch_render` call. A structured planner may refine
the visible checklist, but it may not rewrite the operator's durable task goal;
this keeps an error or a compacted transcript from silently changing the active
project. The native-tool suite passed 47 tests and the bounded task-state suite
passed after these regressions; no renderer, GPU workload, or model change ran.

Later on 2026-09-01, repeated live failures showed this was still too narrow:
the model could still mention H3/ComfyUI/rendering or pick a specialist tool
from stale history during unrelated PowerInfer/file/general turns. `agent.py`
now has a runtime specialist-scope guard, not just prompt guidance. Unless the
current operator message explicitly asks about ComfyUI, H3, MiniMax, Equal
Shares, rendering, batch jobs, story-image generation, clips, prompt sets, or an
active image/video status, the agent blocks those specialist tools before they
run and discards one stale specialist reply/tool path before retrying the actual
current request. Verified by `python local_agent\test_native_tool_calling.py`
(57 tests, 0 failures), including regressions for "continue PowerInfer" not
becoming H3/batch-render work. App revision is now
`2026-09-01-specialist-scope-guard-r74`; the launcher expects the same revision.

### PowerInfer calibration intake

For an operator-approved PowerInfer calibration JSONL, the general agent now
has `validate_powerinfer_calibration`. It validates only the existing approval
and record schema from a supplied repository-local `.jsonl` path; it cannot
start rendering, ComfyUI, PowerInfer, predictor generation, a benchmark, or a
model/registry change. The current review-only directory contains only
`operator-source-safe-subset.UNAPPROVED.jsonl`; no approved calibration JSONL
is currently present there. The next factual input is the exact approved JSONL
path (or placing that file in the review-only directory).

### Direct writes and truthful failures

A specific desktop request authorizes ordinary text-file creation/editing; the
agent no longer asks for a redundant sidebar approval for `.ini`, `.cfg`,
`.json`, `.bat`, or `.vbs` files. Protected records remain refused, phone
identities still require their explicit remote `write_file` capability, and
binary patching still needs its exact-byte approval. If any file write fails for
another reason, the agent reports that no file or directory was created rather
than carrying a nonexistent file into later validation.

### Execution-first action requests

For a direct desktop request to do a safe task, the expected behavior is now:
use the appropriate local tool, then return a concise account of what happened
and any specific blocker. If the model initially emits a command-style answer
without attempting a tool, `agent.py` appends one execution correction and asks
for tool selection before returning it to the operator. The retry happens at
most once and never bypasses protected-file, binary-edit, remote-identity,
GPU, download, or render safeguards. It also does not manufacture capability:
when a required input, permission, or external service is genuinely absent, the
agent reports that exact condition rather than directing the operator to do
work the agent can do itself.

### Failed JSONL formatting recovery

The agent now treats a tool-reported JSONL path as durable task evidence. On a
desktop follow-up such as “fix it” after `validate_powerinfer_calibration`
reports a parsing failure, it deterministically repairs only a top-level JSON
object array into JSONL at that exact path and revalidates the same file. It
will not use an ellipsis, a documentation example, or an invented replacement
path. A successful syntax conversion is not an approval or schema pass; the
agent reports any remaining structural failure and does not begin model,
predictor, GPU, render, registry, or PowerInfer work.

Saved chats now replay only bounded same-chat tool receipts as facts into the
next request. This preserves tool-discovered paths and errors across a server
restart without treating another chat as context or generating orphaned native
tool protocol messages. A 2026-09-01 reliability audit found the previous
receipt was too lossy: it kept only a 240-character text summary, which could
truncate a long Windows `.jsonl` path and make the agent fall back to a bogus
`review-only/.../approved.jsonl` placeholder. Future receipts now preserve
structured fields (`path`, `valid`, `reason`, `records`, and repair status),
and the agent can recover exact `.jsonl` paths from older truncated receipts.

The same audit fixed a Windows status-file race in `atomic_io.atomic_write_text`.
The helper now writes unique sibling temp files and retries replacement briefly,
so nearby requests do not collide on shared names such as `chat_busy.tmp`.

The ComfyUI Whisper-tiny checkpoint exists locally. Its cold import on this
machine can exceed 30 seconds, so `capabilities.comfy_whisper_available()` now
uses a longer bounded timeout before reporting transcription unavailable.

### Broad regression evidence

The 2026-09-01 reliability audit passed the full documented local-agent sweep:
471 bounded local tests, `124/124 valid` H3 prompts, and 19 isolated
worker-farm tests (1 expected skip). These checks are mocked or read-only at the
model/GPU/phone/render boundaries; no ComfyUI, render, Sideband bridge,
PowerInfer predictor, model load, or worker job was started.

### General still-image profiles

The guarded image tools now expose three mutually exclusive model profiles:

| Profile | Architecture | Model | Status |
|---|---|---|---|
| `realvisxl` | SDXL checkpoint | `RealVisXL_V5.0_fp16.safetensors` | Existing default |
| `alicemix_sd15` | Complete SD 1.5 checkpoint | `realAlicemixV1_v10.safetensors` | Static graph verified; no live output yet |
| `realpro_flux` | Flux UNet-only | `realProV3_realProV3Unet.safetensors` + `clip_l`, `t5xxl`, `ae` | Static graph verified; no live output yet |

Never attach AliceMix as a LoRA to RealVisXL: header inspection proves it is a
complete SD 1.5 checkpoint. Never load RealPro V3 through a checkpoint loader:
header inspection proves it is Flux architecture and needs Flux components.
The temporary ComfyUI catalogue probe did not reach port 8188 inside its bounded
window; its temporary processes were stopped. No image render or model load was
left running. First live renders remain guarded operator-approved work.

### SDXL LoRA preparation

`A:\Users\rhine\kohya_ss\.venv-local-agent` is ready and independently
verified with Python 3.11.15, Torch 2.7.0+cu128, and CUDA 12.8. It has not
loaded a checkpoint or trained. The remaining LoRA steps require the operator
to choose a consented objective/dataset and grant a bounded GPU smoke run.

### PowerInfer

PowerInfer remains prepared but unregistered. ReluLLaMA failed its instruction
quality packet. Bamboo-DPO has no source-backed instruction/chat template.
TurboSparse's `20260830b` edit used eight synthetic pairs and is parked: do
not generate predictors, convert, benchmark, serve, or route it until a fresh
immutable edit uses at least 32 operator-approved calibration pairs and passes
the strict quality gate plus human review.

On 2026-09-01, the separately bounded Bamboo-DPO raw-completion diagnostic
completed with CUDA/sparse evidence and released VRAM. Its receipt is
`A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake\validation\bamboo_dpo_raw_completion_20260901_113452.json`.
It is explicitly unscored and does not establish a chat template, tool calling,
or eligibility for registry, picker, or routing.

### Action-resolution layer

`local_agent/action_resolver.py` is a new current-turn classification layer that
runs in `agent.answer()` before the model generates prose. It inspects the
operator's current message plus same-chat tool evidence and returns an
`ActionPlan` (ordered `(tool_name, args)` steps) when the request maps
unambiguously to a known safe tool. If no intent matches, it returns `None` and
the normal model turn proceeds unchanged.

The two prior inline regex/special-case branches in `answer()` — JSONL repair
and ComfyUI stop — have been replaced with the resolver call. The resolver now
owns both cases and three more:

| Intent | Fired by | Evidence required |
|---|---|---|
| `comfyui_stop` | "stop/kill/abort the render" | none |
| `jsonl_repair` | "fix it / fix the formatting error" | pending failed calibration path |
| `calibration_continue` | "continue with the approved JSON" | pending calibration path, non-render turn |
| `list_dir` | "show/list/browse … folder/files" | alias or explicit path token |
| `read_file` | "read/open/view … file" | explicit path token |

All five reported failure patterns are now covered by regression tests in
`test_action_resolver.py` (29 tests total). The 57-test `test_native_tool_calling.py`
suite passes without regressions. `APP_REVISION` is `2026-09-01-action-resolver-r76`;
the launcher `START_LOCAL_AGENT_GUI.ps1` expects the same revision. No GPU, render,
model load, or PowerInfer process was started.

### Source citation contract

The agent now requires source-backed factual claims. A `# Source citation`
section in `CONVERSATION_RULES` specifies:

- **Web / internet** claims must name the URL or page title fetched.
- **Project documents** claims must cite file path and section heading.
- **Files / system state** must include the file path or directory from the
  tool result.
- **Memory and prior chats** must note that provenance explicitly.
- **Unsupported pre-training knowledge** must be labelled "from model
  knowledge" or "unverified".
- Exception: casual chat, creative writing, brainstorming, and code
  generation do not require source labels unless a specific factual claim
  is made within them.

Implementation: `_tool_source_label(name, result)` in `agent.py` extracts
provenance from six tool types (`fetch_url`, `web_search`, `search_docs`,
`read_file`, `list_dir`, `list_memory`/`remember_fact`). The label is passed
to `artifacts.prune_large_text(source_label=…)` so provenance survives context
pruning into the artifact pointer. `read_file` now prepends `[File: path]`;
`list_memory` prepends `[Source: persistent memory]`. 24 new tests in
`test_source_citation.py` cover extraction, artifact embedding, tool headers,
the citation contract, and stale H3/ComfyUI source leak prevention. All 57
existing tests and all 24 new tests pass. GUI source cards are a remaining gap.

## Remaining execution gates

Every open checkbox in `TODO.md` now needs one of these before safe progress:

- operator-provided SDXL LoRA objective/dataset or fresh GPU approval;
- real historical export source selection, archive destination/key custody, or
  approved phone/Android routing contract;
- a secondary device, Pixel, private overlay, or future worker-farm hardware;
- source-backed PowerInfer prompt-contract evidence plus explicit GPU approval;
- an operator-approved 3D ComfyUI workflow/API contract.

`docs/LOCAL_AGENT_OPERATOR_DECISIONS.md` turns those gates into a single
concise response template; it is documentation only and grants no capability.

The local retrieval index was rebuilt after the latest agent-scope and task
identity safeguards (`347 files`, `805 chunks`), so `search_docs` can retrieve
them in a later chat.

No background worker, phone, renderer, ComfyUI instance, or PowerInfer process
may be started merely to clear an unchecked box.
