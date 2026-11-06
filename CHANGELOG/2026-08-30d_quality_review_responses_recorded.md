# 2026-08-30 — ReluLLaMA quality packet: responses recorded, not reviewed

Operator-approved, bounded GPU comparison only. Did **not** score the
rubric, did **not** write `router.py`, did **not** add the candidate to
the picker, and did **not** call `tools/powerinfer/production_registry.py`.
Status on the packet is `responses_recorded` (not `reviewed`). Reviewer
name / `reviewed_at` left blank for Rhine.

Packet:
`A:\Users\rhine\Documents\Codex\PowerInferStaging\relu-llama-7b-source-20260829\validation\quality_review_packet.json`

## Models used

Candidate (PowerInfer `server.exe`, same flags as the 17:59:53 acceptance
gate: `--host 127.0.0.1 --port 8080 --vram-budget 12 -t 8 -c 2048 -a
powerinfer-relu-llama-7b`):

- file `output\relu-llama-7b.q4.powerinfer.gguf`
- bytes `3895410080`
- sha256 `83ba5ef9b1a0c85b41e02e5475931195026f037d5cc55d2e77ac5fac1380ea99`
  (matches `validation/acceptance_gate_20260830_175953.json`)
- `server.exe` build `1594` commit `8bd56d6` (MSVC, CUDA device RTX 5080
  sm_120), binary `A:\PowerInferBuild\bin\server.exe`
- loopback only, 10 independent `/completion` POSTs, llama-2 `[INST]` wrap
  as the gate uses, `n_predict=128`, `temperature=0`, `cache_prompt=false`
  **[CORRECTED 2026-08-30f — both parts of this sentence are wrong: (1) the
  acceptance gate uses raw prose continuation prompts, not `[INST]` wrapping
  — see `main_smoke_bench_20260830_175953.log` line 2; (2) the template
  actually sent was malformed `[Inst]` (mixed case, closing tag missing `/`).
  Full diagnosis in `2026-08-30e_quality_review_diagnosis.md`; corrections
  in `2026-08-30f_corrections.md`.]**
- server log: `validation/quality_capture_server_20260830b.log` (10 HTTP 200
  `/completion` lines)

Baseline (normal GPU Ollama host `127.0.0.1:11434`):

- `huihui_ai/qwen3-abliterated:14b`
- digest `fa0eaa5098bc2a63a999917635534a3b0722c777346c81cc085fde4240b1e2cf`
- size `9001762501` (Q4_K_M, 14.8B)
- modified `2026-08-25T00:38:16-04:00`
- `/api/generate` with `think=false`, `temperature=0`, `num_predict=128`,
  `num_ctx=2048`

## GPU boundary

At start, Comfy Desktop was listening on 8188 with an **empty queue** but
~13 GB VRAM held. It was not killed. The first candidate start was skipped
when 8188 then refused connections; the 14B baseline still ran and was
unloaded (`keep_alive: 0`; later `/api/ps` was `{"models":[]}`).

Candidate capture retried only after nvidia-smi showed the card idle enough
to load `server.exe`. `server.exe` was terminated after the 10 completions.
No production registry write. No picker pin.

No other GPU work was started by this session (no dump, train, convert,
quantize, Equal Shares, VLM). A separate session had `abliterate_turbosparse.py`
processes around the same window; those were not stopped or started here.

## Scoring

`baseline_score`, `candidate_score`, and `review_note` remain null/empty on
every case. Empty `candidate_response` strings are the raw `/completion`
`content` (several turns were 2-token EOS). They are not skipped cases.

Next: Rhine scores the packet and, only if he accepts it, a separate
registry/picker decision.
