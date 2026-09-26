# 2026-09-26l — `render_video_from_reference`: segment chaining built (opt-in), the held-frame seam measured as a visible cut, and the 26k "RAM scales with frames" model found wrong (RAM is weight-bound, ~13–15 GB per prompt whatever the length)

Operator brief: `motion-transfer-chaining-prompt.md` (chunk a long clip into
segments, last frame of one seeding the next, like the MiniMax chain; investigate
first whether AnimateDiff can be seeded from a real frame, and say so plainly if
not). Continues `2026-09-26k`. Id claimed once with `scripts/next_changelog_id.py`.
Benign inputs only (the 15.08 s single-take hallway clip
`ComfyUI-Shared/output/story/VOX_HOUSING_REPRESENTATIVE/attempt_1_00001_.mp4`,
read only; the Kent master copy). Nothing downloaded or installed. Stopped at
the operator's request mid-investigation ("get to a good stopping point"); the
open work is in `motion-transfer-chaining-handoff-26l.md`.

## 1. What was built (`local_agent/motion_transfer_render.py`, LF; `_edit_26l_chain_render.py`, 16 exact anchors + a whole-function replace of `run_job`, md5-checked)

- `plan_segments(total, seg_new, held)`: balanced segments of ≤ `seg_new` new
  frames; segment i > 0 also re-renders the previous segment's last `held`
  frames (`source_offset = delivered − held`), so the pose maps of the held
  frames match their content. `HELD_FRAMES = 4`, `SEGMENT_FRAMES_DEFAULT = 64`,
  `MAX_CHAIN_FRAMES = 600` (a time budget, not a measured run).
- `prepare_request`: `chain` (true/false/omitted) and `segment_seconds`.
  **Chaining is opt-in** (`chain: true` or `segment_seconds`); an unchained
  request over 180 frames is refused as before, the message now naming
  `chain=true` as experimental. Auto-chaining was the first cut and was turned
  off once §3 measured the seam. A chained spec carries `segments`,
  `segment_frames`, `held_frames`, `init_mode`; `frames` still means delivered
  frames; `windows` is the sum over segments.
- `build_graph(spec, inputs, prefix, segment=None)`: `segment=None` is the
  2026-09-26j graph byte-for-byte (`template_sha256()` unchanged,
  `d2943a9d…1ffc8d`). A segment with held frames adds nodes 30–35:
  `VHS_LoadImagesPath` (held PNGs) → `VAEEncode` → `LatentBatch` ahead of the
  smaller `EmptyLatentImage` → `VHS_LoadImagesPath` (one mask PNG per frame,
  black = keep) → `ImageToMask` → `SetLatentNoiseMask` → KSampler at denoise
  1.0. Pinned as `template_sha256(chained=True)` = `00bd278d…4ba2cf`. An
  `img2img` init mode (last held frame repeated, partial denoise, nodes 30/36/31)
  exists for the investigation only and is not a tool parameter.
- Why the noise mask: core `KSamplerX0Inpaint` (`comfy/samplers.py:630`) blends
  masked-out frames back to the init at every step and at the output;
  `comfy.utils.reshape_mask` keeps a per-frame mask batch; AnimateDiff-Evolved's
  `sampling.py` never touches `denoise_mask`, so the context windows see the
  held frames as ordinary batch members. All new node classes validate against
  the 2026-09-21 `object_info` dump offline and against the live backend.
- Runner: one backend for the whole job; per segment: its own 8 track samples
  (`choose_target(..., prev_centre)` keeps following the same person), its own
  band mask, `write_segment_inputs` (byte copies of the previous segment's last
  4 final-stage frames + the mask batch under `segNN/{init,noise_mask}/`),
  graph validation, the same thermal start rule as a job between segments,
  render, collect with sha256, `manifest.json` rewritten after every segment.
  Then `stitch_frames` (hard links of the delivered frames → ffmpeg h264 crf 17
  → `final_chained.mp4`), `sequence_metrics` (frame-to-frame mean |diff| along
  the delivered clip with each seam called out, round-trip diff of held frames,
  per-frame mean RGB), the identity score over the delivered frames.
  `verified_outputs` needs every segment's counts = its frames, delivered =
  planned, and the stitched mp4's `nb_frames` = planned. `_GpuSampler` now also
  samples system RAM (psutil `used`) every 2 s; `ram_frames(spec)` /
  `rendered_frames(spec)`; `job_status` reports `segments_done/total`,
  per-segment RAM/VRAM peaks and the seams.
