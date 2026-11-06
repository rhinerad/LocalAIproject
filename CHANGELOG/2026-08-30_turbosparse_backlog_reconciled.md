# 2026-08-30 — TurboSparse backlog reconciled to the streaming path

## What changed

The stale PowerInfer-2 backlog line that directed future work to
`tools/powerinfer/abliterate_turbosparse.py` is now marked complete and
corrected to the verified streaming path:

- `tools/powerinfer/abliterate_loader.py`
- `tools/powerinfer/abliterate_turbosparse_v2.py`

The completed item records the canonical `20260830b` output, its exploratory
synthetic calibration status, and the existing prohibition on GPU dump, train,
convert, or benchmark work until approved calibration pairs exist.

## Why

`abliterate_turbosparse.py` is the preserved pre-fix implementation that uses
the full-shard loading route which caused the host-RAM stall. Leaving it as an
unchecked instruction could direct a later agent back to the known-bad path.

## Verification

Using the existing isolated `.venv-ablit` environment:

```text
test_abliterate_projected_math.py  -> math-ok; math-subprocess-ok
test_abliterate_loader_smoke.py    -> v2-smoke-ok
test_approved_calibration_pairs.py -> Ran 3 tests ... OK
```

These are bounded local tests. They did not download weights, load a model,
use GPU memory, start a server, alter ComfyUI, or touch the source checkpoint.

## Still unverified

The `20260830b` checkpoint remains parked. Its synthetic calibration does not
identify a scientific refusal direction; predictors/activations have not been
rebuilt; no quality or performance benchmark has been run. Operator-approved
harmful/harmless pairs and a separate GPU approval remain mandatory.
