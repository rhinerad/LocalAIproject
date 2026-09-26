from __future__ import annotations
import ast, json, re, sys, time, urllib.request
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
opath = BASE / "dspy_orchestrator.py"
ot = opath.read_text(encoding="utf-8")

# Confirm _force_frame_length is the safe one
assert "NEVER overwrite image-link" in ot or "protected" in ot and "first_frame" in ot.split("def _force_frame_length")[1][:800]
print("force_frame_length protected OK")

# Hardcode denoise on node3 mapping
# Find existing assignment
hits = list(re.finditer(r'node3\["inputs"\]\["denoise"\]\s*=\s*[^\n]+', ot))
print("denoise assigns", [h.group(0) for h in hits])
if hits:
    ot, n = re.subn(
        r'node3\["inputs"\]\["denoise"\]\s*=\s*[^\n]+',
        'node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise',
        ot,
    )
    print("replaced", n)
else:
    ot, n = re.subn(
        r'(node3\["inputs"\]\["steps"\]\s*=\s*int\([^\n]+\))',
        r'\1\n        node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise',
        ot,
        count=1,
    )
    print("injected after steps", n)

# Also lock in any inputs["denoise"] = float(hparams...) style
ot, n = re.subn(
    r'inputs\["denoise"\]\s*=\s*float\(hparams\.get\("denoise"[^\n]+',
    'inputs["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise',
    ot,
)
print("inputs denoise locks", n)

# Ensure _flux_safe_hparams exists and is used
if "def _flux_safe_hparams" not in ot:
    helper = '''

def _flux_safe_hparams(hparams: dict) -> dict:
    """FLUX Empty-Latent T2I: denoise locked at 1.0; only cfg/steps tunable."""
    out = dict(hparams or {})
    out["denoise"] = 1.0
    return out

'''
    ot = ot.replace("\ndef build_minimax_graph(", helper + "\ndef build_minimax_graph(", 1)
    print("added helper")

if "hparams = _flux_safe_hparams(hparams)" not in ot:
    ot, n = re.subn(
        r'(def build_minimax_graph\([^\)]*\):\n(?:\s+"""[\s\S]*?"""\n)?)',
        r"\1    hparams = _flux_safe_hparams(hparams)\n",
        ot,
        count=1,
    )
    print("safe in build", n)

opath.write_text(ot, encoding="utf-8")
ast.parse(ot)
print("syntax OK")

sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if "dspy_orchestrator" in mod:
        del sys.modules[mod]
import dspy_orchestrator as o
g = o.build_minimax_graph(
    "start hall yellow",
    "walk forward handheld",
    {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 24},
    negative="blur",
    prefix="dspy_opt/debug",
)
print("first_frame", g["20"]["inputs"]["first_frame"])
print("length", g["20"]["inputs"]["length"])
print("node3", {k: g["3"]["inputs"][k] for k in ("denoise", "cfg", "steps")})
assert g["20"]["inputs"]["first_frame"] == ["8", 0]
assert g["20"]["inputs"]["length"] == 192
assert float(g["3"]["inputs"]["denoise"]) == 1.0
assert float(g["3"]["inputs"]["cfg"]) == 4.0
assert int(g["3"]["inputs"]["steps"]) == 24

# Comfy validate
prompt = {k: v for k, v in g.items() if not str(k).startswith("_")}
req = urllib.request.Request(
    "http://127.0.0.1:8188/prompt",
    data=json.dumps({"prompt": prompt, "client_id": "ff-check2"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
        print("Comfy OK", body.get("prompt_id"), "node_errors", body.get("node_errors"))
except Exception as e:
    print("Comfy FAIL", e)
    if hasattr(e, "read"):
        print(e.read().decode()[:1500])
    raise
# clear queue
for path, body in [("/interrupt", {}), ("/queue", {"clear": True})]:
    try:
        urllib.request.urlopen(urllib.request.Request(
            "http://127.0.0.1:8188"+path,
            data=json.dumps(body).encode(),
            headers={"Content-Type":"application/json"},
            method="POST"), timeout=15)
    except Exception as e:
        print("cleanup", path, e)
print("ALL GRAPH CHECKS PASSED")
