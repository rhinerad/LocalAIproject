# Claude Code / Codex prompt — the native Android local-agent app over Reticulum

Paste into your coding agent. Run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). This is the `ROADMAP.md` end goal: a real
Android app that is a **thin client onto the workstation agent** over a Reticulum
mesh — the phone contributes camera, mic, and its own files; **all model compute
stays on the RTX 5080.** Read `local_agent/ROADMAP.md`, `local_agent/README.md`,
`CLAUDE.md`, and `local_agent/UPGRADE/06b_phone_app.md` before anything.

This is the largest piece in the project and spans multiple sessions. It is built
in **phases with STOP gates** — do not skip ahead. Each phase ends with a
`CHANGELOG/` entry and, where noted, operator approval before the next begins.

## Non-negotiables (from ROADMAP.md — hold these across every phase)

- **`server.py` stays bound to `127.0.0.1`.** Reticulum is the remote transport.
  **Never** bind `0.0.0.0` to reach the phone — an unauthenticated, tool-executing
  HTTP server must never touch a shared network.
- **`agent.answer()` stays transport-agnostic** (history list + event callback,
  no HTTP knowledge). That seam is where the Reticulum transport plugs in.
- **`store.py` stays transport-agnostic** plain JSON. A chat started on the phone
  and continued on the desktop is the same file. Add a `source` field
  (`desktop`|`phone`) on messages; add nothing that assumes one client.
- **`tools.py` remains a fixed whitelist.** Once a phone can reach the agent, the
  whitelist *is* the security model. Never relax it for convenience.
- **Per-identity permissions.** A remote phone identity and the desktop operator
  are not equal. Reads/chat/attachments from the phone are fine; `write_file`,
  `run_build`, and any render proposal from a phone identity require an explicit,
  logged allow decision. Default deny for state-changing tools from remote peers.
- **No model on the phone.** Ever. The handset is a terminal.

## Phase 0 — research + stack decision spike (MANDATORY; STOP at the end)

The roadmap forbids designing this from memory. Before writing app code, verify
against **current** documentation and record findings in
`local_agent/UPGRADE/notes/android_stack_decision.md`:

1. **Reticulum (`RNS`)** — current Python API for creating a node, announcing a
   destination, and request/response + link streaming. Source: reticulum.network
   manual and the `markqvist/Reticulum` repo.
2. **`LXMF`** — whether the agent link should be LXMF messages (store-and-forward,
   good for slow/interrupted links) or a raw RNS `Link` with resource transfer,
   or both (LXMF for turns, Link for live token streaming). Decide and justify.
3. **Sideband / `sbapp`** — the existing Android LXMF client
   (`markqvist/Sideband`, `sbapp` on PyPI), built with **python-for-android /
   buildozer** (Kivy). Determine whether to: (a) **fork/extend Sideband**,
   (b) build a **new Python-on-Android app** reusing its p4a + RNS packaging, or
   (c) a **Kotlin app embedding RNS via Chaquopy**. Note that the reference
   Reticulum stack is Python — a pure-Kotlin RNS reimplementation is out of scope.
4. **Android toolchain** — what the build actually needs on this Windows box
   (JDK, Android SDK/NDK, buildozer under WSL or Android Studio + Gradle, a device
   or emulator). Internet is available; list exact install steps, do not run them
   yet.

Output a one-page recommendation with the chosen stack and why, the transport
decision (LXMF vs Link vs hybrid), and the build environment plan. **Then STOP and
report — do not start Phase 1 until the operator approves the stack.**

## Phase 1 — the workstation transport seam (no Android yet)

Make the existing desktop agent reachable over Reticulum without changing its HTTP
behaviour:

- Define a small transport interface that wraps `agent.answer(history, on_event,
  ...)`. Prove it by routing the **existing GUI through it unchanged** (desktop
  experience identical — verify).
- Add `local_agent/reticulum_node.py`: starts an RNS node, loads/creates a
  persistent workstation **identity**, announces the agent destination, and for
  each inbound request builds the history and calls `agent.answer`, streaming
  events back over the chosen transport (chunked/resumable — a mesh link is not a
  low-latency socket; do not assume a held-open stream).
