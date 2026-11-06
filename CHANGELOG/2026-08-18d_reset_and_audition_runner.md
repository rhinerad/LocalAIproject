# 2026-08-18 — corrupt pass erased, ladder counter fixed, audition runner built

Operator instruction: *"just erase the 83 pending clips since they were all done
incorrectly. Reset the ladder count and run the 27 auditions and pick voices."*

## 1. The corrupt pass is cleared — all 124, not 83

`work/reset_corrupt_audio_pass.py` (new). Every one of the 124 manifest records
came from the corrupted-prompt pass: 77 `needs_ear_review`, 41 `retry_required`,
6 `auto_pass_pending_continuity_review`. Nothing was `accepted`. So all 124 were
cleared, not just the 83 pending — the other 41 were equally corrupt.

**"Erase" was implemented as clear-state-and-quarantine, not delete.** CLAUDE.md
forbids deleting raw generations, and the operator named a set of clips rather
than a set of files. Preserved:

```
audio_pass_manifest.BEFORE_RESET_20260818_171456.json    the whole prior manifest
_QUARANTINE_corrupt_prompt_pass_2026-08-17/              124 media folders
                                                         772 candidate WAVs +
                                                         validation reports
```

The manifest now holds **0** clip records; all 124 render from scratch.

## 2. Ladder counter fixed — two separate faults

### 2a. It was counting lifetime attempts

`render_audio_pass.py` derived the ladder rung from total attempts ever made. The
prior attempts were rendered under the *corrupt* prompts, so they said nothing
about which durations had been tried for the current one.

Measured before the fix, on the 41 resumable clips: **36 would have started at
rung 8** (base ±4 s, the far end) and **20 would have reported the ladder
exhausted and rendered nothing at all.**

Now only attempts carrying a `ladder_rung` field count — i.e. attempts made by
the ladder-aware renderer. Self-healing: pre-ladder attempts are ignored but
preserved, so no reset is needed for the counter itself. `attempt_no` stays
lifetime for filenames; `ladder_position` is new and is what drives the rung.

### 2b. The ceiling was comparing seconds against a frame-quantized length

Found while verifying 2a. `ladder()` capped rungs by the clip's scripted
**seconds**, but both soundtrack and picture snap to the 17k+5 grid. A clip
scripted at 15.0 s renders **362 frames = 15.083 s** of picture; its fitted
soundtrack base is also 362 frames — and 15.083 > 15.0, so the cap threw the
**base rung** away.

Measured: **51 of 124 clips** would have skipped their own base duration and
opened at rung 2 (base −1 s), rendering every already-tight clip short on the
first attempt. `ladder()` and `rung_for_attempt()` now take `max_frames`, and the
renderer passes the clip's `scripted_frames`.

Verified after both fixes: **all 124 clips now open at rung 0**, every ladder
starts at the base, and no rung exceeds its clip's picture frame count.

## 3. The audition pass is executable

| File | Purpose |
|---|---|
| `work/render_voice_auditions.py` | **New.** Renders 9 characters x 3 seeds = 27 takes at 0.2 MP, fl2va, **no audio reference wired**. One backend per render, thermal guard, claims the same GPU lock as the soundtrack pass so the two can never overlap. Skips any pack whose prompt contains `<Audio` or does not start `subject_definitions:`. |
| `work/install_audition_winners.py` | **New.** `--pick Kent=2 --apply` cuts the chosen take into a master: measured 'hmpf' trim, one contiguous passage, written as a new version, never overwriting. Reports length and speech density and flags anything under 6 s or below 55% density. |
| `START_VOICE_AUDITIONS.md` | **New.** Paste-ready Claude Code prompt for the pass, with the 124-clip pass explicitly blocked. |

Dry run confirms the 27: Avery 41w/447f, Kent 37w/413f, Doris 32w/362f, Terminal
voice 24w/294f, Ryann Sally 23w/277f, Faith White 21w/260f, Volunteer 18w/226f,
Housing representative 15w/209f, Male Visitor One 3w/107f.

`Male Visitor One` is 3 words and will produce a ~4.5 s master at best. It is
recurring (`00D`, `00D2`) so it needs one, but it will be flagged `short_master`.

## Verified after this change

- manifest holds 0 records; all 124 clips would render fresh
- all 124 open the ladder at **rung 0**; none omits its base rung
- no rung exceeds its clip's scripted frame count
- the operator's 10 s example still reproduces exactly: 10, 11, 9, 12, 8, 13, 7
- 124 media folders + 772 derived files + the full prior manifest all preserved
  in quarantine
- every touched Python file compiles; the audition dry run lists exactly 27

## Still unverified

- **No render, still.** Every fix from 2026-08-17 and 2026-08-18 remains
  unexercised. The first audition take is the first evidence for any of it.
- Whether the fl2va audition path behaves as `17.mp4` did — same node, checkpoint
  and settings, but `17.mp4` had two boundary images and a prompt that declared
  unwired `<Audio>` tags. The auditions have one image and no tags.
- Whether the trimmed 'hmpf' heads are clean. Energy heuristic, never heard.
