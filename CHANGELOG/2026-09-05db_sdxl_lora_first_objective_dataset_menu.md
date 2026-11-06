# 2026-09-05db — SDXL LoRA first-objective dataset menu (no pick)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05db**.

Survey only. No kohya_ss, no GPU, no dataset copy/caption/cull.
TODO ~515 still needs: one objective (consented identity **or** style),
folder, trigger token, eval prompts. Trainer env remains
`2026-09-01_sdxl_lora_environment_recovery.md` (verified, unused).
Runbook bar: identity LoRA wants **20–30 varied** images of **one**
adult subject (`docs/SDXL_REALVISXL_LORA_RUNBOOK.md`).

## Decision menu (do not pick)

Same shape as the archive-destination menu. None of these is a complete
Kohya-ready set (paired `.png`+`.txt` at 1024, unique trigger, one
subject). `outputs/equal_shares/lora_datasets/` from the H3 runbook
**does not exist** on disk.

### A. Canonical identity sheets (ensemble + opening)

| | |
|---|---|
| **What** | `outputs/equal_shares/references/` — `ensemble_cast_master_v1.png` (five principals L→R: Kent, Avery, Doris, Ryann, Faith), plus Narrator / receptionist / visitor one / visitor two / opening-cast strips. Documented in `README_REFERENCES.md`. |
| **Count / size** | **8** images, **9.9 MB**. No `.txt` captions. |
| **Caption-ready?** | No. Sheets are review/IDENTITY-text aids, not a Kohya folder. Several characters share one strip. |
| **Consent** | Mixed. `alex_vale_source.jpg` is a **4032×3024 photograph** marked source for Kent. Other “new 2026-08-10” sheets are **crops of already-approved generated frames**, not model-regenerated. Using Kent/Alex Vale as an identity LoRA is a **real-person** decision. Ensemble strip is five people in one image — not one-subject. |

### B. Desktop first-appearance packs

| | |
|---|---|
| **What** | `Desktop\EQUAL_SHARES_FIRST_APPEARANCE\` — 18 character folders (Narrator, visitors, Doris, Kent, Avery, …). Each has `first_frame` / often `last_frame`, `prompt.txt`, and `identity/` copies of the masters in A. Voice-bootstrap packs, not a trainer set. |
| **Count / size** | **54** images, **102 MB**; **20** `.txt` (clip prompts, not Kohya captions). `ensemble_cast_master_v1.png` is **copied into 15 folders**. Unique master filenames: 6. |
| **Caption-ready?** | No. 1–2 frames per character plus a shared sheet. Far below 20–30 varied shots of one identity. |
| **Consent** | Same as A for identity sheets. Frames are **generated Equal Shares stills**. Equal Shares remains a paused profile — using them for SDXL is a separate product decision. |

### C. Equal Shares approved frames (volume, mixed cast)

| | |
|---|---|
| **What** | `outputs/equal_shares/frames/` — boundary/review stills for the story. |
| **Count / size** | **271** images, **479 MB**. **0** caption `.txt`. |
| **Caption-ready?** | No. Mixed characters, mixed shot scale. The H3 LoRA builder (`work/build_lora_dataset.py`) was meant to crop/caption from these; its output dir is gone. Would need a **new** crop+caption pass and a **named character**. |
| **Consent** | Generated story frames (not snapshots of living people), except any that were derived from the Kent photograph via the identity chain. |

### D. Generation-list thumbs (index, not training)

| | |
|---|---|
| **What** | `Desktop\EQUAL_SHARES_GENERATION_LIST\thumbs\` plus sibling prompt trees. |
| **Count / size** | **175** thumb images, **7.9 MB**. Pack also has hundreds of prompt `.txt` (script/H3 prompts, not per-image Kohya captions). |
| **Caption-ready?** | No. Thumbs are too small for SDXL 1024 identity (runbook: discard tiny faces). |
| **Consent** | Generated index art. |

### E. Voice-audition stills

| | |
|---|---|
| **What** | `Desktop\EQUAL_SHARES_VOICE_AUDITIONS\` — per-speaker folders. |
| **Count / size** | **17** images, **34 MB**; **17** `.txt` (audition notes/prompts, not LoRA captions). |
| **Caption-ready?** | No. Audio-bootstrap stills, ~1 image per speaker. |
| **Consent** | Generated character stills. |

### F. `Documents\me` (real photos)

| | |
|---|---|
| **What** | `A:\Users\rhine\Documents\me\` and `jpegmini_optimized\`. |
| **Count / size** | **5** images total (**4** in jpegmini), **6.7 MB**. **0** captions. |
| **Caption-ready?** | No. Count is far below 20–30. Would need more consented shots + captions. |
| **Consent** | **Real photographs of a real person.** Only valid as an identity LoRA if the operator explicitly consents to that use. Do not treat presence on disk as consent. |

### G. local_agent GUI uploads

| | |
|---|---|
| **What** | `local_agent/uploads/` — files dropped into the assistant UI. |
| **Count / size** | **132** images, **47 MB**. **0** captions. Unsorted. |
| **Caption-ready?** | No. Mixed dump, no trigger, no one-subject split. |
| **Consent** | **Unknown mix.** Do not assume generated-only or consented identity. |

### H. Comfy story output / H3 built LoRA set

`ComfyUI-Shared\output\story`: **6** images, **0.7 MB** — not a pack.
Documented Narrator H3 dataset (`outputs\equal_shares\lora_datasets\narrator\`,
40 crops) is **not on disk**.

## What is missing no matter which letter

1. Operator names **identity vs style**, **one subject**, **trigger**,
   **eval prompts**.
2. A folder of 20–30 varied 1024-class images with matching `.txt`.
3. Explicit consent if the subject is a real person (F, or Kent/Alex
   Vale in A).
4. GPU approval for the smoke run (next TODO item, not this one).

No kohya, no GPU, no file writes.
