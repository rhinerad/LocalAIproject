# Claude Code — Equal Shares continuity and watchdog assignment

> **SUPERSEDED 2026-08-16 — historical, do not execute.**
>
> This file instructs rendering purpose-built VOX clips with invented filler
> dialogue. **That is prohibited.** A missing character voice comes only from
> that character's first qualifying actual story soundtrack.
>
> Current instructions: `docs/AUDIO_PASS_RUNBOOK.md` (procedure),
> `docs/H3_PROMPT_RULES.md` (prompt grammar), `CHATGPT_START_AUDIO_PASS.md`
> (paste-able start prompt). `CLAUDE.md` is binding.


Work in:
`A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09`

Read `CLAUDE.md`, `docs/OMNI_REFERENCE_VOICE_LOCK_PIPELINE.md`, and the newest
`docs/WORKFLOW_NOTES.md` entry completely. The Omni document is authoritative.

Inspect `local_agent_owner.json`, `omni_pipeline_owner.json`,
`render_queue_owner.json`, port 8188, sampler state, logs, and GPU temperature.
If the offline local agent or deterministic coordinator is healthy, monitor it
without launching duplicates. If neither is live and the controlled experiment
is unfinished, start the offline CPU-limited local agent in a hidden background
PowerShell process using:

`A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\work\launch_open_interpreter_handoff.ps1`

Continue safe independent diagnosis, prompt/code auditing, manifest validation,
and recovery while it works. If the local agent exits and no sampler or render
subprocess is active, diagnose and repair the latest recoverable failure, then
restart only one local agent or run
`work/continue_omni_voice_lock_pipeline.py` directly.

The immediate objective is only: three missing VOX identity masters, immutable
5-10 second checksum-pinned masters for all 18 voices, versioned native-tag H3
prompts, and one controlled 0.2 MP attempt each for 00A and 00I. Mechanically
audit exact words, timing, unexpected speech, reference hashes, and evidence of
double tracking using installed tools. Do not start the full Stage-1 queue until
both controlled tests are accepted. Do not start the 0.9 MP picture pass.

Use configured permissions for normal safe reads, versioned edits, validation,
rendering, recovery, and monitoring. Never use Turbo. Never download anything.
Never run two GPU backends, two render coordinators, or two local agents. Never
delete, overwrite, move, or rename evidence. The project permission rules deny
destructive shell operations; do not attempt to bypass them.

If every machine-checkable task is exhausted and a human ear decision is the
only remaining gate, write a precise versioned record at
`outputs/equal_shares/runtime/human_decision_required.json` naming the exact
WAV/video paths and required judgments. That is a legitimate completed pause;
do not burn more generations while waiting for that decision.

