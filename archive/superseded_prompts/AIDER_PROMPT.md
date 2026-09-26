# Aider — paste this

Aider edits files. It does not supervise renders. Use it for surgical changes to the Python tooling and the JSON config, not for operating the pipeline.

Launch from this directory. Add only the files you intend to change — this tree contains hundreds of megabytes of clips, frames, and contact sheets, and adding broadly will exhaust context immediately.

```
aider --read PROJECT_CONTINUATION_BRIEF.md --read CLAUDE.md work/render_until_complete.py
```

---

## Context to give Aider

You are editing tooling for **Equal Shares**, a 124-clip MiniMax H3 film pipeline. This directory is the canonical working tree; the parent directory's `outputs` folder is a stale fork frozen at 2026-08-10 01:43 and must not be read for state.

A render supervisor is probably running right now against these files. That has two consequences for you:

1. **Do not edit `outputs/equal_shares/manifest.json` or `visual_audit.json`.** The running process writes them. Aider's whole-file rewrites will clobber concurrent state.
2. **Edits to `work/render_until_complete.py` or `outputs/minimax_story_runner.py` take effect on the next invocation.** The supervisor re-invokes the runner per clip, so a mid-run edit to the runner will apply to the next clip. Assume your change goes live within about eight minutes. Do not leave the file in a broken intermediate state.

Safe to edit freely: the salvage and repair scripts (`work/salvage_*.py`, `work/repair_*.py`, `work/select_*.py`), the audit scripts, the contact-sheet builders, and the documentation.

Edit with care and re-check afterward: `outputs/equal_shares/story_config.json`. Change only the specific clip you mean to change, preserve UTF-8 with BOM handling as the existing loader expects, and follow any edit with:

```powershell
& "A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe" `
  ".\outputs\minimax_story_runner.py" ".\outputs\equal_shares\story_config.json" --check
```

## Invariants your edits must preserve

- Steps stay at 20 for both single-anchor and dual-anchor. Never introduce a Turbo model, Turbo node, or Turbo LoRA.
- 736×416, 24 fps, 8-bit, `res_multistep` / `simple`, denoise 1.0.
- Frame counts round upward to the next value congruent to 5 modulo 17.
- One clean ComfyUI backend per clip. Do not "optimize" the supervisor by keeping a backend warm across clips — the teardown is deliberate.
- Raw attempts under `A:\Users\rhine\ComfyUI-Shared\output\story\<clip-id>\` are never deleted. Do not add cleanup logic.
- The runner merges only the current clip's manifest record. Do not replace that with a whole-file write; it exists so concurrent visual-review decisions survive.
- H3 audio is discarded downstream. Do not add logic that treats audio quality as a render failure.

## Style

Match the existing code. These scripts are plain, procedural, and resumable by design — state lives in JSON on disk, not in memory. Keep it that way. Prefer a new small script over a clever refactor of a running one.
