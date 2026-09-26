# 2026-09-05n — Coder official-tools retag + DeepSeek R1-tools experiment

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05n**. Follows
`CHANGELOG/2026-09-05g_tool_calling_template_root_cause.md`. GPU idle
(65 MiB, 29–34 °C, Comfy :8188 down) for every load. Old tags were **not**
overwritten. `router.py` was **not** changed (`CAP_LOGIC` still DeepSeek;
`JOSIEFIED_CODER_MODEL` / `CODING_MODEL` still
`josiefied-qwen2.5-coder-14b:q4_k_m`).

Modelfiles:
`local_agent/runtime/gguf/Modelfile.josiefied-qwen2.5-coder-14b-official-tools`
`local_agent/runtime/gguf/Modelfile.deepseek-r1-abliterated-14b-r1-tools`
(`build_tool_template_retags.py` writes them). Live receipts:
`artifacts/benchmarks/2026-09-05_template_retag/`.

## Part 1 — Coder-14B retag (did not promote)

`ollama create josiefied-qwen2.5-coder-14b:official-tools` reused weight
layer `sha256:d5e3ff3e…` from `:q4_k_m`. Digest **`1017c800fa73`**.
Runtime template is the official `qwen2.5-coder:14b` Go template,
including “NO other text. Do not include any backticks or ```json”.
SYSTEM / stop / `num_ctx=8192` kept from the josiefied import. Fallback
tag `:q4_k_m` (`4a4b6c1f443c`) still installed.

Case 3 prompt (same `run_code` clamp debug loop as
`2026-09-05_task_completion`), GPU `:11434`, full GPU tool schemas,
`num_ctx=8192`:

| Tag | native `tool_calls` | content |
|---|---|---|
| `josiefied-qwen2.5-coder-14b:official-tools` (90.5 s) | **[]** | fenced JSON `{name: run_code, …}` |
| same tag, `run_code` schema only (110.3 s) | **[]** | raw JSON object, no fences, still not XML |
| stock `qwen2.5-coder:14b` control (158.1 s) | **[]** | same fenced JSON as the 2026-09-05b failure |

No `<tool_call>` XML in any of the three hops. Ollama therefore never
promoted the intended `run_code` call. The official no-backticks line is
now on the josiefied tag; with a one-tool schema it even dropped the
markdown fences. That is not enough: this Ollama 0.32.15 parser still
requires `<tool_call>…</tool_call>`, and Qwen2.5-Coder (abliterated **and**
stock) emitted a JSON object in `content` instead.

**Not promoted.** `JOSIEFIED_CODER_MODEL` stays `:q4_k_m`.

## Part 2 — DeepSeek-14B R1-tools experiment (no routing change)

`ollama create deepseek-r1-abliterated-14b:r1-tools` reused weight layer
`sha256:38b5e200…` from
`huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M`. Digest
**`70cf39bd428e`**. Template is DeepSeek-R1 tokens with `.Tools` /
`.ToolCalls` / `role=tool` (aleshribar3-style). Confirmed via
`ollama show --modelfile` (not Huihui ChatML). Original Huihui tag
`6b2209ffd758` kept.

Case 1 `read_file` prompt (“first markdown heading inside
`local_agent/README.md`”), full GPU schemas:

1. First hop (217.6 s): `tool_calls=[]`, `content=""`, `eval_count=315`,
   `done_reason=stop`. Thinking was not captured on this hop (stripped
   into `message.thinking`). Native protocol did not fire.
2. Second hop (57.7 s), thinking captured: **native `tool_calls` did
   populate** (`id=call_7i5321qr`). Wrong tool and untrustworthy args:
   `see_image` with `path=local_agent/README.md`,
   `question=What is the first markdown heading…`, plus invented
   `language=python`. Thinking text explicitly treated README.md as an
   image. Real heading in that file is
   `# Local Agent — a local ChatGPT Desktop equivalent`. The model never
   called `read_file`.

So: injecting a DeepSeek-R1 `.Tools` template makes native `tool_calls`
*possible* (run 2) but not reliable (run 1 empty; run 2 wrong tool +
hallucinated argument). Matches the 2026-09-05g warning that R1-style
calling can stay unstable even with a correct template.

**`CAP_LOGIC` routing was not changed.** Operator decision remains:
prefer Huihui-14B for tool-using logic hops vs keep DeepSeek.

## Tests

`python -m unittest test_capability_routing test_native_tool_calling`
from `local_agent/`: **102 OK** in 17.9 s. No router/default-tag edits,
so no new regression test was added.

## What was not done

- No `CODING_RULES` / prompt / `TOOL:`-fallback patches.
- No `router.py` `JOSIEFIED_CODER_MODEL`, `CODING_MODEL`, or `CAP_LOGIC`
  edits.
- Did not overwrite `:q4_k_m` or the Huihui DeepSeek tag.
