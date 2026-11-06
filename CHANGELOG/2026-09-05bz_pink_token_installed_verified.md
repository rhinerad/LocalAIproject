# 2026-09-05bz — Pixel edge token installed and hash-verified in Termux

## Scope

Operator tracking entry, no code change.

## What happened

Operator ran the final Termux-side install step for the PowerInfer-2 edge
gateway token, in the Termux app on the Pixel 10 Pro itself:

```
mkdir -p ~/.config/local-agent
cp /sdcard/Android/data/com.termux/files/powerinfer-edge/edge-token ~/.config/local-agent/edge-token
chmod 600 ~/.config/local-agent/edge-token
sha256sum ~/.config/local-agent/edge-token
rm -rf /sdcard/Android/data/com.termux/files/powerinfer-edge
```

`mkdir`, `cp`, `chmod`, `sha256sum` all succeeded. Verified hash matches
the value recorded in `2026-09-05bt`:
`74f4303021b46a9e02985d4d18ac11e8e8be806e76169d1dc992811f7b51c699`. Token
is now live at `/data/data/com.termux/files/home/.config/local-agent/edge-token`,
mode 600.

Only the final `rm -rf` on the ADB-staged copy at
`/sdcard/Android/data/com.termux/files/powerinfer-edge/` failed with
"Permission denied" — expected, not a new problem: that directory was
created by `adb push` as the `shell` UID, so Termux (`u0_a320`) has
read/traverse rights (`711`/`644`, per `bt`) but not delete rights on an
entry it doesn't own. Not a security issue (still app-private storage,
unreachable by other apps) — just a leftover copy of the same token that
is already installed correctly. Operator advised to remove it with
`adb shell rm -rf /sdcard/Android/data/com.termux/files/powerinfer-edge`
from the PC (the owning UID) when convenient; not blocking.

## Status

Pink's token bootstrap is complete and verified. Clear to run the
single-benign-prompt `--once` test cycle next.
