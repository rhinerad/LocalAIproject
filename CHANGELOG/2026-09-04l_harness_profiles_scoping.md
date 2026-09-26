# 2026-09-04l — Model-aware harness profiles: scoping + test baseline, no implementation

Date: 2026-09-04. Host: DuranGamingPC.
Id from `python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04l**.
Parent: `docs/FARM_EFFICIENCY_EVALUATION_2026-09-04.md` Finding 1 (sharpened),
`TODO.md` farm-efficiency ticket 2. Routing this keys off is live
(`2026-09-04i` / `2026-09-04k`).

## What was asked

Scope the CPU/farm compact harness (comfyui-mcp-style
`list_tools` / `describe_tool` / `call_tool`, lean on `action_resolver`,
GPU path unchanged) **before writing any harness code**. Record a clean
before-state of `test_native_tool_calling.py` and `test_action_resolver.py`.

## What was written

- `docs/HARNESS_PROFILES_DESIGN_2026-09-04.md` — concrete wrapper design:
  switch off existing `router.Decision.tier` / `backend` (no new signal);
  virtual meta-tools not added to `TOOLS`; `schemas()` default stays the
  full GPU surface; `call_tool` unwraps in `agent.run_one` so specialist /
  batch / conversation-id guards see the inner name; per-hop profile
  recomputation; Layer A (execution-first sentence) vs Layer B (extra
  CPU-only intents, later PR); test hazard that `_Route` defaults to
  `tier="cpu"`.
- `TODO.md` — ticket 2 notes the live 65+29 baseline (eval said 57+29)
  and points at the design doc. Still unchecked; implementation not started.

## Test baseline (clean, this session, no harness edits)

```
python local_agent/test_native_tool_calling.py -v
  Ran 65 tests in 5.994s
  OK

python local_agent/test_action_resolver.py -v
  Ran 29 tests in 0.127s
  OK
```

Live registry (not the eval's "~65"): `TOOLS` = **67**, `schemas()` = 67,
`schemas(include_project=False)` = 54, schema JSON = 40,511 chars.

No GPU load, no Ollama, no farm submit, no ComfyUI start. Suites are
mocked at those boundaries.

## What was not done

No change to `tools.py`, `agent.py`, `action_resolver.py`, `router.py`,
or `farm_offload.py`. No meta-tool layer. No new tests. No live Qwythos
compact trial. Implementation waits on design acceptance (three open
questions in the design doc §10).
