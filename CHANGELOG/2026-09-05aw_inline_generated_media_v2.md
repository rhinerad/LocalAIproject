# 2026-09-05aw — Inline generated-media display v2 (comfy_job_status + video)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05aw**.

Follow-on to v1 (`CHANGELOG/2026-09-05ae`). Design:
`docs/design_notes/INLINE_GENERATED_MEDIA_CHAT_2026-09-05.md` v2 cut.

## What shipped

`comfy_job_status(prompt_id)` polls ComfyUI **HTTP** `/history/{prompt_id}`
(not MCP — an in-flight generate holds the MCP lock). Bounded:

| | |
|---|---|
| Default budget | **90 s** |
| Cap (`timeout_s`) | **300 s** |
| Per-request HTTP | 2 s |
| Backoff | 0.5 s, doubles, cap 5 s |
| `timeout_s=0` | single snapshot, no sleep |

Returns `state=complete` with `outputs[]` (`filename` / `subfolder` /
`type=output` only), `state=pending` if still running at the deadline
(call again; GUI shows a pending card, not a broken `<img>`), or
`state=error`. Does not invent paths. `comfy_generate` enqueue is still
not collected.

Allow-list root id **`shared_output`** → `ComfyUI-Shared/output` (same
`EQUAL_SHARES_COMFYUI_PATH` default as mcp_client). Story roots stay
**image-only**. Forbidden still: `uploads/`, `chats/`,
`outputs/equal_shares/`, plus Shared **input**. GET re-resolves; missing
404; hash mismatch 409 (does not serve the new bytes). Video suffixes
(`.mp4` etc.) served as `video/*` with a local `<video controls>` card,
HTML5 duration, and the same reveal helper (now takes `root`).

`APP_REVISION` / `$ExpectedAgentRevision`:
`2026-09-05-generated-media-v2-r78`.

## Tests

```
python -m unittest test_story_image_reveal test_comfy_tools test_launcher_revision
```

**66/66 OK.**

Fail-closed / v2 cases:

- completed `comfy_job_status` → `shared_output` locator + 200 PNG
- still-running / timeout → pending locator, empty filename, no broken card
- `comfy_generate` enqueue still not collected
- video on Shared: 200 `video/mp4`; overwrite → 409, new bytes not shown
- Shared output rejects uploads / chats / equal_shares / Shared input
- story root still rejects `.mp4`
- poller: complete without MCP; empty history + `timeout_s=0` pending;
  backoff then complete; `timeout_s` capped at 300

## Live verify

8188 was **closed** this pass (no live `/history` poll). Offline parse of
the 2026-09-04j history JSON
(`comfy_history_8182b9d1.json`) → `state=complete`,
`ComfyUI_00214_.png`. That file is still on disk:
`A:\Users\rhine\ComfyUI-Shared\output\ComfyUI_00214_.png`, **317295**
bytes (matches 2026-09-04j). `collect_comfy_media_artifacts` +
`generated_media_payload` → 200 `image/png`, sha256
`13b30749c91fab4afce711c873e3225caa5ea21cf286725ef76c96d95cd64660`.

## Files

- `local_agent/tools.py` — `comfy_job_status`, history parse, bounded poll
- `local_agent/server.py` — `shared_output` root, video ctypes, collect,
  reveal-by-root, APP_REVISION
- `local_agent/static/index.html` — pending card, video player + duration,
  reveal `root`
- `local_agent/START_LOCAL_AGENT_GUI.ps1`
- `local_agent/test_story_image_reveal.py`
- `local_agent/test_comfy_tools.py`
- `TODO.md`
