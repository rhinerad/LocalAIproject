# 2026-09-22b — External project-family consolidation pass

## What changed

- Copied the newest stray local-agent health probe into:
  `scripts/diagnostics/local_agent_health_probe.ps1`.
- Copied the small `agent-tools` process helper into:
  `scripts/diagnostics/la_health_check.py`.
- Copied the stray audit marker into:
  `docs/audits/local_agent_audit_20260901.txt`.
- Copied the external historical Equal Shares handoff into:
  `docs/reference/external_handoffs/EQUAL_SHARES_CHATGPT_HANDOFF_2026-08-13.md`.
- Added an inventory and decision log:
  `docs/consolidation/external_project_family_inventory_2026-09-22.md`.

## Not changed

- No external source file was moved or deleted.
- The older `A:\Users\rhine\localagent` CLI harness was not merged.
- The public-safe `local-agent-core` repos were not merged.
- The large `A:\Users\rhine\agent-tools` transcript dumps were not copied
  wholesale.
- The stale `work/r98_patch/local_agent` fragment was not moved or deleted.
- No local-agent server, ComfyUI backend, render, model, predictor, or registry
  state was touched.

## Verification

- Read-only inspection confirmed the copied source files existed.
- The exact root-level WireGuard paths mentioned in the external summary were
  not present during this pass, so no WireGuard files were consolidated.
