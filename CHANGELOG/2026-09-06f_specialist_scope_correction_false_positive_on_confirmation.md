# 2026-09-06f — Scope-correction false positive on a plain confirmation reply

Date: 2026-09-06. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-06`: **2026-09-06f**.

Claude session (separate from the Grok work in `2026-09-06e` and earlier).
Live bug reported by the operator on chat `local_agent/chats/046e1608341e418d.json`:
a multi-clip (12 clips, 24 stills) VHS/liminal-space image-generation request
that had nothing to do with the earlier `Bulma`/`Android-18` thread. Turn 1
correctly planned all the images with `plan_story_image`. Turn 2 — the
operator's plain "yes proceed, and also bear in mind I'll give you more
prompts..." — got the generic refusal `"I could not produce a grounded
answer to the current request without mixing in unrelated project context.
No local action was performed. Please restate the immediate task in one
sentence."` even though this was a direct, on-topic continuation of the turn
immediately before it.

## Root cause

`local_agent/agent.py`'s scope-correction guard (`_irrelevant_specialist_reply`,
used by the `_ACTION_REQUEST_RE`/specialist-scope retry at the bottom of the
hop loop) exists to catch a **different**, real failure mode: a model
hallucinating stale ComfyUI/H3/render content into an unrelated new topic
(covered by `test_stale_h3_render_reply_is_discarded_on_unrelated_turn`).
It works by requiring the **current** operator turn's own text to explicitly
re-open specialist scope (`_SPECIALIST_CONTEXT_REQUEST_RE`); if it doesn't,
and the model's reply mentions render/image/tool-name keywords
(`_SPECIALIST_CONTEXT_LEAK_RE`), the reply is discarded as a "leak" and
retried once.

Two compounding problems:

1. `_SPECIALIST_CONTEXT_REQUEST_RE` only matched the **singular** `image`/
   `picture` and had no `photo` at all. The operator's confirmation said
   "more **images**" (plural) — no match, so the turn was treated as not
   re-opening scope even though it plainly was.
2. Even with the plural fixed, a large class of ordinary continuation
   replies — "yes", "go ahead", "sounds good", "proceed" — will *never*
   restate topic keywords, by design; that's what makes them a natural
   short reply to an assistant's own offer. The guard had no way to
   recognize "this is a direct reply to my own pending offer, not a fresh
   unrelated statement."

## Fix

`local_agent/agent.py`:

1. Broadened `_SPECIALIST_CONTEXT_REQUEST_RE` to match plurals
   (`images?`, `pictures?`, `clips?`, `prompt sets?`, `*generations?`) and
   added `photos?`.
2. New `_SPECIALIST_CONTINUATION_OFFER_RE` + `_pending_specialist_continuation(history)`:
   true only when the **immediately preceding assistant turn** both opened
   specialist scope (matches the request regex) **and** contains an active,
   un-declined invitation to continue ("would you like", "do you want",
   "shall I", "I can start", "ready to render", "plans/images are ready",
   etc.). `_irrelevant_specialist_reply` now takes an optional `history` and
   skips the leak check when this is true.

Deliberately **not** a blanket "did specialist scope ever open earlier in
this conversation" check — that broader version was tried first and breaks
`test_stale_h3_render_reply_is_discarded_on_unrelated_turn`: that test's
prior assistant turn also mentions render/H3, but as an explicit **decline**
("No render was started..."), and the correct behavior is for a later
hallucinated render reply to still be caught and discarded. The distinguishing
signal is whether the immediately-prior assistant turn left an *active,
undeclined offer* on the table, not merely whether the topic was ever
mentioned.

## Tests

```
python -m unittest local_agent.test_native_tool_calling -v
python -m unittest local_agent.test_native_tool_calling local_agent.test_capability_routing local_agent.test_router_switching local_agent.test_general_assistant
```

99/99 (`test_native_tool_calling` alone, including the existing
`test_stale_h3_render_reply_is_discarded_on_unrelated_turn` and
`test_stale_h3_render_tool_is_blocked_on_unrelated_turn` regression cases,
unaffected) plus a new
`test_confirmation_reply_to_a_pending_image_offer_is_not_discarded`
reproducing the exact reported shape. Combined run: 190/192 — the 2
failures are `test_router_switching`'s pre-existing, unrelated coding-model
router failures already noted in `2026-09-05ed`/`2026-09-05ee` (confirmed to
fail identically in isolation; this change never touches `router.py`).

## Not changed

- `_SPECIALIST_CONTEXT_LEAK_RE` (the actual leak-detection keyword list).
- Any capability routing, tool schema, or GPU/model selection logic.
- No GPU work performed. No `outputs/equal_shares/**` touched.

## Files

- `local_agent/agent.py`
- `local_agent/test_native_tool_calling.py`
- `CHANGELOG/2026-09-06f_specialist_scope_correction_false_positive_on_confirmation.md`
- `TODO.md`
