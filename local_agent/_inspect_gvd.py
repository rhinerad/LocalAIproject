from pathlib import Path
base = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
p = base/'generalized_video_director.py'
text = p.read_text(encoding='utf-8', errors='replace')
lines = text.splitlines()
print('total lines', len(lines))
for i in range(40, 100):
    if i-1 < len(lines):
        print(f"{i}: {lines[i-1][:200]}")
print('--- backups ---')
for b in sorted(base.glob('generalized_video_director.py.bak*'))[-10:]:
    print(b.name, b.stat().st_size)
print('--- try parse each bak ---')
import ast
for b in sorted(base.glob('generalized_video_director.py.bak*'))[-10:]:
    try:
        ast.parse(b.read_text(encoding='utf-8'))
        print('OK', b.name)
    except SyntaxError as e:
        print('BAD', b.name, e)
try:
    ast.parse(text)
    print('CURRENT OK')
except SyntaxError as e:
    print('CURRENT BAD', e)
