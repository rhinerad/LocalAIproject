# 2026-09-15k — Patch MIPRO Phase-1 artifact and promote to production

Patched the winning MIPROv2 program so truncated 1.5b output cannot drop
Backrooms lore. Did not restart the 24-clip batch.

## Patch

Appended these exact sentences to
`models/dspy_compiled/temporal_physics_mipro.json`:

- `Must maintain a first-person camcorder perspective.`
- `Mandate 8-second generation lengths.`

Targets: `prog.predict.signature.instructions` and the complete empty-yellow-room
walk demo (`injected_prompt` and `reasoning`). Incomplete OPT01 input-only demo
left unchanged.

JSON round-tripped with `json.dumps(..., indent=2, ensure_ascii=False)`.

## Promote

Copied patched `temporal_physics_mipro.json` over
`models/dspy_compiled/temporal_physics_v1.json`. Files are byte-identical.

`load_compiled_temporal_physics()` accepts the promoted dump. The synthesized
four-demo writer now targets a temp path so unit tests cannot clobber
production `v1.json`.

## Safety

- No `batch_generate_backrooms.py` start.
- Queue owner remains released.
