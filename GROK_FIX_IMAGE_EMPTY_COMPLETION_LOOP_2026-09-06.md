# Grok: finish the image-intent empty-completion fix — paste everything below into Grok

---

You are picking up a live bug-fix loop on **`local_agent/`** (the general
desktop assistant, not Equal Shares — read the SCOPE NOTICE at the top of
`CLAUDE.md` if you need the distinction). Repo root:

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

Claude has been doing this fix loop from a sandbox with no way to restart the
local agent's server process or drive its browser GUI, so every fix has only
been unit-tested, never actually confirmed live. That is your job: **restart,
resend, watch the real telemetry, and keep fixing until it actually works —
not until the tests pass.**

## DO NOT ASK THE OPERATOR QUESTIONS

Work the loop below through to a real result — either "it works, verified
live" or "here is the specific hard blocker I hit and why I can't get past it
myself." Do not stop to report interim progress or ask permission for a
routine restart, edit, test run, or changelog entry.

---

## Background — read in this order

1. `CLAUDE.md` SCOPE NOTICE (top of file) — `local_agent/` rules, thermal/GPU
   safety rules that still bind even though this task never touches GPU
   render.
2. `CHANGELOG/2026-09-05ec_image_intent_and_degenerate_guard.md`
3. `CHANGELOG/2026-09-05ed_unclosed_think_block_telemetry.md`
4. `CHANGELOG/2026-09-05ee_whitespace_prefix_swallow_fix.md`

All three are sibling fixes to the **same live bug**, found today by Claude
running the same exact operator prompt repeatedly through the GUI:

- `ec`: prompt was being misclassified as `CAP_LOGIC`/demoted off the 14B
  model. Fixed — routing is now confirmed correct (`capability=image`, stays
  on GPU 14B).
- `ed`: even with routing fixed, the 14B model was opening a `<think>` tag
  inside `content` and never closing it before running out of turn, so the
  whole reply vanished with zero telemetry. Fixed the telemetry blindness.
- `ee`: a live retry after `ed` hit a **third** shape — the model emitted 275
  tokens of pure whitespace, which `_VisibleTextFilter`'s `"prefix"` state
  swallowed forever (an empty string trivially "starts with" `<think>` in
  Python, so the hold condition never resolved). Fixed.

**Every one of `ec`/`ed`/`ee` has only ever been confirmed by
`python -m unittest ...`.** Live retries after each fix kept showing the
exact same dead result — but Claude eventually noticed `eval_count=275`
identically on *every single retry*, across all three "different" bugs, and
the file mtimes of `ollama_client.py`/`agent.py` were newer than the retries
that supposedly tested them. **The local agent's `server.py` process almost
certainly never got restarted between fixes**, so most of those "still
broken" live retries were silently re-running old code. This is the first
thing to fix before drawing any more conclusions about the model itself.

## The exact reproduction

Chat file `local_agent/chats/b2542251e7814926.json` has the operator's exact
prompt and both reference images already uploaded and attached. Do not
retype the prompt or ask the operator for the images — they're already on
disk:

```
local_agent/uploads/06d4015284cda791_f67cefe1d5bd41598e12aa1aaab7a1f1-882c88a35e4c8191.png   (Bulma sheet)
local_agent/uploads/6e3f395eaaeef31f_08eb12cec03a40b4a1efd3c2a3e1f21f-d718438ed9c17097.png   (Android 18 sheet)
```

The full prompt text is message 0 of that chat file (14 beats, PRE01–PRE14C,
START+LAST stills, ~30 output images, "still frames only, photoreal
live-action, two adult women from my reference sheets" — fictional,
non-graphic, both women are canonical adult characters). Model pinned:
`huihui_ai/qwen3-abliterated:14b`.

`local_agent/knowledge/traces.db` (SQLite) has full span/telemetry history
for every attempt today, keyed by `conversation_id`. Query it directly rather
than guessing from the chat transcript alone — the chat only stores the
final stored reply, the trace has the real per-hop
`visible_chars`/`thinking_chars`/`unclosed_think_chars`/`tool_call_count`/
`eval_count` numbers.

## Job 1 — restart, then resend, then look

1. Stop and relaunch the local agent so today's edits are actually loaded:
   `local_agent/START_LOCAL_AGENT_GUI.ps1` (it detects and replaces a stale
   instance on port 8760 itself — see `Stop-StaleAgent`/`Test-AgentReady` in
   that script if it needs help). Confirm `GET http://127.0.0.1:8760/api/status`
   reports the current `app_revision` after restart.
