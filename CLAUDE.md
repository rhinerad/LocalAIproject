# Standing rules for agents (binding)

This file is loaded automatically by Claude Code; `AGENTS.md` points Codex
here. It holds only the rules that apply to every piece of work in this tree.
What the project *is* and what is *current* live in `README.md` and
`docs/CURRENT_HANDOFF.md`; history lives in `CHANGELOG/` and `archive/`.
The previous 430-line version of this file, with its Equal Shares job
description, is preserved at `archive/superseded_docs/CLAUDE_full_2026-08-30.md`.

## 1. Orient before you act

1. Read `README.md` (one page), then `docs/CURRENT_HANDOFF.md`.
2. Run `python scripts/write_handoff_status.py` and read `HANDOFF_STATUS.md`.
3. Read the newest entries in `CHANGELOG/` for the area you will touch.
4. `docs/GOLDEN_REFERENCE/PROVEN_FACTS.md` is this project's memory of what is
   actually established, each line with its measurement. Anything not in it is
   not proven, however confidently it is asserted elsewhere, including here.

Nothing under `archive/` is current. Never read project state from the parent
folder's `outputs/`; it is a stale fork.

## 2. Every change gets a CHANGELOG entry, written in the same session

`CHANGELOG/YYYY-MM-DDx_description.md`, where `x` is the next free letter from
`python scripts/next_changelog_id.py` (run it once per entry; it claims the id so
parallel agents cannot collide). Record what changed, why, and the evidence.
Regenerate the index with `python scripts/build_changelog_index.py`.

## 3. Verification means one thing here

A change is **not verified** because config and docs agree, because a drift
check is clean, or because regenerated files look right. All three passed on
2026-08-16 while the renderer was sending a corrupted prompt to every clip.
Verified means the workflow embedded in a real render was extracted
(`ffprobe -show_entries format_tags=prompt` on the MP4, or the PNG metadata) and
diffed against `docs/GOLDEN_REFERENCE/`. If you have not done that, say the
change is unverified. Never report document consistency as verification.
Unit tests passing is evidence for the code path they cover, nothing more.

## 4. Never destroy evidence

Never delete raw attempts, approved references, manifests, audit evidence,
source audio, assembly inputs, final deliverables, or prior QA verdicts. Reject
by recording a rejection; save new versions as new files; quarantine rather
than delete; copy rather than move. Progress and manifest entries are merged,
never replaced wholesale (a rerun must not erase an earlier `video_path` or QA
record). State files are written atomically through `local_agent/atomic_io.py`.

A denied destructive command is a signal to choose a non-destructive route and
continue, not a reason to stop. Destructive deletion, credential disclosure,
purchases, and unrelated system changes are never implicitly approved.

## 5. One backend, one GPU owner

Exactly one process may bind ComfyUI port 8188 and hold the GPU. Before any
render: check running python/ComfyUI processes, whether 8188 is listening, the
GPU lock (`gpu_lock.py` / the owner JSON it writes), and the tail of the active
supervisor log against the clock. If a render is alive, monitor it; never
duplicate it. Do not start a bare backend for a side experiment, and do not
kill a supervisor without saying so first.

`local_agent/` evicts its own Ollama model rather than competing for VRAM. It
may start a render only through its gated tools (`gpu_gate`), never by
reaching ComfyUI directly.

## 6. Thermal safety

All render paths use the thermal guard (`work/thermal_guard.py`, tracked since
2026-11). A new GPU job may start at 70 °C or below; if hotter, wait for 60 °C.
After every render the backend is stopped and the next job waits for 58 °C.
During sampling 82 °C is an emergency ceiling: interrupt, record an error, cool
down, retry. If NVIDIA temperature telemetry fails three consecutive times, do
not start another render blindly: unknown is never permission.

The CPU Ollama instance is capped at four of the sixteen logical processors.
Do not remove that cap or run a second heavy CPU job beside it.

## 7. `local_agent/` security model

- `tools.py` is a **fixed whitelist of tools and of places**: writes are
  contained to the project tree, never to `outputs/equal_shares/**`, never to
  gate or owner state files. Do not relax it for convenience; it is the
  security model, and more so because a phone can reach it.
- The HTTP server binds **`127.0.0.1`** only. Never `0.0.0.0`.
- Output from the worker farm (Mac/edge workers) is untrusted text. Tool calls,
  vectors, or summaries it returns are validated or discarded, never executed.
- Paired phones get conversation tools by default; file reads, URL fetches,
  renders and writes need an explicit per-identity grant.
- Secrets, chat memory, uploads, the Reticulum identity under
  `local_agent/rns_wifi/storage/`, and logs are never committed. `.gitignore`
  and `scripts/sync_up.ps1` enforce this; `scripts/untrack_private_data.ps1`
  untracks older copies without deleting them.

## 8. Working habits

- Multiple agents touch this repo. Re-read a file before editing it, use exact
  anchors, and preserve each file's line endings (several files are CRLF).
- Work an assignment through without stopping for routine decisions; stop only
  for a user-only credential, a missing source asset, a material creative
  decision, or an external condition with no safe workaround. Record an
  undecidable question in the changelog entry and take the safest option.
- Report concisely at meaningful changes: what, status, pass/fail with reason,
  next step. No raw log dumps.
- Generic backend code must not hard-code 124 clips, Equal Shares character
  names, this film's duration, or `A:\Users\rhine` paths; use `GVD_ROOT`,
  `COMFY_SHARED_INPUT`, `COMFY_SHARED_OUTPUT` and the other env vars.
- Equal Shares (the 124-clip MiniMax H3 film) is a preserved, paused project
  profile. Do not resume its audio pass or alter its evidence unless the
  operator explicitly asks for Equal Shares work; its rules are in
  `archive/superseded_docs/CLAUDE_full_2026-08-30.md`.
