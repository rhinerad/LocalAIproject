from pathlib import Path
p = Path("GROK_STATUS.md")
t = p.read_text(encoding="utf-8")
old = """Tests: test_native_tool_calling **101/101**.

## Previous (2026-09-06 evening ET, Grok)

Fixed photos/flux"""
new = """Tests: test_native_tool_calling **101/101**.
Live: regenerate on 5404c50e34aa4e53 ran render_story_image (no stale-tool block;
model omitted prompt). /api/action Flux smoke pending sidebar gate
**gpu_a38b751666c5** (image_render:vhs_liminal_space_story) — not auto-approved.
Also pending chat load gpu_37d6fee2add9. No PNG yet.

## Previous (2026-09-06 evening ET, Grok)

Fixed photos/flux"""
if old not in t:
    raise SystemExit("GROK_STATUS anchor missing")
p.write_text(t.replace(old, new, 1), encoding="utf-8")
print("GROK_STATUS live note added")
todo = Path("TODO.md")
tt = todo.read_text(encoding="utf-8")
if "gpu_a38b751666c5" not in tt:
    tt = tt.replace(
        "- [x] revision 2026-09-06-specialist-tool-confirm-r90; changelog 2026-09-06k\n",
        "- [x] revision 2026-09-06-specialist-tool-confirm-r90; changelog 2026-09-06k\n"
        "- [ ] WAITING operator sidebar approve **gpu_a38b751666c5** then retry Flux smoke PNG\n",
        1,
    )
    todo.write_text(tt, encoding="utf-8")
    print("TODO wait note added")
