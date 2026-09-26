# 2026-09-11c — C001 operator acceptance and still-only resume

## Operator decision

After reviewing the displayed corrected `C001_last` frame, the operator said
"looks good continue" on 2026-09-11. This records acceptance of the exact
candidate for continuation of the still-image phase:

- story: `pack_f8f7f70e364d40c0_72a7c2e5_c001_last`
- attempt: `6e12ff2ab0b84085b765b7dd07a6bd4c`
- SHA-256:
  `1302d430636908f50d6d3c2815559a7161300d9d2a5ab96320dd80c95260b4b6`
- automated QA: pass under
  `reference-blind-continuity-face-and-hand-crop-v12`

This is a C001 continuation decision, not the final approval record for the
entire 204-still set. The production approval API deliberately creates one
hash-bound review only after every current still has passed QA. That full-set
approval remains pending, and video generation remains prohibited.

## Authorized continuation

Resume `work/run_prompt_pack_production.py` as a direct script for conversation
`f8f7f70e364d40c0`. The existing C001 start and last records are hash-checked
and QA-checked before being skipped. Production must continue with the next
unfinished still, preserve every attempt, enforce the 82 C thermal ceiling,
and stop before videos for full-set operator approval.

No prior image, QA file, receipt, or failed attempt was overwritten to record
this decision.

## C002 checkpoint and requested stop

The operator subsequently required work to stop as soon as the active C002
attempt reached an unambiguous pass/fail checkpoint. The third bounded
`C002_start` attempt reached that checkpoint and failed exact-model semantic
QA:

- attempt: `95a3e1c246dd4bd0bf869577198f30eb`
- mechanical gate: pass
- semantic gate: fail
- observed failure: different actor face, hair/facial hair and body type, plus
  changed room geometry relative to the accepted C001 reference
- forbidden camera/equipment check: pass

The supervisor was stopped immediately after `qa.json` existed. The watchdog
briefly classified the deliberately stopped PID as stale; that stop-race record
was preserved and explicitly acknowledged as an operator-requested stop, not an
infrastructure failure. Final state is `paused_after_c002_checkpoint`, phase
`stills`, supervisor PID `null`. Port 8188 is free and the GPU returned to its
idle baseline. No C002 last frame, later still, or video was started after the
requested checkpoint.
