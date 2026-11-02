# LocalAIproject

Locally run AI agent project.

## Tools available to the agent

### image-blaster (image -> 3D world, 3D models, sound effects)

Location: `tools/image-blaster/` (cloned by `scripts/setup-image-blaster.*`; not committed here).
Upstream: https://github.com/neilsonnn/image-blaster (MIT).

Use the `image-blaster` skill in `.claude/skills/image-blaster/SKILL.md` whenever the user wants to
turn an image into a 3D environment, 3D object meshes, or sound effects ("blast", "image-blast",
"make a 3D world from this picture", etc.).

Key rules:
- If `tools/image-blaster/` does not exist, run `bash scripts/setup-image-blaster.sh`
  (Windows: `powershell -ExecutionPolicy Bypass -File scripts\setup-image-blaster.ps1`).
- Every image-blaster script must be run with the working directory set to `tools/image-blaster/`
  (its scripts use paths like `.claude/scripts/...`, `worlds/`, `input/`).
- API keys live in `tools/image-blaster/.env` (`WORLD_LABS_API_KEY`, `FAL_KEY`). Never print them,
  never commit them, never paste them into chat output.
- Generation costs real money on World Labs / FAL. Confirm with the user before starting a
  generation unless they explicitly asked for a one-shot blast.
- On Windows, image-blaster CLIs need the local entry patch from
  `scripts/patch-image-blaster-windows-entry.mjs` (the setup script runs it). Upstream
  compares `import.meta.url` to `file://` plus `process.argv[1]`, which does not match
  `A:\...` paths. See `docs/IMAGE-BLASTER.md`.
- User guide: `docs/IMAGE-BLASTER.md`.
