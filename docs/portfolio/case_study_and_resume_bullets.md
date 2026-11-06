# Case study and résumé bullets (verified work only)

Every sentence below is backed by a changelog or a recorded test. Unmeasured
or in-progress work is labeled as such. Do not paste private paths, names,
prompts, or media into a public application.

## One-paragraph case study

I designed and implemented a **localhost-only desktop agent** that talks to
local models through **native tool calling**, keeps a **fixed tool whitelist**,
and treats **GPU ownership as a first-class lock**: a ComfyUI render wins, media
analysis waits, and interactive chat can fall back to a CPU model instead of
layer-offloading onto a busy card. Visual analysis is a **lazy, exact-pair
VLM** that loads on demand and is released afterward. Remote phone access is a
**separate LXMF transport** with paired identities and default-deny privileges;
the HTTP server stays on loopback. The system includes a **privacy-safe
evaluation harness** that fingerprints a 124-prompt corpus and reports only
aggregates plus negative-control failures.

## What is not claimed

- The custom Android Sideband APK is **in progress**, not shipped.
- LoRa/RNode is an **experimental mesh transport**; Bluetooth pairing is not
  delivery proof; packet-loss numbers do not exist yet.
- Equal Shares picture/audio production is **paused** and is not a portfolio
  completion claim.
- No public source repository has been published yet.

## Résumé / LinkedIn bullets (safe)

- Built a local multimodal agent runtime with schema-validated tool calling,
  multi-call hops, and a legacy text-protocol fallback, covered by native-tool
  tests.
- Implemented GPU/CPU routing so an interactive chat yields to a local
  diffusion backend instead of contending for VRAM.
- Added a lazy visual-language path pinned to a specific GGUF + projector pair,
  with a live caption diagnostic that loaded, produced a result, and released
  the GPU.
- Designed remote access as paired LXMF over loopback HTTP rather than a
  public API; default-deny for privileged tools; 11/11 bridge tests on the
  last recorded run.
- Shipped a privacy-preserving evaluation harness: 124/124 valid prompts,
  synthetic negative controls, aggregate-only JSON (hashes, counts, timings).
- Wrote ADRs for localhost binding, tool calling, lazy VLM/render ownership,
  explicit-feedback-only learning, and CPU/GPU fallback.

## Evidence index

See `docs/portfolio/validation_matrix.md` and `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-30.md`.
Review those documents before publishing any numeric claim; rerun tests if the
tree has moved.
