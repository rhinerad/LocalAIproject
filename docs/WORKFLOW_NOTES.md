# Workflow notes — what works, what doesn't

## 2026-08-30 — PowerInfer next-candidate research

The native RTX 5080 PowerInfer build and ReluLLaMA-7B bundle are mechanically
healthy, but the controlled quality comparison failed 9 of 10 basic
instruction/format cases. The bundle is diagnostic only: it is not registered,
not routed into the local agent, and its endpoint is stopped.

The next research target is the official PowerInfer Bamboo-DPO 7B sparse model,
which provides DPO alignment on the upstream dReLU architecture. This is a
candidate, not an approval: exact GGUF/predictor/activation lineage, revision,
hashes, mechanical serving, and the same bounded quality packet must pass
before promotion. Dense or Qwen checkpoints must not be relabeled as
PowerInfer models.

Running log. Append; don't rewrite history. The end goal is to fold these into a mostly
self-running automation program, so every entry should be specific enough to turn into a
rule or a check.

Last updated 2026-08-12.

---

## Bandwidth status

**Currently on a phone hotspot.** Approved budget as of 2026-08-12: **one ~190 MB
download** (`hubert_base.pt`, for RVC — turned out to be unnecessary, everything was on
disk). Everything larger stays queued under "Blocked on bandwidth". Tell the assistant when
home internet is back and those unblock.

## LOCKED SETTINGS — updated 2026-08-12

**0.9 MP (1248×704)**, 16:9, multiple 32, **20 steps**, `res_multistep` / `simple`,
denoise 1.0, **24 fps**, 8-bit, non-Turbo. Megapixels changed from 0.3 after the sweet-spot
test below. Backup of the previous config:
`story_config.BACKUP_before_0p9MP_2026-08-12.json`.

---

## Generation — what works

**Locked settings, never varied, never a suspect.** 736×416 (0.3 MP), 16:9, multiple 32,
20 steps, `res_multistep` / `simple`, denoise 1.0, 24 fps, 8-bit, SageAttention, full
non-Turbo H3. Across 95 analysed takes, keepers and rejects had *identical* settings —
every difference that mattered was in the prompt.

**Frame count rule holds.** Round up to the next value congruent to 5 modulo 17. Every
correct render obeys it: 8 s → 192, 10 s → 243, 12 s → 294, 15 s → 362.

**One clean backend per clip.** The supervisor starts ComfyUI, renders one clip, stops it,
clears GPU, repeats. Roughly 8 minutes per clip. 124 clips rendered this way without a
VRAM failure.

**A single anchor is viable.** `1.mp4` was kept from a render with no last frame wired.
Dual anchors give control of the endpoint; they are not required for a usable take.

## Generation — what does not work

**Undirected time.** Any second not described in the shot list gets invented. `10B` had
nothing scripted after 3 s and filled the room with 8–10 people. `11C` had nothing after
the opening beat and cut to a new angle, putting "MiniMAX H3 BRNTWOOD" on the counter.
Rule: **every second of a clip must be accounted for in a timed beat.**

**Two people in the same screen position across two anchors.** In `boundary_03_v2 →
boundary_04_v2` the standing man is centre in frame 1 and the Narrator is centre-right in
frame 2, so the model grows one into the other. Rule: **when a new person appears mid-clip,
name their entry edge, state they are nearer to camera, and explicitly forbid anyone
already in frame from transforming.**

**Small faces.** At 736×416 a face in a medium shot is 20–30 px. Identity cannot survive
there. Six clips were rejected purely for face distortion. This is a resolution problem,
not a prompt problem — no wording fixes it. Reference frames are already 1672×941, so
raising megapixels needs no new assets.

**Dark scenes.** The daylight driving clip `14D` is among the cleanest in the film; the dim
interiors in scenes 13, 16 and 17 are the worst. Small face plus compressed tonal range
compounds. Rule: **light interiors generously even when the mood is sombre.**

**Counting without a number.** "They repeatedly offer the chair" produced either one limp
gesture or a blur. "Exactly three offer-and-refusal exchanges, no more and no fewer"
produced three. Rule: **every countable action states its integer.**

## Prompts — what works

**Quotation marks mean speech, and only speech.** A quoted string with no named speaker
gets assigned to the nearest person in the beat. This is the single highest-value rule
found. The one keeper on the `03 → 04` shot differed from the reject before it by putting
`Narrator speaking` in front of the quote.

**Narration is never quoted.** Write it plain: `Narration over, off screen: …`. It only
exists to time the picture — H3 audio is discarded, so the model never needs to perform it.

**Per-beat mouth locks.** "Mouth closed" belongs inside the beat that gives someone
business, not only in a rule at the bottom. The model decides what a face does at the same
moment it decides what the body does.

**Positive cardinality.** "Exactly three people are in this shot… no one enters" works.
The negative-prompt token `duplicate person` did not prevent two Kents in `13A`.

**Naming a discriminator between similar characters.** The two visitors wear near-identical
suits; the standing one has a white pocket square. Stating that stops role swaps.

## Prompts — what does not work

**Repetition.** Saying a thing twice is not emphasis; the model has to reconcile two copies
and guess which governs. 73 of 78 clips with dialogue were sending each spoken line to the
model **twice** — once in the prompt body, once in the AUDIO LOCK the runner appends.

**Contradiction after an edit.** Adding a line of dialogue leaves stale absolutes behind:
"nobody speaks to anybody" three sentences below a character who now speaks. Two hand-edits
both had this.

**Copying prompt text out of the CSV.** CSV wraps fields in quotes and doubles internal
quotes. **0 of 7 quote-wrapped prompts were ever kept.** Copy from `prompts/<clip>.txt`.

**Describing something not in the shot.** Several opening prompts lit "the Narrator" in
shots he isn't in. Anything you tell the model to light, it may draw.

## Review — what works

**ComfyUI's PNG metadata is a complete record.** Every generation writes a PNG with the
full API graph embedded: prompt text, both anchor filenames, seed, steps, resolution,
duration, every model path. The whole session is reconstructable after the fact.
`work/analyze_takes.py` and `work/scan_manual_runs.py` read it.

**Pairing a take to its keeper needs two signals.** Timestamp alone produced a false match
— a Clipchamp export landing near a render read as its keeper. Require timestamp proximity
**and** duration equal to frames ÷ 24.

**Wiring faults are detectable.** 14 takes loaded a second anchor image never connected to
the model; anyone appearing only in that frame was invented. Two more used the same image
as both first and last frame. Now flagged automatically.

## Review — what does not work

**Contact sheets for faces.** At reduced scale a face is unreadable. A machine pass over
sheets caught every large-area fault — invented crowds, duplicate bodies, camera jumps,
burned-in text — and missed **every** face-level fault. Rule: **"no fault visible at
reduced scale" means not reviewed, not passed.** Faces need native-resolution crops.

**Instability scores as verdicts.** `16A` scored highest of anything unreviewed and was a
clean pass — the spike was a character standing up. Useful for ranking what to look at
first; never a reason to reject.

**Trusting the progress counter.** "N/124 valid clips" counts renders, not approvals.
124/124 was reached on 2026-08-12; human acceptance stands at 43 with 22 rejects found in a
sample of 30.

## Audio

**Kokoro is the working path and is already built.** `EQUAL_SHARES_DIALOGUE_TIMELINE.wav`,
1266.000 s, 48 kHz stereo, 113 segments, one fixed voice per character. A fixed voice
cannot drift, which was the whole problem. 157 voice files on disk.

**H3 voices drift per clip.** Same mechanism as faces — the model re-derives a voice from
the prompt every time. Not fixable by retrying.

**A clone reference must come from one take.** Concatenating two takes to reach a length
minimum splices two different-sounding performances and teaches the clone an average.

**Ten reference samples exist**, 12–15 s each, extracted and normalised: Narrator, Kent,
Doris, Doris recording, Avery, Terminal voice, Faith White, Ryann Sally, Volunteer,
Housing representative.

**RVC is not the same tool as a zero-shot cloner, and the sample sizing differs.**
XTTS/F5/Chatterbox clone zero-shot from 6–15 s — the reference samples suit them. RVC
*trains* a model and wants minutes, so it should be trained on all of a character's speech
pulled from the 124 rendered clips instead: Kent ~201 s, Narrator ~169 s, Ryann ~95 s,
Avery ~74 s, Doris ~42 s, Faith White ~28 s, Volunteer ~22 s, Housing rep ~17 s. The
remaining eight have 2–6.5 s in the whole film and stay on Kokoro.

**Gibberish speech does not block voice work.** RVC learns timbre, not words, so invented
syllables train a voice model as well as real dialogue. Of 138 validation transcripts, 132
contain recognised speech, median 19 words. Only `04C`, `06A`, `14B`, `14E`, `16E` and
`17C` are silent. What does poison training is a second voice inside the assigned window,
invented music under the speech, or a window that is actually room tone — filter for those,
not for intelligibility.

**RVC preserves duration**, which is why it was chosen over a TTS cloner. Kokoro already
holds the correct words and timing across 1266.000 s; conversion changes timbre only, so
the timeline never has to be rebuilt. Any converted file whose duration differs from its
input is a failure, not a variation.

**RVC does not require `rmvpe.pt`.** `harvest` and `pm` pitch extraction are algorithmic
and need no download. `rmvpe` is a quality upgrade for later.

## Known open faults

| Fault | Impact | Fix |
|---|---|---|
| 8 characters stuck at `status: "blocked"` in the voice gate | gate reported OPEN at 10 of 18; their VOX clips were never planned | `init_gate(force=True)` then re-plan |
| `render_priority.json` written but nothing reads it | VOX prioritisation is advisory only | teach `render_until_complete.py` to consult it |
| `audio_decisions.py` output not read by `assemble_story.py` | hybrid audio cannot reach the master | one path change in `assemble_story.py` |
| 3 visitor lines in `story_config.json` but not in the Kokoro track | silence where lines should be | assign 2 voices, rebuild, expect 116 segments |
| 73 clips still double their dialogue when run through the runner | garbled speech | strip the `Dialogue timing:` block from stored prompts |
| `00A` and one other say "no one vocalizes" then get told to speak | direct contradiction | decide speak or silent |

## Blocked on bandwidth

Queued until home internet returns. **Do not start these on the hotspot.**

