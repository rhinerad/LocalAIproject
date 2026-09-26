# 2026-08-30 — ReluLLaMA quality review: failure diagnosis

**Status: UNVERIFIED diagnosis — awaiting operator-approved re-run to confirm.**

Continuation of `2026-08-30d_quality_review_responses_recorded.md`.
Root-cause analysis of the 7/10 empty and 3/10 prompt-echo responses
recorded in `quality_review_packet.json`.

---

## Evidence base

Files read (no server.exe started, no inference run, no GGUF touched):

- `validation/quality_capture_server_20260830b.log` — server-side timing for the 10 `/completion` requests
- `validation/quality_review_packet.json` — the 10 prompt/response pairs
- `validation/quality_capture_meta_20260830.json` — capture session metadata
- `validation/acceptance_gate_20260830_175953.json` — acceptance gate benchmark turns
- `validation/main_smoke_bench_20260830_175953.log` — acceptance gate `main.exe` invocation
- `A:\PowerInferModels\relu-llama-7b\relu-llama-7b-source-20260829\source\hf\README.md` — model card
- `A:\PowerInferModels\relu-llama-7b\relu-llama-7b-source-20260829\source\hf\config.json` — model config
- `A:\PowerInferModels\relu-llama-7b\relu-llama-7b-source-20260829\source\hf\tokenizer_config.json` — tokenizer config
- `manifest.json` — staging pipeline classification

---

## Findings

### Finding 1 — ReluLLaMA-7B is a base model with no instruction fine-tuning

**Evidence:**

- `manifest.json` line: `"class": "base"` — the staging pipeline itself classifies this as a base model.
- `config.json`: `"_name_or_path": "meta-llama/Llama-2-7b-hf"` — this is the BASE Llama-2 model (not `Llama-2-7b-chat-hf`).
- `README.md` training data (lines 25–26): Wikipedia, Pile, StackOverflow — raw text, no instruction pairs.
- `README.md` training objective (line 29): "conventional language modeling objective and the knowledge distillation objective" — pure LM loss + KL from the base teacher. No RLHF, no SFT on instruction data, no DPO.
- `tokenizer_config.json`: No `chat_template` key. `"add_eos_token": false`. Standard Llama tokenizer with no chat format registered.

**Conclusion:** This model was fine-tuned exclusively for ReLU activation sparsity. It has no instruction-following capability and knows nothing about `[INST]` / `[/INST]` wrappers. Applying an instruction template to it is a category error.

---

### Finding 2 — The quality capture used a malformed instruction template, and the acceptance gate does NOT use instruction format

The existing CHANGELOG entry (`2026-08-30d`) states:

> "llama-2 `[INST]` wrap **as the gate uses**"

**This is incorrect on both counts.**

**The acceptance gate does not use `[INST]` wrapping.**

Evidence from `main_smoke_bench_20260830_175953.log` line 2:

```
Once upon a time, the phrase "the third age" referred to three generations: one generation
```

The acceptance gate invokes `main.exe` with a raw text continuation prompt — no template wrapper of any kind. From that same log (line 529):

```
generate: n_ctx = 2048, n_batch = 512, n_predict = 16, n_keep = 0
```

The benchmark sent plain prose continuations and measured throughput only. It never tested instruction-following behavior.

**The quality capture DID use an `[INST]`-style wrapper, but it was malformed.**

The echoed responses in `quality_review_packet.json` show the exact prompt strings the model received back:

- `constraint_following` (case 0, 128 tokens generated):
  `</s\n<s>[Inst] Give exactly three short steps for organizing a folder. Do not use bullets or headings. [Inst]</s</s...`

- `format_repair` (case 6, 128 tokens generated):
  `</s\n<s>[Inst] Repair this JSON and return valid JSON {name: local-agent, active true} [Inst]</s</s...`

- `bounded_plan` (case 7, 34 tokens generated):
  `</s\n<s>[Inst] Give a two step plan to compare two local text models. mention one measurement and one human review step.[/Inst]</s`

**Two defects in the template string:**

1. **Case error:** `[Inst]` (mixed case) instead of `[INST]` (all caps). Cases 0 and 6 show this clearly. The correct Llama-2 chat format uses ALL CAPS throughout.

2. **Missing slash in closing tag:** In cases 0 and 6, the closing tag is `[Inst]` — identical to the opening tag — instead of `[/INST]`. Case 7 has `[/Inst]` (slash present but wrong case). None of the three match the canonical `[/INST]`.

Even if both defects were corrected, the model would not respond usefully — it has no instruction fine-tuning (Finding 1). But the malformed tags are a secondary failure that also explains why the 3 non-empty cases produced prompt-echo instead of silent EOS.

---

### Finding 3 — The 7 empty responses are immediate EOS from the base model

From `quality_capture_server_20260830b.log`, tasks 1–5 and 8–9 (the 7 empty responses):

```
print_timings: eval time = ~13–17 ms / 2 runs
```

Two eval runs = the model generated exactly one token and that token was EOS (token id=2, `</s>`). The server strips EOS from returned content, leaving `""`. A base model that encounters a context pattern absent from its training distribution has high confidence in immediately ending generation. The malformed `[INST]` prefix is not in Wikipedia/Pile/StackOverflow, so the model routes to EOS.

This is not a malfunction of the model; it is correct base-model behavior on an out-of-distribution input.

---

### Finding 4 — The 3 non-empty responses are prompt echo + EOS repetition, caused by missing stop sequences

From `quality_capture_server_20260830b.log`:

