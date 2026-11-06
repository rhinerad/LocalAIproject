# 2026-09-14ah - Synthesized temporal-physics DSPy artifact

Scope: bake four few-shot demos into `models/dspy_compiled/temporal_physics_v1.json`
without a cloud compile. `logs/run_traces/` is empty; labels come from
`inject_temporal_physics` (same strings the live orchestrator would emit).

## Demos

- Dynamic: flickering yellow hallway; handheld Level 0 corridor walk.
- Locked: static security camera; static tripod shot.
  Handheld family suppressed; VHS / unbroken take / 1990s kept.

Schema is DSPy 2.6+ state-only save for `TemporalPhysicsInjector`:
`prog.predict` with traces/train/demos, CoT signature fields
(Base Prompt, Style, Reasoning, Injected Prompt), `lm: null`.
