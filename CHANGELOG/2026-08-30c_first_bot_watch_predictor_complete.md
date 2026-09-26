# 2026-08-30 — first bot 6pm watch: ReluLLaMA 32/32 on disk, no GPU

## What this session did

Inspect-only Keep-projects-moving run at ~6:07 PM ET. Another session had
just written `tools/powerinfer/batch_suite.ps1` and
`CHANGELOG/2026-08-30_powerinfer_batch_suite.md` at 6:04 PM ET, so this
watch did **not** edit PowerInfer scripts, start `-Execute`, dump, train,
convert, Equal Shares, Harmontown code, or Zing.

## Disk vs the 10am / 6:04 PM notes

The 10am watch (`CHANGELOG/2026-08-30a_first_bot_watch_layer_inventory.md`)
and the 6:04 PM batch-suite changelog still say continue at
**`-LayerStart 15`** (layers 0–14 only). That next-step is stale.

Writable workspace
`A:\Users\rhine\Documents\Codex\PowerInferStaging\relu-llama-7b-source-20260829`:

- `predictor_raw/model_0.pt` … `model_31.pt` (32 files) plus 32
  `layerN.metrics.json`. Last write: layer 31 at 1:54 PM ET.
- assembled `predictor/HASHES.json` (1:54 PM ET)
- Q4 GGUF `output/relu-llama-7b.q4.powerinfer.gguf` (3,895,410,080 bytes,
  5:35 PM ET)
- mechanical gate `validation/acceptance_gate_20260830_175953.json`
  (6:00 PM ET): 20 cold + 20 warm loopback turns, 0 failures; mean decode
  110.729 cold / 100.743 warm tok/s; 2322 MiB FFN offload; status
  `candidate`
- unfilled packet `validation/quality_review_packet.json`
  (`status=prepared`, 10 cases). Not quality evidence.

Held-out recall from the metric files (calibration only):

| layers | recall |
|---|---|
| 0–4 | 0.8584, 0.8412, 0.8329, 0.8133, 0.8093 |
| 5–9 | 0.7986, 0.8082, 0.8161, 0.8411, 0.8420 |
| 10–14 | 0.8443, 0.8425, 0.8435, 0.8485, 0.8465 |
| 15–19 | 0.8489, 0.8318, 0.8175, 0.8096, 0.8164 |
| 20–24 | 0.8066, 0.8037, 0.8069, 0.8147, 0.8091 |
| 25–29 | 0.8248, 0.8121, 0.8155, 0.8161, 0.8193 |
| 30–31 | 0.8334, 0.8668 |

min/mean/max **0.7986 / 0.8262 / 0.8668** (matches `TODO.md`).

Do **not** re-dump or retrain. `SkipDumpTrainIfPresent` is the right
protection. Assembly/convert already happened in a later afternoon session;
the candidate is still not in the production registry, picker, or router.

## GPU / process

`nvidia-smi` at inspect: 31 C, 0% utilization, 87 MiB used of 16,303 MiB.
No python/PowerInfer training process. Brave was listed with no reported
VRAM. GPU is idle.

## Other trees

- Harmontown `feature/nf-epic`: still paused. Dirty working tree from
  2026-08-29 (`voice_anchor_registry.json`, `tests/test_diarize_core.py`,
  untracked `AGENTS.md` / `docs/FIRST_BOT_SESSION_2026-08-29.md`). No new
  code this watch.
- Zing-0.5: unchanged since 2026-08-29 evening. Kit
  `A:\Users\rhine\zing-local`. Always `--local-attn-size 33 --sink-size 5`.
  Do not start a second download.

## Coordination

Updated `GROK_STATUS.md` so other sessions do not restart at layer 15.
Did not rewrite `TODO.md` (already records 32/32 + the 17:59:53 gate).
Did not edit the 6:04 PM batch-suite changelog; this file is the
correction.

## Next (blocked on Rhine)

Human quality comparison vs current Ollama routes using
`validation/quality_review_packet.json`. Fresh GPU-gateway approval before
serving. Do not pin `powerinfer-local` live until that review exists.
