# 2026-09-10d — C001 identity-safe smile refinement

- Added exact reference-blind continuity enforcement to prevent prompt-biased
  semantic approvals.
- Installed and checksum-bound the SDXL IP-Adapter Plus Face identity model.
- Added bounded C001-only localized OpenPose/IP-Adapter recovery and preserved a
  QA-proven wave intermediate whose only remaining miss is the smile.
- Tested the requested hard-clamped lower-face mask. It achieved zero protected
  upper-face overlap but failed because the full-frame mouth region was too small
  in latent space and produced an object-like patch.
- Added `face_refine_identity`, which uses the installed Impact Pack FaceDetailer
  at crop resolution while compositing back into the untouched wave frame.
- Repaired Impact Pack imports by installing its missing declared `piexif`,
  `ultralytics`, `segment-anything`, and `dill` dependencies in the existing
  ComfyUI environment; isolated Ultralytics settings under project runtime.
- Preserved two preflight failures and two real FaceDetailer outputs. Both real
  outputs retained person/hair/beard/clothes/room/wave continuity, but blind QA
  rejected the expression as serious rather than an unmistakable smile.
- Prevented failed smile refinements from becoming future reference anchors.
- Added graph, artifact, policy-promotion, and immutable-anchor tests. Targeted
  suite: 62 tests, 0 failures.
- Production is safely paused at C001_last. No video was started. GPU and port
  8188 were released.

Detailed continuation instructions:
`work/C001_SMILE_REFINEMENT_CLAUDE_HANDOFF_2026-09-10.md`.

