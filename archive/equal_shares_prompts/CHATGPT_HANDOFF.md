# Equal Shares — complete handoff

> **Local-agent update (2026-09-02):** The Equal Shares pipeline is paused while
> the separate `local_agent/` program is being upgraded as a general desktop
> assistant. Read `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md` before doing
> any local-agent work. It records the current APP_REVISION, all verified
> architectural changes, open execution gates, and the rule that the parent
> `outputs/` fork must not be updated.

> **Superseded workflow notice (updated 2026-08-14):** Use this file only for historical
> evidence and paths. The current execution order is defined by `CLAUDE.md`,
> `docs/TWO_STAGE_AUDIO_FIRST_PIPELINE.md`, and
> `CLAUDE_CODE_AUDIO_FIRST_PROMPT.md`: complete/accept the full 0.2 MP native H3
> soundtrack first, then render picture around the exact WAV at 0.9→0.4 MP.
> Do not resume the old single-pass branch. All purpose-built VOX clips, filler
> dialogue, and invented voice samples described later in this historical file
> are explicitly rejected and prohibited. Bootstrap missing voices only from
> their first qualifying actual story soundtrack through
> `work/render_audio_pass.py --bootstrap-missing-voices`.

Written 2026-08-13 02:10; historical Equal Shares material follows. For the
current general local-agent state, use the dated local-agent handoff above.
Everything needed for the historical film context is in
this file. Paths point into the working tree for the detail.

**Working tree (canonical):**

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

**Shared ComfyUI output tree (all raw generations):**

```
A:\Users\rhine\ComfyUI-Shared\output\
```

Never read project state from the parent folder `...\referenced-chatgpt-conversation-this-is-an-2\outputs`. It is a stale fork frozen at 44 clips.

> **Read §15 before you change any setting or rule.** It is the decision log —
> every constraint in this document came from a specific, measured failure, and
> §15 gives the evidence behind each one. Sections 1–14 tell you *what*; §15
> tells you *why*, which is what you need in order to judge a situation these
> rules did not anticipate.

---

## 1. What the project is

A ~21-minute film, "Equal Shares," built as **124 MiniMax H3 clips** rendered
locally in ComfyUI. Total runtime 1266 s. Kent Brentwood is the lead; the story
is a Twilight-Zone-style parable about enforced equality.

**Status: 124 rendered, 43 accepted, 22 confirmed rejects, 51 never reviewed.**
"124/124 valid clips" in the supervisor log is a *render* count, not acceptance.
The film is not finished.

---

## 2. The immediate next action

The last session rendered a test clip and stopped mid-audit. **Do not
regenerate it.**

```
A:\Users\rhine\ComfyUI-Shared\output\story\TEST_09MP_00J\
    00J_00001_.mp4          rendered 01:32
    00J_00001_audio.wav     extracted 01:35
    00J_norm.wav            normalised 01:48
```

`00J` was rendered with the **ref2va checkpoint + an audio reference, at
0.9 MP**. Audit it on four criteria, in this order, recording a separate verdict
for each:

1. **Voice** — compare by ear against `outputs/equal_shares/voices/narrator/h3_voice_ref.wav`
   and `A:\Users\rhine\ComfyUI-Shared\output\video\1.mp4`. Same man?
2. **Face** — Kent and the Narrator at native resolution, across the whole clip.
   Not on a contact sheet.
3. **Camera** — `00J` is a continuous descent from high aerial to chest height.
   At 1.0 MP the camera previously fell through the ground into a different
   cityscape. Verify it does not, and does not cut or reverse.
4. **Words and timing** — scripted line is in
   `outputs/equal_shares/prompts_audio_pass/00J.txt`.

The previous session stalled on an **empty Windows Speech transcription
result**. Diagnose it — check sample rate, channels, bit depth and duration of
`00J_norm.wav`, and whether the recogniser is getting a readable path — but do
not let a broken transcription tool block criteria 1–3. **Download nothing.**

### Why this one clip matters so much

| Outcome | What to do |
|---|---|
| Voice, face and camera all pass | **Drop the two-stage plan.** Render the film in one ref2va pass at 0.9 MP. ~124 renders instead of ~248, and the lipsync problem disappears entirely. |
| Camera wanders, face clean | Retry once at 0.8 MP, then fall back to the two-stage plan below. |
| Face degraded | Try 0.8 MP before concluding anything. |

The reason for doubt: ref2va is `nvfp4`, more aggressive quantisation than the
`int8` fl2va checkpoint the 0.9 MP sweet spot was measured on.

### Machine state as of 02:10

- ComfyUI port 8188 not listening.
- `outputs/equal_shares/runtime/render_queue_owner.json` still names PID `12564`.
  **That entry is stale** — the process is gone. Claim the queue with a fresh
  PID; do not read it as an active render.
- `runtime/render_supervisor.log` last advanced 2026-08-12 04:48.

---

## 3. The discovery this all rests on

At 00:02 on 2026-08-13, one generation produced **accurate words, correct
timing, and no gibberish** — the first time in the project. Saved as
`A:\Users\rhine\ComfyUI-Shared\output\ComfyUI_00108.png` →
`output/video/MiniMax_H3_00002_.mp4`.