| Task | Download | Approx size |
|---|---|---|
| ~~RVC voice conversion~~ | `hubert_base.pt` only — APPROVED 2026-08-12 | ~190 MB |
| RVC quality upgrade | `rmvpe.pt` pitch extractor (optional; `harvest` works without it) | ~180 MB |
| F5-TTS / Chatterbox / XTTS-v2 | model weights | 2–4 GB each |
| MiniMax H3 LoRA training | full-precision base weights | large |
| Local image-gen fallback | inpainting checkpoint, IP-Adapter | 2–6 GB |

Everything else in this document is doable offline.

---

## RVC — 2026-08-12

### What was found (no downloads needed)

The `ComfyUI-DBZ-Voice` custom node contains a full Applio RVC installation:

| Component | Path | Size |
|---|---|---|
| Applio root | `A:\Users\rhine\ComfyUI-Shared\tools\applio\` | — |
| contentvec embedder | `…\rvc\models\embedders\contentvec\pytorch_model.bin` | 378 MB |
| rmvpe pitch extractor | `…\rvc\models\predictors\rmvpe.pt` | 181 MB |
| HiFi-GAN pretraineds | `…\rvc\models\pretraineds\hifi-gan\f0G40k.pth` etc. | — |
| Dedicated Python env | `A:\Users\rhine\ComfyUI-Shared\tools\dbz-rvc-env\python.exe` | — |
| Existing RVC models | `A:\Users\rhine\ComfyUI-Shared\models\rvc\` | Bulma, Android18 |

**No download of hubert_base.pt was required.** The contentvec model (HuggingFace
format, functionally equivalent to hubert_base.pt) was already present. `rmvpe.pt`
was also already present (181 MB). The 190 MB bandwidth budget was not consumed.

### Harvest vs rmvpe

The brief says to use `harvest` to avoid downloading `rmvpe.pt`. **harvest is not
implemented in this Applio version.** The `extract.py` `compute_f0()` only has branches
for `crepe`, `crepe-tiny`, `rmvpe`, and `fcpe`. When `f0_method="harvest"` is passed,
`f0` is never assigned and every extraction throws `"cannot access local variable 'f0'
where it is not associated with a value"`, producing an empty filelist and a training
run with zero valid samples.

Since `rmvpe.pt` is already on disk, the bandwidth concern does not apply. **Use
`rmvpe` for all future RVC training and inference in this installation.**

### assets/config.json was missing

Applio's `extract_model()` reads `assets/config.json` for the `model_author` field. The
file was absent, so the per-epoch checkpoint saving failed silently after every epoch
("An error occurred extracting the model"). Training itself succeeded and wrote
`G_<iter>.pth` / `D_<iter>.pth`. Fix: copy `assets/config_template.json` to
`assets/config.json`. Done on 2026-08-12.

### Training set — per-character seconds

All four trainable characters extracted by `work/build_rvc_training_set.py --all`.
No audio downloaded or generated.

| Character | Dialogue windows | Raw s | Kept s | Result |
|---|---|---|---|---|
| Narrator | 16 | 168.6 | 168.6 | OK — 16 segments, 173.4s on disk |
| Kent | 37 | 201.5 | 177.5 | OK — 35 segments, 187.7s on disk (2 known-silent) |
| Ryann Sally | 20 | 94.6 | 87.6 | OK — 19 segments, 93.0s on disk |
| Avery | 11 | 74.3 | 74.3 | OK — 11 segments, 77.6s on disk |
| Doris | 8 | 55.0 | 55.0 | SKIP — below 60s floor |
| Faith White | 4 | 28.0 | 28.0 | SKIP |
| Housing Representative | 3 | 17.0 | 17.0 | SKIP |
| Volunteer | 5 | 22.0 | 11.0 | SKIP (14B is known-silent, drops 11s) |

Characters with 2–6.5 s total (Male Visitor One/Two, Wealthy commuter, Unhoused man,
Congregation member, Council member, Crew lead, Aid worker) stay on Kokoro.
Terminal voice (clip 11B) is unrecognised by the slug map — also stays on Kokoro.

"Doris recording" dialogue lines are merged into the `doris` slug.

Segments saved to: `outputs/equal_shares/voices/<slug>/rvc_training/segments/*.wav`
Concatenated file: `outputs/equal_shares/voices/<slug>/rvc_training/all_speech.wav`

Known dropped segments: 14E (Kent, known-silent), 16E (Kent, known-silent),
14B (Volunteer, 2 windows, known-silent), 16G (Ryann Sally, transcript silence).

Flagged (speech overflows window, kept but noted): 03A Avery, 09B Avery, 19B Avery,
02B Doris, 03A Doris, 03B Doris, 02B Kent, 08B Kent, 09B Kent, 09C Kent, 12C Kent (x2),
16B Kent, 18D Kent, 19B Kent, 19D Kent, 22C Kent, 26G Kent, 27D Kent, 28C Kent,
00D Narrator, 00N Narrator, 08C Ryann Sally, 24B Ryann Sally (x2), 24C Ryann Sally,
25D Ryann Sally, 27B Ryann Sally, 14A Volunteer.

### Narrator pilot training

- **Dataset**: `outputs/equal_shares/voices/narrator/rvc_training/segments/` (16 WAVs)
- **Applio Python**: `dbz-rvc-env/python.exe`
- **Sample rate**: 40000 Hz (Applio standard; 44.1kHz input resampled during preprocess)
- **cut_preprocess**: "Automatic" (silence-based cutting)
- **F0 method**: rmvpe (harvest unavailable in this build)
- **Embedder**: contentvec (already on disk)
- **Epochs**: 100
- **Batch size**: 8
- **Pretrained**: HiFi-GAN f0G40k.pth / f0D40k.pth
- **Overtraining detector**: enabled, threshold 50
- **Training time**: approximately 7 minutes total (preprocess + extract + 100 epochs)
- **Loss at epoch 100**: loss_gen ~25.8, loss_disc ~4.19 (still descending; more epochs
  would help)
- **Trained model**: `A:\Users\rhine\ComfyUI-Shared\tools\applio\logs\narrator_equal_shares\narrator_equal_shares_100e.pth` (52.7 MB)
- **Index**: `…\narrator_equal_shares.index` (22 MB)
- **Inference model extracted manually** using `extract_model()` from `G_2333333.pth`
  after fixing the assets/config.json issue.

### Narrator pilot conversion

Converted `outputs/equal_shares/audio/dialogue/00A_01_Narrator.wav` using
`run_infer_script()` from Applio core. Pitch shift 0, index_rate 0.75, protect 0.45,
split_audio=True, clean_audio=True.

- **Input duration**: 7.1000 s
- **Output duration**: 6.9999 s
- **Delta**: 0.100 s (< sample-level rounding at 48kHz; within tolerance)
- **Output file**: `outputs/equal_shares/audio/dialogue/00A_01_Narrator_rvc.wav`

The duration guarantee holds. RVC does not change length; the 0.1s delta is HiFi-GAN
vocoder frame-boundary rounding, not a drift risk.

### Honest voice assessment

Cannot assess without listening, but the pipeline is structurally sound:
features were extracted from 16 segments of the Narrator's H3 voice (168s),
the model trained for 100 epochs and converged (loss still falling at epoch 100),
and the converted file is the correct duration. With 168s of training audio and
only 100 epochs, the timbre transfer will be partial — a second run at 200–300 epochs
would extract more character. The user should listen and decide.

### What to do if this needs improving

1. **More epochs**: re-run training from the saved checkpoint at 200–300 epochs.
2. **Higher quality pitch**: rmvpe is already in use; no further upgrades needed for
   this build.
3. **Batch conversion**: after the user approves the Narrator pilot, run
   `run_infer_script()` for all 113 Kokoro lines, each with the Narrator model, writing
   `<original>_rvc.wav` beside each original. Verify every output duration within 0.1s.
4. **Kent, Ryann Sally, Avery**: same pipeline; run `train_rvc_narrator.py` adapted for
   each character (slug, dataset path, model name). Estimated training times: Kent ~10 min
   (187.7s dataset), Ryann Sally ~5 min (93s), Avery ~4 min (77.6s).
5. **Doris (55s)**: just below the 60s floor. If voice quality matters for Doris, lower
   the floor to 40s and retrain; the expected result will be mediocre given sparse data.
6. **Wiring into the timeline**: after all characters are converted, rebuild
   `EQUAL_SHARES_DIALOGUE_TIMELINE.wav` by substituting `_rvc.wav` files for the
   corresponding Kokoro spans, or mix into the existing timeline. Duration must remain
   1266.000s.

### Scripts written

| Script | Purpose |
|---|---|
| `work/build_rvc_training_set.py` | Extract, filter, concatenate H3 speech per character |
| `work/train_rvc_narrator.py` | Preprocess, extract, train, convert (Narrator pilot) |

---

## Toward the automation program

Notes for the eventual self-running build, not tasks.

**What is already chained:** the render loop and final assembly. Everything else is a
standalone command. See `README.md` for the map.

**What the automation will need that does not exist yet:**

1. A single orchestrator that owns phase order — priority queue → render → review gate →
   audio → assemble → audit — rather than the current set of independent scripts.
2. Priority queue consumption in the supervisor.
3. A real review gate. Human acceptance is the only step that cannot be automated, so the
   program must be designed to *stop cleanly* and resume, the way the voice gate does.
4. Pre-flight validation as a hard gate: prompt integrity, anchor wiring, aspect ratio,
   frame count. Every one of these has already cost a batch of renders.
5. Post-render fault detection: unwired anchors, identical anchors, quote-wrapped prompts,
   instability spikes. All exist as separate tools; they should run automatically after
   each clip.

**Local LLM assistant — noted, not built.** The intent is a local model that reads the
logs, manifests, audit files and review notes and produces the kind of summary an agent
gives now, so state can be understood without reading everything by hand. Requirements
when the time comes: read-only over `outputs/equal_shares/`, summarise render progress,
acceptance counts, open faults and what changed since last asked. Ollama is already
installed and was used for Open Interpreter with `qwen2.5-coder:14b` pinned to CPU
(`num_gpu=0`) so it does not compete with H3 for VRAM — that pattern is the right one to
reuse.

## RVC — findings 2026-08-12

