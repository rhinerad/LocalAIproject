# 2026-08-29 — PowerInfer ReluLLaMA test coverage (PoC is relu-llama-7b)

## What changed

- `local_agent/test_powerinfer_pipeline.py`: added `test_relu_llama_7b_is_active_supported_sparse_poc` so the live supported-sparse PoC is `relu-llama-7b` (`hf_id` `SparseLLM/ReluLLaMA-7B`, `expected_hidden_act=relu`, `expected_model_type=llama`, shapes 4096/11008/32, `vocabtype=spm`, `requires_relufication=false`, `retired` absent/false). Added `test_prosparse_7b_is_retired_but_loadable` (`retired=true`, still loaded via `target_config`). Extended `test_both_targets_share_dump_train_fields` so the shared-fields loop includes `relu-llama-7b` plus the parked ProSparse target and the Llama-3.1 research route (`solver_batch` divides `intermediate_size`, `quant=Q4_0`).
- `tools/powerinfer/models.json` `notes[2]`: stopped claiming the live id is `PowerInfer/ReluLLaMA-7B`. It now matches `hf_id` (`SparseLLM/ReluLLaMA-7B`) and points at `hf_id_note` for the 404.
- `TODO.md` PowerInfer / model-conversion bullets: ReluLLaMA-7B is the live parameterized sparse target; ProSparse is parked/retired because FATReLU / `sparsellama`; compile/setup is still blocked on CUDA Toolkit 12.8+ and Visual Studio 2022 with the C++ workload. Operator-gated boxes (GPU execute, validation manifests, live latency) were left unchecked.
- Did **not** edit `run_pipeline.ps1`, `pipeline_lib.py` `target_config()` retired-load behavior, `CHANGELOG/2026-08-29_powerinfer_setup_attempt.md`, or `CHANGELOG/2026-08-29f_*.md`. Did **not** touch `C:\PowerInferVault`, Equal Shares, ComfyUI, GPU, downloads, or Harmontown.

## Why

ReluLLaMA-7B was already adopted in `models.json` and intake had already happened, but the unit tests and `TODO.md` still described the retired ProSparse-7B target as the live PoC. `notes[2]` still named `PowerInfer/ReluLLaMA-7B` even though `hf_id_note` records that repo 404s. A later session could treat ProSparse as the conversion source or retry the 404 id.

## The evidence

`tools/powerinfer/models.json` after the note fix:

- `targets["relu-llama-7b"].hf_id` = `SparseLLM/ReluLLaMA-7B`, `retired` absent, `expected_hidden_act=relu`, `expected_model_type=llama`, 4096/11008/32.
- `targets["prosparse-7b"].retired` = `true`.
- `notes[2]` now starts `relu-llama-7b uses SparseLLM/ReluLLaMA-7B` and no longer names `PowerInfer/ReluLLaMA-7B` as the live id.

`pipeline_lib.target_config()` still merges any registered id, including retired ones. Vault tests still use `"prosparse-7b"` as a bundle id string.

## What was verified after

From `local_agent/`, CPU-only, no GPU, no download, no `-Execute`:

```text
python -m unittest test_powerinfer_pipeline -v
```

Result at 6:13 PM ET on 2026-08-29: **Ran 20 tests in 0.796s — OK** (20/20). New tests `test_relu_llama_7b_is_active_supported_sparse_poc` and `test_prosparse_7b_is_retired_but_loadable` both ok. Shared-fields loop including `relu-llama-7b` ok. Vault tests that still pass `"prosparse-7b"` as a bundle name still ok.

## What is still unverified

- Native RTX 5080 (`sm_120`) compile: CUDA Toolkit 12.8+ and Visual Studio 2022 C++ workload are still absent. Operator install; this session did not compile PowerInfer.
- Live PowerInfer sparse latency/VRAM numbers. GPU was not used; `-Execute` was not run.
- Relu-gate against the real ReluLLaMA vault `config.json` was not re-run here (intake already recorded in a prior session).
- Accepted validation manifests, predictor/activation artifacts, and Harmon Town / Judge routing. Those boxes stay operator-gated.
