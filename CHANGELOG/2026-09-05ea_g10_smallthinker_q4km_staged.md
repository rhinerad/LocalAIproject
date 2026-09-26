# 2026-09-05ea — G10 SmallThinker-3B Q4_K_M staged; waiting Termux inward copy

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05ea**.

No admin inject. No `--once`. Farm `hub.conf` SHA-256 unchanged
`0EA2DF795F5FA8344CDE522FBEC9B22FC3EAA52A2918A724863A4D5B57FC13BC`.

Operator `2026-09-05do` confirmed staying on
`huihui-ai/SmallThinker-3B-Preview-abliterated` (not 7B/8B). That
Hugging Face repo is safetensors only. GGUF used:

| Field | Value |
|---|---|
| Quant repo | `QuantFactory/SmallThinker-3B-Preview-abliterated-GGUF` (llama.cpp quant of the huihui-ai checkpoint) |
| File | `SmallThinker-3B-Preview-abliterated.Q4_K_M.gguf` |
| Quant | **Q4_K_M** (~2.1 GiB; sized for 16 GB Pixel RAM, not Q8/F16) |
| Bytes | 2 104 931 296 |
| SHA-256 | `514100b5dcf6b4e958cb241d77b079286fa8687e6b17de0822f61639eda3107e` (HF LFS oid; host download matched) |

Host path:
`artifacts/powerinfer_vault/SmallThinker-3B-Preview-abliterated.Q4_K_M.gguf`.

ADB push to
`/sdcard/Android/data/com.termux/files/powerinfer-edge/` (dir `711`,
file `644`) at 35.6 MB/s. Device `sha256sum` **matches** the host hash.

Termux home does **not** have the GGUF yet (`RUN_COMMAND` absent;
DocumentsProvider cannot write). Waiting on operator `cp` +
`sha256sum` before inject/`--once`.
