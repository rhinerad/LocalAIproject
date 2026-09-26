# 2026-09-01 — agent.py could not import at all: smart quotes as string delimiters

## Scope

Routine repo/handoff sync check before continuing other work (per standing
practice this session). Found that the version of `local_agent/agent.py`
currently on disk — the one `CHANGELOG/2026-09-01_stop_assuming_comfyui_h3.md`'s
"addendum" section (the specialist-scope-guard pass, `APP_REVISION`
`...-specialist-scope-guard-r74`) claims to have verified with
`python local_agent\test_native_tool_calling.py — 57 tests, 0 failures` —
**cannot be imported at all.**

## What was wrong

Lines 1239–1245 of `agent.py` (the new scope-boundary system message added by
that same pass) used curly/"smart" quotes (`"` U+201C / `"` U+201D) as the
actual Python string delimiters:

```python
msgs.insert(1, {“role”: “system”, “content”:
             “Scope boundary for this turn: ...
```

Python only accepts straight `'`/`"` as string delimiters — curly quotes here
are not string syntax, they're just unrecognized characters, so this is a
hard `SyntaxError` at import time, not a style nit. `import agent` fails
before any test in that module's suite could possibly run.

## Why this matters beyond one file

This means the "57 tests, 0 failures" verification claimed in the
specialist-scope-guard changelog entry could not have been run against the
code as currently saved on disk — either the verification was run before this
exact edit was written to the file, or against a different copy, or the
claim is simply wrong. Either way, the file was left in a state where the
entire local agent cannot start at all (`server.py` imports `agent.py`), which
is a total-outage-level regression, not a cosmetic one.

## Fix

Replaced the curly-quote-delimited dict literal with straight double quotes
in `agent.py`. No wording or logic change — same message content, valid
Python syntax. Other curly characters elsewhere in the file (lines 138, 1183,
1247) are fine and untouched: those are curly apostrophes/quotes used as
*content inside* an already straight-quote-delimited string, which Python
has no issue with — only lines 1239–1245 used them as delimiters.

`APP_REVISION` bumped to `2026-09-01-agent-syntax-crash-fix-r75` in
`server.py` and `START_LOCAL_AGENT_GUI.ps1`, since the running process (if
somehow still running despite this) needs to pick up a corrected file, and
any operator who tried to restart the agent after the specialist-scope-guard
pass would have hit an immediate crash on startup.

## Verification

- `python -m py_compile local_agent/agent.py` — succeeds (previously raised
  `SyntaxError: invalid character '“' (U+201C)` at line 1239).
- `python local_agent/test_general_assistant.py` — all 11 checks pass,
  including this session's earlier `_message_invokes_project` false-positive
  regression tests, confirming that fix also survived the specialist-scope-guard
  pass intact.
- `python local_agent/test_native_tool_calling.py` — 57 tests, 0 failures,
  actually run this time (including the two new
  `test_stale_h3_render_reply_is_discarded_on_unrelated_turn` /
  `test_stale_h3_render_tool_is_blocked_on_unrelated_turn` tests from the
  specialist-scope-guard pass).
- `python -m pytest local_agent/test_launcher_revision.py` — passes,
  `APP_REVISION`/`$ExpectedAgentRevision` back in lockstep.

## Note on the broader pattern

This is the second time this session a changelog entry's own claimed
verification didn't match the actual state of the file it was verifying
(the first being the stale `APP_REVISION` after the image-profile edit). Both
were caught by actually re-running the code rather than trusting the written
claim. Given the operator's standing complaint about the agent "not
hallucinating and calling tools correctly," this is worth normalizing across
concurrent sessions: a changelog entry claiming N tests passed should be
treated as provisional until independently re-run, not as settled fact.
