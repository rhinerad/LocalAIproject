# 2026-08-25 — public-safe local-agent-core tree extracted and scanned

## What

A **new** git tree was created outside the canonical handoff folder:

`local-agent-core` on the operator home directory (not this working tree).

It reimplements public-safe **patterns** (tool loop, whitelist, loopback
preflight, identity default-deny, aggregate eval harness). It does not copy
Equal Shares media, prompts, workflow JSON, Sideband source, memory, or
weight files.

## Scan

Both scanners reported **0 findings**:

- `python local_agent/public_release_audit.py --dir <candidate>`
- `python -m local_agent_core.audit --dir <candidate>`

Reports (private): `artifacts/evaluations/local_agent_core_audit.json` and
`local_agent_core_private_audit.json`.

Extra grep for Windows drive paths, `/Users/`, `sk-`, `ghp_`, and PEM
key banners: no matches in the candidate tree.

Unit tests: **10/10 passed**.

## Git

Local `main` has two commits. GitHub CLI (`gh`) is not installed on this
machine, so no remote was created and nothing was pushed.

## Still required before a public GitHub push

- Human README/claim review
- `gh repo create` (or equivalent) from the candidate tree, not from this
  handoff folder
- SPDX/SBOM generation on that remote

## Not done

- Radio experiment, VLM VRAM timing, screen-capture demo
- Sideband APK / NumPy recipe (Codex)
