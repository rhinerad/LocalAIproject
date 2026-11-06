# Sideband / LXMF agent bridge — Phase 0 recommendation

**Status:** Phase 0 was verified against current upstream documentation on
2026-08-23, and the recommended **Tier A workstation bridge was subsequently
implemented and live-paired** the same day. Pinned local RNS 1.5.0 and LXMF
1.1.1 are present under `local_agent/vendor/`; the bridge stays separate from
the localhost GUI. Tier B (the Android/Sideband fork) remains unstarted.

## Recommendation

Proceed with **Tier A first**: a small, opt-in workstation LXMF peer that a stock
Sideband client can message.  This is the lowest-risk path because LXMF already
supplies encrypted delivery, queues, retries and receipts; the workstation only
adapts an inbound LXMF turn to the existing transport-independent
`agent.answer(history, on_event, ...)` seam.  Sideband describes itself as an
LXMF-compatible Android client and supports other LXMF clients, so no Android
build is necessary to prove the phone experience.  Do not start Tier B until a
real stock-Sideband round trip passes.

## Verified stack findings and message contract

1. **LXMF:** create one `LXMF.LXMRouter(storagepath=...)`, register a delivery
   callback, register a persistent delivery identity, and announce that delivery
   destination.  The documented send path is `LXMF.LXMessage(destination, source,
   content, title, ...)` followed by `router.handle_outbound(message)`.  LXMF
   payloads have separate content, title and a dictionary-valued fields section;
   fields are the correct future carrier for protocol metadata and attachment
   descriptors, never a reason to put binary data in chat JSON.
2. **RNS:** create exactly one `RNS.Reticulum(configdir=...)` instance in the
   bridge process.  Store the workstation's private identity under an excluded
   runtime directory (for example `local_agent/runtime/lxmf/identity`) with user
   access only; losing it changes the peer identity.  The bridge announces its
   destination on start and uses normal RNS path discovery.  Initial connectivity
   should be a configured local/Tailscale TCP interface or an existing Reticulum
   transport path.  It is **not** HTTP and does not change `server.py`'s
   `127.0.0.1` binding.  LoRa and other interfaces remain later transport choices.
3. **Sideband:** it is an Android LXMF-over-Reticulum client and also documents a
   plugin system, including service plugins.  Tier A only needs a normal contact/
   announced LXMF destination in the stock client.  Its stock UI must be proven
   with a real phone because upstream documentation does not promise custom
   agent-specific rendering of arbitrary fields or attachments.  Therefore Tier B
   should be a narrow **Sideband fork with an agent conversation screen/service**,
   not a separate Reticulum app and not a replacement for normal Sideband chats.

**Phase-1 wire shape.** Each inbound message uses text `content` for the operator
turn and fields such as `{protocol: "equal-shares-agent/1", conversation_id,
request_id}`.  Its `source_hash` identifies the caller.  The bridge resolves that
identity through its paired-identity allowlist *before* rebuilding history or
calling the model.  Each reply returns the same `conversation_id` and
`request_id`, with `{kind: "final", sequence, final: true}`.  A response longer
than the conservative post-install measured payload limit is UTF-8 chunked into
numbered LXMF messages; the phone may reassemble only a complete sequence.  Tool
and token events are not assumed to be a live stream: Phase 1 will emit only a
final reply, while Tier B may later display ordered status chunks.

**Permissions and audit.** `store.py` gets a backward-compatible per-message
`source` value (`desktop` or `phone`) plus optional remote identity metadata; no
socket/session concepts enter stored chats.  The LXMF bridge supplies an immutable
request context to the tool dispatcher.  The default remote capability set is
read/chat only: `write_file`, `run_build`, `propose_gpu`, `batch_render`, and all
render-related actions are denied unless that exact paired identity has an explicit
allow.  `tools.py` remains the fixed whitelist and still validates every argument.
Every remote tool attempt (including denial) is appended to a local audit log with
timestamp, identity hash, conversation/request IDs, tool, permitted/denied result
and redacted arguments.  The model never decides permissions.

## Build plan and gates

### Phase 1 — Tier A workstation bridge (approval required)

1. Install only `rns` and `lxmf` into the local-agent Python environment; pin the
   tested compatible versions in a local requirements record.  Do not install
   Sideband or an Android toolchain.
2. Add `local_agent/lxmf_agent.py`, an explicit bridge launcher, persistent
   identity/allowlist stores and mockable RNS/LXMF adapters.  It stays separate
   from the localhost GUI server.
3. Add the source migration, request context, permission gate and audit log at
   tool dispatch; preserve the existing whitelist and render-proposal-only rule.
4. Add stdlib mock tests: paired round-trip, unpaired refusal, denied remote gated
   tool recorded, chunk order, and proof that `agent.answer` has no transport
   import.  Re-run native tools/media/router suites and the 124/124 H3 validator.
5. Perform the live acceptance check with a stock Sideband phone: pair the identity,
   import/find the announced peer, exchange a short message, then test an unpaired
   refusal and a denied write/render attempt.  The desktop GUI must remain unchanged.

### Phase 2 — Tier B Sideband fork (only after Tier A live acceptance)

Use the Sideband source tree and its Kivy/service/plugin architecture.  Implement
file selection first: an attachment is validated and written to
`local_agent/uploads/<request-id>/`, then only its local path/metadata enters a
tool request.  Add camera and microphone capture second, routing the file to the
existing workstation vision/Whisper tools.  Add ordered completion/tool cards last.

**Android build environment, planned but not installed:** on this Windows machine,
use WSL2/Linux for Buildozer; its current documentation says Windows users build
through WSL and use Windows ADB/platform-tools for device access.  Prerequisites
to install only after Tier A: a Linux distribution, JDK 17, Android SDK/platform
tools and NDK selected by the fork's build configuration, Python virtual
environment, Buildozer/python-for-android dependencies, a USB-debug-enabled test
phone and an APK signing key.  Build a debug APK first, deploy with ADB, then test
storage/camera/microphone runtime permissions.  This is intentionally deferred:
the first build downloads the SDK/NDK/toolchain and is unrelated to the Tier-A
proof.

## Decision

**Tier A completed; stop here for mobile work.** A stock Sideband phone has
completed a paired LXMF round trip with the workstation bridge, while privileged
remote tools remain default-denied. Approval is still needed before Tier B's
Android build, file/camera/microphone integration, toolchain downloads, or any
new remote capability grant.

## Sources checked

- LXMF API and payload/router examples: https://github.com/markqvist/LXMF
- Reticulum API and destination/announce semantics: https://reticulum.network/manual/reference.html
- Sideband compatibility, Windows setup and plugin architecture: https://github.com/markqvist/Sideband
- Buildozer's current WSL/Android toolchain guidance: https://github.com/kivy/buildozer/blob/master/docs/source/installation.rst
