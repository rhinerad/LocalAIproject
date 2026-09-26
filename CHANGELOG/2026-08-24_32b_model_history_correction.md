# 2026-08-24 — 32B local-agent model history correction

## What changed

- Corrected `local_agent/README.md` and the CPU-handoff changelog so they no
  longer imply that a 32B model was only a ComfyUI MiniMax H3 encoder.
- Recorded the distinction between the H3 encoder and the historical local-agent
  vision/action model `huihui_ai/qwen3-vl-abliterated:32b`.
- This is a documentation correction only. It does not download, remove,
  register, select, or load any model, and it does not start a render.

## Why

The operator correctly reported using the 32B model in the local agent on the
previous day. A later CPU-handoff note conflated that historical VLM with the
separate `qwen3vl_32b_minimax_h3_*` ComfyUI text encoder.

## Evidence

- `2026-08-23_abliterated_models_only.md` records that
  `huihui_ai/qwen3-vl-abliterated:32b` was pulled successfully (20 GB, Q4_K_M)
  with vision, tools, and thinking capabilities.
- `2026-08-18e_local_agent_gui.md` records the earlier idle-GPU routing to a
  32B model on the card.
- `2026-08-24_qwen25_vl_caption_setup.md` records the newer explicit decision:
  replace the 32B action-extraction path with the exact
  `mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF` pair, because the 32B VLM
  could CPU-offload. That newer configuration is the current visual-action
  policy.

## Verification

- Re-read all three dated records above and reconciled their model roles.
- Confirmed the documentation now distinguishes historical 32B local-agent VLM,
  current exact Qwen2.5-VL V4 visual runtime, and separate H3 encoder.

## Still unverified

- Whether the old 32B Ollama tag and files remain locally recoverable is not
  established by the current server tag list. No assumption has been made and
  no model has been altered.
