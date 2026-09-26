# 2026-08-25 — Current local-agent handoff and launcher-bundle sync

## What changed

- Added `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-25.md` as the concise current
  state document for the general local assistant and storyboard work.
- Added visible pointers from `README.md`, `CHATGPT_HANDOFF.md`, and
  `PROJECT_CONTINUATION_BRIEF.md` so older Equal Shares production documents are
  not mistaken for current local-agent operating instructions.
- Corrected the repository overview: the desktop assistant has a fixed,
  separately guarded general batch-render action and read-only storyboard
  planning, but remains forbidden from Equal Shares output and from implicit
  image/model execution.
- Updated the desktop launcher bundle at
  `A:\Users\rhine\Desktop\EQUAL_SHARES_LOCAL_AGENT\`:
  - `README_FIRST.txt` now identifies the general assistant, active pause, and
    canonical handoff;
  - `PROMPT_INDEX.txt` now clearly labels 00–09 historical while pipeline work
    is paused;
  - `10_LOCAL_AGENT_CURRENT_STATE.txt` provides a short launcher-side summary.

## Authority boundary

- The canonical repository and handoff remain
  `COMFYUI_STORY_HANDOFF_2026-08-09`.
- The parent `outputs/` tree was deliberately not touched: binding project rules
  identify it as a stale fork that must not receive state copies.
- No model, render, download, queue, source asset, or Equal Shares evidence was
  changed by this documentation synchronization.
