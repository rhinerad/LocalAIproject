# 2026-09-05ae — Inline generated-media display v1 (story stills)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05ae**.

Design: `docs/design_notes/INLINE_GENERATED_MEDIA_CHAT_2026-09-05.md`
(`CHANGELOG/2026-09-05x`). Task #49 v1.

## What shipped

Complete `story_image_job_status` / `render_story_image` manifests that
already name a file under `outputs/stories/_comfy_output/` now persist a
`media_artifacts` locator on the assistant message (root id, subfolder,
filename, sha256, bytes, prompt_id — **no file bytes, no absolute path**).
`GET /api/chat` already returns extra message keys, so restore needs no
new history route.

`GET /api/generated_media` (and the old `/api/story_image_file` alias)
re-resolves on every request. `_send` already sets `Cache-Control:
no-store`. Missing file → JSON **404** `{status: missing}`. sha256
mismatch after a regenerate/truncate on disk → JSON **409**
`{status: hash_mismatch}` and **does not** return the new bytes.
The GUI mounts via `fetch` + blob URL; 404/409 become “file missing” /
hash-mismatch copy instead of a broken `<img>`.

Allow-list: root ids `story_comfy` (`outputs/stories/_comfy_output/`) and
`story_output` (`outputs/stories/`). Candidate must stay under
`outputs/stories/` and is rejected if it falls under `uploads/`,
`chats/`, or `outputs/equal_shares/`. Unknown root ids (`uploads`,
`shared_output`, a raw path) return None.

`comfy_generate` enqueue payloads are not collected. No `/history/{prompt_id}`
poll. No video cards. No Equal Shares. No `tracing.py` dependency.

`APP_REVISION` / `$ExpectedAgentRevision`:
`2026-09-05-generated-media-v1-r77`.

## Tests

```
python -m unittest test_story_image_reveal test_launcher_revision -v
```

23/23 OK. Fail-closed:

- `test_uploads_chats_and_equal_shares_are_rejected` — even with
  `STORY_OUTPUT_ROOT` widened to the temp parent, locators into
  `uploads/`, `chats/`, and `equal_shares/` return None.
- `test_unknown_root_id_is_rejected` — `uploads`, `shared_output`, and a
  filesystem path as `root` return None.
- `test_hash_mismatch_returns_409_and_not_the_new_bytes` — after
  overwriting the PNG, GET with the stored sha256 is 409 JSON, not the
  new file.

Also: collect-from-complete-manifest; enqueue/start payloads empty;
missing 404; matching hash 200; persist + `/api/chat`-shaped load +
`truncate_after` drops the locator without re-rendering; existing
`resolve_story_image` / reveal suite held.

## Files

- `local_agent/server.py`
- `local_agent/static/index.html`
- `local_agent/START_LOCAL_AGENT_GUI.ps1`
- `local_agent/test_story_image_reveal.py`
- `TODO.md`
