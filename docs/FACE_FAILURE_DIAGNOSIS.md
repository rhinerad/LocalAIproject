# Face and identity failure — diagnosis

Written August 10, 2026 from the attempt records in `outputs/equal_shares/manifest.json` and `visual_review.json`.

> **Update, 2026-08-10, later the same day.** The caveat below has been overtaken by evidence and is now wrong. A human review of clips `14B`, `14C`, `15A`, `15B`, `15C`, and `16A` at native resolution found **distorted faces in every one of them**, plus a desk and a person materialising in `15A` and furniture drifting around the room in `16A`. Face and identity failure is the dominant failure mode, not a structural risk awaiting confirmation.
>
> The reason it did not appear in the rejection records is now clear: nothing downstream of `09C` had been reviewed at all, and the machine-assisted pass that reviewed it used downscaled contact sheets in which faces were 20 to 30 pixels — too small to show the fault. The absence of face rejections in the archive reflected the absence of face-capable review, not the absence of face failures.
>
> The resolution hypothesis in section "Face degradation as a structural risk" below is therefore **supported**, and its recommended measurement is now the priority action rather than a future nicety. The furniture drift in `16A` extends it: at 736 × 416 the model is failing to hold not just facial features but static set geometry across a shot.
>
> See `outputs/equal_shares/VISUAL_REVIEW_PENDING_10A_ONWARD.md` for the per-clip findings and the required review method.

**Read this caveat first — superseded, retained for the record.** The title of this document presumes a face-specific failure mode. The evidence on disk does not support that presumption as the dominant problem. What the data actually shows is a *population and blocking* failure concentrated in the opening sequence, plus a large volume of historical retries spent on an audio criterion that has since been abandoned. Face and identity degradation is real and worth guarding against, but it is a structural risk driven by resolution, not the thing that has actually been costing attempts. The rest of this document separates what is measured from what is hypothesis.

---

## What the attempt data shows (measured)

Across the 77 clips currently in the manifest, 128 total attempts were made. Sixty-five clips succeeded on the first attempt. The retry burden is almost entirely concentrated in one place:

| Clip | Attempts |
|---|---|
| `01A` | 17 |
| `00C` | 10 |
| `00A` | 7 |
| `00D` | 7 |
| `00B` | 5 |
| `04C` | 4 |
| `00E` | 3 |
| `00D2`, `00F`, `00G`, `00H`, `07C` | 2 each |

That is 55 attempts spent on the ten opening clips (`00A`–`00H`, `00D2`, `01A`), against 12 attempts total for everything else combined. From `09A` onward — thirty-plus consecutive clips — **every clip has rendered clean on the first attempt.**

The naive reading is that the model got better. It didn't. Three things changed.

## Why the opening was expensive (measured)

`visual_review.json` records the actual rejection reasons for the opening clips, and they fall into two groups.

**Group one: invented people and wrong blocking.**

- `00A` attempt 1 "invents a man behind reception."
- `00C` "invents public-side people."
- `00D` had a "three-man error," fixed only at attempt 4.
- `00D2` required an explicit "two men only; one seated / one standing; receptionist always behind desk."

This is the real, recurring visual failure. The opening is the only sequence in the film with a hard numerical constraint on how many people may be in frame and which side of a barrier they occupy. The model does not natively respect cardinality. Given a waiting room, it populates the waiting room. Every additional person it invents is a rejection.

**Group two: audio — now obsolete.**

- `00A` rejected for "gibberish/invented speech."
- `00C` rejected because "offline transcript confirms invented gibberish before the intended line."
- `00D` "visual geometry passes, but offline transcription found malformed/invented narration."
- `00D2` "visual blocking passes, but narration is largely unintelligible."

Note the phrasing on the last two: **the picture was acceptable and the clip was regenerated anyway, for audio.** The project has since adopted a blanket policy that all H3 speech and music is discarded and replaced in post. Under current rules, `00D` and `00D2` would have been accepted immediately.

