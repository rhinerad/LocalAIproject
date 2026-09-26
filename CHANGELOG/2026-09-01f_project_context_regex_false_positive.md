# 2026-09-01 — Root-caused and fixed the repeat "H3/ComfyUI leaks into unrelated chats" bug

## Scope

Operator has reported multiple times, across sessions, that the local-agent
chat keeps bringing up MiniMax H3, ComfyUI rendering, or Equal Shares content
in conversations that have nothing to do with any of that, and that despite
being told it was fixed before, it kept happening. This entry documents the
actual root cause found by reading the code rather than assuming a prior fix
attempt worked, and a real fix with regression tests.

## Root cause

`local_agent/agent.py`'s `PROJECT_CONTEXT_RE` — the regex that decides
whether the current chat turn should load the large "Equal Shares specialist
reference" handbook into the model's context — contained this alternative:

```
\b[0-9]{2}[A-Z](?:[0-9])?\b
```

This matches **any** bare two-digit-plus-letter token: a temperature ("72F"),
a flight gate or apartment number ("24B"), an exam grade, a hotel room
number, and so on — with no requirement that the word "clip," "shot," or
anything else project-related appear anywhere nearby. Once matched, the
model's system prompt grew by several hundred lines of strongly-worded
Equal Shares/H3 render-pipeline rules. Small local models (this project uses
CPU/GPU Ollama models, not a frontier model) are not reliable at recognizing
that an injected specialist handbook doesn't apply to the current request —
they tend to run with whatever specialized content was just placed in front
of them. That combination is exactly the reported symptom: bringing up
renders, H3, or ComfyUI pipeline language in conversations that never
mentioned any of it.

Notably, the comment directly above this regex already described the
intended fix: *"a generic clip/shot must never activate the film handbook...
Only an unmistakable Equal Shares marker may do that."* The keyword-gated
alternative (`\b(?:clip|shot)\s*[0-9]{2}[A-Z]...\b`) existed right next to
the bare, ungated one — meaning a previous attempt to fix this exact bug was
made and then silently undone or left incomplete, with the comment claiming
success while the code still contained the unguarded pattern. This is
presumably why the operator's repeated reports that "this was supposed to be
fixed already" kept recurring: it genuinely was fixed once, then the fix
didn't stick or wasn't the whole fix.

## Why the bare form couldn't just be deleted

`test_general_assistant.py` already had (and still has) a passing test
asserting that `"compare the ladders for 00B and 00A"` — a bare clip-ID
mention with no "clip"/"shot" word — activates project context. This
matches how this project's own documents write clip IDs (e.g. `CLAUDE.md`:
`` `04C`: Kent has already declined... ``), so simply removing the bare
pattern would have broken a real, intended capability.

## Fix

Replaced the single unconditional-OR regex with a two-signal check in a new
`_message_invokes_project()` helper:

- An unmistakable marker (`Equal Shares`, `MiniMax H3`, a `clip`/`shot`-
  prefixed ID, `voice lock`, `duration ladder`, a project file path, etc.)
  still activates project context on its own, unchanged.
- A **bare** two-digit-letter token now only counts when the **same message**
  also contains an independent project-flavored word (`ladder(s)`, `clip(s)`,
  `shot(s)`, `scene(s)`, `render...`, `voice(s)`, `soundtrack(s)`, `audio`,
  `narrator`, `duration`, `take(s)`, `dialogue`, `prompt(s)`, `frame(s)`).

A temperature or gate number alone never has one of those companion words;
an operator actually asking about a clip almost always does (as the existing
"ladders for 00B and 00A" test already demonstrates — it contains "ladders").
Both `needs_project_context`'s immediate-message check and its short-follow-up
recent-context check now go through this same helper.

`APP_REVISION` bumped to `2026-09-01-project-scope-falsepos-r72` in
`server.py` and `START_LOCAL_AGENT_GUI.ps1` so the launcher replaces any
already-running stale process.

## Verification

- `python local_agent/test_general_assistant.py`: all existing checks still
  pass (including the legitimate bare-clip-ID case), plus five new checks
  confirming ordinary temperature/gate/room/grade mentions no longer trigger
  `needs_project_context` or load the film handbook into `system_prompt()`.
  Exit code 0.
- `python -m pytest local_agent/test_launcher_revision.py`: passes, confirming
  `APP_REVISION`/`$ExpectedAgentRevision` are back in lockstep.
- Not yet verified against a live model turn on the operator's machine (this
  session has no way to run the actual Ollama-backed chat loop end to end) —
  a live audit prompt for that is provided separately for the operator to run
  with Claude Code on the workstation.

## What this does not fix

This addresses one confirmed, mechanically-verifiable root cause of
project-context leakage. It does not by itself prove the agent "calls tools
correctly" or "doesn't ask the operator to do the work" in general — those
are separate, less mechanically pinned-down complaints that need live
behavioral testing against the running agent, not just a regex fix. See the
audit prompt provided to the operator for that follow-up.