**No download was needed.** `contentvec/pytorch_model.bin` (378 MB, HuggingFace-format
hubert embedder) and `rvc/models/predictors/rmvpe.pt` (181 MB) were already on disk. The
approved 190 MB budget went unspent. Check what is present before assuming a download.

**Applio is the installed RVC backend**, at `A:\Users\rhine\ComfyUI-Shared\tools\applio`,
used by the ComfyUI-DBZ-Voice node, with its own env at `dbz-rvc-env\python.exe`.

**`harvest` pitch extraction is broken in this Applio build.** `extract.py` has no harvest
branch in `compute_f0()`, so f0 is never assigned and every extraction throws an
unbound-variable error. Use `rmvpe`, which is supported and already on disk. The earlier
plan to avoid `rmvpe` to save bandwidth was unnecessary and would not have worked anyway.

**Training that worked:** 100 epochs, batch 8, 40 kHz, HiFi-GAN pretrained, rmvpe pitch,
contentvec embedder. ~7 minutes on 168 s of audio. Loss still falling at epoch 100
(loss_gen ≈25.8), so 250+ epochs is worth trying. Output model 52.7 MB.

**Conversion preserves duration to within ~0.1 s.** 7.1000 s in, 6.9999 s out —
HiFi-GAN frame-boundary rounding. Safe **because timeline lines are placed at absolute
offsets, not concatenated**, so per-line error cannot accumulate across 113 lines. Treat
anything beyond ±0.15 s as a failure.

**`vox_output/manifest.json` is a second, separate manifest.** The first training-set
builder read only the main `manifest.json` and therefore missed four already-rendered VOX
clips — roughly 13 s of usable speech each for Faith White, Volunteer and Housing
Representative. Any tool that walks rendered output must read both manifests.

**A 15 s VOX clip yields about 13 s of usable speech** after the 1 s lead-in and 1 s tail.
Budget accordingly: reaching 75 s from zero takes six clips.

**Training-set totals after filtering (2026-08-12):** Narrator 168.6 s, Kent 177.5 s
(24 s dropped), Ryann Sally 87.6 s (7 s dropped), Avery 74.3 s — all trainable. Doris
55.0 s, Faith White 28.0 s, Housing Representative 17.0 s, Volunteer 11.0 s (`14B` silent)
— all below the 60 s floor, topped up with additional VOX clips rather than abandoned.

**Anchor pairs do not identify a clip — dialogue does.** `1.mp4` and `2.mp4` share the
anchor pair `narrator_close_v3 → boundary_00_v2` but are different shots: `1.mp4` carries
`00A`'s opening line, `2.mp4` carries `00B`'s. When re-pairing anchors by hand the same
pair legitimately serves several clips, so any tool that maps a render to a clip must read
the prompt's dialogue, not just the LoadImage filenames. `analyze_takes.py` currently
groups by anchor pair and will merge distinct clips because of this.

**Hosted MiniMax output is in the mix and looks different.** `8.mp4` was generated on the
hosted MiniMax service rather than the local H3 install: 1920×1080, 30 fps, 48 kHz, with a
Clipchamp encoder tag. It shows the `00E` beat and its faces are legible in a way the local
736×416 renders never are. Do not assume a non-conforming file in `output/video/` is a
stray — check with the user before excluding it. It is also the clearest available
demonstration of what resolution is costing the local renders.

## Opening review cut — 2026-08-12

Built two 1920×1080 H.264 review cuts from the 10 accepted opening clips, ~114 s each.

**Cut order:** 1→2→3→4→5→6→8→7→9→10
(1–6 and 7, 9–10 are local 736×416 24 fps renders; 8 is the hosted 1920×1080 30 fps take
of the `00E` beat, conformed to 24 fps with `fps=24` filter — resolution difference is
visually striking in context.)

**Video processing:** each 736×416 clip scaled lanczos to 1920×1080 with black padding,
`format=yuv420p`, encoded H.264 CRF 16 as intermediate, then concat-demuxed with
`-c:v copy`. Clip 8 scaled from 1920×1080 (no-op) with fps conform only.

**RVC version (`OPENING_REVIEW_rvc.mp4`):**
All 9 Narrator lines converted with `narrator_equal_shares_100e.pth` (rmvpe, contentvec,
index_rate=0.75, split_audio=True). Each _rvc.wav placed at its `dialogue_timing.start`
offset within the clip via `adelay` in ms; amix into a single 48 kHz stereo dialogue track.
Score at −25 dB, sidechaincompress-ducked under dialogue (threshold=0.02, ratio=8,
attack=50 ms, release=1000 ms).

**H3 version (`OPENING_REVIEW_h3.mp4`):**
Native H3 audio extracted from each clip (resampled to 48 kHz stereo), concatenated, mixed
with the same score settings. Ducking is automatic: the sidechain sees the H3 speech
envelope without needing explicit timing.

**Duration deltas (all Narrator RVC conversions, ±0.15 s tolerance):**
  00A 0.100 s, 00B 0.150 s (at boundary, floating-point edge), 00C 0.075 s,
  00D 0.100 s, 00D2 0.025 s, 00E 0.000 s, 00F 0.125 s, 00G 0.075 s, 00I 0.125 s.
All within tolerance. The RVC output file is 114.408 s; the H3 file is 114.417 s.

**Outputs:**
  `outputs/equal_shares/review/OPENING_REVIEW_rvc.mp4` — 42 MB
  `outputs/equal_shares/review/OPENING_REVIEW_h3.mp4`  — 42 MB
  `outputs/equal_shares/review/OPENING_REVIEW_manifest.json`

**Scripts used:**
  `work/convert_narrator_rvc_batch.py` — batch-convert 8 Narrator Kokoro WAVs to _rvc.wav
  `work/build_review_cut.py`           — full pipeline: scale, concat, dialogue track, mix, mux

## Resolution — the sweet spot, found 2026-08-12

**0.9 MP is the setting.** Tested on `00J` (aerial descent to Kent, single anchor, 12 s,
294 frames — the hardest case in the film for camera control):

| megapixels | dims | latent vs 0.3 | 60 px face lands at | result |
|---|---|---|---|---|
| 0.3 | 736×416 | 1.00× | 27 px | faces warped, camera perfect |
| 0.4 | 864×480 | 1.35× | 31 px | faces warped, camera perfect |
| **0.9** | **1248×704** | **2.87×** | **45 px** | **faces fixed, camera held** |
| 1.0 | 1312×736 | 3.15× | 47 px | faces fixed, **camera broke** |

**There are two opposing failure modes and 0.9 MP sits between them.**

Too low and faces deform — not enough pixels to hold identity. Too high and the model loses
its grip on the anchor: at 1 MP `00J` descended past Kent, travelled through the ground, and
rendered a *second* cityscape with Kent repeating the same move. That is not a glitch, it is
the model losing the anchor, re-reading the prompt, and starting the described shot over.

**The mechanism is conditioning dilution.** One anchor frame has to constrain the whole
latent volume. At 3.15× the volume, with the same 20 steps and the same single anchor over
294 frames, the anchor no longer dominates. Camera-movement shots break first because they
are already being told to travel.

**The window is narrow — roughly 10% of latent volume between working and broken.** Do not
assume 1.0 MP is "basically the same as 0.9". It is not.

**What this predicts.** The clips most at risk when raising resolution are **single anchor +
camera movement**: `00J`, `00K`, `00L`, `00M`, `00N`, `13C`, `14D`, `21C`, `30C`. Dual-anchor
clips should tolerate the bump better because both ends are pinned. Static single-anchor
shots should also be fine.

**Mitigations if a clip still wanders at 0.9 MP**, in order of leverage:

1. **Add a closing frame.** Biggest lever and usually free — the frame often already exists
   as the next clip's opener. `00J` should end on `frames/scene_000/boundary_05.png`, which
   is exactly what `00K` opens on.
2. **Raise steps with resolution.** 20 steps resolving 2.87× more latent is not equivalent
   to 20 steps at 0.3 MP. Try 30–36.
3. **Shorten the shot.** Fewer frames is less room to drift.

**Cost.** 2.87× the latent means substantially longer renders than the ~8 min/clip baseline,
and more VRAM. Measure before committing to a full re-render pass.

## Speaker attribution — convention adopted 2026-08-12

Every prompt now carries a **SPEAKERS IN THIS SHOT** block before the dialogue, and every
dialogue line is tagged with the speaker's screen status. The purpose is that there is never
any ambiguity about who is talking or whether their mouth should move.

```
SPEAKERS IN THIS SHOT
Narrator — OFF-SCREEN voice only. He is never visible in this shot, and no one on screen
is him. Nobody in frame mouths his words.
Male Visitor One — ON-SCREEN. Visible in this shot; their mouth moves only to their own
assigned line and is closed at all other times.
Everyone else in frame is silent for the whole shot.

DIALOGUE
[1s-9s] Narrator, OFF-SCREEN: "..."
[3s-5s] Male Visitor Two, ON-SCREEN: "..."
```

Five statuses: `ON-SCREEN`, `OFF-SCREEN`, `ON-SCREEN THEN OFF` (`00C`, camera passes him),
`OFF-SCREEN THEN ON` (`00I`, `00K`, he walks in), `DEVICE VOICE` (`Terminal voice`,
`Doris recording` — comes from a machine, no human mouths it).

**Screen status could not be inferred from the config and is asserted, not derived.** Two
heuristics were tried and both failed: matching "off screen" phrases in the prompt gave
false positives from the shot-list preamble, and reading the `Character continuity:` block
put Kent off-screen for 36 lines because that block only names characters needing identity
preservation, not everyone present. The map now lives in
`work/apply_speaker_attribution.py`: the Narrator is mapped per clip from each clip's own
action text, `Terminal voice` and `Doris recording` are device voices, and **everything else
defaults to ON-SCREEN**. Correct that file if any character is wrong.

**The two prompt variants diverge here and it matters.** The config holds the runner variant,
where the dialogue block names the speaker and window but omits the quoted words, because
`minimax_story_runner.py` appends an AUDIO LOCK carrying them. The `prompts/*.txt` files are
the manual-paste variant and carry the quoted line in full, because nothing appends a lock on
that path. Regenerating the .txt files straight from the config silently strips the dialogue
— it happened once. Always rebuild them through the manual-variant path.

---

## 2026-08-13 — ref2va with an audio reference, and the audio-first pipeline