ComfyUI embeds the full API graph in every output PNG, so it is fully
recoverable. Two halves matter, and the prompt is the more important one.

### The graph

| | |
|---|---|
| UNet | `minimax_h3_ref2va_pruned_nvfp4.safetensors` |
| Node | `MiniMaxH3ReferenceToVideo` |
| Image reference | `ref_images.ref_image_0` ← `LoadImage` |
| Audio reference | `ref_audios.ref_audio_0` ← `VHS_LoadVideoPath` **output 2 (audio)** |
| `ref_image_size` | `match` |
| Resolution | `ResolutionSelector`, 16:9, **0.2 MP**, multiple 32 |
| Steps / sampler | 20, `res_multistep` / `simple`, denoise 1.0 |
| Frames | `max(5, round(a*24)) + (5 - (max(5, round(a*24)) % 17)) % 17` |
| fps / depth | 24 / 8-bit |

**Reference sockets are a dynamic list** — `ref_audio_0`, `ref_audio_1`,
`ref_audio_2`. A second character in a scene gets `ref_audio_1`. This was the
open question and it is answered.

### The prompt format — read `docs/H3_PROMPT_RULES.md`

**Superseded 2026-08-15.** The four-rule recipe that used to sit here was
reverse-engineered from one good render before the official guides were read. It
was wrong about the format. H3's native R2V prompt is **six named sections**:

```
subject_definitions:   <Subject N> people and sets, <Picture N> frame anchors,
                       <Audio N> voice masters
summary:               [task types] one paragraph
retention_analysis:    one line per reference declaring its relationship
detailed_description:  style sentence, then [Shot 1], prose, <d> dialogue
overall_soundscape:    ambience and physical sound only
non_diegetic_music:    N/A for this film
```

**`retention_analysis` is the section that fixed the doubled voice.** For a
voice master the marker is always `reference`:

```
<Audio 1>: reference - S1 follows <Audio 1>'s voice timbre, pitch, accent, and
delivery without copying the original signal; none of its words, breaths, or
room tone appear in the target video.
```

Nothing had ever told H3 the master was a reference rather than a source to
copy, and a partial copy under fresh speech is exactly what the quieter second
vocal layer was. One line removed it.

**Three more rules, all confirmed by renders on this machine:**

1. **One scripted line, one `<d>[English] …</d>` block.** Splitting a line across
   two fragments puts a second of gibberish at the seam — observed on `00B`.
2. **Delivery before the tag, mouth closes after it.** Prose about a character
   speaking placed after `</d>` reads as speech still in progress and the model
   talks past the scripted words. The guide's own examples close the mouth in the
   very next clause.
3. **`[Shot N]` marks a cut, not a beat.** A continuous take is one `[Shot 1]`
   with no timestamp; timing inside it is prose. Double quotes mean on-screen
   lettering, never speech.

All 124 prompts are regenerated in this format by
`work/build_native_r2v_prompts.py` into
`outputs/equal_shares/prompts_native_r2v/`, verified for one `<d>` per line,
exact word fidelity, and a mouth-close after every tag.

---

## 4. Locked settings

**Fixed on every path:**

- Text encoder `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`
- Video VAE `minimax_h3_video_vae_fp16.safetensors`, audio VAE `minimax_h3_audio_vae_fp32.safetensors`
- `res_multistep` / `simple`, denoise 1.0, SageAttention on
- 16:9, multiple of 32, 24 fps, 8-bit, **20 steps**
- Frame count rounds up to the next value congruent to **5 modulo 17**
  (8 s → 192, 10 s → 243, 12 s → 294, 15 s → 362)

**Three render paths — do not mix their settings:**

| | checkpoint | node | MP |
|---|---|---|---|
| Story render | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `MiniMaxH3ImageToVideo` | **0.9 (1280×736)** |
| Stage-1 audio pass | `minimax_h3_ref2va_pruned_nvfp4.safetensors` | `MiniMaxH3ReferenceToVideo` | **0.2** |
| Single-pass, under test | `minimax_h3_ref2va_pruned_nvfp4.safetensors` | `MiniMaxH3ReferenceToVideo` | **0.9** |

**0.3 MP is superseded — it warps faces.** 0.9 MP is the measured sweet spot:
0.3 and 0.4 warp faces, 1.0 breaks camera control. The window is roughly 10%
wide. If VRAM will not carry a clip, drop that clip by 0.1 to 0.8 and record it.
Historical setting, now superseded: the user-authorized Stage-2 fallback ladder
is 0.9→0.8→0.7→0.6→0.5→0.4 MP, with `human_review_needed` after a failed 0.4 MP
attempt.

`ResolutionSelector` drives resolution by **megapixels**. When that node is
present, the `width`/`height` values in `story_config.json` are dead tokens.

**Prohibited:** `minimax_h3_turbo_4step_ema_ckpt850.safetensors`, all Turbo
nodes, all Turbo LoRAs.

---

## 5. The two-stage plan (only if Task 0 fails)

### Stage 1 — harvest the voice track, 0.2 MP

