# What the official ComfyUI H3 docs confirm, and what they change

Source: <https://docs.comfy.org/tutorials/video/minimax/minimax-h3>
Read 2026-08-15.

---

## Confirmed — keep doing these

**Reference by tag, in connection order.** `<Picture 1>`, `<Video 1>`, `<Audio 1>`.
Tags follow the exact order the inputs were connected, which is why
`audio_pass_config.json` fixes the `ref_audio` index order per clip and why `09B`
and `09C` differ despite both being Kent and Avery.

**Give every reference an explicit job.** The docs put it plainly: *"State which
reference drives which part of the shot (identity, style, motion, camera, voice).
Explicit assignments tend to work much better."* This is the REFERENCE JOBS block,
and it is officially endorsed rather than a local invention.

**Frame count.** *"The duration input snaps to the model's 17-frame-per-block
(17k+5) grid at 24fps."* Exactly the mod-17 rule already in `CLAUDE.md`.

**R2V uses a different checkpoint from T2V/I2V.** ref2va for reference work,
fl2va for first/last-frame work. Already the project's three-path table.

**Reference limits: 9 images, 3 videos, 3 standalone audio clips.** The project's
worst case is 3 speakers in `27E`, so it fits, but there is no headroom for a
fourth speaking character in one shot.

---

## New — worth acting on

### 1. `ref_image_size: max` may be the face fix

> `match` scales references down to the generation resolution for speed; **`max`
> keeps up to a 2048px short edge for stronger identity fidelity** at the cost of
> speed.

Every render in this project has used `match`, which throws away reference
detail at exactly the moment identity is being decided. Reference sheets are
already 1672×941, so `max` has real detail to use.

This is a one-word change and a plausible answer to the face-drift problem that
drove the whole 0.9 MP investigation. **Test it on one clip.**

### 2. An int8 ref2va checkpoint exists

The docs name the R2V model as `minimax_h3_ref2va_pruned_int8_convrot`. This
project uses `minimax_h3_ref2va_pruned_nvfp4` — a more aggressively quantised
variant. The 00J audit already flagged nvfp4 as the reason to doubt ref2va at
0.9 MP.

If the int8 ref2va is on disk, it is worth a comparison. **If it is not, it is a
multi-GB download and stays blocked on the hotspot** — do not fetch it without
agreement.

### 3. Official MiniMax prompt guides exist and have not been read

- Base modes (T2VA, I2VA, FL2VA, L2VA):
  `MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md`
- **Reference mode (R2V)**:
  `MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md`

The R2V guide covers *"the rewrite output structure, including subject
definitions, reference labels, and retention analysis, and how to assign each
reference a role."* "Retention analysis" is not a concept this project has been
using and may be directly relevant to the doubled-vocal problem — it is about
deciding what to keep from a reference and what to discard.

MiniMax also ships installable H3 skills including a prompt-writing skill.
Both guides are text files, so they are cheap to fetch.

### 4. Native canvas is ~1.0 MP, and this project deliberately runs below it

> *"For full-quality output, raise Megapixels to about `1.0` at 16:9, which
> yields roughly 1344×768: H3's native canvas."*

This project measured 1.0 MP breaking camera control on clip 11 and settled on
0.9 MP. **That empirical result stands** — it was observed directly. But it means
the project runs just under native, and the completion criteria in `CLAUDE.md`
still call for a 1344×768 master, so the film is upscaled slightly at assembly.

Worth knowing rather than changing. The camera failure was real.

### 5. Sage Attention warnings are expected

> *"MiniMax H3 runs some layers in other dtypes, so you may see 'Input tensors
> must be in dtype of torch.float16 or torch.bfloat16, using pytorch attention
> instead' messages. These are expected."*

If those appear in a render log, they are not a fault and not worth debugging.

---

## Nothing in the docs explains the doubled vocal layer

The docs do not mention voice duplication, echo, or reference leakage. So the
doubling remains unexplained by official guidance, and the live suspects are
unchanged:

1. the master reaching the model more than once (a second socket, or a reference
   video still carrying its audio track),
2. the master being long enough to supply material to replay, or
3. something the R2V "retention analysis" section addresses, which has not been
   read yet.

Reading `VIDEO_PROMPT_WRITING_GUIDE_ref_en.md` is the cheapest next step.
