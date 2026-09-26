# 2026-09-04h — Capability-routing models: download and smoke-test only

Date: 2026-09-04. Hosts: Louises-MBP (Mac worker, 16 GB unified RAM) and
DuranGamingPC (RTX 5080 16303 MiB). Id from
`python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04h**.
Operator decision in `TODO.md` 2026-09-04. **No routing code.** `router.py`
was not touched. GPU was idle (ComfyUI not occupying the card). Each host
model was loaded alone, then unloaded (`keep_alive: 0`) after its smoke.

## 1. Mac worker — `richardyoung/qwythos-9b-abliterated`

Pulled on Louises-MBP via `/usr/local/bin/ollama pull richardyoung/qwythos-9b-abliterated`
(latest = publisher-recommended **Q4_K_M**, 5.6 GB).

| Field | Value |
|---|---|
| Tag | `richardyoung/qwythos-9b-abliterated:latest` |
| Digest | `82663f0413020edd6983bf612443de5a20c48d29b59aef30f2e5c5588fa6eb6f` |
| Quant | Q4_K_M |
| Disk size | 5,629,109,190 bytes |
| Architecture | qwen35, 9.0B, tools + thinking + completion, `num_ctx` 8192 |

Smoke (`POST /api/generate`, prompt "Reply with the single word OK.",
`num_predict` 16): loaded, `done=true`, `eval_count=16`. Response started
with thinking-style instruction restatement rather than a bare `OK` — load
and decode succeeded.

### RAM coexistence (the actual check)

Nothing was resident before the test (`/api/ps` empty). Then, in order:

1. `nomic-embed-text:latest` (farm embed) — 376,449,269 bytes resident
2. `krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS` (farm summarize) —
   7,595,916,000 bytes resident
3. qwythos — 6,158,412,676 bytes resident

All three were resident together. Combined ~14.1 GB of model RAM on a
16 GB machine.

| | Before | After all three loaded |
|---|---|---|
| Swap total | 1024.00M | 5120.00M |
| Swap used | 391.50M | 3723.25M |
| Compressor pages | 100,887 | 1,475,824 (~5.7 GB) |

**Finding: qwythos + nomic-embed is fine; qwythos + summarize + embed is
not.** Three-way residency blew past comfortable 16 GB and paged ~3.7 GB
to swap. Do not plan to keep qwythos loaded on the Mac at the same time as
mistral-nemo. Routing design (later) must treat Mac summarize and Mac
qwythos as mutually exclusive residents, or run qwythos only with the
tiny embed model. qwythos was unloaded after the smoke; farm models were
left on their 10-minute keep-alive.

## 2. Host GPU — `huihui_ai/deepseek-r1-abliterated:14b-qwen-distill`

Registry tags confirmed on `ollama.com/huihui_ai/deepseek-r1-abliterated`
before pull (14b-qwen-distill family):

| Tag suffix | Size |
|---|---|
| q3_K_M | 7.3 GB |
| q4_K_M (also unadorned `14b-qwen-distill`) | 9.0 GB |
| q5_K_M | 11 GB |
| q6_K | 12 GB |
| q8_0 | 16 GB |

**Picked `q4_K_M`.** q8_0 fills the 16 GB card with no KV headroom. q5_K_M /
q6_K leave too little for a 14B KV cache (the existing
`huihui_ai/qwen3-abliterated:14b` Q4_K_M baseline already used 11,859 MB at
20,480 context). q4_K_M matches that proven 14B footprint.

| Field | Value |
|---|---|
| Tag | `huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M` |
| Digest | `6b2209ffd7582e8310a4b3a99691b7e7253be608fe38b3d6d97cd3b9b1844ff4` |
| Quant | Q4_K_M |
| Disk size | 9.0 GB |
| Capabilities | tools, thinking, completion |

Loaded **alone** (GPU otherwise idle: 70 MiB used). Resident VRAM:

- Default load (`context_length` 16384 in `/api/ps`): **11,916 MiB used /
  4,062 MiB free**
- After a `num_ctx=2048` generate: **8,985 MiB used / 6,993 MiB free**

Smoke: `think:false`, `num_predict=8`, `num_ctx=2048`. `done=true`,
`eval_count=8`, response `<think></think>\n\nSure! What would` (truncated
by `num_predict`). Then unloaded; GPU back to 70 MiB.

## 3. Host GPU — Josiefied-Qwen2.5-Coder-14B

**No Coder-tagged Ollama registry model.** Checked
`https://ollama.com/goekdenizguelmez` and
`https://ollama.com/goekdenizguelmez/JOSIEFIED-Qwen2.5/tags`. Published
repos: JOSIEFIED-Qwen3, JOSIEFIED-Qwen2.5 (0.5b/1.5b/3b/7b/14b **general**),
JOSIE, JOSIEFIED-Llama, Gabliterated-Qwen3, JOSIE-2. Confirmed general tag
only: `goekdenizguelmez/JOSIEFIED-Qwen2.5:14b` (Q5_K_M, 11 GB, digest
`3e9a718e4a3c`) — **not** the Coder-Instruct variant. Did not pull that tag.

`Goekdeniz-Guelmez/Josiefied-Qwen2.5-Coder-14B-Instruct-abliterated-v1` on
Hugging Face is **safetensors only** (six shards, BF16, ~29.5 GB). The
model-card "GGUF" link
`…/Josiefied-Qwen2.5-Coder-14B-Instruct-abliterated-v1-gguf` **404s**.

Used the verified quantization of that exact base model:
`mradermacher/Josiefied-Qwen2.5-Coder-14B-Instruct-abliterated-v1-GGUF`
file `Josiefied-Qwen2.5-Coder-14B-Instruct-abliterated-v1.Q4_K_M.gguf`
(Q4_K_M, same 16 GB VRAM budget as the DeepSeek pick).

| Field | Value |
|---|---|
| Local tag | `josiefied-qwen2.5-coder-14b:q4_k_m` |
| Ollama digest | `4a4b6c1f443c25493b92ee049efb4c9a366271ee9a1cdfc8a668b37b45f1b5ac` |
| Quant | Q4_K_M |
| GGUF SHA-256 | `b6bcf343f81af5833b91554eb1a6d14424e0f8c09c8ee6ba908f30ac314b0c14` |
| GGUF path | `local_agent/runtime/gguf/Josiefied-Qwen2.5-Coder-14B-Instruct-abliterated-v1.Q4_K_M.gguf` |
| Modelfile | `local_agent/runtime/gguf/Modelfile.josiefied-qwen2.5-coder-14b` |
| Capabilities | completion, tools |

`ollama create josiefied-qwen2.5-coder-14b:q4_k_m -f …Modelfile…` wrote
manifest `success`. Smoke **after DeepSeek was unloaded**, GPU idle: prompt
"Reply with the single word OK." → response **`OK`**, `done_reason=stop`,
`eval_count=2`. Resident VRAM at `num_ctx=2048`: **8,991 MiB used /
6,987 MiB free**. Then unloaded; GPU back to 70 MiB.

## Not done (intentionally)

- No edits to `local_agent/router.py` or any harness profile.
- Host 14B models were never resident together.
- Mac qwythos was not left loaded with mistral-nemo.
