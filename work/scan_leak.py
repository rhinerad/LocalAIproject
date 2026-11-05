from pathlib import Path
p = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\work\audit_turn4_sse.txt")
t = p.read_text(encoding="utf-8")
keys = ["Equal shares", "comfyui", "comfy", "miniMax", "minimax", "h3", "handbook", "film clip", "render pipeline", "specialist"]
low = t.lower()
print("bytes", len(t))
for k in keys:
    if k.lower() in low:
        print("HIT", k)
print("---notes/route/error---")
for ln in t.splitlines():
    if '"kind": "note"' in ln or '"kind": "error"' in ln or '"kind": "route"' in ln:
        print(ln[:400])
print("---done snippet---")
for ln in t.splitlines():
    if '"kind": "done"' in ln:
        print(ln[:500])
