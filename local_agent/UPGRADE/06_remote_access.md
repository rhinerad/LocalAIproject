# Upgrade 6 — reach the agent from your phone over cellular. Before the mesh.

Paste everything below the line into Claude Code. Run **after** upgrade 3.

Needs internet **once**, to install Tailscale. After that it works on cellular.

---

Make the local agent reachable from the operator's phone over the cellular
network, as an interim step before the Reticulum mesh in `local_agent/ROADMAP.md`.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

## Read this before writing any code

**The agent currently has NO authentication.** None. Zero. Its entire security
model is the single line binding it to `127.0.0.1` — the assumption that only a
process on this machine can reach it.

That assumption is about to be removed. And this agent can:

- write files anywhere not on the protected list
- run build actions that regenerate project state
- read any file on the machine
- (if upgrade 3 added it) execute Python

So **transport alone is not enough.** Even on a private network, the app itself
needs authentication. A phone left on a table is now a key to the workstation.
Both layers, or neither.

## Job 1 — the transport: Tailscale, not port forwarding

**Do not port-forward. Do not use ngrok or a public tunnel.**

Cellular carriers put phones behind CGNAT, so nothing can connect *in* to the
phone, and many home ISPs now do the same. Tailscale solves this: it is a
WireGuard mesh with NAT traversal and a relay fallback, so both devices dial out
and meet in the middle. Traffic is end-to-end encrypted between devices.

The free Personal plan covers this comfortably — as of August 2026 it allows six
users and **unlimited user devices**, with no expiry.

Install on the workstation and on the phone, sign both into the same tailnet.
Verify the phone can ping the workstation's `100.x.x.x` address over cellular
with Wi-Fi **off** — that is the actual test, not Wi-Fi.

**Alternatives, if a third-party coordination server is unacceptable:**
`headscale` is a self-hosted control plane but needs a VPS with a public IP;
plain WireGuard is free and fully self-hosted but requires a reachable endpoint
at home, which CGNAT may prevent. Tailscale is the pragmatic choice here.
Record which was chosen and why.

## Job 2 — bind to the tailnet interface only, never 0.0.0.0

This is the important line of code.

`server.py` currently binds `127.0.0.1`. Change it to bind **the Tailscale
interface address specifically** — not `0.0.0.0`.

The difference matters: `0.0.0.0` exposes the agent on every network the machine
joins, including hotel Wi-Fi and coffee shops. Binding the tailnet IP exposes it
only on the encrypted overlay, which no other network can route to.

Implement as `--bind` with a default of `127.0.0.1`, plus `--tailscale` which
discovers the tailnet address and binds that **in addition to** loopback. If the
address cannot be found, **fail loudly and stay on loopback** — never silently
fall back to a wider bind.

Update `ROADMAP.md`: the "never bind 0.0.0.0" rule stands unchanged; this is a
narrower exception, not a repeal.

## Job 3 — real authentication on the app

Add a token layer to `server.py`:

- a long random token generated on first run, stored in
  `local_agent/remote_token.txt` with a note that it is a secret
- every `/api/*` request requires it, via `Authorization: Bearer` header or a
  cookie set once from a `?token=` URL
- **loopback requests are exempt** so the desktop experience is unchanged
- constant-time comparison; never log the token
- a `--rotate-token` flag

Also add basic rate limiting on `/api/send` — a phone reconnecting in a loop
should not be able to queue fifty generations.

## Job 4 — remote gets fewer powers than the desk

A request arriving over the tailnet is not the same as one from the keyboard.
Add a permission tier keyed on whether the connection is loopback:

| | desktop (loopback) | remote (tailnet) |
|---|---|---|
| read tools — `project_state`, `clip_info`, `read_prompt`, `duration_ladder`, `search_docs`, `read_file`, `list_dir` | yes | **yes** |
| `run_build` — regenerates derived files | yes | **no by default** |
| `write_file` | yes | **no by default** |
| `run_python` if it exists | yes | **no** |
| `propose_gpu` — proposes only, starts nothing | yes | yes |

Make it configurable in one obvious place, defaulting to the table above. The
operator can widen it deliberately; it must not be wide by accident.

This is also the groundwork for Reticulum, where permissions will key on
cryptographic identity instead of loopback. Structure it so that swap is easy.

## Job 5 — make the UI usable on a phone

`static/index.html` is a fixed desktop layout with a 262 px sidebar. On a phone
it will be unusable.

- responsive breakpoint: below ~700 px the sidebar becomes a slide-over drawer
- touch targets at least 44 px
- the composer must not be hidden by the on-screen keyboard
- `<meta name="viewport" content="width=device-width, initial-scale=1">`
- show a clear **REMOTE** indicator with the reduced permission set, so it is
  never ambiguous which mode you are in
- assume a slow, flaky link: if the SSE stream drops mid-generation, reconnect
  and recover the reply rather than losing it. The conversation is already
  persisted server-side, so the answer survives — make the client re-read it.

## Job 6 — the workstation has to be awake

The agent cannot answer if the machine is asleep. Document, do not automate:

- how to disable sleep while allowing the monitor to turn off
- Wake-on-LAN over the tailnet if the operator wants it
- what happens if a render is mid-flight — the router already sends replies to
  CPU, so remote use during a render is fine and expected

## Verify

- [ ] phone reaches the workstation over **cellular with Wi-Fi off**, not just Wi-Fi
- [ ] the server binds the tailnet address and loopback, and **not** `0.0.0.0` —
      confirm with `netstat -ano | findstr 8760`
- [ ] a request with no token from the tailnet is **rejected**
- [ ] a request from loopback with no token still works
- [ ] a remote request to `write_file` or `run_build` is **refused**, with a clear
      message rather than a silent failure
- [ ] the same conversation is visible from both phone and desktop
- [ ] a dropped connection mid-generation recovers the reply instead of losing it
- [ ] the UI is usable one-handed on a phone; the keyboard does not cover the input
- [ ] with Tailscale stopped, the agent still works normally on the desktop
- [ ] guard rails still refuse; `validate_h3_prompt.py` still **124/124**

## Do not stop

Work through. Stop only when every box is ticked and the `CHANGELOG/` entry is
written — including which transport was chosen and why, and the exact permission
table as implemented.

**One thing to flag to the operator when done:** the token file is a secret that
grants access to their workstation. Tell them where it is.
