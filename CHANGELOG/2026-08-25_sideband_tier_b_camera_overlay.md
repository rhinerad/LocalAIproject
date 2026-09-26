# 2026-08-25 — Sideband Tier B camera overlay prepared

## What changed

- Added an Android-only **Capture Camera Image** entry to the checked-in
  Sideband fork's attachment menu.
- Declared the Android `CAMERA` permission, but request it only after the user
  selects that capture action.
- Captured images enter the existing Sideband medium-image attachment path. The
  app never receives a workstation path and does not directly invoke an agent
  tool or HTTP endpoint.
- Added a static no-model Tier-B regression suite and build/acceptance guide.
- Assigned the derivative its own Android package identity
  `local.equalshares.sidebandagent`, and updated its provider, service, cache,
  notification, and power-management references so it can be installed beside
  stock Sideband rather than replacing it.

## Why

Stock Sideband already carried files, gallery images, and recorded audio to the
paired bridge. The direct camera shortcut is the smallest phone-side addition
that closes the media-input gap while retaining Sideband's proven LXMF transport
and the bridge's default-deny remote capability boundary.

## Verification

- `python local_agent/test_sideband_tier_b.py` verifies the permission/capture
  route and path-only bridge boundary without importing Android/Kivy or loading
  a model.
- `python local_agent/test_lxmf_bridge.py` verifies paired attachment routing,
  unpaired refusal, redacted progress, and remote tool denial.

## Still unverified

No Android toolchain, SDK/NDK/JDK, APK, model, render, or remote privilege grant
was created. A real phone build and the six-item live media acceptance test in
`local_agent/SIDEBAND_TIER_B_BUILD.md` remain operator-gated.
