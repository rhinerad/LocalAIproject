from pathlib import Path
p = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent\dspy_orchestrator.py")
lines = p.read_text(encoding="utf-8").splitlines()
for i in range(620, 680):
    if i-1 < len(lines):
        print(f"{i}: {lines[i-1]}")
print("--- search denoise ---")
for i, ln in enumerate(lines, 1):
    if "denoise" in ln.lower() or "node3" in ln:
        if 600 <= i <= 720 or "FLUX Empty" in ln or "denoise" in ln:
            print(f"{i}: {ln}")