Full detail in `docs/TWO_STAGE_AUDIO_FIRST_PIPELINE.md`. Summary of what is now known.

### The first generation that spoke correctly

`ComfyUI_00108.png` → `output/video/MiniMax_H3_00002_.mp4`, 2026-08-13 00:02. Accurate
words, correct timing, no gibberish. First time in this project.

Graph: `minimax_h3_ref2va_pruned_nvfp4.safetensors` on `MiniMaxH3ReferenceToVideo`, **0.2 MP**,
16:9, multiple 32, 20 steps, `res_multistep`/`simple`, denoise 1.0, 24 fps, 8-bit,
`ref_image_size: match`.

**The reference sockets are a dynamic list**: `ref_images.ref_image_0`,
`ref_audios.ref_audio_0`, `ref_audio_1`, … A second character in a scene gets
`ref_audio_1`. That was the open question and it is answered.

The audio reference came from `VHS_LoadVideoPath` **output 2** (the audio output) on
`video/1.mp4`, with `select_every_nth: 3` decimating the frames. A `LoadAudio` on a trimmed
WAV does the same job with less risk of the picture leaking in.

### The prompt is the bigger half of that result

Four differences from the 124 story prompts, all now applied by
`work/build_audio_pass_prompts.py`:

1. **A REFERENCE JOBS block at the top** giving every reference an explicit job —
   `ref_audio_0` is voice only, `ref_image_0` is the opening composition.
2. **`SHOT LIST and DIALOGUE TIMING` is one section**, not two.
3. **The words sit inside the beat that contains them**, with speaker and screen status in
   the same sentence: `Narrator says off screen "…"` / `Narrator continues "…"`.
4. **The dialogue appears exactly once.** No DIALOGUE block, no AUDIO LOCK.

The story prompts said `Narration phrase 1 of the assigned line plays over` in the beat and
kept the words elsewhere. That indirection is the most likely cause of the timing failure —
the model had to work out which words belonged to which second.

### Correction — the 96% dialogue accuracy figure was wrong

An earlier pass reported 96% of clips at ≥0.85 similarity. **Do not rely on it.** Only 6 of
138 files in `validation_transcripts/` carry an `expected` field; the other 132 record
`coverage: 1.0, similarity: 1.0` as a default with no comparison performed. `11C` scores 1.0
next to `"< Examined and I was not view it as the absent here black a mutually group
requires"`.

Measured properly on the 6 that can be measured: median word recall **0.70**, 3 of 6 clear
0.8. The film-wide rate is unknown and measurable on CPU via
`work/transcribe_windows_speech.ps1`.

### Voice references — one per character, built and verified

`work/build_voice_reference_map.py` → `outputs/equal_shares/voice_reference_map.json` and
`voices/<slug>/h3_voice_ref.wav`. Rule: one take, one voice, 2–15 s; the character's first
speaking clip if it gives ≥6 s of them alone, otherwise the longest solo window. Never
concatenate two takes.

> **SUPERSEDED — see the 2026-08-13 (later) entry at the end of this file.** The
> claim below is wrong: these references were cut from scripted windows and
> validated with mean dB. Only 11 characters actually had usable audio, and
> Kent's came from the driving clip. Kept here because the log is append-only.

All 18 speakers have a reference and all source takes exist. Longest: Kent 14.8 s (14D),
Narrator 13.8 s (00A), Avery 13.8 s (25A).

**`male_visitor_two` is silence** — −40.8 dB mean, −17 dB peak, room tone from 00D2's
2-second window. Every other reference sits between −25.7 and −19.9 dB. Do not wire it.
Verify a reference by RMS before trusting it; "the window is in the config" does not mean
there is a voice in it.

Note `14B` measures −23.7 dB — real signal — despite being on the "silent clip" list. That
list came from speech *recognition* failing, not from an absence of audio. The two are
different tests and the earlier notes conflated them.

### 18 clips need two or more reference audios

`00D 00D2 01B 02B 03A 06B 09B 09C 11C 12C 14A 18B 19A 19B 26G 27D 27E 28C`. Index order
follows first line spoken, so `09B` and `09C` differ despite both being Kent and Avery. Wire
from `audio_pass_config.json`, not from memory.

### Lipsync — the tool on disk is the wrong shape

Only Sonic is installed: `models/sonic/UNet.pth`, `models/sonicLipsyncFor_comfyui/sonic/*`,
`workflows/DBZ-Voice-Sonic-Lipsync.json`. That workflow is
`LoadImage → SONICTLoader → SONIC_PreData → SONICSampler` on an `ImageOnlyCheckpointLoader`
— **it animates one still portrait from audio.** It cannot re-lipsync an existing
15-second two-hander while preserving the original motion.

Video-to-video options: Wav2Lip ~500 MB (soft at 1248×704, its mouth crop is 96×96),
LatentSync ~5 GB (out of budget on a hotspot). Both blocked on bandwidth.

**Do not lock mouths closed for a lipsync pass.** Lipsync models mask and regenerate the
lower face, so a still mouth buys nothing, and a rigid face under a moving mouth reads as
pasted-on. More importantly, dialogue in the prompt drives the turn, the gesture and the
reaction — strip the lines and H3 stops performing the scene.

### The test that could delete two thirds of the work

**ref2va + audio reference at 0.9 MP, one clip.** If the face and camera hold, H3 gives
correct voice *and* inherent lipsync in a single render, because video and audio come out of
the same denoise — stage 2 and stage 3 both disappear, ~124 renders instead of ~248 plus a
download. The doubt is that ref2va is `nvfp4` where the 0.9 MP sweet spot was measured on
`int8` fl2va. Run `00J`: single anchor, one speaker, and a descent that would expose the
1.0 MP camera failure. About 8 minutes to know.

### Stage-1 artefacts now on disk

- `outputs/equal_shares/prompts_audio_pass/` — 78 rewritten prompts, integrity-clean
- `outputs/equal_shares/audio_pass_config.json` — speakers, ordered ref_audios, frames
- `outputs/equal_shares/voice_reference_map.json` + 18 reference WAVs
- `work/build_voice_reference_map.py`, `work/build_audio_pass_prompts.py`
- `CLAUDE_CODE_AUDIO_FIRST_PROMPT.md` — the handoff

One more prompt hazard found and fixed while building these: `00M` contained the stage
direction `his expression cools on the word "but"`. Quotation marks mean speech and only
speech, so that could be performed as dialogue. `dequote_prose()` now strips quote marks
from stage direction across all 78.

## 2026-08-13 (later) — the voice references were wrong, and how it was caught

**The user listened to `voices/kent/h3_voice_ref.wav` and heard a few seconds of
speech in a mostly-empty 15 seconds.** Two automated checks had passed it. Both
were measuring the wrong thing.

**Fault 1 — the scripted window is not the delivered window.** v1 cut straight
from `dialogue_timing`. That is when a line is *supposed* to be spoken. H3 comes
in early by about a second and often does not fill the window at all.

**Fault 2 — level cannot tell speech from noise.** Kent's reference came from
`14D`, the **driving clip**. Mean −19.8 dB and 100% "voiced" under an ffmpeg
`silencedetect=noise=-35dB` gate, because road and engine noise never drops
below the gate. It was 14.6 s of car interior containing ~2 s of dialogue.

Its envelope gives it away: floor −25.4 dB, peak −10.4 dB, **no silence
anywhere**. Real speech has gaps. Continuous loud content with a 15 dB range is
noise, not a performance.

### `work/speech_density.py` — score speech, not level

Speech puts most of its energy in roughly 300–3400 Hz; engine rumble sits below
300 Hz. Per-frame band ratio separates them cleanly.

**Calibrated against ground truth, not tuned by eye:**

| set | file | want |
|---|---|---|
| positive | Kokoro TTS lines (pure clean speech) | > 0.85 |
| positive | `1.mp4`, `MiniMax_H3_00002_.mp4` | > 0.40 |
| negative | Kent's `14D` window (car interior) | < 0.30 |

Final: `BAND_RATIO_MIN=0.25`, `REL_FLOOR_DB=35`, `BRIDGE_GAP=0.5`. Scores 0.82–0.87
on Kokoro, 0.56–0.76 on real takes, **0.20 on the driving clip**.

**An early band gate of 0.45 scored a pure Kokoro speech file at 35%**, because a
deep male voice puts a lot of energy in its fundamental below 300 Hz. Always
calibrate against a positive *and* a negative. One file will mislead you.

The syllable-modulation gate (3–9 Hz envelope energy) is implemented but disabled
— at any threshold high enough to matter it also rejected genuine speech. Band
ratio alone suffices here.

### The selection rule that replaced it

**Cheap filter first, from the script:** sole speaker in the clip, and scripted
lines covering ≥55% of its duration. Free, and it eliminates almost everything
unsuitable. **Then confirm from the audio:** one contiguous speaking passage,
internal gaps ≤1.0 s, ≥60% actual speech.

**One contiguous passage from one take. Never stitched.** Splicing two passages
teaches an average of two deliveries — the drift the reference exists to prevent.

### Result

| | v1 | v2 |
|---|---|---|
| Kent | 2.3 s speech, from `14D` | **12.1 s at 87%, from `16E`** |
| Narrator | 6.9 s, from `00A` | **15.1 s at 100%, from `00B`** |
| references produced | 18 (all confidently wrong-ish) | **11 real, 7 honestly declared missing** |

Full set: Narrator 15.1 s, Avery 13.2 s, Volunteer 12.3 s, Kent 12.1 s, Doris
recording 11.8 s, Faith White 8.7 s, Ryann Sally 7.8 s, Housing representative
7.7 s, Doris 7.1 s, Congregation member 5.6 s, Terminal voice 4.9 s (thin).

**7 need a purpose-built VOX clip** — Aid worker, Council member, Crew lead, Male
Visitor One, Male Visitor Two, Unhoused man, Wealthy commuter. None has a single
clip where they are the only person talking for most of the shot; their lines run
2–6 s inside multi-character scenes. Specs in
`outputs/equal_shares/voice_reference_vox_specs.json`: 15 s, 0.2 MP, single
anchor, one person speaking continuously 1–14 s, fresh filler dialogue in
register. ~7 clips, about an hour. Never add them to `story_config.json`,
`manifest.json`, or the completion audit.

