# 2026-08-27 — Loop Engineering design and persistent goal

## Request

The operator asked the local-agent project to remember Addy Osmani's June 7,
2026 “Loop Engineering” article and determine how its approach applies here.

## Recorded

The operator's interest is stored as durable local-agent memory id 40. The
preference is for measured, safety-gated loops with persistent state,
discovery/triage, separate implementation and verification, explicit
evaluations, and operator review. It explicitly excludes loops that bypass
render, download, permission, or evidence safeguards.

## Design added

`local_agent/UPGRADE/22_loop_engineering.md` maps the article's automation,
state, skill, connector, and independent-verifier ideas onto existing local
agent components. It defines a phased build beginning with read-only discovery
and testable state, then approved repair proposals, deterministic verification,
and finally worktree-isolated parallel work.

## Not enabled

No automation, render, download, model load, model training, unattended edit,
or remote permission was enabled by this design record. Implementation remains
operator-approved and must begin with the Phase 0 baseline/evaluation work.
