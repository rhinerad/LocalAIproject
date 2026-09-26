# 2026-09-13k — C014 localized pose recovery rejected

The one allowed localized OpenPose recovery rendered as attempt
`d97cab19cf034ade91f7e51bf10c17f0` (SHA-256
`202738f7832a5d7aa19450f488a7a390659383e0509664c4547cf578bd95a7fa`).

Exact Qwen continuity review found the same person, hair, facial hair,
clothing, and room geometry. It still rejected the image because the pose was
forward-leaning, hands were visibly on a table rather than below the frame,
and a large gray lower-body obstruction appeared. The deterministic image
checks passed; semantic QA correctly kept the artifact ineligible.

The attempt, OpenPose guide, protected-face mask, render receipt, and QA
evidence are preserved. C014 last remains paused; no video or further seed
reroll was started.
