# Design: inline generated-media display in chat

| Field | Value |
|---|---|
| **Document** | Viewable image/video cards on the originating assistant turn |
| **Date** | 2026-09-05 |
| **Status** | Scope only — do not build from this pass |
| **TODO** | `TODO.md` “Inline generated-media display in chat” |
| **Sibling** | Story-still preview `CHANGELOG/2026-08-31g`; activity-trace scope `VISIBLE_AGENT_ACTIVITY_TRACE_2026-09-05.md` |
| **Out of scope here** | Equal Shares H3 soundtrack/video pipeline; `media_queue` (that queue is **analysis** of existing files, not generation — live `done/` jobs are `kind: transcribe`); user-upload previews; Phoenix/tracing |

Preview is an extra UI reference. File path, checksum, manifest, and
`comfy_mcp_audit.jsonl` stay the evidence trail. The card must not replace
them.

---

## Overview

A slice of this already shipped for **one** pipeline: when
`story_image_job_status` / `render_story_image` returns a complete
manifest, `index.html` `addStoryImagePreviews()` appends an `<img>` to the
live tool card (`CHANGELOG/2026-08-31g`). That card dies on refresh
(`openChat` only `render(m.content)`). `comfy_generate` / `enqueue_workflow`
never get a card at all: they return `{status: "enqueued", prompt_id}` and
write into `ComfyUI-Shared\output` (`CHANGELOG/2026-09-04j`).

v1 is: persist a **safe, re-validated** media reference on the assistant
turn, serve bytes only from allow-listed roots, restore the card from
`/api/chat` without re-running ComfyUI, and show missing/deleted as a
plain unavailable state instead of a broken or cached image.

---

## What exists today (cited)

### Story stills (owned backend)

| Piece | Code | Notes |
|---|---|---|
| Job start | `tools.render_story_image` (`tools.py` ~1765–1939) | Background Popen; JSON `{started, pid, story, manifest_glob}`. **No file yet.** |
| Completion | `tools.story_image_job_status` (~1942–2007) | `state=complete` iff latest `outputs/stories/<story>/manifests/image_*.json` has `status: "complete"`. |
| Manifest outputs | e.g. `outputs/stories/night_greenhouse/manifests/image_a4e32fe6-….json` | `prompt_id`, full graph, `outputs: [{filename, subfolder, type}]`. **No checksum.** Real file is **not** under `outputs/stories/<story>/` — it is `outputs/stories/_comfy_output/<subfolder>/<filename>` (tool note ~1998–2002). |
| Security boundary | `server.resolve_story_image` (`server.py` ~80–107) | Filename = basename only; no `..` in subfolder; `resolve()` then `relative_to(STORY_IMAGE_ROOT)`; image suffix; file must exist. Else `None`. Tests: `test_story_image_reveal.py` (traversal, absolute path, non-image, missing). |
| Serve / reveal | `GET /api/story_image_file`, `POST /api/reveal_story_image` (`server.py` ~276–282, 176–194) | Bytes + `explorer /select,`. Loopback-only server. |
| Live GUI | `addStoryImagePreviews` (`index.html` ~446–483) | **Only** those two tool names. Parses `manifest.outputs` or a top-level manifest. `<img src="/api/story_image_file?...">` + folder button. Leaves the `<pre>` JSON in place. |
| Refresh | `openChat` (~392–395) | Content HTML only. No `tool_evidence`, no img. |
| Missing file | `resolve_story_image` → 404 (`server.py` ~279–280) | GUI has **no** `onerror`. Browser shows a broken image; that is a stale/failed preview, not an honest state. |

`render_story_image` tool_result with `started: true` has no `outputs`;
`addStoryImagePreviews` walks empty `outputs` and draws nothing — correct
(intention vs completion already matches the activity-trace rule).

### `comfy_generate` / MCP audit (shared Rockernow)

