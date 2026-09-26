# 2026-09-08 — Remove camera-positive prompt tokens

Repeated exact-VLM rejections showed that negative prompts were insufficient:
the positive prompt still named the camcorder, tripod, lens, and body. The
still-job normalizer now removes those equipment-positive tokens and retains
only VHS/found-footage aesthetic plus an off-screen viewpoint. The next retry
must be a new evidence attempt; prior failures remain immutable.
