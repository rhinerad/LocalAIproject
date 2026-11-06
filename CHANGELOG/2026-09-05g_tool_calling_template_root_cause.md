# 2026-09-05g — DeepSeek-14B / Coder-14B tool-calling gap: root cause found

## Scope

🔴 lane. Diagnosis only, no code/prompt/router changes this pass — the
report explicitly confirms `CODING_RULES` and the reasoning prompt were
not touched, per instruction.

## Root cause

Template/capability mismatch, not a prompt-wording problem. Ollama 0.32.15
advertises `capabilities: tools` for both failing tags, but that flag
reflects `/api/show`'s GGUF Jinja `tokenizer.chat_template`, not the actual
Go renderer `ollama show --modelfile` prints and inference uses. The two
tags diverge:

- **DeepSeek-14B** (`huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M`):
  the live Go template is DeepSeek-R1 chat only — never reads `.Tools`,
  `.ToolCalls`, or `role=tool`. The model never sees a function-calling
  protocol at all. Live symptom: invented file contents instead of calling
  `read_file`, `inner_tools_executed: []`.
- **Coder-14B** (`josiefied-qwen2.5-coder-14b:q4_k_m`, the 2026-09-04h GGUF
  import): the template does inject `.Tools` and instructs `<tool_call>`
  XML, but is missing the official Coder template's "no other text / no
  backticks" constraint. Live symptom: the model correctly tried to call
  `run_code`, but emitted it as markdown-fenced JSON in `content` instead
  of `<tool_call>` XML, so Ollama never promotes it to `message.tool_calls`.

The existing native-first/`TOOL:`-fallback parser (`docs/adr/0002-native-ollama-tool-calling.md`)
already ran on both live turns and matched neither output shape. Teaching
either model `TOOL: name {json}` via `CODING_RULES` would be a prompt
workaround for a template gap and was explicitly ruled out.

## Proposed fix (not yet built)

- **Coder — high confidence, cheap.** Re-`ollama create` the same Q4_K_M
  GGUF with the official `qwen2.5-coder:14b` template (already local on
  the workstation), which includes the missing no-backticks/no-other-text
  line. No new download, no weight change.
- **DeepSeek — necessary but lower confidence.** The Huihui tag's template
  has no `.Tools` branch at all; a fix requires injecting tools using
  DeepSeek-R1's own special tokens, not Huihui's Qwen3 ChatML template
  (wrong tokens if copied directly). A community reference exists
  (`aleshribar3/deepseek-r1-tool-calling:14b`), but DeepSeek's own
  function-calling guidance describes R1-style tool calling as unstable
  even with a correct template — this may still invent answers after a
  template fix.

## Recommendation from the report

Retag Coder first (cheap, high odds), re-verify case 3. Treat DeepSeek as
reasoning-only until a DeepSeek-format tools template is proven live in a
real test; route logic-flavored tool-using hops to Huihui-14B in the
meantime, since it already emits native `tool_calls` correctly.

## What was not done

No router, `CODING_RULES`, or prompt edits. No retag performed yet.

## Open decision for the operator

Whether to (a) dispatch the Coder retag now (low risk, high odds) and (b)
whether to also attempt the DeepSeek community-template experiment now or
defer it, and in the meantime whether `router.py`'s `CAP_LOGIC` routing
should temporarily prefer Huihui-14B over DeepSeek-14B until DeepSeek's
tool-calling is proven live.
