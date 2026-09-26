# 2026-08-24 — Chat-to-render-job bridge

## What changed

- `local_agent/chat_render_jobs.py` added a deterministic bridge from a desktop
  conversation to a fresh batch-render job.
- `local_agent/tools.py` added `prepare_chat_render` and
  `start_current_chat_render`.
- `local_agent/server.py` now passes the server-selected conversation ID into
  desktop tool dispatch; the model cannot select a different chat.
- `local_agent/agent.py` instructs a folderless “render it” request to use the
  current-chat action, instead of inventing a folder.
- `local_agent/remote_security.py` keeps both actions default-deny for phone
  identities.
- `local_agent/test_chat_render_jobs.py` added a source-preservation regression.

## Why

The user had already supplied images, a chunk directory, and generated prompts
inside one chat, but `batch_render_folder.py` only accepted a manually assembled
`prompts/`, `img0/`, `img1/`, and `video_refs/` directory. Pointing it at an
output folder correctly found zero prompts, but imposed unnecessary setup.

## Behavior and safeguards

The bridge uses the **latest complete fenced prompt set** in that same desktop
chat, the two earlier attached images, and the first earlier folder containing
video chunks. It creates a timestamped job beneath `local_agent/render_jobs/`;
sources are copied with metadata and never moved, renamed, or overwritten.

The exact imperative `start render` is deterministic: it bypasses model tool
selection and invokes the current-chat bridge. A long or compacted chat therefore
cannot revive the former documentation-path example.

It translates only the old zero-based `<Image 0..2>` labels to native
`<Picture 1..3>` labels, declares missing picture references, and removes old
arbitrary video numbering so the established batch runner can inject its one
real `<Video 1>` socket mapping. Every prompt is validated after that injection;
an incomplete trailing model draft is skipped, not rendered. If no valid prompt
remains, the start is refused. Existing queue, port, thermal, and output
protections remain in `start_batch_render` and the runner.

## Evidence and verification

- `python local_agent\\test_chat_render_jobs.py` passed **1/1**: source image
  stayed intact; two valid prompts and naturally sorted video copies were made;
  one incomplete prompt was skipped.
- `python local_agent\\test_native_tool_calling.py` passed **16/16**, including
  verification that the server replaces a model-supplied chat ID with the active
  desktop conversation ID and that exact `start render` never reaches model
  folder selection.
- `python local_agent\\validate_h3_prompt.py --dir
  outputs\\equal_shares\\prompts_native_r2v` still reports **124/124 valid**.

## Still unverified

No real job was prepared or rendered from an operator conversation in this
change. A real launch must still be audited from its runner log and output
metadata; document agreement and prompt validation do not prove render quality.
