# Equal Shares specialist reference

This is reference material for the Equal Shares project, a 21-minute film built
as 124 MiniMax H3 clips in ComfyUI on this Windows machine. It is
not the local agent's identity or default task. Apply it only after the current
operator request explicitly identifies Equal Shares, MiniMax H3, an Equal
Shares clip identifier, or an Equal Shares project file/path.

# The one rule above all others

A change is **not verified** because the config and the docs agree, because a
drift check is clean, or because regenerated files look right. All three passed
on 2026-08-16 while the renderer sent a corrupted prompt to every clip.

Verified means: the workflow embedded in a real render was extracted
(`ffprobe -show_entries format_tags=prompt` on the MP4, or the PNG metadata) and
diffed against `docs/GOLDEN_REFERENCE/GOOD_AUDIO_GRAPHS.json`. If that has not
been done, say the change is **unverified**.

# Render settings — identical across all 15 proven-good renders, never change them

| | |
|---|---|
| UNet (with references) | `minimax_h3_ref2va_pruned_nvfp4.safetensors` |
| UNet (no references) | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| Text encoder | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| VAEs | `minimax_h3_video_vae_fp16` + `minimax_h3_audio_vae_fp32` |
| Sampler / scheduler | `res_multistep` / `simple`, denoise 1.0 |
| Steps | 20 |
| Megapixels | **0.2** for soundtrack, 0.9 first for picture |
| fps / bit depth | 24 / 8-bit |
| Frame count | must be congruent to **5 modulo 17** |

Turbo checkpoints, Turbo nodes and Turbo LoRAs are **prohibited**.

# The prompt format

Six sections in this exact order — **nothing above `subject_definitions:`**.
A prepended header is the most expensive fault in this project's history.

```
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
```

Tags: `<Subject N>` visible content, `<Picture N>` frame anchor, `<Audio N>` voice
reference. Tags follow wiring order. Limits: 9 images, 3 audio.

Key rules (each from a failed render):
1. `retention_analysis` must declare every reference; a voice master is always `reference`.
2. One scripted line = one `<d>[English] …</d>` block. Split = gibberish at the seam.
3. Delivery before the closing tag; mouth closes after `</d>`. Prose after reads as speech.
4. Quotation marks = on-screen lettering. Speech goes in `<d>`.
5. `[Shot N]` = a cut. One continuous take = one `[Shot 1]`. `[0-1 s]` is not H3 grammar.
6. `non_diegetic_music: N/A` for this film.

Use `search_docs` to retrieve a real prompt example or the full rule context.

# Two rules about voices

**One-off speakers need nothing.** ONE clip → no voice master, no `<Audio N>`.
A clip with no recurring speaker uses `MiniMaxH3ImageToVideo` with no references.

- recurring, need a master (10): Avery, Doris, Faith White, Housing representative, Kent, Male Visitor One, Narrator, Ryann Sally, Terminal voice, Volunteer
- one-off, need nothing (8): Aid worker, Congregation member, Council member, Crew lead, Doris recording, Male Visitor Two, Unhoused man, Wealthy commuter
- clips with no references: 01B, 20B, 22B, 30B
- mixed clips: 00D2, 27E, 28C

**Duration ladder.** Gibberish or mispronounced words → retry by changing
**duration** (base, +1, −1, +2, −2, +3, −3 s), seed held fixed. A doubled voice
is a `retention_analysis` fault, not a duration fault.

# Current state — regenerated 2026-09-25T21:23:11

- 124 native prompts; 78 dialogue clips;
  45 shortened for soundtrack pass (padded back at assembly)
- soundtrack manifest: **0** clip records
- voice auditions: **0 rendered, 0 chosen**
- provisional/unapproved masters: Male Visitor One, Male Visitor Two, Wealthy commuter, Unhoused man, Terminal voice, Council member, Crew lead, Aid worker

**Soundtrack pass blocked** until voices are chosen; only the Narrator is approved.

# Standing constraints

- One ComfyUI, ever (port 8188). Never delete raw renders, references, manifests.
- No downloads without stating size. No hand-edits to generated prompts.
- No picture rendering until audio gate = 124/124 accepted.
- Every change gets a CHANGELOG/ entry: what, why, evidence, verified, unverified.
