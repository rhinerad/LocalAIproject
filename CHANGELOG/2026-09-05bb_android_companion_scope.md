# 2026-09-05bb — Trusted Android companion upgrade (scope only)

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-05bb**.

Task #53. **No APK, no Sideband-fork edit, no production-agent change.**
Same posture as the edge-gateway routing contract: numbered sign-off
(A1–A14) must be accepted before any build.

## What landed

`docs/design_notes/TRUSTED_ANDROID_COMPANION_2026-09-05.md` — operator
sign-off routing contract. Review loop `499f772f` (write + one revise
round, 0 open issues).

Coverage:

- SAF persistable **per-folder** grants (`ACTION_OPEN_DOCUMENT_TREE`);
  never `MANAGE_EXTERNAL_STORAGE`. API 33: Download/volume root are
  **not** persistable trees (one-shot picker only). Example grants are
  `Documents/…`.
- Live ingest unchanged: paired 32-hex identity, `open("xb")` immutable
  copy, SHA-256, 75 MiB per item, `received_attachment` JSONL
  (`lxmf_agent.py` / `remote_security.py`).
- Revoke axes: SAF URI, workstation `revoke()`, ADB ledger. Phone-loss
  kill switch is pairing revoke (including ungated workstation **read**
  tools until then).
- v1 APK delivery is **USB only** (live `_send` has no outbound 0x05).
  Review: signing identity, SHA-256, requested permissions; Android
  `PackageInstaller` confirmation on the phone. No auto-`commit`.
- Optional USB/ADB: `adb_trusted_devices.json` (serial + fingerprint +
  exact APK hash + explicit row). Only workstation wrapper may `adb install`.
- Unattended LXMF/Wi-Fi/LoRa install is a list of **APIs that must not
  exist**, not a policy comment.

**A1–A14 are unsigned.** PR 0 is operator sign-off. First toolchain
touch is A13, then a no-product-APK pyjnius spike (PR 3b), not a
daily-driver APK.

## Tests

None (design-only). Existing `test_lxmf_bridge.py` / `test_sideband_tier_b.py`
were cited, not run as a change.

## Files

- `docs/design_notes/TRUSTED_ANDROID_COMPANION_2026-09-05.md` (new)
- `TODO.md` (pointer to the note; item stays `[ ]` until A1–A14)

## Scope

No `outputs/equal_shares/`. No GUI. No APK. No farm overlay. No
`MANAGE_EXTERNAL_STORAGE` added. APP_REVISION unchanged.
