from __future__ import annotations
import ast, inspect, re, sys
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
sys.path.insert(0, str(BASE))

import generalized_video_director as gvd
import dspy_orchestrator as o

print("gvd attrs", [a for a in dir(gvd) if "sig" in a.lower() or "direct" in a.lower() or "INSTR" in a or "DENOISE" in a or "RANGE" in a])
# Find signature class
for name in dir(gvd):
    obj = getattr(gvd, name)
    if isinstance(obj, type) and "Signature" in name:
        print("class", name, list(getattr(obj, "output_fields", {}) or {}))

# Try common factories
for fn in ["director_signature_class", "get_director_signature", "make_director_signature", "build_director_signature"]:
    if hasattr(gvd, fn):
        print("call", fn, getattr(gvd, fn)())

# Read instructions constant names
for n in dir(gvd):
    if "INSTR" in n.upper() or n.endswith("INSTRUCTIONS"):
        val = getattr(gvd, n)
        if isinstance(val, str):
            print(n, "len", len(val), "has denoise ban", "denoise" in val.lower(), "has video_prompt", "video_prompt" in val)

# Inspect signature in source
src = (BASE/"generalized_video_director.py").read_text(encoding="utf-8")
m = re.search(r"class GeneralizedVideoDirectorSignature[\s\S]*?(?=\n    GeneralizedVideoDirectorSignature\.|\n\n    return|\n\ndef |\nclass )", src)
print("--- sig snippet ---")
print(m.group(0)[:1200] if m else "NOT FOUND")

# Check how director_signature_class works
if hasattr(gvd, "director_signature_class"):
    print("src", inspect.getsource(gvd.director_signature_class)[:800])

# build graph
g = o.build_minimax_graph(
    "start hall",
    "walk forward",
    {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 24},
    negative="blur",
    prefix="dspy_opt/s",
)
print("node3", g.get("3", {}).get("inputs"))
print("has extract", hasattr(o, "extract_eval_frames"))
if hasattr(o, "extract_eval_frames"):
    print(inspect.getsource(o.extract_eval_frames)[:700])

# Also check parse_director_hparams / DENOISE_RANGE dependency
print("DENOISE_RANGE", getattr(gvd, "DENOISE_RANGE", None))
print("CFG", getattr(gvd, "CFG_SCALE_RANGE", None), getattr(gvd, "STEP_COUNT_RANGE", None))

# Live compiled
for comp in [ROOT/"models"/"dspy_compiled", BASE/"models"/"dspy_compiled"]:
    print(comp, "exists", comp.exists(), "jsons", list(comp.glob("*.json")) if comp.exists() else [])
