# Local Agent — reproducible validation matrix

This matrix is the private-safe evidence index for a future portfolio. Run
commands from the canonical handoff root. Commands and expected results do not
include private files, credentials, identities, or network configuration.

| Area | Command | Expected outcome | Current evidence |
|---|---|---|---|
| H3 corpus evaluation | `python local_agent/h3_evaluation.py --dir outputs/equal_shares/prompts_native_r2v --output artifacts/evaluations/h3_prompt_validation_latest.json` | Aggregate-only JSON, 124 valid prompts, negative controls rejected | **Passed 2026-08-25**: 124/124; see H3 harness changelog |
| H3 baseline validator | `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v` | `124/124 valid` | **Passed 2026-08-25** |
| H3 harness regression | `python local_agent/test_h3_evaluation.py` | Privacy-safe aggregate result and negative controls | **Passed 2026-08-25**: 1/1 |
| Native function calls | `python local_agent/test_native_tool_calling.py` | Schema calls, multiple calls per hop, legacy fallback, guard validation | Run before public claim; retain only aggregate result |
| Local agent safety | `python local_agent/test_agentic_eval.py` | Offline, mocked tool/safety expectations | **Previously passed**; rerun before release |
| LXMF bridge | `python local_agent/test_lxmf_bridge.py` | Pairing, default-deny, tool audit, UTF-8 chunking, path-only attachments | **Passed 2026-08-25**: 11/11 |
| Sideband Tier B source | `python local_agent/test_sideband_tier_b.py` | Camera permission and path-only attachment boundary | **Passed 2026-08-25**: 4/4 |
| Exact VLM model identity | `python local_agent/test_qwen25_vl_caption.py` | Exact GGUF/projector configuration; no substitute VLM | Rerun only when GPU is free; never start a render for it |
| VLM lifecycle benchmark | controlled benchmark script (pending) | Cold-load, analysis, VRAM release, render-yield measurements | **Not yet measured** |
| Android package | WSL Buildozer build (pending operator download approval) | APK plus live device acceptance | **Not yet built** |
| Radio transport | controlled packet experiment (pending) | Delivery rate, loss, median/p95 latency by test condition | **Experimental; not measured.** Design: `docs/portfolio/radio_packet_experiment.md`. Inventory: `docs/portfolio/experimental_rnode_inventory.md`. Bluetooth pairing is not mesh proof. |
| VLM lifecycle | method in `docs/portfolio/vlm_lifecycle_benchmark.md` | Cold-load, analysis, VRAM release, render-yield | **Method only; not measured** (GPU owned by ComfyUI when written) |
| Public extraction | new repo per `docs/portfolio/public_repo_layout.md` | Synthetic fixtures, SPDX, audit clean | **Not created.** License draft: `docs/portfolio/license_inventory.md`. |

## Interpretation rules

- A source test passing is not a device or transport-acceptance claim.
- A configuration check is not a model-performance claim.
- Keep raw logs and media local; publish only redacted aggregate results after a
  reproducible run.
- Never start ComfyUI or a render merely to satisfy this matrix.
