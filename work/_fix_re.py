from pathlib import Path
p = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent\managed_prompt_pack.py")
t = p.read_text(encoding="utf-8")
old = '''_CLIP_HEADER_RE = re.compile(
    r"(?:(?m)^|[ \\t]{2,})#{2,4}\\s*(C\\d{2,4})\\b",
    re.I,
)'''
new = '''_CLIP_HEADER_RE = re.compile(
    r"#{2,4}\\s*(C\\d{2,4})\\b",
    re.I,
)'''
if old not in t:
    raise SystemExit("clip header re not found:\n" + t[t.find("_CLIP_HEADER_RE"):t.find("_CLIP_HEADER_RE")+200])
t = t.replace(old, new, 1)
# also fix _FIELD_STOP_RE which may have same issue
old2 = '''_FIELD_STOP_RE = re.compile(
    r"(?i)(?:\\bStart\\s+Frame\\s*:|\\bLast\\s+Frame\\s*:|\\bVideo\\s+Prompt\\s*:|"
    r"(?:(?m)^|[ \\t]{2,})#{2,4}\\s*C\\d{2,4}\\b|\\n\\s*##\\s+)"
)'''
new2 = '''_FIELD_STOP_RE = re.compile(
    r"(?i)(?:\\bStart\\s+Frame\\s*:|\\bLast\\s+Frame\\s*:|\\bVideo\\s+Prompt\\s*:|"
    r"#{2,4}\\s*C\\d{2,4}\\b|\\n\\s*##\\s+)"
)'''
if old2 not in t:
    raise SystemExit("field stop not found")
t = t.replace(old2, new2, 1)
p.write_text(t, encoding="utf-8")
print("fixed regex")
