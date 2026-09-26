# Upgrade 23 — prove the phone scheduler live, and stop one missing package killing the agent

Paste everything below the line into Claude Code. **No downloads.**

---

Two jobs. The first finishes a fix that is code-complete but has never sent a real
message. The second removes a fragility found while testing it.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

Read `CHANGELOG/2026-08-27_phone_scheduled_messages.md` first — it explains what
was wrong and what was built.

---

# Job 1 — prove the scheduler actually reaches the phone

## Background

The operator asked the agent from their phone to *"send a message every 30 seconds
for the next 20 or 30 minutes starting with 0 and counting up."* It claimed
success and sent nothing, then mentioned permissions for no reason.

Cause: `phone_scheduler.py` existed but was **orphaned at both ends** — no tool
created schedules, and nothing called `dispatch_due`. Both connections now exist
(`schedule_phone_messages` / `list_phone_schedules` / `cancel_phone_schedule` in
`tools.py`; `_scheduled_send` + `drain_scheduled` in `lxmf_agent.py`), and
`local_agent/test_phone_scheduler.py` passes 10/10.

**But every one of those tests uses an injected send callback. No message has
ever gone to the real phone.** That is what this job settles.

## What to do

1. Start the bridge and confirm the paired phone is active.
2. From the **phone**, ask in plain language: *"message me every 15 seconds five
   times, counting up from 0."* Use 15 s × 5 so the test finishes in about a
   minute.
3. Watch and record:
   - does the model call `schedule_phone_messages`, or does it narrate success
     again? **This is the real test.** If it narrates, the wiring is fine and the
     *wording* is the fault — fix the tool description and `CONVERSATION_RULES`
     until it reliably picks the tool, and say so plainly.
   - do **five** messages actually arrive on the phone?
   - are they `0, 1, 2, 3, 4` at roughly 15-second spacing?
   - does a **sixth** never arrive?
4. From the phone, run the same thing again and **cancel it midway** with
   `list_phone_schedules` then `cancel_phone_schedule`. Confirm delivery stops.
5. Restart the bridge with an active schedule pending. Confirm it resumes from
   durable state rather than starting over or double-sending.

## Report honestly

State the measured interval, the counter values received, and whether the model
chose the tool unprompted. If any message was lost, say so — LXMF queueing is not
delivery, and this project does not report queued as sent.

## Known limits — verify, do not "fix" without asking

- interval 10–3600 s, count 1–120, span within 24 h
- a schedule needs the bridge running; there is **no catch-up** for intervals
  missed while it was stopped. `dispatch_due` sends one message per job per tick,
  so an outage skips intervals rather than producing a burst. Confirm that is
  what happens; do not add replay without the operator asking.

---

# Job 2 — one missing package must not take the whole agent down

## The finding

While testing, importing `lxmf_agent` failed entirely because `chromadb` was
absent. The chain is `lxmf_agent → agent → exemplar_embeddings → chromadb`, and
that import is unguarded at module top level.

Audited across `local_agent/*.py`, there are **8 unguarded third-party imports at
module top level**:

| file | package | in the chain? |
|---|---|---|
| `exemplar_embeddings.py` | `chromadb` (2 lines) | **yes** — `agent.py`, `server.py` |
| `feedback_manager.py` | `cryptography` | **yes** — `server.py` |
| `media_tools.py` | `PIL` | not currently imported by the chain |
| `probe_rnode.py` | `serial` (2 lines) | standalone script |
| `probe_rnode_ble.py` | `bleak`, `winrt` | standalone script |

The first two are the dangerous ones: a broken or uninstalled optional package
means the **chat app will not start at all**, with a traceback that names a
vector database rather than the real problem.

This matters more than it looks. Feedback exemplars and encrypted feedback keys
are enhancements. Chat is the product. An enhancement must never be able to take
the product offline.

## What to do

Apply the pattern this project already uses for sensory tools: **degrade with a
specific reason, never crash.**

- Guard the import. On `ImportError`, set a module-level flag and a reason string.
- Every public function in that module returns a clear, actionable message when
  unavailable — the package name and how to install it — rather than raising.
- `capabilities.py` already exists for exactly this. Register the affected
  features there so `capabilities` reports them accurately, alongside vision,
  transcription and speaker comparison.
- **Do not** silently no-op. A retrieval call that quietly returns nothing is the
  wrong-measurement failure this project has been bitten by repeatedly. It must
  say *why* it returned nothing.

Leave the two `probe_rnode*` scripts alone unless it is trivial — they are
standalone diagnostics, not part of the app, and a hard import there is honest.

## Then prove it

The point is not that the code changed. The point is that the app survives.

- With the packages present: everything behaves exactly as it does now.
- **Simulate absence** — block the import in a test (`sys.modules` stub raising
  `ImportError`) and confirm:
  - `agent` and `server` still import
  - the GUI still starts and answers a normal question
  - `capabilities` reports the missing component **by name**
  - the affected tool returns the reason, not a traceback and not silence

Add this as a real test file so the regression cannot come back.

---

## Verify — both jobs

- [ ] the phone received the messages, with the measured interval and counters
      recorded
- [ ] the model chose `schedule_phone_messages` unprompted, or the wording was
      fixed until it did
- [ ] cancel works from the phone; a restart resumes without double-sending
- [ ] `python -m unittest test_phone_scheduler` still 10/10
- [ ] `agent` and `server` import with `chromadb` and `cryptography` stubbed to
      raise
- [ ] `capabilities` names any missing component
- [ ] `python local_agent\validate_h3_prompt.py --dir outputs\equal_shares\prompts_native_r2v`
      still **124/124**
- [ ] `tools.schemas()` still returns one schema per registered tool

## Rules

- No downloads. No renders. No widening of any permission — the scheduler is
  phone-only and source-bound, and the identity stays injected by the dispatch
  seam. It must remain impossible for the model to name a recipient.
- Never delete a raw generation, reference, manifest, audit record, or source
  audio.
- Finish with a `CHANGELOG/` entry carrying the measured live result — interval,
  counters received, whether the model picked the tool on its own — and add its
  row to `CHANGELOG/README.md`. A claim without a number is not evidence here.

## Do not stop

Work straight through. The one legitimate stop is the phone being unavailable to
test against — in which case do Job 2 fully, and say plainly that Job 1 remains
unverified.
