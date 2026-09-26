# 2026-09-05bx — Calibrate KV-cache filler chars/token (no router estimator change)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05bx**.

2026-09-05bm's Qwen3.8-27B "20K fill" used
`measure_ollama_kv_cache.probe_prompt(18000)`, which sized the body as
`tokens * 3.4` chars. That 3.4 is the router's JSON-wire **estimator**
(chars → tokens, conservative over-count). Used backwards to **generate**
a fill it under-filled: live `prompt_eval_count` was **9375**, ~6.5
chars/token on this repetitive filler.

## Where 3.4 actually lives

| Location | Role | This ticket |
|---|---|---|
| `measure_ollama_kv_cache.probe_prompt` | fill generation (`chars = tokens * 3.4`) | **fixed here** — the bm silent under-fill |
| `2026-09-05_qwen38_27b_eval.py` | imported that helper | now uses `sized_probe_prompt` |
| `router._MESSAGE_CHARS_PER_TOKEN = 3.4` | production chars → tokens for **messages** | **untouched** (2026-09-05bn already replaced schema `len/3.4` with `MEASURED_SCHEMA_TOKENS`) |
| `test_capability_routing.py`, `2026-09-05_gpu_core_live.py` | `/ 3.4` as the **old** estimator for comparison | historical, left |
| `retrieval.py` `CHUNK_CHARS = 3000  # ~800 tokens at ~3.75` | RAG chunk size | different constant, not this fill |

Not a production routing bug. Cross-cutting only among **benchmark fill
generators**, and they already shared one helper — so the fix is central
there, not a per-script patch and not `estimate_context_tokens`.

## Fix

`probe_prompt(..., chars_per_token=)` sizes filler from a measured (or
explicit) chars/token. Live paths:

- `calibrate_fill_chars_per_token(host, model)` — one short chat, `len(prompt) / prompt_eval_count`
- `sized_probe_prompt` / `run_once` (when `chars_per_token` omitted) use that before the timed request
- Offline fallback for this filler is **6.5** (bm measurement), not 3.4
- Receipts record `fill_chars_per_token`, `fill_calibrated`, `fill_rel_error`

`router.py` was not edited. The 2026-09-05bm 9375-token figure is still
the recorded 20k-probe result; this does not re-run the GPU eval.

Tests: `python test_measure_ollama_kv_cache.py` — **8/8**.
