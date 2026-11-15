# Finish the local agent — paste everything below the line into Claude Code

---

Your job is to take `local_agent/` from "built and unit-tested" to "the operator
opens it and uses it." It has **never run against a real Ollama or a real GPU**.
That is the entire gap. Close it.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

## Read first

1. `local_agent/README.md` — what it is, how it routes, what it deliberately cannot do
2. `CHANGELOG/2026-08-18e_local_agent_gui.md` — how it was built and what is unverified
3. `docs/GOLDEN_REFERENCE/PROVEN_FACTS.md` — the project facts the agent answers from
4. `CLAUDE.md` — binding standing rules

---

# DO NOT STOP UNTIL IT WORKS

**Work straight through. Do not stop to report, ask permission, or check in.**
Diagnose, fix, re-test, continue. A failing test is a task, not a stopping point.

You may stop for exactly three things:

1. **No Ollama model is installed at all.** Pulling one is a multi-GB download and
   the operator is on a phone hotspot — state the exact size and ask. Everything
   else, decide yourself.
2. Ollama is not installed on the machine.
3. You have met every acceptance criterion below.

Nothing else qualifies. Not a crash, not a slow model, not a missing file, not a
PowerShell quirk, not a model that ignores the action protocol. Fix it.

---

## Job 1 — reality check

```powershell
python local_agent\router.py
```

This prints what it detects and why. Then:

```powershell
.\local_agent\START_LOCAL_AGENT_GUI.ps1
```

Expect breakage. The launcher has never been executed. Likely suspects: the
Ollama path, PowerShell environment inheritance for the two servers, port
collisions, `python` not on PATH under PowerShell.

**Fix whatever breaks.** Record each fix in the CHANGELOG entry you will write.

## Job 2 — make the routing real

This is the part with no real-world evidence behind it.

- `nvidia-smi` parsing has **never seen real output**. Run it, compare with what
  `router.gpu_memory()` returns, fix the parsing. Multi-GPU output, locale
  differences, and a missing `--query-compute-apps` are all plausible.
- Confirm the GPU tier actually loads on the card: ask the agent something, then
  check `nvidia-smi` shows VRAM in use by Ollama.
- **Then prove it yields.** With the agent idle on GPU, start something that
  claims the card and confirm the next reply comes back on CPU *and* that the
  GPU model was evicted. The cheapest honest test:

  ```powershell
  python work\render_voice_auditions.py --dry-run    # claims nothing, safe
  ```

  That will not trip the busy signals, so also test by hand: write a live PID
  into `outputs\equal_shares\runtime\render_queue_owner.json`, confirm the agent
  moves to CPU, then restore the file exactly as it was.

- Verify the three busy signals independently. Any one must be enough.

If the GPU tier cannot be made to work, **say so plainly and leave it on CPU** —
a working CPU-only agent beats a broken dual-tier one.

## Job 3 — make it behave like an assistant

Talk to it. Real questions, in the GUI:

- "Where are we and what runs next?"
- "What's blocking the 124-clip pass?"
- "Show me clip 27E"
- "What's the duration ladder for 00B?"
- "Check the config for drift"
- "Which characters need a voice master?"
- Something unrelated to the project, to confirm it is a general assistant too

**What must be true:**

- it calls an action rather than inventing counts, paths, or settings
- the `TOOL:` line never appears as prose — it renders as an action card
- answers are plain English, no restating the question
- it never claims to have heard audio or seen an image
- it never claims something is "verified" on the strength of documents agreeing

If the model leaks the protocol, loops, or invents facts: tune
`agent.py` `CONVERSATION_RULES` and the brief in `build_knowledge_pack.py`, try a
different model, adjust temperature. **Iterate until it behaves.** If a model is
simply too weak, try a smaller/newer one that is already installed and record
which one works.

## Job 4 — the desktop features, exercised by hand

Every one of these, in the browser:

- send a message in a **new** chat (this used to crash on `id: null`)
- reload the page — the conversation is still there
- new chat, switch between chats, rename, delete
- **Stop** mid-generation — it must actually halt, not just hide output
- **Regenerate** and **Copy**
- attach a text file and confirm the agent reads its contents
- the tier indicator changes when the GPU state changes
- force CPU, force GPU, and confirm forcing GPU is refused while a render runs

## Job 5 — prove the safety net still holds

```powershell
python local_agent\validate_h3_prompt.py --dir outputs\equal_shares\prompts_native_r2v
python local_agent\tools.py
python work\classify_voice_requirements.py --check
```

Expect **124/124 valid**, all nine actions listed, and 18 speakers = 10 recurring
+ 8 one-off. If any of that changed, something upstream broke — find it.

Then confirm the guard rails still refuse: an unknown action, a clip id of
`../etc`, a doc name of `/etc/passwd`, a build action of `rm -rf /`.

## Job 6 — a real prompt draft, validated

```powershell
python -c "import sys; sys.path.insert(0,'local_agent'); import agent, json; print(json.dumps(agent.draft_prompt('00A','keep it exactly as scripted'), indent=2)[:2000])"
```

The draft will probably fail validation — a small model rarely gets all six
sections and the tag numbering right first time. **That is fine and expected.**
What matters is that the failure is *caught and reported*, not silently passed
through. Confirm `safe_to_use` is accurate either way.

---

## Acceptance — you are done when ALL of these are true

- [ ] `START_LOCAL_AGENT_GUI.ps1` runs clean from a cold start and opens the app
- [ ] `router.py` reports real GPU state from real `nvidia-smi` output
- [ ] the agent answers on the **GPU** tier while the card is idle
- [ ] claiming the GPU moves the next reply to **CPU**, and the GPU model is evicted
- [ ] all three busy signals verified independently
- [ ] six project questions answered correctly, each using an action not memory
- [ ] one general question answered sensibly
- [ ] new chat, persistence across reload, rename, delete, stop, regenerate, copy,
      attachment — all working
- [ ] 124/124 prompts still valid; all guard rails still refuse
- [ ] `draft_prompt` returns an accurate `safe_to_use`
- [ ] `local_agent/README.md` updated so every "not yet verified" line is either
      resolved or restated as a real, current limitation
- [ ] a `CHANGELOG/` entry written with what changed, why, the evidence, what you
      verified, and what remains unverified

## While you work

- **Never start a render.** The agent proposes; the operator approves. The
  124-clip pass is blocked until voices are chosen.
- **Never delete** a raw generation, an approved reference, a manifest, an audit
  record, or source audio. Versioned siblings or a labelled quarantine folder.
- **No downloads** without stating the size first.
- **Do not weaken the safeguards to make a test pass.** The CPU thread cap stays
  at 4. The GPU-busy check keeps failing safe. `tools.py` stays a whitelist. If a
  safeguard is genuinely wrong, fix it properly and write down why.
- **Say what you measured.** This project has been misled seven times by a
  checker measuring the wrong thing. When you assert something works, give the
  number or the command output.

Report about once a minute: what you are testing, what broke, what you changed,
what is next. No log dumps, no questions.

Begin with Job 1 and keep going until the acceptance list is complete.
