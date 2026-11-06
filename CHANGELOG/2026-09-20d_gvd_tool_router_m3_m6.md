# 2026-09-20d — GVD tool router M3–M6 control plane

Continues `2026-09-20c`. Implements remaining spec modules: family inventory,
discovery adapters, promotion gates, planner, model-switch protocol, dialogue,
lip-sync, repair, assembly, and quality gates. No custom nodes or checkpoints
were installed. No live Comfy submit.

## M3 family scan (Rockernow custom_nodes)

Installed, still blocked pending a measured local VRAM profile:
IPAdapter, ControlNet Aux, VideoHelperSuite, ProPainter, Wan, LTX, MiniMax H3
(feihou-easy-h3 + MiniMax-H3-Turbo), HF-Flux.

Missing nodes, visibly blocked:
StoryDiffusion, AnimateDiff/Fizz, F5-TTS Comfy pack, MuseTalk, SAM2,
TiledDiffusion, LongCat.

## M4 discovery

HTTPS fetcher rejects non-HTTPS, credentials-in-URL, private/loopback DNS,
disallowed hosts, and model/archive suffixes. Quarantine is hash-named and
immutable. Search wraps `search_backend`. Validation queue is SQLite and
reconciles `validation_pending` after a crash. Nothing is pip-installed.

## M5 promotion

Unknown node classes require a code-trust receipt. `promote` still refuses
unknown VRAM. Rollback snapshots remain under `registry/releases/`.

## M6 extensions

- Planner: narrative → typed manifest; unknown text returns NEEDS_MANIFEST_REVIEW.
- F5 dialogue and MuseTalk lip-sync fail closed (`adapter_required` / missing nodes).
- Repair copies source bytes then blocks without a ProPainter VRAM profile.
- Assembly writes a narrative-order EDL.
- Quality gate checks duration tolerance and protected-region hashes.

## Tests

`python local_agent/test_gvd_tool_router.py` — 27 passed.

## Still not a live family activation

LTX/Wan/H3/IPAdapter cannot enter `active.json` until a cold+warm local
resource profile is measured on this 5080. That is a GPU smoke pass, not a
missing module.
