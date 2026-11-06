# 2026-09-05bt — Termux token path: Android/data staging, not tmp

Date: 2026-09-05. Pixel 10 Pro, Android 17 (SDK 37). Termux
`googleplay.2026.06.21` (`targetSdk=37`, **not debuggable**).

Verified on device:

- `run-as com.termux` → `package not debuggable`
- `/data/local/tmp/powerinfer-edge` is `700 shell` — Termux cannot read
- `/sdcard/Android/data/com.termux` is `2770 u0_a320:ext_data_rw` — other
  apps cannot traverse; ADB shell can (`ext_data_rw`)
- Termux uid is **not** in `ext_data_rw` (1078); files adb-pushed as
  `shell` need `other` bits for Termux to read (`chmod 711` dir, `644`
  files). `chown` to `u0_a320` is not permitted from shell
- DocumentsProvider can *query* Termux home; `insert`/`write`-create/`delete`
  are unsupported from `adb shell content`
- `termux-setup-storage` already created `~/storage`; that path is shared
  storage and was **not** used

Staged (USB/ADB only) at
`/sdcard/Android/data/com.termux/files/powerinfer-edge/` with token SHA-256
`74f4303021b46a9e02985d4d18ac11e8e8be806e76169d1dc992811f7b51c699`.
Still needs a Termux-side `cp` into `~/.config/local-agent/` + `chmod 600`
+ delete staging. No `--once`, no Wi-Fi copy.