2. Resend the exact same prompt+images (reuse the existing chat
   `b2542251e7814926` — "Retry" if the GUI has that, or send the identical
   text with the same two attachment paths as a new turn) through the actual
   GUI, exactly as the operator does it. Do not simulate this via a
   hand-rolled HTTP call unless you've confirmed it reproduces the same
   `server.py` code path (`POST` handler in `local_agent/server.py`, the one
   that inlines attachments per `att.get("kind") == "image"` — read that
   function first, ~line 1100).
3. Immediately after, query `traces.db` for the new `conversation_id` (or the
   newest `agent.answer` span by `start_ts`) and inspect every `reason` /
   `hop` span's `attributes`. Compare `eval_count` (`tokens_out`) to the
   `275` seen on every previous attempt — if it's still exactly 275, that is
   a real clue (fixed `num_predict`? a genuinely deterministic degenerate
   completion given identical inputs/options — check `options` sent in
   `router.Decision.options()` for this route, and whether `temperature`/
   `seed` are pinned) worth chasing directly, not just another swallow-filter
   symptom to patch around.

## Job 2 — if it's still empty, diagnose the *real* new shape

Do not assume it's a fourth flavor of the same `_VisibleTextFilter` bug
without checking. Look at the actual `visible_chars`/`thinking_chars`/
`unclosed_think_chars`/`tool_call_count` combination in the fresh trace:

| Shape in the trace | What it means | Where to look |
|---|---|---|
| `tool_call_count > 0` | **It worked.** Stop here, verify the chat shows real `plan_story_image`/`render_story_image` calls, write the changelog closing this out. | — |
| `unclosed_think_chars > 0` | `ed`'s case is firing correctly. Something upstream is still not converting that into a useful retry/response — read `agent.py`'s `_UNCLOSED_THINK_EMPTY_COMPLETION_REPLY` path. | `agent.py` ~2149-2193 |
| all four still 0, `eval_count` matches `ee`'s repro shape | `ee` isn't loaded yet (didn't actually restart) or another swallow path exists in `_VisibleTextFilter`/`chat_stream` you haven't found yet — reproduce offline first with a script that feeds the filter, don't burn GPU time guessing | `local_agent/ollama_client.py` `_VisibleTextFilter`, `chat_stream` |
| `eval_count` differs from 275 for the first time | The model's actual behavior changed — re-read the raw content this time before assuming another filter bug exists at all | add temporary raw-content logging in `chat_stream` if telemetry alone isn't enough to tell |

For any new fix: reproduce offline with a small script against
`local_agent/ollama_client.py` first (see `ec`/`ed`/`ee` changelogs for the
exact reproduction style used), then patch, then add unit tests in
`local_agent/test_ollama_chat_telemetry.py` following the existing style,
then restart the server and retry live again. **Do not consider a fix done
until the live retry after restarting shows the improvement in `traces.db`
— unit tests passing is necessary but is exactly what already gave a false
sense of "fixed" three times today.**

## Job 3 — if the model genuinely can't do this request at any size

If you get a clean, restart-confirmed live trace showing `visible_chars`,
`thinking_chars`, and `unclosed_think_chars` all genuinely 0 with no
swallow-filter bug left to find (i.e., the model is really producing nothing
useful, not being silently eaten by the harness), test the scope hypothesis
directly: resend a trimmed version of the same prompt (e.g. just `PRE01`,
one beat, two stills) with the same two reference images and the same
`capability=image` routing. If a 2-still version works and the full 14-beat/
~30-still version doesn't, that's real evidence this specific request is too
large for one turn on this model — say so plainly in your final report and
changelog, and don't keep patching the harness to force a 30-image single
turn to work if the actual ceiling is model capacity, not code.

## Stop conditions / guardrails

- Never touch `outputs/equal_shares/**`, GPU render pipelines, model
  weights/predictors, or `router.py` unless a fix genuinely requires it (none
  of `ec`/`ed`/`ee` did).
- Every code change gets a `CHANGELOG/<id>_<description>.md` via
  `python scripts/next_changelog_id.py --date 2026-09-06` (or the correct
  current date), naming `ec`/`ed`/`ee` as siblings, with real test commands
  and pass counts, plus the live trace evidence (paste the relevant
  `traces.db` rows, not just "tests pass").
- Update `TODO.md` and `GROK_STATUS.md` the same way every other entry in
  this tree already does, so Claude or the operator can pick this back up
  cleanly if you get interrupted.
- If you hit a genuine hard blocker (something needs an operator decision,
  credential, or asset you truly cannot find or substitute), stop and say
  exactly what's blocking you and what you already ruled out — don't just
  report "still doesn't work" the way the last three live retries did
  without the restart-timing diagnosis attached.

Finish with: whether it actually works now (live trace showing real tool
calls, not just green tests), the exact evidence, and if it doesn't work,
the most specific true statement you can make about why — including "the
request is too large for this model" if that's what the trimmed-prompt test
actually shows.
