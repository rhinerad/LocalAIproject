# Upgrade 3 — memory, and the remaining desktop gaps. No internet needed.

Paste everything below the line into Claude Code. Run **after** upgrades 1 and 2.

---

Close the remaining gaps between the local agent and ChatGPT Desktop. **No
downloads.**

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

## Job 1 — memory across conversations

Every chat currently starts blind. Add a persistent facts file the agent reads at
the start of each turn and can append to.

New file `local_agent/memory.py`, storing to `local_agent/memory.json`:

```
remember(fact, category)   append, deduplicated
recall()                   all facts, for the system prompt
forget(index)              move to a `_forgotten` list, never hard-delete
```

Expose `remember` as a tool. **Do not** let it write silently on every turn —
that fills up with noise. It writes when the operator says something like
"remember that…" or states a durable preference.

Inject the facts into the system prompt under `# What I know about this operator`.
Cap it at ~1 KB; if it grows past that, report so it can be pruned deliberately.

Seed it with what is already established: prefers concise answers, is on a phone
hotspot so downloads need approval, runs an RTX 5080 with 16 GB, and is the only
one who can accept a take by ear.

Also seed the **end goal**, from `local_agent/ROADMAP.md`: a Reticulum mesh
linking phone and workstation, so this agent becomes reachable from an Android
client with file access — one assistant available on both devices, with all the
compute staying on the workstation. The agent should know this, because it
changes what "add remote access" means if it is ever asked.

## Job 2 — the rename button

`/api/rename` exists in `server.py`; **nothing in the UI calls it.** Verify:

```powershell
findstr /C:"api/rename" local_agent\static\index.html
```

Add rename to the conversation sidebar — double-click the title, or a pencil on
hover. Match the existing style; no new dependencies.

## Job 3 — harden web search

`web_search` scrapes DuckDuckGo lite. That will rate-limit and its HTML will
change. Make it degrade honestly rather than silently returning nothing:

- distinguish **no internet** from **blocked/rate-limited** from **zero results**,
  and say which
- a short retry with backoff on a transient failure
- if the HTML shape no longer parses, say *that* rather than returning empty —
  a silently empty search is the kind of wrong-measurement failure this project
  has been bitten by repeatedly
- add a `search_docs`-first note in the tool description: local docs before the
  web, for anything about this project

Also make `fetch_url` handle redirects, non-HTML content types, and large pages
without dumping binary into the context.

## Job 4 — the code execution question

ChatGPT Desktop runs Python in a sandbox. **Do not simply add that here.** This
machine holds 124 irreplaceable renders and a live GPU queue, and `tools.py`
being a fixed whitelist is a deliberate safety property.

Instead, implement a **narrow** version and document the reasoning:

- new tool `run_python`, executing a snippet in a **subprocess** with a hard
  timeout (30 s), no network, working directory pinned to a scratch folder under
  `local_agent/scratch/`
- the project tree mounted **read-only in effect**: the snippet may read project
  files but any write outside the scratch folder is refused
- output truncated; a non-zero exit reported plainly
- refuse outright if the snippet text matches obvious destructive patterns
  (`shutil.rmtree`, `os.remove`, `subprocess`, `open(...,'w')` outside scratch)

If you judge this too risky to do safely, **say so and skip it** — write the
reasoning in the CHANGELOG instead. A missing feature is better than a
plausible-looking sandbox that isn't one.

## Job 5 — do not foreclose the mesh

`local_agent/ROADMAP.md` records the end goal: phone and workstation linked over
a Reticulum mesh, with an Android client acting as a thin terminal onto this
agent. Nothing in this upgrade should make that harder.

Two hard rules while you work:

- **Never bind the server to `0.0.0.0`**, not even temporarily to test something
  from another device. The agent executes actions and writes project files; the
  remote path will get its own authenticated transport, not an open HTTP port.
- **Keep transport out of `agent.py`.** `answer()` takes a history list and an
  event callback and knows nothing about HTTP — that seam is where a mesh
  transport will plug in. Do not let request objects, sockets or SSE assumptions
  leak into it.

If a change you are about to make would violate either, choose a different
approach and note why in the CHANGELOG.

## Job 5b — small things that make it feel finished

- keyboard shortcut for a new chat (Ctrl+N when the input is focused)
- a token/character count on the conversation so context pressure is visible
- an "export chat as markdown" action
- make the sidebar show which tier each conversation last used

## Verify

- [ ] a fact remembered in one chat is visible in a brand-new chat
- [ ] `forget` moves rather than deletes
- [ ] memory stays under the cap, and reports when it doesn't
- [ ] rename works from the sidebar and survives a reload
- [ ] `web_search` reports *why* it failed, distinguishing the three cases
- [ ] `fetch_url` on a PDF or binary URL refuses cleanly instead of dumping bytes
- [ ] `run_python` (if implemented) computes `2+2`, times out on a `while True`,
      and **refuses** a snippet that writes outside scratch — or is skipped with
      written reasoning
- [ ] all guard rails from before still refuse
- [ ] `validate_h3_prompt.py` still reports **124/124 valid**

## Do not stop

Stop only when every box is ticked and the `CHANGELOG/` entry is written.