| Piece | Code | Notes |
|---|---|---|
| Wrapper | `tools.comfy_generate` (`tools.py` ~965–995) | MCP `generate_image`; default `action: "image"` (also controlnet / ip_adapter / **video** / 3d / upscale / remove_background / audio per docstring). |
| Return | Live `2026-09-04j` | `{status: "enqueued", prompt_id, queue_remaining, checkpoint}` — **not** a filename. |
| Audit | `_comfy_audit` → `runtime/comfy_mcp_audit.jsonl` (`tools.py` ~780–797, 982–993) | `ts`, `local_tool`, `mcp_tool`, `action`, `args`, `caller`, `prompt_id` or error. Investigator log. **No output path, no checksum, no conversation_id.** |
| Disk | `CHANGELOG/2026-09-04j` | `A:\Users\rhine\ComfyUI-Shared\output\ComfyUI_00214_.png`. History `/history/{prompt_id}` names SaveImage `filename`. Comfy `/view?filename=&type=output` is **ComfyUI's** HTTP, not the agent GUI. |
| `filename_prefix` | MCP 0.52.x limitation (`COMFYUI_MCP_INTEGRATION_PLAN.md` §4b) | Image/controlnet/ip_adapter/upscale **hardcode** `ComfyUI`. Do not fork the composer in `comfy_generate`. Probe isolation is `mcp_test_output.py` (`mcp_test/` subfolder). |
| `comfy_workflow` enqueue | `tools.comfy_workflow` (~997–1014) | Same shared output; **no** `_comfy_audit` on enqueue (audit is generate / irreversible / process). |
| `comfy_assets` `get_image` | `tools.comfy_assets` (~1017–1020) | MCP fetch; not a chat card. |

### Not generation (do not treat as this TODO)

- `media_queue`: transcribe / caption / extract on **existing** paths
  (`media_queue.py` docstring; sample `done/7efc9bb88ec04267.json` is
  `kind: transcribe`).
- User attachments: `server._upload` → `uploads/`; those are inputs.
- Equal Shares `outputs/equal_shares/**` and `start_current_chat_render`:
  paused specialist pipeline. MCP plan already forbids generate touching
  that tree.

### Persistence that almost helps

`store.append(..., meta={"tool_evidence": _tool_evidence})`
(`server.py` ~621–623). Evidence copies `path` / `file_changed` if those
keys exist on the tool JSON (`~556–559`). Story manifests use
`filename`/`subfolder`, **not** `path`, so `_tool_evidence` does not
currently carry a media locator. `/api/chat` returns the full conversation
object (`do_GET` ~290–292), so a new `media_artifacts` field on the
assistant message would ride the existing history API with no new route.

---

## Requirements, concretely

### 1. Persist a safe media-artifact reference on the assistant turn

Do **not** store bytes in `chats/{id}.json`. Store a locator the server can
re-check:

```json
{
  "media_artifacts": [
    {
      "kind": "image",
      "root": "story_comfy",
      "subfolder": "stories/night_greenhouse/renders",
      "filename": "20260901_001317_00001_.png",
      "sha256": "<hex of file at persist time>",
      "bytes": 317295,
      "prompt_id": "a4e32fe6-8cdb-4276-be02-d8d23a115eda",
      "local_tool": "story_image_job_status",
      "manifest_relpath": "outputs/stories/night_greenhouse/manifests/image_a4e32fe6-….json"
    }
  ]
}
```

`root` is an allow-list **id**, never a filesystem path in the JSON the
browser sends back. Server maps:

| `root` | Directory | Source pipeline |
|---|---|---|
| `story_comfy` | repo `outputs/stories/_comfy_output/` (`STORY_IMAGE_ROOT`) | `render_story_image` |
| `shared_output` | `A:\Users\rhine\ComfyUI-Shared\output` (from live Rockernow argv / `COMFYUI_PATH`) | `comfy_generate` / enqueue once history names a file |