A conservative reading of the records suggests something on the order of fifteen to twenty of the fifty-five opening attempts were spent chasing an audio criterion that no longer exists. This is the single largest identified source of wasted GPU time in the project, and it is already fixed — provided nobody reintroduces the old rule. `CLAUDE.md` and the agent prompts all now state explicitly that gibberish speech is never grounds for rejection.

## A data integrity defect to fix

`outputs/equal_shares/visual_review.json` is malformed. `00D` and `00D2` each appear **twice**: once inside the `clips` object with `status: rejected`, and again as a top-level sibling key of `clips` with `status: approved_visual_only`.

The top-level records are the later, correct ones — they name the specific accepted source files (`attempt_1_00004_.mp4` and `attempt_1_00002_.mp4`) and note the three-man error was fixed. But any consumer that parses `visual_review.json["clips"]` and stops there will read both clips as rejected.

This file appears to be superseded in practice by `visual_audit.json`, which is what `archive/superseded_docs/TECHNICAL_OPERATIONS.md` treats as the manual review record. Either repair the duplicate keys or formally retire `visual_review.json` with a note pointing at `visual_audit.json`. Leaving a file on disk that reports approved clips as rejected is a trap for the next reader.

## Face degradation as a structural risk (hypothesis, not measured)

No rejection record in the files inspected cites a broken face as the reason. That is not proof faces are fine — visual review has only reached `09C`, and roughly 34 rendered clips have never been examined. It does mean face failure is unconfirmed rather than established.

There is nonetheless a clear structural reason to expect face problems, and it is worth stating precisely so it can be tested rather than argued about.

Generation runs at **736 × 416**. In a wide or medium waiting-room shot, a standing figure occupies perhaps 40 to 60 percent of frame height — call it 170 to 250 pixels. A head is roughly one-seventh of standing height, so 25 to 35 pixels tall, and the face proper is smaller still. Kent's identifying features — the neat dark mustache, the receding hairline, the prominent brows — have to survive inside a region of perhaps twenty by twenty pixels, through a VAE encode and decode.

There is simply not enough spatial budget for a mustache to be reliably present. This predicts a specific signature: identity holds acceptably in close and medium-close shots and degrades in wides, and the degradation shows up as *feature dropout* — the mustache vanishes, the hairline flattens — rather than as the face morphing into a different person. It also predicts that the negative prompt's `identity drift, face change` terms will have little effect on wides, because the problem is resolution, not guidance.

**How to test this properly**, once the review backlog is cleared: for each reviewed clip, record the approximate face height in pixels from the overview contact sheet, and record whether identity was judged acceptable. If the hypothesis holds, there will be a visible threshold — a face height below which acceptance collapses. That number is the actionable output. It tells you which shots in the remaining 47 clips are at risk before you render them.

If the threshold turns out to sit above the face sizes your wides actually produce, the options are, in increasing order of cost: reframe the affected shots tighter in the prompt and boundary frames; raise generation resolution for those specific clips (which changes VRAM and timing and must be validated against the proven graph before adopting); or accept the wides and rely on the fact that an audience cannot resolve a mustache at that scale either.

Do not raise resolution globally on a hunch. The 736 × 416 / 0.3 MP / multiple-of-32 configuration is part of the proven manual H3 baseline, and changing it invalidates the comparison against every clip already accepted.

## What to actually do about the opening pattern

The lesson from `00A`–`00H` generalizes to any future multi-person shot. Cardinality and side-of-barrier constraints must be stated positively and numerically in the prompt, not left to the negative prompt to suppress. "Exactly two men, one seated and one standing, on the public side; one woman, the receptionist, behind the staff window" succeeded where negative terms like `duplicate person, missing person` did not.

The negative prompt is a weak instrument for counting. It biases against a concept; it does not enforce an integer. Any clip whose acceptance depends on how many people are in frame should carry the count in its positive prompt and should be reviewed with the every-second contact sheet rather than the six-frame one, because an invented person often walks in partway through.
