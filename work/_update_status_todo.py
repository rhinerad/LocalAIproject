from pathlib import Path

# GROK_STATUS
p = Path("GROK_STATUS.md")
t = p.read_text(encoding="utf-8")
header = """# Grok status note for ChatGPT / Codex

## Current (2026-09-06 evening ET, Grok)

Fixed stale specialist-project **tool** block on confirmation turns.
`specialist_scope` now includes `_pending_specialist_continuation(history)`
(offer prose + successful prior `plan_story_image` tool_evidence), so
operator `proceed` / `yes` after an image plan can run `render_story_image`.
Real stale-H3 protection kept. APP_REVISION=2026-09-06-specialist-tool-confirm-r90.
Evidence: CHANGELOG/2026-09-06k_specialist_tool_allowlist_on_confirmation.md.
Tests: test_native_tool_calling **101/101**.

## Previous (2026-09-06 evening ET, Grok)

"""
if not t.startswith("# Grok status note"):
    raise SystemExit("unexpected GROK_STATUS header")
# replace first Current section by splicing after title
rest = t.split("\n", 1)[1]
# drop old Current until previous Previous marker content - simplest: prepend new Current
# Find old "## Current" and rename it by inserting before it
idx = t.find("## Current (")
if idx < 0:
    raise SystemExit("no Current section")
# Keep everything from old Current onward as Previous content (already labeled)
body_from_old_current = t[idx:]
# Rename first Current -> keep as Previous by our new header already saying Previous for the flux one
# Actually old starts with ## Current ... flux. Our new header includes ## Previous for that.
# So strip the first "## Current (...)" line from body and keep rest.
lines = body_from_old_current.splitlines(True)
# skip first line (## Current ...) and maybe blank? Keep from line 0 renamed:
# Better approach: insert new Current before old Current, then rename old Current to Previous
old = t
new_current = """## Current (2026-09-06 evening ET, Grok)

Fixed stale specialist-project **tool** block on confirmation turns.
`specialist_scope` now includes `_pending_specialist_continuation(history)`
(offer prose + successful prior `plan_story_image` tool_evidence), so
operator `proceed` / `yes` after an image plan can run `render_story_image`.
Real stale-H3 protection kept. APP_REVISION=2026-09-06-specialist-tool-confirm-r90.
Evidence: CHANGELOG/2026-09-06k_specialist_tool_allowlist_on_confirmation.md.
Tests: test_native_tool_calling **101/101**.

"""
# Replace the first "## Current (" occurrence title only to Previous, then insert new Current after title line
first = t.find("## Current (")
second_nl = t.find("\n", first)
title_line = t[first:second_nl]
# Insert new current before first Current, and rename first Current title to Previous
renamed = title_line.replace("## Current (", "## Previous (", 1)
t2 = t[:first] + new_current + renamed + t[second_nl:]
p.write_text(t2, encoding="utf-8")
print("GROK_STATUS updated")

# TODO
todo = Path("TODO.md")
tt = todo.read_text(encoding="utf-8")
block = """## Grok 2026-09-06k — specialist tool allowlist on confirmation (DONE)

- [x] specialist_scope OR _pending_specialist_continuation for tool allowlist
- [x] plan_story_image tool_evidence / prepared-plan prose counts as pending
- [x] test: proceed after plan allows render_story_image; stale H3 still blocked
- [x] revision 2026-09-06-specialist-tool-confirm-r90; changelog 2026-09-06k

"""
if "2026-09-06k" not in tt:
    # insert after title
    if tt.startswith("# TODO\n"):
        todo.write_text("# TODO\n\n" + block + tt[len("# TODO\n"):].lstrip("\n"), encoding="utf-8")
    else:
        todo.write_text(block + tt, encoding="utf-8")
    print("TODO updated")
else:
    print("TODO already has 2026-09-06k")
