from pathlib import Path
import re, json, copy
BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
orch = (BASE/"dspy_orchestrator.py").read_text(encoding="utf-8")
print("=== first_frame hits ===")
for i, ln in enumerate(orch.splitlines(), 1):
    if "first_frame" in ln or "MINIMAX_NUM_FRAMES" in ln or '["20"]' in ln or "node20" in ln:
        print(f"{i}: {ln}")

# Simulate build
import sys
sys.path.insert(0, str(BASE))
import dspy_orchestrator as o
g = o.build_minimax_graph("start hall yellow", "walk forward handheld", {"cfg_scale":4.0,"denoise":0.2,"step_count":24}, negative="blur", prefix="dspy_opt/debug")
print("=== built node 8 ===", g.get("8"))
print("=== built node 20 ===", json.dumps(g.get("20"), indent=2))
print("=== built node 3 ===", json.dumps(g.get("3"), indent=2))
# Check if first_frame still link
ff = g["20"]["inputs"].get("first_frame")
print("first_frame value", ff, type(ff))