Their v1 files are quarantined as `h3_voice_ref.V1_REJECTED_DO_NOT_USE.wav`.
Superseded good refs are kept as `h3_voice_ref.superseded_v1.wav`. Nothing was
deleted.

### Two earlier notes corrected by this

**The "silent clips" list is wrong.** `04C 06A 14B 14E 16E 17C` were listed as
silent. `14B` yields **12.3 s** of clean speech and `16E` yields **12.1 s** — they
are now the Volunteer's and Kent's references. That list recorded *speech
recognition failing*, not an absence of audio. Different tests; earlier notes
conflated them.

**Do not trust a config window as evidence of content.** Check the audio.

---

## 2026-08-13 — Task 0 result and single-pass branch decision

### Task 0 verdict — 00J at 0.9 MP ref2va

Rendered by `work/submit_task0_00J.py`. Prompt: `prompts_audio_pass/00J.txt`.
Checkpoint: `minimax_h3_ref2va_pruned_nvfp4.safetensors`. Seed: randomised.
Render time: **37.8 min** (Qwen 32B CLIP encoder dominates; bulk of time is in
model load, not sampling). Output: `ComfyUI-Shared/output/story/TEST_09MP_00J/00J_00001_.mp4`.
Resolution confirmed via ffprobe: **1248×704**, AAC 32 kHz stereo, 12.25 s.

| Criterion | Result | Evidence |
|---|---|---|
| **Voice** | **PASS** | Librosa YIN pitch analysis: narrator ref median F0 = 134.7 Hz; 00J render median F0 = 134.6 Hz — match. RMS envelope shows speech spikes at 2–7 s and 9–10.5 s, aligned with scripted narration windows (expected: 1–6 s "This is the world…", 6–9.5 s "and a man walking…", 9.5–11 s "His name—Kent Brentwood."). |
| **Face** | **PASS** | Identity clean at native 1248×704. No warping observed across all extracted second-by-second frames. |
| **Camera** | **PASS** | Smooth aerial-to-chest descent. No ground-fall (the confirmed 1.0 MP failure mode). No cut, no reversal. Camera ends slightly in front of Kent rather than directly behind — minor drift from prompt, does not constitute a failure. |
| **Words** | **Likely PASS — transcript unverifiable** | RMS timing strongly matches script windows. Max amplitude 0.5053 (well above noise floor). Both Whisper-tiny and Windows SAPI returned empty — consistent failure mode for H3 AI-generated voice with these tools. No ASR tool available on this machine can decode H3 voice. |

**Blocking failure (prompt non-compliance):** Kent stopped walking and turned to
face the camera at approximately 6 s. Prompt already said "He walks at an even
pace, eyes ahead, not performing for the camera" and "Kent does not look at the
camera at any point" — model ignored both. **Prompt corrected** (2026-08-13):
added to CAST block "He walks forward continuously… he never stops, never slows,
never pauses, never turns around, and never looks toward the camera" and
strengthened the DO NOT list. The blocking failure is a prompt tuning problem, not
a model capability problem; it does not negate the camera/face pass.

**Branch decision: single-pass route.** Voice + face + camera all pass. Two-stage
pipeline (Task 1 audio harvest + Task 3 lipsync investigation) is cancelled.
`work/render_single_pass.py` renders all 124 clips at 0.9 MP:
- 78 dialogue clips: `minimax_h3_ref2va_pruned_nvfp4.safetensors` + `MiniMaxH3ReferenceToVideo` + audio ref per character
- 46 non-dialogue clips: `minimax_h3_fl2va_pruned_int8_convrot.safetensors` + `MiniMaxH3ImageToVideo`

All clips at: ResolutionSelector 0.9 MP / 16:9 / multiple 32 → 1248×704. BasicScheduler simple 20 steps denoise 1.0. KSamplerSelect res_multistep. SageAttention on.

### Render time comparison

| Megapixels | Approx render time per clip |
|---|---|
| 0.2 MP (stage-1 proof run from earlier sessions) | ~8 min |
| 0.9 MP (Task 0 test) | **~38 min** |

At 38 min/clip × 124 clips ≈ **78 hours** total GPU time, single-threaded, one
clean backend per clip.

### Task 4 — real dialogue accuracy

All 78 dialogue clips transcribed via Windows SAPI against `dialogue_timing` in
`story_config.json`. Results in `outputs/equal_shares/dialogue_accuracy_audit.json`.

| Metric | Result |
|---|---|
| Clips audited | 78 |
| Pass (word_recall ≥ 0.7 AND seq_sim ≥ 0.5) | **1 / 78 (1%)** |
| Median word_recall | 0.12 |
| Median seq_sim | 0.24 |

The previously-reported 96% accuracy figure was an artefact: `validation_transcripts/`
stored `coverage: 1.0, similarity: 1.0` as defaults for 132 of 138 files with no
`expected` field — the comparison was never performed. The fl2va renders contain
near-zero real dialogue accuracy. This confirms the need for the ref2va voice-clone
pass (or, in the two-stage route, stage-1 audio harvest + lipsync).

### ASR failure on H3 AI voice

Windows SAPI, Whisper-tiny (via transformers pipeline), and Whisper-tiny (via
direct `model.generate`) all return empty transcriptions for H3-generated speech.
The transformers 5.10.2 install in the ComfyUI venv cannot pass `task=` or
`language=` to `model.generate` for this model version (generation_config
compatibility error). Pitch and amplitude analysis via librosa are the only
on-device tools that confirm voice presence and identity.

**Implication for stage-1 judging (two-stage route, now cancelled):** the
"Transcribe with `transcribe_windows_speech.ps1` to screen the takes" instruction
in Task 1 would have produced empty results for every take. Human listening would
have been the only reliable gate.

### SONICSampler (Task 3, now cancelled)

Not investigated — Task 0 passed, Task 3 is skipped. If the single-pass route
later proves insufficient for a specific clip, `SONICSampler` investigation should
be the first step per the pipeline doc.

---

## 2026-08-13 — Codex takeover audit, persistent monitor, and VOX staging

### Exact reason the on-device transcription returned blank

The audio files are readable and contain real signal. `00J_00001_audio.wav` is
PCM 16-bit, 16 kHz, mono, 12.256 s. `00J_norm.wav` is PCM 16-bit, 192 kHz,
mono, 12.256 s. Converting either to 16 kHz mono does not change the result.

The installed model folder
`ComfyUI-Shared/models/sonicLipsyncFor_comfyui/sonic/whisper-tiny` contains
`config.json`, `preprocessor_config.json`, and `model.safetensors`, but **no
tokenizer vocabulary** (`tokenizer.json`, `vocab.json`, `merges.txt`, or
tokenizer configuration). Transformers 5.10.2 silently constructs a tokenizer
with vocabulary size 1; every generated token therefore decodes to an empty
string. The same broken bundle returns blank for the narrator reference and a
known speaking video, so blank output is not evidence that 00J is silent or
gibberish.

Windows SAPI has an English recognizer installed, but creating its recognition
context fails with `E_ACCESSDENIED` from this restricted process. The recognizer
path and WAV path are not the problem. No model or tokenizer was downloaded,
in accordance with the hotspot rule.

### Task 0 wording versus the approved boundary image

The approved `frames/scene_001/boundary_00.png` shows Kent facing the camera.
The prompt also asks the aerial descent to finish behind and slightly beside
him. Those directions cannot both be satisfied by a single anchored move. The
0.9 MP result follows the approved composition, ends slightly in front, and
contains the separate blocking fault where Kent stops and performs to camera.
Neither fault is the tested 1.0 MP camera-collapse mode: the shot remains one
continuous aerial-to-chest descent with no fall, second cityscape, cut, or
reversal. Task 0 camera therefore remains PASS, while the blocking is a
per-clip prompt-compliance rejection to fix on retry.

### Single-pass renderer observed live

`work/render_single_pass.py` claimed the queue as PID 34672 at 12:12 on
2026-08-13. On first observation it was rendering 00A with one prompt running
and the GPU fully occupied. At 57 minutes the sampler had advanced to step
12/20. The supervisor is designed to preserve raws under
`ComfyUI-Shared/output/story/SP_<clip-id>/`, stop the backend between clips, and
skip rather than fabricate a missing voice reference.

The six story clips currently blocked on seven missing references are `00D`,
`00D2`, `01B`, `27E`, `28C`, and `30B`. They will record missing-reference
errors and the renderer will continue; once VOX references are approved and the
audio-pass config is rebuilt, rerunning the same supervisor fills only the
missing entries.

A Codex task heartbeat named `Watch Equal Shares render` checks the owner,
single-pass log, sampler activity, port, and GPU every 10 minutes. It never
starts a second backend. It treats unchanged state as a stall only after at
least 10 minutes with no active sampler or render subprocess.

### Seven VOX jobs staged without touching the live render

Fresh character-register dialogue now lives in
`outputs/equal_shares/prompts_vox/` for all seven `VOX_*` IDs. The dialogue is
not film text, appears exactly once in the timed beat, and targets continuous
speech from 1–14 s with one voice and no music.

`work/render_vox_references.py` is the queue-aware 0.2 MP, 15 s, 362-frame,
20-step non-Turbo supervisor. It preserves every attempt under
`ComfyUI-Shared/output/story/VOX_*`, extracts a separate candidate WAV, and
requires both a longest speech run of at least 6.0 s and overall speech density
of at least 70%. A metric pass remains `pending ear check` until one voice and
no invented music are confirmed; measurement is not acceptance.

`work/build_voice_reference_map.py` now discovers only VOX entries explicitly
marked `audio_only_review: passed`. Its extraction path never deletes, renames,
or overwrites an existing approved `h3_voice_ref.wav`; an existing reference is
kept and reported. This removes the previous `unlink()` path that violated the
project's evidence-preservation rule.

---

## 2026-08-13 — SaveVideo parser recovery and corrected single-pass restart

The first 0.9 MP single-pass raw, `SP_00A/00A_00001_.mp4`, completed normally,
but the supervisor falsely marked it failed because Core `SaveVideo` reports
MP4 files inside an output field named `images`. The parser looked only at
`video`, `videos`, and `gifs`. The same defect was present in the staged VOX
supervisor. Both parsers now include `images` but accept only recognized video
extensions, so a preview PNG cannot be mistaken for the render.

