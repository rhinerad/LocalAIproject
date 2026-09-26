# 2026-09-23d — Backrooms clip-to-clip chaining wired in; shadow review FAILED, live not enabled

Spec: `backrooms-frame-chaining-spec.md`. `batch_run_backrooms_gvd.py` renders a
fresh FLUX still for every clip. This change lets it start a clip from the
previous clip's actual last frame when `work/scene_reasoner.py` says
`context_video` and two deterministic guards allow it. **Default is `off`**, so
existing invocations behave as before. No render was run.

## Code

- `local_agent/video_chain.py` (new)
  - `extract_last_frame()` uses the same ffprobe + ffmpeg subprocess pattern
    as `dspy_optimizer.extract_eval_frames` (CREATE_NO_WINDOW, 15 s/60 s
    timeouts, check=True). It seeks to duration−1 s and writes with
    `-update 1`, so the file ends as the true last frame.
  - Unlike eval frames, any failure raises `ChainFrameError`. There is no
    guessed 2 s fallback duration.
  - Output name is stem + content digest (not path digest), under
    `local_agent/runtime/gvd_backrooms_batch/chain_frames/`.
  - `upload_to_comfy_input()` POSTs `/upload/image`, the same multipart form as
    `gvd_qa/smoke_i2v_from_receipt.py`. Nothing uploaded frames before:
    `bind_h3_image_frames` passes a basename that ComfyUI's input dir must
    already hold.
- `local_agent/dspy_orchestrator.py`: new `prune_unreferenced_flux_nodes()`,
  called in `build_minimax_graph` when a first frame is bound and the run is
  not stills-only.
  - Rebinding `first_frame` already orphaned the FLUX branch. Pruning makes
    the skipped still explicit in the payload dump (`_meta.flux_still_skipped`,
    `pruned_flux_nodes`).
  - This also affects the single-clip CLI when a QA-accepted still is passed.
    Its FLUX nodes were already orphaned there, so what executes is unchanged.
- `work/scene_reasoner.py`
  - `decide_shot` / `reason_about_shot` accept an optional explicit `history`.
    The append-only log follows decision order, which differs from story
    order on resume, `--force`, or repeated passes.
  - History rows may carry `camera_mode`, `speakers`, `shot_summary`. Before
    this, the model was asked about character reappearance while seeing only
    prior decisions, never what the shots contained.
- `batch_run_backrooms_gvd.py`
  - `--continuity off|shadow|live`, `--chain-max-consecutive`
    (`CHAIN_MAX_CONSECUTIVE = 4`), `--continuity-story`.
  - Policy: `continuity_policy()`. Guards on top of the reasoner:
    camera-mode change (`Camera Mode:` in the clip header) and the ceiling.
  - Live fallbacks, every one to a fresh still:
    - reasoner error or blocked (including confidence < 0.6)
    - `reference_image` or `none`
    - clip 0 or `--stills-only`
    - previous clip not SELECTED (legacy `done` does not count)
    - extract or upload error
    - a ref2vid clip
  - Each clip's `progress.json` entry carries `continuity` (setting, policy,
    mode_used, reason_code, continuity_reason, source clip/video, chain frame,
    uploaded name, chain_depth, reasoner summary) and `start_frame_source`.
    The error entry carries them too.
  - **`--dry-run` no longer overwrites `progress["clips"]`.** It writes
    `dry_run_report.json` instead. Before, a dry run replaced SELECTED or
    rendered entries (and their `video_path`) with `{"status": "dry_run"}`.
    The live file has C001 SELECTED plus C002–C008, so the spec's full-pack
    shadow dry run would have destroyed that resume state.
  - Shadow runs also write `continuity_shadow_review.md`.
- `local_agent/backrooms_prompt_adapter.py`: comment only.

## Decisions

- **Adapter `references`: not a continuity input.** The spec says nothing
  reads it, but that is wrong: `backrooms_still_contract.py`,
  `creative_still_qa.py`, `flux_still_batch.py` and two live_jobs scripts do.
  It is also absent on all 102 clips of the FULLY MERGED pack, because
  `apply()` returns early. It stays still-review metadata for older packs;
  `scene_reasoner` is the only continuity input for this path.
- **ref2vid × chaining: exclusive per clip for now.**
  `PATCH_minimax_ref2vid.md` says "STAGED", but the code is integrated in
  `build_minimax_graph` and `clip_overrides/C002.json` opts C002 in.
  `ReferenceToVideo` has no `first_frame`, so a chained frame would be dropped
  silently. Such clips record `ref2vid_path_has_no_first_frame`. If both are
  wanted later, the chained frame should become an extra `<Picture N>`.
- **Ceiling 4**: a fresh still at least every 5th clip (~50 s).

## Evidence

- `extract_last_frame` on
  `ComfyUI-Shared\output\dspy_opt\gvd_br_c001_d393fd2aba_00001_.mp4` (192
  frames, 1280×704): pixel-identical to frame 191 (`select=eq(n,191)`), mean
  abs diff 0.139 vs frame 190. 1.5 s cold, cached after.
- Offline `build_minimax_graph(clip_id=br_c003, start_frame_path=…)`:
  - FLUX nodes 3,5,6,7,8,10,11,12,14,41 are pruned.
  - `20.first_frame` → `["1001",0]` (LoadImage), and all links resolve.
  - `--stills-only` keeps FLUX.
