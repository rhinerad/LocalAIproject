# PATCH: VHS post-process hook (STAGED — do not apply yet)

**Status:** draft / dry-run only.  
**Do not** edit live `dspy_orchestrator.py` until this patch is approved.  
**Do not** run `vhs_postprocess.py` as part of this staging step.

## Intent

Diffusion (FLUX still → MiniMax / Wan I2V) smooths away high-frequency camcorder texture. After ComfyUI writes the MP4, run FFmpeg once to bake:

1. color noise / grain  
2. mild chromatic fringe  
3. blinking `REC` overlay  

Then (and only then) hand the processed path to Qwen-VL.

## New module

- `local_agent/vhs_postprocess.py`  
  - Public API: `apply_vhs_look(input_mp4, output_mp4, ...) -> Path`  
  - CLI: `python vhs_postprocess.py in.mp4 out.mp4`

## Exact call site in `dspy_orchestrator.py`

Hook **immediately after** the Comfy wait returns a saved `.mp4`, and **before** any VLM / Qwen-VL frame extract or scoring.

Locate the success path inside `generate_minimax_clip` (names may vary slightly), roughly:

```python
        video_path = wait_for_video(pid, orch.comfy_url, timeout_s=60)
        # ... existing /free / VRAM release ...
```

Insert the staged boilerplate **right after** `video_path` is confirmed on disk, **before** `prepare_vlm` / `extract_eval_frames` / `run_qwen_director_scores`:

```python
        # --- STAGED VHS POST (apply when approved) ---
        # Must run AFTER Comfy saves the MP4, BEFORE Qwen-VL grades it.
        from vhs_postprocess import apply_vhs_look

        _raw = Path(video_path)
        _vhs = _raw.with_name(_raw.stem + "_vhs" + _raw.suffix)
        try:
            video_path = apply_vhs_look(_raw, _vhs)
            print(f"  VHS post -> {video_path}")
        except Exception as _vhs_exc:
            # Fail-open during rollout: keep raw MP4 so the batch can proceed.
            print(f"  VHS post skipped: {_vhs_exc}")
            video_path = _raw
        # --- END STAGED VHS POST ---
```

### Suggested full sketch (context only)

```python
def generate_minimax_clip(...):
    ...
    tracked = _track_prompt_with_phase(...)
    if tracked.get("state") != "complete":
        raise TimeoutError(...)

    video_path = wait_for_video(pid, orch.comfy_url, timeout_s=60)

    # POST /free so VRAM is free for Qwen-VL
    try:
        vram_controller.comfy_free(...)
    except Exception:
        pass

    # >>> VHS POST HOOK GOES HERE (before any VLM call) <<<
    from vhs_postprocess import apply_vhs_look
    _raw = Path(video_path)
    _vhs = _raw.with_name(_raw.stem + "_vhs" + _raw.suffix)
    try:
        video_path = apply_vhs_look(_raw, _vhs)
    except Exception as _vhs_exc:
        print(f"  VHS post skipped: {_vhs_exc}")
        video_path = _raw

    # VLM / media accuracy gate consumes `video_path` next
    # frames = extract_eval_frames(Path(video_path))
    # parsed = run_qwen_director_scores(frames, ...)
    return Path(video_path)
```

## Batch path note

If `batch_run_backrooms_gvd.py` calls `run_literal_vlm_qa` on the path returned from `submit_comfy` / `generate_minimax_clip`, wiring the hook inside `generate_minimax_clip` covers both MIPRO eval and batch without a second call site.

Optional later: a `--skip-vhs` flag on the batch CLI for A/B checks.

## Acceptance checks (when execution is allowed)

1. Raw Comfy MP4 unchanged on disk.  
2. Sibling `*_vhs.mp4` exists and is larger or differently hashed.  
3. VLM QA dump `video_path` points at the `*_vhs.mp4`.  
4. No FFmpeg call happens during this staging PR itself.

## Out of scope for this patch file

- Editing `dspy_orchestrator.py`  
- Running FFmpeg or any Python entrypoint  
- Changing VLM rubrics or clip overrides  
