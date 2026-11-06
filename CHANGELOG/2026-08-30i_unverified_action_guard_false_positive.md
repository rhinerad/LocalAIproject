# 2026-08-30 — agent.py: "unverified action" guard discarded honest future-tense replies

## What changed

`agent.py`'s `_UNVERIFIED_EXECUTION_RE` — the guard that replaces the
model's reply with "No verified local action was performed..." whenever the
model claims to have done something without a tool call backing it up —
matched ordinary **future-tense** statements of intent, not just false
completion claims. Its auxiliary group included `will\s+`, so any reply
containing phrasing like "I will download the model once you approve the
GPU gate" or "I will save this file for you once you tell me the path"
tripped the same guard as an actual false claim ("I downloaded UnityEX and
modified the game files"), silently discarding the honest, correct reply
and replacing it with a generic, confusing non-answer — even though the
model never claimed anything had already happened.

Removed `will\s+` from the auxiliary alternation. `have\s+`/`just\s+`
(genuine completed-action phrasing: "I have downloaded", "I just deleted")
are unchanged, and bare past-tense claims ("I downloaded", "I've installed")
still match, since those genuinely assert something already happened.

## Why

Found during a code-level audit of `agent.py`'s response-construction path,
requested specifically to find and fix response-quality problems. This is
squarely a general-assistant correctness issue, not an Equal Shares one:
"I will do X once you approve" / "I will write the code and then run it" are
extremely ordinary, honest phrasings for an assistant to use when describing
a next step or a plan — not a false claim of already-completed action, which
is what the guard exists to catch. Any reply using this idiomatic
future-tense construction was getting nuked regardless of how helpful or
accurate the rest of the answer was.

## What was verified

Directly tested the regex against 7 cases before and after the change:

| Text | Before | After | Correct |
|---|---|---|---|
| "I will download the model once you approve the GPU gate." | matched (wrong) | no match | after |
| "I will save this file for you once you tell me the path." | matched (wrong) | no match | after |
| "We will create a plan before touching anything." | matched (wrong) | no match | after |
| "I will write the code and then run it to test it." | matched (wrong) | no match | after |
| "I downloaded UnityEX and modified the game files." | matched | matched | both (intended) |
| "I've installed the package." | matched | matched | both (intended) |
| "I just deleted the old logs." | matched | matched | both (intended) |

Ran the existing test through `agent.answer()` directly (mocking
`chat_stream` and `router.decide`, working around this review sandbox's
unrelated inability to unlink `runtime/chat_busy.json` — see below):
`test_unverified_action_claim_is_not_returned_as_completed_work`'s exact
"I downloaded UnityEX and modified the game files." case still produces
"No verified local action was performed" and drops "UnityEX", confirming the
real guard is unaffected for its intended case. The new future-tense case
now returns the actual reply text unchanged, with no
"No verified local action was performed" substitution.

Added `test_future_intent_is_not_treated_as_a_false_completion_claim` to
`test_native_tool_calling.py`, next to the existing guard test, asserting
both directions explicitly.

## What is still unverified / known residual gap

Could not get a clean `python local_agent/test_native_tool_calling.py` run
in this review sandbox: 12 of 28 tests (including both the old and new guard
tests) error on an unrelated `PermissionError` unlinking
`runtime/chat_busy.json` from `agent.py`'s `_chat_busy_guard` `finally`
block — this sandbox's mount cannot delete any file, confirmed separately
across three unrelated test files earlier the same day, not caused by this
change. Verified the actual behavior directly instead, bypassing the
unittest harness, by patching `router.set_chat_busy` to a no-op and calling
`agent.answer()` the same way the tests do (see evidence above). Needs a
real run on the Windows workstation, where that file can actually be
deleted, to get the official test-suite count.

Not attempted: a broader sweep of the other regex-based guards in
`agent.py` (`_ACCESS_BYPASS_RE`, `_START_CURRENT_RENDER_RE`,
`_STOP_COMFYUI_RE`, `_SONIC_PI_*`) for the same class of over-matching. This
fix addressed the one confirmed, high-frequency false positive found so
far; a similar review of the others is a reasonable next step, not done
here to keep this change narrow and verifiable.