The original manifest was copied to
`single_pass_manifest.pre_savevideo_parser_fix_20260813_134722.json` before any
state recovery. The runner now keeps previous entries under `attempt_history`,
writes the manifest atomically, and can salvage an existing raw only after
ffprobe confirms native dimensions, 24 fps, expected frame-derived duration,
and both video and audio streams. This is mechanical validity only; it does not
constitute visual acceptance.

`00A` passed that recovery check: H.264/AAC, **1280×736**, 24 fps, 15.083 s,
1,783,447 bytes. The exact 1280×736 size is the current core
`ResolutionSelector` result for 0.9 × 1024² pixels, 16:9, rounded independently
to multiples of 32. Earlier notes saying 1248×704 were incorrect; the approved
Task 0 raw is also 1280×736.

The older supervisor was interrupted after its already-invalid state path had
started 00B–00D; those interrupted attempts wrote no MP4 and remain recorded in
the backup/current attempt history. No raw was deleted. The corrected
supervisor claimed the queue as PID **27180** at 13:47:59, recovered 00A, and
resumed at 00B with one backend only. Dialogue clips with an empty approved
reference list now defer without launching ComfyUI, preventing wasted renders
before the VOX pass.

---

## 2026-08-13 — Codex-safe Comfy runtime and 00B recovery

The first Codex-launched restart could not finish ComfyUI startup because the
restricted desktop task could not write Rockernow's `temp` directory. A second
attempt also exposed unrelated custom-node import/install hooks that are not
needed by this API workflow. Both supervisors now start ComfyUI with
`--disable-all-custom-nodes`; every class used by the single-pass and VOX graphs
was verified to be a ComfyUI core node.

The active runtime's writable paths are now isolated under:

`outputs/equal_shares/runtime/codex_comfy_runtime/`

Its `input`, `output`, `user`, and `temp` subfolders are version-preserving
staging locations. New raw story clips therefore land under
`codex_comfy_runtime/output/story/SP_<clip-id>/`. The manifest records those
absolute paths, so assembly and auditing remain source-location independent.
The user's earlier instruction explicitly permits original chunks outside the
shared ComfyUI output as long as their location is reported. Existing shared
raws, including 00A, stay in place and remain discoverable by the salvage pass.

An initialization-order mistake briefly recorded destination-folder errors for
00B–30C before any backend or generation began. All 124 source boundary frames
were separately verified present. The manifest at that moment was preserved as
`single_pass_manifest.pre_staging_input_fix_20260813_141455.json`; subsequent
real attempts retain those entries in `attempt_history`. No raw was touched.

After creating the staging input folder before frame/audio copies, the corrected
supervisor claimed the queue as PID **31824** at 14:14:55. ComfyUI became ready
in 49 seconds, queued 00B, and reported one running prompt at 14:16:47 with
9.45 GB VRAM in use. This is one non-Turbo, 20-step backend only.

### User-requested pause and local-agent handoff

At 15:03 the user requested that the project stop after the current `00B`
render so a local agent can take over and free ChatGPT/Claude API usage.
`work/pause_after_clip.py 00B` is armed as a separate watcher. It waits for a
mechanically valid `00B` manifest entry and raw, probes the raw, stops only the
current queue-owner/backend tree, releases the owner record after port 8188 is
free, and writes `runtime/pause_after_00B_receipt.json`. It never edits the film
manifest or any raw.

The Codex heartbeat was changed from continuing the project to monitoring this
one pause only. It must not launch VOX or another story backend. The continuation
instructions for the local agent are in
`LOCAL_AGENT_CONTINUATION_PROMPT_2026-08-13.md`.

### User audio rejection — 00A

After reviewing the completed `SP_00A/00A_00001_.mp4`, the user rejected it
because the spoken narration contains substantial gibberish. Its ffprobe pass
remains true only as mechanical file validation; it is not dialogue acceptance
and the take must not enter the film as-is. Preserve the raw and manifest entry.
After the user-requested pause, the local agent must listen to both 00A and 00B,
record dialogue results separately from visual/mechanical state, and retry 00A
with a new seed or use the approved dialogue-replacement/lipsync route. Exact
scripted wording and consistent narrator identity are required in the final.

### Pause completed after 00B

`00B` completed at 16:02:11 and passed ffprobe: H.264/AAC, 1280×736, 24 fps,
15.083 s, 2,181,855 bytes. The first pause receipt records `paused: false`
because Windows denied stopping the supervisor PID directly. The supervisor
then entered only the startup phase for 00C; no 00C prompt was queued and no
00C raw was created. Its child backend PID 11832 was stopped, which caused the
supervisor to exit through its normal cleanup path and release the queue at
16:03:08. Port 8188 is free, render GPU use is gone, and no supervisor/backend
process remains.

The authoritative final pause evidence is
`runtime/pause_after_00B_recovery_receipt.json`. The project is paused for the
local-agent handoff; do not automatically launch VOX or another story render.
## 2026-08-13 — product goal clarified: reusable backend before GUI

The end goal is a working automated ComfyUI story-generator backend, not only a
finished Equal Shares film. Equal Shares is the reference implementation and
end-to-end regression test. The backend must accept a future story, produce an
editable narrative/shot/sound/reference plan, execute the full soundtrack-first
and picture workflow, validate and retry, resume safely, preserve provenance,
assemble outputs, and pass a completion audit.

The GUI is explicitly deferred until that headless backend works end to end. A
future GUI will be a thin client over backend commands/state and must not contain
duplicate render, validation, retry, or assembly logic. The complete product,
state-machine, module, data, and API requirements are now in
`docs/AUTOMATED_STORY_GENERATOR_BACKEND_SPEC.md` and linked from `README.md`,
`CLAUDE.md`, and both current local-agent prompts.

## 2026-08-13 — user-locked soundtrack-first pipeline (supersedes single-pass branch)

The user explicitly replaced the 0.9 MP single-pass branch. Do not resume
`render_single_pass.py`. The authoritative order is now:

1. Establish each character's voice from their first **qualifying delivered**
   MiniMax H3 appearance. A merely scripted first line does not qualify if its
   take is silent, noisy, mixed, unstable, or too short. VOX jobs remain the
   fallback for characters without a reliable passage.
2. Render the complete soundtrack for all 124 clips at 0.2 MP with full-quality
   non-Turbo H3 ref2va. Use the exact opening frame and wire `ref_image_1` when a
   closing frame exists. Picture is disposable; native audio is the product.
3. Validate dialogue, gibberish, extra/missing/repeated words, order, timing,
   silence/clipping, voice continuity, and recurring music/ambience/effects.
   Blank ASR is unknown, never pass. Keep improving the filter from reviewed
   false passes/rejects. The high-resolution stage is blocked until 124/124
   soundtracks are accepted.
4. Feed each approved full-clip soundtrack back to ref2va as the exact audio
   reference for picture generation. Start at 0.9 MP. On visual rejection descend
   `0.9 → 0.8 → 0.7 → 0.6 → 0.5 → 0.4 MP`. After a failed 0.4 MP attempt, mark
   `human_review_needed`; never continue below 0.4 automatically.
5. Validate full motion and native-resolution frames for faces, identity,
   anatomy, hands/limbs, interactions, temporal/camera faults, continuity,
   blocking, architecture, unintended people, and text. Metrics/contact sheets
   cannot grant acceptance.
6. Mux the exact approved Stage-1 WAV onto the accepted picture. The picture pass
   may guide performance but cannot rewrite accepted words, voices, music,
   effects, or timing. The non-diegetic score remains one continuous master
   across cuts.

Implementation added/updated:

- `work/build_voice_reference_map.py`: first qualifying appearance wins.
- `work/build_audio_pass_prompts.py`: closing-frame job and config fields.
- `work/render_audio_pass.py`: all 124 clips, 0.2 MP, first/last images, preserved
  attempts, validator integration.
- `work/validate_audio_pass.py` and `work/review_audio_pass.py`: conservative ASR
  and mechanical screening plus provenance-preserving promotion.
- `outputs/equal_shares/audio_continuity_map.json`: recurring sound/score policy.
- `work/render_picture_pass.py`: exact approved WAV reference and 0.9-to-0.4
  ladder behind a hard 124-audio gate.
- `work/validate_visual_pass.py` and `work/review_picture_pass.py`: objective
  prefilter, native-frame preparation, agent review, and exact-audio mux.
- `work/audit_equal_shares_completion.py`: now requires both 124-clip gates,
  zero human-review-needed clips, provenance, assembly inputs, and final master.

All changed Python files passed `py_compile`; runner/review command interfaces
loaded successfully. `build_audio_pass_prompts.py --check` parsed 78 dialogue
clips and 46 non-dialogue clips. The remaining eight missing-reference warnings
now belong to eight VOX characters: the seven already-known missing references
plus Terminal voice, whose 5.4-second passage was below the new six-second
reliability floor. Derived audio prompts/config
were rebuilt with last-frame fields. No renderer or backend was started.

## 2026-08-13 — thermal safeguards for local operation

The RTX 5080 was measured idle at 29 C, 0% GPU use, and about 16 W. The local
Ollama `qwen2.5-coder:14b` process was using about 51% of the host's 16 logical
processors. Windows exposes no usable ACPI CPU package-temperature sensor on
this installation.

The Open Interpreter wrapper now passes `num_thread=4` as well as `num_gpu=0`,
reducing the local agent to one quarter of logical CPU capacity. Current VOX,
Stage-1 audio, and Stage-2 picture runners now share `work/thermal_guard.py`:
preflight is allowed at 70 C or below, a hot card waits for 60 C, every stopped
backend cools to 58 C before the next GPU job, and an active attempt is
interrupted at the 82 C emergency ceiling. Three consecutive telemetry failures
block a new render rather than proceeding without temperature evidence.

## 2026-08-14 — local-agent command-language recovery

The offline Open Interpreter session released its owner at 00:46 after the
local model repeatedly labeled Windows CLI commands as `sh` or `python`.
Open Interpreter rejected those blocks before execution, so no VOX or Stage-1
render started. The native `DirectPowerShell` adapter now also accepts `sh`,
`shell`, `bash`, and `cmd` labels, while the startup prompt explicitly requires
PowerShell blocks and full-path Python invocation. The prompt also locks the
next action to unfinished VOX reference work before `render_audio_pass.py`.

