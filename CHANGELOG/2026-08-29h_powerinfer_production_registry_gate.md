# 2026-08-29 - PowerInfer accepted-bundle production gate

## Change

- Added `tools/powerinfer/production_registry.py`, an offline registry that
  admits only explicitly approved `accepted` supported-sparse bundles with a
  complete benchmark checklist and a matching SHA-256 GGUF.
- The loopback PowerInfer OpenAI proxy now refuses to start without a named,
  revalidated registry entry. It also refuses an alias mismatch, so a manually
  started proxy cannot quietly front a different model.
- Added offline regression coverage for candidate, incomplete, and
  post-registration evidence changes.

## Safety boundary

This does not compile PowerInfer, download a model, start a model/backend/proxy,
load GPU memory, or modify normal Ollama routing. Registration still requires a
human-provided evidence identifier after the controlled benchmark and coherence
review.

## Verification

`python tools/powerinfer/test_production_registry.py -v` and
`python local_agent/test_powerinfer_openai_proxy.py -v` pass without GPU work.
