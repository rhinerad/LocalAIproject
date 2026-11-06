# 2026-09-05bc — Catalog drowning is cross-model; 14B→8B overflow demotion is real

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05bc**. Investigation
only; no `router.py` / schema-surface change. Receipts:
`artifacts/benchmarks/2026-09-05_catalog_drowning/`.

Same case-1a prompt (“first markdown heading inside
`local_agent/README.md`”), full GPU `schemas(include_project=True)` —
**68** tools today (55 without project tools). `think=false`.

## 1. Catalog drowning — not DeepSeek-only

| Model | Tools sent | First call | Verdict |
|---|---|---|---|
| Huihui-14B (2026-09-05b 1a) | **54** general | **`read_file`** | correct |
| Huihui-14B (this probe) | **68** project | **`fetch_url`** `{url: local_agent/README.md}` | wrong (not even an http URL) |
| Josiefied-Coder official-tools | 68 | content JSON **`fetch_url`** `{url: file:///local_agent/README.md}` | wrong |
| DeepSeek r1-tools (2026-09-05at) | 67 | **`see_image`** | wrong |
| gpt-oss-20b-heretic | 68 | **`read_file`** `{path: local_agent/README.md}` | correct |

A screenshot-biased variant (“might be text or a screenshot”) made
Huihui-14B pick `see_image` — that is prompt leading, not drowning.
The table above is the drowning test.

Live `prompt_eval_count` on the short user message + 68 schemas (no
agent system prompt): **4098** (Qwen/Coder/Huihui) vs **7058**
(Heretic harmony). Router estimate for the same wire:
**11940** (`len(json)/3.4`). The estimator inflates schema cost ~2–3×
on Qwen.

Heretic resisted drowning but **rejected `num_ctx=4096`**
(`n_prompt_tokens=7058`). Opt-in 20B already needs ≥8k context just to
*hold* the catalog.

## 2. 14B→8B demotion — not a farm-outage red herring

`_adaptive_gpu_model` demotes **only** `PRIMARY_REASONING_MODEL`
(Huihui-14B) when `estimate_context_tokens > 16000`. Capability
DeepSeek/Coder hops skip this. A `CAP_TOOL` turn with farm down falls
through to ordinary GPU auto → Huihui-14B → this check.

Measured estimates (agent system prompt included):

| Case | Estimate | Over 16k? |
|---|---|---|
| 68 GPU schemas only | 11900 | no |
| README + general GPU (55) + general system | 15697 | no — matches 1a staying on 14B |
| README/enqueue + **project** GPU (68) + project system | 19258 / **19352** | **yes** — matches 2026-09-05b case 4 (`18919`) |
| Same enqueue + compact 3-tool schema | 7821 | no |

Farm being down only *selects* the local GPU path. The demotion is
schema+handbook size vs a conservative estimator, independent of why
the Mac was frozen. Compact profile is `tier in {cpu,farm}` only; the
8B GPU fallback still gets **`profile=gpu` → full 68 tools**
(`docs/HARNESS_PROFILES_DESIGN_2026-09-04.md` §3). So a farm-down tool
turn can land on Huihui-8B *and* the drowning catalog (case 4).

If Qwen’s real schema cost is ~4k, case 4’s 19k estimate may have
falsely demoted a 14B that would have fit. That is still a real routing
bug, not a red herring.

## Proposed fix (not built)

Two complementary changes, neither is a DeepSeek-only crutch:

1. **Curated GPU subset for tool-classified local hops** (farm down or
   `skip_farm`): advertise `CORE_DIRECT_TOOLS` (`list_dir`, `read_file`,
   `web_search`, `fetch_url`, `capabilities`, `run_code`) plus `comfy_*`
   only when the prompt is actually a Comfy/workflow turn. Already
   sketched as compact v1.1 in the harness-profile design. Cuts both
   drowning and the 16k estimate. Do **not** silently shrink every
   Huihui conversation hop until this is measured on a happy-path pin.
2. **Stop counting schema JSON as `len/3.4` tokens** (or use a measured
   per-schema constant from `prompt_eval_count`). Prevents 14B→8B
   demotion on estimates that are 2–3× actual Qwen prompt tokens.

Prefer (1) for tool-fallback hops; (2) is cheap and independent.
Do not apply compact-3 to GPU 14B as the first move — Qwythos already
has compact when the farm is up.

## Not changed

No router, schema, or prompt edits this pass. GPU unloaded after Heretic.
