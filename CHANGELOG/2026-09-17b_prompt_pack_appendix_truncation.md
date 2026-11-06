# 2026-09-17b — Prompt-pack parser truncates global appendix/footer sections

## What changed

- Updated `local_agent/managed_prompt_pack.py`.
- `parse_clips()` now truncates prompt-pack source text before global appendix/footer sections before splitting clip records.
- This prevents trailing sections such as `## Dialogue Tone`, `## Generation Notes`, `## Story Rules`, `## APPENDIX`, or `### Character Bible` from being captured as part of the final clip's video prompt.

## Why

The Backrooms Sitcom Prompt Pack diagnostic parsed all 102 clips and validated structurally, but `C102.video_prompt` bled into the following global `## Dialogue Tone` section. The parser needed a footer boundary before clip parsing.

## Scope

- No ingestion/export files were written.
- No render, model load, ComfyUI job, PowerInfer work, or registry change was started.
