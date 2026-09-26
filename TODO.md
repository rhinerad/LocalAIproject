## START OVER — 2026-09-22j

- Operator restarted all Backrooms generations from the beginning (C016 forward).
- Every recovery item below (C016–C027) is superseded; its "Do not start videos"
  gates no longer apply to the fresh run. Prior attempts are preserved, not deleted.
- Pending Flux smoke grant `gpu_a38b751666c5` and the 204-still hash approval are
  superseded by the fresh clip-by-clip review flow.

Evidence: `CHANGELOG/2026-09-22j_restart_all_generations.md`.

---

## Operator decisions — 2026-09-26d

Four roadmap Section-A items decided in chat on 2026-09-26 (evidence:
`CHANGELOG/2026-09-26d_roadmap_phase1_operator_decisions.md`).

- [x] Motion-transfer identity path: FaceID Plus v2 SDXL weights (already on
      disk since 00:55) confirmed, **and** Wan 2.2 Animate 14B approved for
      download: `Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors`
      (18,401,760,586 B) from `Kijai/WanVideo_comfy_fp8_scaled` into
      `ComfyUI-Shared/models/diffusion_models/`; optional relight LoRA
      `LoRAs/Wan22_relight/WanAnimate_relight_lora_fp16.safetensors` (1.44 GB)
      from `Kijai/WanVideo_comfy`. Wan 2.1 VACE not approved.
- [ ] Run that download only while no render owns the GPU/drive (the
      motion-transfer session was mid-render when decided); verify size and
      sha256 against the Hub LFS metadata; never load it without a pinned
      template + measured VRAM profile (doc §7).
- [x] Backrooms motion-keyword table: **relax** (implemented under Phase 2b;
      see the GVD judge section item below).
- [ ] Still QA (`creative_still_qa.creative_approve`): **add a prompt-content
      axis** (does the rendered scene/objects match the prompt), reusing the
      existing video-submission semantic check (CLIP/WD14/Caption V4). Decided,
      not built; keep face/continuity behaviour unchanged when it lands.
