# 2026-09-24z — adopted the orphaned run-2 verify PNG into a manifest

## What

Wrote `outputs/stories/startup-deadline-fix-verify/manifests/image_09a1f706-5421-4549-8c2c-80afa926d66d.json`
for `outputs/stories/_comfy_output/stories/startup-deadline-fix-verify/renders/bfa0d801c89941669f1a1586a6195c7b_00001_.png`
(written 19:14:32 local; sha256 `f57b9afdd6cb71a934e0654ef22c8bdf19b0cc62ced19e122af6a28eb6d4350f`).
That render finished, but `image_render.py` had already exited 2 on the
`/history` timeout fixed in `2026-09-24w`, so no manifest was written. No
existing file was modified; the PNG and the run-1 manifest are untouched.

## How the record was reconstructed

- `prompt_id` `09a1f706-…` comes from the failed run's own error line
  (`work/runtime/agent_image_jobs/startup-deadline-fix-verify_run2_20260924_185909.log`);
  its backend (`comfy_20260924_185910_757374.stderr.log`) received exactly one
  prompt and logged `Prompt executed in 00:12:16`.
- `graph` is the ComfyUI prompt embedded in the PNG's metadata, meaning the
  graph that actually ran. Seed 2 and attempt prefix `bfa0d801…` come from it.
- CLI args were reconstructed: seed, size, steps and profile from the embedded
  graph; the negative prompt and the remaining args match the run-1 manifest.
  `ir.build_graph(...)` applied to those args reproduces the embedded graph
  exactly (asserted). The negative prompt cannot be confirmed from the graph,
  because the `realpro_flux` graph does not use it.
- Record built with the current `ir.manifest()`, so it uses the
  effective-settings format from `2026-09-24x` (top-level effective values plus
  `requested`). Status `complete`, `verified_outputs` with sha256, plus an
  `adopted_orphan` block holding this provenance. `created_at` is the adoption
  time; the block records the PNG's real write time.
- Corroboration: the PNG is pixel-identical to the 19:21 live verify render
  (`history-poll-fix-verify`, same args, seed 2). The 4-byte file-size
  difference is the story-name length inside the embedded save prefix.

## Correction during the session

The first write put a carriage return in `outputs[0].subfolder` (`\r` from
`\renders`): Git Bash collapsed `\\` inside the heredoc before Python saw it.
Within a minute, the same session rewrote that one field of the just-created
file using `os.sep`. Verified afterwards: the path resolves to the PNG, the
sha256 matches, and there is no CR in the file.
