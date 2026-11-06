# Upgrade 6a — phone over a USB cable. Do this BEFORE 06.

Paste everything below the line into Claude Code.

One small download: Android platform-tools (~10 MB). Nothing else.

---

Get the agent working on the operator's phone over a **USB cable**, using
`adb reverse`. This is the right first step: it proves the entire mobile
experience while changing nothing about how the server is exposed.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

## Why this approach is better than it sounds

`adb reverse tcp:8760 tcp:8760` makes a port on the **phone's own localhost**
forward, over the USB cable, to the **workstation's localhost**.

From the phone's browser, `http://127.0.0.1:8760` *is* the workstation's agent.

That has a property nothing else does: **the server keeps binding `127.0.0.1`
and nothing changes.** No `0.0.0.0`, no tailnet address, no firewall rule, no
network exposure of any kind. The transport is a physical cable. `ROADMAP.md`'s
"never bind 0.0.0.0" rule is not bent — it is not even touched.

It also needs no internet, no account, and no coordination server, which suits an
operator currently on a hotspot.

## What this DOES prove

Everything except the network:

- the UI on a real phone screen, with a real on-screen keyboard
- SSE streaming into a mobile browser
- the token layer
- the remote-vs-desktop permission tier
- conversations shared between phone and desktop
- reconnect behaviour when the stream drops

## What it does NOT prove

Be honest about this in the CHANGELOG — do not let it be mistaken for a
completed 06:

- NAT traversal and CGNAT, the actual hard part of remote access
- real latency and packet loss over cellular
- behaviour when the link drops for minutes rather than seconds
- whether the workstation is reachable at all when the operator is out

## Job 1 — the cable path

Install Android platform-tools on the workstation (~10 MB — state the exact size
before downloading). Then:

1. Phone: Settings → About → tap Build Number seven times → Developer Options →
   **USB debugging on**
2. Connect by cable, accept the RSA fingerprint prompt on the phone
3. `adb devices` — the device must show as `device`, not `unauthorized`
4. `adb reverse tcp:8760 tcp:8760`
5. Phone browser → `http://127.0.0.1:8760`

Write `local_agent/START_PHONE_USB.ps1` doing all of it: check adb is present,
wait for a device, set up the reverse, start the server if it is not running,
print the URL, and tell the operator plainly what to do if the device shows
`unauthorized` or `offline` — those two are the failures they will actually hit.

`adb reverse` does not survive unplugging. Have the script re-establish it if the
device reconnects.

## Job 2 — the parts that are NOT transport

These are the real work, and they are identical whether the bytes arrive over USB
or Tailscale. Do them now, so 06 becomes almost nothing.

**Authentication.** The agent has none today; its whole security model is the
loopback bind. Over `adb reverse` the requests *arrive* as loopback, so an exempt-
loopback rule would exempt the phone too. So:

- generate a token into `local_agent/remote_token.txt` on first run
- treat a request as **remote** if it carries the token, or if a
  `X-Client: phone` header is set by the phone UI — not merely by source address
- desktop browser on the same machine stays token-free
- constant-time comparison, never logged, `--rotate-token` provided

**Permission tier.** A remote session gets fewer powers, same table as 06:

| | desktop | remote |
|---|---|---|
| reads — `project_state`, `clip_info`, `read_prompt`, `duration_ladder`, `search_docs`, `read_file`, `list_dir` | yes | **yes** |
| `run_build` | yes | **no by default** |
| `write_file` | yes | **no by default** |
| `run_python` if present | yes | **no** |
| `propose_gpu` — proposes only | yes | yes |

Configurable in one obvious place. Wide only on purpose, never by accident.

**Mobile UI.** `static/index.html` is a fixed desktop layout with a 262 px
sidebar; on a phone it is unusable.

- responsive breakpoint below ~700 px — sidebar becomes a slide-over drawer
- touch targets ≥ 44 px
- the composer must stay visible above the on-screen keyboard
- `<meta name="viewport" content="width=device-width, initial-scale=1">`
- a clear **REMOTE** badge showing the reduced permissions
- if the SSE stream drops, reconnect and re-read the conversation rather than
  losing the reply — it is already persisted server-side

## Job 3 — leave 06 a short walk

Structure the permission check so the "is this remote" decision is **one
function**. USB answers it by header/token; Tailscale will answer it by source
address; Reticulum will answer it by cryptographic identity. Three transports,
one predicate, changed in one place.

Note in the CHANGELOG that this is the seam.

## Verify

- [ ] `adb devices` shows `device`; `adb reverse --list` shows the mapping
- [ ] the phone loads the UI over the cable with **Wi-Fi and mobile data off** —
      that proves the traffic is on the cable, not the network
- [ ] `netstat -ano | findstr 8760` still shows **127.0.0.1 only**
- [ ] a phone request without the token is rejected; the desktop browser still
      works untouched
- [ ] `write_file` and `run_build` are refused from the phone with a clear message
- [ ] a conversation started on the phone appears on the desktop and vice versa
- [ ] unplugging mid-generation, then replugging, recovers rather than losing the
      reply
- [ ] the UI is usable one-handed; the keyboard does not cover the input
- [ ] guard rails still refuse; `validate_h3_prompt.py` still **124/124**

## Do not stop

Work through. Stop only when every box is ticked and the `CHANGELOG/` entry is
written, stating plainly that this validates the mobile client but **not** remote
networking, which is upgrade 06.

Tell the operator where the token file is when done — it is a secret.