- **This is not render verification.** Per CLAUDE.md, verification needs a
  real render's embedded workflow, and none was run.
- Tests pass:
  - `test_batch_run_backrooms_continuity.py` (new, 31, including real ffmpeg on
    a synthetic clip)
  - `test_batch_run_backrooms_gvd.py` (6)
  - `work/test_scene_reasoner.py` (20, 3 new)
- `verify_p0_offline.py` fails before reaching this code:
  `handoff/gvd_core.py` is missing. That failure predates this change.

## Shadow review — FAILED; do not use `--continuity live` yet

Setup: the full 102-clip pack, `huihui_ai/qwen3-abliterated:8b`, GPU idle, no
ComfyUI. Eviction was verified at the end.

- **v1** (history included prior decisions; saved as `*_v1_with_prior_decisions.*`):
  101/101 `context_video`, all at confidence 1.0, with only 5 distinct reason
  strings. The model copied its own earlier reasons verbatim. C015 (the fall
  into the Backrooms) got "Same room and camera, no scene change".
- **A/B, 14 boundary clips, no prior decisions**
  (`continuity_ab_no_prior_decisions.json`): reasons became specific, but
  decisions stayed 14/14 `context_video` at 0.95–1.0. That includes C015,
  C016 (apartment → Backrooms), C063 (camera propped) and every ENTITY
  entry or re-entry (C050, C051, C054).
- **v2** (the committed code: prior decisions removed; current
  `dry_run_report.json`, `continuity_shadow_review.md`): 101/101
  `context_video`, 63 distinct reasons. C063 was blocked only because the
  model named an unregistered character id (`outputs/stories/character_library.json`
  does not exist).
  - Reason codes: 80 chain, 18 `chain_ceiling`, 2 `camera_mode_change`
    (C015, C016), 1 blocked, 1 first clip.

Conclusion: with this model and prompt, the reasoner never picks
`reference_image`, so it adds nothing over "always chain". All scene-boundary
protection comes from the deterministic guards. ENTITY re-entry, which is
the drift case `scene_reasoner` exists for, is caught by nothing. Live mode
would chain it.

## Follow-up (same session): 14B trial, and a deterministic re-entry guard

- **14B trial** (`continuity_ab_14b.json`): through `scene_reasoner`'s
  `format: json` call, `huihui_ai/qwen3-abliterated:14b` returns the literal
  `{}`. That is parsed as confidence 0 and blocked, so every shot would get a
  fresh still (safe). A direct call with Ollama `think: false` (Ollama
  0.32.15) returns real decisions, but they repeat the 8B mistakes: C015
  `context_video` 0.9 ("the scene has not changed"), C016 and C054 the same.
  `scene_reasoner._call_ollama` was not changed; the default 8B model works
  as is.
- **Re-entry guard** in `batch_run_backrooms_gvd.py`:
  - New helpers: `pack_cast`, `clip_characters_present`,
    `character_reentries`, and constant `POV_HOLDER_BY_CAMERA_MODE = {"B": "ACTOR"}`.
  - Present means the character speaks, or their speaker id appears as a word
    in the opening composition or action text.
  - A re-entry is: present in this clip, absent from the previous clip, and
    present in some earlier clip. It forces reason `character_reentry`.
  - The pack's Mode B says the actor's "face/body is never shown", so the
    handheld camera holder counts as present throughout Mode B. Without that,
    11 ACTOR "re-entries" were false positives.
  - Records carry `reentering_characters`, and the review table has a
    re-entry column.
  - This duplicates a judgement `scene_reasoner` is asked to make, on
    purpose: the model never made it.
- **Shadow v3** (current `dry_run_report.json`, `continuity_shadow_review.md`;
  v2 kept as `*_v2_no_prior_decisions.*`):
  - Policy: 76 chain / 26 fresh (102 fresh today).
  - Fresh-still reasons: 3 `camera_mode_change` (C015, C016, C063), 8
    `character_reentry` (ENTITY C047, C049, C053, C056, C059, C061, C074;
    ACTOR C071), 14 `chain_ceiling`, 1 first clip.
  - Longest chained run is 4. The reasoner is still 101/101 `context_video`.
- Tests: `test_batch_run_backrooms_continuity.py` has 37 tests (6 new);
  37 + 6 + 20 pass.
- **Status:** the protection comes entirely from the deterministic guards.
  The reasoner is kept in the loop only because it can make things safer
  (anything other than `context_video` means a fresh still), never less
  safe. `--continuity live` is ready for the small live test below. It has
  not been run.

## Not done

- **Live 3–4 clip test.** Not run: ComfyUI (Rockernow) was not running,
  CLAUDE.md forbids starting a backend for a side experiment, and each clip
  is about 15–20 GPU minutes. Proposed run:
  `--clip C012 --clip C013 --clip C014 --clip C015 --continuity live`.
  - Expected: C012 fresh (`prev_clip_not_selected`), C013 and C014 chained,
    C015 fresh (`camera_mode_change`).
  - Verify by extracting each MP4's embedded workflow
    (`ffprobe -show_entries format_tags=prompt`). C013 and C014 should show
    `LoadImage 1001` and no FLUX nodes.
  - Then compare C013's first frame with C012's last frame.
- Scratch from the frame check: `local_agent/runtime/gvd_backrooms_batch/_verify_tmp/`
  (2 PNGs).