78 dialogue clips, ref2va, one audio reference per speaking character. Picture is
disposable; only the audio is kept. Output to `story/AUDIO_<clip>/` — **never**
into `story/<clip>/`, `manifest.json`, or `story_config.json`.

Judge **by ear, audio only**. Accept when all four hold: the words are the
scripted words; they land inside the assigned window; one voice per line with no
second character muttering underneath; no invented music.

Re-roll by editing the prompt, not the seed. Across 95 analysed takes, keepers
and rejects had *identical* settings and every difference that mattered was in
the prompt. In order: tighten the beat window (H3 speaks a median ~1 s early) →
split long lines across more beats at clause boundaries → name who is silent in
that beat → only then change seed.

### Stage 2 — the picture at 0.9 MP

All 124 clips. Use `prompts_audio_pass/` for the 78 dialogue clips, existing
prompts for the 46 without. **Leave the dialogue in — do not lock mouths closed.**

### Stage 3 — lipsync, and the constraint nobody had checked

The only lipsync tooling on the machine is **Sonic**:

```
models/sonic/UNet.pth
models/sonicLipsyncFor_comfyui/sonic/{audio2bucket,audio2token,unet}.pth
models/sonicLipsyncFor_comfyui/sonic/{RIFE/flownet.pkl, whisper-tiny/, yoloface_v5m.pt}
workflows/DBZ-Voice-Sonic-Lipsync.json
```

That workflow is `LoadImage → SONICTLoader → SONIC_PreData → SONICSampler` on an
`ImageOnlyCheckpointLoader`. **Sonic animates a single still portrait from
audio.** It cannot take an existing 15-second two-hander and replace the mouths
while preserving the original motion. It is the wrong shape of tool for this.

| Option | Cost | Verdict |
|---|---|---|
| Single-pass ref2va at 0.9 MP | 0 | Test first — removes the problem |
| Wav2Lip | ~500 MB | Only in-budget video-to-video option; 96×96 mouth crop looks soft at 1280×736 |
| LatentSync 1.5 | ~5 GB | Better, but out of budget on a phone hotspot |
| Sonic | 0 | Single-portrait only |

**On whether mouths should move: yes, they should.** Two reasons. Lipsync models
mask and regenerate the lower face, so a still mouth buys nothing, and a rigid
face under a moving mouth reads as pasted-on. More importantly, dialogue in the
prompt drives the turn, the gesture and the reaction — strip the lines and H3
stops performing the scene, and no lipsync pass gives that back.

---

## 6. Voice references — rebuilt 2026-08-13, v1 was wrong

`outputs/equal_shares/voice_reference_map.json`, plus a WAV per character at
`outputs/equal_shares/voices/<slug>/h3_voice_ref.wav`.

**Selection rule — two steps, cheap filter first.**

1. **From the script.** Only clips where the character is the **sole speaker**
   and their scripted lines fill at least **55%** of the clip. A clip that is 13
   seconds of one person talking is the right shape; four words at the end is
   not, however clean those four words are. Free — reads `story_config.json`.
2. **From the audio.** Confirm the take actually contains one **contiguous
   speaking passage**, using `work/speech_density.py`. The script says what was
   asked for; only the audio says what H3 delivered.

**One contiguous passage from one take. Never stitched, never concatenated.**
Splicing two passages teaches an average of two deliveries — the exact drift the
reference exists to prevent. Natural breath pauses up to 1.0 s stay inside a
passage, but the span must be at least 60% actual speech.

### The 11 that have a reference

| character | speech | density | source clip |
|---|---|---|---|
| Narrator | 15.1 s | 100% | `00B` |
| Avery | 13.2 s | 94% | `25B` |
| Volunteer | 12.3 s | 90% | `14B` |
| Kent | 12.1 s | 87% | `16E` |
| Doris recording | 11.8 s | 88% | `22B` |
| Faith White | 8.7 s | 78% | `10B` |
| Ryann Sally | 7.8 s | 72% | `24B` |
| Housing representative | 7.7 s | 96% | `18A` |
| Doris | 7.1 s | 85% | `13B` |
| Congregation member | 5.6 s | 84% | `20B` |
| Terminal voice | 4.9 s | 87% | `11B` — **thin** |

### The 7 that need a purpose-built VOX clip

None of these has a single clip where they are the only speaker talking for most
of the shot, so **no reference is invented for them.** Specs are written to
`outputs/equal_shares/voice_reference_vox_specs.json`:

`Aid worker` · `Council member` · `Crew lead` · `Male Visitor One` ·
`Male Visitor Two` · `Unhoused man` · `Wealthy commuter`

Each needs one 15 s clip, 0.2 MP, single anchor, **one person in frame speaking
continuously from 1 s to 14 s**, with fresh filler dialogue in that character's
register — never film dialogue, so a leaked clip is obviously not part of the
story. Judge on audio only; gibberish words are fine, this is a timbre
reference. Seven clips, roughly an hour.

Never add VOX clips to `story_config.json`, `manifest.json`, or the completion
audit.

Their **stale v1 files are quarantined** as
`voices/<slug>/h3_voice_ref.V1_REJECTED_DO_NOT_USE.wav`. Do not wire those.
`build_audio_pass_prompts.py` now warns for each of the 8 places they were
referenced, in `00D`, `00D2`, `01B`, `27E`, `28C` and `30B`.

