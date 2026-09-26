# 2026-08-20 — the local_agent upgrade plan, the mesh roadmap, and a second render pipeline

No code changed in this entry. It records **specifications and plans** added to
the tree, and the handoff updates that make them findable.

## 1. `local_agent/UPGRADE/` — nine numbered prompts

`00_INDEX.md` plus eight self-contained Claude Code prompts taking the offline
assistant from working to close-to-ChatGPT-Desktop. **Five need no internet at
all**, which is deliberate — the operator is on a phone hotspot.

| # | What it does | Internet |
|---|---|---|
| 01 | native function calling — replaces the `TOOL:` regex protocol | no |
| 02 | 8K → 32K context, BM25 retrieval over the whole doc tree | no |
| 03 | memory across chats, rename button, hardened web search, code-exec decision | no |
| 04 | vision/audio/embedding tools built and gated, no-op until models exist | no |
| 05 | model swap to gpt-oss-20b, then switch the gates on | yes, ~21 GB |
| 06a | phone over a USB cable via `adb reverse` | ~10 MB |
| 06b | Progressive Web App — home screen, share sheet, camera, voice | no |
| 06 | the same over cellular via Tailscale | once |
| 07 | **a second, general batch render pipeline** | no |

**01 has already been executed** — see `2026-08-19_native_function_calling.md`.

Two design choices worth recording. Retrieval in 02 is **lexical BM25 in plain
Python**, with a swappable scorer interface, so it works with zero downloads and
embeddings drop in later — and 05 instructs a comparison, keeping BM25 if
embeddings do not clearly win. And 04 builds every sensory tool **now**, returning
a specific "model not installed, N GB" message, so the internet wait costs no
rewiring.

## 2. `local_agent/ROADMAP.md` — the end goal

Operator's stated aim: a **Reticulum mesh** linking phone and workstation, with an
Android client as a thin terminal onto this agent — one assistant on both devices,
all compute staying on the RTX 5080.

Recorded as a roadmap because it **constrains decisions being made now**:

- the HTTP server keeps binding `127.0.0.1`; the obvious shortcut of `0.0.0.0`
  would put a file-writing, action-executing server on any network the laptop joins
- `agent.answer()` stays transport-agnostic — it takes a history list and a
  callback and knows nothing about HTTP. That is the seam a mesh plugs into
- conversations stay transport-agnostic in `store.py`
- the `tools.py` whitelist becomes *more* important once a phone can reach it,
  not less

Not researched against current Reticulum documentation. It is a plan, not a
verified design, and says so.

## 3. `UPGRADE/07_batch_renderer.md` — a second pipeline

Point the agent at a folder of numbered prompts, video motion references and image
reference slots; it renders the sequence unattended. Two findings shaped the spec:

**Socket numbers and prompt tags are different numbers.** The operator specified
slots as "img 0 / img 1 / img 2"; ComfyUI sockets are zero-based
(`ref_image_0`) while MiniMax prompt tags are one-based (`<Picture 1>`). Tags also
follow connection order, so an empty slot shifts everything after it. This project
already lost four clips to exactly this class of error — `<Audio 2>` declared
while wired into `ref_audio_0`.

Related: the operator's existing hand-made renders used **`<Video 0>`**, which is
non-conforming. The guide is one-based throughout, so that tag likely bound to
nothing — which would explain why those prompts needed heavy prose to compensate.

**There is a canonical way to say "motion only".** From
`docs/reference/MINIMAX_PROMPT_GUIDE_ref.md` §2.1:

> `<Subject 1> is the woman whose appearance comes from <Picture 1> and whose
> walking motion comes from <Video 1>.`

Plus a `retention_analysis` line marked `weak_reference`, per §4.1's own example
`<Video 1> (cut and pacing structure): weak_reference`. That section is the one
this project proved the model actually acts on — adding it is what removed the
doubled voice after weeks of prose failing.

The spec is walled off: it reuses `render_single_pass.py`, `thermal_guard.py`, the
queue owner and the duration ladder, and is **forbidden from reading or writing
`outputs/equal_shares/**`.**

## 4. Handoff updates

- `README.md` — `local_agent/` added to Read-first and the folder map, with its
  own section
- `CLAUDE.md` — new binding section for `local_agent/`
- both now disambiguate a **real name collision**: "the local agent" has meant
  the ChatGPT/Codex render agent throughout this tree, and now also means the
  offline Ollama app. They are unrelated. Confusing them wastes time, so both
  entry points state the difference explicitly.

## Verified

- all nine UPGRADE files present and cross-referenced from `00_INDEX.md`
- `README.md` and `CLAUDE.md` both reference `local_agent/`
- the `<Video N>` and marker quotes above were read from the local copy of
  MiniMax's guide, not recalled

## Still unverified

- **Every UPGRADE prompt except 01 is unexecuted.** These are specifications.
- **07's central unknown:** whether `MiniMaxH3ReferenceToVideo` has a video
  reference socket at all. The 15 proven-good graphs use image and audio
  references only. The prompt's first job is to query the live ComfyUI
  `/object_info` and **stop and report** if no such socket exists, rather than
  shipping something that silently ignores the video.
- `validate_h3_prompt.py` passes 124/124 on this project's dialogue prompts;
  its behaviour on motion-reference prompts is untested.
- The Reticulum design is unresearched.
