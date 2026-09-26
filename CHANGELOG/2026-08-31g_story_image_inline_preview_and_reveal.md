# 2026-08-31 — show generated story images inline in chat, with an Open Folder button

## What the operator asked for

After `render_story_image`/`story_image_job_status` were built (`2026-08-31f`),
the operator asked for two GUI conveniences on top: being able to see the
generated image directly in the chat, and a way to open a File Explorer
window at the image's actual location, rather than reading a raw JSON
manifest and finding the file by hand.

## What changed

**`local_agent/server.py`:**

1. `STORY_IMAGE_ROOT` — the one shared root `work/image_render.py`'s owned
   ComfyUI backend writes every general-story still under
   (`outputs/stories/_comfy_output/`).
2. `resolve_story_image(subfolder, filename)` — the single security boundary
   for this feature. Takes the `{filename, subfolder}` pair straight out of
   a render manifest (the same shape ComfyUI's own `SaveImage` node reports)
   and returns a real `Path` only if: the filename has no directory
   component of its own, the subfolder has no `..` segment, the resolved
   path still lands inside `STORY_IMAGE_ROOT` (checked again after
   resolution as defense in depth), the extension is an actual image type,
   and the file exists. Anything else returns `None`. This function is the
   only thing standing between a JSON blob and both serving raw bytes over
   HTTP and spawning a real Windows process, so every rejection path was
   written and tested as carefully as the success path.
3. `GET /api/story_image_file?subfolder=...&filename=...` — serves the
   resolved file's bytes with the right image content-type, or 404.
4. `reveal_story_image(subfolder, filename)` / `POST /api/reveal_story_image`
   — resolves the same way, then runs `explorer /select,<path>` on Windows
   only (refused elsewhere) via `subprocess.Popen`. This server only ever
   binds `127.0.0.1` (see the module docstring), so this route was already
   desktop-only by construction before this change — nothing remote can
   reach it.
5. Bumped `APP_REVISION` again (`...-story-image-preview-r67`) and the
   matching `$ExpectedAgentRevision` in `START_LOCAL_AGENT_GUI.ps1`, so the
   next launcher run replaces the running process automatically — the same
   self-repair mechanism used for `2026-08-31f`.

**`local_agent/static/index.html`:**

Tracks the name of the most recently started tool call (`lastToolName`) in
the existing streaming-event handler. When a `tool_result` event arrives for
`story_image_job_status` or `render_story_image`, `addStoryImagePreviews()`
parses the JSON, walks `manifest.outputs` (or the top-level object if it's
already a manifest), and for each output with a `filename` appends an
`<img>` pointed at `/api/story_image_file?...` plus an "Open containing
folder" button that POSTs to `/api/reveal_story_image`, alongside the raw
JSON `<pre>` block that was already being shown (nothing removed, just
added to). Any other tool's result is untouched — this never guesses a path
from arbitrary tool output, only from the two tools whose JSON shape is
actually a render manifest.

## Why the path validation is this strict

This is the first place in the local agent where a tool result's JSON
directly drives both a file read served over HTTP and a spawned OS process.
Every other subprocess call in this codebase (`tools.py`'s batch-render
launch, `stop_all_comfyui`, etc.) either uses fixed, hardcoded arguments or
values that were themselves validated earlier in the same call chain — none
of them take a `{subfolder, filename}` pair sourced from a JSON blob that,
somewhere upstream, ultimately reflects the model's own tool-call arguments
(the `story` slug in `render_story_image`). `resolve_story_image` treats
that provenance as untrusted all the way through: no directory components
in the filename, no `..` in the subfolder, and a final `relative_to()`
check against the root regardless of what the first two checks already
caught.

## What was verified

- `python3 -m py_compile server.py test_story_image_reveal.py` — clean.
- `node -e "new Function(...)"` over the extracted `<script>` block in
  `static/index.html` — confirms no JS syntax error was introduced.
- New `test_story_image_reveal.py`, 12 tests: valid file resolves; empty
  filename, directory traversal via filename, directory traversal via
  subfolder, an absolute-path filename, a non-image extension, and a
  nonexistent file are all rejected; an empty subfolder (top-level file) is
  allowed; `reveal_story_image` never calls `subprocess.Popen` for a missing
  or rejected path, calls it with `explorer`/`/select,`/the resolved
  absolute path for a valid one only when the platform flag is Windows, and
  is refused (without spawning anything) when it isn't.
- `test_launcher_revision` still passes — `APP_REVISION` and
  `$ExpectedAgentRevision` remain in lockstep.
- Full regression sweep: `test_launcher_revision`, `test_story_image_reveal`
  (12), `test_yield_gpu`, `test_status_cache`, `test_ctx_ceiling`,
  `test_native_tool_calling` (43), `test_render_story_image` (18),
  `test_story_image_plan` (5), `test_router_switching` (41),
  `test_subtask_dispatch` (8), `test_retrieval_relevance` (4) — 134 tests
  total, 0 failures, 0 errors. (`test_media_gpu_queue`'s
  `test_interactive_priority_is_fifo_and_precedes_batch` was seen to fail
  once during this sweep; reproduced it failing intermittently in isolation,
  unrelated to any file this change touches — a pre-existing timestamp-
  ordering flake, not a regression from this work.)

## What is still unverified

Not yet opened in a real browser against the real server — the JS was only
syntax-checked, not exercised against a live `tool_result` event or a real
rendered PNG. Needs the same real end-to-end pass already pending for
`render_story_image` itself: request an image, let it actually render, and
confirm the thumbnail appears inline and "Open containing folder" opens the
right Explorer window.
