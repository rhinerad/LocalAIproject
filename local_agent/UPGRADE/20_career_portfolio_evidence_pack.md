# Career portfolio evidence pack

## Goal

Turn the verified, general-purpose local-agent work into a clear, privacy-safe
technical portfolio for AI-infrastructure, applied-AI, local-inference, MLOps,
developer-tools, and creative-AI pipeline roles.

This is an evidence and presentation track. It must never pressure the project
to overstate progress or relax safety controls merely to create a demo.

## Public-safe boundary

Never include the following in public material:

- private creative media, scripts, prompts, voice material, or raw uploads;
- personal names, identities, absolute paths, chat transcripts, keys, tokens,
  paired-device identities, or network configuration;
- model weights, model files, or assets that cannot legally be redistributed;
- unverified performance, reliability, security, or product-completion claims.

Use synthetic fixtures, redacted screenshots, and short reproducible test cases.
Call unfinished components **experimental** or **in progress**.

## Work items

1. Create a sanitized architecture diagram covering chat/model routing, native
   tool calling, retrieval/memory, GPU arbitration, media analysis, ComfyUI
   render ownership, and LXMF transport boundaries.
2. Produce decision records for key tradeoffs: localhost-only HTTP, tool
   whitelisting, structured Ollama calls, lazy VLM loading, CPU/GPU fallback,
   explicit feedback-only learning, and remote default-deny permissions.
3. [x] Add a reproducible validation matrix with commands, expected outcomes,
   and evidence links. Include native-tool multi-call, blocked unsafe
   operations, queue behavior, model release/yield, and transport permission
   tests. See `docs/portfolio/validation_matrix.md`.
4. Capture measured results only after a controlled benchmark: latency, VRAM
   usage, context behavior, and failure/recovery outcomes. Preserve raw test
   logs privately; publish summarized, redacted figures.
5. Create a public-safe repository layout with synthetic sample inputs,
   installation instructions, an architecture overview, a threat model, and
   an explicit model/license inventory.
6. Write one concise case study and targeted résumé/LinkedIn bullets using only
   completed, verifiable work. Review every claim against the changelog and
   test evidence before publication.
7. Record Android/Sideband work as an experiment until the custom APK is built
   and device-tested. Tier A pairing may be claimed only with its completed
   acceptance evidence; Tier B features may not be represented as shipped.

## Actionable portfolio to-do list

### Claims requiring evidence and benchmarking

#### H3 evaluation harness — completed 2026-08-25

Run the private-safe harness with:

```powershell
python local_agent\h3_evaluation.py --dir outputs\equal_shares\prompts_native_r2v --output artifacts\evaluations\h3_prompt_validation_latest.json
```

The JSON contains only aggregate evidence and hashes; it is not a public export
of prompt content. See `CHANGELOG/2026-08-25_h3_portfolio_evaluation_harness.md`.

- [x] Define a versioned MiniMax H3 prompt-validation evaluation harness around
  the existing 124-prompt corpus (`local_agent/h3_evaluation.py`).
- [x] Record the validator version, input-fixture checksum, execution command,
  elapsed time, pass/fail count, and structured failure reasons for every run.
- [x] Add synthetic invalid-prompt fixtures so the harness proves it can reject
  broken prompts rather than only reporting the existing 124/124 pass result.
- [x] Publish only sanitized aggregate evaluation results; retain private prompt
  content and source material locally.
- [x] Label ESP32 LoRa RNode work explicitly as an **experimental mesh transport
  layer** in all portfolio material.
- [x] Inventory the actual Heltec LoRa32 and LilyGO RNode hardware, firmware,
  antenna, frequency, bandwidth, spreading factor, coding rate, and legal
  operating assumptions without publishing device identities or network keys.
  See `docs/portfolio/experimental_rnode_inventory.md` (phone-side exact SKU
  still not independently re-verified).
- [x] Design a repeatable packet-delivery experiment covering controlled message
  size, distance/environment, retry behavior, latency, delivery rate, and loss.
  See `docs/portfolio/radio_packet_experiment.md`.