- Task 0 (`constraint_following`): `eval time = 1796.78 ms / 128 runs` — exhausted `n_predict=128` budget
- Task 6 (`format_repair`): `eval time = 1658.74 ms / 128 runs` — exhausted `n_predict=128` budget
- Task 7 (`bounded_plan`): `eval time = 478.57 ms / 34 runs` — stopped at 34 tokens

For tasks 0 and 6 the model echoed the prompt text and then produced the string `</s>` repeatedly until the token budget expired. The `</s>` text here is the model generating individual characters (`<`, `/`, `s`, `>`) that spell out the EOS string — NOT the EOS token (id=2). The llama.cpp server halts on the actual EOS token, but these are text-level tokens that happen to spell it out.

**The direct cause of the 128-token runaway is that no `stop` parameter was passed in the `/completion` request.** Had `"stop": ["</s>"]` been present, the server would have halted on the first occurrence of the EOS string in the text output.

Task 7 stopped at 34 tokens because the model happened to generate the actual EOS token (id=2) after producing the partial echo, not because of any stop sequence.

---

### Finding 5 — Acceptance gate passed because it never tested instruction following

The acceptance gate benchmark (from `acceptance_gate_20260830_175953.json`) validated:

- CUDA acceleration active
- FFN split working (2322 MiB offloaded to GPU)
- 20 turns × 2 passes (cold + warm) of raw text completion with `max_tokens=64`
- Throughput, latency, and TTFT measurements

It did NOT test: instruction format, response quality, stop-sequence behavior, or any output content beyond measuring token count and timing. Many turns in the benchmark also produced 2-token (immediate EOS) responses — `"completion_tokens": 2`, `"stopped_eos": false` — and these were counted as normal throughput measurements, not failures.

The acceptance gate is a hardware/throughput gate. It cannot distinguish a functional chat model from a base model that immediately generates EOS on most inputs.

---

## Diagnosis

**Primary cause: Category error — quality review applied instruction-following tests to a base model.**

ReluLLaMA-7B (`manifest.json` `class: base`) is a pure text-completion model trained on raw corpora. It has no instruction template, no RLHF, no SFT on dialogue. Wrapping prompts in any variant of `[INST]...[/INST]` is meaningless to it. The 7/10 immediate-EOS responses and 3/10 prompt-echo responses are the expected behavior of a base model receiving out-of-distribution instruction-format input.

**Secondary cause: The quality capture template string was malformed in two ways** (`[Inst]` not `[INST]`; closing tag missing `/`). This is irrelevant for this model since the correct template would also fail, but it must be fixed before the script is used against a genuine chat model.

**Tertiary cause: No `stop` sequences were configured in the `/completion` requests.** Without `"stop": ["</s>"]`, the three non-empty cases filled their entire 128-token budget with repeated EOS-string characters. The benchmark used `n_predict=64` and the same absence of stop sequences — but its prompts were short enough that the model often hit EOS naturally.

**The claim in `2026-08-30d` that the quality capture used "llama-2 `[INST]` wrap as the gate uses" is incorrect on both parts:** the gate uses no template, and the template used in quality capture was malformed.

---

## Proposed corrected request format (unverified — do not run without operator approval)

This section applies only IF a re-run is approved. It does NOT apply to this model in its current form.

**For this base model (`class: base`):** The instruction-following quality rubric cannot be meaningfully applied. Options:
- (A) Re-run with raw completion prompts that match what the acceptance gate uses, and evaluate text continuation quality instead.
- (B) Reject the model at the quality gate because `class: base` models do not satisfy instruction-following requirements. The staging pipeline already records `class: base` in `manifest.json`; this could be an automatic quality-gate exclusion criterion.

**If the quality review script is to be fixed for future chat models** (e.g., a `Llama-2-7b-chat-hf`-derived model), the corrected `/completion` request format is:

```json
{
  "prompt": "<s>[INST] {user_message} [/INST]",
  "n_predict": 256,
  "temperature": 0,
  "cache_prompt": false,
  "stop": ["</s>", "[INST]"]
}
```

Corrections from what was used:
1. `[INST]` — ALL CAPS (not `[Inst]`)
2. `[/INST]` — includes forward slash (not `[Inst]` again)
3. `"stop": ["</s>", "[INST]"]` — halts on EOS string or new instruction tag
4. BOS `<s>` prepended explicitly (the tokenizer also auto-prepends via `add_bos_token: true`, but explicit is safer for raw prompt mode)

These corrections apply only to Llama-2 chat variants. A different base model will need its own template (if any).

---

## What this does NOT change

- The GGUF file, predictor, and activation files are unchanged and their hashes remain valid.
- The acceptance gate results (throughput, FFN split, VRAM) remain valid.
- The quality packet status remains `responses_recorded` — the responses were accurately captured; the fault is in how the requests were constructed, not in the capture mechanism itself.
- The model has NOT been promoted to the picker and the production registry was NOT touched. No re-run is needed to maintain that status.

---

## Recommended next steps (for operator decision)

1. Decide whether `class: base` models should automatically bypass or fail the instruction-following quality rubric (and update the quality review script to enforce this).
2. If a re-run is desired: get operator GPU approval, then run against raw completion prompts (Option A above) or apply the corrected template to a chat-class model.
3. Fix the quality review script's template string and add the `stop` parameter regardless, so the bugs do not recur on a future chat-class candidate.
4. Update `2026-08-30d_quality_review_responses_recorded.md` to note that the claim "as the gate uses" was incorrect — the acceptance gate uses raw prompts, not `[INST]` wrapping.
