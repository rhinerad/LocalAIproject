# 2026-09-14ac - Video temporal physics layer

Scope: Media Generation Pipeline task 5. No Equal Shares production, no
ComfyUI, no live video render.

## Added

- `local_agent/temporal_physics.py` with `inject_temporal_physics(base_prompt,
  style="backrooms")`. Default Backrooms cues are first-person camcorder
  tracking, heavy VHS artifacting, handheld walking momentum, continuous
  unbroken shot, realistic camera shake, and 1990s home video aesthetic.
  Dedup skips phrases already in the base prompt. Locked cameras (tripod,
  static shot, security camera) and specified moves (dolly, pan, tilt) drop
  the handheld-momentum family.
- `local_agent/prompt_router.py` video dialect now expands Action through
  that function and adapts the Camera motion line on lock/specified-move.
- Tests in `tests/test_media_pipeline.py`. TODO.md task 5 marked complete.

## Validation

```
python -m py_compile local_agent/temporal_physics.py local_agent/prompt_router.py
  tests/test_media_pipeline.py
python -m unittest tests.test_media_pipeline -q
```

19 passed.