- [ ] Run the radio experiment across multiple sessions and report sample count,
  packet loss, median/p95 latency, failure modes, and limitations.
- [x] Record that Bluetooth pairing alone is not proof of end-to-end Reticulum or
  LXMF mesh delivery.
- [x] Create a controlled Qwen2.5-VL timing benchmark using the exact approved
  GGUF and matching projector only. Method only:
  `docs/portfolio/vlm_lifecycle_benchmark.md`.
- [ ] Measure cold lazy-load time, first-analysis latency, subsequent-analysis
  latency, VRAM before/during/after, and VRAM release time on the RTX 5080.
  Three controlled observations were recorded 2026-08-26. Stable output,
  VRAM, and release were measured, but cache effects invalidate a cold-load
  claim until a cold-cache protocol exists. See
  `CHANGELOG/2026-08-26_qwen25_vl_lifecycle_benchmark.md`.
- [x] Add regression controls verifying that the VLM does not load for ordinary
  text chat and that active render ownership blocks it before a VRAM/runtime
  check. These are mocked safety checks; a real render will never be started
  solely to make a benchmark claim.
- [ ] Publish the benchmark method and redacted aggregate results; do not claim
  performance until measurements are reproducible.

### Privacy-safe portfolio strategy

- [ ] Select a completely benign, legally usable test asset such as a public
  domain train video, and retain its license/source attribution.
- [x] Create a separate sanitized demo profile with synthetic prompts and no
  private project media, voice masters, scripts, identities, or uploads.
- [ ] Record a short screen-capture demo covering chat, structured tool use,
  media analysis, and guarded rendering/preflight behavior.
- [ ] Inspect every demo frame and blur or remove local paths, usernames,
  network addresses, keys, device identifiers, and private conversation text.
- [x] Create an architecture diagram showing the operator boundary, localhost
  HTTP server, agent/tool layer, GPU arbitration, ComfyUI ownership, and the
  Reticulum/LXMF remote-transport boundary.
- [x] Add separate diagrams for model/VRAM lifecycle and remote permission
  decisions so the safety design is easy to understand.
- [x] Write concise Architecture Decision Records (ADRs) for major tradeoffs.
- [x] Write an ADR explaining why remote commands use paired LXMF identities
  instead of exposing a public HTTP server or public IP.
- [x] Write ADRs for native Ollama function calling, localhost-only binding,
  lazy VLM loading, render ownership, explicit-feedback-only learning, and
  CPU/GPU fallback.
- [x] Review each ADR against current code, tests, and changelog evidence before
  publication.
- [x] Define a public-release boundary so the canonical private project is never
  mistaken for a publication source. See
  `docs/portfolio/public_release_boundary.md`.
- [x] Audit candidate modules and all transitive licenses before open sourcing
  anything. Draft only: `docs/portfolio/license_inventory.md`. Not an SBOM.
- [x] Extract only public-safe core modules for a new repository: orchestration
  engine, structured tool-calling router, and ComfyUI preflight checkers.
  Candidate tree: home-directory `local-agent-core` (local git, not this
  handoff folder). GitHub remote not created (`gh` missing).
- [x] Add synthetic fixtures, installation steps, tests, security boundary
  documentation, and a model/license inventory to the public repository.
- [x] Keep workflow JSONs, private UI work, media, prompts, model files,
  identities, paths, runtime state, and all secrets private.
- [x] Perform a final secret/path/license scan before the first public push.
  Both scanners 0 findings; extra token/path grep clean. Human review and a
  GitHub remote are still required before a public push.
- [x] Write one concise case study and targeted résumé/LinkedIn bullets using
  only completed, verifiable work. See
  `docs/portfolio/case_study_and_resume_bullets.md`. Review before publishing.

## Definition of done

- A hiring manager can understand the system in under five minutes without
  access to private project content.
- Every public claim has a linked test, changelog entry, measurement, or
  reproducible demonstration.
- No private data, sensitive device/network details, or restricted assets leave
  the workstation.
- The portfolio explicitly distinguishes completed functionality, measured
  prototypes, and planned work.
