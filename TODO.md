# TODO — live execution queue

Prepend new dated sections at the top. Closed items and sections older than the
2026-09-22 restart live in `archive/TODO_closed_2026-09.md` (nothing was deleted).
Open items that were below the restart are carried over at the bottom of this file.

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
- [x] Run that download only while no render owns the GPU/drive (the
      motion-transfer session was mid-render when decided); verify size and
      sha256 against the Hub LFS metadata; never load it without a pinned
      template + measured VRAM profile (doc §7). Done 2026-09-26h: on disk,
      18,401,760,586 B, sha256 `2936b314…5b8e6` = Hub LFS oid, 0 render
      pauses; relight LoRA not fetched. Nothing loaded or promoted.
- [ ] `catalog_seed.py` row `wan22_animate_14b_unvalidated` and doc §3c still
      say the Animate weights are missing; update the text (row stays
      disabled until template + measured profile + promotion). Left for the
      motion-transfer session, which owns those anchored edits. 2026-09-26h.
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

## GVD router "ask, don't guess" reaches the chat — 2026-09-26f

- [x] The router's honest-failure statuses (NEEDS_MANIFEST_REVIEW,
      PROFILE_REQUIRED, NO_COMPATIBLE_TOOL, RESOURCE_BLOCKED,
      UNAVAILABLE_CAPABILITY, plus ENGINE_FALLBACK_WAN / QA_GATE_BLOCKED)
      used to reach the model as a JSON blob and the operator as whatever the
      model narrated (replayed on HEAD: "rendering has started" for a
      blocked route). `agent.py` now ends such a turn with a fixed question
      built from the tool's own fields (`_gvd_router_question`), and a
      selected route's `operator_notice` (Wan fallback, 26b) is appended
      verbatim to the model's reply. 24 tests + before/after replay.
- [ ] The running GUI `server.py` loads the old `agent.py` until restarted;
      no live chat has used this yet.
- [ ] Notices are not appended on the hop-limit or empty-completion reply
      paths (rare; the fixed replies there carry no router text).

Evidence: `CHANGELOG/2026-09-26f_gvd_router_honest_failures_reach_chat.md`.

---

## Motion transfer productionization (roadmap Phase 3) — 2026-09-26i

Two sessions are building this. The motion-transfer session owns the tool
(`render_video_from_reference` / `video_reference_job_status`, worker
`local_agent/motion_transfer_render.py`, `motion_transfer_faces.py`; its
artefacts are labelled `26h`, an id already used by the download entry). The
roadmap session added CPU building blocks only.

- [x] Per-frame character masks + face rule from DWPose keypoints
      (`local_agent/motion_transfer_masks.py`), pinned two-stage API templates
      + builder (`local_agent/graphs/motion_transfer_animatediff_*`,
      `motion_transfer_graph.py`), router `requires_capabilities` gate, and
      the `animatediff_pose` family in `apply_profile.py` / `smoke_measure.py`.
      46 tests. 2026-09-26i.
- [ ] Fixture `gvd_tool_router/fixtures/animatediff_pose_smoke.api.json` from
      the graph the tool really renders (files must exist on this machine).
- [ ] Receipt-gated smoke on the owned backend (`smoke_measure --family
      animatediff_pose`) → measured peak → `apply_profile.py` promotion. Only
      when no render owns the GPU; the seed row stays disabled until then.
- [ ] Decide whether the worker adopts the per-frame masks (the worker uses a
      static per-job vertical band from InsightFace faces today).
- [x] Confirm `test_gvd_tool_router` + `test_gvd_engine_policy` still pass
      after the router gate (`runtime/roadmap_20260926/tests_p3_router.log`):
      74/74 OK, 2026-09-26i.

Evidence: `CHANGELOG/2026-09-26i_motion_transfer_per_frame_masks_pinned_templates_router_gate.md`.

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

---

## Carried-over open items (from sections older than 2026-09-22)

Each line keeps its original section name. Close or delete here when done.

