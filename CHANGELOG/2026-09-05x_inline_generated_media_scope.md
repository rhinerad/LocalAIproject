# 2026-09-05x — Inline generated-media display in chat: scope only

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05x**.

Task #49. Design note only — no GUI, SSE, or `APP_REVISION` change.

Doc: `docs/design_notes/INLINE_GENERATED_MEDIA_CHAT_2026-09-05.md`.

## Finding

Live stills from `render_story_image` / `story_image_job_status` already
get an `<img>` on the tool card (`2026-08-31g`,
`resolve_story_image` + `/api/story_image_file`). That preview is
session-only (`openChat` ignores it), has no missing-file UI, and does
not cover `comfy_generate`. MCP generate returns `{status: enqueued,
prompt_id}` and writes `ComfyUI-Shared\output`; `comfy_mcp_audit.jsonl`
stores caller/args/`prompt_id`, not a path or checksum.

v1: persist `media_artifacts` (root id + subfolder + filename + sha256)
on the assistant turn from **complete story manifests only**, restore via
existing `/api/chat`, re-resolve on every byte GET, 404/hash-mismatch →
honest unavailable. Do not poll history after enqueue in v1. Do not
serve Equal Shares or arbitrary paths. Preview does not replace
manifest/audit/JSON.

No production code changed.
