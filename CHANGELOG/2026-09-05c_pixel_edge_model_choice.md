# 2026-09-05c — Pixel edge test model: swap to SmallThinker-3B-Preview-abliterated

## Scope

Planning-only decision for the PowerInfer-2 mobile edge evaluation track
(`TODO.md`, "PowerInfer-2 mobile edge evaluation — planning only"). No code
changed, no phone contacted, no runtime built, no GPU/ComfyUI/worker-farm
activity.

## Decision

The plan's step-2 test item ("run a single benign, battery/thermal-observed
Pixel test with a compatible 4B sparse model") is updated to name a specific
model: `huihui-ai/SmallThinker-3B-Preview-abliterated`
(https://huggingface.co/huihui-ai/SmallThinker-3B-Preview-abliterated), also
published as Ollama tags `huihui_ai/smallthinker-abliterated` and
`mannix/smallthinker-abliterated`.

Reasoning: it is built on PowerInfer's own SmallThinker sparse architecture
(runtime-compatible with the pinned mobile sparse engine this plan targets),
and huihui-ai is the same publisher already backing an existing GPU model in
this stack (`huihui_ai/qwen3-abliterated:8b`), so provenance is consistent
with what is already in production use here.

Trade-off accepted: this is the 3B-Preview line, not the 4B line the plan
originally specified. The closer size match to "4B sparse model" is the
official, non-abliterated `PowerInfer/SmallThinker-4BA0.6B-Instruct`
(4B total params, 0.6B active), but no abliterated variant of that exact
checkpoint was found published anywhere as of this date.

## TODO.md changes

- Step-2 test item now names `huihui-ai/SmallThinker-3B-Preview-abliterated`
  explicitly, with the reasoning and accepted size trade-off inline.
- New deferred item added: abliterate `PowerInfer/SmallThinker-4BA0.6B-Instruct`
  itself later, to close the size gap against the plan's original 4B target.
  Explicitly scoped as **new** abliteration work, not a reuse of the parked
  TurboSparse-Mistral pipeline or its calibration artifacts — and explicitly
  still gated behind this project's standing calibration-and-operator-approval
  process per `CLAUDE.md`. Not to be started opportunistically alongside
  unrelated tasks.

## What was not done

No runtime build, no download of any model weights, no phone contact, no
change to `local_agent/worker_farm/termux_powerinfer2_edge_worker.py`, no
TurboSparse-Mistral evidence or staging tree touched.

## Next step

Step 1 (cross-build the pinned Android sparse runtime on x86_64 Linux/WSL,
hash-recorded) is dispatched separately and unaffected by this model choice.
Step 2's Grok prompt, when sent, should reference this file for the model
pin instead of the generic "4B sparse model" language.
