from __future__ import annotations
import ast, json, re, sys, time, urllib.request
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
OUT = Path(r"A:\Users\rhine\.grok\long-running-background-tasks")

# Restore from safety3 again (known good before broken denoise replace), then apply BOTH fixes carefully
baks = sorted(BASE.glob("dspy_orchestrator.py.bak*"), key=lambda p: p.stat().st_mtime, reverse=True)
# Prefer bak that has protected first_frame fix if any
chosen = None
for b in baks:
    t = b.read_text(encoding="utf-8", errors="replace")
    try:
        ast.parse(t)
    except SyntaxError:
        continue
    if "NEVER overwrite image-link" in t or ("protected" in t and "first_frame" in t and "_force_frame_length" in t):
        # check force_frame has protected
        chunk = t.split("def _force_frame_length", 1)[1][:1200] if "def _force_frame_length" in t else ""
        if "first_frame" in chunk and ("protected" in chunk or "NEVER" in chunk):
            chosen = b
            break
if chosen is None:
    # use latest syntactically valid
    for b in baks:
        t = b.read_text(encoding="utf-8", errors="replace")
        try:
            ast.parse(t)
            chosen = b
            break
        except SyntaxError:
            continue
print("restore base", chosen.name if chosen else None)
ot = chosen.read_text(encoding="utf-8")

# 1) Replace _force_frame_length entirely
new_fn = '''def _force_frame_length(graph: dict, num_frames: int = MINIMAX_NUM_FRAMES) -> dict:
    """Hard-set MiniMax / I2V length fields to 192 frames (8s @ 24fps).

    Only touch explicit length scalars. NEVER overwrite image-link inputs such as
    ``first_frame`` / ``image`` / ``images`` (Comfy links like ``["8", 0]``).
    """
    length_keys = {
        "num_frames",
        "frame_count",
        "frames",
        "length",
        "video_length",
        "num_frames_total",
        "total_frames",
        "duration_frames",
    }
    protected = {
        "first_frame",
        "last_frame",
        "image",
        "images",
        "start_image",
        "end_image",
        "init_image",
        "pixels",
    }
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key in list(inputs.keys()):
            lk = str(key).lower()
            if lk in protected:
                continue
            if lk not in length_keys:
                continue
            val = inputs[key]
            if isinstance(val, (list, tuple, dict)):
                continue
            inputs[key] = int(num_frames)
    return graph


'''
m = re.search(r"def _force_frame_length\([\s\S]*?\n(?=def )", ot)
assert m
ot = ot[: m.start()] + new_fn + ot[m.end() :]

# 2) Replace multi-line denoise float(...) with hardcoded 1.0
ot2, n = re.subn(
    r'node3\["inputs"\]\["denoise"\]\s*=\s*float\(\s*\n\s*hparams\.get\("denoise",\s*node3\["inputs"\]\.get\("denoise",\s*1\.0\)\)\s*\n\s*\)',
    'node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise',
    ot,
)
print("multiline denoise replace", n)
if n == 0:
    # try single-line variants / orphaned forms
    ot2, n = re.subn(
        r'node3\["inputs"\]\["denoise"\]\s*=\s*[^\n]+\n(?:\s+hparams\.get\("denoise"[^\n]+\n)?(?:\s+\)\n)?',
        'node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise\n',
        ot,
        count=1,
    )
    print("fallback denoise replace", n)
ot = ot2

# 3) Lock other inputs["denoise"] = float(hparams...) 
ot, n = re.subn(
    r'inputs\["denoise"\]\s*=\s*float\(hparams\.get\("denoise"[^\n]+\)',
    'inputs["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise',
    ot,
)
print("inputs denoise", n)

# 4) Helper + call at start of build_minimax_graph
if "def _flux_safe_hparams" not in ot:
    helper = '''

def _flux_safe_hparams(hparams: dict) -> dict:
    """FLUX Empty-Latent T2I: denoise locked at 1.0; only cfg/steps tunable."""
    out = dict(hparams or {})
    out["denoise"] = 1.0
    return out

'''
    if "\ndef build_minimax_graph(" in ot:
        ot = ot.replace("\ndef build_minimax_graph(", helper + "\ndef build_minimax_graph(", 1)
    else:
        # maybe different name
        ot = ot.replace("\ndef build_flux_minimax_graph(", helper + "\ndef build_flux_minimax_graph(", 1)

# inject call - find actual build fn name
for fname in ("build_minimax_graph", "build_flux_minimax_graph", "build_minimax_workflow"):
    if f"def {fname}(" in ot and "hparams = _flux_safe_hparams(hparams)" not in ot.split(f"def {fname}(")[1][:500]:
        ot, n = re.subn(
            rf'(def {fname}\([^\)]*\):\n(?:\s+"""[\s\S]*?"""\n)?)',
            r"\1    hparams = _flux_safe_hparams(hparams)\n",
            ot,
            count=1,
        )
        print("inject", fname, n)

opath = BASE / "dspy_orchestrator.py"
opath.write_text(ot, encoding="utf-8")
ast.parse(ot)
print("syntax OK")

sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if "dspy_orchestrator" in mod:
        del sys.modules[mod]
import dspy_orchestrator as o

# discover build fn
build = getattr(o, "build_minimax_graph", None) or getattr(o, "build_flux_minimax_graph", None)
print("build fn", build.__name__)
g = build(
    "start hall yellow",
    "walk forward handheld",
    {"cfg_scale": 4.0, "denoise": 0.2, "step_count": 24},
    negative="blur",
    prefix="dspy_opt/debug",
)
print("first_frame", g["20"]["inputs"]["first_frame"])
print("length", g["20"]["inputs"]["length"])
print("node3 denoise/cfg/steps", g["3"]["inputs"]["denoise"], g["3"]["inputs"]["cfg"], g["3"]["inputs"]["steps"])
assert g["20"]["inputs"]["first_frame"] == ["8", 0]
assert int(g["20"]["inputs"]["length"]) == 192
assert float(g["3"]["inputs"]["denoise"]) == 1.0

prompt = {k: v for k, v in g.items() if not str(k).startswith("_")}
req = urllib.request.Request(
    "http://127.0.0.1:8188/prompt",
    data=json.dumps({"prompt": prompt, "client_id": "ff-check3"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=30) as resp:
    body = json.loads(resp.read().decode())
    print("Comfy accepted", body.get("prompt_id"), "node_errors", body.get("node_errors"))
for path, body in [("/interrupt", {}), ("/queue", {"clear": True}), ("/free", {"unload_models": True, "free_memory": True})]:
    urllib.request.urlopen(urllib.request.Request(
        "http://127.0.0.1:8188"+path,
        data=json.dumps(body).encode(),
        headers={"Content-Type":"application/json"},
        method="POST"), timeout=15)
print("READY TO RUN")