- Add the **per-identity permission layer**: an allowlist of paired phone identity
  hashes with a capability set each; enforce it in the tool-dispatch path so a
  remote identity cannot invoke a gated tool. Log every remote tool call with the
  caller identity.
- Add the `source` field to messages in `store.py`.
- Keep it all off by default — the node only runs when the operator starts it, and
  binding stays `127.0.0.1` for HTTP throughout.

CHANGELOG the seam + node + permission layer, with the tests below.

## Phase 2 — prove it with a CLI peer (STOP at the end)

Before any app: `local_agent/reticulum_cli_peer.py`, a headless RNS client that
pairs with the workstation node (by identity hash), sends a prompt, and prints the
streamed reply and any tool events. Run it from a second machine (or a second RNS
instance locally). This proves transport, identity pairing, streaming, and the
permission gate end to end. **STOP and confirm the link works before writing the
app.**

## Phase 3 — the Android app (chat → files → camera/mic, in that order)

Build per the approved Phase 0 stack. Land it incrementally, each a CHANGELOG:

1. **Chat client** — pair with the workstation identity (scan a QR of the identity
   hash or paste it), one conversation list backed by the *workstation's* store
   (the phone shows what the desktop shows; conversations are the same files),
   send/receive with streaming, offline/queued sends over LXMF when the link
   drops. A background service keeps the RNS connection; a local notification
   fires when a long generation completes so the operator can lock the screen.
2. **Phone file access** — this is the capability the PWA (06b) could not give:
   true handset filesystem access via Android's Storage Access Framework / scoped
   storage, so the operator can pick *any* file (not just push a share) and send
   it as an attachment; large files transfer as RNS resources with a size cap and
   clear progress. Uploads land on the workstation in `local_agent/uploads/`
   (path passed to tools, never binary in conversation JSON — same rule as 06b).
3. **Camera + mic as agent inputs** — capture a photo/video → vision tool; record
   audio → the workstation's local Whisper (never a cloud speech API). Until a
   given model exists, the control says what is missing and its size (the honesty
   rule from upgrades 4 and 06b). Respect Android runtime permissions.

Security in the app: the phone holds only its own RNS identity and the paired
workstation hash; no project secrets on the handset. State-changing tools obey the
Phase 1 permission gate — surface a clear "not permitted from phone" rather than a
silent failure.

## Verify (per phase — show commands/output; say what is live vs mocked)

- Workstation stdlib tests still green (`test_native_tool_calling.py`,
  `test_media_analysis.py`) — the seam must not regress them.
- New tests for the transport seam and permission layer (mock RNS I/O): a gated
  tool from a non-allowlisted identity is refused; an allowed identity streams a
  full turn; `agent.answer` still knows nothing about transport.
- `validate_h3_prompt.py` still **124/124**.
- Live checks (need real RNS + a device — mark unverified until run): CLI peer
  round-trip; app pairs and chats; a picked phone file reaches `uploads/`; camera
  photo → vision; mic → local Whisper; completion notification on a locked screen;
  desktop GUI unchanged throughout.

## Rules that hold (from CLAUDE.md / ROADMAP.md)

- Never weaken a safeguard to pass a test. Whitelist stays a whitelist; the
  GPU-busy check keeps failing safe; never bind `0.0.0.0`.
- Never start a render from the phone; propose only, and only if the identity is
  permitted.
- Never delete a raw generation, reference, manifest, audit record, or source
  media.
- Every phase ends with a `CHANGELOG/` entry — what changed, why, the evidence,
  what was verified, what remains unverified — and the phase's new files added to
  `local_agent/README.md`. Do not let this large piece land undocumented.

## Reality check to give the operator up front

State plainly in the Phase 0 note: this needs an Android build toolchain and a
physical device/emulator, spans multiple sessions, and the app is a real
application (packaging, a background service, runtime permissions, an RNS stack on
the handset) — not a script. Recommend whether forking Sideband beats building
fresh, with the evidence for it.
