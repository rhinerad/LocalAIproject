# 2026-08-25 — coding mode and sandboxed run_code

## What changed

- `router.CODING_MODEL` (default `huihui_ai/qwen2.5-coder-abliterate:14b`, env
  `EQUAL_SHARES_CODING_MODEL`) is an explicit chat choice, not only a fallback.
  Installed coder tags are marked `kind: "coding"` in `chat_models()`.
- The GUI picker labels those models **Coding mode**. Selecting one pins the
  coder and swaps the system prompt to a test-driven debug loop. Status warns
  when coding is falling back to CPU because a render owns the GPU.
- Routing is unchanged in shape: GPU 14B-coder when the card is idle; CPU path
  when a render owns it (prefer 7B coder, else Huihui 8B). An unknown coder tag
  falls back cleanly instead of returning a blank model.
- `run_code` is a whitelist tool. Execution is isolated to
  `local_agent/sandbox/run_<id>/`, Python (`-I`) with an in-process path/network
  guard, optional Node if `node` is on PATH, 30 s timeout (cap 120), capped
  output, process-group kill, `CUDA_VISIBLE_DEVICES=-1`, network off by default.
  A path outside the sandbox — including `outputs/equal_shares/` — is refused.
- `run_code` is desktop-only and default-denied for phone identities
  (`GATED_REMOTE_TOOLS`). `write_candidate_tool` still cannot run or replace
  project code; candidates can be copied into the sandbox to try.
- Launcher pull of the coder is opt-in: `-EnsureCodingModel` or
  `EQUAL_SHARES_ENSURE_CODING_MODEL=1`. Default startup does not fetch ~9 GB.

## Why

A 14B general chat model can propose code; it cannot debug without a bounded
place to run it. The sandbox is that place. The honest ceiling is a strong local
junior/mid coder, not a frontier model.

## Tests

```
python local_agent/test_native_tool_calling.py
python local_agent/test_run_code.py
python local_agent/test_router_switching.py
python local_agent/test_gui_render_hint.py
python local_agent/test_launcher_kv_cache.py
python local_agent/test_launcher_revision.py
python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v
```

- native tool calling: **19/19 passed** (schema set includes `run_code`)
- run_code: **11/11 passed** (hello-world exit 0, timeout kill, outside-path
  refuse, Equal Shares path refuse, project-file open refused, output cap,
  phone default-deny, coding system prompt swap)
- router switching: **20/20 passed** (coding model on idle GPU, unknown coder
  fallback, CPU path while render-busy, `kind: coding` in picker metadata)
- GUI / launcher / revision: **2/2, 3/3, 1/1 passed**
- H3 validator: **124/124 valid**

No render, no ComfyUI, no deletes, no new pip dependencies.

## Unverified

A live coding session with the 14B-coder loaded on GPU. The model is not pulled
by default; `-EnsureCodingModel` is required before that check is honest.
