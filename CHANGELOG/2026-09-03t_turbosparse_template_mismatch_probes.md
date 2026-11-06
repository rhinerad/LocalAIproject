# 2026-09-03t - TurboSparse template-mismatch probes; V1 grammar-forced only; registry FAIL

Did not dump. Did not train predictors. Did not convert. Did not quantize. Did not
edit o_proj. Did not write into the parked 20260830b tree. Did not mark accepted.
Did not write production_models.json. Canonical `validation\agentic_quality_gate.json`
left `failed_turn_1`. Kept failed_turn_1, grammar, and registry_attempt evidence.

## A Freeze-check

nvidia-smi 2026-09-03 14:54:07 ET: RTX 5080 61 C / 49% util / 10612 MiB of 16303,
apps ChatGPT.exe + Rockernow python.exe + brave.exe x2. No leftover server.exe.
Port 8080 free. Thermal cap 82 C never hit.

Hashes reconfirmed:
- Q4 `59318ed894f16d791ee418cb1536ba9bab62a85986a6a7b112ce59b17436c98b` (4194219136 bytes)
- F16 `14474bd8f1d76fa7246bca5b9b63312fd661807dbe56eda38223015f493678d2` (14787775552 bytes)
- contract `151dcbed9fbd8f6f020e6c12f8cf7c848c1edfc6f7138648b922282e77d6e2ea`

## B Reconstruction

Wrote `validation\gate_reconstruction.2026-09-03.json` (SYSTEM, TURN1, EXPECTED,
ChatML template first 500 chars from prompt_contract/tokenizer_config, bos `<s>`,
eos `<|im_end|>`, official settings). Prior GBNF was generic JSON allowing `{}`.
Baked template is ChatML, not `[INST]`.

## C Probes

New script `tools/powerinfer/template_mismatch_probes.py`. Q4 server from bundle
`output` cwd: `server.exe -m <q4> -c 2048 --vram-budget 12 --host 127.0.0.1 --port 8080 -t 8`.
Reported VRAM 5927.70 MB. Temp 0, n_predict 256, stop ChatML+`[INST]`.

Out: `validation\template_mismatch_probes.2026-09-03.json`

- C1 official ChatML, no grammar: FAIL `invalid_json` (garbled prose)
- C2 Mistral `[INST]<<SYS>>...`, no grammar: FAIL `invalid_json` (garbled)
- C3 same as C2 + exact-tool_calls GBNF: PASS exact EXPECTED JSON (diagnostic only, not a registry cheat)
- C4 Mistral few-shot with that JSON then TURN1, no grammar: FAIL `invalid_json`
- C5 ChatML + exact GBNF: PASS (optional)

D skipped: not all C failed. No baseline GGUF search. No copy into the bundle.

## E Stop

Stopped server.exe. Final nvidia-smi 2026-09-03 15:09:40 ET: 36 C / 1% util / 4070 MiB,
no server.exe, 8080 TIME_WAIT only.

## Verdict

Bucket **V1** because C3 passed (operator C.3/C.4 -> V1). Unconstrained C1/C2/C4
still fail, so this is tokenizer/grammar-forced capability, not an unconstrained
tool-call pass. Registry still **FAIL**. Manifest left `candidate`.

`validation\agentic_gate_verdict.2026-09-03.json`

20260830b parked: untouched (config.json mtime 2026-08-30 18:35:46 ET;
abliteration_manifest.json 20:24:02 ET).

Recommended next operator action: Do not mark accepted or register; unconstrained
ChatML, [INST], and few-shot still garble, so treat C3/C5 exact-GBNF PASS as
tokenizer-capability only and leave this candidate parked.
