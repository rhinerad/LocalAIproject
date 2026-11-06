# ARCHIVE_DECISION.md — local only, never commit

Recorded 2026-09-05. Operator-decided. Not a changelog. Contains no
repository password.

## 1. Destination pair

- **Live sources:** A: (Toshiba MG08ACA16TE, disk 0, SATA, RAD Disk).
  Project media stays here. This is not a second Restic repository.
- **Encrypted Restic repository:** D: (Seagate Portable, disk 2, USB,
  unique id `3E543346485A464B`, volume label `Seagate Por`, exFAT).
  Dedicated new folder: `D:\restic-local-agent-evidence`
  (do not reuse `D:\Backups` or other existing trees).
- **Between runs:** unplug D: and store it elsewhere. Operator accepted
  this. While D: is plugged into this chassis, fire/theft of the tower
  can still take A: and D: together.

## 2. Recovery-secret custody

- Password manager (phone-synced), once a manager is installed.
- One offline copy stored away from the desk.
- Password is created at `restic init` via Restic’s interactive prompt
  only. Never on the CLI, never in argv, never in a file, never in a
  log, never in CHANGELOG.
- Shown once to the operator at init time to write down / enter into a
  manager before backup continues.
- No password manager is installed on this workstation yet.

## 3. Source-root scope (first pass)

Include only:

- `outputs/equal_shares/`
- `outputs/stories/`
- `docs/GOLDEN_REFERENCE/`
- Desktop Equal Shares packs:
  `EQUAL_SHARES_FIRST_APPEARANCE`,
  `EQUAL_SHARES_GENERATION_LIST`,
  `EQUAL_SHARES_VOICE_AUDITIONS`

Exclude this pass:

- `ComfyUI-Shared\output` entirely (no good-audio, no upscales)
- `local_agent/chats/`
- `.env`, keys, phone identities, WireGuard private keys
- virtual environments
- `ComfyUI-Shared\models`
- the source-and-documentation ZIP
- empty farm / powerinfer vaults

## 4. First restore-drill scope

- `docs/GOLDEN_REFERENCE/` (all files in that directory)
- one small Equal Shares manifest:
  `outputs/equal_shares/audio_pass_manifest.json`
- Not the good-audio folder (out of first-pass scope)

Scratch restore target: a fresh temp directory on C:, never overwriting
sources on A: and never inside the Restic repo on D:.

## 5. Execution window

Run only when all are true:

- GPU idle: temperature ≤ 70 °C (prefer ≤ 60 °C), ~0 % utilization;
  thermal emergency ceiling 82 °C — do not start if the card is hot
- Port 8188 down
- No live render-owner PID (Equal Shares / batch / image-render)
- Equal Shares pass confirmed still paused
- No in-flight local-agent media turn (`chat_busy.json` absent or PID dead)
- Farm Mac may stay up
- D: plugged in only for this window; unplug and store elsewhere
  immediately after restore-drill verify
- No `prune` / `forget` in this first window
