# 2026-08-30 — ReluLLaMA-7B quality-review corrections

Follows diagnosis in `2026-08-30e_quality_review_diagnosis.md`.
No GPU work, no server.exe, no GGUF touched. All changes are code and
documentation only.

---

## Files changed

### `tools/powerinfer/models.json`

**`relu-llama-7b.chat_format`: `"llama2"` → `"raw"`**

The acceptance gate's `_render_prompt` uses the `chat_format` field to select
a prompt template. With `chat_format: "llama2"`, every server-bench turn was
wrapped in `<s>[INST] {prompt} [/INST]`, which is meaningless to a base
completion model and caused immediate EOS responses. The field now reads
`"raw"`, which maps to the new `_render_prompt` branch that passes the prompt
verbatim.

`chat_format: "llama2"` is left unchanged on the retired `prosparse-7b`
entry — it can never be used as a live benchmark target.

---

### `tools/powerinfer/record_acceptance_gate.py`

**`_render_prompt()` — add `"raw"` branch**

Added an `elif chat_format == "raw":` branch that passes `user` through
unchanged. This is the format for base completion models (`class: base`) that
have no instruction fine-tuning. Without this branch, any `chat_format` that
is not `"llama3"` fell through to the `[INST]...[/INST]` wrapper — correctly
designed for chat-class models but wrong for base models.

The smoke bench already used a raw prose prompt (`"Once upon a time"` via
`main.exe -p`) independent of `chat_format`; this fix aligns the server bench
with the same behaviour.

---

### `local_agent/powerinfer_openai_proxy.py`

**`completion_payload()` — inject default stop sequences**

Before this change, stop sequences were forwarded only when the caller
explicitly included a `stop` key in the OpenAI-format request body. A
caller that omitted `stop` got no halting condition beyond the token
budget, which allowed a base model to fill the entire `n_predict` window
with EOS characters written as text tokens (`<`, `/`, `s`, `>`) rather
than the actual EOS token id=2.

Now: when the caller provides no `stop`, the proxy injects
`["</s>", "[INST]"]` by default. A caller that provides its own `stop`
list overrides this — existing behaviour for explicit callers is
unchanged.

---

### `local_agent/router.py`

**PowerInfer picker entry `kind`: `"chat"` → `"base_completion"`**

`chat_models()` labelled the PowerInfer entry as `"kind": "chat"`. The
current registered model (`relu-llama-7b.q4.powerinfer.gguf`) is a base
completion model (`manifest.json` `"class": "base"`). Labelling it `chat`
was a mislabel that misrepresented its capability to the picker and any
downstream consumer that reads `kind`. Changed to `"base_completion"` to
match `manifest.json`.

---

### `local_agent/test_powerinfer_openai_proxy.py`

Two new tests in `PowerInferProxyTests`:

- `test_default_stop_sequences_injected_when_caller_omits_stop` — asserts
  that `completion_payload()` emits `["</s>", "[INST]"]` when the caller
  omits `stop`.
- `test_caller_stop_sequences_are_not_overridden` — asserts that an
  explicit caller-supplied `stop` list is passed through unchanged.

---

### `local_agent/test_powerinfer_chat_route.py`

One new test in `PowerInferChatRouteTests`:

- `test_powerinfer_picker_entry_is_base_completion_not_chat` — asserts
  that `chat_models()` returns `"kind": "base_completion"` for the
  PowerInfer entry. Mocks `powerinfer_ready()` and `up()` so no network
  access is required.

---

### `local_agent/test_powerinfer_pipeline.py`

Two new tests in `TargetConfigTests` (replaced a draft that incorrectly
asserted `[INST]` is absent from the source file — the gate legitimately
contains `[INST]` as a chat-class template path):

- `test_base_class_model_uses_raw_format_not_instruction_template` —
  asserts `pipeline_lib.target_config("relu-llama-7b")` returns
  `class: "base"` and `chat_format: "raw"`.
- `test_render_prompt_raw_format_produces_no_instruction_tags` — calls
  `record_acceptance_gate._render_prompt([], prompt, "raw")` and asserts
  the returned string contains neither `[INST]` nor `[/INST]` and equals
  the input verbatim.

---

### `CHANGELOG/2026-08-30d_quality_review_responses_recorded.md`

Added an inline `[CORRECTED 2026-08-30f]` annotation on the sentence that
claimed "llama-2 `[INST]` wrap as the gate uses." Both parts of that
sentence are factually wrong:

1. The acceptance gate uses raw prose continuation prompts, not `[INST]`
   wrapping (evidence: `main_smoke_bench_20260830_175953.log` line 2).
2. The template actually transmitted in the quality capture was `[Inst]`
   (mixed case, closing tag missing `/`), not the canonical `[INST]`.

The original text is preserved; only the inline annotation was added.

---

## What is NOT changed

- GGUF file, predictor, activation files, and their hashes
- `validation/quality_review_packet.json` — `status` stays
  `responses_recorded`; the captures are accurate evidence and must not
  be altered
- `validation/acceptance_gate_20260830_175953.json` — throughput, FFN
  split, and VRAM results remain valid; the gate is a hardware/throughput
  gate and its conclusions are unaffected
- Production registry — not touched
- Picker pin — not set; the model is still not in the picker
- Source HF files and read-only locks

---

## Remaining operator decisions (from `2026-08-30e`)

1. Whether `class: base` models should automatically fail or bypass the
   instruction-following quality rubric (the quality review script has no
   such guard today).
2. Whether to re-run quality capture with raw continuation prompts
   (Option A in `2026-08-30e`) or reject automatically on `class: base`.
3. Whether the current `relu-llama-7b.q4.powerinfer.gguf` model should
   ever be promoted, given it cannot follow instructions.