- [ ] D02 `614e` judge miss: **open a follow-up investigation** — a brief-free
      "list every object" first pass or per-frame object question before the
      rig check (25g's suggestion). VLM-only, measured on the labeled sets,
      separate session; compare against the v3f cold baseline (25o).

---

## GVD live-metric judge — operator decisions closed — 2026-09-24ac/ad/ae

Context: 24q rewrote the judge (`local_agent/video_judge.py`, brief-aware
checks, CPU cut detector; false pass 80% → 29% on 50 labeled clips), 24r
confirmed it on a 29-clip held-out set (8/12 → 2/12) and left three items
open. All three are now decided and measured; the judge, its prompt and its
caps table are unchanged since 24q.

- [x] Strict curriculum bar 0.85 → 0.80 (`media_accuracy_gate._CURRICULUM_STEPS`,
      iteration 6+ is 0.80). Good held-out clips failing the strict tier
      8/12 → 3/12; three medium-confidence rejects scoring exactly 0.80 now
      pass too. Scores are 0.05-quantized with nothing between 0.80 and 0.85,
      so 0.80 was the only bar that admits correct Backrooms clips. 24ac.
- [x] Judged clips floored above every failure penalty
      (`dspy_orchestrator.JUDGED_SCORE_FLOOR = 0.10`; feedback rows carry
      `mipro_raw`). An all-zero render used to score 0.0, below a timeout
      (0.05); 138 of 201 real judged history rows sat there. No good clip's
      scalar changed. 24ad.
- [x] `llama_cpp_client.chat` forwards `repeat_penalty` and the other
      sampler fields (never sent before). Measured on the judge at 1.08:
      false pass 10/35 → 4/35 but false fail 0/8 → 2/8 and 3/12 → 6/12,
      3/79 outputs truncated before the scores; the yes/no checklist flips by
      token frequency. The judge and the still/video semantic verdicts pin
      `repeat_penalty=1.0` (13 re-judged clips identical to v2b). Free-text
      VLM callers now really run at 1.08. 24ae.
- [x] Free-text VLM callers measured at 1.0 vs 1.08 (8 clips, 75 calls,
      2026-09-25a): no truncation, no format loss, full frame coverage at
      either value. Prose callers (watcher vision, `analyze_video` timeline)
      stay at 1.08. `extract_video_actions` pinned to 1.0: its per-line
      required fields got rarer at 1.08 (camera-motion term on 51% → 19% of
      lines, noisy) and the penalty bought it nothing.
- [x] Action-log camera-motion field compliance: mandatory `cam=` slot in
      the line template plus `camera_labels` / `missing_camera_labels` /
      `camera_complete` in `_action_coverage`. Valid slot on 0/196 lines
      before, 196/196 after, stable across repeats, no truncation. 2026-09-25b.
- [x] Action-log camera-motion *accuracy*: `local_agent/camera_motion.py`
      measures pan/tilt/push/pull per window from the pixels (block phase
      correlation + similarity fit) and `extract_video_actions` reports it
      as `camera_motion` beside the model's `cam=` claim, with a
      disagreement list. On all 79 labeled clips forward drone flights and
      hallway walks read push-in, locked macros static, black clips
      uncertain; the VLM had called all of them static. 2026-09-25c.
- [x] Measured camera motion fed to the VLM (listed after the frame table,
      copied verbatim into `cam=`). A/B on the same 8 clips: `cam=` agrees
      with the measurement on 127/127 plain and 56/56 H3 windows (was 49
      and 10), no inversions, descriptions intact. A first wording that put
      the value inside each table row collapsed descriptions and inverted
      push-in to pull-back on 20 windows; kept as v1 evidence only. 2026-09-25d.
      Rerun with the 25e ring labels: identical outcome, 11/11 deterministic.
      2026-09-25f.
- [x] Border-ring fit + `subject_motion` flag in `camera_motion.py`
      (4x4 grid, outer 12 blocks fit the camera, centre excess flags the
      subject). Parity with the full-frame fit on real footage (636/656
      windows), flags real subject action (skateboard flip 5.7 px), does
      not fix the creek or the butterfly (the subject reaches the ring). A
      coherence gate was tried and removed: uniform flow is coherent,
      real drone moves are not (parallax). 2026-09-25e.
- [ ] Subject spanning the whole frame vs camera move: needs parallax
      across farther-apart frames or a labeled camera-motion set; no such
      set exists, so 48 ring-vs-full disagreements cannot be adjudicated.
      2026-09-25e.
- [x] First live MIPRO pass with every judge change active (4 rows: B01,
      D01, D02, M03; 1 candidate / 1 trial; iteration 6 = bar 0.80; floor
      0.10; sanctioned Rockernow, thermal guards, watchdog, peak 77 C, no
      trip). History rows 262-269. All 7 live-judged rows agree with a
      sheet review; in 24o's pass the same 4 clip ids all passed and 3 of
      those renders are labeled rejects. Good D02 0.92 and M03 0.96 clear
      the bar live; the good B01 was never judged live (mechanical gate,
      below) and scores exactly 0.80 offline. Row 266: raw 0.050 (= a
      timeout) floored to 0.10 above the 0.02 mechanical fail. Rig check
      fired once (a hand in frame), stayed off on a true FPV clip, missed a
      "likely drone" object. Flicker rules not exercised (no flicker clip
      reached the judge). Scores not comparable with rows <= 260 (24q).
      2026-09-25i.
- [x] `mechanical_director_gate` now runs before the render (it reads only
      the prompts and the example; its `video_path` argument was never
      used). A gated candidate still scores 0.02 but costs ~0 s instead of
      ~13 min of GPU (row 265). Only an injected `check_fn` runs after the
      render. +3 tests. 2026-09-25j.
- [x] Whether to relax the Backrooms motion-keyword table: the prompt row
      265 rejected ("gradually moves ... panning") rendered a clip the
      review calls good and the judge scores 0.80 offline. Operator
      decision; not changed in 25j. 2026-09-25i. Decided 2026-09-26d:
      relax it. Done 2026-09-26e: word-bounded motion vocabulary
      (moves/pan/tilt/turn/drift/...) with a negation floor; row 265's
      wording now renders; +8 tests.
- [x] Judge runaway repetition (2 in 87 scorings: D03 `5c73`, D02 `53ae`
      offline) -> parse failure -> 0.02 / 0.01 in production, below the 0.10
      floor for a clip the same judge scored 0.92 live. One retry when the
      answer has no scores (`video_judge.scores_missing`): same frames, a
      neutral note (frame lines under 15 words, close the JSON after the
      scores), 2048 tokens, repeat_penalty kept at 1.0. Measured first: a
      penalty on the retry (1.05 / 1.08) or a "never repeat" note flips the
      good D02 `53ae` to a cut, 1.08 closes the JSON early again, and
      dropping the frame lines fails every good clip. First full pass: 2
      runaways in 87 first answers, both recovered (D03 -> judged reject at
      the 0.10 floor; D02 -> judged false fail at 0.10, not the 0.92 of a
      parsed first answer); all 85 other verdicts identical to v3c / 25i.
      2026-09-25k.
- [x] Camera rig / drone / operator in the picture (24q's open wrong_viewpoint
      family): eighth judge check `camera_or_operator_visible`, alignment
      cap 0.25, brief exemption for gear the brief asks to show. Catches
      D01 `3032`, c036 and the held-out tripod-camcorder clip; fires on no
      good or partial clip. Tuning false pass 10/35 -> 8/35, AUC 0.821 ->
      0.836. D02 `614e` is still missed: the VLM reads the brief's "FPV
      drone" as the viewpoint and never lists the quadcopter. 2026-09-25g.
- [x] Requested flicker read as a location change or cut (24r's c004, c018):
      CPU dip rule (the lit picture on the far side of a lighting dip
      matches the lit side, 0.82-0.91 vs <= 0.56 across every real cut),
      near-black / dim sampled frames marked in the user prompt from the
      measured luma, and a prompt rule. c018 0.25 -> 0.80, c004 0.00 ->
      0.85; hard cuts passed 1/10 -> 1/10, late drift 3/4 -> 1/4; held-out
      high-confidence false fails 2/5 -> 0/5, AUC 0.809 -> 0.833. 2026-09-25h.
- [x] Requested camera turn read as a cut (c038, held-out good): the
      measured camera-motion estimator (25c/e, unchanged) now runs over
      the gaps between the judge's 8 sampled frames and a rigid pan/tilt
      (>= 0.20 of the frame across the gap, estimator subject_motion flag
      off) is marked in the user prompt the way `dark_spans_s` marks a
      dip, with one reading rule. c038 0.00 -> 0.85 (passes the 0.80
      bar); M05 `c6a5` (reject, lost in 25g) caught again 0.90 -> 0.00;
      9 clips marked in all, every other prompt byte-identical and all 70
      unmarked verdicts reproduced. Tuning FP 8/35 -> 7/35, AUC 0.843 ->
      0.864; held-out FF 2/12 -> 1/12, AUC 0.833 -> 0.872; hard_cut and
      location_drift rows unchanged on both sets. 2026-09-25l.
- [ ] Judge misses still open: D02 `614e` (rig read as viewpoint), D02
      `53ae` whenever its first answer runs away (the retry's shorter
      frame lines describe the climb out of the canopy and call the
      requested exit a cut; the climb reads push-in, not a turn, so the
      25l mark does not apply), stylized medium, c030 (reject, false
      pass since 24q: every swing of its cut-and-return carries the
      estimator's subject_motion flag, so it is unmarked and unchanged).
      2026-09-25g/h/k/l. 2026-09-26d: operator opened a follow-up
      investigation on `614e` (brief-free object listing, per 25g).
- [x] Judge non-determinism measured (262 judgements, 9 launches): the
      judge is deterministic given llama-server's prompt-cache state, not
      noisy. Cold (fresh launch, nothing cached: every live MIPRO judgement)
      reproduces byte for byte across launches (29/29 twice; the 7 live
      phase C rows 7/7 score- and check-identical offline). Warm-prefix
      (every eval-runner clip after the first: the system prompt's KV kept
      from the previous request) is reproducible only with an identical
      request history (v3c=v3d=v3e=r3 29/29; a mid-run server relaunch or a
      reversed order changes the raw text of 14/14 resp. 27/29 clips, with
      0 verdict flips). Cold and warm differ in wording on ~90% of clips and
      in verdict on 4/79 labeled (086a, B01 3172 pass cold; c030 caught cold;
      c028 0.75 warm -> 0.80 cold) plus phase C 7d15 (reject cold/live, pass
      warm) and 53ae (parses cold/live, loops warm). 25h's 4-of-60 was v3b's
      mid-run relaunch, reproduced today. 2026-09-25n.
- [x] Judge cold everywhere (operator decision on 25n): the judge sends
      `cache_prompt: false` on every call (`video_judge.JUDGE_CACHE_PROMPT`,
      forwarded by `llama_cpp_client`, keyword on `_run_vision_gpu`), first
      attempt and retry, so a judgement is the same cold prefill in the
      live metric and in `gvd_judge_eval`. Re-baselined through the
      unchanged runner: v3f is byte-identical to the 25n cold measurements
      on 87/87 clips and to the 7 live phase C rows. **New baseline
      (results_v3f / results_heldout_v3f / results_phaseC_v3f)**: tuning FP
      8/35, FF 0/8, hc FP 4/27, AUC 0.852, hard_cut 0/10; held-out FP 2/12,
      FF 1/12 at both bars (c035 only), hc FF 0/5, AUC 0.861; phase C FP
      0/5, FF 0/3. Warm -> cold flips: D01 `086a` and B01 `3172` (rejects)
      now pass, c030 (reject) and D02 `7d15` (reject) now fail, c028 and
      D02 `53ae` (goods) now pass; 0 no-score answers in 87. Every 24q-25l
      number was warm; compare future runs with v3f. 2026-09-25o.
- [ ] With the current judge every clip's minimum axis is ≤ 0.40 or ≥ 0.80,
      so the 0.80 strict tier and the 0.60 base tier accept the same clips
      on both labeled sets; the curriculum does no extra work above
      iteration 2 until scores spread.

Evidence: `CHANGELOG/2026-09-24ac_gvd_curriculum_strict_bar_080.md`,
`CHANGELOG/2026-09-24ad_gvd_judged_clip_mipro_floor.md`,
`CHANGELOG/2026-09-24ae_llama_cpp_repeat_penalty_forwarded.md`,
`CHANGELOG/2026-09-25a_freetext_vlm_repeat_penalty_ab.md`,
`CHANGELOG/2026-09-25b_action_log_camera_slot_compliance.md`,
`CHANGELOG/2026-09-25c_camera_motion_estimator.md`,
`CHANGELOG/2026-09-25d_measured_camera_in_vlm_frame_table.md`,
`CHANGELOG/2026-09-25e_camera_motion_border_ring.md`,
`CHANGELOG/2026-09-25f_measured_camera_feed_rerun_ring_labels.md`,
`CHANGELOG/2026-09-25g_gvd_judge_camera_rig_check.md`,
`CHANGELOG/2026-09-25h_gvd_judge_flicker_not_a_cut.md`,
`CHANGELOG/2026-09-25i_gvd_live_mipro_validation_pass.md`,
`CHANGELOG/2026-09-25j_mechanical_gate_before_render.md`,
`CHANGELOG/2026-09-25k_gvd_judge_retry_when_scores_missing.md`,
`CHANGELOG/2026-09-25l_gvd_judge_measured_turn_not_a_cut.md`,
`CHANGELOG/2026-09-25n_gvd_judge_nondeterminism_is_cache_state.md`,
`CHANGELOG/2026-09-25o_gvd_judge_cold_prefill_rebaseline.md`.

---

## C027 start close yellow-wall recovery — 2026-09-14z

- [x] Read the v3 receipts: output 1 is CLIP, not IPADAPTER. Do not restart v3.
- [x] Authored C027-start is Mode B close yellow wall, not a portrait.
- [x] Add one checksum-pinned close-wall donor after v3 is exhausted.
- [x] v4 attempt `85bc7de1e1154bf9a8b6c286672ac9c8` passed exact VLM QA.
      Stills continued to C027 last. No IPAdapter retry. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14z_c027_start_close_wall_recovery.md`.

## C026 handheld-corner POV recovery — 2026-09-14x

- [x] Preserve the two rejected C026 start attempts and the older, non-semantic
      portrait candidate; none is an accepted C026 still.
- [x] Add a C026-only, two-attempt, scene-only i2i recovery for the physically
      possible handheld camera-holder POV. The recovery requires the corner and
      continuation corridor and rejects face/body/selfie/external-camera views.
- [x] Add regression coverage; bounded still/QA suite: 178 passing tests.
- [x] Run and review the one bounded C026 recovery. Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14x_c026_handheld_corner_recovery.md`.

## C025 long-corridor recovery — 2026-09-14w

- [x] Preserve two rejected C025 start stills.
- [x] Reuse reviewed C022 corridor donors for C025 start and last.
- [x] C025 last passed on the vanishing-corridor donor. Runner reached C026
      start and paused after two SDXL failures. Stop point.
- [x] Next: C026 start Mode B recovery. Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14w_c025_corridor_recovery.md`.

## C024 last flickering-passage recovery — 2026-09-14v

- [x] Preserve two rejected C024 last stills.
- [x] Add one checksum-pinned flickering-passage donor.
- [x] v1 attempt `267a53ac19494d0a80f585ce5122f294` passed exact VLM QA.
      Stills continued to C025 start. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14v_c024_last_flickering_passage_recovery.md`.

## C024 start branching-corridor recovery — 2026-09-14u

- [x] Preserve two rejected C024 start hand-on-wall stills.
- [x] Add one checksum-pinned branching-corridor donor.
- [x] v1 attempt `3be2b8192e7e4d088250e01232a503a5` passed exact VLM QA.
      Stills continued to C024 last. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14u_c024_start_branching_corridor_recovery.md`.

## C023 last hand-slap-wall recovery — 2026-09-14t

- [x] Preserve two rejected C023 last gesturing-hand stills.
- [x] Add one checksum-pinned tilted hand-slap-wallpaper donor.
- [x] v1 attempt `66439c03a80c4885af499b9433e07f19` passed exact VLM QA.
      Stills continued to C024 start. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14t_c023_last_hand_slap_recovery.md`.

## C023 start gesturing-hand recovery — 2026-09-14s

- [x] Preserve two rejected C023 start stills.
- [x] Add one checksum-pinned look-back gesturing-hand donor.
- [x] v1 attempt `8be0a3c926d6484493b09e9c8b31ab12` passed exact VLM QA.
      Stills continued to C023 last. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14s_c023_start_gesturing_hand_recovery.md`.

## C022 last longer-corridor recovery — 2026-09-14r

- [x] Add one checksum-pinned longer/more-distant corridor donor.
- [x] Two C022 last SDXL attempts rejected; donor review started.
- [x] v1 attempt `67b3041f32554af791515c8ae5764cbc` passed exact VLM QA.
      Stills continued to C023 start. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14r_c022_last_longer_corridor_recovery.md`.

## C022 start empty-corridor recovery — 2026-09-14q

- [x] Preserve two rejected C022 start stills.
- [x] Reuse the reviewed empty yellow-corridor donor.
- [x] v1 attempt `195fdf8ebaea4c0aa0bf6a3f52c75261` passed exact VLM QA.
      Stills continued to C022 last. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14q_c022_start_empty_corridor_recovery.md`.

## C021 last look-back corridor recovery — 2026-09-14p

- [x] Preserve two rejected C021 last office-hallway stills.
- [x] Add one checksum-pinned look-back yellow-corridor donor.
- [x] v1 attempt `78d518fbeda345d9a9af97f551add488` passed exact VLM QA.
      Stills continued to C022 start. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14p_c021_last_look_back_recovery.md`.

## C021 start low narrow-corridor recovery — 2026-09-14o

- [x] Preserve two rejected C021 start chest-height stills.
- [x] Add one checksum-pinned low narrow-corridor donor.
- [x] v1 attempt `f1598c867b2747699faa45158cb7a3c9` passed exact VLM QA.
      Stills continued to C021 last. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14o_c021_start_narrow_corridor_recovery.md`.

## C020 last center-opening recovery — 2026-09-14n

- [x] Preserve two rejected C020 last stills (feet / office doors).
- [x] Add one checksum-pinned center-opening donor.
- [x] v1 attempt `9df12c98d0dd45cfb41eed0f1147f9d6` passed exact VLM QA.
      Stills continued to C021 start. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14n_c020_last_center_opening_recovery.md`.

## C020 start three-openings recovery — 2026-09-14m

- [x] Preserve two rejected C020 start stills.
- [x] Add one checksum-pinned three-openings repeating-fluorescent donor.
- [x] v3 same-pixel review passed exact VLM QA. Stills continued.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14m_c020_start_three_openings_recovery.md`.

## C019 last three-openings recovery — 2026-09-14l

- [x] Preserve two rejected C019 last mismatched-doorway stills.
- [x] Add one checksum-pinned three-identical-openings donor.
- [x] v1 attempt `c6fe2b7d76f84c65bf9f858ed0c39e0a` passed exact VLM QA.
      Stills continued to C020 start. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14l_c019_last_three_openings_recovery.md`.

## C019 start chest-height cuff recovery — 2026-09-14k

- [x] Preserve two rejected C019 start wallpaper-hand stills.
- [x] Add one checksum-pinned chest-height empty-room cuff donor.
- [x] v2 same-pixel review passed exact VLM QA. Stills continued to C019 last.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14k_c019_start_chest_cuff_recovery.md`.

## C018 last moist-hand pullback recovery — 2026-09-14j

- [x] Add one checksum-pinned wet-hand pullback donor.
- [x] Two C018 last SDXL attempts rejected; donor review started.
- [x] v1 attempt `73e44e2822174f6195420772b7f53b5b` passed exact VLM QA.
      Stills continued to C019 start. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14j_c018_last_hand_pullback_recovery.md`.

## C018 start hand-on-wallpaper recovery — 2026-09-14i

- [x] Preserve two rejected empty-wall C018 start stills.
- [x] Add one checksum-pinned hand-pressing-wallpaper donor.
- [x] v1 attempt `ab4d651616f94c3eb7de01c15fa2af1e` passed exact VLM QA.
      Stills continued to C018 last. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14i_c018_start_hand_wallpaper_recovery.md`.

## C017 last wallpaper-wall recovery — 2026-09-14h

- [x] Preserve two rejected C017 last SDXL attempts (visible camcorder).
- [x] Add one checksum-pinned yellow-wallpaper wall-POV donor.
- [x] v1 attempt `33580996a6d74e2d818f3e75da224524` passed exact VLM QA.
      Stills continued to C018 start. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14h_c017_last_wallpaper_wall_recovery.md`.

## C017 start hand-press recovery — 2026-09-14g

- [x] Preserve two rejected C017 start SDXL attempts.
- [x] Add one checksum-pinned hand-pressing-into-carpet floor-POV donor.
- [x] v1 attempt `9d77805f8c6f4e47a1e27aaf1ecfb3db` passed exact VLM QA.
      Stills continued to C017 last. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14g_c017_start_hand_press_recovery.md`.

## C016 last floor-POV recovery — 2026-09-14e

- [x] Preserve the C016 last stall receipt and both rejected SDXL stills.
- [x] Do not weaken owned-backend startup or loopback-only bind rules.
- [x] Add one checksum-pinned empty floor-POV donor; skip face/body identity
      comparison because this shot cannot show them; keep exact-VLM setting,
      composition, and forbidden-equipment checks.
- [x] Focused tests: 124 passed. One controlled donor copy was reviewed.
- [x] v1 exact-VLM review failed closed on empty-plate subject/pose checks
      despite `pass: true` and matching setting/composition/no equipment.
      Evidence kept. Production paused. No video.
- [x] Same-pixel v2 empty-plate subject/pose scope fix. Do not seed-spin.
- [x] v2 attempt `9dd2d9a33a4647b6becae97ef0979486` passed exact VLM QA on the
      same donor hash. Stills continued to C017 start. No video.
- [x] Do not start videos. Superseded by 2026-09-22j START OVER (C016-C027 gates no longer apply to the fresh run); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-14e_c016_last_floor_pov_recovery.md`.

## C002 repair stop — 2026-09-11m

- [x] Preserve the complete C002_start localized arm-repair ladder and all
  failed-attempt evidence; do not promote VLM-only passes.
- [x] Leave task `f8f7f70e364d40c0` paused after v5a2 visual rejection. No
  supervisor, C002_last continuation, or video phase is authorized.
- [x] Operator resumed C002_start and selected the bounded hash-pinned donor
  route. v6 attempt `379a7e9ed6484f73918e2258c0250146` passed mechanical and
  exact-model semantic QA with SHA-256
  `c8d8dda8a47d8a4cca510d8280dff232b9ccd1f4c6b5fb50a15e24614b9305ab`.
- [ ] Operator visually reviews and explicitly accepts or rejects that exact
  C002_start hash. Do not proceed to C002_last before this decision.

Evidence: `CHANGELOG/2026-09-11m_GPT_HANDOFF_c002_arm_repair_stop.md`.

## C002 v5a bgnoise-prefill SD erase - 2026-09-11h

- [x] Classical non-SD erase dry-runs failed visually; evidence kept.
- [x] Implement v5a (bgnoise prefill -> SD erase) + v5b (hanging-arm on v5a plate) after v4b_failed.
- [x] Tests: still_retry 38 OK; +image_render 53 OK; production_integrity 39 OK.
- [x] One supervisor ran; v5a attempt 372f98ca accepted by VLM (still SHA 2b8136b57e71...); advanced toward C002_last — force-stopped; visual/operator QA still required (v5b skipped because v5a passed).

Evidence: `CHANGELOG/2026-09-11h_c002_v5a_bgnoise_prefill_sd_erase.md`.

## C002 two-pass erase→arm - 2026-09-11g

- [x] v3 union-mask attempt failed (dark-green blob / bad hand); evidence preserved.
- [x] Implement v4a erase + v4b hanging-arm ladder.
- [x] Superseded by the explicit C002 repair stop; v4a→v4b evidence remains
  preserved and must not be rerun automatically.

Evidence: `CHANGELOG/2026-09-11g_c002_v3_fail_two_pass_v4.md`.

## C002 teal-glow strategy - 2026-09-11f

- [x] Measure root cause: teal only inside mask; left_shoulder outside v1/v2 polygon.
- [x] Rank strategies; implement v3 shoulder-inclusive union mask (grow 0).
- [x] v3 was run and failed; later ladder evidence supersedes this pending item.
- [x] Escalation occurred and ended in the explicit C002 repair stop; no silent retries.

Evidence: `CHANGELOG/2026-09-11f_c002_teal_glow_root_cause_and_strategies.md`.

﻿## C002 arm-down continuity - 2026-09-11d

- [x] Inspect live supervisor (PID 39872); do not launch a duplicate.
- [x] Visually reject C002_start v1 `2c0ad89d...` despite VLM pass (teal/blue glow arm); write `operator_review.json`.
- [x] Stop supervisor; preserve all evidence.
- [x] Arm exactly one distinct second repair: OpenPose arm-down v2 + grow_mask_by=2 + denoise 0.55; tests 79 OK.
- [x] v2 was run and visually rejected; later ladder evidence supersedes this pending item.
- [x] Independently inspect PNG (identity/room locked, natural arm down, no glow/camera). Do not trust VLM blindly.
- [x] If v2 fails: stop all production, leave evidence, report both failures. No third method.
- [x] Not applicable: v2 failed and C002 repair is now explicitly paused.

Evidence: `CHANGELOG/2026-09-11d_c002_start_teal_glow_reject_openpose_v2.md`.
# TODO

## C001 operator review gate - 2026-09-11a

- [x] Repair the malformed `C001_last` hand without regenerating the accepted
  face, body, clothing, room, or framing.
- [x] Verify the hash-bound v28 candidate with the exact Qwen2.5-VL Caption V4
  llama.cpp runtime: four upright fingers plus one visible thumb, five total
  digits, plausible anatomy/wrist, and matching identity/setting.
- [x] Preserve every failed attempt and stop the supervisor after the C001-only
  success guard; port 8188 is free and no video was started.
- [x] Operator accepted `C001_last` attempt
  `6e12ff2ab0b84085b765b7dd07a6bd4c` for continuation on 2026-09-11;
  candidate SHA-256
  `1302d430636908f50d6d3c2815559a7161300d9d2a5ab96320dd80c95260b4b6`.
- [x] C002_start resumed with a new hash-pinned donor method after the explicit
  operator instruction. The accepted C001 pixels were preserved outside two
  bounded arm corridors; the resulting v6 candidate is pending visual review.
- [x] Formal hash-bound approval of the complete 204-still set remains pending;
  do not begin videos before it. Superseded by 2026-09-22j START OVER (the
  set no longer exists; fresh run is reviewed clip-by-clip); closed 2026-09-26e.

Evidence: `CHANGELOG/2026-09-11a_c001_five_digit_hand_repair.md`,
`CHANGELOG/2026-09-11c_c001_operator_acceptance_and_still_resume.md`,
`work/C001_SMILE_REFINEMENT_CLAUDE_HANDOFF_2026-09-10.md`.

## PowerInfer educational calibration draft - 2026-09-08d (review-only)

- [x] Create/rewrite the four required files under `review-only/turbosparse-mistral-projected-abliteration/`.
- [x] 32 matched A/B pairs with taxonomy counts 6/6/5/5/5/5; all `operator_approved: false`; all `approval_id: null`.
- [x] Draft-mode validator rejects `operator_approved: true` and non-null `approval_id`; tests 4/4.
- [x] Preserve prior frozen 2026-09-02 draft under `preserved-frozen-2026-09-02/`; leave approved-2026-09-02 evidence untouched.
- [ ] Operator reviews worksheet keep/replace notes (notes are NOT approval) and explicitly approves or replaces pairs.
- [ ] TurboSparse remains parked â€” do not dump/train/convert/bench/register from this draft.

Evidence: `CHANGELOG/2026-09-08d_turbosparse_educational_draft_calibration.md`, `tools/powerinfer/STATUS.md`, `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-08.md`.



## Prompt-pack QA repair - 2026-09-08c / finish-prove 2026-09-08e

- [x] Replace historical-PNG fallback with attempt-specific receipts and hashes.
- [x] Preserve versioned media, ledger snapshots, startup and watchdog evidence.
- [x] Require exact-model semantic QA plus explicit hash-bound operator approval.
- [x] Bind approved previous-last still paths/hashes to the next video's first input.
- [x] Enforce 4:3 video selection, owned-backend lifecycle and thermal guard.
- [x] Bounded regression checks: 49 tests passed; startup-only probe reached
  /object_info (905 nodes) in 19.36 s and released port 8188.
- [x] Finish-prove 2026-09-08e: approval_status=unapproved when semantic_check=not_run;
  media_accuracy_gate tests are real unittest cases; required suite 32/32; CPU audit
  reconfirmed 139/126/0/0 (no production).
- [ ] Semantic QA is not run. Implement/execute review through the installed exact
  Qwen2.5-VL Caption V4 lazy llama.cpp runtime before any still can be approved.
- [x] Add duplicate-generation detection to semantic QA: compare each new still's
  image-to-text caption and perceptual/embedding fingerprint against prior frames
  and the requested prompt. Flag near-identical outputs (including repeated
  hallway/camera compositions) as a prompt, seed, conditioning, or workflow
  failure; record the evidence and diagnose the cause before any bounded retry.
  Adaptive prompt/process adjustment remains a later follow-up after the gate is
  proven reliable.

  Evidence: `CHANGELOG/2026-09-22i_gvd_video_pipeline_readiness.md` —
  `gvd_qa/duplicate.py` + `evaluate_artifact` integration + 12 CPU tests.
  Duplicates hold review (never auto-reroll).
- [ ] Regenerate current-prompt candidates through receipts, then obtain explicit
  operator still approval. Historical 139 PNGs do not match current prompts.
- [ ] Verify a real approved-input video and its embedded graph/hashes only after
  the still gate passes. No real video example exists in this QA pass.
- [ ] Optional operator step: bounded verify_prompt_pack_startup.py only if
  :8188 free, thermal OK, one backend max, and full cleanup afterward.

Current detailed evidence: docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-08.md,
CHANGELOG/2026-09-08e_prompt_pack_evidence_finish_prove.md.

## Done â€” managed prompt-pack tasks (2026-09-07b / r96)

- [x] Root cause: Backrooms chat be96946279cf480d routed CAP_IMAGE â†’ gpu_image â†’ partial render_story_image_batch
- [x] managed_prompt_pack ingest/export/progress + CAP_CREATIVE classifier
- [x] action_resolver deterministic ingest/export; render gated in dry-run
- [x] tests 9/9; real pack dry-run 102 clips exported; no Comfy start
- [x] APP_REVISION + launcher r96; changelog 2026-09-07b
- [x] **Did not restart** live agent (still on prior revision until Rhine restarts)
- [ ] After Rhine restarts: paste/continue Backrooms pack on a fresh chat and confirm outputs under local_agent/runtime/managed_tasks/<cid>/


## Done â€” Flux/RealPro owned-backend visibility (2026-09-06s / r95)

- [x] Root cause: empty `diffusion_models: ''` skipped by Comfy + wrong Downloads subfolder
- [x] Fixed `work/runtime/image_render_model_paths.yaml` (RealPro + AliceMix)
- [x] Fail-fast path helpers in `work/image_render.py`
- [x] Unit tests (empty segment / dot / live yaml) â€” 11 OK
- [x] Live visibility smoke + tiny Flux PNG still
- [x] APP_REVISION + launcher r95; changelog 2026-09-06s
- [x] Agent restarted via START_LOCAL_AGENT_GUI.ps1; /api/status shows 2026-09-06-flux-model-visible-r95
- [ ] Full 18-clip Flux sheet after operator paste + review gate (VRAM: t5xxl_fp16 + ~12GB UNet on 16GB â€” expect slow / sequential only)


## Done â€” no still-batch cap (2026-09-06r / r94)

- [x] Removed `_MAX_BATCH_JOBS = 24` + ToolError in render_story_image_batch
- [x] Guidance: queue ALL unique frames; never say capped
- [x] Unit test 30 jobs mocked through batch
- [x] APP_REVISION + launcher r94; changelog 2026-09-06r
- [x] **Did not restart** live agent (still on r93 until Rhine restarts)


## Done â€” stills batch + review gate (2026-09-06o / r93)

- [x] render_story_image_batch sequential still queue
- [x] Review gate before video (approve_story_stills)
- [x] Stale pid_running when owner released
- [x] Unit tests + APP_REVISION r93 (restart to load tools)


## Grok 2026-09-06n â€” continue / finish-earlier specialist unlock (DONE, on disk; restart later)

- [x] Root-cause: server stripped tool_evidence from answer() history (system receipt only)
- [x] Forward tool_evidence on assistant history rows; parse system evidence receipts
- [x] Unfinished plan + continuation utterances (continue / finish earlier prompt)
- [x] Keep stale H3 / powerinfer-continue blocked
- [x] tests 103/103; changelog 2026-09-06n; APP_REVISION ...-specialist-continue-finish-r92
- [x] **Did not restart** live agent / did not run START_LOCAL_AGENT_GUI.ps1
- [ ] After Rhine restarts: regenerate or continue on chat d98731129ac743ac and confirm render/plan no longer stale-blocked


## Grok 2026-09-06l â€” GUI Send/Stop unlock (DONE, on disk; restart later)

- [x] stream() try/finally + streamEpoch orphan on Stop (Send restores immediately)
- [x] per-event JSON/handler guards; drain SSE after Stop (no abort)
- [x] test_gui_render_hint unlock markers; launcher revision lockstep r91
- [x] changelog 2026-09-06l; APP_REVISION 2026-09-06-send-stop-unlock-r91
- [x] **Did not restart** live agent / did not run START_LOCAL_AGENT_GUI.ps1
- [ ] After Rhine restarts: hard-refresh GUI and verify Stop returns Send mid-turn

## Grok 2026-09-06k â€” specialist tool allowlist on confirmation (DONE)


- [x] specialist_scope OR _pending_specialist_continuation for tool allowlist
- [x] plan_story_image tool_evidence / prepared-plan prose counts as pending
- [x] test: proceed after plan allows render_story_image; stale H3 still blocked
- [x] revision 2026-09-06-specialist-tool-confirm-r90; changelog 2026-09-06k
- [x] WAITING operator sidebar approve **gpu_a38b751666c5** then retry Flux smoke PNG
      -- grant stale against the fresh run per 2026-09-22j; closed 2026-09-26e.

## Grok 2026-09-06j â€” flux/photos CAP_IMAGE + timeshare /free fallback (DONE)

- [x] _IMAGE_GEN_SIGNAL matches photos + START/END FRAME + flux intent â†’ CAP_IMAGE
- [x] timeshare clear_vram: MCP not started â†’ HTTP POST /free fallback
- [x] plan/render_story_image tool text: Flux â†’ model_profile=realpro_flux; no tool 
lux
- [x] revision 2026-09-06-flux-photo-intent-r89; changelog 2026-09-06j

## PHASE 1: Engine Architecture Evaluation (ACTIVE, operator directive 2026-09-02) â€” do this first

**Operator directive, recorded verbatim in intent:** all Phase 2 context/memory
optimization work below is **strictly blocked** until a final inference-engine
decision is made and documented. Do not start any Phase 2 item until this
phase's milestone is closed.

**Reconciliation note (read before working this phase) â€” the existing record
below does not match a "not yet started" evaluation, and this note exists so
nobody re-derives conclusions that are already on file:**
- PowerInfer is **not at square one**. `ReluLLaMA-7B` was already dumped,
  calibrated (32/32 layers), and quality-gated against the current Ollama
  route â€” it **failed 9 of 10 basic instruction/format cases** and was marked
  **not eligible for promotion** (see the "PowerInfer control-plane
  evaluation" section below). `TurboSparse-Mistral` projected abliteration is
  **parked**, not under test â€” it has an 8-pair *synthetic* calibration only,
  predictors were never rebuilt from it, and it is explicitly blocked pending
  operator-approved 32-pair calibration data (see `review-only/` prep and
  `CLAUDE.md`'s SCOPE NOTICE). "Finalize testing... determine if stable
  enough" is therefore really: **decide whether to (a) approve the 32-pair
  calibration set and continue the TurboSparse route, (b) try a different
  sparse candidate (Bamboo-DPO 7B is intake-complete but prompt-contract
  unresolved), or (c) abandon the PowerInfer sparse-offload approach given
  ReluLLaMA's rejection.**
- **TinyEngine has no prior evaluation in this repo** â€” no doc, no intake,
  no hardware-compatibility check exists yet. Treat this as a genuine
  from-scratch research task, not a resumed one.
- **"Swarm offload to the Farm" (Phase 2, item 4 below) is largely already
  built**, not a from-scratch design: Redis/Celery worker farm is live,
  WireGuard hub-and-spoke networking is standing (workstation `10.90.90.1`),
  a Mac worker is connected and `connectivity_probe` verified end-to-end
  2026-09-02, and a real workload (`judge_transcript`) shipped the same day.
  See "Phase 1 worker-farm bootstrap" and "Worker farm â€” judge_evaluation"
  sections below. Phase 2 item 4's spec (ZeroMQ/FastAPI daemon) describes a
  **different transport than what's already running (Celery/Redis over
  WireGuard)** â€” when this phase unblocks, that item needs to be re-scoped
  as "route summarization/embedding tasks onto the existing worker farm" or
  an explicit decision to replace the existing transport, not built as if
  nothing exists yet.

- [ ] **Task 1 â€” Evaluate PowerInfer architecture (resume, don't restart).
  Status as of 2026-09-02: read in full, operator decision still needed.**
  Re-read `tools/powerinfer/README.md` and `work/POWERINFER_STATUS_2026-08-30.md`
  end to end (there is no `tools/powerinfer/STATUS.md` â€” the README carries
  that role). Confirmed still true: `ReluLLaMA-7B` is mechanically proven
  (native `sm_120` CUDA build, cold/warm 20-turn acceptance gate) but failed
  9/10 elementary instruction-format cases and is diagnostic-only, never to
  be registered. `TurboSparse-Mistral` (`...20260830b`) is parked: 32/32
  `o_proj` edited, 2.1e-4 max drift, but calibrated on only 8 *synthetic*
  pairs â€” predictors were never rebuilt and the pipeline refuses to unless
  supplied â‰¥32 *operator-approved* pairs. Review-only educational draft files now exist at `review-only/turbosparse-mistral-projected-abliteration/` (UNAPPROVED 32-pair JSONL + worksheet + banner + validation-report; see 2026-09-08d). Prior approved INPUT `approved-calibration-32-pairs.2026-09-02.jsonl` also remains on disk. TurboSparse still parked pending operator review of the educational draft and a separate GPU gate. `Bamboo-DPO 7B` intake is mechanically complete
  (CUDA sparse load, 3,024 MiB FFN offload) but its prompt/chat-template
  contract is unresolved, blocking its own 10-case quality comparison.
  **This is an operator decision, not one to make unilaterally** â€” it
  determines whether GPU time goes toward finishing the 32-pair TurboSparse
  calibration, resolving Bamboo-DPO's prompt contract, or dropping the
  PowerInfer sparse-offload approach entirely given ReluLLaMA's rejection.
  Options laid out for operator sign-off:
  (a) approve/complete the 32-pair TurboSparse calibration set and continue
  that route: requires finishing the missing `review-only/` files and an
  explicit operator approval of the pairs themselves;
  (b) invest in resolving Bamboo-DPO's prompt-contract gap so its quality
  gate can actually run;
  (c) close PowerInfer out as not viable for this agent loop â€” Ollama
  remains the fallback either way, so "no PowerInfer" has zero downtime cost.
- [ ] **Task 2 â€” Evaluate TinyEngine architecture â€” researched 2026-09-02,
  finding: not applicable to this hardware, but a same-family project is.**
  MIT Han Lab's `mit-han-lab/tinyengine` (the literal "TinyEngine") targets
  **microcontrollers only** â€” its own benchmarks are profiled on an
  STM32H743 with a 512 KB peak-memory / 2 MB flash budget. It has no path to
  an RTX 5080/Ryzen desktop and is not a llama.cpp/Ollama/PowerInfer
  alternative for this agent; ruling it out does not require an intake.
  The same lab ships a **different, actually relevant project**,
  `mit-han-lab/TinyChatEngine`, which does target x86/ARM/CUDA desktop and
  edge GPUs (CUDA backend, compute capability â‰¥ 6.1, which the RTX 5080
  comfortably exceeds). **2026-09-02: operator asked to "research tinyengine
  and make a plan to implement it" without directly resolving the
  MCU-vs-TinyChatEngine question raised above; since the literal MCU project
  has no desktop/GPU path at all, this was read as confirming TinyChatEngine
  and acted on that basis â€” flagged here in case that inference is wrong.**
  A staged, gated intake plan (mirroring PowerInfer's
  discipline â€” hash-pinned commit, no GPU without approval, no registry
  without a passed quality gate) is written at
  `tools/tinychatengine/INTAKE_PLAN_2026-09-02.md`. Key findings from the
  upstream README: MIT license; **no HTTP server** (CLI chat binary only â€”
  an OpenAI-compatible proxy wrapper would need to be built, same scope as
  `powerinfer_openai_proxy.py`); CUDA backend is real but **narrow model
  coverage** (int4 AWQ Llama-2/CodeLlama only â€” no Llama-3, no Mistral, no
  VLM on GPU); Windows CUDA build is upstream-labeled "Experimental" and
  requires a manual `-arch=sm_120` edit whose compatibility with this RTX
  5080 (Blackwell) is **unverified by upstream** (PowerInfer's own `sm_120`
  build was new/fragile territory, which at least proves the toolchain path
  exists on this host). No stage has been executed â€” plan only. Three
  operator decisions are still open in that document before Stage 1 (cheap
  CPU-only build/smoke-test) starts: whether the CUDA model-coverage gap is
  worth spending build effort on, whether to greenlight Stage 1 now while
  holding Stage 3 (GPU/`sm_120`) for a separate approval, and awareness that
  Stage 7 requires building a new proxy wrapper.
- [x] **Milestone â€” final inference-engine decision, documented and closed.**
  **Operator decision, 2026-09-02: stay on the models already in use (Qwen
  models, `gpt-oss`) via Ollama. No PowerInfer route (TurboSparse
  calibration, Bamboo-DPO) and no TinyChatEngine intake are being pursued at
  this time** â€” this is option (c) from Task 1 and the "not worth the
  Stage 1 effort right now" outcome for Task 2, not a rejection of either on
  technical grounds; both remain documented above if revisited later. Losing
  candidates and why: PowerInfer's only benchmarked candidate (ReluLLaMA-7B)
  already failed its quality gate (9/10 cases) and TurboSparse/Bamboo-DPO
  both have unresolved prerequisites (calibration pairs, prompt contract);
  TinyChatEngine's CUDA path is narrow (no Llama-3/Mistral) and carries
  unverified `sm_120` risk. Ollama with the current models remains the
  production path. **Phase 2 below is unblocked as of this decision.**

## PHASE 2: Context & Memory Optimization â€” was BLOCKED by Phase 1, now unblocked (2026-09-02)

Phase 1's milestone closed above â€” items below may now be worked. Historical
note, not a current instruction: this section was blocked from its creation
until 2026-09-02, and item 4 (RAG upgrade, Stages 1-2 only) was implemented
under an explicit operator override *before* this milestone closed â€” see
that item for details. Note: Phase 2's existing "Context & Token Optimization (Pillars 1-4)"
section further down this file already shipped four *different* optimizations
(context compaction, artifact/tool-output pruning, memory extraction,
prompt-prefix caching) â€” the four items below are additional/new, not
duplicates of those, but should be read together with that section so nothing
is built twice.

1. [ ] **KV cache quantization** â€” BLOCKED by Phase 1. Update the chosen
   engine's launch arguments for 8-bit quantized KV caching (e.g.
   `--cache-type-k q8_0`). Engine-specific; cannot be scoped further until
   Phase 1 names the engine.
2. [x] **Sliding-window context summarizer â€” resolved 2026-09-02, already
   built, no new code needed.** `HARNESS_OPTIMIZATION.md`'s audit confirmed
   this overlap was the whole item: `local_agent/context_compactor.py`
   (Pillar 1) + `agent.py::_trim_context` already do exactly this â€”
   automatic summarization of older turns, triggered when
   `router.estimate_context_tokens(msgs, tool_schemas) > num_ctx`. That
   trigger is arguably better than the originally-proposed fixed
   "6,000 tokens": it's the model's real adaptive context budget, not a
   guessed constant, and it already preserves the last complete
   tool-call/result pair intact rather than a crude "last 5 messages"
   cutoff. Nothing further to build here.
3. [ ] **RAG-first memory retrieval** â€” BLOCKED by Phase 1. Enforce Chroma DB
   (via `nomic-embed-text`) vector lookups for old data instead of injecting
   raw logs, keeping the active prompt window lean.
4. [~] **Agentic RAG upgrade for local-docs retrieval** â€” Stages 1-2
   **implemented 2026-09-02 under explicit operator override** (requested
   before the Phase 1 milestone above had formally closed; the same
   conversation turn that authorized the override also supplied the
   engine decision that closed Phase 1, so by the time this landed the
   block was moot anyway). Gap analysis in `RAG_EVALUATION.md`.
   - [x] **Stage 1 â€” `EmbeddingScorer`, `local_agent/retrieval.py`.** Real
     dense retrieval via the same CPU-only `nomic-embed-text` Ollama
     endpoint/host pattern `exemplar_embeddings.py` already proved out.
     Embeddings cached on disk (`knowledge/retrieval_embeddings.json`),
     keyed by chunk id + a hash of its text so an edited file only
     re-embeds its own changed chunks. Fulfills
     `local_agent/UPGRADE/05_models_after_internet.md` Job 2.
   - [x] **Stage 2 â€” `HybridScorer`, same file.** Fuses `LexicalScorer` +
     `EmbeddingScorer` via Reciprocal Rank Fusion (rank-based, since BM25
     and cosine scores aren't comparable). Deliberately **not** naive RRF
     over the whole corpus: only chunks clearing a lexical hit (BM25>0) or
     an embedding hit (cosine â‰¥ `MIN_EMBED_SIMILARITY=0.35`, an unverified
     heuristic â€” flagged for revisit) enter the pool, preserving the
     "empty result means local docs don't establish the claim" contract
     that unfiltered RRF would have destroyed (RRF scores are otherwise
     always positive). Falls back to lexical-only ranking if the embedding
     endpoint errors, so `search_docs` keeps working fully offline.
   - **Default as of 2026-09-02ab:** `search`/`search_docs` use
     `HybridScorer`. `search_relevant()` keeps embedding-only hits tagged
     `match_by=embedding|both` so semantic matches are not stripped; lexical
     near-misses without that tag are still dropped. See Stage 5 below.
   - [x] **Tests written and actually executed by the operator, 2026-09-02.**
     `local_agent/test_retrieval_embeddings.py`, 7 tests (corrected count â€”
     an earlier note here said 9, that was wrong), all Ollama calls mocked.
     `mcp__workspace__bash` was denied in-session, so this had only been
     verified by manual trace-through until the operator ran
     `python -m unittest local_agent.test_retrieval_embeddings -v` from the
     repo root and confirmed: **7/7 passed.** `py_compile` still not run
     separately but moot â€” the module clearly imports and executes cleanly
     since the tests ran.
   - [x] Stage 3 â€” cross-encoder reranking. **Close-call, not implemented
     2026-09-03ae (re-read live `retrieval.py`; still no install).** FlashRank
     catalog options remain `ms-marco-TinyBERT-L-2-v2` (default) and
     `ms-marco-MiniLM-L-12-v2` (larger). `ms-marco-MiniLM-L-6-v2` is not in
     the catalog. onnxruntime 1.29.0 is **already** on the workstation via
     chromadb (~43 MB), so the 2026-09-02ab "new native runtime" reason is
     stale; FlashRank itself + TinyBERT (~5 MB) + ~510 MiB Ranker RSS are
     what would still be added. TinyBERT's published lift is vs BM25
     (~+3 nDCG@5), not vs this HybridScorer, and 61% of the 940-chunk index
     exceeds the 2000-char CE window. Stage 4 already grades/retries.
     Default stays `HybridScorer`. Hand-judged eval now exists
     (`local_agent/evaluations/retrieval_hand_judged.json`, 18 queries).
     Fail-closed Hybrid **13/18 top-5**. Live-dense Hybrid (2026-09-03bb,
     nomic-embed-text on CPU `:11435`): still **13/18 top-5**, search_docs
     gold **13/18 vs lexical 12/18**. Mixed: Hybrid recovers 3 paraphrases
     lexical ranked 6â€“16, and drops 2 lexical already had in top-2
     (`phase1_stay_on_ollama`, `judge_not_registered`). Not a clear win;
     default stays Hybrid (fail-closed still equals BM25). FlashRank window
     still 5/18. See
     `CHANGELOG/2026-09-03bb_retrieval_stage5_human_comparison.md`. If later
     approved: opt-in `RerankedScorer` over fused top-N 20â€“50, same lexical
     fallback. `docs/hybrid_scorer_proposal.md`.
   - [x] **Stage 4 â€” implemented 2026-09-02: `local_agent/agentic_retrieval.py`
     (`agentic_search_docs`).** Bounded retrieveâ†’gradeâ†’retry loop over
     `retrieval.search(..., scorer=HybridScorer())`, mirroring
     `deep_research.py`'s proven plan/gather/synthesize shape (same
     dependency-injection test style, same "untrusted evidence, not
     instructions" defensive framing). The model grades whether retrieved
     evidence actually answers the question and, if not, proposes up to 4
     rewritten queries for another round (capped at `MAX_ROUNDS=3`). This is
     the piece that actually closes the "no retry on empty/weak search" gap
     â€” Stages 1-2 only improved the retriever itself. Includes an
     anti-hallucination guard: any `(path.md)` citation the model invents
     that wasn't actually in the retrieved evidence gets stripped and
     replaced with `[unverified citation removed]`, and forces
     `sufficient=false` so a fabricated citation can't pass as a good
     answer. Registered as a **new, separate tool** (`agentic_search_docs`,
     added to `PROJECT_ONLY_TOOLS` alongside `search_docs`, deliberately
     **not** in `CONCURRENCY_SAFE_TOOLS` since it calls the model) â€” the
     existing `search_docs` tool and its lexical-only `search_relevant()`
     grader are untouched, so this is additive, not a default-behavior
     change requiring Stage 5 first. Tests:
     `local_agent/test_agentic_retrieval.py`, 8 tests (schema registration,
     scope/concurrency-safety placement, first-round success, multi-round
     retry, honest fallback when evidence and model are both unavailable,
     fabricated-citation stripping, max-rounds clamping). **Executed by the
     operator 2026-09-02: 8/8 passed.** (Same run also re-confirmed
     `test_retrieval_embeddings.py`'s 7/7 still passing after the Stage 4
     changes â€” no regression.)
   - [x] Stage 5 â€” cheap comparison + Hybrid default wiring, 2026-09-02ab;
     live-dense human comparison 2026-09-03bb. 2026-09-02ab compared
     Lexical vs Hybrid on a mocked fixture (Hybrid recall 2/2 vs Lexical
     1/2) and fail-closed on-disk (top-5 matched Lexical on three queries)
     and flipped `_DEFAULT_SCORER` to `HybridScorer`. 2026-09-03bb ran the
     18-query fixture with nomic-embed-text actually up (CPU `:11435`,
     Vulkan off, no 5080). Result is **mixed**, not a clear win:
     search_docs gold 13/18 Hybrid vs 12/18 lexical; Hybrid recovers
     `gpu_idle_but_cpu_8b`, `farm_embed_no_celery_import`,
     `relullama_not_promotable`; lexical still wins
     `phase1_stay_on_ollama` (hy rank 9) and `judge_not_registered`
     (hy rank 12). Default stays Hybrid **but is inert until CPU Ollama
     `:11435` is started deliberately** (eval instance stopped
     2026-09-03bf; fail-closes to lexical). Those two regressions need
     addressing before dense is turned on for real. Packet:
     `local_agent/evaluations/retrieval_human_side_by_side.md`.
     See `CHANGELOG/2026-09-03bb_retrieval_stage5_human_comparison.md`
     and `CHANGELOG/2026-09-03bf_cpu_ollama_11435_stopped_fail_closed.md`.
**Reference resource added 2026-09-02 (not implemented, catalogued for when
this phase unblocks):** [karpathy/autoresearch](https://github.com/karpathy/autoresearch),
MIT license. Read directly from upstream README before adding â€” it is
**not** a context-management/orchestration harness like LangChain Deep
Agents or Letta/MemGPT (the actual subject of this Phase 2 backlog); it's an
autonomous overnight ML-*training*-experiment loop: an agent edits a single
`train.py` (nanochat-style GPT), runs a fixed 5-minute training budget on
one NVIDIA GPU, keeps the change if `val_bpb` improves, discards and repeats
â€” ~12 experiments/hour, unattended. Two places it might actually be
relevant here, neither of which is Phase 2 proper:
- Its "agent edits code â†’ bounded run â†’ keep/discard on a metric â†’ repeat"
  loop pattern is a plausible template for the **Supervisor Loop** design
  (Phase 2 item 4, once unblocked) â€” worth reading `program.md`'s structure
  for that, not for the training code itself.
- It could plausibly automate **Phase 1's own PowerInfer predictor/
  calibration tuning** (bounded GPU runs, a held-out-recall metric already
  exists there) more than it fits Phase 2 â€” flagged for Task 1's operator
  decision, not decided here.
There's a community Windows/RTX fork, `jsegov/autoresearch-win-rtx`, worth
checking first given this host's RTX 5080/Windows setup â€” not vetted here.
Do not clone, run, or point an agent at any of these repos without a
separate explicit approval; this is a bookmark, not an intake.

5. [x] **Swarm offload to "The Farm"** â€” spec in `HARNESS_OPTIMIZATION.md`
   Â§4a. **Queues live 2026-09-02; agent routing via `farm_status.json`.**
   - [x] `summarize_conversation` and `embed_chunks` Celery tasks in
     `worker_farm/tasks.py`, registered on new `summarize`/`embed` queues
     in `celery_app.py` â€” added to **both** `task_queues` and
     `task_routes` this time (the `judge` queue's original bug was
     exactly forgetting the first one; see the code comment now warning
     against repeating it). `summarize_conversation` reuses
     `context_compactor.summarize_old_messages` and degrades gracefully
     (`{"summarized": false, "model_expected": ..., ...}`) if the worker
     has no summarizer model installed rather than failing. `embed_chunks`
     is stateless â€” embeds `{id, text}` chunks from the envelope and
     returns vectors only; does **not** touch `retrieval.py`'s on-disk
     embedding cache itself, that merge is left to a workstation-side
     caller (not written).
   - [x] **Per-worker summarizer model override, added 2026-09-02.**
     `summarize_conversation` no longer assumes `llama3.1:8b` fleet-wide â€”
     it reads the model name from that worker's own `FARM_SUMMARIZE_MODEL`
     environment variable (falling back to `context_compactor.MODEL` if
     unset), per `worker_farm/README.md`'s "per-worker model choice"
     policy. `context_compactor.summarize_old_messages` and `_installed`
     gained `model=`/`host=`/`timeout=` overrides to support this without
     changing behavior for existing workstation callers (regression-guarded
     in `test_context_compactor.py`). `embed_chunks` stays on the fixed
     `nomic-embed-text` model â€” embedding doesn't need a per-worker choice
     the way generation does. `mac_worker` is recorded as choosing
     `krith/mistral-nemo-instruct-2407-abliterated` (not installed yet).
   - [x] Tests added to `local_agent/worker_farm/test_farm_core.py`
     (registration-in-both-dicts check, envelope validation, graceful
     model-absent handling, mocked success path) and
     `local_agent/test_context_compactor.py` (model/host/timeout override
     honored, default call unchanged for existing callers) â€” **written and
     executed 2026-09-02.** Farm-core suite run via the isolated farm venv
     from the repo root; all four new tests passed.
   - [x] **Resolved 2026-09-02:** Ollama installed on mac_worker; Ollama
     MLX-runner bug fixed (install.sh replaced the embedded runner binary with
     an Apple Silicon-only binary, breaking CPU inference; fixed by killing the
     broken server and restarting with `/usr/local/bin/ollama serve`);
     `nomic-embed-text` and `krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS`
     (~6.8 GB) pulled fresh (the model was not pre-installed despite initial
     belief; `ollama list` showed only llava:7b, llama3:8b, deepseek-coder:6.7b
     after the install run). `EQUAL_SHARES_CPU_HOST=127.0.0.1:11434` set in
     mac_worker's `.env` so `router.CPU_HOST` resolves to the Mac's own Ollama
     (default port 11434, not the workstation's 11435).
   - [x] `Add-Phase1SecondaryWorkerCredential.ps1` re-run with
     `-Queues 'probe','judge','summarize','embed'` (PowerShell array syntax
     from bash â€” `@('a','b')` form was rejected as invalid queue name characters;
     correct form is bare `'a','b'`). New credential written to mac_worker `.env`;
     worker restarted with all four queues. Updated files deployed via scp:
     `context_compactor.py`, `ollama_client.py`, `router.py`, `atomic_io.py`,
     `worker_farm/tasks.py`, `worker_farm/celery_app.py`. End-to-end verified:
     `summarize_conversation` task ID `05015820-cc65-41d4-9166-f0e5a7f4ca83`
     returned a structured summary; `embed_chunks` task ID
     `6509195d-c718-4179-9e58-0453ade2b23f` returned 768-dim vectors. First-call
     latency ~55s (model cold load + ~18.5s inference on 2019 Intel Mac CPU).
     See `CHANGELOG/2026-09-02r_summarize_embed_queues_live.md`.
   - [x] **Workstation-side routing implemented 2026-09-02.** New module
     `local_agent/farm_offload.py` provides `try_summarize_on_farm()` and
     `try_embed_on_farm()` â€” thin wrappers that submit via the farm venv's
     Python (subprocess, since celery[redis] is not in the main agent env) and
     return None on any error/timeout. Two integration points:
     (a) `agent.py::_trim_context`: tries farm before calling
     `context_compactor.summarize_old_messages` locally; falls back on None or
     `{"summarized": false}` result; emits "farm CPU summary (model: ...)" vs
     "local CPU summary" in the context-compact note.
     (b) `retrieval.py::EmbeddingScorer.vectors_for`: restructured to a 3-pass
     lock pattern (cache read â†’ farm/local embed outside lock â†’ cache write) so
     the lock isn't held during the blocking network call; tries farm for stale
     chunks, falls back to `_embed()` for any the farm doesn't cover.
     `local_agent/worker_farm/_farm_submit_wait.py` is the farm-venv helper
     subprocess: reads request from stdin, loads `.env`, submits via Celery,
     waits, prints JSON to stdout. 22 tests in `test_farm_offload.py`, all pass.
     See `CHANGELOG/2026-09-02s_farm_offload_routing.md`.
   - [x] **Proactive pre-compaction trigger â€” implemented 2026-09-02.**
     `local_agent/compaction_prefetch.py`: module-level one-slot state machine
     (ignore-if-busy, fingerprint on the summarizable slice so the result is
     discarded if the slice grows between trigger and overflow). Trigger fires
     in the hop loop when `prompt_tokens > 80% Ã— num_ctx` but not yet
     overflowing; `_trim_context` calls `compaction_prefetch.consume()` first
     (no wait â€” None means fall through). Synchronous farm call and local CPU
     fallback are unchanged when prefetch is absent or mismatched.
     `_summarizable_slice()` extracted as a shared helper used by both the
     trigger site and `_trim_context` so their fingerprints always agree.
     30 tests in `test_compaction_prefetch.py`, all pass. See
     `CHANGELOG/2026-09-02u_compaction_prefetch.md`.

## Worker farm â€” first real workload: judge_evaluation (2026-09-02)

- [x] **Operator objective recorded:** use the worker farm to make the local
  agent "better, more efficient, smarter, faster and more logical," keep
  workers continuously busy, and scale as more machines join, with the
  explicit requirement that the work actually helps the agent.
- [x] **Built the judge_evaluation workflow** â€” `worker_farm/judge_rubric.py`
  (4 deterministic rules: unverified completion claims, work dumped on the
  operator, specialist-project leakage, unexecuted direct action requests),
  a `judge_transcript` Celery task on a new `judge` queue, and
  `submit_judge_batch.py` to continuously source un-judged/changed chats
  from `local_agent/chats/*.json` as the "always busy" job supply. 32 tests
  pass (10 new rubric tests + 3 new task-registration/envelope tests,
  3 expected skips same as existing pattern). Smoke-tested against 8 real
  chats: sane, bounded findings, not noisy. See
  `CHANGELOG/2026-09-02c_judge_evaluation_workflow.md`.
- [x] **Explicit operator decision recorded:** real chat transcripts
  (confirmed to include NSFW/explicit content, and separately a transcript
  showing the agent drafting uncensoring-leaning "calibration categories")
  may go to any credentialed secondary machine with no filtering â€” asked
  and confirmed twice, once before and once after that content was found.
  This deliberately widens the worker farm's prior public-data-only design
  for secondary machines, the same way `distill` would need its own
  decision. Recorded so it isn't mistaken for an inferred default later.
- [x] Grant the `judge` queue to `mac_worker` and run `submit_judge_batch.py`
  against the live broker â€” verified 2026-09-02. Three real `judge_transcript`
  tasks completed end to end on `celery@Louises-MBP` (54ms/16ms/68ms). ACL DENY
  probe also run: mac_worker can read distill queue envelopes via `~*` key
  pattern but cannot run admin commands (ACL SETUSER, CONFIG â€” NOPERM); actual
  sensitive content is in encrypted on-disk artifacts, not Redis. Accepted
  trade-off documented in `CHANGELOG/2026-09-02d_judge_evaluation_end_to_end_verified.md`.
  See also: `celery_app.py` bug fixed (judge was missing from `task_queues`,
  causing silent key-name mismatch); Mac worker environment rebuilt at
  `~/worker_farm/` (old directory had been deleted, venv gone).
- [x] **Decide on an LLM-based judge pass as a follow-up to the
  mechanical rubric â€” designed 2026-09-05bg, built 2026-09-05bo.**
  Mechanical `judge_transcript` stays regex-only (`judge_rubric.py`).
  Semantic task `judge_transcript_semantic` on the `judge` queue;
  Qwythos-9B CPU at local `:11434`; sidecar
  `farm-judge-semantic-verdict-v1` (`advisory: true`, default **off**).
  Four safeguards tested (isolation grep + adversarial import, kill
  switch, circuit breaker, busy-skip / no write into chats or
  mechanical status). No live run on real chats. Enable:
  `python -m local_agent.worker_farm.semantic_judge enable`. Evidence:
  `CHANGELOG/2026-09-05bo_farm_semantic_judge_pass_v1.md`.

## New model candidate â€” DeepSeek-V4-Flash abliterated (operator goal, 2026-09-01)

- [ ] **Operator goal:** experiment with
  `cebeuq/DeepSeek-V4-Flash-0731-abliterated`
  (https://huggingface.co/cebeuq/DeepSeek-V4-Flash-0731-abliterated) as a
  candidate model for the local agent, loaded onto the `C:\` SSD, using
  "tiny engine." **Not started.** Repo **exists**. It is a **284B-total /
  13B-active DeepSeek-V4 MoE** (256 experts, top-6) abliterated overlay,
  **~167 GB native FP4+FP8**, documented on **2Ã— DGX Spark 128 GB** + vLLM.
  Smallest public GGUF is still **~87 GB (Q2)**. This box is **~31 GB RAM +
  16 GB 5080** â€” it does **not** GPU-fit at any published quant. `C:\` is
  disk for the file (would fit), not VRAM. **"tiny engine" is the
  TinyEngine (MCU) vs TinyChatEngine (Llama-2 7B/13B CUDA) name collision;**
  neither can load DeepSeek-V4 MoE. Decision menu (skip / wait for a real
  small variant / llama.cpp mmap / ds4 / vLLM-on-Sparks / hosted) is in
  `CHANGELOG/2026-09-05ci_deepseek_v4_flash_abliterated_mismatch.md`. No
  pick. No download, no engine install, no registration.
- [ ] **2026-09-05, follow-up: KTransformers / PowerInfer MoE feasibility
  study (research only, no install).** Operator asked whether
  KTransformers or PowerInfer's heterogeneous CPU-GPU expert-offload
  approach changes the picture above for large DeepSeek MoE models.
  Verified via web search (not from training-data recall alone):
  KTransformers (kvcache-ai, Tsinghua MADSys/Apache-2.0) keeps a MoE off
  VRAM by placing hot/shared experts on GPU and offloading routed experts
  to CPU/DRAM with AMX-optimized kernels and async CPU-GPU scheduling.
  Its flagship published result is DeepSeek-R1/V3 (671B) on **one 24GB
  GPU paired with ~512GB system RAM** (SOSP 2025 paper) â€” this box has
  **~31GB RAM total**, nowhere close, so the 236B/284B/671B-class models
  (including the DeepSeek-V4-Flash candidate above) are **not** made
  feasible by switching to KTransformers; the bottleneck is system RAM
  for expert storage, not VRAM, and PowerInfer's own architecture is
  ReLU/dReLU-sparsity-based (already tracked separately in this file),
  not this MoE-expert-offload technique. **Real finding, not a dead
  end:** KTransformers' own numbers show DeepSeek-V2 (16B total, 2.4B
  active MoE) dropping from 21GB to 11GB VRAM with their kernels, and
  DeepSeek-Coder-V2-Lite (same 16B/2.4B-active family) already fits this
  RTX 5080 at INT4/FP8 quantization via existing llama.cpp/Ollama-class
  tooling â€” no KTransformers install needed for that size class. Does
  not replace or invalidate the TinyChatEngine Phase 1 closure (that was
  a separate, already-decided "stay with Ollama for now" call, not an
  open ticket to swap out) and does not change the DeepSeek-V4-Flash
  verdict above. If there is operator interest in
  DeepSeek-Coder-V2-Lite specifically as a coding-focused GPU candidate,
  that is a new, separate, right-sized evaluation â€” not started.

## Local-agent task completion reliability

- [x] Audit the current action/tool loop, saved-response evidence, context
  recall, media capability detection, GPU/router checks, phone permission
  boundaries, and regression coverage after the operator reported repeated
  failures to carry out a PowerInfer JSONL task.
- [x] Preserve structured tool-evidence fields across saved-chat reloads so
  exact paths, validation state, record counts, and repair status survive
  transcript compaction and server restart.
- [x] Recover exact `.jsonl` paths from older truncated same-chat tool receipts
  instead of falling back to ellipses, example paths, or guesses.
- [x] Harden shared local-agent atomic writes against Windows temp-file lock
  races by using unique sibling temp files plus bounded replacement retries.
- [x] Fix false-negative local transcription detection by allowing the existing
  ComfyUI Whisper-tiny runtime longer to complete its cold CPU-only import.
- [x] Extract a durable action-resolution layer from `agent.answer()` so direct
  operator requests map to concrete tool plans before the model drafts prose.
  This should replace more of the current regex/special-case recovery branches
  and make new task types easier to add without repeating today's failures.
  Implemented in `local_agent/action_resolver.py`; the two prior regex/special-case
  branches (JSONL repair and ComfyUI stop) were replaced in `agent.answer()` with
  a single `_execute_plan()` dispatch call. Five intents are handled deterministically
  (comfyui_stop, jsonl_repair, calibration_continue, list_dir, read_file);
  all guards are preserved through `tools.call()`. 29 new tests pass in
  `test_action_resolver.py`; 57 existing tests pass in `test_native_tool_calling.py`.
  `APP_REVISION` is `2026-09-01-action-resolver-r76`. See
  `CHANGELOG/2026-09-01k_action_resolver.md`.
- [ ] **2026-09-01, operator feedback:** "Claude, Claude Code, GPT are all very
  good at inferring what to do when I'm not super specific and I really want
  the local agent to be like that. Right now it feels hard to use." This is
  broader than the tool-plan-mapping item above â€” it's about underspecified/
  vague requests generally, not just direct ones the model already understood
  but routed badly. Not diagnosed yet: this needs concrete before/after
  examples from the operator (an actual vague request and what the local
  agent did versus what a frontier model would infer) before it's actionable.
  Guessing at a fix without those examples risks tuning against the wrong
  failure mode â€” a small local Ollama model's weaker general reasoning may be
  doing some of this regardless of prompt/tool-routing quality, so the first
  step is separating "prompting/routing problem, fixable here" from "small
  local model capability ceiling, not fixable by this codebase alone."
  **2026-09-05 capture (not a fix):** GUI button "this wasn't what I meant" on
  assistant messages writes one JSONL record per click to
  `local_agent/runtime/intent_mismatch.jsonl` (user message, full assistant
  text, stored tool_evidence, routing model/tier/capability, timestamp).
  Fire-and-forget after the fact â€” no routing/prompt change, no training, no
  analysis. Restart the desktop agent once so `/api/intent_mismatch` loads;
  HTML is served from disk. Review the log later and hand over concrete cases.

## RealVisXL / SDXL LoRA capability â€” setup in progress

- [x] Diagnose the legacy Kohya environment without overwriting it: its uv
  trampoline points at a missing Python 3.11 child; Python 3.12 is not a safe
  substitute because this Kohya revision declares `<3.12`.
- [x] Add a separate-environment installer, a no-GPU dataset/caption readiness
  check, and a RealVisXL-specific runbook. These are separate from the MiniMax
  H3 video LoRA workflow.
- [x] Finish the separate `A:\Users\rhine\kohya_ss\.venv-local-agent`
  dependency installation and run its import/trainer-help verification. This
  was re-verified on 2026-09-01 with Python 3.11.15, Torch 2.7.0+cu128 and
  CUDA 12.8; no checkpoint was loaded and no training job was started. See
  `CHANGELOG/2026-09-01_sdxl_lora_environment_recovery.md`.
- [ ] Select one first training objective (consented identity *or* style), its
  dataset location, unique trigger token/output name, and evaluation prompts.
- [ ] With explicit GPU approval, make one bounded SDXL LoRA smoke run and
  compare it against fixed RealVisXL baseline images before any agent exposure.

## Phase 1 worker-farm bootstrap â€” active, CPU-only

- [x] Build a local-only Redis/Celery foundation under `local_agent/worker_farm/`.
  The checked-in Redis binding is fixed to `127.0.0.1`; no queue listener is
  exposed to Wi-Fi, LoRa, LXMF, or the public internet.
- [x] Implement the first allow-listed workflow: historical-export staging and
  review-only candidate extraction. Raw source and results are AES-256-GCM
  encrypted artifacts; the worker cannot promote memory, write Chroma, render,
  execute commands, or edit the workstation.
- [x] Add cross-platform worker configuration: Windows and Android use the safe
  single-process Celery pool; Linux may use prefork. Remote worker queues remain
  disabled until a private encrypted overlay and separate credentials exist.
- [x] Add an offline doctor and unit coverage for encryption, sanitization,
  review-only output, and invalid-key refusal.
- [x] Install the Phase 1 dependencies: Docker Desktop plus the dedicated
  Python `celery[redis]` environment. Celery 5.6.3, Redis client 6.4.0, and
  Cryptography 46.0.7 are installed in the isolated worker environment; Docker
  Desktop 4.88.1 is installed.
- [x] Create a local `.env` from `local_agent/worker_farm/.env.example` with a
  unique Redis password and a fresh base64 32-byte AES-256-GCM key. Keep it
  local and out of version control.
- [x] Start only the loopback broker, run the benign `--sample` job, and verify
  an encrypted `review_required` result. On 2026-08-29 the broker became
  healthy on `127.0.0.1:6379`, the single CPU-only worker registered
  `distill_export`, and synthetic job `distill_5090ec5b50892412f0c1a04a`
  completed with a result artifact and three review-required candidates.
  No real chat export, model, GPU job, render, Chroma write, or memory
  promotion was performed.
- [ ] Obtain an explicit operator decision and source selection before staging
  any real historical export. The live worker remains restricted to the
  approved review-only workflow; successful synthetic execution does not
  authorize handling private transcripts.
  **Encryption bar, scoped 2026-09-05az; v1 helper 2026-09-05bj:**
  `docs/design_notes/SEALED_CHAT_EXPORT_2026-09-05.md`,
  `CHANGELOG/2026-09-05bj_sealed_export_synthetic_v1.md`.
  Synthetic-only `sealed_export.py` age-seals the distill `--sample`
  fixture; `chats/` is a hard refuse. This still does **not** select a
  source or authorize `submit_distillation` without `--sample`.
- [ ] Add the secondary laptop only after it connects over a private encrypted
  overlay with separate broker credentials. Phone/Termux work remains limited
  to small non-sensitive `edge` batches. The runbook, scripts (WireGuard
  tunnel + relay, scoped Redis ACL credential), and open questions for exactly
  this step are in `docs/WORKER_FARM_PHASE1_5_SECONDARY_NODE_PLAN_2026-08-29.md`.
  Nothing in it has been run; it assumes the Phase 1 single-node sample above
  is accepted first.
- [x] **2026-09-01: operator decided to start using several already-owned
  idle LAN machines (4+, mixed Windows/Linux/Mac) now, ahead of the 10-node
  cluster hardware, "prove connectivity first."** Generalized the plan above
  to N machines in `docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md`
  (hub-and-spoke WireGuard instead of one point-to-point tunnel, one scoped
  ACL credential per machine, Pixel phone explicitly excluded â€” it stays on
  its separate credential-free Termux edge-worker track). Implemented the
  one code prerequisite the Phase 1.5 doc had pre-flagged
  (`celery_app._is_authenticated_loopback_redis_url` now also accepts the
  one fixed WireGuard tunnel-hub address) and a new minimal
  `connectivity_probe` task/queue for the "prove connectivity" milestone,
  both covered by new tests (16 passed, 1 skipped â€” see
  `CHANGELOG/2026-09-01e_multi_node_worker_farm_connectivity.md`).
  **2026-09-01 (same session, continued):** WireGuard hub fully stood up on
  the workstation â€” WireGuard 1.1 installed, hub keypair generated
  (`hub public key: ABIeyNucK9ctn5hPaDWMkworftoxKfg02kHX9RRl9mM=`), hub
  service running on `10.90.90.1:51820`, firewall rule added (UDP 51820
  inbound, all profiles). Mac joined as first peer (`10.90.90.2`, public key
  `H0IsFuY1eREqu4jWXz94fKR9oC+4qdcBU7d83shvNzo=`); ping workstationâ†’Mac
  confirmed 0% loss at 28-108 ms. `mac_worker` Redis ACL credential created,
  scoped to `probe` queue only. Tunnel relay live on workstation
  (`10.90.90.1:6379 â†’ 127.0.0.1:6379`). Scripts in
  `local_agent/worker_farm/wireguard/` (see
  `CHANGELOG/2026-09-01h_wireguard_hub_scripts.md` and
  `CHANGELOG/2026-09-01i_wireguard_hub_standup.md`).
  **2026-09-02:** Mac worker (`celery@Louises-MacBook-Pro.local`) ran
  `worker.py --queues probe`; workstation submitted `connectivity_probe`;
  result returned Mac hostname, platform (macOS 13.7.8 x86_64), and PID â€”
  end-to-end verified. Root cause of earlier failure: `relay/tunnel_relay.py`
  had `MAX_CONCURRENT_CONNECTIONS = 8`; Celery's Kombu transport opens ~8
  persistent broker connections, leaving no slot for the result-backend
  write, which timed out. Fixed: limit raised to 64. See
  `CHANGELOG/2026-09-02a_mac_worker_probe_verified.md`.
  **2026-09-02d:** judge_evaluation verified end-to-end on Mac (see section
  below). ACL DENY probe run â€” see CHANGELOG entry for honest result.
  **Still needed:** relay autostart so it survives reboots; repeat
  Add-WireGuardPeer + credential steps for each additional machine (.3, .4, ...).

- [x] **2026-09-02: standalone farm_health diagnostic.** `local_agent/worker_farm/farm_health.py`
  plus `check_farm_health(timeout_s=5.0)`. CLI:
  `local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_health`.
  Loads `.env` / `FARM_BROKER_URL` the same way `_farm_submit_wait` does, TCP-checks
  the broker host from that URL, then Celery `inspect.ping()` for worker process
  liveness. No summarize/embed/judge/distill job is submitted. Failures become
  `unreachable` / `no_workers` (never raises, never hangs past timeout). Not
  wired into `agent.py` or `farm_offload.py`. Tests:
  `local_agent.worker_farm.test_farm_health`. See
  `CHANGELOG/2026-09-02t_farm_health.md`.

- [x] **2026-09-02: farm_status.json snapshot daemon.** `local_agent/worker_farm/farm_status_daemon.py`
  calls `check_farm_health()` on an interval (default 30s, `--interval` or
  `FARM_STATUS_INTERVAL_S`) and atomically writes `worker_farm/farm_status.json`.
  `farm_health --json` now includes `checked_at`. Not wired into `agent.py` or
  `farm_offload.py`. Tests: `local_agent.worker_farm.test_farm_status_daemon`.
  See `CHANGELOG/2026-09-02v_farm_status_daemon.md`.

- [x] **Farm dashboard bind (2026-09-05dk / 2026-09-05dr).** Default is
  **loopback** `http://127.0.0.1:8765/` (not home LAN). LAN or WireGuard hub
  is opt-in: `$env:FARM_DASHBOARD_HOST='192.168.50.208'` or `'10.90.90.1'`.
  Never `0.0.0.0`. GET-only, no auth (unchanged). Start:
  `powershell -File local_agent\worker_farm\dashboard\Start-FarmDashboard.ps1`.
  Restart the logon dashboard task to pick up the new default. See
  `local_agent/worker_farm/README.md` and
  `CHANGELOG/2026-09-05dr_farm_dashboard_loopback_default.md`.



## Context & Token Optimization (Pillars 1â€“4)

- [x] Pillar 1: Secondary LLM Context Compactor (`local_agent/context_compactor.py`) â€” the exact `llama3.1:8b` helper is installed on `router.CPU_HOST` and passed a controlled live structured-compaction check. It returns strict JSON for `goal`, `decisions`, `open_questions`, `tool_state`, `hard_constraints`, and `notable_files`, with `keep_alive="0"` and no GPU use.
- [x] Pillar 2: Artifact Registry & Tool Pruning (`local_agent/artifacts.py`) â€” oversized tool outputs are persisted under `runtime/artifacts/{id}.json` with SHA-1 fingerprints; live prompts retain a â‰¤2,400-character pointer instead of the raw output.
- [x] Pillar 3: Autonomous Memory Extraction (`local_agent/memory_extractor.py`) â€” the exact CPU helper is installed and passed a controlled sensitive-input check that stored no fact. Extraction is asynchronous, capped, CPU-only, and rejects sensitive or transient facts before `memory.remember()`.
- [x] Pillar 4: Byte-Stable Prompt Prefix Memoization (`local_agent/prompt_prefix.py`) â€” static policy, operating-memory, learned-lesson, recalled-memory, and scoped-project sections are deterministically ordered and cached with `@lru_cache(maxsize=128)`.
- [x] Router bug fix: VRAM eviction (`local_agent/router.py`) â€” `decide()` now requests eviction and verifies the original resident models have disappeared from `/api/ps` before a CPU handoff. Unverified eviction safely refuses the handoff.

## High-Priority Architectural Fixes

### Idle-8188 GPU picker (2026-09-06h)

- [x] `status()` inventories GPU tags when `timeshare_idle` so 14B stays selectable after restart while Comfy listens idle. Evidence: `CHANGELOG/2026-09-06h_timeshare_idle_picker_available.md`. `APP_REVISION=2026-09-06-timeshare-idle-picker-r88`.

### ComfyUI timeshare follow-ups (origin CHANGELOG 2026-09-04q / 2026-09-04u / 2026-09-04z)

- [x] Option B live verify (six cases, 2026-09-04u): idle 8188 â†’ 14B `/free`; hop-N no second `/free`; live owner â†’ CPU+evict; post-generate 2461â†’413 then 14B; farm skip no `/free`; `EQUAL_SHARES_COMFY_TIMESHARE=0` restores 8188-hard-busy. Evidence: `CHANGELOG/2026-09-04u_comfy_timeshare_live_verify.md`.
- [x] Option B PR 2 live re-verify (2026-09-04z): same six outcomes against urllib-first queue + occupancy rewrite + host-GPU gate. Extra probes: non-empty urllib never MCP-lists; ComfyUI `python.exe` is not occupancy (`/free` still proceeds); Qwythos/CPU-only pins do not enter the timeshare gate. Remaining-unsafe 5 documented live (348â†’348 is **not** a GPU-resident drop; 2462â†’414 is). Evidence: `CHANGELOG/2026-09-04z_comfy_timeshare_pr2_live_verify.md`. **Option B is fully closed.**
- [x] `status()` badge third state (`8188 up, idle, agent may claim`) from owner files + last-known queue cache. No MCP/urllib `/queue` from `status()`. Origin: CHANGELOG `2026-09-04q`. Closed: `2026-09-04aa`.
- [x] `agent.py` `gpu_gate`: 8188-only busy and timeshare would claim â†’ sidebar `gpu_gate.request()` before hop-0 `decide()` / `/free`. Claim WARNING removed. Origin: CHANGELOG `2026-09-04q`. Closed: `2026-09-04aa`. **Timeshare feature fully closed â€” no further follow-ups.**

- [x] VRAM Eviction Lock (`router.py`): CPU handoff now waits for verified local-Ollama eviction; an unreadable or timed-out `/api/ps` response fails safely rather than risking stale-VRAM OOMs.
- [x] LXMF Race Condition (`phone_scheduler.py`): jobs receive a persisted lease before an LXMF send. Concurrent loops cannot send the same counter twice, and expired crash leases become `uncertain` rather than auto-retrying duplicates.
- [x] Memory Queue Unbounding (`feedback_manager.py`): feedback encryption has a 256-record cap, metadata-only overflow/poison quarantine, and a three-failure ceiling for records that cannot be encrypted.

## PowerInfer control-plane evaluation â€” opt-in, not active

- [x] PowerInfer hops (`backend="powerinfer"`) now get a distinct text-only
  system prompt in `apply_hop_profile()`, not the full agentic
  `system_prompt()`. Native schemas were already `[]` and the UI already
  noted "text-only"; the model was still being told to call tools it cannot
  invoke. Project/memory/operating-memory sections are kept. GPU and
  CPU/farm prompts are unchanged. Regression:
  `test_powerinfer_system_prompt_is_text_only_not_tool_assuming`. Closed:
  `CHANGELOG/2026-09-05a_powerinfer_text_only_system_prompt.md`.
- [x] Add a loopback-only OpenAI-compatible PowerInfer adapter contract at
  `local_agent/powerinfer_openai_proxy.py`; it is unlaunched and is not wired
  into normal agent startup or routing.
- [x] Verify the exact RTX 5080/Ryzen CUDA build, a supported sparse PowerInfer
  model plus matching predictor/activation files, license, hashes, and actual
  host-RAM/VRAM requirements. Do not assume an arbitrary 70B GGUF or the
  existing Qwen/Ollama models gain sparse acceleration. Native compile/setup
  prerequisites are now present: CUDA 12.8 (`nvcc`), RTX 5080 driver 595.97,
  and Visual Studio 2022 (17.x) Community/Build Tools with the C++ workload.
  The upstream source is now cloned at `external/PowerInfer` and its isolated
  Python environment imports its required packages with CUDA 12.8 PyTorch;
  all 32 predictor/activation assets were calibrated, converted, hash-recorded,
  and mechanically validated through a loopback-only native run. The candidate
  remains isolated and unregistered.
  VS 2022 now compiles PowerInfer successfully through its Ninja developer
  environment with CUDA 12.8/cuBLAS and `sm_120`. The runner uses short A:
  source/build paths to avoid the canonical repository path-length failure.
  `SparseLLM/ReluLLaMA-7B` is downloaded, hash-recorded, and passes the strict
  ReLU/shape gate; its public 8,000-record calibration manifest is also ready.
  The candidate sparse model remains ReluLLaMA-7B (`relu-llama-7b`), not
  ProSparse. Its controlled native service has been stopped after validation.
- [x] Install Visual Studio 2022 (17.x) Build Tools with **Desktop development
  with C++** and complete the controlled native CUDA build. The source remains
  at `external/PowerInfer`; its short-path junction/build are
  `A:\PowerInferNative` and `A:\PowerInferBuild`.
- [x] Run the controlled text-only mechanical acceptance gate: final evidence
  `validation/acceptance_gate_20260830_175953.json` records CUDA, 2,322 MiB
  sparse FFN offload, 32 activation files, and 20 cold + 20 warm loopback turns
  with zero request failures. The endpoint was not kept running.
- [ ] Conduct a human quality comparison against the current Ollama routes
  before enabling the endpoint for interactive Teacher turns or Harmon Town
  Stage dialogue. The fixed benign packet and verifier are
  `tools/powerinfer/quality_comparison.py`; the prepared packet is
  `validation/quality_review_packet.json`. Initial controlled capture against
  `huihui_ai/qwen3-abliterated:8b` found the current ReluLLaMA candidate fails
  nine of ten basic instruction/format cases, so it is **not eligible for
  promotion**. Preserve it as diagnostic evidence; investigate prompt/template
  alignment before any future re-test. Do not promote a mechanical benchmark
  into a routing change.
- [x] Obtain explicit GPU-gateway approval before `dump`: this is the first
  operation that loads ReluLLaMA-7B weights to produce activation/predictor
  artifacts. It must not overlap ComfyUI, vision, or a render. The approved
  ReluLLaMA-7B dump completed on 2026-08-30; it created all 32 activation and
  predictor-input layer pairs and released VRAM afterward.
- [x] Complete the bounded predictor-training calibration across the remaining
  layers, then compare held-out recall, runtime, temperature, and artifact
  integrity before choosing production training settings. All 32 layers exist
  in the staging workspace. Aggregate held-out recall
  min/mean/max is 0.7986/0.8262/0.8668. See
  CHANGELOG/2026-08-30_powerinfer_bounded_predictor_calibration.md.
- [ ] Require a fresh GPU-gateway approval and keep PowerInfer separate from
  ComfyUI, VLM/media, and Celery/Redis batch workers. Never bind it outside
  loopback or let a worker/phone start or stop it.
- [ ] Parked: TurboSparse-Mistral projected abliteration. Canonical weights
  only:
  `A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`
  (32/32 `o_proj` edited, `down_proj` unchanged, max norm drift 2.1e-4,
  Bamboo/ReLU reload + finite one-layer forward). Do **not** use `...20260830`
  without the `b`. Root cause of the old 2/4 shard stall was host-RAM pressure
  from full-shard loading; the streaming `safe_open` loader is the fix.
  Calibration used eight synthetic pairs and is exploratory only. Predictors
  have **not** been rebuilt; no quality benchmark has been run. **Do not dump,
  train, convert, or run production benchmarks** until operator-approved
  harmful/harmless pairs exist. Predictor/activation regeneration from this
  exact tree is then mandatory before any quality claim. Do not overwrite the
  source snapshot, ReluLLaMA GGUFs, or existing predictor artifacts.
- [x] Prepare the TurboSparse-specific conversion and quality infrastructure:
  dedicated Bamboo/ReLU target, reviewed-local-code flag, checkpoint ChatML
  prompt-contract receipt, and a fail-closed two-turn JSON tool-call gate. The
  current `20260830b` source now deliberately refuses predictor generation:
  it was created from eight synthetic pairs. First rebuild a **new immutable**
  edit using at least 32 operator-approved pairs, then regenerate predictors,
  convert, and run the gate against a manually launched loopback server. The
  native 20-turn acceptance harness now uses that same ChatML contract and
  keeps generated answers transient rather than storing them in evidence.
- [x] Research the official PowerInfer Bamboo-DPO 7B sparse/instruction
  candidate as the next quality-gate target. The research precheck and
  immutable remote revision/hash lock are in
  `tools/powerinfer/BAMBOO_DPO_INTAKE_PRECHECK.md` and
  `tools/powerinfer/bamboo_dpo_remote_metadata_2026-08-30.json`; the local
  receipt verifier is `verify_bamboo_dpo_intake.py`. The frozen received source
  verifies Bamboo dReLU (`relu(gate) * relu(up)`). Do not substitute an
  ordinary dense or Qwen checkpoint.
- [ ] Bamboo-DPO Q4 runtime intake is complete and byte-verified as a
  **candidate only** at
  `A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake`. Its isolated
  mechanical gate passed: native sparse loading + CUDA + 3,024 MiB FFN GPU
  offload, with VRAM released on exit. The frozen prompt-contract classifier
  records `prompt_contract_unresolved`: no chat template or explicit source
  instruction format. Its frozen model code does support one plain
  raw-completion example, so a separately approved bounded raw-completion
  diagnostic is permittedâ€”but it is not an instruction/format comparison. The
  approved 2026-09-01 diagnostic completed unscored with CUDA/sparse evidence,
  3,024 MiB FFN offload, and VRAM released; receipt:
  `validation\bamboo_dpo_raw_completion_20260901_113452.json`. It did not
  resolve the prompt contract or qualify the candidate for any route.
  Obtain source-backed prompt-format evidence before any ten-case
  instruction/format comparison. Keep it unregistered until it passes behavior
  and latency/thermal gates; preserve failed captures as immutable evidence.
  2026-09-05cf public-source pass (no load, no intake files): HF tokenizer
  has no `chat_template`; the only documented generate example is raw
  completion; DPO YAML lists `jondurbin/bagel-v0.3` (four formats, none
  shipped). **Still `prompt_contract_unresolved`** â€” bagel narrows the lead,
  it does not pick a wrapper. Ten-case comparison remains unauthorized.

## Model Conversion & Profiling â€” mandatory preparation track

- [x] Define the model lineage, storage, validation, and deployment gates in
  `docs/MODEL_CONVERSION_AND_PROFILING_PLAN_2026-08-29.md`. The plan covers
  base, abliterated, and post-LoRA-merge candidate models without assuming that
  every ordinary GGUF/Safetensors checkpoint can gain PowerInfer sparsity.
- [x] Document a reproducible predictor/profiling path for the parameterized
  targets in `tools/powerinfer/` (DejaVu-style dump/train + `activation_L.pt`
  solver histograms). The live supported-sparse PoC is `relu-llama-7b`
  (`SparseLLM/ReluLLaMA-7B`, plain ReLU, `model_type=llama`). `prosparse-7b`
  is parked/retired because FATReLU / `sparsellama`. The research route remains
  `llama31-8b-abliterated-relu`. The native CUDA build is now verified; a
  supported model plus predictor/activation assets still require separate
  controlled validation before any live inference.
- [x] Implement per-build manifests with source/calibration/predictor/activation
  /GGUF SHA-256 and `candidate|quarantine|accepted` (`write_manifest.py`).
  Intake still requires `-Execute` to download; it does not load VRAM.
- [x] Establish an encrypted model-vault/scratch layout outside the repository
  (`tools/powerinfer/vault.py`, `init_vault.py`): free-space preflight with 20%
  margin, source read-only after hash, per-build activation/predictor dirs,
  SHA-256 records, AES-256-GCM private envelopes, no delete API for evidence.
  Preferred root is `D:\PowerInferModels`. `run_pipeline.ps1` now calls
  `vault.init_vault()` once before any real stage runs and refuses to
  proceed if the resolved vault falls back to the in-repo default (no `D:`
  drive present and no explicit `-Vault`/`POWERINFER_VAULT`) rather than
  silently writing GGUFs/activations into the git tree with no `.gitignore`.
  See `CHANGELOG/2026-08-29e_powerinfer_vault_wiring.md`. Per-stage bundle
  directory creation still uses its own ad-hoc `New-Item` calls rather than
  `vault.create_bundle()`/`bundle_paths()` â€” a reasonable follow-up, not a
  safety gap.
- [x] Add a controlled profile/convert runner (`tools/powerinfer/run_pipeline.ps1`)
  that refuses ComfyUI-port/render owners, refuses overwrite without `-Force`,
  and stays off the launcher. Live GPU execute remains operator-initiated.
- [x] Add the 20-turn cold/warm acceptance-gate recorder (`record_acceptance_gate.py`)
  for latency, tokens/sec, RAM, VRAM, solver/split flags, and artifact hashes.
  Held-out coherence/tool-call quality vs Ollama is still a later gate.
- [x] Require an explicit accepted validation manifest before a model can enter
  the local PowerInfer production registry or its loopback OpenAI proxy can
  start. `tools/powerinfer/production_registry.py` rechecks the accepted
  manifest, acceptance evidence, supported-sparse route, and GGUF hashes both
  at registration and proxy startup; candidate, tampered, retired, and
  incomplete bundles are refused.
- [ ] After an accepted model exists, deliberately wire the registered endpoint
  into real-time interactive use, Harmon Town post-character-LoRA deployment,
  or Judge evaluation-loop routing. Existing Ollama routes remain the fallback;
  no task may silently change those routes.

## PowerInfer-2 mobile edge evaluation â€” planning only

- [x] Keep TurboSparse abliteration research isolated. The streaming
  `tools/powerinfer/abliterate_turbosparse_v2.py` pathâ€”not the preserved
  pre-fix `abliterate_turbosparse.py`â€”produced the canonical `20260830b`
  staging tree without source overwrite. Its synthetic calibration remains
  exploratory. Do not rebuild predictors/activations, run a GPU dump/train/
  convert/benchmark, or reuse pre-edit predictors until operator-approved
  harmful/harmless pairs and a separate GPU approval exist.

- [x] Record the mobile architecture correction: Pixel 10 Pro uses Tensor G5,
  not Qualcomm/Hexagon. The current upstream Android material documents the
  sparse SmallThinker runtime, but not a Tensor/NNAPI backend. See
  `docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md`.
- [x] Add an inert, stdlib-only Termux edge-worker gateway contract at
  `local_agent/worker_farm/termux_powerinfer2_edge_worker.py`. It does not
  receive Redis/AES credentials, connect to Celery, start a service, or run by
  default; tests verify HTTPS/private-overlay, job-kind, and shell-free command
  boundaries.
- [x] On an x86_64 Linux/WSL host, reproducibly cross-build the exact pinned
  upstream Android sparse runtime and record source/NDK/binary/model/bundle
  hashes. Do not compile inside Termux and call it an NPU build. **Done
  2026-09-05, pins accepted by operator same day** (the plan doc had never
  named an exact commit/NDK version, only placeholders â€” Grok's choices of
  commit `8bd56d6` and NDK r27d LTS are now the locked project pins).
  Produced a real ELF64 AArch64 PIE `llama-cli` for
  `aarch64-linux-android34`, built on WSL (not Termux), not run on a phone.
  Full hashes: `docs/POWERINFER2_CROSSBUILD_2026-09-05.md`. Locked pins
  also recorded in `docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md`.
  Evidence: `CHANGELOG/2026-09-05i_powerinfer2_android_crossbuild.md`,
  `2026-09-05k_powerinfer2_pins_accepted.md`.
  Host build exists (2026-09-05, see
  `docs/POWERINFER2_CROSSBUILD_2026-09-05.md` and
  `artifacts/powerinfer2_android_arm64/2026-09-05/`) but this box stays
  unchecked: the plan names the Tiiny-AI/PowerInfer repo without a
  commit/tag, and NDK is still the `<pinned-ndk-version>` placeholder.
  This session used `8bd56d69906c9d2dba4d3bf6899763401e01a9a4` (existing
  `external/PowerInfer` HEAD, not a newer `main`) and NDK r27d LTS
  (`27.3.13750724`) and recorded hashes. No model/bundle was fetched.
  Accept those two pins before checking this off.
- [ ] Run a single benign, battery/thermal-observed Pixel test with
  `huihui-ai/SmallThinker-3B-Preview-abliterated` (chosen 2026-09-05 over the
  official non-abliterated `PowerInfer/SmallThinker-4BA0.6B-Instruct` for
  runtime-compatible provenance already used elsewhere in this stack â€”
  see `huihui_ai/qwen3-abliterated:8b`; accepted size mismatch, 3B not 4B)
  before considering a 21B model. Do not root the phone or claim NPU use
  without a supported Tensor backend and device evidence.
- [x] Implement and review a private-overlay edge gateway with per-device
  credentials, mTLS, capability limits, job leases, replay refusal, revocation,
  and size limits. Only then enable small non-sensitive phone batches.
  **v1 built 2026-09-05.** Overlay installed; listeners
  `10.90.91.1:8743` / `127.0.0.1:8744` (PID 46176). **G6â€“G9 accepted
  2026-09-05 via independent workstation test** (`2+2`, device
  `ws-indep-1`, overlay HTTPS not loopback; lease is idempotent same
  job; mutated complete 409; oversized inject 400; revoke 401; logs
  sizes-only). **G10 overlay is up; runtime files hash-ok; model
  staged, `--once` still not run.** `QuantFactory` GGUF of
  `huihui-ai/SmallThinker-3B-Preview-abliterated` **Q4_K_M**
  (2â€¯104â€¯931â€¯296 bytes, SHA-256
  `514100b5dcf6b4e958cb241d77b079286fa8687e6b17de0822f61639eda3107e`)
  downloaded and ADB-pushed to Termux Android/data; device hash
  matches. Termux home does not have the GGUF yet â€” waiting operator
  inward `cp`. No inject. Evidence:
  `CHANGELOG/2026-09-05dy_g10_termux_copies_hash_ok_model_missing.md`,
  `CHANGELOG/2026-09-05ea_g10_smallthinker_q4km_staged.md`.
- [ ] Later, separately: abliterate `PowerInfer/SmallThinker-4BA0.6B-Instruct`
  itself (no published abliterated variant of this exact checkpoint exists as
  of 2026-09-05) to close the size gap with the plan's original 4B sparse
  target. This is new abliteration work, not a reuse of the parked
  TurboSparse-Mistral pipeline â€” it still requires the project's standing
  calibration-and-operator-approval process before any predictor rebuild, GPU
  dump/train, or benchmark; do not start it opportunistically alongside
  unrelated tasks.

## Deferred distributed worker farm â€” planning only

- [ ] **10-node asynchronous Worker Farm** â€” planned control-plane/worker-plane
  split: the Ryzen/RTX 5080 workstation remains the interactive controller;
  a future 10-node, 60-core, 160-GB aggregate-RAM cluster runs only queued,
  background work. No cluster service, model, download, network listener, or
  external account is authorized by this roadmap alone.
  - [ ] Establish the 1-GbE capacity baseline: inventory every node, measure
    throughput/latency, reserve OS headroom, and record the fact that aggregate
    RAM is distributed rather than a shared 160-GB address space.
  - [ ] Prototype a private RabbitMQ ingress with publisher confirms, manual
    acknowledgements, bounded prefetch, dead-letter queues, idempotency keys,
    and compact artifact referencesâ€”not raw logs or documents in messages.
  - [ ] Add Celery for durable fetch/extract/encrypt workflows and Ray actors
    for batched CPU-model and multi-agent workloads; benchmark the smallest
    stable distributed judge group before any 70B claim. Do not treat a
    10-stage 1-GbE pipeline as low latency; use micro-batches and independent
    horizontal worker pools to maximize throughput.
  - [ ] Build four operator-reviewed workflows: encrypted Judge evaluation;
    source-attributed Researcher/Chroma ingestion; Teacher/Student synthetic
    JSONL generation; and historical ChatGPT/Claude export distillation into
    clean, source-traceable memory candidates.
  - [ ] Encrypt raw artifacts and backups with authenticated AES-256-GCM;
    keep Chroma searchable on encrypted storage behind one ingestion gateway.
    Never embed ciphertext or raw noisy chat exports directly.
  - [ ] Gate all production work on private-network isolation, source/license
    provenance, encrypted-backup/restore testing, queue failure recovery,
    human review of promoted memories/training data, and proof that workers
    cannot control the workstation.
  - [ ] See `docs/WORKER_FARM_ARCHITECTURE_PLAN_2026-08-29.md` for the
    staged Kanban-ready implementation plan and acceptance gates.

- [x] **comfyui-mcp integration for local_agent** â€” implemented 2026-09-04
  (see `CHANGELOG/2026-09-04e_comfyui_mcp_client_and_tools.md`). Node
  v24.15.0 already installed. `local_agent/mcp_client.py` + seven
  `comfy_*` tools, project-only `comfy_process`/`comfy_nodes`, process
  guardrail on `thermal_guard.sample_gpu()` + `router.queue_owner()` /
  batch / image-render live PIDs. Mocked stdio suite: 10+14 tests OK.
  Live MCP handshake against real `npx -y comfyui-mcp` listed 41 tools
  in 1.0s. `comfy_process` refuse proven with a live PID on the real
  owner file (restored byte-for-byte). **Stopped before a real render:**
  port 8188 was not listening (`ECONNREFUSED` on `/system_stats`); did
  not start ComfyUI, did not `comfy_generate`, did not
  `comfy_models(remove)` / `comfy_nodes(install)` / `comfy_process` live.
- [x] **comfyui-mcp live generate** â€” done 2026-09-04 (see
  `CHANGELOG/2026-09-04j_comfyui_mcp_live_generate.md`). Node v24.15.0.
  Stage supervisor pid 16900 dead; one Rockernow ComfyUI on 8188 with
  Shared input/output. Live `comfy_system` returned real
  `comfyui_version=0.34.0` / RTX 5080 stats (39.81s). Live
  `comfy_generate` prompt_id `8182b9d1-e080-4d9e-9f85-bc5bccdb4be6`
  wrote `A:\Users\rhine\ComfyUI-Shared\output\ComfyUI_00214_.png`
  (512Ã—512 RGB, 317295 bytes). Did not live-call
  `comfy_models(remove)` / `comfy_nodes(install)` / `comfy_process`.
- [x] **comfyui-mcp live `comfy_process(restart)`** â€” done 2026-09-04 (see
  `CHANGELOG/2026-09-04v_comfy_process_live_restart.md`). Thermal refuse
  with live nvidia-smi 31 C vs in-process `START_MAX_C=30` (restored to
  70). Fake owner lock pid 30984 on the real queue-owner file, refused,
  restored byte-for-byte. Default MCP restart did **not** cycle
  (Desktop misclassify, PID 40924 unchanged). Real cycle via
  `COMFYUI_RESTART_COMMAND` (`restart_comfy_rockernow.ps1`): PID
  **40924 â†’ 37056**, same Rockernow argv. `comfy_generate` after:
  `bc1d7c5b-â€¦` â†’ `ComfyUI_00218_.png` 377697 bytes.
- [x] **comfyui-mcp live `comfy_nodes(install)`** â€” done 2026-09-04 (see
  `CHANGELOG/2026-09-04w_comfy_nodes_live_install.md`). Throwaway local
  git pack (no pip deps), commit `e047a3b`. Landed at Rockernow
  `custom_nodes/comfyui-mcp-throwaway-probe` after pointing
  `COMFYUI_PATH` at the code checkout for that call. Audit
  `risk=custom_node_install` at 2026-09-04T18:01:49. Pack left on disk,
  not loaded (no extra restart).
- [x] **comfyui-mcp live `comfy_models(remove)`** â€” done 2026-09-04 (see
  `CHANGELOG/2026-09-04x_comfy_models_live_remove.md`). Dummy
  `embeddings/mcp_throwaway_probe.safetensors` (37 bytes) in Shared
  models; MCP unlinked it. No operator weights touched. Audit
  `risk=model_delete` at 2026-09-04T18:05:10.
- [x] **`comfy_workflow` enqueue accepts a file path** â€” done 2026-09-05
  (see `CHANGELOG/2026-09-05d_comfy_workflow_path_load.md`). 2026-09-05b
  case 4: models passed `workflow_path` / path-as-`workflow`; MCP wants
  a record. Wrapper now loads/parses the JSON (also JSON-string graphs).
  Mocked suite 16â†’25. Live `workflow_path` enqueue of
  `txt2img_mcp_test.json`: prompt_id
  `60b78f0f-f3e1-4f11-b4bc-2239e438ff5f` â†’
  `output/mcp_test/task_completion_20260905_00001_.png` 446242 bytes.
- [x] **Farm efficiency, ticket 1 (do first) â€” Mac worker `--concurrency=2`
  experiment.** Done 2026-09-04: **negative result, reverted to 1.**
  Evidence: `CHANGELOG/2026-09-04n_mac_celery_concurrency_2_reverted.md`.
  Eight 8-chunk `embed_chunks` jobs, live `celery@Louises-MBP`,
  `nomic-embed-text:latest`. Wall clock **90.973 s at conc=1** vs
  **89.769 s at conc=2** (+1.3% throughput, noise). Worker-side time
  **11.3 s â†’ 20.8 s mean**; client min **9.1 s â†’ 20.7 s**. Both
  ForkPoolWorkers overlapped; single `ollama serve` serialized the
  embeds. Thermal/swap not the failure (no swapouts; thermal peak 63 vs
  55). Live flag restored: `FARM_CONCURRENCY=1`. Do not retry 2 without
  a change on the Ollama side.
- [x] **Farm efficiency, ticket 2 â€” progressive-disclosure meta-tool layer
  for `tools.py`, generalized into model-aware harness profiles (operator
  idea, 2026-09-04).** Implemented 2026-09-04o per
  `docs/HARNESS_PROFILES_DESIGN_2026-09-04.md`. `schemas(profile="gpu")`
  (default) still sends all 67 tools; `tier=cpu` or farm gets virtual
  `list_tools`/`describe_tool`/`call_tool` (not in `TOOLS`). Per-hop
  switch off `router.Decision`. `call_tool` unwraps in `run_one` so
  guards see the inner name; direct real names still dispatch.
  **Layer B shipped 2026-09-04p:** CPU/farm-only resolver intents
  `web_search`, `capabilities`, `list_memory`, plus relative `list_dir`
  for the 2026-09-04o compact miss (bare folder name). Default GPU
  `classify()` is unchanged. Tests: **76/76**
  `test_native_tool_calling.py` (unchanged this PR) and **46/46**
  `test_action_resolver.py` (29 existing held + 17 new). Live compact
  farm turn: GPU classify None, CPU classify `list_dir{path:local_agent}`,
  inner listing executed, Qwythos/chat_stream not called, 4.3 s
  (`artifacts/benchmarks/2026-09-04p_cpu_resolver_intents_live.json`).
  v1 live Qwythos receipt remains
  `artifacts/benchmarks/2026-09-04m_compact_qwythos_live.json`.
  `CORE_DIRECT_TOOLS` remains rollback-only, not advertised. Full
  analysis: `docs/FARM_EFFICIENCY_EVALUATION_2026-09-04.md`.
- [x] **Farm efficiency, ticket 3 â€” gather evidence before offloading
  `run_code` to the farm.** Closed 2026-09-04 **not worth building**
  (`CHANGELOG/2026-09-04m_run_code_cpu_contention_not_worth_building.md`).
  Real sessions almost never call it (3 executed calls across saved chats;
  two sandbox/language errors, one short traceback). Agent loop does not
  overlap `run_code` with host generation on the same hop. Forced overlap
  vs CPU Ollama (`llama3.1:8b`, `num_gpu:0`, `num_thread:4`): typical
  `run_code` 0.06â€“0.22s; busy 1-core loop slowed generate by **2.0%**
  (10.73 â†’ 10.52 tok/s). No offload code written.
- [ ] **Farm efficiency, ticket 4 â€” Ratchet Loop (autoresearch-style
  auto-revert): deferred, not scoped as a farm item.** NOT a quick win and
  NOT recommended near-term â€” flagging here so it's visible in the queue
  rather than buried in the doc, not as something to start. High effort,
  and the real blocker is risk, not code: automatic `git revert` gated on a
  mechanical test metric is exactly the class of action `CLAUDE.md` treats
  as most dangerous elsewhere in this project (see its evidence-preservation
  and destructive-command rules). It also isn't really about farm
  *efficiency* â€” it's a different capability (autonomous test-and-fix
  loops), best fit so far being PowerInfer calibration tuning, already
  noted as a bookmark on 2026-09-02, not this project. Needs its own
  explicit go/no-go conversation with the operator before any design work,
  separate from tickets 1-3 above. Full reasoning:
  `docs/FARM_EFFICIENCY_EVALUATION_2026-09-04.md`.
- [x] **Ops â€” Mac Qwythos cold-load on every farm tool-calling turn.
  Closed 2026-09-05o.** Live LaunchDaemon
  `system/com.local-agent.ollama` had **no** `OLLAMA_KEEP_ALIVE`
  (plist + `launchctl` + `ps eww`; Ollama default 5m). `sudo -n` cannot
  rewrite `/Library/LaunchDaemons/com.local-agent.ollama.plist`; 30m
  copy staged at `local_agent/worker_farm/macos/com.local-agent.ollama.plist`.
  Live fix without sudo: farm task `keep_alive=_QWYTHOS_KEEP_ALIVE`
  (`"30m"`), same convention as CPU-tier `Start-Server` `$CpuOnly`.
  Mac `ollama_client` already forwards the field. Timed on Louises-MBP
  `:11434` (the process `qwythos_evaluate` uses): first **45.300 s**
  (`load_duration` 40.882 s, cold), immediate second **3.188 s**
  (`load_duration` 0.058 s, warm); `ollama ps` **UNTIL 29 minutes**.
  Celery `try_qwythos_on_farm` two-call skipped (`farm_status` flapped
  `ok` â†’ `no_workers`). Prior farm cold: 62.423 s (2026-09-04k) with
  `ps` empty after. Evidence:
  `CHANGELOG/2026-09-05o_qwythos_mac_keep_alive_30m.md`.
  **2026-09-05aa:** Mac back; hung Celery + 3 orphan workers cleaned;
  `farm_health` `ok` with `qwythos_evaluate` registered.
  **2026-09-05aq:** live LaunchDaemon now has `OLLAMA_KEEP_ALIVE=30m`
  (`launchctl` + `ps eww`). Daemon-default two-call (no request
  `keep_alive`): **23.946 s** cold / **2.526 s** warm; still loaded
  after 5m30s idle (**2.156 s** third call). Evidence:
  `CHANGELOG/2026-09-05aq_ollama_daemon_keepalive_30m_live.md`.
- [x] **Ops â€” dedicated CPU Ollama on 11435 dies during GPU discovery
  (`CUDA_VISIBLE_DEVICES=-1`). Closed 2026-09-04y.** Root cause:
  Ollama 0.32.15 `CUDA_VISIBLE_DEVICES=-1` only skips CUDA; Vulkan
  still enumerated the RTX 5080 (upstream ollama#16508). Not a
  Windows env-propagation miss. Launcher `Start-Server` `$CpuOnly`
  now also sets `OLLAMA_VULKAN=false` and `GGML_VK_VISIBLE_DEVICES=-1`.
  Live after (pid 19960, actual `Start-Server`): psutil
  `OLLAMA_VULKAN=false`; `inference compute id=cpu library=cpu`;
  `total_vram="0 B"`. Comfy `:8188` up: `decide()` stayed on 11435
  Huihui 8B `size_vram=0` / `-ngl 0`; 11434 `/api/ps` stayed empty.
  Diagnosis stopgap pid 30080 was session-only, not this fix.
  Evidence: `CHANGELOG/2026-09-04y_cpu_ollama_11435_disable_vulkan.md`.

- [x] **Capability-based dynamic model routing â€” operator decision
  2026-09-04. Implemented 2026-09-04i** (pulls 2026-09-04h).
  `local_agent/router.py` + `farm_offload.py` (no new `model_router.py`).
  Tags: Qwythos `richardyoung/qwythos-9b-abliterated:latest`
  (`82663f041302`) on Mac via farm Celery summarize queue; DeepSeek
  `huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M`
  (`6b2209ffd758`); Coder **`josiefied-qwen2.5-coder-14b:q4_k_m`**
  (`4a4b6c1f443c`). Host 14B swap uses existing `unload()` /
  `keep_alive: 0` + `/api/ps`. GPU path refuses on
  `thermal_guard` / `queue_owner` / Comfy :8188. Tests:
  `test_capability_routing.py` 16 OK + router 42 + farm_offload 44.
  Live 2026-09-04i: Comfy :8188 up â€” toolâ†’farm Qwythos decision;
  code/logic refused GPU and used CPU 8B; Celery Qwythos returned
  None (worker not yet restarted). **Live gaps closed 2026-09-04k:**
  Mac `~/worker_farm` restarted; `try_qwythos_on_farm` returned
  `{"content":"OK",â€¦}` in 62.4 s (not None). Idle Comfy backend
  stopped after empty-queue/0%-GPU check; DeepSeekâ†’Coder swap sent
  real `keep_alive:0` to DeepSeek, `/api/ps` emptied, Coder loaded
  and answered `def ping(): return 1`. Evidence:
  `CHANGELOG/2026-09-04i_capability_model_routing.md` (routing/tests),
  `CHANGELOG/2026-09-04k_capability_routing_live_verify.md` (live).
  **VRAM sizing math done 2026-09-04:** `MODEL_VRAM_BUDGET.md` â€” Q4_K_M
  @ `num_ctx=8192` recommended (8.99GB weights + 1.5GB FP16 KV + 1.25GB OS
  = 11.74GB, 4.3GB headroom). Q8_0 fails the 16GB check outright. 32B
  alternative fails at every practical quant/context combo tested (Q3_K_S
  alone is already 16.65GB at just 4k context). 8B alternative passes with
  large headroom but is a real reasoning-depth tradeoff, not just a sizing
  one.
  **Superseded for live `num_ctx` 2026-09-05dx:** 95% of this 5080's
  VRAM-fit max, per deployed GGUF + per-model GQA, is now wired in
  `router.GPU_VRAM_NUM_CTX`. 8192 remains farm/Qwythos only.

- [x] **GPU-resident `num_ctx` ceilings from this card's VRAM math
  (2026-09-05dx).** Not a routing change. Alone-on-GPU, FP16 KV, 1.25 GiB
  leftover, explicit 15.21% graph scale from a 2048â†’8192 primary-14B
  delta. Live 14B @ 33976: 13986 MiB used / 1992 MiB free, no OOM.
  Table: primary 33976, fallback 40960 (native), DeepSeek/Josiefied 28371,
  Heretic 1742 (Q4_K_M already collides with leftover). Evidence:
  `MODEL_VRAM_BUDGET.md` addendum, `CHANGELOG/2026-09-05dx_gpu_vram_num_ctx_ceilings.md`.

- [x] **Coder/DeepSeek tool-template retags (2026-09-05n). Did not
  promote.** Follows `CHANGELOG/2026-09-05g`. New tags (old tags kept):
  `josiefied-qwen2.5-coder-14b:official-tools` (`1017c800fa73`, same
  GGUF layer, official `qwen2.5-coder:14b` template including
  no-backticks); `deepseek-r1-abliterated-14b:r1-tools` (`70cf39bd428e`,
  same DeepSeek weights, aleshribar3-style R1 `.Tools` template â€” not
  Huihui ChatML). Live: Coder retag still did **not** populate native
  `message.tool_calls` on the case-3 `run_code` prompt (fenced or raw
  JSON in `content`). Stock `qwen2.5-coder:14b` control failed the same
  way. DeepSeek r1-tools: first hop empty; second hop native
  `tool_calls` **did** fire but called `see_image` on README.md with
  invented `language=python` â€” untrustworthy. **`router.py` defaults
  unchanged** (`JOSIEFIED_CODER_MODEL` / `CODING_MODEL` still
  `:q4_k_m`; `CAP_LOGIC` still DeepSeek). Operator still decides
  whether tool-using logic hops should prefer Huihui-14B.
  Evidence: `CHANGELOG/2026-09-05n_coder_deepseek_tool_template_retags.md`.

- [x] **Content-JSON tool promoter (2026-09-05t).** Parser-level, not a
  prompt/`TOOL:` workaround. `agent.parse_content_json_tool` promotes a
  standalone `{"name","arguments"|"parameters"}` object in content when
  native `tool_calls` is empty and the name matches an advertised schema.
  Live case 3: both `josiefied-qwen2.5-coder-14b:official-tools` and stock
  `qwen2.5-coder:14b` now **execute** `run_code` (sandbox AssertionError
  on the buggy clamp). Tests: `test_native_tool_calling` 108 OK with
  fenced/bare promote + prose/malformed reject. Evidence:
  `CHANGELOG/2026-09-05t_content_json_tool_promoter.md`.

- [x] **DeepSeek-14B tool-calling closed (2026-09-05at).** One more
  attempt: temp 0.0 + `think=false` still called `see_image` on README.md;
  `num_predict=128` truncated before any call; `read_file`-only schema
  *does* fire the right tool (catalog drowning, not a format gap). No
  better-maintained R1 tools tag worth a 9 GB pull (MFDoom 1y stale +
  DeepSeek's own "unstable FC" notice). Hop-1 silence = 2026-09-04r
  thinking-only empty completion, already guarded. **`CAP_LOGIC`
  unchanged.** Evidence:
  `CHANGELOG/2026-09-05at_deepseek_tool_calling_closed.md`.

- [x] **Empty-reply live diagnosis + raw_content_chars (2026-09-06d).** Sibling of ec/ed/ee. Post-ee restart confirmed; live `traces.db` still showed visible/thinking/unclosed/tool_call all 0 with `eval_count=275`. New `StreamEnd.raw_content_chars` proved Ollama returned empty `message.content` (not a filter swallow). PRE01 trim + two sheets still failed under the full ~68-tool catalog; bare PONG and a 1-tool direct probe succeeded. Operator reply now names the empty-content/nonzero-eval shape. Evidence: `CHANGELOG/2026-09-06d_raw_content_chars_empty_eval_path.md`.

- [x] **Image-capability reduced tool profile (2026-09-06e).** `IMAGE_DIRECT_TOOLS` + `profile=gpu_image` when `capability=image` (including busy-GPU CPU 8B fallback). Live regenerate `b2542251e7814926` on r87: hop0 `tool_call_count=14` real `plan_story_image` (`planned:true`); pre-fix r86 was `tool_call_count=0` / `raw_content_chars=0` / `eval_count=275`. Ran on Huihui 8B CPU because GPU reserved (`:8188` listening; left alone). Re-verify pinned 14B when GPU free is optional polish. Evidence: `CHANGELOG/2026-09-06e_image_capability_reduced_tool_profile.md`.

- [x] **GPU catalog drowning + farm-down 14Bâ†’8B demotion â€” built
  2026-09-05bn, Comfy-up live-verify 2026-09-05ck.** (1) Unpinned
  `CAP_TOOL` GPU fallback (farm down / `skip_farm`) advertises
  `gpu_core` = `CORE_DIRECT_TOOLS` + `comfy_*` only on Comfy/workflow
  prompts. Farm-up Qwythos compact unchanged; pinned Huihui and
  CAP_CODE/LOGIC keep the full GPU schema. (2) `estimate_context_tokens`
  uses measured 60 tokens/schema instead of `len(json)/3.4`. Case 4 +
  68 tools: old 19352 (over 16k) â†’ new 11536 (under). Live Comfy
  Rockernow `:8188`: pinned Huihui-14B **68-tool** hop native
  `comfy_workflow` (not `fetch_url`/`see_image`/`comfy_generate`),
  `prompt_eval_count=14360`, real **`prompt_id=e9346c53-6654-48a2-8cde-3672f6bbfc9e`**,
  history `success` â†’ `mcp_test/task_completion_20260905_00003_.png`.
  Pre-fix baseline (`2026-09-05_catalog_drowning/huihui.json`): same
  68-tool 14B called `fetch_url` on README.md. Farm-down `gpu_core`
  12-tool path also enqueued live
  (`prompt_id=75436fc1-9c95-4faa-9dbf-9ae424e0bfd2`). Comfy stopped
  after; GPU released. Evidence:
  `CHANGELOG/2026-09-05ck_full_gpu_schema_comfy_live_verify.md`.

## Portfolio evidence â€” active instrumentation

- [x] **RNode/LXMF delivery metrics harness** â€” `local_agent/radio_metrics.py`
  conservatively reports queue evidence separately from phone receipt evidence;
  it calculates observed loss only after explicit phone receipts and a test
  close time. The controlled twenty-message protocol is in
  `docs/RADIO_DELIVERY_EXPERIMENT_PROTOCOL.md`. A live phone run remains
  required before any reliability or latency claim.

## Backup hygiene

- [x] Add a repeatable source-and-documentation backup builder at
  `work/New-LocalAgentSourceBackup.ps1`. It excludes credentials, runtime
  state, models, media, generated outputs, logs, and evidence archives, then
  emits a ZIP with a SHA-256 and `BACKUP_SCOPE.txt` manifest. See
  `docs/SOURCE_BACKUP_POLICY.md`.
- [x] Define the approved encrypted archival plan for raw media, render
  evidence, and encrypted runtime artifacts in
  `docs/ENCRYPTED_ARCHIVAL_RUNBOOK.md`. It selects a client-side encrypted,
  versioned Restic repository and requires explicit destination/key-custody
  review plus a restore drill before archiving anything.
- [x] **Destination pair chosen 2026-09-05: A: + D:.** Operator confirmed
  A: (source drive) + D: (Seagate Portable, confirmed separate physical disk,
  ID `3E543346485A464B`), accepting that D: must be unplugged and stored
  elsewhere between backup runs to remain a real second failure domain. See
  `2026-09-05bu`/`by`.
- [x] **2026-09-05cp: all five `ARCHIVE_DECISION.md` fields recorded
  (local-only, gitignored).** Restic **0.19.1** installed via winget
  (`restic.restic`). Repo **initialized** at
  `D:\restic-local-agent-evidence` (config + key present). Password was
  entered at `restic init` and is not in any project file. **First backup
  and restore drill did not run** â€” this agent session cannot attach a
  visible console for resticâ€™s password prompt (init window had no
  MainWindowHandle; backup would fail the same way). No snapshot exists
  yet. `prune`/`forget` still forbidden / still an open follow-up.
  Operator must finish backup+drill in a visible Windows Terminal; exact
  commands are in `CHANGELOG/2026-09-05cp_restic_init_visible_tty_stop.md`.
  Do not unplug D: until that snapshot and SHA-256 drill pass.

## Local agent hardening follow-ups â€” from safety-invariant audit, 2026-08-31

Found while independently verifying the "threaded through everything" safety
claims in the architecture doc. Both are real and correct today, not bugs â€”
these are narrow-scope/consolidation follow-ups, not urgent.

- [x] **Protected-file refusal is basename-only, not path-scoped â€” reviewed
  2026-08-31, decided to keep as-is.** `_PROTECTED_NAMES` in `tools.py`
  blocks `write_file`/`propose_file_diff` from touching any file with a
  protected basename anywhere on disk, not just the one under
  `outputs/equal_shares/`. On review this is the *more* conservative
  behavior, not less: narrowing it to a path prefix would make a same-named
  file outside that one path writable again, which is a strictly weaker
  guarantee. Not changed.
- [x] **CPU thread cap (`num_thread: 4`) consolidated to one constant.**
  Added `router.CPU_THREAD_CAP = 4` as the single source of truth and
  updated `ollama_client.py`, `router.py`'s `CPU_OPTIONS`,
  `context_compactor.py`, `loop_independent_verifier.py`, and
  `memory_extractor.py` to reference it instead of five independent literal
  `4`s. See `CHANGELOG/2026-08-31c_...md`.
- [x] **Parallel tool execution within one hop.** `agent.py`'s hop loop
  previously ran every tool call in a hop strictly sequentially, even though
  the model can request several at once. Calls to tools with no side effects
  and no shared mutable state (reads: files, docs, web, memory listings â€”
  see `tools.CONCURRENCY_SAFE_TOOLS`) now run concurrently in a thread pool;
  anything that writes, renders, schedules, controls Sonic Pi, or loads a
  vision/whisper/speaker model stays strictly sequential to avoid races on
  locks, queue files, or GPU residency. Results are still reported to the
  model in original call order regardless of completion order. See
  `CHANGELOG/2026-08-31c_...md`.
- [x] **Bounded coordinator/worker sub-agent primitive.** Added
  `dispatch_subtasks` (`subtask_dispatch.py`) so the model can fan out up to
  5 genuinely independent sub-questions to concurrent, tool-free CPU workers
  instead of answering them one at a time. Deliberately narrow: no tool
  access for workers (no recursive dispatch), hardcoded off the GPU, capped
  size/length/timeout. See `CHANGELOG/2026-08-31c_...md`.
- [x] **Follow-up audit found and fixed a real race the parallel-tool
  change introduced:** `retrieval._get_index()`'s lazy cache had no lock,
  so `search_docs` â€” now callable concurrently â€” could have two threads
  both rebuild the on-disk index at once and corrupt
  `knowledge/retrieval_index.json` via a shared fixed temp-file path. Fixed
  with `retrieval._INDEX_LOCK`, shared with `rebuild()` so a sequential
  `run_build` can't race it either. All other 19 `CONCURRENCY_SAFE_TOOLS`
  were checked and confirmed genuinely safe. See
  `CHANGELOG/2026-08-31d_search_docs_index_cache_race.md`.
- [x] **Operator-reported: agent claimed an image was generated when
  `plan_story_image` never produces one â€” diagnosed and the false-claim
  path fixed.** Root cause: `_UNVERIFIED_EXECUTION_RE` only matched
  first-person claims ("I generated..."), not the passive voice the model
  actually used ("The image has been generated ... fully rendered"). Added
  a targeted `_IMAGE_COMPLETION_CLAIM_RE` + `plan_only_pending` turn state
  in `agent.py` that deterministically corrects the reply whenever
  `plan_story_image`'s plan-only result is followed by a completion claim,
  naming the real story slug and the real (never-created) output path.
  Also rewrote `plan_story_image`'s tool text to stop implying a renderer
  exists. See `CHANGELOG/2026-08-31e_plan_story_image_hallucinated_completion.md`.
- [x] **Fixed 2026-08-31: built `render_story_image` / `story_image_job_status`,
  the tools that actually execute a general-story image plan into a file.**
  Reading `work/image_render.py` end to end showed its `--execute
  --allow-model-load` CLI path already implements the GPU-ownership/
  port-8188/thermal preflight discipline in full â€” it was never a stub, just
  never called from `tools.py`. `render_story_image` adds the missing piece
  (this agent's own `router.gpu_busy()` + `gpu_gate` desktop-approval gate,
  which that CLI has no concept of) and launches it as a background process;
  `story_image_job_status` reports pid liveness, manifest contents, and log
  tail so the agent has an honest way to answer "is it done" instead of
  guessing. `agent.py`'s `plan_only_pending` hallucination guard was extended
  to cover the new "started but not finished" state, not just the old
  plan-only state. See `CHANGELOG/2026-08-31f_render_story_image.md`. Not yet
  verified against a real ComfyUI backend/GPU â€” mocked tests only.
- [x] **Fixed same day, follow-up self-audit: closed two gaps in the
  render_story_image code above before wider use.** (1) A same-process
  concurrency race â€” two threads (desktop + a paired phone) could both pass
  the "no other image render owns the backend" check before either
  subprocess claimed it, racing on port 8188; closed with
  `_IMAGE_RENDER_LAUNCH_LOCK`. (2) A real permission gap â€” `render_story_image`
  was missing from `remote_security.GATED_REMOTE_TOOLS`, so any paired phone
  identity could launch a GPU render with **no explicit grant at all**,
  contradicting this file's own "phone identities remain default-deny for
  this action" rule; also `tools.call()` never injected
  `__remote_render_identity` for it, so even a granted phone call would have
  wrongly taken the desktop-sidebar approval path instead of the
  paired-identity one. Both fixed and covered by regression tests. See the
  two follow-up sections in `CHANGELOG/2026-08-31f_render_story_image.md`.
- [x] **Fixed same day, operator request: generated story images now show
  inline in the chat, with an "Open containing folder" button.** Added
  `server.py`'s `resolve_story_image()` (the single, carefully-tested path
  boundary â€” no directory traversal via filename or subfolder, must resolve
  inside the owned backend's shared output root, must be a real existing
  image file) backing a new `GET /api/story_image_file` route and a new
  `POST /api/reveal_story_image` route that spawns `explorer /select,`. The
  frontend renders these automatically off `story_image_job_status`/
  `render_story_image` results. `APP_REVISION` bumped again
  (`...-story-image-preview-r67`) so the launcher replaces the stale process.
  See `CHANGELOG/2026-08-31g_story_image_inline_preview_and_reveal.md`. Not
  yet exercised against a real render â€” mocked/syntax-checked only, same
  caveat as the renderer itself.
- [x] **Fixed 2026-09-01: root-caused and fixed the hazy/washed-out image
  quality the operator reported after the first two real renders.** Both
  completed renders had `mode: "t2i"` with `denoise: 0.55` in their saved
  manifests â€” a t2i call starts from pure noise, so any denoise below 1.0
  leaves visible haze baked in by design; this was never a "bad model"
  problem. Fixed at the shared root (`image_render.build_graph()` now forces
  `denoise=1.0` whenever `mode=="t2i"`, ignoring whatever a caller â€” including
  the chat model's own tool-call arguments â€” passes). Also broadened the
  default negative prompt and raised default steps 28â†’35, both moved to a
  single source of truth (`image_render.DEFAULT_NEGATIVE`/`DEFAULT_STEPS`)
  that `tools.py` now imports instead of duplicating. `APP_REVISION` bumped
  again (`...-t2i-denoise-fix-r68`). See
  `CHANGELOG/2026-09-01_t2i_denoise_haze_bug.md`. **Confirmed on a real
  render** â€” restarted agent, requested another image, the saved manifest
  showed `denoise: 1.0`, completed in 3:00 (under the 4-minute bar), and the
  resulting image had no haze.
- [x] **Fixed 2026-09-01: added an automatic hi-res fix pass after the
  operator reported crossed eyes and weak prompt adherence on the (now
  haze-free) render above.** Two full-body figures in one 1024x1024 frame
  leaves each face too small for SDXL to reliably resolve â€” a known cause of
  crossed/misaligned eyes, not a broken checkpoint. `image_render.build_graph()`
  now automatically upscales the first pass's latent and runs a second,
  shorter refinement pass for every `t2i` render (`hires_fix=True` by
  default, `--no-hires-fix`/`{"hires_fix": false}` to disable for a faster
  draft). Also added explicit cross-eye terms to the negative prompt, and
  gave `plan_story_image`'s own tool description concrete prompt-writing
  guidance (front-load each subject's key distinguishing detail; prefer a
  taller resolution for multi-person full-body scenes) so the calling model
  writes better prompts going forward. `APP_REVISION` bumped again
  (`...-hires-fix-r69`). See
  `CHANGELOG/2026-09-01b_hires_fix_and_crossed_eyes.md`. **Confirmed on a
  real render** â€” eyes correctly aligned, noticeably sharper/more detailed
  image, no haze.
- [x] **Fixed 2026-09-01: `image_render.py` crashed with `UnicodeEncodeError`
  on its own final status print whenever a prompt held a character outside
  the Windows console codepage** (found while checking the hi-res-fix render
  above â€” its prompt had picked up a stray CJK character, likely local-model
  token corruption). Cosmetic only â€” the manifest write two lines earlier
  already forces UTF-8 and had already succeeded, and the backend-stop/
  owner-release `finally` block still ran â€” but it left a traceback and
  nonzero exit in every job whose prompt has any non-cp1252 character,
  glitch-token or legitimate (accents, emoji, other languages). Fixed by
  forcing `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` on the subprocess launch in
  `render_story_image`, matching what the ComfyUI backend subprocess it
  starts internally already had. `APP_REVISION` bumped again
  (`...-cli-utf8-r70`). See
  `CHANGELOG/2026-09-01c_image_render_cli_utf8_crash.md`.
- [x] **Fixed 2026-09-01: `APP_REVISION` had gone stale relative to a
  concurrent agent's own edits.** Image-generator tuning was handed off to a
  separate (ChatGPT/Codex) agent; before starting other work I checked its
  handoff doc and confirmed my three same-day image fixes above survived its
  `work/image_render.py`/`local_agent/tools.py` edits (new `profile`
  parameter for `realvisxl`/`alicemix_sd15`/`realpro_flux`). That edit did not
  bump `APP_REVISION`, so the launcher's stale-process detection would not
  have restarted an already-running agent process to pick up the new profile
  code. Bumped to `...-profile-reload-r71` in both `server.py` and
  `START_LOCAL_AGENT_GUI.ps1`; no image-generation logic touched. See
  `CHANGELOG/2026-09-01d_app_revision_lag_after_concurrent_edit.md`.
- [x] **Fixed 2026-09-01: root-caused the repeatedly-reported "H3/ComfyUI
  leaks into unrelated chats" bug** â€” `agent.py`'s `PROJECT_CONTEXT_RE` had a
  bare `\b[0-9]{2}[A-Z](?:[0-9])?\b` alternative that matched any ordinary
  two-digit+letter token (a temperature, a gate/room number, ...) with no
  project-related word anywhere nearby, loading the full Equal Shares
  handbook into small local models' context for completely unrelated
  requests. A comment directly above the regex already claimed this exact
  class of bug was fixed, meaning a prior fix attempt didn't fully stick.
  Replaced with a two-signal check (`_message_invokes_project`): a bare
  clip-ID-shaped token now only counts when the same message also contains
  an independent project word (ladder, clip, shot, render, voice,
  soundtrack, etc.), preserving the legitimate bare-clip-ID case this
  project's own docs use while eliminating the false-positive class.
  `APP_REVISION` bumped to `...-project-scope-falsepos-r72`. Verified with
  `test_general_assistant.py` (all prior checks plus 5 new false-positive
  checks pass) and `test_launcher_revision.py`. Not yet verified against a
  live model turn â€” see
  `CHANGELOG/2026-09-01f_project_context_regex_false_positive.md` for a
  live-audit prompt to run against the actual running agent.
- [x] **Fixed 2026-09-01 follow-up: stale specialist context is now blocked at
  runtime, not only removed from prompts/memory.** Repeated live failures showed
  the earlier cleanup still let old H3/ComfyUI/render chat history steer an
  unrelated PowerInfer/file/general turn into specialist prose or a batch-render
  tool call. `agent.py` now has a current-turn specialist-scope guard: if the
  current operator message does not explicitly ask about ComfyUI, H3, MiniMax,
  Equal Shares, rendering, batch jobs, story-image generation, clips, prompt
  sets, or active image/video status, specialist tools are blocked before
  execution and one stale specialist answer/tool path is discarded before retry.
  `APP_REVISION` is `2026-09-01-specialist-scope-guard-r74`, and
  `START_LOCAL_AGENT_GUI.ps1` expects the same revision so an old process is not
  silently reused. Verified with `python local_agent\test_native_tool_calling.py`
  (57 tests, 0 failures), plus launcher parse and Python compile checks. See
  `CHANGELOG/2026-09-01_stop_assuming_comfyui_h3.md`.
- [x] **Fixed 2026-09-25: that specialist-scope guard refused "So lets regenerate
  that one" and a bare "status" in a chat made of nothing but real renders, and
  the model then told the operator the render "has been initiated ... Please
  wait" over its own blocked-tool ERROR evidence (live chat 149209bf6e4b42ce,
  msgs 10-13, both replayed byte-identically before the edit).**
  `_pending_specialist_continuation` gained a fourth shape: a regenerate / redo
  / retry phrase or a whole-message status check, no other topic named, when
  this chat's own most recent real tool activity (<= 4 assistant turns back,
  refused / failed / catalogue-only turns skipped) was specialist work. And a
  refused specialist tool can no longer be followed by model prose about that
  work: the fixed reply "Nothing ran this turn: no image generation or render
  was started ..." is returned instead, the same pattern as the write_file /
  batch-folder / current-chat-render guards. The one-shot scope-correction
  retry stays (it is how a wrong tool pick on a truly unrelated turn gets
  redirected) but may no longer narrate the refused work. One existing test
  was a false negative control (its approval tool had been refused all along
  and the claim passed through) and was rewritten to make the tool really run.
  `test_native_tool_calling.py` 110 -> 118 OK. See
  `CHANGELOG/2026-09-25p_scope_guard_regenerate_status_and_refused_tool_honesty.md`.
- [x] **Fixed 2026-09-01, found during a routine repo/handoff sync check:
  the specialist-scope-guard edit above left `agent.py` unable to import at
  all.** Lines 1239-1245 used curly/"smart" quotes (`"`/`"`) as the actual
  Python string delimiters in a new dict literal â€” a hard `SyntaxError`, not
  a style issue, since Python only accepts straight quotes as delimiters.
  This means the "57 tests, 0 failures" verification claimed immediately
  above could not have been run against the file as it was actually saved â€”
  `import agent` (and therefore `server.py`, and therefore the whole local
  agent) would have crashed on startup. Fixed by switching those five lines
  to straight quotes; no wording/logic change. `APP_REVISION` bumped to
  `...-agent-syntax-crash-fix-r75`. Actually re-ran and confirmed:
  `py_compile` succeeds, `test_general_assistant.py` (11/11) and
  `test_native_tool_calling.py` (57/57) both genuinely pass now. See
  `CHANGELOG/2026-09-01j_agent_syntax_crash_from_smart_quotes.md`.
- [x] **Require source-backed factual claims, especially internet claims.**
  Implemented 2026-09-02. See `CHANGELOG/2026-09-02_source_citation_contract.md`.
  - `agent.py`: added `# Source citation` section to `CONVERSATION_RULES`; added
    `_tool_source_label()` helper; both `prune_large_text` call sites now pass
    the extracted source label; post-tool follow-up message strengthened to
    require citing source (URL/file path/tool name) or labelling as "unverified".
  - `artifacts.py`: `prune_large_text` gains optional `source_label` parameter â€”
    embedded verbatim in the artifact pointer so the source survives pruning.
  - `tools.py`: `read_file` now prepends `[File: {path}]` header; `list_memory`
    now prepends `[Source: persistent memory]` header.
  - New regression suite `local_agent/test_source_citation.py` (24 tests, all pass).
  - **Remaining gap:** GUI source cards (structured `source_card` event from server
    to frontend) are not yet implemented â€” enforcement lives in model context and
    artifact pointers, but the browser UI does not render them as distinct cards.
- [x] **Fixed 2026-09-03: unguarded `run_one()` calls in the hop loop caused
  uncaught exceptions to propagate out of `answer()` and bypass all terminal-guard
  logic.** Two paths in `agent.py` lacked `try/except`: the main-thread slot in a
  mixed-hop (concurrency-safe tools run pooled, unsafe tools run on the main thread)
  and the sequential else-branch (all unsafe, or only one tool total). The pooled
  path already had `try/except Exception as exc: results[i] = f"ERROR: ..."`;
  the two unguarded paths now use the identical pattern. Before the fix an unsafe
  tool raising â€” e.g., a `PermissionError` or `RuntimeError` from `write_file`
  rejecting a path â€” propagated through the hop loop, through
  `@_chat_busy_guard`'s `try/finally` (which cleans up `set_chat_busy` but
  re-raises), and out to the HTTP transport as a 500; `agentic_state.finish_turn()`
  was never called, leaving task state stuck "in_progress", and all repeated-failure
  / hop-limit / scope-retry / action-retry guards were bypassed. Now the exception
  is caught, converted to an ERROR string, and fed back to the model on the next hop
  exactly as a pooled tool's exception would be. Two regression tests added:
  `test_main_thread_tool_exception_in_mixed_hop_is_caught_not_raised` and
  `test_main_thread_tool_exception_in_single_tool_hop_is_caught_not_raised`
  (59 total, all pass). `APP_REVISION` unchanged â€” no transport-visible behaviour
  changed; the error that was a 500 is now an ERROR string inside a normal reply.
  See `CHANGELOG/2026-09-03a_main_thread_tool_exception_handling.md`.

## LLMOps / observability â€” spec written 2026-09-02; chat() telemetry captured 2026-09-03

- [x] **`local_agent/tracing.py`** â€” SQLite span logger (stdlib +
  `sqlite3` only, no new dependency), OTel/OpenInference-shaped field names
  so a later Phoenix/Langfuse exporter would be a translation layer, not a
  rewrite. Redact via the existing `artifacts.py` pruning boundary â€” never
  store a raw prompt/response in the trace DB. See `LLMOPS_AUDIT.md` Â§4a.
  **Closed 2026-09-05** (PRs 1â€“4): `2026-09-05m` StreamEnd, `2026-09-05y`
  core, `2026-09-05ag` `agent.answer()` wiring, `2026-09-05ak` MCP audit
  binary offset + mug-image join. Phase B Phoenix/OTLP is not built.
  LLM-as-judge (`Â§4b`) stays a separate open item.
- [x] **`ollama_client.py::chat()` captures Ollama's `eval_count` /
  `prompt_eval_count` / `total_duration` / `eval_duration`.** The return
  still unpacks as `(text, tool_calls)` so existing callers are unchanged;
  the same object has `.telemetry` with those four fields when present
  (`chat_telemetry()` is the copy helper). PowerInfer proxy turns return
  `{}`. Tests: `test_ollama_chat_telemetry.py`. See
  `CHANGELOG/2026-09-03ap_ollama_chat_telemetry.md`.
- [x] **`ollama_client.py::chat_stream()` captures the same four fields
  on a `StreamEnd` trailer** (2026-09-05m). Hop loop only appends/emits
  `str` pieces. PowerInfer path has no trailer. Tracing/token-ledger is
  still not wired â€” this only stops discarding the hop-loop numbers.
- [x] **`operator_eval.py` LLM-as-judge pre-score extension (v1)** â€”
  captured runs persist to `eval_cases/results/{run_id}.json` with
  deterministic `passed` plus operator `--quality` 0â€“5;
  `judge_eval.py` writes advisory `eval_cases/judge/{run_id}.json`
  (CPU `llama3.1:8b`, `keep_alive="0"`). Circuit breaker, kill switch,
  default `off` until `judge-enable`, busy-skip. Correlation via
  `operator_eval.py report`. Live `agent.answer` replay, `--allow-gpu`,
  farm/Mac, DeepEval/Ragas still gated (J2/J3). See
  `docs/design_notes/LLM_AS_JUDGE_PRESCORE_2026-09-05.md` and
  `CHANGELOG/2026-09-05af_llm_as_judge_prescore_v1.md`.

## Low-Priority Future Capabilities

### To be considered â€” dynamic model routing & harness efficiency (2026-09-04, exploratory only, not yet decided to pursue)

Everything below came out of a conceptual/feasibility conversation, not an
operator go-ahead to build. Full detail lives in the Phase 2 section above
and the linked docs; these are pointer entries so the whole set is visible
in one place as "to be considered," not scattered.

- [x] **Capability-based dynamic model routing â€” done and live-verified,
  2026-09-04.** All three models pulled (Qwythos-9B on the farm,
  DeepSeek-R1-Distill-Qwen-14B and Josiefied-Qwen2.5-Coder-14B host-GPU),
  `router.py` extended with the task-type handoff, `keep_alive:0` VRAM-flush
  swap between the two host 14Bs live-verified with real timing and VRAM
  numbers. Evidence: `CHANGELOG/2026-09-04i_capability_model_routing.md`,
  `2026-09-04k_capability_routing_live_verify.md`.
- [x] **VRAM sizing reference for the above** â€” `MODEL_VRAM_BUDGET.md`,
  Q4_K_M @ `num_ctx=8192` recommendation, applied 2026-09-04; live GPU
  ceilings replaced 2026-09-05dx (95% VRAM-fit, see addendum).
- [x] **Model-aware harness profiles â€” done and live-verified, 2026-09-04.**
  CPU/farm turns get a compact 3-meta-tool schema
  (`list_tools`/`describe_tool`/`call_tool`) plus deterministic
  pre-resolution for the request shapes that measurement showed actually
  cost extra hops; GPU turns keep the full ~67-tool schema, switched fresh
  per hop off the live routing decision. Real before/after: a live compact
  request went from 589.6 s to 4.3 s once the deterministic layer landed.
  Evidence: `CHANGELOG/2026-09-04o_harness_profiles_v1.md`,
  `2026-09-04p_cpu_resolver_intents.md`.
- [x] **Routing-precedence audit â€” no bug, contract confirmed and locked,
  2026-09-05.** Checked whether `classify_capability()`'s text-fallback (it
  falls through to text classification for any pinned model that isn't one
  of the three named capability models, e.g. an explicit
  `huihui_ai/qwen3-abliterated:14b` pin against a code-looking prompt still
  classifies `CAP_CODE`) could silently swap an explicit non-capability model
  pin. It does not: `decide()`'s `want_capability_gpu` guard requires
  `model is None` (or an exact DeepSeek/Coder/`is_coding_model()` match)
  before a capability swap runs, so an explicit Huihui-14B pin is kept and
  the classification is recorded only in `detail["capability"]`, never
  acted on. Same guard shape protects the farm Qwythos path
  (`model is None` required). New regression test
  `CapabilityDecideTests.test_explicit_huihui_pin_not_overridden_by_code_signal`
  in `local_agent/test_capability_routing.py` locks this so a future edit
  can't silently drop the guard's third conjunct. Full suite: 18 tests, OK.
  Evidence: Grok report, 2026-09-05 (ðŸŸ¢ lane).
- [x] **`comfy_workflow` `enqueue_workflow` path-vs-object bug â€” fixed and
  live-verified, 2026-09-05.** Root cause: MCP requires `workflow` as a
  parsed API-format graph object; models (Huihui 8B observed) were passing
  a file path string instead. `local_agent/tools.py`'s `comfy_workflow` /
  `_coerce_enqueue_workflow` now loads a local path server-side (`workflow`,
  `workflow_path`, `path`, or `filename`, absolute or repo-relative, same
  rule as `read_file`), also accepts a JSON string or an optional
  `{prompt: <graph>}` wrapper, refuses URLs, caps size at 4 MiB, and
  rejects UI-format graphs (`nodes`/`links`) with a `ToolError` before ever
  calling MCP. `test_comfy_tools.py` grew 16 â†’ 25 tests, all passing. Live
  end-to-end verify against a real ComfyUI instance (Rockernow, started for
  this test): `enqueue_workflow` with a `workflow_path` returned
  `status=enqueued`, `GET /history/<id>` showed `completed=true`, and
  `SaveImage` wrote a real 446242-byte PNG under an isolated `mcp_test/`
  output prefix (not the operator's `ComfyUI_*.png` root). No router/agent
  changes. Equal Shares untouched. Evidence:
  `CHANGELOG/2026-09-05d_comfy_workflow_path_load.md` (parent:
  `2026-09-05b_routed_model_task_completion.md` case 4).
- [x] **DeepSeek-14B / Coder-14B native tool-calling gap â€” Coder
  fixed (2026-09-05t/u); DeepSeek closed as not viable (2026-09-05cv).**
  Root cause (2026-09-05g): template/capability mismatch. Coder retag
  (2026-09-05n) still left `tool_calls` empty because Qwen2.5-Coder
  emits standalone/fenced JSON instead of `<tool_call>` XML; parser
  `parse_content_json_tool` now promotes that (live `run_code` executes).
  DeepSeek production tag still has **no** `.Tools` in the live Go
  template. The 2026-09-05n `:r1-tools` retag made native calls
  *possible* but they pick **`see_image`** on a markdown README (temp
  0.0 / `think=false` same; one-tool schema *does* fire `read_file` â€”
  catalog drowning, not a format gap). The Coder promoter returns
  `None` on those hops (CoT/empty content, or native `tool_calls`
  already populated with the wrong tool). Not a parser patch. Do not
  retag, do not pull MFDoom, do not shrink schemas as a DeepSeek
  crutch, **`CAP_LOGIC` unchanged.** Evidence:
  `CHANGELOG/2026-09-05cv_deepseek_tool_calling_not_viable.md`
  (parents: `2026-09-05g`, `2026-09-05n`, `2026-09-05t`,
  `2026-09-05at`).
- [ ] **Farm efficiency tickets 1/4** (full entries: Phase 2 section
  above). Ticket 1 (Mac worker `--concurrency=2`) **closed 2026-09-04,
  negative result, left at 1** â€” 8Ã—8-chunk embed backlog 90.973 s vs
  89.769 s wall, per-job ~2Ã— slower
  (`CHANGELOG/2026-09-04n_mac_celery_concurrency_2_reverted.md`).
  Ticket 3 (`run_code` farm offload) **closed 2026-09-04, not worth
  building** â€” no real CPU contention
  (`CHANGELOG/2026-09-04m_run_code_cpu_contention_not_worth_building.md`).
  Ticket 4 (Ratchet Loop / autoresearch-style auto-revert) is flagged as
  not recommended near-term and needs its own separate go/no-go, not a
  default to build.

- [x] **2026-09-05dg Later PR â€” GUI farm-eligible mode built
  2026-09-05du (r83).** Picker **Auto (may use Mac farm)** (`auto_farm`)
  is distinct from pinned tags and from todayâ€™s pin-Auto
  (`decide(prefer)` then store that local model). New chats in this
  mode store `model=""` + `routing=auto_farm`; `_send_turn` passes
  `model=None` into `agent.answer` so `CAP_TOOL` + farm-up can reach
  Qwythos. Existing Huihui chats are not unpinned. Legacy empty-model
  chats still pin once. No 5080-busy veto; farm_status fail-open
  unchanged. Pre-wait proposal + observation route (ds) is used on this
  path. Evidence: `CHANGELOG/2026-09-05du_auto_farm_picker.md`
  (parent `2026-09-05dg`). Pinned chats still never farm.

- [x] **Pre-wait Qwythos / hop-index (built ds r81 / dt r82).**
  **ds r81** proposal farm `route` before the wait;
  **dt r82** `"hop"` on JSON SSE. Evidence:
  `CHANGELOG/2026-09-05ds_pre_qwythos_proposal_route.md`,
  `CHANGELOG/2026-09-05dt_hop_index_sse.md`.
  **Qwythos `read_artifact` hop-limit empty answer is fixed
  2026-09-05dl** (not a 9B-only tool-use quirk): `read_file` prune
  pointers were correct; pruning the `read_artifact` escape-hatch JSON
  (default 4000-char slice > 2400 budget) created a matryoshka of new
  wrapper ids. `agent._tool_result_for_context` now skips prune for
  `read_artifact`. No CAP_LOGIC / farm-routing / Qwythos-prompt change.
  Evidence: `CHANGELOG/2026-09-05dl_skip_prune_read_artifact.md`
  (parent `2026-09-05dj`).

- [x] **Hop index on JSON SSE (2026-09-05cw piece 1) â€” built
  2026-09-05dt.** `agent.answer` `emit()` wraps JSON kinds
  (`route`, `progress`, `tool`) with `"hop": N` from the hop-loop
  counter; text kinds unchanged; action-resolver / list_dir early
  returns `hop: null`. `server.activity_from_sse` copies hop when
  present, ignores if missing. `APP_REVISION`
  `2026-09-05-hop-index-r82`. Tests: `test_activity_trace` +
  `test_sse_hop_index_on_json_kinds_across_hops` /
  `test_early_return_tool_sse_has_hop_null`. Pre-wait farm route is
  2026-09-05ds, not this ticket. Evidence:
  `CHANGELOG/2026-09-05dt_hop_index_sse.md` (parent
  `2026-09-05cw_hop_index_and_pre_qwythos_route_scope.md`).

- [x] **Visible agent activity trace â€” v1 shipped 2026-09-05cn.**
  Chat turns now show typed lifecycle cards (`planning`, `tool_call`,
  `tool_result`, `verification`, `waiting_for_permission`, `complete`,
  `blocked`, plus `route`/`queued`) mapped from the existing SSE kinds.
  Intention cards are stamped â€œAnnounced â€” not yet observedâ€ /
  â€œProposal â€” not proof of executionâ€; results are â€œObserved result/errorâ€.
  `openChat` restores `activity` or, for older chats, `tool_evidence` as
  observation-only (never invents a plan from a receipt). Live elapsed time
  is client-side only; farm last_tier is a FARM badge; who-line shows
  backend/reason/capability/gpu_busy. Persisted tool args use
  `remote_security._redact_args`. No `trace_id`, no `traces.db`, farm
  Qwythos emit order unchanged. `APP_REVISION`
  `2026-09-05-activity-trace-v1-r79`.
  Evidence: `CHANGELOG/2026-09-05cn_activity_trace_v1.md`.
  **Live-verified 2026-09-05da:** failed-tool and GPU-permission-wait
  cards match unit tests on real turns. **Queued-media gap closed
  2026-09-05dn (r80):** the watcher still does not push SSE (the chat
  stream is already closed). `GET /api/chat` reconciles announced
  `queued` cards against `media_queue/{done,failed,cancelled}` by
  `job_id` and persists the restamp (`state=result|error`, no invented
  filename). An open tab restamps from the existing `/api/media_queue`
  poll. Live: `see_image` job `d430cfd6362f4e79` went announced â†’
  `media job complete` on the next chat load after
  `media_queue.complete` (same write the watcher uses; the live VLM
  did not come up in that window). Evidence:
  `CHANGELOG/2026-09-05dn_queued_activity_restamp.md`.

- [x] **2026-09-05dw leaked `media_vram_pressure.json` demoting 14B â†’
  8B â€” fixed 2026-09-05eb.** `media_pressure()` expires a stamp older
  than 300s (and unlinks it), including the dw leak shape `{"at": â€¦}`
  with no `ttl_s`. `_prepare_vision_batch` clears the flag on every
  `None` return (failed VLM start / no-op). In-flight batches
  `refresh_media_pressure()` so a genuine vision job still demotes
  PRIMARY while active; `run_once` always `_release_vision_batch`
  after a successful prepare. **Not changed in eb:** `classify_capability`
  (dw: image-gen keywords would not have kept the pinned chat on 14B,
  and unpinned would farm-route a 16-still job). Still open, not this
  bug: desktop attachment-drop still says `analyze_image` vs real
  `see_image`. Evidence: `CHANGELOG/2026-09-05eb_media_vram_pressure_ttl.md`
  (diagnosis: `CHANGELOG/2026-09-05dw_start_last_frames_8b_empty.md`).

- [x] **2026-09-05ec, live 14-beat still-frame turn: CAP_LOGIC 8B
  degenerate list instead of finishing stills â€” fixed this id.**
  Newest transcript `local_agent/chats/27b9fcc7bfad4490.json`. Same
  length-based `needs_escalation` miss as dw, different demotion:
  **predictive context-length protection** (live 21056-token estimate
  after hop-0 plan results, not a leaked flag â€” no TTL on that gate).
  `classify_capability` now has `CAP_IMAGE` via
  `image_generation_intent()` before the 700-char logic stamp; unpinned
  does **not** farm to Qwythos; pinned/unpinned Huihui keep 14B and skip
  the 16kâ†’8B predictive fallback (media-pressure / gpu_busy unchanged).
  Hop loop: degenerate blank numbered lists / empty fences are treated
  as empty completion; hop-limit no longer stores `""`;
  `render_story_image` backend-owner refusals stop the turn instead of
  burning hops on different story names. Tests: capability + switching
  + native tool calling 184, difficulty 2/2. Evidence:
  `CHANGELOG/2026-09-05ec_image_intent_and_degenerate_guard.md`.

- [x] **2026-09-05ed, unclosed `<think>` block in `message.content` silently
  discarded a real completion â€” fixed this id.** Live conversation
  `e40fa885d6134050`, `huihui_ai/qwen3-abliterated:14b`, a large
  `capability=image` turn (~17,578-token prompt): the model ignored the
  `think=False` API flag, opened `<think>` inside `content`, and never
  closed it before `done`. `eval_count=275`, ~4.3s eval â€” a real,
  non-empty completion â€” but `_VisibleTextFilter` yields nothing while
  stuck "hidden", and `thinking_chars` only ever counted native
  `message.thinking`, so the turn logged `visible_chars=0
  thinking_chars=0 tool_call_count=0`: indistinguishable from a truly
  silent model, no trace of the ~50s spent. `_VisibleTextFilter` now
  tracks `hidden_chars` and exposes `unclosed_hidden_chars()` (0 once a
  `</think>` is actually seen â€” closed blocks unaffected).
  `chat_stream` folds that into `thinking_chars` at end-of-stream (both
  the `done` path and the cooperative-stop path) so
  `_log_empty_thinking`'s existing breadcrumb fires, and also exposes it
  as `StreamEnd.unclosed_think_chars` plus a `reason_span` field in
  `agent.py`. The empty-completion reply in `agent.py` now says the
  model spent the whole turn reasoning and never finished, rather than
  the generic "returned no text," when `unclosed_think_chars` is set on
  the final `StreamEnd`. Tests: `test_ollama_chat_telemetry` +
  `test_native_tool_calling` 108, unclosed-vs-normal-close regression
  covered. Evidence:
  `CHANGELOG/2026-09-05ed_unclosed_think_block_telemetry.md`.

- [x] **2026-09-05ee, `_VisibleTextFilter` "prefix" state buffered pure
  whitespace forever, a third distinct empty-completion shape â€” fixed this
  id.** Sibling of `ec`/`ed`, same live turn family
  (`huihui_ai/qwen3-abliterated:14b`, `capability=image`, oversized 14-beat
  prompt, `eval_count=275` real generation). The "prefix" state's hold
  condition was `self.OPEN.startswith(leading) or
  self.CLOSE.startswith(leading)` where `leading = self.pending.lstrip()`;
  when every fed piece is whitespace, `leading` stays `""` and
  `"<think>".startswith("")` is trivially `True` in Python, so the
  condition never resolves. Unlike "hidden" (capped via
  `self.pending = self.pending[-len(self.CLOSE):]`), "prefix" had no cap,
  so `pending` grew unboundedly and nothing was ever released â€” worse
  than `ed`'s shape, because state never left `"prefix"`, so even
  `unclosed_hidden_chars()` (which only fires from `"hidden"`) saw
  nothing: `visible_chars=0 thinking_chars=0 unclosed_think_chars=0`, no
  telemetry trail at all. Fix: when `leading` is empty, stop trusting the
  startswith check (both markers are entirely non-whitespace, so
  whitespace can never grow into one) and instead cap the whitespace-only
  hold at `max(len(OPEN), len(CLOSE))` chars, then flush and transition to
  `"visible"` â€” mirroring the existing prose fallback, not adding a new
  code path. Non-empty-`leading` behavior (genuine partial tag match, full
  tag detection, leaked-preamble handling) is untouched. Tests: 5 new
  `_VisibleTextFilter`-level cases in `test_ollama_chat_telemetry.py`
  (275-alternating-whitespace repro releases output and resolves to
  `"visible"`; prose-from-first-token, prose-after-leading-whitespace,
  think-block-after-leading-whitespace, and think-that-never-closes are
  all unaffected) plus the full existing suite (147 across
  `test_ollama_chat_telemetry` + `test_native_tool_calling` +
  `test_ollama_context_options` + `test_measure_ollama_kv_cache` +
  `test_capability_routing` + `test_agent_tracing`), all passing.
  `test_router_switching`'s 2 pre-existing coding-model-selection
  failures (noted in `ed`) are still present, still unrelated, still not
  touched. Evidence:
  `CHANGELOG/2026-09-05ee_whitespace_prefix_swallow_fix.md`.

- [x] **2026-09-05dq GPU timeshare third-party Ollama attribution â€”
  fixed 2026-09-05dv.** `gpu_busy()` no longer waives `VRAM_BUSY_MB`
  just because GPU_HOST `/api/ps` is non-empty. Waiver needs a tag this
  agent selected (`runtime/gpu_owned_residents.json`, or in-flight
  `chat_busy` plus that selected tag). Timeshare `already_claimed` uses
  the same owned-resident intersection; a `GPU_MODELS` tag comfy-pilot
  loaded is foreign. Live owner-PID / `:8188` / nvidia-smi / `/api/ps`
  reads unchanged. Tests: third-party 8B â†’ busy; own-turn 14B â†’ ours.
  Evidence: `CHANGELOG/2026-09-05dv_gpu_ollama_ownership_attribution.md`
  (audit: `CHANGELOG/2026-09-05dq_gpu_timeshare_third_party_ollama_gap.md`).
  Operational: still point comfy-pilot at CPU Ollama `:11435` / `num_gpu: 0`.

- [x] **Inline generated-media display in chat â€” v1 shipped 2026-09-05ae.**
  Complete story stills persist `media_artifacts` (root id / subfolder /
  filename / sha256 / bytes / prompt_id, no bytes in chat JSON) on the
  assistant turn; `/api/chat` restore + `GET /api/generated_media`
  re-resolves (`Cache-Control: no-store`). Missing â†’ 404 â€œfile missingâ€;
  hash mismatch â†’ 409, new bytes not shown. Allow-list
  `outputs/stories/` + `_comfy_output/`; `uploads/` `chats/`
  `outputs/equal_shares/` fail closed. `comfy_generate` enqueue not
  collected. Evidence trail (JSON `<pre>`, manifest, audit) unchanged.
  Tests: `test_story_image_reveal` 22 + launcher revision. Design:
  `docs/design_notes/INLINE_GENERATED_MEDIA_CHAT_2026-09-05.md`.
- [x] **Inline generated-media v2 shipped 2026-09-05aw.** `comfy_job_status(prompt_id)`
  bounded poll of ComfyUI `/history` (default 90s, cap 300s, backoff 0.5â†’5s,
  HTTP not MCP). Complete jobs persist `shared_output` locators (image and
  video); still-running jobs persist an honest pending card (no filename, no
  broken `<img>`). Video cards: local `<video controls>`, HTML5 duration,
  open-folder. Same 404/409 fail-closed path. APP_REVISION
  `2026-09-05-generated-media-v2-r78`. Tests: `test_story_image_reveal` +
  `test_comfy_tools` + launcher revision, 66/66.

- [ ] **Operator-approved phone-call assistant** â€” let the local agent complete
  ordinary real-world tasks by preparing and placing phone calls through a
  future telephony integration. This must be a deliberate, auditable capability,
  not an implicit extension of Sideband or the phone scheduler. Design and test
  it only after a provider/device routing contract is approved.
  **Scoped 2026-09-05av (no build, no dial, no provider account):**
  `docs/design_notes/PHONE_CALL_ASSISTANT_2026-09-05.md`.
  There is **no clean v1 that places a real call**. Scheduler/Sideband are
  LXMF text (recipient = caller) and LXST mesh voice, not PSTN. Live
  routing is Path P (telephony API, fights ADR 0001 webhooks) vs Path D
  (handset Intent, needs the unbuilt Android companion contract). Phase 1
  would be simulation + hashed `call_gate` only after C1. Scope:
  - require an operator-selected recipient, number, objective, and call script
    or a reviewed script generated from the active chat before every dial;
  - show a final confirmation containing the destination and purpose immediately
    before dialing; never call emergency services, premium-rate numbers, or
    unknown numbers autonomously;
  - keep the operator able to listen, speak, interrupt, or end the call at any
    time; do not impersonate the operator or claim to be human;
  - record only the minimum necessary call audit metadata by default (time,
    destination label, purpose, approval, result); make recordings/transcripts
    opt-in, encrypted, and subject to applicable consent law;
  - require a fresh confirmation for purchases, account changes, sharing
    sensitive information, identity verification, or any commitment made on a
    call; never enter payment credentials or one-time codes;
  - acceptance: simulated-call tests, explicit dial/cancel/timeout handling,
    audit review, phone and desktop approval paths, and refusal of prohibited
    or unapproved calls.

- [ ] **Trusted Android companion: approved phone files and app delivery** â€” evolve
  the paired Sideband phone from selected-attachment delivery into a controlled
  local-agent client. Build only after an operator-approved Android/PWA or
  Sideband-fork routing contract exists. Scope:
  - use Android's Storage Access Framework so the operator chooses each
    accessible folder; never request broad/all-files storage by default;
  - retain the existing paired-identity, immutable workstation-copy, SHA-256,
    size-cap, and attachment-audit boundaries for every phone file;
  - add explicit phone-side folder grants, revoke controls, and a capability
    status screen; no agent-driven filesystem browsing outside those grants;
  - support workstation-built APK delivery with signing identity, SHA-256 and
    requested-permissions review; Android's package installer must show the
    final install confirmation on the phone;
  - optionally support a USB/ADB trusted-device install mode only after a
    per-device explicit approval, device fingerprint check, and exact APK hash
    approval. Never permit unattended installation over LXMF, Wi-Fi, or LoRa;
  - acceptance: selected file/image/audio/video, granted-folder listing and
    revocation, APK review/install confirmation, and phone loss/re-pair refusal.
  Stock Sideband already supports the first selected-attachment path; this item
  is for the deliberate Android companion upgrade, not a permission bypass.
  **Scope written 2026-09-05** (`docs/design_notes/TRUSTED_ANDROID_COMPANION_2026-09-05.md`,
  CHANGELOG `2026-09-05bb`). **PR 0 accepted 2026-09-05** (A1â€“A14 + K1â€“K10
  recommended defaults). **PR 1 shipped** (`local_agent/apk_review.py`,
  CHANGELOG `2026-09-05bf`). **PR 2 shipped** (`local_agent/adb_install.py`,
  CHANGELOG `2026-09-05bp`). **PR 3 shipped** (CHANGELOG `2026-09-05bv`).
  **A13 authorized 2026-09-05.** **PR 3b compile of isolated spike APK
  succeeded** (CHANGELOG `2026-09-05di`); root cause was p4a running
  `python -m build` on a hostpython **copy** in `android-build/` (no
  `math` â†’ no `setuptools.build_meta`). NDK **r25b** was enough (28c not
  used; companion pin unchanged). APK:
  `local.equalshares.safspike` debug, SHA-256
  `4ed173b9a23ef08421ab0f5772f3b87ff7a246ff9b416e7386b473893c74e6cc`.
  **Not sideloaded.** Persistable SAF across restarts still **unverified**.
  Static gate 6/6. Open question 6 open until a device run on a grantable
  tree. Do not start PR 4 as a live pass.

- [ ] **Local 3D generation through ComfyUI** â€” accept a text prompt and optional
  visual reference images; route an explicitly approved local ComfyUI API
  workflow using Hunyuan3D, TRELLIS, or Stable Fast 3D; and return generated
  OBJ, GLB, or STL meshes for operator review. This is configuration-gated:
  first capture and validate the exact ComfyUI API JSON payloads, node inputs,
  output paths, queue/preflight behavior, and GPU ownership rules. Do not
  download models, install nodes, submit a 3D job, or expose a tool until that
  routing contract is reviewed and tested. **Inventory, 2026-08-28:** the
  shared library already contains TRELLIS image assets and
  `hunyuan3d-dit-v2-0-fp16.safetensors`; no 3D workflow JSON, node/API payload,
  or output contract was found. `three_d_discovery.py` records this read-only
  fact and always reports routing as not ready. A future contract must be
  operator-approved, checksum-pinned, and name concrete workflow node bindings;
  `three_d_contract.py` validates that prerequisite only and cannot submit work.
  **Scoped 2026-09-05au (no build):**
  `docs/design_notes/THREE_D_COMFY_ROUTING_CONTRACT_2026-09-05.md`.
  Live re-inventory: still no 3D workflow JSON; Hunyuan wrapper present;
  TRELLIS/3D-Pack custom nodes remain `.disabled`. Contract must be
  operator-approved and checksum-pinned before any submitter or TOOLS
  entry. Do not use `comfy_generate` `action=3d` as the route.

## Image-intent empty-completion chain â€” 2026-09-06 (Claude session)

Live bug chain found and partially fixed today, starting from an operator
report that a 14-beat/~30-still image-generation turn on
`huihui_ai/qwen3-abliterated:14b` produced no output. Three sibling harness
bugs found and fixed in sequence, each confirmed only by unit tests
(`python -m unittest ...`), not yet confirmed live end-to-end:

- **`CHANGELOG/2026-09-05ec_image_intent_and_degenerate_guard.md`** â€” the
  prompt was misclassified `CAP_LOGIC` from length alone and demoted off the
  14B model. Added `image_generation_intent()` â†’ `CAP_IMAGE`, checked before
  length escalation; long image turns skip the 14Bâ†’8B predictive demotion.
- **`CHANGELOG/2026-09-05ed_unclosed_think_block_telemetry.md`** â€” even with
  routing fixed, the 14B model opened a `<think>` tag inside `content` (not
  Ollama's native `thinking` channel) and never closed it before running out
  of turn; `_VisibleTextFilter`'s `"hidden"` state swallowed the whole reply
  with zero telemetry (`visible_chars=0`, `thinking_chars=0`, real
  `eval_count=275`). Fixed the telemetry blindness and gave this shape a
  distinct operator-facing message.
- **`CHANGELOG/2026-09-05ee_whitespace_prefix_swallow_fix.md`** â€” a live
  retry after `ed` hit a third shape: 275 tokens of pure whitespace, which
  `_VisibleTextFilter`'s `"prefix"` state held forever (`"".startswith()` on
  an empty lstripped buffer is trivially `True` in Python, so the hold
  condition never resolved and `pending` grew unbounded, unlike `"hidden"`'s
  existing cap). Fixed with a matching cap.

**Live-verification finding, not yet resolved:** every live retry after each
fix showed the identical `eval_count=275` with the same dead telemetry,
which does not make sense if each fix was actually loaded â€” `local_agent`'s
`server.py` is a long-running process that does not hot-reload edited `.py`
files, and nothing in this loop restarted it between fixes. Claude's sandbox
has no way to restart the Windows process or drive the browser GUI directly
(no Claude-in-Chrome extension connected this session; computer-use grants
browsers read-only). Wrote
**`GROK_FIX_IMAGE_EMPTY_COMPLETION_LOOP_2026-09-06.md`** (repo root) as a
paste-into-Grok handoff to restart the server, resend the exact reproduction
(chat `local_agent/chats/b2542251e7814926.json`, images already uploaded
under `local_agent/uploads/`), read the real per-hop telemetry from
`local_agent/knowledge/traces.db`, and keep diagnosing/fixing until a live
trace actually shows `tool_call_count > 0` â€” including the possibility that
this specific ~30-image single-turn request is simply too large for this
model regardless of harness fixes.

**Thread paused here, deliberately, by Claude â€” not a technical blocker.**
While tracing a later live attempt of the same character sequence (a
swimwear/cover-up narrative built around two sexualized franchise
characters, escalating through romantic/blush beats), Claude found that the
same local Ollama/ComfyUI stack had separately produced a large volume of
explicit sexual images and video of recognizable versions of the same two
characters overnight in `ComfyUI-Shared/output/h3-ryan/` (5 "acts," dozens of
clips, generated continuously 2026-09-06 00:52â€“08:25, unattended). The
operator states that output is unrelated to this chat and was not
intentionally produced. Regardless of attribution, Claude declined to
continue writing fixes or Grok handoff prompts aimed at getting this specific
character image/video request working, since doing so means hardening the
same pipeline that is demonstrably capable of and has recently been used for
large-scale explicit content generation. The three harness fixes above
(`ec`/`ed`/`ee`) are general-purpose telemetry/routing correctness fixes and
stand regardless; **the open "make the render actually work" thread is what
Claude stopped on**, not the underlying bug diagnosis. `h3-ryan`'s output was
not touched, deleted, or reviewed further â€” noted here only as the reason
this thread is paused, per this project's own evidence-preservation norms.
Whoever picks this back up (operator or another agent) should decide
deliberately whether and how to continue, rather than this being silently
dropped.

## Scope-correction false positive on plain confirmations â€” fixed 2026-09-06

`CHANGELOG/2026-09-06f_specialist_scope_correction_false_positive_on_confirmation.md`.
Unrelated to the Bulma/Android-18 thread above â€” a different operator request
(a 12-clip VHS/liminal-space still sequence) got a bogus "I could not produce
a grounded answer... mixing in unrelated project context" refusal on turn 2,
a plain "yes proceed" reply to the assistant's own pending offer from turn 1.
Root cause: `_irrelevant_specialist_reply`'s scope guard required the
*current* turn's own text to restate topic keywords (regex was singular-only
â€” "images" didn't match `\bimage\b`), and had no notion of "this is a direct
reply to my own open offer." Fixed: broadened the keyword regex to plurals
plus `photo(s)`, and added `_pending_specialist_continuation(history)`,
which only looks at whether the *immediately preceding assistant turn* left
an active, undeclined invitation to continue â€” deliberately narrower than
"was this topic ever mentioned earlier in the chat," which would have broken
the existing `test_stale_h3_render_reply_is_discarded_on_unrelated_turn`
regression test (a real prior decline must still let a later hallucinated
render reply get caught). 99/99 `test_native_tool_calling` (new test
`test_confirmation_reply_to_a_pending_image_offer_is_not_discarded`
included), 190/192 combined with `test_capability_routing`/
`test_router_switching`/`test_general_assistant` â€” the 2 failures are the
pre-existing, unrelated `router.py` coding-model issue noted in
`2026-09-05ed`/`ee`. Not yet live-verified (same sandbox limitation as the
image-intent chain above â€” no way to restart `server.py` or drive the GUI
this session); needs a live resend of the reported chat shape to confirm.

## CPU-pinned 8B fallback falsely refused â€” fixed 2026-09-06

`CHANGELOG/2026-09-06g_cpu_pinned_fallback_model_falsely_refused.md`.
Operator-reported: a chat pinned to `huihui_ai/qwen3-abliterated:8b` on the
CPU tier, GPU idle, produced a self-contradictory routed message ("cannot
run now: ... GPU tier is unavailable" immediately followed by "using Huihui
8B on CPU ... GPU idle"). Root cause in `router.py`'s `decide()`: a correct
CPU-tier resolution (reuse the GPU-store 8B copy with `num_gpu=0`) was
computed and assigned to `selected`, then discarded by a later
anti-silent-substitution gate that checked the wrong variable
(`paired_cpu_fallback`, scoped to the primary-14B-pairing/coding-model
cases only) instead of recognizing that the pinned model *was itself* the
fallback model, so using it isn't a substitution at all. Fixed by checking
`_is_configured_variant(model, FALLBACK_REASONING_MODEL)` in that gate.
Verified the new regression test actually catches the bug (reverted the fix
in a scratch copy, watched the test fail exactly as reported, restored and
confirmed it passes) rather than trusting an added-but-unverified test.
`test_router_switching` 52/54, combined suite 210/212 â€” same 2 pre-existing,
unrelated coding-model failures noted since `2026-09-05ed`. Confirmed no
regression on `test_gpu_only_pin_refuses_instead_of_substituting_when_busy`,
the test that guards against silently substituting 8B for an unrelated
pinned model. Not yet live-verified against the running server (same
sandbox limitation noted in the sections above).

## Portfolio â€” job-search deliverable, not project infrastructure

- [x] **Portfolio showcase finished, 2026-09-04.** `outputs/portfolio/local-agent-platform-showcase/` is now a self-contained, initialized git repo (LICENSE, .gitignore, one commit): redacted README, two case-study docs (`docs/OVERVIEW_SIMPLE.md`, `docs/OVERVIEW_TECHNICAL.md`), and five real, genericized code excerpts (`router_gpu_arbitration.py`, `thermal_guard.py`, `celery_app.py`, `mcp_client.py`, `harness_profiles.py`) â€” the last two added once their underlying features actually shipped and live-verified, per the original plan. Technical doc updated to reflect harness profiles as shipped (not in-progress), with the real 589.6s -> 4.3s evidence, plus a fourth evidence-driven example covering the GPU-timeshare TOCTOU residual-risk discipline. Final grep scrub for personal paths/identifiers came back clean. Remaining: operator review pass over both case-study docs before sending to a recruiter or making the repo public â€” that review is the operator's call, not something to do unprompted.

## Media accuracy gate â€” added 2026-09-08

- [x] Add deterministic still-output checks for decodeability, dimensions, aspect ratio, blank frames, and prompt controls (`local_agent/media_accuracy_gate.py`).
- [x] Stop the stills phase when a generated image fails the gate; preserve the failed artifact and reasons in production progress.
- [x] Add regression tests (`local_agent/test_media_accuracy_gate.py`).
- [ ] Add optional exact-Qwen2.5-VL semantic review only when the GPU is explicitly idle; never substitute another VLM.
- [ ] Re-run production with the gate enabled after the current r98 worker naturally finishes or is resumed.
# Media QA follow-up â€” adaptive failure analysis (requested 2026-09-08)

- [ ] Integrate the exact Qwen2.5-VL Caption V4 output into a prompt-grounded
  JSON verdict (subjects, setting, composition, camera visibility, pose/action,
  continuity) for each still/video; a generic caption alone is not QA.
- [ ] After the semantic image/video checker is proven reliable, count consecutive
  failed generations per clip/prompt (threshold: 3â€“4).
- [ ] On threshold, capture the prompt, negative prompt, model/profile, seed,
  references, sampler settings, VLM caption, QA rationale, and render receipts.
- [ ] Have the local agent diagnose the failure pattern and propose a bounded
  prompt/process adjustment; never silently alter neighboring clips or approved
  evidence.
- [ ] Apply an adjustment only after deterministic validation and preserve the
  original prompt/output as versioned evidence.
- [ ] Add regression tests proving the escalation occurs at 3â€“4 failures and
  cannot loop indefinitely or auto-approve a failed generation.
# High-priority local-agent execution parity

- [ ] Add a durable task controller that converts a user request into explicit
  stages, executes tools, and records a receipt after every stage.
- [ ] Require each stage to report physical evidence (file path, checksum,
  process/endpoint state, and structured result) before the controller advances.
- [ ] Add prompt-pack-specific state: source revision, clip/shot IDs, approved
  references, model profile, seeds, sampler settings, and current attempt.
- [ ] Add a failure classifier that distinguishes bad prompt, bad graph/payload,
  unavailable model, startup failure, timeout, OOM, and QA mismatch.
- [ ] Add bounded recovery: retry the failed stage with preserved evidence,
  never overwrite approved artifacts, never change neighboring clips, and stop
  after a configurable retry budget with a diagnostic receipt.
- [ ] Add semantic image/video QA that compares the exact VLM caption against
  required subjects, setting, camera mode, pose/action, continuity, and negative
  constraints; generic captions must not count as approval.
- [ ] Add an operator-visible execution timeline showing what the agent did,
  what evidence was produced, and the exact next action.
- [ ] Add regression tests for stage resumption, stale context, wrong-project
  routing, hallucinated completion, stale artifact reuse, and failed QA repair.



## C002 repair stopped — 2026-09-11m
- [x] Operator: stop C002 repair; leave production paused (no v5a3/v5b/donor).
- C002_start still blocked on raised-arm continuity; accepted C001_last unchanged.

## C003 start identity pause — 2026-09-11q

- [x] C002_last accepted for still-only continuation through a hash-pinned,
  exact-VLM-reviewed endpoint candidate; videos remain unauthorized.
- [x] Add one bounded same-image retry for malformed exact-VLM response
  envelopes; format errors no longer trigger a replacement render.
- [x] Add and test SDXL `i2i_identity` full-frame IP-Adapter conditioning.
- [x] Recover C003_start with a separately generated, room-preserving,
  hash-pinned reset donor and pass the normal mechanical plus exact-VLM gates.
- [x] Add a two-completed-attempt stop guard for unconditioned C003_last
  failures so a restart cannot roll seeds indefinitely.
- [ ] C003_last is paused after two reviewed whole-frame failures. Use targeted
  identity-plus-gesture control or a separately reviewed hash-pinned endpoint;
  do not regenerate by seed alone. The third created artifact is explicitly
  unreviewed and ineligible for acceptance.

## Media Generation Pipeline — COMPLETE 2026-09-15a

Offline loop is operational: compiled DSPy (`models/dspy_compiled/temporal_physics_v1.json`)
via local Ollama (`configure_local_dspy_lm`, silent regex fallback if 11434 is down),
SDXL/FLUX-style txt2img through `PipelineOrchestrator`, Wan 2.2 First-Last-Frame
video (`WanFirstLastFrameToVideo`, live peak 13453 MiB). Legacy
`work/image_render.py` startup is unchanged.

- [x] **Dual-stage prompting / router-rewriter — implemented 2026-09-14aa.**
  Existing Backrooms adapters and prompt-pack production code rewrite specific
  reviewed packs, append strong negatives, and bind LoRA/environment rules, but
  there is no general routing middleware that converts arbitrary operator
  prompts into model-specific dialects for SDXL, FLUX, Qwen-Image, or future
  video models. Added `local_agent/prompt_router.py` with reusable SDXL, FLUX,
  and video dialect formatting plus known failure-mode negatives.
- [x] **Dynamic JSON workflow injection — implemented 2026-09-14ab.**
  `work/image_render.py` still owns production mode graphs (custom nodes
  disabled on that renderer). Media-pipeline injection lives in
  `local_agent/comfy_graph_builder.py`: load a base txt2img API graph, allocate
  the next string node id, copy live `[node_id, slot]` links, and splice a
  conditioner (ControlNet-style) between CLIPTextEncode and KSampler without
  dropping existing KSampler keys.
- [x] **Automated local correction / FaceDetailer — implemented 2026-09-14ab.**
  Human-subject regex on the finalized prompt (man/woman/person/girl/boy/face/
  portrait, prohibitions stripped) auto-injects Impact Pack FaceDetailer after
  VAEDecode, reuses the base CheckpointLoaderSimple model/clip/vae pointers,
  and routes IMAGE through FaceDetailer into SaveImageWebsocket. Empty Mode B
  plates do not trigger. Coverage in `tests/test_media_pipeline.py`.
- [x] **Resolution and bucket math — implemented 2026-09-14aa.**
  Current code validates multiples of 8 and hardcodes common sizes such as
  1024x768 or model-profile defaults, but there is no reusable aspect-ratio
  middleware that snaps requested outputs to optimal SDXL/FLUX bucket sizes
  with multiples of 64 and records the chosen bucket. Added
  `local_agent/media_buckets.py` with a reusable bucket resolver for standard
  aspect strings and custom numeric ratios.
- [x] **Video temporal physics layer — implemented 2026-09-14ac.**
  `local_agent/temporal_physics.py` expands arbitrary video prompts for
  8-second Backrooms renders into a dense paragraph (first-person camcorder
  tracking, VHS, handheld walking momentum, unbroken take, camera shake,
  1990s home video). Locked or already-specified camera moves (tripod, static
  shot, dolly, pan, security camera) suppress the handheld-momentum family.
  `prompt_router` video dialect consumes the same expander. Compiled DSPy
  artifact `models/dspy_compiled/temporal_physics_v1.json` is loaded by
  `runtime_inject_temporal_physics` when a local LM is configured; otherwise
  the deterministic injector is used. Coverage in `tests/test_media_pipeline.py`.

- [x] **DSPy compile + runtime integration — implemented 2026-09-14ai.**
  Four few-shot demos baked offline. Orchestrator video/Backrooms jobs call
  `runtime_inject_temporal_physics`; CLIPTextEncode receives the expanded
  paragraph. No XAI_API_KEY required at dispatch time.
- [x] **Local Ollama DSPy inference — implemented 2026-09-15a.**
  `configure_local_dspy_lm` pings `127.0.0.1:11434` and points `dspy.settings.lm`
  at `ollama_chat/<installed model>` (prefers qwen2.5:7b / mistral, else
  llama3.1:8b). If Ollama or dspy is missing, dispatch still uses the
  deterministic injector. `test_dynamic_dspy_dispatch.py` exercises the path.
- [x] **Ollama keep_alive=0 + 24-clip batch runner — implemented 2026-09-15b.**
  DSPy LM kwargs include `keep_alive=0`; after each inject, `/api/generate`
  with `keep_alive=0` unloads weights before Wan. Preferred models are
  `llama3.2:1b` / `qwen2.5:1.5b` first. `batch_generate_backrooms.py` runs
  C016–C039 sequentially (inject → stills → `/free` → Wan FLF → `/free`),
  logging failures and continuing. Default is dry-plan; `--execute` submits.
- [x] **Phase 4 Wan Tile upscale — implemented 2026-09-15c.**
  After Wan FLF `/free`, 720p low-denoise (0.35) KSampler +
  `wan2.1_tile_control` ControlNet; output `photoreal_video_<clip>.mp4`.
  Phase 4 errors keep the Phase 3 mp4 and continue.

---

## Reference-video motion transfer with character replacement — operator decision — 2026-09-25q

- [ ] **Approve one download, or accept the installed-only path.** No tool in this
      tree can reuse a reference video's motion with a different character; the
      GVD router now says so with names (`gvd_route_shot` → `missing_capabilities:
      motion_reference`, `blocked_candidates`), and `plan_video_from_reference`
      reports feasibility per approach. Options (details and sizes in
      `docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md` §3c–§4):
      (a) Wan 2.2 Animate 14B — ~17 GB fp8 into `ComfyUI-Shared/models/diffusion_models/`
          (+0.6 GB optional relight LoRA into `loras/`); best fit for the request.
      (b) Wan 2.1 VACE 1.3B module — ~1.2 GB into `diffusion_models/`; cheapest real
          pose-driven video-to-video, lower fidelity.
      (c) AnimateDiff SDXL + ControlNet union + IP-Adapter Plus Face — nothing to
          download; lowest quality, flickers over long clips.
          2026-09-25t: the upside-down output is root-caused (DWPose face + hand
          keypoints together; `detect_face: disable` fixes it) and one 16-frame
          window now renders upright and follows the reference motion.
          2026-09-25u: `ComfyUI-Advanced-ControlNet` installed (operator
          approval); 24-frame multi-window clips render upright and follow the
          motion. 2026-09-25v: a tight face crop of the character (+ a region
          mask) holds identity through 24 frames; softness and late-clip
          drift on head turns remain. 2026-09-26a: a video face-detail pass
          (denoise 0.5) improves late frames with no added flicker; faces stay
          soft at 768x448 (face ~60 px). 2026-09-26g: FaceID Plus V2 installed
          (approved); FaceID only in the detail pass is the best balance (ArcFace
          identity 0.173 vs 0.040, scene/body unchanged); operator to judge likeness.
          2026-09-26d: operator decision — FaceID Plus v2 SDXL weights
          (on disk since 00:55) confirmed, and option (a) Wan 2.2 Animate
          14B approved for download (18.4 GB fp8 e4m3fn scaled KJ).
      Whichever is chosen still needs a pinned API template, a measured local VRAM
      profile, a validation render and GVD promotion before a
      `render_video_from_reference` tool can exist (doc §7). Nothing renders today.
- [ ] Never put a real, identifiable person's likeness into sexual content with
      these tools; the planner does not check inputs for that.

Evidence: `CHANGELOG/2026-09-25q_queued_analysis_honesty_and_motion_transfer_plan.md`.
