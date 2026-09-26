# 2026-08-22 — pin the image/video watcher to an abliterated Qwen3-VL

## What changed

| File | Change |
|---|---|
| `local_agent/capabilities.py` | `vision_model()` now selects deterministically: `EQUAL_SHARES_VISION_MODEL` override → preferred abliterated Qwen3-VL tags → any installed vision model (unchanged fallback). Vision-capability check retained: a tag that does not advertise `vision` is never used blind. |
| `local_agent/Modelfile.qwen3-vl-abliterated` | new — imports the local 8B abliterated GGUF (+ mmproj) into Ollama as `qwen3-vl-abliterated:8b-q8_0`. |

## Why

The watcher (`media_tools.see_image` / `analyze_video`) had **no pinned model** —
`vision_model()` returned the *first* installed model advertising a `vision`
capability, so which model watched was nondeterministic and depended on
Ollama's tag order. The operator wants the abliterated Qwen used explicitly, and
the best one that fits the 16 GB RTX 5080.

## The model — already on disk, no download

`ComfyUI-Shared\models\LLM\GGUF\mradermacher\Qwen3-VL-8B-Instruct-c_abliterated-v3-GGUF\`:

- `...Q8_0.gguf` — 8.71 GB (8B weights, Q8_0)
- `...mmproj-f16.gguf` — 1.16 GB (vision projector; **required** for sight)

~9.9 GB total, fully resident on a 16 GB card. This exactly matches the operator's
choice (8B, Q8_0, fully on GPU). Sizes read directly from the files.

Note: the sibling `LLM\Qwen-VL\Huihui-Qwen3-VL-4B-Instruct-abliterated\` is a
**partial** HF checkout — `model.safetensors.index.json` present but no weight
shards — so it is unusable and was not considered.

## Operator steps (run on the Windows host, GPU Ollama on :11434)

    ollama create qwen3-vl-abliterated:8b-q8_0 -f local_agent\Modelfile.qwen3-vl-abliterated
    ollama show   qwen3-vl-abliterated:8b-q8_0        # capabilities MUST list: vision

If `ollama show` does not list `vision` (a known GGUF-import quirk on some Ollama
builds), pull the packaged build instead — the watcher already prefers it next:

    ollama pull huihui_ai/qwen3-vl-abliterated:8b-instruct-q8_0

## Verified

- `python -c "import ast; ast.parse(open('local_agent/capabilities.py').read())"` — syntax OK.
- Both GGUF files exist at the paths the Modelfile references (byte sizes above,
  read from disk this session).
- Selection order reviewed: override → preference list → first-vision fallback;
  the original behaviour is the final branch, so nothing regresses when the new
  tag is absent.

## Still unverified (requires the operator's Ollama — unreachable from this session)

- That `ollama create` succeeds and `ollama show` reports `vision` for the
  imported GGUF. Ollama has open issues where an imported mmproj is not retained
  (ollama/ollama#9967) or the architecture is unrecognised (#14730); the packaged
  `huihui_ai` build is the fallback for exactly that case.
- A live `see_image` / `analyze_video` call actually routing to
  `qwen3-vl-abliterated:8b-q8_0` and returning a description.
- That the imported GGUF carries a usable chat template (mradermacher GGUFs
  normally embed it; if replies are malformed, add a `TEMPLATE` to the Modelfile).
