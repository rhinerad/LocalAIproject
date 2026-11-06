# 2026-09-13j — C014 last localized OpenPose recovery

After two fully reviewed FaceID/IP-Adapter whole-frame attempts failed to
produce the required backward-brace posture without drift, C014 now has one
separate, one-attempt recovery: protected-face, lower-torso-and-arms-only
inpainting guided by an auditable OpenPose skeleton. It does not alter either
prior candidate or allow another unconditioned seed.

The mask protects the full face/upper-face area and leaves the room outside the
lower actor region immutable. The workflow retains the exact accepted C014
start frame as its identity anchor, uses the existing SDXL FaceID/IP-Adapter
and Union/OpenPose ControlNet assets, and remains under normal mechanical and
exact-Qwen semantic QA.

Verification: `py_compile` plus the still retry, production integrity, and
media accuracy suites: **115 tests passed**. No video was started and no prior
evidence was overwritten.
