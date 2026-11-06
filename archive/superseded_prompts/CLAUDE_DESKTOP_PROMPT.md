# Claude Desktop — paste this

Paste everything below the line into a new Claude Desktop conversation, after connecting the folder `A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09`.

Claude Desktop cannot reach the Windows host's processes, GPU, or ComfyUI. It can read and write files. Use it for review, planning, documentation, and config edits — not for starting renders.

---

You are continuing the **Equal Shares** film project. The connected folder is the canonical working tree.

**Before anything else, read `PROJECT_CONTINUATION_BRIEF.md` in full.** It supersedes `TECHNICAL_OPERATIONS.md` on the question of which folder is authoritative. Then read `HANDOFF.md`, `outputs/equal_shares/story_config.json`, `outputs/equal_shares/manifest.json`, and `outputs/equal_shares/visual_audit.json`.

## Hard constraints

- **Never start a ComfyUI backend, a render supervisor, or anything that binds port 8188.** A render supervisor is likely already running on the Windows host. Exactly one backend may exist at a time. If you believe a render must be started or stopped, say so and let the human do it.
- **Do not edit `manifest.json` or `visual_audit.json` while a render is active.** The runner merges records into them; a concurrent write will corrupt state or silently drop a review decision.
- Before assuming the render is alive or dead, read the tail of `outputs/equal_shares/runtime/render_supervisor.log` and compare its timestamp to the current time. Do not guess.
- Full-quality MiniMax H3 only, 20 steps, single and dual anchor. Turbo models, Turbo nodes, and Turbo LoRAs are prohibited.
- Never delete a raw attempt. Rejection is recorded, not erased.

## What you are good for here

Visual review of rendered clips using the contact sheets in `outputs/equal_shares/validation_contacts/`; reconciling manifest state against `visual_audit.json`; drafting corrected prompts for failed clips; planning salvage strategies; and keeping the documentation in this folder accurate.

## Continuity you must never violate

The receptionist is the only woman in the opening and stays behind the staff window. Exactly two male visitors perform the chair interaction; both enter through the separate doorway and remain on the public side. One public chair at screen-left. No glass gate, fence, divider, extra chair, or third man. The Narrator appears only where the script places him and never resembles Kent. `references/alex_vale_master_v1.png` is authoritative for Kent Brentwood; `references/ensemble_cast_master_v1.png` is authoritative for the five principals, left to right: Kent Brentwood, Avery Renfield, Doris Lovelay, Ryann Sally, Faith White.

In `04C`, Kent has already declined before the clip begins — no bill, donation, transaction, or reaching toward the plate. Attempt 4 is the accepted take; attempt 3 must never be reselected.

H3 audio is always discarded. Never reject a visually correct take for gibberish speech or wrong music.

## How to report

Plain language, concise. State the clip or stage, whether it is generating, validating, retrying, editing, assembling, or auditing, what passed or failed and why, what you will try next, and the accepted and unresolved counts when they change. Do not dump raw logs.

Start by reading the brief and giving me a five-line status: active tree, render state, clips rendered, clips reviewed, and the single most urgent open item.
