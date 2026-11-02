---
name: image-blaster
description: Turn an image into a 3D explorable world (Gaussian splat), 3D object meshes (.glb/.obj) and sound effects using the image-blaster toolkit in tools/image-blaster. Use when the user asks to "blast" an image, make a 3D world/scene/level from a picture, extract 3D models from a photo, or generate SFX for a scene.
argument-hint: [image path or world name] [instructions]
---

# image-blaster bridge

image-blaster lives in `tools/image-blaster/`. It is its own Claude Code project with its own skills
(`image-blast-project`, `-uncover`, `-plate`, `-world`, `-3d`, `-sfx`, `-image-edit`, `-wildcard`),
subagents, hooks and rules (`tools/image-blaster/.claude/`). Those only load fully when Claude Code is
started **inside** that folder.

## 1. Make sure it is installed

```bash
ls tools/image-blaster/.claude/skills
```

If that fails, run `bash scripts/setup-image-blaster.sh` (Windows PowerShell:
`powershell -ExecutionPolicy Bypass -File scripts\setup-image-blaster.ps1`).

Check keys without printing them:

```bash
cd tools/image-blaster && CLAUDE_PROJECT_DIR="$PWD" bash .claude/hooks/setup-check.sh
```

If keys are missing, ask the user to paste them into `tools/image-blaster/.env`
(World Labs: https://platform.worldlabs.ai/ , FAL: https://fal.ai/). Do not echo key values.

## Windows entry patch

On Windows, run `node scripts/patch-image-blaster-windows-entry.mjs tools/image-blaster` from the
LocalAIproject root if a `node .claude/scripts/...` command exits 0 with no output. Upstream starts
those CLIs only when `import.meta.url` equals `file://` plus `process.argv[1]`, which does not match
Windows paths. The setup script applies this patch. Do not commit the patched files. Details:
`docs/IMAGE-BLASTER.md`.

## 2. Pick a mode

**Interactive (preferred, full pipeline with check-ins):** tell the user to run

```bash
cd tools/image-blaster
claude
```

then drop an image in `input/` and say `blast it and confirm each step with me`.

**Headless (when the user wants you to drive it from here):** stage the image and launch a nested
Claude Code session inside the folder:

```bash
cp "<image path>" tools/image-blaster/input/
cd tools/image-blaster && claude -p "blast the image in input/ in one-shot as world <slug>. report the output paths and viewer URL when done."
```

Headless mode cannot pause for confirmations, so get the user's go-ahead (it spends API credits) first.

**Single step / scripted:** the generation scripts are plain Node CLIs. Always run them from
`tools/image-blaster/`. Read the matching `tools/image-blaster/.claude/skills/<skill>/SKILL.md`
for exact flags before calling one:

| Step | Script |
|------|--------|
| create/inspect project, stage `input/` | `node .claude/scripts/project/project-state.mjs --world <slug> --stage-input` |
| clean plate / image edit | `node .claude/scripts/image-edit/generate-edit.mjs ...` |
| 3D world (World Labs Marble) | `node .claude/scripts/world/generate-world.mjs --world <slug> --prompt "<caption>"` |
| 3D object (Hunyuan via FAL) | `node .claude/scripts/asset-pipeline/generate-single-asset.mjs --world <slug> --object-id <id> --image-edit-prompt "..."` |
| sound effect (ElevenLabs via FAL) | `node .claude/scripts/sfx/fal-elevenlabs-sfx.mjs ...` |
| re-download missing files | `node .claude/scripts/project/ensure-local-assets.mjs --from <request-json>` |

These scripts block until the API call finishes; do not background them.

## 3. Viewing results

```bash
cd tools/image-blaster && bun run dev
```

Then open http://localhost:5173 (or `node .claude/scripts/project/show-url.mjs <slug>` for the exact
route). Outputs are under `tools/image-blaster/worlds/<slug>/output/`.
