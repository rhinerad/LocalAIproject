import json, re
from pathlib import Path
BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
# find graph json
cands = list(BASE.glob("**/*minimax*.json")) + list(BASE.glob("**/graphs/*.json"))
print("graphs", [str(p.relative_to(BASE)) for p in cands[:20]])
for p in cands[:10]:
    try:
        g = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(p.name, e); continue
    n20 = g.get("20") or g.get(20)
    print("---", p.name, "node20", n20)
    # find any MiniMax* nodes
    for k,v in (g.items() if isinstance(g, dict) else []):
        if isinstance(v, dict) and "minimax" in str(v.get("class_type","")).lower():
            print(" ", k, v.get("class_type"), "inputs keys", list((v.get("inputs") or {}).keys()), "inputs", v.get("inputs"))
# also grep orchestrator for first_frame wiring
orch = (BASE/"dspy_orchestrator.py").read_text(encoding="utf-8", errors="replace")
for m in re.finditer(r".{0,80}first_frame.{0,120}", orch):
    print("ORCH:", m.group(0).replace("\n"," ")[:200])
for m in re.finditer(r".{0,60}node.?20.{0,100}", orch, re.I):
    s=m.group(0).replace("\n"," ")
    if "first" in s or "image" in s or "length" in s or "192" in s:
        print("N20:", s[:200])
