# 2026-09-24f — local_agent GUI: inline cards for failed and not-started batch stills

## Why

After 2026-09-24b, `render_story_image_batch` got one ready card per completed
still. `failures[]` and `pending[]` produced nothing, so in a half-failed batch
the operator saw the frames that rendered and no sign of the ones that didn't.

## What changed

`local_agent/server.py`
- `collect_story_media_artifacts()` now adds `_batch_status_cards()` after
  the ready cards of a batch result:
  - **one error card per `failures[i]`** (`status: "error"`, no filename),
    in the same locator shape as the `poll_render_watches()` error cards.
    `label` = `batch item <index>: <prompt_preview>`. `note` is the
    `blocked_by` summary when present (e.g. `foreign_backend: port 8188 is
    held by pid …`). Otherwise it is the error (`finished_without_manifest` /
    `timed_out` / the launch error), plus `(pid N)` and the last `log_tail`
    line. Capped at 240 chars. Also carries `batch_index` and `phase`.
  - **one summary card for all of `pending[]`** (`status: "not_started"`),
    labelled `N batch items (i, j, …)` and noted `not started after failure —
    story <s>`. Decision: one card, not one per entry. With
    `stop_on_failure` (the default), every job after the first failure lands
    in `pending[]`. Twenty identical "not started" cards would bury the one
    real failure. The label still lists every missing index.
- These file-less cards carry a `card_key`. `media_artifact_key()` uses it,
  and `extend_unique_artifacts()` de-duplicates on it just as it does for
  files. Pending/error locators without a `card_key` (render-watch cards)
  still always pass. Real duplication path found: `agent._emit_tool_result`
  sends the clipped `tool_result` **and** the full internal media event, and a
  batch result under 4000 chars (e.g. an all-launch-failure batch) parses on
  both. Without the key every error card appeared twice. The key includes the
  pid, so a retry that fails again with a new pid is a new card. It is
  per-turn only: the turn's `_media_artifacts` list starts empty.

`local_agent/static/index.html` — `mountMediaArtifact()`
- The error branch also renders `status === "not_started"` with the headline
  "not started" instead of "generate failed".
- Error/not-started cards show `label` inline unless `art.late` (late cards
  already show it in their tag). The GUI's own `mediaKey` de-dup is unchanged
  (files only), so a retried batch that fails again in a *later* turn still
  shows its card.

## Evidence

- `python -m unittest test_render_media_announce test_story_image_reveal
  test_story_stills_batch_review test_native_tool_calling` → 185 tests OK.
- `test_render_media_announce.py`: the `_batch_result()` fixture's await
  failure gained a `log_tail`. New tests cover card order (ready, ready,
  error, not_started), await/timed_out/launch-blocked notes, the pending
  summary card, malformed entries, key-based de-dup, and two turn-level cases:
  a short failed batch parsed twice, and the same batch re-reported in one
  turn. Existing tests now filter to ready cards where they only meant files.
- Mutation check: with `card_key` identity disabled, the two turn-level tests
  fail (`['error','not_started'] != [... ×2]`, `4 != 6`).
- GUI script: `node --check` on the extracted `<script>` passes.
- **Not verified in the live GUI**: no batch render was run (none needed and
  not requested). The card text is exercised through the SSE/store path in tests only.

Backups: `server.py`, `static/index.html`, `test_render_media_announce.py`
→ `*.bak_batchcards_20260924_012955`.
