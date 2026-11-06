# General-chat scope and model-role fix — 2026-08-22

## Problem

The request `write a story about huckle berry fin but fan fic` was incorrectly
treated as an Equal Shares H3 prompt task. The reply demanded sensory context and
operator approval instead of writing the story. Two causes combined:

- the entire strongly worded Equal Shares production handbook was injected into
  every request, including ordinary creative writing;
- the GPU router promoted `qwen3-vl-abliterated:8b-q8_0`, the vision watcher, to
  the primary conversation model.

## Change

- Added deterministic request scoping in `local_agent/agent.py`.
- General chat now receives compact general-assistant and media-grounding rules.
- The project handbook is added only when the conversation explicitly invokes
  Equal Shares, MiniMax H3, ComfyUI, a clip ID, duration ladders, voice locks,
  soundtrack work, native R2V, VOX, or a project path.
- Creative writing explicitly requires no attachment, sensory evidence, ear
  approval, H3 format, or voice reference.
- Project drafting forces project context explicitly.
- A substantive new user request can leave project mode even inside an existing
  project conversation; only short follow-ups inherit the immediately preceding
  project context.
- Removed the vision watcher from `router.GPU_MODELS`; `qwen3:8b` is again the
  first installed general text/tool model for GPU chat. Vision selection remains
  in `capabilities.py` for image and video tools.

## Measurement

Using Ollama's `qwen3:8b` tokenizer path with the production tool schemas and the
same one-token reply request:

- general-chat request: 3,172 prompt tokens;
- project-context request: 5,758 prompt tokens;
- handbook omitted from ordinary chat: **2,586 tokens reclaimed**.

The system text itself is 4,197 characters / 667 words in general mode versus
14,317 characters / 2,254 words in project mode.

## Verification

- Exact failed sentence through live `/api/send`: wrote a Huckleberry Finn story
  immediately; no tool call, H3 detour, sensory demand, or approval demand.
- Live route: GPU `qwen3:8b`, not the Qwen3-VL watcher.
- Live `compare the ladders for 00B and 00A`: two `duration_ladder` calls in one
  model turn; both tool cards/results reached the final answer.
- `python local_agent\\test_general_assistant.py`: 3/3 pass.
- `python local_agent\\test_native_tool_calling.py`: 8/8 pass.
- `python local_agent\\test_router_switching.py`: 3/3 pass.
- `python local_agent\\test_media_analysis.py`: 6/6 pass.
- `python local_agent\\validate_h3_prompt.py --dir outputs\\equal_shares\\prompts_native_r2v`: 124/124 valid.

No model was downloaded and no render/pipeline process was started.
