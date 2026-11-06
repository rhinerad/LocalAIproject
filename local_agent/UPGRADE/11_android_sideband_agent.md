# Claude Code / Codex prompt — the Android local agent by building on Sideband

Paste into your coding agent. Run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). Read `local_agent/ROADMAP.md`,
`local_agent/README.md`, `CLAUDE.md`, and `local_agent/UPGRADE/06b_phone_app.md`
first.

## The idea (why this is the path that actually works with the local agent)

**Sideband** (`markqvist/Sideband`, `sbapp` on PyPI) is an existing, mature Android
client for **LXMF over Reticulum** — it already does identity, pairing, the mesh
transport, message store-and-forward, and Android packaging. We do **not** rebuild
any of that. Instead we make the **workstation agent speak LXMF**, so:

- **Tier A — works with a stock Sideband app, no Android build.** The workstation
  runs the local agent as an **LXMF peer** (a Reticulum destination that receives a
  message, runs `agent.answer`, and replies). The operator adds that peer in a
  normal Sideband install on the phone and chats with the local agent immediately.
- **Tier B — a forked Sideband build for the agent extras.** Only once Tier A works,
  fork Sideband to add what a generic LXMF client lacks: sending **phone files** to
  the workstation `uploads/`, **camera → vision**, **mic → local Whisper**, and
  richer streaming/tool-event display — reusing Sideband's Reticulum stack and its
  python-for-android/buildozer packaging rather than writing an app from scratch.

The phone never runs a model. All compute stays on the RTX 5080. The handset is a
terminal.

## Non-negotiables (from ROADMAP.md — hold these throughout)

- `server.py` stays bound to **`127.0.0.1`**. LXMF/Reticulum is the remote
  transport; **never** bind `0.0.0.0`.
- `agent.answer()` stays transport-agnostic (history + event callback, no HTTP).
  The LXMF bridge calls it exactly like the GUI does.
- `store.py` stays transport-agnostic plain JSON; a chat from the phone and one from
  the desktop are the same files. Add a `source` field (`desktop`|`phone`) on
  messages.
- `tools.py` stays a fixed whitelist — the security model once a phone can reach in.
- **Per-identity permissions.** Map each paired phone LXMF identity to a capability
  set. Reads/chat/attachments from the phone are fine; `write_file`, `run_build`,
  and render proposals from a phone identity are **default-deny** and require an
  explicit, logged allow. Log every remote tool call with the caller identity.

## Phase 0 — verify the stack against current docs (MANDATORY; STOP at the end)

The roadmap forbids designing this from memory. Record findings in
`local_agent/UPGRADE/notes/sideband_agent_stack.md`:

1. **LXMF** (`markqvist/LXMF`) — the current API for standing up a `LXMRouter`,
   creating/announcing a destination identity, receiving inbound messages, and
   sending replies (including large content / fields for attachments). Decide the
   message shape for a turn and for streamed/partial replies (LXMF is
   store-and-forward; a turn may arrive as one message, and a long reply may be
   chunked).
2. **Reticulum (`RNS`)** — how the LXMF router is transported (TCP interface for
   same-LAN/Tailscale now; note LoRa/others later) and how a persistent workstation
   identity is stored.
3. **Sideband / `sbapp`** — confirm it is the LXMF Android client, how a user adds a
   peer/announce, whether it renders message **fields/attachments** (so Tier B can
   send files), and its build path (python-for-android / buildozer, Kivy). Confirm a
   fork can be built and installed on a device, and what toolchain that needs on
   this Windows box (JDK, Android SDK/NDK, buildozer under WSL, a device/emulator) —
   list exact steps, don't run them yet.

Output a one-page recommendation: message shapes, whether Tier B forks Sideband or
contributes a plugin/screen, and the build-environment plan. **STOP and report
before Phase 1.**

## Phase 1 — the workstation LXMF agent bridge (Tier A; no Android work)

- `local_agent/lxmf_agent.py`: start an RNS + LXMF node, load/create a persistent
  workstation identity, announce an "agent" destination. On an inbound message from
  a **paired** identity: rebuild the conversation from `store.py`, call
  `agent.answer(history, on_event, ...)`, and send the reply back over LXMF (chunk
  long replies per the Phase 0 decision). Unpaired identities get a one-line "not
  authorised" and nothing else.
- Reuse the exact agent path the GUI uses — do **not** duplicate agent logic. Add
  the `source="phone"` tag when persisting phone-originated turns.
- Add the **per-identity permission layer** in the tool-dispatch path so a phone
  identity cannot invoke a gated tool; log every remote tool call.
- Pairing: a tiny operator step on the desktop to add a phone's LXMF identity hash
  to the allowlist with its capabilities (a CLI or a small GUI field). Keep HTTP on
  `127.0.0.1`; the bridge is opt-in and only runs when started.
- A launcher entry (or documented command) to start the bridge alongside the server.

**Acceptance for Tier A:** from a **stock Sideband install** on the phone (or a
second Sideband/CLI LXMF client), the operator sends a message to the announced
agent destination and gets the agent's reply; a non-allowlisted identity is refused;
a gated tool from the phone is denied and logged; the desktop GUI is unchanged. CHANGELOG it.

## Phase 2 — forked Sideband for the agent extras (Tier B; after Tier A works)

Fork/extend Sideband (per the Phase 0 decision), reusing its Reticulum transport and
packaging. Land incrementally, each a CHANGELOG:

1. **Send phone files to the agent** — pick any file via Android storage and send it
   as an LXMF attachment/field; the bridge writes it to `local_agent/uploads/`
   (path to tools, never binary in conversation JSON — the 06b rule) and routes
   images → vision, audio/video → transcribe/audio_measure.
2. **Camera → vision, mic → local Whisper** — capture and send; transcription runs on
   the workstation's Whisper, never a cloud speech API. Until a model exists, the
   control names what is missing and its size (the honesty rule from upgrades 4 /
   06b).
3. **Agent-aware display** — show tool/route events and chunked streaming so a long
   generation reads well on the phone; a local notification when it completes.

Keep Sideband's normal LXMF messaging intact; the agent is an added peer type, not a
replacement. No project secrets on the handset — it holds only its RNS identity and
the paired workstation hash.

## Verify (per phase; show commands/output, live vs mocked)

- Workstation stdlib suites still green (`test_native_tool_calling.py`,
  `test_media_analysis.py`); `validate_h3_prompt.py` still **124/124**.
- New tests (mock LXMF/RNS I/O): a paired identity streams a full turn; an unpaired
  identity is refused; a gated tool from a phone identity is denied; `agent.answer`
  still knows nothing about transport.
- Live checks (need real RNS + a device — mark unverified until run): stock Sideband
  round-trip in Tier A; forked build installs and sends a file/camera/mic capture in
  Tier B.

## Rules that hold (CLAUDE.md / ROADMAP.md)

Never weaken a safeguard to pass a test; whitelist stays a whitelist; GPU-busy check
keeps failing safe; never bind `0.0.0.0`. Never start a render from the phone
(propose only, and only if permitted). Never delete a raw generation, reference,
manifest, audit record, or source media. Every phase ends with a `CHANGELOG/` entry
(what/why/evidence/verified/unverified) and its new files added to
`local_agent/README.md`.

## Note to the operator up front

State in the Phase 0 note: **Tier A gives a working phone agent through a stock
Sideband install with no Android build at all** — do that first and confirm it
before any fork. Tier B (the fork) needs an Android toolchain and a device, and
should reuse Sideband rather than rebuild its Reticulum stack.
