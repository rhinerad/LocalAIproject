from pathlib import Path
p = Path(r'A:/Users/rhine/Documents/Codex/2026-08-07/referenced-chatgpt-conversation-this-is-an-2/COMFYUI_STORY_HANDOFF_2026-08-09/local_agent/test_prompt_pack_production.py')
t = p.read_text(encoding='utf-8')
t = t.replace('action_resolver.resolve', 'action_resolver.classify')
needle = 'complete images and videos'
i = t.find(needle)
assert i > 0
j = t.find(')', t.find('cid=', i))
assert j > 0
insert = ',' + chr(10) + '                pending_calibration_path_fn=lambda history, cid: None,' + chr(10) + '                specialist_scope=False'
if 'specialist_scope=False' not in t[i:i+400]:
    t = t[:j] + insert + t[j:]
p.write_text(t, encoding='utf-8')
print('ok')
