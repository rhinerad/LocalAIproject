# 2026-09-05ax — Status sync: DeepSeek closed, two scopes clean, Pixel token on-device

## Scope

Operator-facing tracking entry for four reports found together
(`2026-09-05as`/`at`/`au`/`av`). No new production work from this entry.

## 2026-09-05at — DeepSeek-14B tool-calling: avenue closed

Real, well-isolated conclusion. Lowering temperature didn't change the
wrong-tool selection; capping `num_predict` just truncated the reasoning
before any call fired. Control test proved the weights *can* call
`read_file` correctly when it's the only tool in the schema — with the
full 67-tool catalog they prefer a vision tool for a markdown file. This
is catalog-drowning / reasoning quality, not a template or format gap,
and shrinking DeepSeek's schema to fix it would be a DeepSeek-only
crutch. No better-maintained R1 tool-calling tag exists worth a 9GB pull
(the two alternatives checked are either already tried or explicitly
documented upstream as unstable). Hop-1 silence from 2026-09-05n was
confirmed to be the already-fixed empty-completion shape, not a
remaining bug. **Recommendation: close the avenue, do not retag, keep
tool-using logic hops on Huihui-14B as an operator decision, not another
DeepSeek experiment.**

## 2026-09-05au — 3D generation routing contract: scoped

Live re-inventory confirms nothing changed since 2026-08-28:
`routing_ready` still False, no 3D workflow JSON exists anywhere, two
relevant custom nodes are still `.disabled` from the 2026-09-04j
sageattention break. Design note specifies the concrete bindings a real
contract needs (via existing `enqueue_workflow`, not a new
`comfy_generate action=3d`), reusing existing preflight/thermal/owner
checks. No tool exposed, contract stays `status: "draft"`.

## 2026-09-05av — Phone-call assistant: scoped, honest "no clean v1"

Important finding: **there is no clean v1 that actually dials.** Neither
the paired phone (LXMF chat identity, not cellular) nor Sideband's
"telephony" (LXST over Reticulum, cannot reach a real phone number) can
place a real call today. A real dial needs either a telephony API
(Twilio-class — needs a vendor account and a public webhook, which
conflicts with this project's loopback-only HTTP posture) or an Android
intent contract that the companion TODO item hasn't approved yet.
Forcing a v1 here would be an implicit extension of Sideband/the phone
scheduler, which the TODO explicitly forbids. What can exist later, only
after real sign-off: a `call_gate` modeled on `file_edit_gate` (not
`gpu_gate`'s allow-and-go pattern), simulated dial/cancel/timeout, and
recordings held off pending actual legal review — correctly flagged as
a legal question, not a code comment.

## 2026-09-05as — Pixel edge token on-device

Duplicate of the report just relayed in chat: ADB push succeeded,
on-device token SHA-256 matches the workstation
(`74f4303021b46a9e02985d4d18ac11e8e8be806e76169d1dc992811f7b51c699`),
still scoped to `pixel1`/`edge_text_inference` only. Termux client config
copy and the first `--gateway` run are the remaining steps.

## Status

Task tracker: DeepSeek investigation fully closed (no code, an honest
recommendation). 3D and phone-call scoping both complete, both correctly
identified as not-yet-buildable without further operator decisions —
neither forced a premature v1.
