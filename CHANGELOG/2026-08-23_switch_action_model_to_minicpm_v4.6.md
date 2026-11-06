# Switch action extraction model: MiniCPM-V 2.6 8B → Huihui MiniCPM-V 4.6 1B

**Date:** 2026-08-23  
**Revision bump:** r12 → r13

## Change

Replaced the video action extraction model with the huihui-ai abliterated variant
of MiniCPM-V 4.6 Thinking.

| | Old | New |
|---|---|---|
| Model | `openbmb/minicpm-v2.6:8b` | `huihui-minicpm-v-4.6-abliterated:q8_0` |
| Parameters | 8B | 1B |
| GGUF size | ~7.5 GB | 812 MB weights + 812 MB mmproj = 1.6 GB |
| `MINICPM_VRAM_MB` | 7500 | 2500 |
| Source | Ollama library | mradermacher GGUF (HuggingFace) |

## Files changed

- **`local_agent/capabilities.py`**: Updated `MINICPM_V_MODEL`, `MINICPM_VRAM_MB`,
  `action_model()` docstring and install error message, `all_capabilities()` comment
  and install hint.
- **`local_agent/Modelfile.huihui-minicpm-v-4.6-abliterated`** (new): Ollama Modelfile
  that imports the mradermacher Q8_0 GGUF + mmproj-Q8_0 from the local GGUF path.
- **`local_agent/server.py`** / **`START_LOCAL_AGENT_GUI.ps1`**: revision r12 → r13.

## Install steps (requires internet)

1. Download both files from
   `mradermacher/Huihui-MiniCPM-V-4.6-Thinking-abliterated-GGUF` on HuggingFace:
   - `Huihui-MiniCPM-V-4.6-Thinking-abliterated.Q8_0.gguf` (812 MB)
   - `Huihui-MiniCPM-V-4.6-Thinking-abliterated.mmproj-Q8_0.gguf` (812 MB)

2. Place both in:
   `A:\Users\rhine\ComfyUI-Shared\models\LLM\GGUF\mradermacher\Huihui-MiniCPM-V-4.6-Thinking-abliterated-GGUF\`

3. Create the Ollama model:
   ```
   ollama create huihui-minicpm-v-4.6-abliterated:q8_0 -f local_agent\Modelfile.huihui-minicpm-v-4.6-abliterated
   ```

4. Confirm vision capability:
   ```
   ollama show huihui-minicpm-v-4.6-abliterated:q8_0
   ```
   Output must include `vision` in capabilities. If it does not, the mmproj
   FROM line was not picked up — re-run the create command.

5. Restart the agent: run `START_LOCAL_AGENT_GUI.ps1` (r13 mismatch will
   trigger Stop-StaleAgent automatically).

## VRAM impact

The 1B model needs ~2.5 GB VRAM at 32768 ctx vs ~7.5 GB for the old 8B. The
`_evict_chat_models()` call before action extraction still runs (good practice),
but VRAM contention is much less likely to be an issue.