- `tools.py` (LF; `_edit_tools_26l_chain.py`, 6 anchors, md5-checked, then two
  small text fixes): RAM refusal on `ram_frames`, launch result with
  `chained/segments/segment_frames/held_frames/rendered_frames`, estimate on
  rendered frames, `segment_seconds` + `chain` in the schema, description marks
  chaining EXPERIMENTAL with the seam finding. `agent.py`, `remote_security.py`
  untouched. **The GUI server must be restarted to load the new `tools.py`.**
- Text: doc §7 limits, `motion_transfer.py` AnimateDiff `why`, `TODO.md` note
  (CRLF files kept CRLF).

## 2. Tests

`test_motion_transfer_render.py` 34 → **57**: refusal unless chain is asked
for, chain=true on the 70 s clip (9 segments, 565 delivered / 597 rendered,
RAM checked for 67 frames not 565), short clips keep the single path (`chain:
true` on one segment is still one job), `segment_seconds` forcing and
validation, the 600-frame cap, `plan_segments` coverage/overlap invariants,
`_windows`, `prev_centre` tracking, both template pins, first segment ≡ single
graph, the held graph node by node, the img2img graph, `write_segment_inputs`
(byte equality, mask values), `stitch_frames` (link order + ffmpeg argv; real
ffmpeg run when installed), `sequence_metrics` on synthetic PNGs, chained
`job_status` in progress and complete, the chained tool launch. Also fixed a
pre-existing fragility: three wrapper tests called the real free-RAM probe and
failed when the suite ran beside a live render (2.6 GB free); `_gates` now stubs
`ram_check`.

`python -m unittest test_motion_transfer_render test_remote_tool_allowlist
test_motion_transfer_plan` → **80 OK**. Full non-live suite
(`runtime/motion_transfer_20260925/full_26l_a.log`, run beside the held render
before the stub): **1772 tests, 3 failures, all the RAM-probe fragility above**;
not re-run after the fix and after the opt-in change (GPU still busy) — **the
next agent must re-run it.**

## 3. Seam investigation, run 1: held frames + noise mask (`chain_investigate_26l.py held`; job `mtr_20260926_132450_0bc483`, through `tools.call`)

0–4 s at 12 fps = 48 delivered frames as 24 | 4 held + 24 (52 rendered), face
detail on, seed 20260925, same prompt as 26k. Backend start 97.7 s.

| | seg 1 | seg 2 |
|---|---|---|
| frames (held) | 24 (0) | 28 (4) |
| prompt / history | `4650e50d…` success | `fb9a9815…` success |
| render | 449.2 s | 373.1 s |
| VRAM peak / temp | 14 590 MiB / 72 C | 13 476 MiB / 74 C |
| system RAM used, first → peak | 16.8 → 30.79 GB | 18.16 → 29.84 GB |
| counts source = pose = generated = detailed | 24 = 24 = 24 = 24 | 28 = 28 = 28 = 28 |

Stitched `final_chained.mp4`: 48 frames, 4.000 s, 410 009 B, sha256
`fa7d6706b01ec0bc…`; `verified_outputs: true`; 52 + 52 + 52 + 52 files with
sha256; the 4 init PNGs are byte-identical to seg 1's `fd_frame_00021–24`
(same sha256). Identity (ArcFace, caveat as before): mean **0.373**, min 0.297,
48/48 (frames 1–24: 0.352, 25–48: 0.394 — no identity reset at the seam).

**The seam is a hard cut.** `chain_held_seam1.png` (frames 21–28: output over
source over native head crops): frames 21–24 are a dark corridor with an
orange-lit doorway on the right, cardigan over a beige vest, no envelope; frame
25 is a bright backlit doorway behind him, different wall stripes, white shirt,
a folder in his hand. Numbers (`manifest.sequence`): frame-to-frame mean |diff|
median **2.28**, p90 3.45, max 5.2 inside the segments; at the seam (24 → 25)
**25.6 = 11.2× the median**; mean RGB (57, 58, 41) → (76, 76, 61). The held
frames themselves survive: round trip init → rendered held frame 1.25–1.29 (VAE
+ re-detail). For comparison the 26k single 180-frame job over the same clip
(`chain_single26k_*.png`, `sequence_metrics` on its frames): median 2.76, p90
4.62, **max 11.3** — its worst window-blend transition is half this seam. So the
held-frame scheme is *worse* at the seam than the current single job, and it
must not be the default. Reason, as far as the mechanism allows: the inpaint
blend feeds the held frames to the model at the *same noise level* as the new
frames, so at the early high-sigma steps that decide composition and lighting
they are almost pure noise; identity and pose still carry because IP-Adapter
and the pose ControlNet act at every step regardless.

## 4. RAM: the 26k model is wrong at the low end

