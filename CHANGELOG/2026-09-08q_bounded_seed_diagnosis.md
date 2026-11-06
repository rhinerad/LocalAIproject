# 2026-09-08 — Bounded duplicate/camera retry diagnosis

Five exact-VLM reviews rejected C001 for visible camera equipment. The failure
was reproducible under the fixed seed, so still jobs now use deterministic
per-clip/per-frame seeds to avoid cloning one bad composition while remaining
reproducible. No adaptive multi-failure rewriting is enabled; that remains a
tracked follow-up.