## 7. A correction to earlier project notes

**An earlier pass reported 96% dialogue accuracy from `validation_transcripts/`.
That figure is wrong. Do not rely on it.**

Only 6 of 138 transcript files carry an `expected` field. The other 132 record
`coverage: 1.0, similarity: 1.0` as a default with no comparison ever performed.
`11C` scores a perfect 1.0 next to the recognised text `"< Examined and I was not
view it as the absent here black a mutually group requires"`.

Measured properly on the 6 that can be measured: median word recall **0.70**,
3 of 6 clear 0.8.

**The film-wide dialogue accuracy rate is unknown.** It is measurable on CPU with
no download and no GPU, using `work/transcribe_windows_speech.ps1` against the
selected takes in `manifest.json`, compared to `dialogue_timing` in
`story_config.json`. Run it while the GPU renders — it tells you how many
re-rolls stage 1 will actually need.

### The voice references were rebuilt on 2026-08-13 — v1 was wrong

The first reference set was cut from the scripted `dialogue_timing` window and
checked with mean dB. **Both were wrong, and listening caught it, not the
metric.**

* `dialogue_timing` is when a line is *scripted*, not when speech occurs. H3
  comes in early by about a second and often does not fill the window.
* Mean dB cannot tell speech from noise. Kent's reference came from `14D`, the
  **driving clip** — 14.6 seconds of road and engine with about 2 seconds of
  dialogue in it. It measured −19.9 dB mean and "100% voiced" under a −35 dB
  silence gate, because engine noise never drops below the gate.

Kent's replacement, from `16E`, has **12.1 seconds of speech at 87% density**.
Across the set, 7 characters turned out to have no usable reference at all,
where v1 had confidently produced one for all 18.

The lesson generalises: **level is not speech, and a scripted window is not a
delivered one.** `work/speech_density.py` now scores speech by spectral band
ratio and is calibrated against known-good and known-bad files.

Related: the "silent clips" list (`04C`, `06A`, `14B`, `14E`, `16E`, `17C`) came
from speech *recognition* failing, not from an absence of audio. `14B` measures
−23.7 dB, which is real signal. The two are different tests and earlier notes
conflated them.

---

## 8. Hard-won prompt rules

**What works**

- **Quotation marks mean speech, and only speech.** A quoted string with no named
  speaker gets assigned to the nearest person in the beat. Highest-value rule
  found. `00M` had the stage direction `his expression cools on the word "but"`
  — that could be performed as dialogue. Quote marks are now stripped from all
  stage direction.
- **Every second must be in a timed beat.** Undirected time gets invented. `10B`
  had nothing scripted after 3 s and filled the room with 8–10 people.
- **Every countable action states its integer.** "They repeatedly offer the
  chair" gave one limp gesture; "exactly three offer-and-refusal exchanges, no
  more and no fewer" gave three.
- **Per-beat mouth locks.** "Mouth closed" belongs inside the beat that gives
  someone business, not only in a rule at the bottom.
- **Name a discriminator between similar characters.** The two visitors wear
  near-identical suits; the standing one has a white pocket square. Stating that
  stops role swaps.
- **Light interiors generously even when the mood is sombre.** The daylight
  driving clip `14D` is among the cleanest; the dim interiors in scenes 13, 16
  and 17 are the worst.

**What does not work**

- **Repetition.** Saying a thing twice is not emphasis — the model must
  reconcile two copies and guess which governs.
- **Contradiction after an edit.** Adding dialogue leaves stale absolutes
  behind: "nobody speaks to anybody" three sentences below someone who now
  speaks.
- **Copying prompt text out of the CSV.** CSV wraps fields in quotes and doubles
  internal quotes. **0 of 7 quote-wrapped prompts were ever kept.**
- **Describing something not in the shot.** Anything you tell the model to light,
  it may draw.
- **Two people in the same screen position across two anchors** — the model grows
  one into the other.

---

## 9. Review rules

**Contact sheets rank what to look at first. They never pass anything.** A
machine pass over sheets caught every large-area fault — invented crowds,
duplicate bodies, camera jumps, burned-in text — and missed **every** face-level
fault, because a face at reduced scale is unreadable. "No fault visible at
reduced scale" means not reviewed, not passed. Faces need native-resolution
frames.

**Instability scores are for ranking, never verdicts.** `16A` scored highest of
anything unreviewed and was a clean pass — the spike was a character standing up.

**Reject for:** warped, duplicated, merged, disappearing or anatomically wrong
bodies; broken faces, hands, fingers, limbs, or object interactions; identity,
wardrobe, location, architecture or screen-direction drift; unintended people;
wrong blocking; role swaps; actions contradicting the script; severe flicker;
temporal morphing; visible gibberish text.

**Never reject a visually correct take for gibberish speech or wrong music.** All
H3 audio is discarded and replaced in post.

**Upscaling does not repair anatomy or identity drift.** Broken footage is
regenerated, shortened, or cut — not enhanced.

**Salvage before regeneration:** vary prompt and seed at 20 steps → simplify
motion → shorten → clean cut or approved-frame hold → an insert built from
approved frames. A new boundary image is the last resort.

