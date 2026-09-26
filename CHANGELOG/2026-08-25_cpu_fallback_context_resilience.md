# 2026-08-25 — CPU fallback context resilience

## Fixed

The local agent's CPU-safe route used an 8,192-token context even though the
reviewed always-on policy plus the native tool schemas need approximately 9,600
tokens before an operator request is added. This made an ordinary GPU-busy turn
start over budget and repeatedly show an unhelpful context warning.

- Raised the CPU-only Ollama request context from **8,192** to **16,384**
  tokens. CPU thread and GPU safeguards are unchanged: four CPU threads and
  `num_gpu: 0` remain mandatory.
- Added deterministic clipping for oversized tool evidence after old history is
  compacted. The current request and the newest tool evidence are retained;
  raw listings or JSON no longer crowd out the answer.
- The optional structured task planner now runs only when the GPU is free and
  the GPU Ollama server is available. When ComfyUI owns the GPU, the agent uses
  its existing deterministic task record directly instead of starting a second
  CPU model request that can time out before the real reply.
- Removed the recurring operator-facing “task plan kept deterministic” timeout
  note. A skipped optional plan is normal resilience behavior, not an error.

## Verification

- `python local_agent/test_agentic_state.py` — 9/9 passed, including the new
  busy-GPU planner-skip regression.
- `python local_agent/test_context_resilience.py` — passed, including the
  policy+schema CPU-window assertion and oversized multi-tool evidence case.
- `python local_agent/test_router_switching.py` — 16/16 passed.

## Follow-up — visible work trace

The desktop UI now shows a live, expandable **work trace** for every turn. It
records only verifiable activity milestones: request receipt, selected compute
route, evidence review, tool use, tool-result review, and answer drafting. It
does not expose hidden model chain-of-thought or private reasoning tokens.

The trace remains available after a response as “Completed — show work trace.”
- `python local_agent/test_launcher_revision.py` — passed.
- `python local_agent/test_general_assistant.py` — 6/6 passed.

No model was loaded, no model was downloaded, and no ComfyUI work was started.

## Follow-up — model-picker capability label

The picker previously hid the GPU catalogue during a busy-GPU status poll, then
rendered the same Huihui model as “CPU only.” It now retains the last verified
GPU model inventory for display only. This does not permit GPU use while busy:
each actual turn still makes a fresh routing decision and yields to ComfyUI.

- `python local_agent/test_router_status_busy.py` — 3/3 passed.
- `python local_agent/test_router_switching.py` — 16/16 passed.
