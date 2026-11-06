# 2026-08-18 — an offline CPU agent with a chat GUI

Operator request: *"I need my cpu local agent to be able to take prompts that are
made from ollama... so im not reliant on claude or chatgpt when we have no usage
or internet"*, then *"essentially i want a program gui that i can use just like
chatgpt desktop but that runs completely locally."*

## What was built

`local_agent/` — a browser chat window served from `127.0.0.1:8760`, talking to a
CPU-only Ollama, with this project's tooling wired in as callable actions.

| File | Purpose |
|---|---|
| `START_LOCAL_AGENT_GUI.ps1` | launcher: CPU-only Ollama on :11435, rebuild knowledge, open GUI |
| `server.py` | stdlib `http.server` + SSE streaming |
| `static/index.html` | the entire interface, one file, no CDN |
| `agent.py` | message → model → tool → answer; also a terminal chat |
| `tools.py` | whitelist of 9 allowed actions in three tiers |
| `ollama_client.py` | `num_gpu: 0`, `num_thread: 4`, port 11435 |
| `build_knowledge_pack.py` | compiles the brief from live state |
| `validate_h3_prompt.py` | the safety net |
| `Modelfile.equal-shares` | local model definition |

## Two constraints that shaped every decision

**No downloads.** The operator is on a phone hotspot. So no Electron, Tauri,
FastAPI, Flask, npm, `requests`, or the `ollama` package — standard library only.
The client never pulls a model; a missing one is reported with its size.

**No GPU.** A *second* Ollama on port 11435 started with `CUDA_VISIBLE_DEVICES=-1`,
deliberately not the default 11434, which may have GPU access. Four of sixteen
threads, matching the existing cap in `work/run_open_interpreter_handoff.py` and
the thermal rule in `CLAUDE.md`.

## The architecture, and why it is not "let the model do it"

A 14B model on four CPU threads cannot write a correct 4,600-character prompt with
every reference tag numbered right. It can reliably pick which script to run.

```
you -> model -> picks a TOOL -> deterministic Python does the work
                            -> result -> model explains it
```

The model **chooses**; the project's own code **produces**. Prompts still come
from `build_native_r2v_prompts.py`, classification from
`classify_voice_requirements.py`, rungs from `duration_ladder.py`. The one place
the model writes text is `draft_prompt()`, and that is validated before display
with the deterministic fallback named.

Giving it a shell was rejected. Every action is a named entry with fixed argv on a
machine holding 124 irreplaceable renders and a live GPU queue. Renders are
*proposed* for operator approval, never started. The reset tool is not exposed.

## Verified

**The validator, which is what makes model output safe at all:**

- **124/124** current known-good prompts pass — no false positives, including the
  real 3-speaker `27E`
- **9/9** deliberately broken prompts caught: prepended header, split `<d>` block,
  delivery prose after `</d>`, missing section, sections reordered, beat brackets,
  wrong `<Audio N>` count, undeclared tag, missing `[English]`

**The tools:** all 9 exercised against real project data and returning sensible
output. All 5 injection attempts refused — unknown tool, `../etc` as a clip id,
`/etc/passwd` as a doc name, `rm -rf /` as a build action, unknown GPU action.

**End to end with a stubbed model:** tool call parsed from the reply, tool run,
result fed back, final answer produced; the 4-hop cap terminates a model stuck in
a loop; the GUI page serves; `/api/status`, `/api/state` and `/api/chat` all
respond; SSE emits 96 events including `done`.

**Knowledge pack:** 9.5 KB / 1,548 words — fits an 8K context with room for the
conversation. Generated from live state, never hand-written, so it cannot drift.

## Two faults found in my own validator while building it

1. **It failed 12 of 124 correct prompts.** The E09 rule flags delivery prose
   after `</d>`, and the *prescribed* mouth-close clause — "He closes his mouth
   and **says** nothing further" — contains "says". Sanctioned silence clauses are
   now stripped before the check. This is the **seventh** checker in this project
   caught measuring the wrong thing.
2. **The beat-bracket check scanned only `detailed_description`** and missed a
   stray timestamp in `subject_definitions`, which is where
   `<Picture 1> is the first frame of [Shot 1]` lives — the most likely place for
   one to be pasted. Now scans the whole prompt.

## Still unverified

- **Never run against a real Ollama.** There is none in this environment. Tool
  dispatch, streaming, endpoints and the hop cap were tested with a stubbed
  model; the first live run is the real test.
- **Model quality is unknown.** Whether `qwen2.5-coder:14b` follows the
  `TOOL: name {json}` protocol reliably on this brief has not been measured.
  Expect to tune the model choice and possibly the temperature.
