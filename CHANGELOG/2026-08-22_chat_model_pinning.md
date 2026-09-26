# Per-chat model selection and pinning — 2026-08-22

## Result

New chats now expose a `Model for this chat` picker populated from installed,
approved conversation models. The choice becomes immutable after the first
message and persists in the chat JSON across reloads and app restarts.

## Behavior

- The model is selected at the beginning of each new chat.
- Reopen, continue, Stop, Regenerate, attachments, and persistence retain it.
- CPU/GPU routing may move the selected model between tiers only when that exact
  model is installed on both tiers.
- The router never silently substitutes another model.
- A CPU-only model stays on CPU even when the GPU is free.
- A GPU-only model refuses safely while the GPU is reserved rather than falling
  back to a different CPU model.
- Sensory models such as `qwen3-vl-abliterated:8b-q8_0` are excluded; image and
  video analysis continues to invoke them through media tools.
- Legacy chats without a saved model are pinned once on their next message.

## Live installed choices

- `qwen3:8b` — CPU + GPU
- `qwen2.5-coder:14b` — CPU + GPU
- `qwen3.6:latest` — CPU only
- `dolphin3:latest` — CPU only

## Verification

- Live GUI: selected `qwen2.5-coder:14b`; first response header reported GPU +
  that exact model and the picker locked.
- New Chat unlocked the picker.
- Reopening the saved chat restored the locked `qwen2.5-coder:14b` selection.
- Regenerate again used GPU `qwen2.5-coder:14b`.
- API rejected the Qwen3-VL watcher as a conversation-model selection.
- Router pinning suite: 6/6 pass, including CPU/GPU movement and no-substitution
  refusal cases.
- Native tool suite: 8/8 pass.
- Media suite: 6/6 pass.
- General-assistant scope suite: pass.
- H3 prompts: 124/124 valid.

No downloads occurred. ComfyUI and the render pipeline remained stopped.
