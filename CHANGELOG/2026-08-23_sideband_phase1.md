# 2026-08-23 — Sideband/LXMF workstation bridge (Phase 1)

## What changed

- Added `local_agent/lxmf_agent.py`: a separate, opt-in LXMF peer using the same
  transport-agnostic `agent.answer()` path as the localhost GUI. Inbound turns are
  serialized through one worker; long UTF-8 replies are numbered and chunked.
- Added `local_agent/remote_security.py`: persistent pairing by 32-hex LXMF source
  address, per-identity grants, default-deny privileged tools, recoverable identity
  revocation, and append-only pairing/tool audit logs with redacted arguments.
- Added a backward-compatible `source` field to stored messages. Existing messages
  load as `desktop`; bridge messages persist as `phone` with identity/request IDs.
- Routed the trusted tool context through URL prefetch and native/legacy model tool
  calls. The model and incoming fields cannot grant capabilities.
- Added `START_SIDEBAND_BRIDGE.ps1`, bridge documentation, pinned dependency record,
  offline RNS smoke configuration and mocked bridge/security tests.
- Installed pinned RNS 1.5.0, LXMF 1.1.1 and pyserial 3.5 under
  `local_agent/vendor/`. The user-level Python directory was not writable, so no
  global Python installation was changed.

## Safeguards preserved

- `server.py` still binds only `127.0.0.1:8760`; LXMF is a separate transport.
- `agent.py` imports neither RNS nor LXMF. `tools.py` remains the fixed whitelist
  and retains every existing argument/path/protected-record validation.
- A phone defaults to read/chat/sensory access. `write_file`, `run_build`,
  `propose_gpu`, `batch_render`, `remember_fact`, and `forget_fact` require an
  explicit grant for the exact paired identity. A render proposal still cannot
  execute a render.
- The Equal Shares pipeline and port 8188 were not started or changed.

## Verification

- `test_lxmf_bridge.py`: 8/8 passed (paired full turn, unpaired refusal, remote
  gated denial plus redacted audit, per-identity grant, lossless bounded chunking,
  unchanged underlying tool guards, old-chat source migration, transport-independent
  agent module).
- Existing suites: native tools 9/9, media 9/9, router 13/13.
- `validate_h3_prompt.py`: 124/124 valid.
- Installed-module check: RNS 1.5.0 and LXMF 1.1.1 import from the pinned local
  vendor directory.
- Safe live initialization against an offline RNS config created/reloaded the
  persistent LXMF identity, registered/announced the delivery destination and
  stopped cleanly. Address: `2adc394dd3e580e4965aa88aa7b67cc4`.

## Still requiring the operator's phone

The stock-Sideband end-to-end network round trip is unverified until the phone's
LXMF address is paired and both peers share a Reticulum interface. Tier B Android
files/camera/microphone work has not started.