---

## 10. Continuity locks

**Opening.** The receptionist is the only woman and never leaves the staff-only
window. Exactly two male visitors perform the chair interaction, both entering
through the separate doorway and remaining on the public side. One public chair,
screen-left. No glass gate, fence, invented divider, extra chair, or third man.
The Narrator appears only where the script places him and never resembles Kent.

**Identity.** `references/alex_vale_master_v1.png` is authoritative for Kent
Brentwood. `references/ensemble_cast_master_v1.png` shows, left to right, Kent
Brentwood, Avery Renfield, Doris Lovelay, Ryann Sally, Faith White. Those faces
and clothes override any prose description.

**`04C`.** Kent has already declined before the clip begins. No bill, donation,
transaction, or reaching toward the plate. Attempt 4 is accepted; attempt 3 must
never be reselected.

---

## 11. Operating rules

- **One backend on port 8188, ever.** Before launching anything, check all
  three: running python/ComfyUI processes, whether 8188 is listening, and the
  tail of `runtime/render_supervisor.log` against the clock. If that log is
  advancing, the render is alive — monitor it, never duplicate it.
- **One clean backend per clip.** Start ComfyUI, render one clip, stop it, clear
  GPU, repeat. ~8 minutes per clip. 124 clips rendered this way with no VRAM
  failure.
- **Never delete a raw attempt.** Everything stays under
  `A:\Users\rhine\ComfyUI-Shared\output\story\<clip-id>\`. Reject with
  `work/reject_clip_visual.py`, which records the rejection without deleting.
  Never overwrite an approved reference — save new versions.
- **If a deletion or overwrite would be needed, don't pause and don't delete.**
  Keep the original and write a versioned sibling, copy rather than move, or
  quarantine an obsolete generated intermediate.
- **Do not hand-edit `manifest.json` or `visual_audit.json` while a render is
  live.** The runner merges only the current clip's record so concurrent review
  decisions survive; a manual write defeats that.
- **Bandwidth: the user is on a phone hotspot. Download nothing** without
  reporting the size and getting agreement first.
- **Completion gate:** `work/audit_equal_shares_completion.py`. Not complete
  until 124/124 valid, every clip visually passed, all raws preserved, all
  assembly clips exist, and a 1344×768 H.264 master with synced AAC sits within
  two seconds of 1266 s.

---

## 12. Folder map

Root, after the 2026-08-13 cleanup:

```
CHATGPT_HANDOFF.md              this file
CLAUDE.md                       standing rules, binding, auto-loaded
README.md                       folder index
RESUME_PROMPT_00J_AUDIT.md      the immediate next action
CLAUDE_CODE_AUDIO_FIRST_PROMPT.md   Tasks 0–5 in operational detail
CLAUDE_CODE_PROMPT.md           partly superseded; banner explains which parts
PROJECT_CONTINUATION_BRIEF.md   background state
docs/                           reference material
work/                           scripts
outputs/equal_shares/           config, prompts, audio, manifests, audits
archive/                        superseded material, kept as evidence — nothing
                                in here is current
