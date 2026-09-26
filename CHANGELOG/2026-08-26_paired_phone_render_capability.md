# 2026-08-26 — paired-phone current-chat render capability

## What changed

The remote-policy default remains deny. A paired LXMF identity can now receive
an explicit grant for **only** `start_current_chat_render`. The trusted LXMF
bridge injects the identity after pairing/capability verification; model tool
JSON cannot forge, select, or replace that identity.

An explicitly granted phone request can launch only the immutable general job
prepared from that same phone chat. It still:

- refuses all Equal Shares output paths;
- performs the existing prompt/job, queue-owner, ComfyUI-port, and thermal
  preflight;
- respects GPU gateway **Block**;
- writes a redacted, append-only remote tool audit record;
- cannot grant itself any permission, stop ComfyUI, edit files, run builds, or
  use broad folder-based batch rendering.

Desktop renders continue to require the visible one-shot GPU gateway approval.
The remote exception is intentionally narrow: the paired cryptographic identity
and explicit per-tool grant are its operator authorization.

## Verification

- Native tool suite: 24/24, including granted phone launch and global GPU Block
  refusal.
- LXMF bridge suite: 11/11, including pairing, default deny, audit, and
  transport-agnostic agent behavior.
- H3 validation: 124/124 valid.
- No model was loaded and no render was started.

## Operator control

Grant or revoke only this capability with `remote_security.py grant|deny` for
the exact 32-hex LXMF identity. Pair revocation disables all remote actions for
that identity.