Sampling the backend process (`psutil.Process(6444)`) every 10 s through seg 2:
RSS climbs 4.5 → 15.3 GB over ~2.5 min while the checkpoint, motion module,
ControlNet, IP-Adapter and detailer weights load, then stays **flat at 15.32 GB**
through sampling; between prompts it drops back to ~4.5 GB (models unloaded).
System "used" 14.6 GB before the job → 28.2 GB plateau (+13.5, of which ~0.9 GB
was my test suite running beside it; peak 30.8 GB with a transient). 26k
measured +14.4 GB at 180 frames. So RAM ≈ **~12.5–13 GB of weights + ≈ 12 MB
per frame** (two points: 28 and 180 frames), not `14.4 GB × frames/180`:
`ram_needed_gb(24)` = 3.4 GB is a factor of four too low, and a 565-frame single
job would need ~19–20 GB + margin, which this 31 GB machine has only when
little else is open. **`ram_needed_gb` was left as in 26k on purpose** (one
more point, 60–64 frames, comes from the long run) — the next agent refits it
(affine) and updates `test_ram_need_scales_with_length`.

## 5. Run 2: img2img seed (`chain_investigate_26l.py img2img`; job `mtr_20260926_134245_e966d8`, launched like the tool with the gate asked)

Same 24 | 4 + 24 split; every frame of seg 2 starts from seg 1's last frame at
denoise 0.7 (`init_mode: img2img`; the 4 held positions are regenerated too and
dropped at stitch). Backend start 181.0 s; seg 1 386.7 s (15 902 MiB, 72 C, RAM
14.76 → 29.94 GB), seg 2 210.0 s (13 244 MiB, 73 C, RAM 26.52 → 28.99 GB);
counts 24 = 24 = 24 = 24 and 28 = 28 = 28 = 28; `final_chained.mp4` 48 frames,
402 163 B, sha256 `b2602aad72343273…`; `verified_outputs: true`. Identity mean
0.373, min 0.297, 48/48 (1–24: 0.352, 25–48: 0.394; per-frame values differ from
run 1, the rounded means coincide).

| | held + noise mask (run 1) | img2img 0.7 (run 2) | 26k single job, same clip |
|---|---|---|---|
| f2f median inside segments | 2.28 | 2.47 | 2.76 |
| f2f at the seam (24 → 25) | **25.6 (11.2×)** | **9.44 (3.8×)** | worst window blend 11.3 |
| mean RGB before → after | (57, 58, 41) → (76, 76, 61) | (57, 58, 41) → (51, 50, 36) | — |
| seg 2 f2f median | 2.9 | 3.3 | — |

`chain_img2img_seam1.png`: frames 25–28 keep the same dark corridor, the orange
doorway on the right, the beige vest, the phone pose — a continuation with a
softening and a small lighting shift, not a cut. `chain_img2img_overview.png`:
frames 25–48 stay in that scene. Motion in this 0–4 s span is mild in the source
itself, so whether the img2img start damps body motion is **not decided** by this
run; the 3-segment span (walking toward the camera) is the test. img2img is the
seam scheme to carry forward; the driver has a `long_img2img` variant ready.

## 6. Evidence

`local_agent/runtime/motion_transfer_20260925/`: `chain_investigate_26l.py`
(driver + sheet builder), `chain_held_26l.{log,json}`, `chain_held_seam1.png`,
`chain_held_overview.png`, `chain_held_rgb_strip.png`, `chain_held_sheets.json`,
`chain_single26k_{overview,rgb_strip}.png`, `chain_single26k_sheets.json`,
`chain_img2img_26l.{log,json}`, `chain_img2img_{seam1,overview,rgb_strip}.png`, `chain_img2img_sheets.json`, `full_26l_a.log`, the three `_edit_*26l*.py`
scripts. Jobs under `outputs/motion_transfer/mtr_20260926_132450_0bc483/`
and `mtr_20260926_134245_e966d8/` (both complete); raw frames under
`outputs/stories/_comfy_output/motion_transfer/<job>/segNN/`.

## Not done

- No continuous long clip yet: the shipped default init mode (`held`) seams as a
  cut; the img2img seed measured at the single job's window-blend level on one
  2-segment run and has not been run over a span with real motion.
- Hybrid (exact held frames + img2img new frames) not built; the 3-segment run
  (`chain_investigate_26l.py long_img2img`, 60 | 64 | 64 over the 26k span) not
  run, so RAM flatness across ≥ 3 segments is inferred from two 2-segment runs
  (peaks 30.8/29.8 and 29.9/29.0 GB used), not proven; `ram_needed_gb` not
  refit; `INIT_MODE_DEFAULT` still `held`; full suite not re-run after the last
  edits; GUI server not restarted.
