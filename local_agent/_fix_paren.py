from pathlib import Path
p = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent\tools.py")
t = p.read_text(encoding="utf-8")
old = "until approve_story_stills after explicit operator approval.',\n    \"await_story_image_job\""
new = "until approve_story_stills after explicit operator approval.'),\n    \"await_story_image_job\""
assert old in t, "fix target missing"
p.write_text(t.replace(old, new, 1), encoding="utf-8")
compile(p.read_text(encoding="utf-8"), str(p), "exec")
print("syntax OK")
