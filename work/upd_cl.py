from pathlib import Path
p = Path("CHANGELOG/2026-09-06k_specialist_tool_allowlist_on_confirmation.md")
t = p.read_text(encoding="utf-8")
extra = """

## Live verification (DuranGamingPC)

1. Restarted `local_agent/server.py`; `/api/status` reports
   `APP_REVISION=2026-09-06-specialist-tool-confirm-r90`. `:8188` closed; GPU idle.
2. `/api/regenerate` on chat `5404c50e34aa4e53` (last user text `proceed`):
   `render_story_image` **was invoked** (no longer
   `stale specialist-project tool selection blocked`). Model omitted `prompt`
   on regenerate → `ERROR: prompt is required` — guard fix confirmed; args
   still model-dependent on that path.
3. `/api/action` `render_story_image` smoke (`model_profile=realpro_flux`,
   story `vhs_liminal_space_story`, clip1-start prompt) returned
   `ERROR: GPU permission pending in the sidebar; approve the image render once, then retry`.
   Pending gate id: **`gpu_a38b751666c5`**
   (`workload=ComfyUI still-image render`, `key=image_render:vhs_liminal_space_story`).
   Also pending unrelated chat load: `gpu_37d6fee2add9`.
   Waiting on operator sidebar approval — not auto-approved.
"""
if "Live verification" not in t:
    p.write_text(t.rstrip() + "\n" + extra, encoding="utf-8")
    print("changelog live section added")
else:
    print("already had live section")