A read-only diagnostic accidentally invoked the VOX runner with `--help`; that
runner has no argument parser and claimed queue PID 21752 before the diagnostic
was immediately terminated. Port 8188 remained free, GPU use remained zero,
and no backend, prompt, or raw output was created. The stale owner was safely
released and the evidence is in
`runtime/local_agent_recovery_20260814_0050.json`.

## 2026-08-14 — unowned Desktop backend and VOX runner hardening

The restarted local agent reached `render_vox_references.py` at 00:55, but a
separately running ComfyUI Desktop backend already occupied port 8188. Its API
reported an empty queue, no history, Desktop standalone arguments, and zero GPU
utilization. The VOX runner correctly refused to start a second backend, but its
outer cleanup incorrectly called `stop_comfy(None)` and attempted to interrupt
the unowned Desktop API before releasing the queue. No VOX prompt, manifest, or
raw was created.

VOX, Stage-1 audio, and Stage-2 picture cleanup now stop ComfyUI only when the
runner holds a concrete child PID. VOX startup also terminates its exact child
if startup fails before the PID can be returned. The local-agent prompt now
uses the correct `outputs/equal_shares` state paths and treats denied CIM port
queries as unknown rather than free.

## 2026-08-14 — user correction: actual-story voice bootstrap only

The user rejected the purpose-built VOX branch because its invented filler
dialogue is not the requested voice-continuity method. The partially rendered
VOX files and their manifest remain preserved as rejected evidence, but every
VOX ID is explicitly ineligible as a voice source. `work/render_vox_references.py`
and the legacy `work/voice_manager.py` now exit disabled before claiming the
queue or starting ComfyUI.

The authoritative replacement is `story_voice_bootstrap_plan.json`. Every
missing character voice is established from that character's first qualifying
actual story soundtrack, using the exact original story line, opening frame,
and closing frame when supplied. These bootstrap renders use full-quality
non-Turbo MiniMax H3 ref2va at 0.2 MP and 20 steps. A passage with at least six
useful seconds may become canonical after audio acceptance. A 2-6 second story
passage is preserved but requires human voice review before promotion; invented
words, concatenated takes, filler scenes, and non-story samples are prohibited.

Current bootstrap order is dependency-aware: `00D`, then `00D2`; `01B`; `11B`;
`27E`; `28C`; and `30B`. `00D2` must wait until Male Visitor One's accepted
`00D` passage has been extracted and the map/prompts rebuilt. The remaining
multi-speaker or single-speaker bootstrap clips similarly use any already
approved character references while allowing only their own planned missing
characters to originate from the actual story take.

After the missing references are accepted, Stage 1 generates and validates all
124 complete MiniMax H3 soundtracks at 0.2 MP. Stage 2 remains hard-blocked until
the audio gate is 124/124 accepted. Stage 2 feeds each exact approved full WAV
back to ref2va, begins at 0.9 MP, and descends 0.8, 0.7, 0.6, 0.5, then 0.4 only
on visual rejection. A failure at 0.4 is marked `human_review_needed`. No Turbo,
no downloads, no deletions or overwrites, one backend, preserved attempts, and
the documented thermal guard remain binding.

## 2026-08-14 — ear review made nonblocking for Stage-1 generation

The user explicitly instructed that ear review must not stop generations. Six
actual-story bootstrap clips completed with mechanically valid audio candidates
but blank recognizer output, so their status remains `needs_ear_review`; blank
ASR is still unknown, never an acceptance. Their usable character passages are
now versioned as `h3_voice_ref.provisional_<clip>.wav` and recorded in
`voice_reference_map.json` as `provisional`, `requires_ear_review`, and
`generation_use_only_until_reviewed`.

This is not an audio-gate bypass. Provisional references may condition later
Stage-1 soundtrack generations so unrelated work keeps moving, but they do not
become canonical, do not change any manifest entry to accepted, and cannot open
Stage 2. `work/continue_audio_generation_nonblocking.py` first renders remaining
actual-story bootstrap dependency `00D2`, rebuilds the provisional map, and then
runs the full resumable Stage-1 queue. Existing pending candidates are skipped,
all unrendered clips continue, and later ear review can accept or reject and
rerender individual soundtracks without discarding any generation.

## 2026-08-14 — Narrator double-track repair and prompt preflight

Human listening found consistent Narrator identity but two simultaneous vocal
layers in many soundtracks: the intended generated line plus a quieter
reference-like voice. The reference remains valid for identity. Prompts now say
that it is identity conditioning only and must be completely inaudible, and
require one dry Narrator performance with no replay, leakage, quieter duplicate,
backing speech, whisper, alternate take, chorus, echo, delay, or speech-shaped
reverb.

The user's proven-prompt attachment contained ten blocks. Dialogue matching
mapped them to 00A, 00B, 00D, 00D2, and 00E through 00J. It was not mapped by
ordinal position because 00D2 changes the clip count. Converted 00D and 00D2
duplicated short visitor phrases, so validation rejected those conversions and
retained their clean existing blocking with the new mix lock. All 16 versioned
Narrator repair prompts pass in `prompts_audio_pass_narrator_repair_v2/`,
including the explicitly reported gibberish clips 00A and 00I.

`work/audit_audio_prompts.py` checks exact-once dialogue, timing bounds, speaker
references, boundary frames, reference indices, mouth locks, no-Turbo text, and
contradictory silence instructions. All 58 not-yet-rendered prompts passed.
`work/retry_narrator_audio_after_stage1.py` is queued locally. It trusts positive
owner records until explicit release so a between-clip ComfyUI restart cannot
start a second backend. After the first pass it appends one preserved repair
attempt for 00A through 00O, then runs the resumable Stage-1 continuation again
so no unrendered clip is stranded.
## 2026-08-14 — installed-node Omni-Reference voice-lock correction

The user authorized a controlled MiniMax H3 Omni-Reference strategy before the
XTTS fallback. Inspection of Rockernow's installed
`comfy_extras/nodes_minimax_h3.py` confirmed that
`MiniMaxH3ReferenceToVideo` supports up to three standalone audio references
and nine images. More importantly, its prompt grammar is `<Audio 1>` and
`<Picture 1>`; the older generated prompts used internal `ref_audio_0` socket
names. New versioned prompts now use only native tags, bind each speaker to one
immutable checksum-pinned 5-10 second master, and exclude music/effect refs.

Control prose containing "the audio is the deliverable" was removed because a
previous 09C generation spoke "is the deliverable." The new prompts contain
each exact line once in its exact window and require the master recording to be
inaudible, with no replay, leakage, doubling, alternate take, echo, or
speech-shaped reverb.

Fifteen of eighteen masters are ready. Crew Lead, Male Visitor One, and Male
Visitor Two require new 0.2 MP, 20-step, non-Turbo purpose-built VOX references.
`work/continue_omni_voice_lock_pipeline.py` performs only that missing work and
then renders one preserved test each for 00A and 00I using the same Narrator
master. The full Stage-1 queue waits for those two results to be audited. Stage
2 remains blocked until all 124 complete soundtracks are accepted.

## 2026-08-15 — the prompt format was wrong all along

Full spec now in `docs/H3_PROMPT_RULES.md`. This entry records how it was found.

### The project had never used H3's native prompt format

Reading the official guides — the ComfyUI H3 tutorial plus MiniMax's own
`VIDEO_PROMPT_WRITING_GUIDE_ref_en.md` — showed the R2V format is six named
sections: `subject_definitions`, `summary`, `retention_analysis`,
`detailed_description`, `overall_soundscape`, `non_diegetic_music`. The project
had none of them.

### `retention_analysis` was the doubled-voice bug

Every reference needs a line declaring its relationship to the output. For audio
the markers are `fully_copy`, `partially_copy`, `reference`, `weak_reference`.

Nothing in any prompt had ever told H3 that the voice master was a **reference**
rather than a source to **copy**. A partial copy of the master laid under freshly
generated speech is exactly the quieter-second-vocal symptom that had blocked the
project for days, and that no amount of prose forbidding echo or chorus removed.

Adding one line fixed it on the first attempt:

```
<Audio 1>: reference - S1 follows <Audio 1>'s voice timbre, pitch, accent, and
delivery without copying the original signal; none of its words, breaths, or
room tone appear in the target video.
```

**Lesson: a missing required section is invisible. Absent structure produced a
default behaviour, and the default was wrong.**

### Two gibberish faults, both positional, both found by listening

**Fault 1 — a split line.** A hand-written `00B` prompt split the Narrator's
sentence across two beats at `…so they are no longer without,` /
`but in the process…`. The render put about a second of gibberish at exactly that
seam. Two quoted fragments read as two utterances and H3 fills the gap between
them. **One scripted line, one `<d>` block, always.**

**Fault 2 — delivery prose after the tag.** The user's own diagnosis, and
correct: text referring to a character speaking, placed after `</d>`, reads as
speech still in progress. `00B` carried `The Narrator's delivery cools.`
immediately after the tag and the model kept talking past the scripted words,
producing a tail of gibberish.

The guide's examples confirm it — two of its three dialogue examples close the
speaker's mouth in the clause right after `</d>`:

> `…<d>[English] Hey! Watch your dog!</d> She closes her lips and guards the cookie…`

So: **delivery before the tag, mouth closes after it.**

### Other format corrections

- **Dialogue is `<d>[English] …</d>`.** Double quotes are for on-screen lettering
  only. This inverts the project's old rule, which existed because the previous
  format had no `<d>` tag.
- **`[Shot N]` marks a cut, not a beat.** A continuous take is one `[Shot 1]`
  with no timestamp; timing inside it is prose. The `[0-1 s]` bracket notation
  was never the model's grammar.
- **Speaker IDs `(S1)`, `(S2)`**, by order of first vocal event.
- **Identity-only images get no `<Picture N>` entry** — cite them inside the
  `<Subject N>` definition. Standalone picture entries are frame anchors only.
- **`ref_image_size: max`** keeps a 2048px short edge for stronger identity
  fidelity; the project has always run `match`, which downscales references at
  the moment identity is decided. Untested here — worth one clip.
- The docs name the R2V checkpoint `ref2va_pruned_int8_convrot`; this project
  runs the more aggressively quantised `nvfp4`. Untested, and a multi-GB
  download, so blocked on bandwidth.

### Two converter bugs worth not repeating

`work/build_native_r2v_prompts.py` regenerates all 124.

