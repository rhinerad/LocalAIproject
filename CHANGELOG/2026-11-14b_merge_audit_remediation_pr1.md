# 2026-11-14b — Merge the 2026-11 audit remediation (PR #1) into main

## What changed

`claude/epic-hypatia-6mrayy` (PR #1: the 2026-11-02 audit, its part 1 and
part 2 remediation, lint, docs consolidation) is merged into `main`. Earlier
today `main` was fast-forwarded to `claude/jolly-dirac-9impbq`, so this is the
first commit where both lines of work are together.

Four conflicts, resolved by hand:

| File | Resolution |
|---|---|
| `.gitignore` | Took the PR's comment retiring the blanket `work/` rule |
| `README.md` | Kept the new public overview at the top; dropped the old Equal Shares H1 the PR had already retired |
| `local_agent/README.md` | Took the PR's pointer to the archived history, and carried forward the current "Local-first, plan-only cloud assist (2026-11-04)" paragraph, which is policy, not history |
| `local_agent/router.py` | PowerInfer detection (3 hunks): both sides made the same PureWindowsPath fix; took the PR's `_names_powerinfer_server` helper (`_proc_stem` and `_exe_stem` are identical, both kept). `decide()`: kept both new parameters, `allow_cloud` (model gateway) and `snapshot` (eviction poll), and both docstring notes. `status()`: kept both `model_gateway` and `render_eviction` keys |

## Evidence

Full `pytest` run in a Linux container, compared with `main` before the merge
(with `--continue-on-collection-errors`, because `main` alone stops with 5
collection errors):

- before: 233 failing test IDs
- after: 228 failing test IDs, 2,248 passing
- 9 tests failed only after the merge (`test_agent_stream_guard.py`,
  `test_agent_farm_trust.py`). Cause: the PR stops tracking the generated
  knowledge pack. After `python local_agent/build_knowledge_pack.py`, all 26
  tests in those two files pass. Not a code regression.
- 14 tests that failed before now pass.
- The remaining failures are identical before and after and need files that
  live only on the workstation (`work/*.py` modules, `vendor_sideband`, torch,
  absolute `A:\` paths).

Unverified: nothing here was run on the workstation, and no render was made.
Router changes are unit-tested only.

## Before the workstation syncs this (important)

The PR stops tracking runtime files, so on the workstation a plain merge of
`main` would **delete them from disk**: the Reticulum identity and mesh state
(`local_agent/rns_wifi/storage/`, phone pairing breaks), `adb`/`fastboot`
binaries (`local_agent/vendor_tools/platform-tools/`), `CHANGELOG/.id_claims/`,
the retrieval caches, and `tools/powerinfer/.hf_cache/`. Before merging `main`
into the workstation branch, back those folders up, or untrack them in the
workstation checkout first (`git rm -r --cached <path>` and commit), so the
merge has nothing left to delete.

Still open from the audit (operator): rotate the Reticulum identity and re-pair
the phone, run `scripts/untrack_private_data.ps1`, and decide on a history
rewrite for the chats, uploads and keys that are still in old commits.