### C002 repair stop — 2026-09-11m
- [ ] Operator visually reviews and explicitly accepts or rejects that exact
### PowerInfer educational calibration draft - 2026-09-08d (review-only)
- [ ] Operator reviews worksheet keep/replace notes (notes are NOT approval) and explicitly approves or replaces pairs.
- [ ] TurboSparse remains parked — do not dump/train/convert/bench/register from this draft.
### Prompt-pack QA repair - 2026-09-08c / finish-prove 2026-09-08e
- [ ] Semantic QA is not run. Implement/execute review through the installed exact
- [ ] Regenerate current-prompt candidates through receipts, then obtain explicit
- [ ] Verify a real approved-input video and its embedded graph/hashes only after
- [ ] Optional operator step: bounded verify_prompt_pack_startup.py only if
### Done — managed prompt-pack tasks (2026-09-07b / r96)
- [ ] After Rhine restarts: paste/continue Backrooms pack on a fresh chat and confirm outputs under local_agent/runtime/managed_tasks/<cid>/
### Done — Flux/RealPro owned-backend visibility (2026-09-06s / r95)
- [ ] Full 18-clip Flux sheet after operator paste + review gate (VRAM: t5xxl_fp16 + ~12GB UNet on 16GB — expect slow / sequential only)
### Grok 2026-09-06n — continue / finish-earlier specialist unlock (DONE, on disk; restart later)
- [ ] After Rhine restarts: regenerate or continue on chat d98731129ac743ac and confirm render/plan no longer stale-blocked
### Grok 2026-09-06l — GUI Send/Stop unlock (DONE, on disk; restart later)
- [ ] After Rhine restarts: hard-refresh GUI and verify Stop returns Send mid-turn
### PHASE 1: Engine Architecture Evaluation (ACTIVE, operator directive 2026-09-02) — do this first
- [ ] **Task 1 — Evaluate PowerInfer architecture (resume, don't restart).
- [ ] **Task 2 — Evaluate TinyEngine architecture — researched 2026-09-02,
### PHASE 2: Context & Memory Optimization — was BLOCKED by Phase 1, now unblocked (2026-09-02)
1. [ ] **KV cache quantization** — BLOCKED by Phase 1. Update the chosen
3. [ ] **RAG-first memory retrieval** — BLOCKED by Phase 1. Enforce Chroma DB
4. [~] **Agentic RAG upgrade for local-docs retrieval** — Stages 1-2
### New model candidate — DeepSeek-V4-Flash abliterated (operator goal, 2026-09-01)
- [ ] **Operator goal:** experiment with
- [ ] **2026-09-05, follow-up: KTransformers / PowerInfer MoE feasibility
### Local-agent task completion reliability
- [ ] **2026-09-01, operator feedback:** "Claude, Claude Code, GPT are all very
### RealVisXL / SDXL LoRA capability — setup in progress
- [ ] Select one first training objective (consented identity *or* style), its
- [ ] With explicit GPU approval, make one bounded SDXL LoRA smoke run and
### Phase 1 worker-farm bootstrap — active, CPU-only
- [ ] Obtain an explicit operator decision and source selection before staging
- [ ] Add the secondary laptop only after it connects over a private encrypted
### PowerInfer control-plane evaluation — opt-in, not active
- [ ] Conduct a human quality comparison against the current Ollama routes
- [ ] Require a fresh GPU-gateway approval and keep PowerInfer separate from
- [ ] Parked: TurboSparse-Mistral projected abliteration. Canonical weights
- [ ] Bamboo-DPO Q4 runtime intake is complete and byte-verified as a
### Model Conversion & Profiling — mandatory preparation track
- [ ] After an accepted model exists, deliberately wire the registered endpoint
### PowerInfer-2 mobile edge evaluation — planning only
- [ ] Run a single benign, battery/thermal-observed Pixel test with
- [ ] Later, separately: abliterate `PowerInfer/SmallThinker-4BA0.6B-Instruct`
### Deferred distributed worker farm — planning only
- [ ] **10-node asynchronous Worker Farm** — planned control-plane/worker-plane
- [ ] Establish the 1-GbE capacity baseline: inventory every node, measure
- [ ] Prototype a private RabbitMQ ingress with publisher confirms, manual
- [ ] Add Celery for durable fetch/extract/encrypt workflows and Ray actors
- [ ] Build four operator-reviewed workflows: encrypted Judge evaluation;
- [ ] Encrypt raw artifacts and backups with authenticated AES-256-GCM;
- [ ] Gate all production work on private-network isolation, source/license
- [ ] See `docs/WORKER_FARM_ARCHITECTURE_PLAN_2026-08-29.md` for the
- [ ] **Farm efficiency, ticket 4 — Ratchet Loop (autoresearch-style
### Low-Priority Future Capabilities
- [ ] **Farm efficiency tickets 1/4** (full entries: Phase 2 section
- [ ] **Operator-approved phone-call assistant** — let the local agent complete
- [ ] **Trusted Android companion: approved phone files and app delivery** — evolve
- [ ] **Local 3D generation through ComfyUI** — accept a text prompt and optional
### Media accuracy gate — added 2026-09-08
- [ ] Add optional exact-Qwen2.5-VL semantic review only when the GPU is explicitly idle; never substitute another VLM.
- [ ] Re-run production with the gate enabled after the current r98 worker naturally finishes or is resumed.
### Media QA follow-up — adaptive failure analysis (requested 2026-09-08)
- [ ] Integrate the exact Qwen2.5-VL Caption V4 output into a prompt-grounded
- [ ] After the semantic image/video checker is proven reliable, count consecutive
- [ ] On threshold, capture the prompt, negative prompt, model/profile, seed,
- [ ] Have the local agent diagnose the failure pattern and propose a bounded
- [ ] Apply an adjustment only after deterministic validation and preserve the
- [ ] Add regression tests proving the escalation occurs at 3–4 failures and
### High-priority local-agent execution parity
- [ ] Add a durable task controller that converts a user request into explicit
- [ ] Require each stage to report physical evidence (file path, checksum,
- [ ] Add prompt-pack-specific state: source revision, clip/shot IDs, approved
- [ ] Add a failure classifier that distinguishes bad prompt, bad graph/payload,
- [ ] Add bounded recovery: retry the failed stage with preserved evidence,
- [ ] Add semantic image/video QA that compares the exact VLM caption against
- [ ] Add an operator-visible execution timeline showing what the agent did,
- [ ] Add regression tests for stage resumption, stale context, wrong-project
### C003 start identity pause — 2026-09-11q
- [ ] C003_last is paused after two reviewed whole-frame failures. Use targeted
### Reference-video motion transfer with character replacement — operator decision — 2026-09-25q
- [ ] **Approve one download, or accept the installed-only path.** No tool in this
- [ ] Never put a real, identifiable person's likeness into sexual content with
