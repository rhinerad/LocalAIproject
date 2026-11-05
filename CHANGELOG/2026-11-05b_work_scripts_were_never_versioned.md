# 2026-11-05b — `work/` was git-ignored wholesale, so the project's own tooling was never versioned

Found while chasing the launcher exit in `CHANGELOG/2026-11-05a`. Branch
`claude/jolly-dirac-9impbq`. Id claimed with `scripts/next_changelog_id.py`.

## 1. What is wrong

`.gitignore` line 106 listed `work/` under "Runtime/staging directories
(external clones, GPU scratch, temp work)". But `work/` is where this project
keeps its tooling, not scratch:

- `CLAUDE.md` names `work/thermal_guard.py`, `work/duration_ladder.py`,
  `work/render_audio_pass.py`, `work/validate_audio_take.py`,
  `work/classify_voice_requirements.py`, `work/build_native_r2v_prompts.py`,
  `work/audit_equal_shares_completion.py` and more as the implementations of
  its binding rules.
- `local_agent/router.py` (`thermal_blocks_gpu`), `tools.py`,
  `media_tools.py`, `chat_render_jobs.py`, `prompt_pack_production.py`,
  `motion_transfer*.py` and `gvd_judge_eval.py` all insert `ROOT / "work"`
  on `sys.path` and import from it at call time.

`git log --all -- 'work/*'` is empty: no commit has ever contained a `work/`
file. The scripts exist only on the workstation's original checkout. Every
fresh clone or worktree, including the gateway worktree
`..\COMFYUI_STORY_HANDOFF_gateway` and this cloud session, has no `work/`
directory at all. That is the literal cause of the "missing
`work/thermal_guard.py`" errors recorded in `2026-11-04a` section 3, and it
means any agent code path that reaches the thermal guard, batch rendering, or
chat render jobs fails in the worktree while working in the main checkout.

## 2. Change

`.gitignore`: `work/` becomes `work/*` followed by `!work/*.py`, `!work/*.ps1`
and `!work/*.md`. The directory's contents stay ignored by default, the
top-level scripts and notes are re-included, and `work/runtime/` plus any data
subfolder remain ignored. Proven in a throwaway repository with this exact
`.gitignore`: `work/thermal_guard.py`, `work/notes.md` and `work/run.ps1` are
reported as untracked (addable), while `work/big.safetensors`,
`work/runtime/image_render_owner.json` and `work/data/x.bin` stay ignored
(`git check-ignore -v`).

Nothing is added by this commit, because the files are not in this
environment. **The workstation must add them once**, from the gateway
worktree, taking the files from the main checkout where they live:

    REM from ..\COMFYUI_STORY_HANDOFF_gateway, after pulling this commit
    robocopy ..\COMFYUI_STORY_HANDOFF_2026-08-09\work work *.py *.ps1 *.md /LEV:1
    dir work | findstr /i "\.py \.ps1 \.md"
    git add work
    git status --short work
    git commit -m "Version the work/ tooling that CLAUDE.md and local_agent import"
    git push -u origin claude/jolly-dirac-9impbq

Before the `git add`: check that no top-level `work/*.py|ps1|md` is larger
than 1 MB (`dir work /o-s`) and that none embeds a credential
(`findstr /i /m "api_key password secret token=" work\*.py`). Anything that
trips either check is reported, not committed. `/LEV:1` copies only the top
level; subfolders (runtime state, scratch data) are left behind on purpose.

## 3. Effect once added

- `test_router_switching` / `test_router_status_busy` lose their two
  `ModuleNotFoundError: thermal_guard` ERRORs in the worktree. The 12 FAILs
  driven by the machine-wide `EQUAL_SHARES_PRIMARY_REASONING_MODEL` override
  are a separate matter and are still not addressed.
- The gateway worktree becomes a faithful environment for the launcher
  reproduction in `2026-11-05a` section 3, instead of one missing the thermal
  guard the router calls on heavy-logic turns.

## 4. Unverified

- The contents and sizes of the workstation's `work/` directory are unknown
  here; the size and credential checks above are the gate.
- Whether anything under `work/` needs to live in a subfolder that is still
  ignored (a package rather than flat scripts). If `git status` after the
  copy shows a script the agent imports still missing, report it and extend
  the negation for that path only.
