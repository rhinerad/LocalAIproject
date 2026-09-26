# 2026-08-28 — Trusted Android companion backlog

## Planned

Recorded the next local-agent phone upgrade in `TODO.md`: a controlled Android
companion path for operator-granted folders and workstation-built APK delivery.

The design preserves the active security boundary:

- Phone files remain limited to explicit Android Storage Access Framework
  grants, and grants must be visible and revocable.
- Every received file remains a new immutable workstation copy with a hash and
  audit record; the agent never receives unrestricted phone storage access.
- APK installation remains a phone-confirmed action after signing, hash, and
  requested-permissions review. Optional USB/ADB installation is separately
  bound to a trusted device and an exact operator-approved APK hash.
- No unattended remote installation via LXMF, Wi-Fi, or LoRa is permitted.

## Current test state

The paired LoRa scheduler has live-proven five-message delivery. A newly sent
phone-file transfer is awaiting receipt; no attachment evidence has been
claimed yet.
