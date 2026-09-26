from __future__ import annotations
import ast, inspect, json, re, sys, time
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
opath = BASE / "dspy_orchestrator.py"
text = opath.read_bytes()
if text.startswith(b"\xef\xbb\xbf"):
    text = text[3:]
ot = text.decode("utf-8")

# Show _force_frame_length
m = re.search(r"def _force_frame_length\([\s\S]*?\n(?=def )", ot)
print("--- _force_frame_length BEFORE ---")
print(m.group(0) if m else "MISSING")

# Replace with a safe version that only touches length/duration/num_frames/frames keys, never first_frame/image links
new_fn = '''def _force_frame_length(graph: dict, num_frames: int = MINIMAX_NUM_FRAMES) -> dict:
    """Force MiniMax clip length to num_frames without touching IMAGE wire links.

    CRITICAL: never overwrite `first_frame` / `image` / `images` — those are
    Comfy link lists like ["8", 0]. A prior bug set first_frame=192 (int), which
    crashes MiniMaxH3ImageToVideo with "'int' object is not subscriptable".
    """
    SAFE_LENGTH_KEYS = ("length", "duration_frames", "num_frames", "frames", "frame_count")
    for node_id, node in list(graph.items()):
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key in SAFE_LENGTH_KEYS:
            if key in inputs:
                val = inputs[key]
                # Only overwrite scalars / numeric strings — never list links
                if isinstance(val, (list, tuple, dict)):
                    continue
                inputs[key] = int(num_frames)
        # Explicitly refuse to touch image-like keys even if somehow listed
        for protected in ("first_frame", "image", "images", "start_image", "init_image"):
            if protected in inputs and isinstance(inputs[protected], (list, tuple)):
                continue  # leave link intact
    return graph


'''

if m:
    ot = ot[: m.start()] + new_fn + ot[m.end() :]
else:
    raise SystemExit("missing _force_frame_length")

# Also silence denoise fallback warning: force denoise=1.0 in parse_director_hparams path
# Find parse / fallback message
if "hparam denoise=" in ot or "using fallback" in ot:
    # After parse, force denoise
    ot2, n = re.subn(
        r'(hparams, hparam_notes = parse_director_hparams\(pred\))',
        r'\1\n        hparams["denoise"] = 1.0  # FLUX Empty Latent: ignore LM / fallback denoise',
        ot,
        count=0,
    )
    print("denoise force after parse", n)
    ot = ot2

opath.write_bytes(ot.encode("utf-8"))
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
ff = g["20"]["inputs"]["first_frame"]
print("first_frame after fix", ff)
assert ff == ["8", 0], ff
assert g["20"]["inputs"]["length"] == 192
assert g["3"]["inputs"]["denoise"] == 1.0
print("GRAPH WIRING FIXED")

# Dry-validate against live Comfy if up
import urllib.request
try:
    payload = {"prompt": {k: v for k, v in g.items() if not str(k).startswith("_")}, "client_id": "wiring-check"}
    req = urllib.request.Request(
        "http://127.0.0.1:8188/prompt",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
        print("Comfy /prompt", resp.status, body[:300])
except Exception as e:
    print("Comfy validate", type(e).__name__, e)
