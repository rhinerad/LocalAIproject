from pathlib import Path

agent = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent\agent.py")
server = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent\server.py")

at = agent.read_text(encoding="utf-8")
old = "resident_gpu = router._running_models(router.GPU_HOST) if not gpu_busy else []"
new = "resident_gpu = (router._running_models(router.GPU_HOST) or []) if not gpu_busy else []"
if old not in at:
    raise SystemExit("agent pattern missing")
agent.write_text(at.replace(old, new, 1), encoding="utf-8")

st = server.read_text(encoding="utf-8")
oldr = "2026-09-01-project-scope-falsepos-r72"
newr = "2026-09-01-resident-gpu-none-r73"
if oldr not in st:
    raise SystemExit("revision pattern missing")
server.write_text(st.replace(oldr, newr, 1), encoding="utf-8")
print("patched ok")