- **Speed is unmeasured.** A few tokens per second is expected on four CPU
  threads. That is the cost of leaving the GPU alone.
- No render was performed; no workflow was modified.

---

# Addendum — GPU/CPU auto-routing, natural conversation, desktop features

Operator: *"I want it to run on cpu if something is being generated on the gpu but
if its not the larger model will run on the gpu... Also I should just be able to
talk to it with natural language just like chatgpt. It should also be able to do
anything chatgpt desktop can do."*

## 1. It routes itself, per turn

`local_agent/router.py` (new). Two Ollama servers, chosen before **every** reply:

```
127.0.0.1:11434   GPU   default instance, largest installed model
127.0.0.1:11435   CPU   CUDA_VISIBLE_DEVICES=-1, 4 threads, 7B preferred
```

Two servers rather than one because a single instance cannot be CPU-locked and
GPU-enabled simultaneously, and "mostly on CPU" is not good enough when a render
needs the VRAM.

**It evicts, not just avoids.** On detecting a render it calls `keep_alive: 0` on
the GPU model before answering on CPU. A 14B model holds 9-10 GB; releasing it
late is the same as not releasing it.

**Three busy signals, any one sufficient:**

1. `render_queue_owner.json` names a live PID — the project's own lock, which
   covers the gap between claiming the queue and the backend loading, exactly
   when a naive VRAM check would report "idle"
2. port 8188 listening — catches a manual ComfyUI session, which is how the
   good-audio takes were made
3. `nvidia-smi`: VRAM over 2500 MB, or any foreign compute process

**Fails safe:** no `nvidia-smi` means the GPU is treated as BUSY. An unknown GPU
state is never permission to use it. A forced "GPU" preference is refused while a
render runs — the operator can force CPU, never force a conflict.

## 2. Natural conversation

The `TOOL:` line is protocol, never prose: the GUI renders it as an action card
the way any chat app does. Added conversation rules telling it to answer like a
normal assistant, to handle ordinary non-project questions, to act on plain
requests without asking permission for read-only and build actions, and never to
mention "tools" as a concept.

## 3. Desktop features

`local_agent/store.py` (new) plus a rebuilt interface: conversation sidebar,
new/rename/delete, history surviving restarts, **Stop** mid-generation (a
cooperative check inside the token stream, not just hiding output),
**Regenerate**, **Copy**, text-file attachments inlined into the message, tier
selector, and a live GPU/CPU indicator.

Deleted chats move to `chats/_deleted/` rather than being unlinked — a chat can
hold the only written record of a decision.

## Two bugs found by testing

### A crash on the very first message of a new chat

The GUI sends `id: null` for a new conversation. `store.load("")` raised
`ValueError` from the id validator, killing the request before a reply could
start — the first thing a new user would ever do. `load()` now returns `None` for
a missing or malformed id. `_path()` still refuses, so nothing escapes the chats
directory; only the failure mode changed.

### The CPU tier picked a 14B over an available 7B

`_pick()` fell back to base-name matching inside its main loop, so
`qwen2.5-coder:7b` (earlier in the list) matched an installed `qwen2.5-coder:14b`
and returned it, even though `qwen2.5:7b` was also installed. Size is the entire
point of the CPU tier. Now two passes: exact names across the whole list first,
base-name matching only as a fallback.

## Verified

**Router** — 12 checks: missing `nvidia-smi` reads BUSY; a live queue-owner PID
reads BUSY; a dead PID does not; a listening 8188 reads BUSY; auto+busy routes to
CPU; a forced GPU is refused while busy; a forced CPU is always honoured; CPU
options really carry `num_gpu: 0` / `num_thread: 4`; GPU options enable layers;
model preference correct for both tiers and for an unknown model; empty install
returns None.

**Tier switching** — GPU idle routes to the 32B on the card; flipping the busy
signal moves the next turn to the 7B on CPU; the GPU model is evicted in the
process.

**App** — new chat with `id: null` completes; route/tool/token/done all stream;
conversations auto-create, save, and list with a derived title; regenerate
re-answers; attachments are inlined and recorded verbatim in history; rename
works; Stop halts generation promptly rather than merely hiding it.

## Still unverified

- **No real Ollama and no real GPU** in the environment this was built in. Busy
  signals were tested by simulation; `nvidia-smi` parsing has never seen real
  output.
- Whether the installed model follows the action protocol reliably is unmeasured.
- Speed on either tier is unmeasured.

Run `python local_agent\router.py` first on the real machine — it prints exactly
what it detects and why.
