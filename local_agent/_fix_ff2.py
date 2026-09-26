from __future__ import annotations
import ast, json, re, sys, time, urllib.request
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
opath = BASE / "dspy_orchestrator.py"
raw = opath.read_bytes()
if raw.startswith(b"\xef\xbb\xbf"):
    raw = raw[3:]
ot = raw.decode("utf-8")

# If previous patch left IndentationError, restore from newest good bak first
try:
    ast.parse(ot)
except SyntaxError as e:
    print("orch broken, restoring", e)
    baks = sorted(BASE.glob("dspy_orchestrator.py.bak*"), key=lambda p: p.stat().st_mtime, reverse=True)
    restored = False
    for b in baks:
        try:
            t = b.read_bytes()
            if t.startswith(b"\xef\xbb\xbf"):
                t = t[3:]
            ast.parse(t.decode("utf-8"))
            opath.write_bytes(t if not t.startswith(b"\xef\xbb\xbf") else t)
            # write decoded without bom
            opath.write_bytes(t.decode("utf-8").encode("utf-8") if False else t)
            # ensure no bom
            data = b.read_bytes()
            if data.startswith(b"\xef\xbb\xbf"):
                data = data[3:]
            # verify
            ast.parse(data.decode("utf-8"))
            opath.write_bytes(data)
            ot = data.decode("utf-8")
            print("restored from", b.name)
            restored = True
            break
        except Exception as ex:
            print("skip bak", b.name, ex)
    if not restored:
        raise SystemExit("could not restore orchestrator")

# Backup current
ts = time.strftime("%Y%m%dT%H%M%S")
(BASE / f"dspy_orchestrator.py.bak_pre_firstframe_{ts}").write_bytes(ot.encode("utf-8"))

new_fn = '''def _force_frame_length(graph: dict, num_frames: int = MINIMAX_NUM_FRAMES) -> dict:
    """Hard-set MiniMax / I2V length fields to 192 frames (8s @ 24fps).

    Only touch explicit length scalars. NEVER overwrite image-link inputs such as
    ``first_frame`` / ``image`` / ``images`` (Comfy links like ``["8", 0]``).
    A prior bug matched any key containing ``frame`` and set ``first_frame=192``,
    which crashes MiniMaxH3ImageToVideo with TypeError: int is not subscriptable.
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
                continue  # leave Comfy links alone
            inputs[key] = int(num_frames)
    return graph


'''

m = re.search(r"def _force_frame_length\([\s\S]*?\n(?=def )", ot)
assert m, "missing _force_frame_length"
ot = ot[: m.start()] + new_fn + ot[m.end() :]

# Force denoise=1.0 after parse without breaking indent: replace fallback default instead
ot2, n = re.subn(
    r'(hparam denoise=.*using fallback )0\.9',
    r'\g<1>1.0',
    ot,
)
print("fallback string updates", n)
ot = ot2
# Also change numeric fallback in code if present
ot2, n = re.subn(
    r'(["\']denoise["\']\s*,\s*)0\.9\b',
    r'\g<1>1.0',
    ot,
)
print("denoise 0.9->1.0 literals", n)
ot = ot2
# DEFAULT hparams denoise
ot2, n = re.subn(
    r'(["\']denoise["\']\s*:\s*)0\.\d+',
    r'\g<1>1.0',
    ot,
    count=3,
)
print("default denoise keys", n)
ot = ot2

opath.write_bytes(ot.encode("utf-8"))
ast.parse(ot)
print("syntax OK")

sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if "dspy_orchestrator" in mod or "generalized_video_director" in mod:
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
print("first_frame", ff)
print("length", g["20"]["inputs"]["length"])
print("denoise", g["3"]["inputs"]["denoise"])
assert ff == ["8", 0], ff
assert int(g["20"]["inputs"]["length"]) == 192
assert float(g["3"]["inputs"]["denoise"]) == 1.0

# Validate with Comfy (will enqueue — interrupt after)
prompt = {k: v for k, v in g.items() if not str(k).startswith("_")}
payload = json.dumps({"prompt": prompt, "client_id": "firstframe-check"}).encode()
req = urllib.request.Request("http://127.0.0.1:8188/prompt", data=payload, headers={"Content-Type": "application/json"}, method="POST")
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
        print("Comfy accept", resp.status, "prompt_id", body.get("prompt_id"), "err", body.get("node_errors"))
        pid = body.get("prompt_id")
except Exception as e:
    print("Comfy reject", e)
    # try to print error body
    if hasattr(e, "read"):
        print(e.read().decode()[:1000])
    raise

# Poll briefly for execution_error vs success start
import urllib.error
time.sleep(3)
# interrupt so we don't burn a full gen during check — only needed validation accept
try:
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8188/interrupt", data=b"{}", headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
    urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8188/queue", data=json.dumps({"clear": True}).encode(), headers={"Content-Type":"application/json"}, method="POST"), timeout=10)
except Exception as e:
    print("cleanup", e)
print("WIRING FIX VERIFIED")