Resolver: generalize `resolve_story_image(root, subfolder, filename)` —
same basename / `..` / `relative_to(root_dir)` / suffix / `is_file()`
rules. Video suffixes only when `kind=video` and the root allows them
(`MEDIA_EXTS` already lists `.mp4` etc. at `server.py` ~60–64; story
resolver currently **rejects** non-images ~103–104).

**When to attach (v1):** only when a tool_result **already names an
existing file** that resolves. That is `story_image_job_status` with
`state=complete` and `manifest.outputs`. Compute `sha256`/`bytes` from
the resolved path at persist time (`hashlib.sha256` of file bytes, or
first N MB + size if we later worry about huge video — v1 can hash
whole files for stills; for video hash + `bytes` is enough).

`comfy_generate` enqueue is **not** a card. Audit JSONL remains the
receipt that a generate was asked. Completing it needs history (below).

Keep the `<pre>` tool JSON and `comfy_mcp_audit.jsonl` untouched.

Server `push` on `tool_result` should also emit a small SSE
`kind: "media"` **after** resolve succeeds, so the live turn and the
stored meta stay in sync. New kind → `APP_REVISION` bump
(`server.py` ~55).

### 2. History API / restore without re-render

`GET /api/chat?id=` already returns messages including extra keys
(`store.load` returns the JSON as saved). `openChat` must, for each
assistant message, call a shared `renderMediaArtifacts(msg.media_artifacts)`
that builds the same card as the live `media` SSE handler.

Serving always goes through `GET /api/generated_media?root=&subfolder=&filename=`
(or keep `/api/story_image_file` as an alias of `root=story_comfy`).
**Re-resolve on every GET.** Do not embed `file://` or absolute paths in
HTML. Do not bake a data-URL into chat JSON.

Regenerate (`store.truncate_after`) drops later assistant rows and their
`media_artifacts` with them. A new answer only gets a card if tools run
again and resolve again. Tests must assert truncate does not leave a
card pointing at a dropped turn, and that restore does not call
`comfy_generate` / `render_story_image`.

### 3. Missing / deleted / unavailable — no stale preview

| Condition | Server | GUI |
|---|---|---|
| File gone | resolver `None` → **404** (already the story-image behavior) | `img.onerror` / `video.onerror` or a HEAD/GET that is not 200 → replace the card with “file missing (deleted or never written)” plus the stored `filename` / `prompt_id`. No broken-image icon. |
| File exists but `sha256` mismatch | 200 would be the **wrong** bytes (ComfyUI reused `ComfyUI_00214_.png` style names). Compare hash at GET; if mismatch return **409** or a JSON status, not the new bytes as if they were the original. | “file changed on disk since this turn; not showing a substitute.” Offer reveal-folder if the path still resolves. |
| Root/id unknown or path escapes allow-list | 404, never 200 | Same unavailable card. |
| Browser HTTP cache | Set `Cache-Control: no-store` on the byte route | Prevents a 200 PNG living in disk cache after a 404. |

Do **not** copy the PNG into `runtime/artifacts/` as a preview cache for
v1. That would become a second, stale store. `artifacts.py` is a context
boundary for tool **text**, not a media CDN (`artifacts.py` docstring).

### 4. Security boundary

Untrusted inputs: model-chosen `story` slug, MCP history filenames,
anything in tool JSON. Trusted: allow-listed root dirs in server code.

Must keep (from `test_story_image_reveal.py` + extend):

- no `..` in subfolder; filename is `Path.name` only
- `resolve().relative_to(root)`
- suffix allow-list (image vs video vs reject `.txt` / `.py` / no suffix)
- missing file → None
- **absolute Windows path as filename** rejected (already tested)
- **root id not in the table** rejected
- path under `uploads/`, `chats/`, `outputs/equal_shares/`, home, or
  `ComfyUI-Shared\input` rejected even if the JSON says `filename`