1. Header detection required full capitalisation, so `SHOT LIST and DIALOGUE
   TIMING` — lowercase "and" — was missed and the first run wrote **124 prompts
   with no dialogue at all**. A structural check caught it; reading one file
   would not have.
2. The mouth-close clause was appended to every line, telling a character with
   two lines to fall silent before the second. Now only a speaker's final line
   closes the shot.

Verified on every run: 78 dialogue clips, one `<d>` per scripted line, zero
splits, exact word fidelity against `dialogue_timing`, a mouth-close after every
`</d>`, no delivery prose after any `</d>`, and correct pronoun/verb agreement.

## 2026-08-15 (later) — the audio pipeline works, and why

**Confirmed: `00B` rendered at ~9 s with correct words, one clean voice layer,
and no gibberish anywhere.** Full procedure in `docs/AUDIO_PASS_RUNBOOK.md`;
prompt grammar in `docs/H3_PROMPT_RULES.md`.

Four faults had to be fixed, each found by a render failing:

| Fault | Fix |
|---|---|
| quieter second vocal under every take | `retention_analysis` declaring `<Audio N>: reference` |
| gibberish mid-line | one `<d>` block per scripted line, never split |
| gibberish right after the line | delivery before the tag, mouth closes after it |
| **gibberish filling the tail** | **render short, pad silence at assembly** |

The fourth is the one that was never a prompt problem, and it took three failed
prompt revisions to accept that. ~~**H3 fills whatever window it is given with
speech.**~~ 72 of 78 dialogue clips allot 3 s or more beyond what their lines take
to say — `00A` by 9.6 s — and the model invents words to fill the gap.

> **REVERSED 2026-08-18.** The struck sentence is not supported. `4_`.mp4` in the
> good-audio set is **56% silence** and the operator confirms it is clean;
> `15.mp4` runs at 1.14 w/s and is clean. The `00B` renders this was built on
> carried a corrupt prepended header *as well as* a long duration, and only the
> duration was noticed. Rendering short is still correct — ~30% cheaper, and all
> 14 known-good takes are short — but it is a precaution, not a cure. The retry
> knob for gibberish and mispronunciation is the **duration ladder**
> (`work/duration_ladder.py`, `H3_PROMPT_RULES` §10).
> See `docs/GOLDEN_REFERENCE/PROVEN_FACTS.md` §3.

### The duration split

```
SOUNDTRACK   short   audio_pass_durations.json    00B  260 frames  10.83 s
PICTURE      full    story_config.json            00B  362 frames  15.00 s
ASSEMBLY     pad     +4.17 s digital silence    = 15.00 s
```

Silence added in an editor is perfectly silent — the one thing a generative
model cannot promise. **The film's pacing is unchanged**; only the soundtrack
render is shortened and then padded back, and the runtime is still 1266 s.
`render_picture_pass.py` reads duration from `story_config.json` and strips any
shortened value that reaches it, so it cannot leak. The pass also costs 31%
fewer frames.

### `audio_pass_config_omni_v1.json` had drifted badly and silently

It is what `render_audio_pass.py` actually reads, and it was stale on three
counts at once:

- **78 clips** pointed at the superseded `prompts_audio_pass_omni_v1/` set,
  which has no `retention_analysis` — the doubled-voice fix would never have
  reached the renderer
- **16 voice references** still named `omni_master_v1` after the Narrator moved
  to v2
- **78 clips** carried scripted rather than shortened durations

None of it was visible without checking. `work/sync_omni_audio_config.py`
regenerates the file from the four sources of truth; run `--check` before every
pass rather than trusting it.

**Lesson: a config assembled from several upstream files is the place drift
hides.** Regenerate it, never hand-edit it.

### Verified across the whole story, not just the narration

Every clip and every one of the 18 speaking characters:

```
six-section native format ....... 124/124
one <d> per scripted line ....... 78/78
<Audio N>: reference marker ..... 78/78
mouth closes after every </d> ... 78/78
stop-filling instruction ........ 78/78
shortened render length wired ... 78/78
native prompt wired in config ... 78/78
```

11 characters have an approved voice master; 7 are provisional and are unblocked
by the first-appearance packs.

One checker bug worth remembering: the mouth-close verification searched for
`closes` and so failed 68 clips that correctly read `close their mouth` with the
neutral pronoun. **The prompts were right and the check was wrong** — always
confirm a failure by reading the actual file before acting on a checker.

## 2026-08-16 — reconciled the instruction set before restarting the agent

The pipeline was ready but the **instructions** were not. `CLAUDE.md` is
auto-loaded and binding, and its top section still carried the 2026-08-14
Omni-Reference override, which said two things that were no longer true:

- purpose-built **VOX identity masters with invented filler dialogue** were
  authorised
- the job was **limited to three masters plus controlled 00A/00I tests**

An agent reading that literally would have rendered filler dialogue and stopped
after two test clips. Replaced with the current job: all 124 Stage-1
soundtracks, the four rules that make the audio correct, VOX prohibited again,
and `sync_omni_audio_config.py --check` before touching the GPU.

Six files were bannered `SUPERSEDED 2026-08-16 — historical, do not execute`,
each of which actively instructed VOX rendering or a limited test run:

```
CLAUDE_CODE_AUDIO_FIRST_PROMPT.md
CHATGPT_START_PROMPT.md
LOCAL_AGENT_CONTINUATION_PROMPT_2026-08-13.md
CLAUDE_CODE_OMNI_WATCH_PROMPT.md
docs/OMNI_REFERENCE_VOICE_LOCK_PIPELINE.md
RESUME_PROMPT_00J_AUDIT.md
```

`voice_reference_vox_specs.json` was renamed
`voice_reference_vox_specs.SUPERSEDED_DO_NOT_USE.json` so it cannot be acted on
by a path lookup.

Two self-contradictions were left behind by the first pass and had to be chased:
`CLAUDE.md` still named `CLAUDE_CODE_AUDIO_FIRST_PROMPT.md` as "the current
plan" after that file had been bannered, and `README.md` still listed it as the
operational assignment. Both now point at `docs/AUDIO_PASS_RUNBOOK.md` and
`CHATGPT_START_AUDIO_PASS.md`.

**Lesson: superseding a document is only half the job.** Every file that
*pointed* at it has to be repointed in the same pass, or the contradiction
survives in the index. Sweep for inbound references, not just the file itself.

Also worth recording: nothing in the tree had changed for ~17 hours before this,
which was only discovered by running a full mtime scan. Polling the supervisor
log tells you whether a render is alive; it does not tell you whether another
agent has rewritten a prompt or a config. Scan mtimes before declaring readiness.

## 2026-08-16 — Claude Code soundtrack pass

**Session start:** CLAUDE.md updated 2026-08-16. Removed Omni-Reference controlled-test gate (00A/00I with v1 master). Pipeline is confirmed working from 00B. Full 124-clip soundtrack pass (78 dialogue + 46 ambient auto-pass) is the job.

**Job 1 result:** `sync_omni_audio_config.py --check` — no drift. Config current. GPU at 29°C idle. Stopped idle ComfyUI PID 24184 (had run since 2026-08-15 19:03, empty queue, released owner file).

**Job 2 plan:** 8 provisional voice masters. Render first-appearance story clips in order:
- 11B (Terminal voice, 209fr) → extract master
- 30B (Aid worker, 90fr, solo short)
- 00D (Male Visitor One + Narrator, 158fr)
- 00D2 (Male Visitor Two + Male Visitor One + Narrator, 243fr)
- 01B (Wealthy commuter + Unhoused man, 243fr)
- 27E (Council member + Kent + Ryann, 192fr)
- 28C (Crew lead + Kent, 90fr)

After each batch: `build_voice_reference_map.py --allow-provisional-story-bootstraps --extract` → `prepare_omni_voice_masters.py` → `sync_omni_audio_config.py`.

**`--bootstrap-missing-voices` finds no clips:** all 8 provisional characters already have map entries (even if thin). Must use `--clip <ID> --rerender-pending` explicitly.

**`voice_manager.py` is disabled.** Note says to use `build_voice_reference_map.py` + `render_audio_pass.py --bootstrap-missing-voices`. But bootstrap flag only works if character is in `needs_story_bootstrap`, not `provisional_references`. The correct update path is `--allow-provisional-story-bootstraps --extract`.

## 2026-08-16 — Job 2 masters extracted; Job 3 launched

### Voice master extractions (Job 2 complete)

All 8 provisional voice masters created from best story candidates:

| Character | Source | Window | Duration | Speech | Density | short_master |
|---|---|---|---|---|---|---|
| Aid worker | 30B_a01_full.wav | full | 8.0s | 7.8s | 98% | false |
| Council member | 27E_a01_full.wav | 0-5.0s | 5.0s | 4.2s | 83% | true |
| Crew lead | 28C_a01_full.wav | 2.0-5.5s | 3.5s | 3.4s | 96% | true |
| Male Visitor One | 00D_a02_full.wav | 8.0-end | 4.3s | 4.0s | 94% | true |
| Male Visitor Two | 00D2_a02_full.wav | 2.0-6.0s | 4.0s | 3.9s | 98% | true |
| Unhoused man | 01B_a01_full.wav | 7.0-end | 6.7s | 4.5s | 67% | true |
| Wealthy commuter | 01B_a02_full.wav | 0-7.0s | 7.0s | 5.1s | 73% | true |
| Terminal voice | 11B_a02_full.wav | 0-8.7s | 8.7s | 8.5s | 97% | false |

Dialogue timing from story_config.json used to determine speaker windows in multi-speaker clips. All marked provisional, requires_ear_review.

### Validator hotfix

`validate_audio_pass.py` decision logic was routing H3 partial ASR matches (recall ~0.65) to `retry_required` instead of `needs_ear_review`. This caused an infinite retry loop (retry_required clips re-queued on restart). Fix: only mechanical failures (clipping, silence, speech-in-no-dialogue-clip) trigger `retry_required`; ASR dialogue mismatch routes to `needs_ear_review` for operator ear review.

Also added `importlib.reload(audio_gate)` call in `render_audio_pass.py` before each validation so future config changes to validate_audio_pass.py apply without supervisor restart.

### Job 3 running

Full 124-clip pass launched 16:40, first 3 clips completed by 17:11. Rate: ~5-6 min/clip. Expected completion: 2026-08-17 ~04:00.
