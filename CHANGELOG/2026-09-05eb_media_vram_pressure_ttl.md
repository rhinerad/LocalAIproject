# 2026-09-05eb — Expire leaked media VRAM pressure; clear on failed vision start

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05eb**.

Implements the scoped fix from `2026-09-05dw`. A failed VLM start left
`local_agent/runtime/media_vram_pressure.json` on disk forever, so every
later pinned Huihui-14B GPU chat was silently demoted to 8B. No
`classify_capability` change. No image-gen keywords. dw ruled those
unsafe (they would not have kept the pinned chat on 14B, and unpinned
would farm-route a 16-still job to Qwythos).

## What changed

1. **TTL.** `media_pressure()` is no longer `is_file()`. A stamp older
   than `MEDIA_PRESSURE_TTL_S` (300s) is unlinked and treated as absent.
   The dw leak shape `{"at": <old>}` (no `ttl_s`) expires the same way
   via `at` or mtime. A leftover file from a failed `see_image` no
   longer demotes 14B after five minutes, without a manual delete.
2. **Clear on None.** `_prepare_vision_batch` still sets the flag on
   downgrade/evict *before* the VLM is proven up. Every failed/no-op
   return (`tier is None`, VRAM still short, `ensure_qwen25_vl_runtime`
   false, or exception) now `set_media_pressure(False)` in `finally`.
   A successful return leaves the flag for `_release_vision_batch`.
3. **In-flight.** Watcher jobs call `refresh_media_pressure()` (rewrite
   `at` if the file is still on disk) at job start and on video
   progress, so a genuine batch longer than the TTL keeps demoting 14B
   until the reclaim window ends. `run_once` always releases after a
   successful prepare, even if the queue raced empty (`vision_ran` used
   to skip that clear).

`decide()` still demotes PRIMARY → 8B with reason `media VRAM pressure`
while the flag is fresh.

## Tests

```
python -m unittest local_agent.test_router_switching local_agent.test_media_watcher_exact_qwen local_agent.test_vram_arbitration -q
```

70/70 OK. Explicit cases:

- Fresh flag demotes a pinned 14B GPU chat to 8B (`media VRAM pressure`).
- Leaked `{"at": 1.0}` after TTL does **not** demote; file is unlinked.
- Failed VLM start after downgrade/evict, and the `None` wait path,
  clear the flag immediately.
- Successful prepare keeps the flag while the batch is in flight.
- `run_once` calls `_release_vision_batch` after prepare even if no job
  was claimed.

## Files

- `local_agent/router.py`
- `local_agent/media_watcher.py`
- `local_agent/test_router_switching.py`
- `local_agent/test_media_watcher_exact_qwen.py`
- `TODO.md` (dw item marked fixed)

No GPU work. No `APP_REVISION` bump (routing latch only; launcher
readiness unchanged). Semantic judge / farm / `.env` untouched.
