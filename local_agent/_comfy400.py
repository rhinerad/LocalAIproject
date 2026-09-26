import json, sys, urllib.request, urllib.error
from pathlib import Path
BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
sys.path.insert(0, str(BASE))
import dspy_orchestrator as o
g = o.build_minimax_graph(
    "start hall yellow",
    "walk forward handheld",
    {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 24},
    negative="blur",
    prefix="dspy_opt/debug",
)
prompt = {k: v for k, v in g.items() if not str(k).startswith("_")}
# strip _meta if nested
print("nodes", sorted(prompt.keys(), key=lambda x: str(x)))
print("node20", json.dumps(prompt.get("20"), indent=2))
print("node8", json.dumps(prompt.get("8"), indent=2))
print("node3", json.dumps(prompt.get("3"), indent=2))
req = urllib.request.Request(
    "http://127.0.0.1:8188/prompt",
    data=json.dumps({"prompt": prompt, "client_id": "ff-check4"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        print("OK", resp.read().decode()[:500])
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print("HTTP", e.code)
    print(body[:4000])
