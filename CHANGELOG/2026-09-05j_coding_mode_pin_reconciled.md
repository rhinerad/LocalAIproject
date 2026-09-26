# 2026-09-05j — Coding-mode picker pin vs auto capability routing: reconciles

## Scope

🟢 lane, Task #46. Audit only, no production code changed.

## Finding: reconciles cleanly

The desktop "Coding mode" picker always sets an explicit `model=` pin
(the real Ollama tag, e.g. `josiefied-qwen2.5-coder-14b:q4_k_m` /
`JOSIEFIED_CODER_MODEL`) on the first message; it never leaves `model=None`.
`#prefer` (Compute Auto: auto/cpu/gpu) is a separate control and is not the
model pin. The picker is chosen once per chat and disabled after the first
message.

Because of that, the 2026-09-05e "DeepSeek surprise" scenario (an unpinned
logic-flavored prompt auto-routing away from the intended model) cannot
happen on desktop — desktop never calls `decide()` with `model=None` for a
Coding-mode chat. `classify_capability()` short-circuits on a Coder /
`is_coding_model()` pin and returns `CAP_CODE` immediately regardless of
prompt text, so a logic-flavored message in a Coding-mode chat stays on the
pinned Josiefied-14B.

Internally this takes a different branch than the 2026-09-05e Huihui-pin
case (Huihui: classifier falls through to text, but `want_capability_gpu`
is false so the pin still wins; Coding-mode: `want_capability_gpu` is true
because `is_coding_model()` matches, and `prepare_gpu_model` runs with
Josiefied) — but the user-visible result is identical in both: the selected
model is kept, the farm path is skipped (`model is None` fails either way).
`_timeshare_would_load_host_gpu()` is consistent too: a Coding-mode pin is
treated as a host-GPU load of Josiefied specifically, not a different
capability model.

Reverse-UX check: not indistinguishable. Desktop's default new-chat model
is the first available `chat_models()` entry (Huihui-14B), not
prompt-based auto-routing, so a code-looking message in a default chat
stays on Huihui per the 2026-09-05e pin contract. Auto `CAP_CODE` →
Coder-14B only happens for genuinely unpinned callers (tests; a
blank-identity phone client, which has no picker at all).

## Related note, left alone

Picking a *different* installed coder tag in the same dropdown (e.g.
`huihui_ai/qwen2.5-coder-abliterate:32b`, also shown with the "Coding
mode —" label prefix) still triggers `is_coding_model()` →
`want_capability_gpu=true`, but `target_cfg` is hardcoded to Josiefied-14B
regardless of which coder tag was actually picked — confirmed live. This
is the existing exclusive-14B-pair policy, not a bug introduced by this
audit. Left alone per the report: whether every installed coder tag should
be honored individually, versus keeping one canonical Coding-mode target,
is a product decision, not something to silently change.

## What shipped

Two regression tests only, in `local_agent/test_capability_routing.py`:
`test_coding_pin_wins_over_logic_text`,
`test_explicit_coder_pin_not_overridden_by_logic_signal`. Full suite: 20
tests, OK. No router/server/UI changes.

## Open decision for the operator

Whether the "any coder tag silently becomes Josiefied-14B" behavior above
is acceptable long-term, or whether the picker should honor whichever
coder tag was actually selected. Not urgent — current behavior is
consistent and tested, just worth a conscious yes/no rather than leaving
it merely undiscussed.
