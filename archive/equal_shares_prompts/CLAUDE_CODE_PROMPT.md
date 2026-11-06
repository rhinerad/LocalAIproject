# Claude Code — paste this

> **SUPERSEDED IN PART, 2026-08-13.** The current plan is
> `CLAUDE_CODE_AUDIO_FIRST_PROMPT.md` and `docs/TWO_STAGE_AUDIO_FIRST_PIPELINE.md`.
>
> Still correct here: the one-backend rule, the process checks, the
> never-delete rules, the reporting format, and the continue-until-finished
> requirement.
>
> **Out of date here:** "Standing constraints" names fl2va at 736×416 / 0.3 MP —
> 0.3 MP warps faces and was replaced by 0.9 MP, and the audio pass uses the
> ref2va checkpoint. "Resume commands" points at `render_until_complete.py`,
> which is the old full-story fl2va render, not the current next action. "Known
> open items" is stale; the tree divergence is resolved and the review backlog
> has moved.
>
> Where this file and the audio-first documents disagree, the audio-first
> documents win. The previous version is
> `archive/config_backups/CLAUDE_CODE_PROMPT.BACKUP_before_ref2va_2026-08-13.md`.

Run Claude Code with its working directory set to:

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

Claude Code **can** execute processes on the Windows host. That makes it the only agent in this project capable of causing a two-backend collision. The constraints below are the point of this file.

---

You are continuing the **Equal Shares** film project from this directory, which is the canonical working tree.

**Read `PROJECT_CONTINUATION_BRIEF.md` before touching anything.** It supersedes `archive/superseded_docs/TECHNICAL_OPERATIONS.md` on which folder is authoritative. `CLAUDE.md` in this directory holds the standing rules; treat them as binding.

## The one-backend rule — read this twice

A render supervisor may already be running. Exactly one process may own ComfyUI port 8188 and the GPU. Before you launch **anything**:

```powershell
Get-Process python*, ComfyUI* -ErrorAction SilentlyContinue |
  Select-Object Id, ProcessName, StartTime, Path
Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue
Get-Content .\outputs\equal_shares\runtime\render_supervisor.log -Tail 15
Get-Date
```

If the supervisor log's last timestamp is within roughly ten minutes of now, **the render is alive**. Monitor it. Do not start a second supervisor, do not start a bare backend for a side experiment, and do not run the finalizer expecting it to render.

If you need the GPU for something else, ask the human to stop the supervisor first. Never kill it yourself without saying so and getting agreement.

## Standing constraints

- Full-quality H3 only: `minimax_h3_fl2va_pruned_int8_convrot.safetensors`, 20 steps single and dual anchor, `res_multistep` / `simple`, denoise 1.0, 736×416 at 24 fps. Turbo models, Turbo nodes, and Turbo LoRAs are prohibited.
- Never delete a raw attempt under `A:\Users\rhine\ComfyUI-Shared\output\story\<clip-id>\`. Use `work/reject_clip_visual.py` to reject.
- Do not write `manifest.json` or `visual_audit.json` by hand while the runner is active. The runner merges only the current record so concurrent review decisions survive; a hand edit defeats that.
- Mechanical validation is not acceptance. The supervisor's "N/124 valid clips" counts renders, not approvals. Never report it as an acceptance count.
- Do not claim completion until `work/audit_equal_shares_completion.py` passes every requirement.

## Resume commands

From this directory, only when you have confirmed no supervisor is running:

```powershell
$Python = "A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe"

& $Python ".\outputs\minimax_story_runner.py" ".\outputs\equal_shares\story_config.json" --check
& $Python ".\work\render_until_complete.py"
```

After all clips pass visual review:

```powershell
& $Python ".\work\finalize_equal_shares_when_ready.py"
& $Python ".\work\audit_equal_shares_completion.py"
```

## Known open items

The brief lists five, in priority order. The top two are: resolve the divergence between this tree and the stale live root one level up, and clear the visual review backlog of roughly 34 rendered-but-unreviewed clips between `09C` and `18D`.

## How to report

Concise plain language at meaningful changes and about once a minute during long work: current clip or stage, running status, pass or fail and why, next step, updated counts. No raw log dumps. Keep working unless input is genuinely required.

Start by running the four process checks above and reporting what you find, before proposing any action.

## Continue-until-finished requirement

This is a terminal-condition assignment. Keep working autonomously until the entire Equal Shares task is genuinely finished and `work/audit_equal_shares_completion.py` passes. Do not stop after a plan, status report, completed clip, completed stage, rejected generation, or ordinary recoverable error. Diagnose, preserve evidence, retry or use the documented fallback hierarchy, and proceed.

For long-running work, keep monitoring at sensible intervals and continue as soon as state changes. Automatically use the project permissions in `.claude/settings.local.json` for routine reads, edits, commands, renders, audits, recovery, assembly, and publishing. Do not ask the user to approve normal in-scope work and do not ask whether you should continue.

Stop only after the completion audit passes and final paths are verified, or for a genuine user-only credential, approval, missing source asset, material creative decision, or external-state change that remains after all safe alternatives are exhausted. If that rare blocker occurs, request only the smallest action needed. Do not treat waiting, rendering, retrying, visual review, or ordinary failures as blockers.

Deletion and overwrite prompts must not stall the work. Do not request deletion permission for routine cleanup. Keep the original and create a versioned replacement, copy instead of move, or archive/quarantine an obsolete disposable intermediate while preserving provenance. If a destructive command is denied, immediately use a non-destructive alternative and continue. Never delete raw generations, approved frames, project state, audit evidence, audio sources, assembly inputs, or deliverables.
