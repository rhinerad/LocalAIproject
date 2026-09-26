# 2026-08-30 — Documentation-consistency pass for the general-agent reprioritization

## What changed

The operator reprioritized: the local agent is now general-purpose first;
Equal Shares is a preserved, optional project profile, explicitly paused
(no render, no audio-pass resumption, no evidence/manifest changes). Three
documents that still framed Equal Shares as the default active workflow, or
contained directive language that could read as "keep working toward the
124/124 audio gate," were marked — not rewritten, not stripped of safety
content:

- `CLAUDE.md` — added a **SCOPE NOTICE** section at the very top (before
  "READ FIRST"), pointing to `local_agent/README.md`, `TODO.md`,
  `docs/design_notes/architecture_audit_2026-08-27.md`, and recent
  `CHANGELOG/2026-08-*.md` entries as current-priority sources, and stating
  this file is binding only for its safety/verification/evidence/thermal-GPU
  rules, not its Equal Shares job description. Added inline "Superseded
  2026-08-30" notes directly above three specific directive blocks that
  could otherwise be read as live instructions to keep pushing Equal Shares
  to completion: the "Current job — 2026-08-16" header, "Do not interrupt
  the operator" ("rendering all 124 soundtracks is your job"), and
  "Persistence and permission handling" ("terminal-condition assignment...
  continue autonomously until the audio gate passes"). No safety rule,
  evidence-preservation rule, or thermal/GPU constraint was removed or
  weakened anywhere in the file.
- `docs/CLAUDE_CODE_CONTINUATION_2026-08-29.md` — added a short banner
  under the title marking it a dated snapshot and redirecting to current
  sources.
- `GROK_STATUS.md` — added a "Reprioritization — 2026-08-30" section (this
  file is the live cross-agent coordination note per the operator's own
  "any change must be recorded here the same session" rule); did not alter
  any of the existing status content below it.

## Why

CLAUDE.md is loaded automatically as binding instructions for Claude Code
sessions in this tree, and its "Current job" / "Do not interrupt the
operator" / "Persistence and permission handling" sections contain
autonomous-continuation language written when Equal Shares actually was the
job. Left unmarked, that language could plausibly cause a future session
(any agent, not just this one) to treat "keep working until 124/124" as a
live directive and resume the paused pipeline against the operator's
explicit 2026-08-30 instruction. The fix is targeted notices at the exact
points of risk, not a rewrite — the underlying render-safety and
verification rules remain exactly as strict as before, since general-agent
work still benefits from them (evidence preservation, no destructive
deletion, real verification over document-consistency claims).

## What was verified after

Read all three files back after editing to confirm: the SCOPE NOTICE and all
three inline notes render correctly and sit above their respective sections;
no line inside the "READ FIRST", "Verification means one thing here",
continuity-lock, or "Never destroy evidence" sections of CLAUDE.md was
touched; `GROK_STATUS.md`'s existing 2026-08-30 status content (UPGRADE 23
re-verify) was preserved unchanged below the new section.

## What is still open

- `local_agent/README.md` does not yet mention the PowerInfer chat-picker
  integration (router.py's `is_powerinfer_model`/`_decide_powerinfer` path,
  built and verified today) in its Files table or model-policy section —
  a real documentation gap, not a scope-framing one. Not fixed in this pass;
  flagged for a follow-up doc update once PowerInfer's production registry
  has an actual accepted model.
- Other older docs in `docs/` (e.g. the various superseded/bannered audio
  prompts already marked in CLAUDE.md's "Which handoff prompt is current"
  section) were not re-audited here; this pass targeted only the three
  documents most likely to be read as live instructions by an autonomous
  agent picking up this tree cold.
