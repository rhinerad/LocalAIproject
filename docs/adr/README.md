# Architecture Decision Records

These records preserve the safety and operational decisions behind the local
agent. They describe the canonical handoff only; they do not contain private
media, prompts, paths, identities, keys, or device/network configuration.

| ADR | Status | Decision |
|---|---|---|
| [0001](0001-localhost-http-and-lxmf.md) | accepted | Keep HTTP on localhost; use paired LXMF for remote transport. |
| [0002](0002-native-ollama-tool-calling.md) | accepted | Use structured Ollama function calls with a legacy fallback. |
| [0003](0003-lazy-vlm-and-render-ownership.md) | accepted | Keep the VLM lazy and let active renders own the GPU. |
| [0004](0004-explicit-feedback-only-learning.md) | accepted | Learn only through explicit operator feedback and approval. |
| [0005](0005-gpu-cpu-reasoning-fallback.md) | accepted | Route full models between GPU and CPU; do not CPU-offload GPU models. |

All records should be rechecked against code, tests, and changelog evidence
before any public release.