```

Key files under `outputs/equal_shares/`:

| path | what |
|---|---|
| `story_config.json` | authoritative for prompts, timing, frames, anchors |
| `manifest.json` | per-clip selected take and `comfy_source` |
| `visual_audit.json` | acceptance — `reviewed_pass` holds the 43 |
| `prompts_audio_pass/` | 78 rewritten dialogue prompts |
| `prompts_no_dialogue/` | the other 46 prompts — together these are all 124 |
| `ref2va_proven_workflow.api.json` | the graph from `ComfyUI_00108`, ready to POST to `/prompt` |
| `ref2va_proven_workflow.ui.json` | the same graph, loadable in the ComfyUI editor |
| `voice_reference_vox_specs.json` | the 7 voice-reference clips still to render |
| `audio_pass_config.json` | per-clip speakers and ordered ref_audios |
| `voice_reference_map.json` | one voice reference per character |
| `voices/<slug>/h3_voice_ref.wav` | 18 reference WAVs |
| `audio/dialogue/` | 113 Kokoro per-line WAVs — the fallback, do not overwrite |
| `audio/EQUAL_SHARES_DIALOGUE_TIMELINE.wav` | 1266.000 s, do not modify |

Key scripts under `work/`:

| script | what |
|---|---|
| `build_voice_reference_map.py` | picks and cuts the per-character references |
| `build_audio_pass_prompts.py` | rewrites dialogue prompts into the proven structure |
| `analyze_takes.py` | reads the API graph out of ComfyUI PNGs |
| `prompt_integrity.py` | quote / encoding faults |
| `reject_clip_visual.py` | records a rejection without deleting |
| `transcribe_windows_speech.ps1` | on-device speech recognition, no download |
| `render_until_complete.py` | the one-backend-per-clip render loop |
| `audit_equal_shares_completion.py` | the completion gate |

---

## 13. Also on the Desktop

`A:\Users\rhine\Desktop\EQUAL_SHARES_GENERATION_LIST\` holds a manual-paste
working set: `index.html`, `generation_list.csv`, `prompts/` (124),
`prompts_audio_pass/` (78), `voice_refs/` (18 WAVs), `thumbs/`, and copies of
the current docs.

---

## 14. Open items

1. **Finish the 00J audit** and branch. Everything else waits on it.
2. **Render 7 VOX voice-reference clips** for the characters with no usable
   reference — specs in `outputs/equal_shares/voice_reference_vox_specs.json`.
   About an hour, and it unblocks `00D`, `00D2`, `01B`, `27E`, `28C`, `30B`.
3. Diagnose the empty Windows Speech transcription.
4. Measure real dialogue accuracy on CPU (section 7).
5. 51 clips never visually reviewed; 22 confirmed rejects need regeneration.
6. Stale `blocked` statuses in `voice_approval_gate.json` — needs
   `init_gate(force=True)`.
7. Wire `render_priority.json` into `render_until_complete.py`, and
   `audio_decisions.py` output into `assemble_story.py`.
8. Add 3 visitor lines to the Kokoro timeline — expect 116 segments, still
   1266.000 s.

---

## 15. Why things are the way they are — decision log

Every rule above came from a specific failure. This section gives the reasoning,
so you can tell when a rule still applies and when a situation is genuinely new.
**Do not treat these as arbitrary conventions.** Most of them cost hours to
learn.

### Why this folder is canonical, and the parent is not

A sync watcher used to mirror this folder from the parent tree. It **died at
02:22 on 2026-08-10** and nobody noticed for some time. The render supervisor
was later restarted pointing at *this* folder. So the parent's `manifest.json`
froze at 44 clips while this one kept advancing.

Both trees look plausible. That is the danger. The dead sync files are kept in
`archive/stale_state/` as evidence rather than deleted, so that anyone who finds
a reference to them can see why they are not to be trusted.

### Why exactly one backend, ever

One GPU, and MiniMax H3 at these settings consumes most of its VRAM. Two
ComfyUI processes bound to port 8188 means one dies or both thrash.

The pattern that works: **start a clean backend, render one clip, stop it, clear
GPU state, repeat.** ~8 minutes per clip. 124 clips completed this way with zero
VRAM failures. A long-lived backend accumulates state and eventually fails
mid-render, which is worse than the startup cost.

This matters more than usual here because several agents have touched this
project — Claude Code, Codex, Open Interpreter, and manual ComfyUI sessions —
and any of them can start a backend. Hence checking three things before
launching, not one.

### Why 0.9 megapixels, and why the window is narrow

**This was a resolution problem masquerading as a prompt problem.** At 736×416,
a face in a medium shot is 20–30 pixels. Identity cannot survive there. Six
clips were rejected purely for face distortion and no wording fixed any of them.

Then the measurements:

| MP | result |
|---|---|
| 0.3, 0.4 | faces warp |
| **0.9** | face fixed, camera still obeys the prompt |
| 1.0 | camera broke — on clip 11 it fell through the ground into a different cityscape |

So the usable window is roughly 10% wide. Above it the model starts
hallucinating geometry; below it faces collapse. 0.8 is the floor for a VRAM
drop, and going lower should be reported rather than done silently.

Reference frames are already 1672×941, so raising megapixels needed no new
assets. That is why this was cheap to fix once identified.

### Why `ResolutionSelector` megapixels, not width and height

When that node is in the graph it computes width and height itself. The
`width`/`height` fields in `story_config.json` are then **dead tokens** — they
sit there looking authoritative and control nothing. They said 736×416 long
after the real resolution had changed, which is exactly the kind of thing that
sends someone down a wrong path for an hour.

### Why the frame count rule

MiniMax H3 requires frame counts congruent to 5 modulo 17. Round up to the next
such value. Every correct render obeys it: 8 s → 192, 10 s → 243, 12 s → 294,
15 s → 362. Get it wrong and the render fails or the duration drifts.

### Why ref2va at all — the voice problem

H3 **re-derives a voice from the prompt on every render.** Same mechanism as
faces: nothing carries between clips, so the same character sounds like a
different person in every scene. Retrying does not help, because there is
nothing to converge on.

`ref2va` is the only checkpoint that accepts an audio reference. Give it a fixed
sample and the timbre stops drifting. That is the entire reason for the
checkpoint switch — not quality, not speed.

### Why the prompt rewrite mattered more than the checkpoint

Two faults, both structural:

**Indirection.** The story prompts put `Narration phrase 1 of the assigned line
plays over` in the timed beat and kept the real words in a separate block. The
model had to work out which words belonged to which second. The one prompt that
produced correct timing put the words *inside* the beat.

**Double-sending.** 73 of 78 dialogue clips sent every line **twice** — once in
the prompt body, once in the AUDIO LOCK the runner appends. Repetition is not
emphasis; the model has to reconcile two copies and guess which governs.

This is the general principle behind several rules: **say each thing exactly
once, in the place where it applies.**

### Why quotation marks are treated so strictly

A quoted string with no named speaker gets assigned to the nearest person in the
beat. This is the highest-value rule found in the project.

Consequences observed: **0 of 7 quote-wrapped prompts were ever kept** — copying
prompt text out of the CSV wraps the whole field in quotes and the model tries
to speak it. And `00M` carried the stage direction `his expression cools on the
word "but"`, which could be performed as dialogue. Quote marks are now stripped
from all stage direction automatically.

### Why Kokoro and RVC exist, and why they are still the fallback

Kokoro TTS gives **correct words, one fixed voice per character, and exact
timing** — `EQUAL_SHARES_DIALOGUE_TIMELINE.wav`, 1266.000 s, 113 segments. A
fixed voice cannot drift, which was the whole problem.

RVC was chosen over a zero-shot TTS cloner for one specific reason: **voice
conversion does not change duration.** Lines are placed at absolute offsets, so
the 1266 s timeline survives. A TTS cloner regenerates the audio and the timing
moves. Narrator, Kent, Ryann Sally and Avery have trained RVC models.

The ref2va approach may beat both, because H3 audio is a performance rather than
synthesis. But Kokoro remains the guaranteed-correct fallback, which is why
nothing overwrites `audio/dialogue/` or the timeline WAV.

### Why a voice reference is verified by ear and by spectrum, not by level

This one was caught by the user listening, after two automated checks passed it.

A mean-dB check passes a file that is 3 seconds of speech and 12 of silence,
because the mean is respectable. A silence-gate check passes a car interior,
because engine noise never drops below the gate — that is how Kent ended up with
14.6 seconds of road noise scored as "100% voiced".

What actually separates voice from engine rumble is **where the energy sits**:
speech puts most of its power in roughly 300–3400 Hz, engine noise below 300 Hz.
`work/speech_density.py` scores that ratio per frame, and was calibrated against
known ground truth — Kokoro TTS lines that must score high, Kent's driving clip
that must score low — rather than tuned until the numbers looked nice.

An early setting of the band gate at 0.45 rejected a pure Kokoro speech file at
35%, because a deep male voice puts a lot of energy in its fundamental below
300 Hz. That is why the gate sits at 0.25. **Calibrate against both a positive
and a negative, never one file.**

### Why the reference is filtered on the script first

Searching every take's audio is slow and finds fragments. Reading
`story_config.json` for "is this character the only speaker, and do their lines
fill most of the clip" is free and eliminates almost everything unsuitable in
one pass. Audio analysis then only has to confirm the handful that survive.

Cheap filter first, expensive confirmation second — and never the confirmation
alone, because the script says what was asked for and the audio says what H3
actually delivered.

### Why 7 characters get a purpose-built clip instead of a salvaged one

For seven speakers there is no clip anywhere in the film where they are the only
person talking for most of the shot. Their lines are two to six seconds, buried
in scenes with other characters.

Mining a reference out of that means either splicing fragments — which teaches
an average — or accepting two seconds, which barely constrains timbre. A
purpose-built 15-second clip whose only job is to make that character talk
continuously costs about eight minutes and produces a far better reference. The
content is irrelevant, so it uses fresh filler dialogue rather than film lines,
which also means a leaked clip is obviously not part of the story.

### Why a voice reference must be one take

Concatenating two takes to reach a length minimum splices two different-sounding
performances and teaches the reference an average of both — the exact drift the
reference exists to prevent. Hence: one take, 2–15 s, one voice, and prefer a
window where the character speaks alone.

And why RMS-verify them: `male_visitor_two`'s window looked fine in the config
and turned out to be room tone at −40.8 dB. Configuration is not evidence.

### Why "validation is not acceptance"

The supervisor logs `Progress N/124 valid clips`. That counts renders that
produced a file of the right duration with visual detail. It says nothing about
whether the clip is usable.

Reporting it as an acceptance count has caused false confidence more than once
in this project. Real acceptance is 43.

### Why contact sheets cannot pass a clip

A machine pass over overview, ending and every-second sheets caught **every**
large-area fault — invented crowds, duplicate bodies, camera jumps, burned-in
text — and missed **every** face-level fault. A face at reduced scale is
unreadable, so "no fault visible" means the face was never actually inspected.

Related: instability scores are useful for deciding what to look at first and
useless as verdicts. `16A` scored highest of anything unreviewed and was a clean
pass; the spike was a character standing up.

### Why nothing is ever deleted

The salvage ladder depends on old attempts — an earlier take often supplies a
usable frame, a closing anchor, or an insert. Rejections are recorded, not
enforced by deletion, so a rejected take can be reconsidered when the
alternative is a re-render.

It is also simple evidence hygiene: several conclusions in this project were
overturned later, and they were only reviewable because the raw files still
existed. The same reasoning is why the 2026-08-13 cleanup **moved** 24 files
into `archive/` rather than removing them.

### Why bandwidth is a hard constraint

The user is on a phone hotspot. LatentSync at ~5 GB is not a download decision,
it is a several-hour decision. Always state a size and get agreement first.

### Why the accuracy correction is called out so prominently

An earlier pass reported 96% dialogue accuracy and it was wrong — the metric was
reading default values, not comparisons. That number, if believed, makes the
whole audio-first plan look unnecessary: if H3 already says the right words 96%
of the time, why build a voice-harvest stage?

The real figure is unknown, and the measurable subset gives 0.70. **A wrong
number that points at the wrong plan is worse than no number.** Hence the
explicit correction and the CPU job to measure it properly.

### Why the lips stay moving

Every video-to-video lipsync model masks the lower face and regenerates it from
the audio. It overwrites the mouth, so a closed mouth buys nothing — and a rigid
face under a moving mouth reads as pasted-on, because jaw, throat and head
motion no longer agree with the speech.

The stronger reason is that dialogue in the prompt drives more than the mouth:
the turn, the gesture, the reaction, the pause. Strip the lines and H3 stops
performing the scene. No lipsync pass gives blocking back.

And there is a fallback argument: if lipsync is skipped or fails, a clip with
natural speech motion is still usable. A clip of silent people with dubbed audio
is not.

### Why one test clip before committing

The cost asymmetry. If ref2va holds at 0.9 MP, the film needs ~124 renders and
no lipsync stage. If it does not, ~248 renders plus a lipsync pass plus a
download. That is roughly 17 hours against 38 or more.

Eight minutes of rendering decides which. Almost nothing else in this project
has that ratio, which is why it comes before everything else.

### Why several handoff prompts exist and only some are current

The project has been handed between agents repeatedly, and each handoff wrote
its own prompt. Most describe completed or abandoned work. They are archived
rather than deleted because they document what was tried.

The trap is that some of them state settings as absolutes — `CLAUDE_CODE_PROMPT.md`
still mandates fl2va at 736×416, and `CLAUDE.md` itself did until 2026-08-13.
Anything asserting 736×416 or 0.3 MP as current is out of date, whatever its
tone of authority.

---

## 16. What lives outside this folder

Every **document** you need is in the handoff folder. Four things are not, by
design, and you need read access to them:

### `A:\Users\rhine\ComfyUI-Shared\` — required

| path | what | why it is not here |
|---|---|---|
| `output\story\<clip-id>\` | every raw generation ever made | tens of GB; the archive of record |
| `output\story\TEST_09MP_00J\` | **the clip you are auditing first** | raw render |
| `output\video\1.mp4` | the `00A` keeper, Narrator on camera | raw render |
| `output\ComfyUI_00108.png` | the winning generation | its graph is now also extracted, below |
| `models\diffusion_models\` | `minimax_h3_ref2va_pruned_nvfp4`, `minimax_h3_fl2va_pruned_int8_convrot` | multi-GB weights, verified present |
| `models\text_encoders\`, `models\vae\` | `qwen3vl_32b…`, both H3 VAEs | verified present |
| `models\sonic\`, `models\sonicLipsyncFor_comfyui\` | the only lipsync tooling on the machine | see §5 |
| `workflows\DBZ-Voice-Sonic-Lipsync.json` | shows Sonic is portrait-only | — |

**You do not need to parse `ComfyUI_00108.png` to get the proven graph.** It is
extracted into this folder as
`outputs/equal_shares/ref2va_proven_workflow.api.json` (POST to `/prompt`) and
`ref2va_proven_workflow.ui.json` (open in the editor). The PNG remains the
original evidence.

### `A:\Users\rhine\Desktop\EQUAL_SHARES_GENERATION_LIST\` — convenience only

The human's manual-paste working set: `index.html`, `generation_list.csv`,
`prompts/` (124), `prompts_audio_pass/` (78), `voice_refs/` (11 live plus 7
marked `V1_REJECTED_DO_NOT_USE`), `thumbs/`, and mirrored copies of the current
docs. Nothing here is authoritative — the handoff folder is. It exists so the
user can paste prompts into ComfyUI by hand without digging through JSON.

### The ComfyUI install — required to render

`A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\`, python at
`.venv\Scripts\python.exe`. Not mirrored anywhere.

### `...\referenced-chatgpt-conversation-this-is-an-2\outputs` — **do not read**

The stale fork, frozen at 44 clips. Listed only so you recognise it if you find
it. See §15 for why it exists and why it is dangerous.

---

## 17. Completeness check

Verified 2026-08-13 02:40. Every path referenced by the current documents
resolves, either inside this folder or in the external locations in §16.

| | |
|---|---|
| prompts | **124** — 78 in `prompts_audio_pass/`, 46 in `prompts_no_dialogue/` |
| voice references | **11** live WAVs, matching 11 entries in `voice_reference_map.json` |
| voice clips still to render | **7**, specs in `voice_reference_vox_specs.json` |
| quarantined v1 references | **7**, named `*.V1_REJECTED_DO_NOT_USE.wav` |
| audio-pass config | 78 clips, 8 warnings — one per place a missing reference is used |
| proven ref2va graph | extracted to JSON, both API and UI form |
| boundary frames | 240 PNGs in `outputs/equal_shares/frames/` |
| identity references | 8 PNGs in `outputs/equal_shares/references/` |
| models | all 5 required checkpoints confirmed present in `ComfyUI-Shared\models\` |
| state files | `manifest.json`, `visual_audit.json`, `story_config.json`, `runtime/render_priority.json`, `runtime/voice_approval_gate.json` all present |

Two things are referenced but **do not exist yet, by design** — you create them:
`work/render_audio_pass.py` and `outputs/equal_shares/audio_pass_manifest.json`.