Do not proxy ComfyUI `/view` with an operator-supplied `filename` that
skips `relative_to`. Do not spawn `explorer` except through the same
resolver (`reveal_story_image` already does this).

Desktop bind `127.0.0.1` is necessary but **not** sufficient — the
resolver is the boundary (`2026-08-31g` “Why the path validation is this
strict”).

### 5. Video card

v1 video = `kind=video` + `shared_output` (or story root if a later
manifest grows video outputs). `<video controls src=...>` ; duration:
omit unless already in the manifest (story manifests have none).
Open-file = same reveal helper with video suffixes allowed.
Do not transcode. Do not play Equal Shares `.mp4` from `good audio\`.

---

## `comfy_generate` plumbing vs new work

Already available:

- `prompt_id` on MCP return and audit JSONL
- `/history/{prompt_id}` (and `comfy_system` `get_history`) naming
  SaveImage/SaveVideo files
- Shared output directory from the live backend
- Caller/args audit for “which turn asked for a mug”

**Not** available:

- conversation_id on the audit row
- output filename at `tool_result` time (enqueue races the GPU)
- checksum
- any GUI hook for `comfy_generate` (`addStoryImagePreviews` early-returns)

v1 **does not** background-poll ComfyUI to attach a card to the enqueue
turn. That is a follow-up: either a later `story_image_job_status`-shaped
`comfy_job_status(prompt_id)` tool whose complete result carries
`outputs[]`, or a small watcher that emits `media` SSE when history
succeeds. Until then, operator generate via MCP remains path+prompt_id in
prose/audit only — honest, not a fake thumbnail.

Optional small v1 add: when `get_history` / a future status tool returns
outputs and the files resolve under `shared_output`, persist
`media_artifacts` the same way as story stills.

---

## Suggested PR cut (when authorized)

**v1 (ship)**

1. Generalize `resolve_story_image` → `resolve_generated_media(root, subfolder, filename, kinds=)`.
2. Persist `media_artifacts` on `store.append` from **complete story
   manifests only**; sha256+bytes at persist; SSE `media` for the live
   turn.
3. `openChat` restores cards; byte GET re-resolves; 404/hash-mismatch →
   unavailable copy; `Cache-Control: no-store`.
4. Tests: existing reveal suite plus outside-root, video suffix rejected
   on image-only root, missing file, hash mismatch, truncate/regen, GUI
   contract that `/api/chat` includes `media_artifacts` and never includes
   an absolute path the browser could fetch as `file://`.
5. `APP_REVISION` bump (new GET + SSE kind).

Keep JSON `<pre>`, manifests, and `comfy_mcp_audit.jsonl` as-is.

**Not v1**

- Poll `/history/{prompt_id}` after `comfy_generate` enqueue
- Copy files into `runtime/artifacts/`
- Equal Shares / `media_queue` / user uploads
- Duration via ffprobe
- Data-URL embedding
- Waiting on `tracing.py`

**v2**

- `comfy_job_status(prompt_id)` + `shared_output` cards for
  image **and** video MCP actions
- `conversation_id` on `_comfy_audit` extra (helps join mug-image mixups;
  tracing PR 4 is the investigator join — UI still must not require
  `traces.db`)
- Hash-mismatch UX + reveal

---

## Acceptance mapped to live code

| TODO acceptance | Hook |
|---|---|
| Completed image job | `story_image_job_status` `state=complete` + `manifest.outputs` |
| Completed video job | **v2** unless a status tool already returns a video `outputs[]` under an allow-listed root |
| Refresh / persistence | `media_artifacts` on assistant message + `/api/chat` + re-resolve GET |
| Regenerated answers | `truncate_after` drops the row; no re-render |
| Path outside allow-listed roots | resolver `None`; test with `uploads/` and `equal_shares/` |
| Honest missing | 404 + card text; no `<img>` left pointing at a 404 |
| Evidence trail preserved | tool `<pre>` + manifest on disk + audit JSONL unchanged |
