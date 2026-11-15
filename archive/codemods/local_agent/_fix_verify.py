from __future__ import annotations
import ast, inspect, re, shutil, sys, time
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
TS = time.strftime("%Y%m%dT%H%M%S")

opath = BASE/"dspy_orchestrator.py"
ot = opath.read_text(encoding="utf-8")

# Fix broken denoise block (orphan lines)
ot2, n = re.subn(
    r'        node3\["inputs"\]\["denoise"\] = 1\.0  # FLUX Empty Latent T2I: always full denoise\n'
    r'            hparams\.get\("denoise", node3\["inputs"\]\.get\("denoise", 1\.0\)\)\n'
    r'        \)\n',
    '        node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise\n',
    ot,
    count=1,
)
print("fix orphan", n)
ot = ot2

# Also force denoise lock in other hparam apply sites that write denoise from hparams on KSampler
# Line ~550 area: if "denoise" in inputs -> force 1.0 for FLUX path
ot2, n = re.subn(
    r'        if "denoise" in inputs:\n'
    r'            inputs\["denoise"\] = float\(hparams\.get\("denoise", inputs\["denoise"\]\)\)\n',
    '        if "denoise" in inputs:\n'
    '            # FLUX Empty Latent T2I: always full denoise (ignore learner value)\n'
    '            inputs["denoise"] = 1.0\n',
    ot,
    count=1,
)
print("inputs denoise lock", n)
ot = ot2

# parse_director_hparams: keep denoise fallback 1.0 but it's ok if signature doesn't emit it
# Ensure extract_eval_frames has cap
if "max(8, min(12" not in ot:
    m = re.search(r"def extract_eval_frames\([\s\S]*?\n(?=def )", ot)
    if m:
        fn = m.group(0)
        fn2 = re.sub(r"(count:\s*int\s*=\s*)\d+", r"\g<1>10", fn, count=1)
        fn2 = re.sub(
            r"(def extract_eval_frames\([^\)]*\):\n(?:\s+\"\"\"[\s\S]*?\"\"\"\n)?)",
            r"\1"
            r"    # MiniMax emits ~192 frames; NEVER feed the full clip to Qwen-VL.\n"
            r"    try:\n"
            r"        _requested = int(count)\n"
            r"    except Exception:\n"
            r"        _requested = 10\n"
            r"    count = int(max(8, min(12, _requested)))\n",
            fn2,
            count=1,
        )
        ot = ot[:m.start()] + fn2 + ot[m.end():]
        print("added frame cap")
    else:
        print("WARN no extract_eval_frames")
else:
    print("frame cap already present")

# Ensure build_minimax_graph / generate use _flux_safe_hparams if present
if "def _flux_safe_hparams" not in ot and "def _flux_safe_hparams" not in ot:
    pass
# There's already _flux_safe_hparams at line 676 - ensure callers use it
if "hparams = _flux_safe_hparams(hparams)" not in ot:
    # inject into build_minimax_graph body
    ot, n = re.subn(
        r'(def build_minimax_graph\([^\)]*\):\n(?:\s+"""[\s\S]*?"""\n)?)',
        r"\1    hparams = _flux_safe_hparams(hparams)\n",
        ot,
        count=1,
    )
    print("inject build", n)
    ot, n = re.subn(
        r'(def generate_minimax_clip\([^\)]*\):\n(?:\s+"""[\s\S]*?"""\n)?)',
        r"\1    hparams = _flux_safe_hparams(hparams)\n",
        ot,
        count=1,
    )
    print("inject generate", n)

# Rename leftover video_motion if any
ot = ot.replace("video_motion_prompt", "video_prompt")

opath.write_text(ot, encoding="utf-8")
try:
    ast.parse(ot)
    print("orch syntax OK")
except SyntaxError as e:
    print("SYNTAX FAIL", e)
    lines = ot.splitlines()
    for i in range(max(1,e.lineno-5), min(len(lines), e.lineno+5)+1):
        print(f"{i}: {lines[i-1]}")
    raise

# Also check gvd still good and has no denoise field
gpath = BASE/"generalized_video_director.py"
ast.parse(gpath.read_text(encoding="utf-8"))
print("gvd syntax OK")

# Wipe compiled again
wiped=[]
for comp in [ROOT/"models"/"dspy_compiled", BASE/"models"/"dspy_compiled"]:
    if not comp.exists():
        continue
    for p in list(comp.glob("*.json")):
        if ".bak_wipe_" in p.name:
            continue
        dest = p.with_name(p.name + f".bak_wipe_{TS}")
        p.rename(dest); wiped.append(dest.name)
print("WIPED", wiped)

# Verify imports
sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if mod in {"dspy_orchestrator","generalized_video_director"} or mod.startswith(("dspy_orchestrator.","generalized_video_director.")):
        del sys.modules[mod]
import generalized_video_director as gvd
import dspy_orchestrator as o

# Ensure DENOISE_RANGE still exists for parse fallbacks - or patch parse if it crashes without denoise in signature
sig = gvd.director_signature_class()
outs = list(sig.output_fields.keys())
print("outputs", outs)
assert "denoise" not in outs
assert "video_prompt" in outs and "start_prompt" in outs
assert "Do NOT emit denoise" in gvd.DIRECTOR_SIGNATURE_INSTRUCTIONS

g = o.build_minimax_graph("a","b",{"cfg_scale":4.0,"denoise":0.2,"step_count":24},negative="x",prefix="dspy_opt/s")
print("node3", g["3"]["inputs"])
assert float(g["3"]["inputs"]["denoise"]) == 1.0
assert float(g["3"]["inputs"]["cfg"]) == 4.0
assert int(g["3"]["inputs"]["steps"]) == 24

src = inspect.getsource(o.extract_eval_frames)
assert "max(8, min(12" in src
print("frame cap OK")

live=[]
for comp in [ROOT/"models"/"dspy_compiled", BASE/"models"/"dspy_compiled"]:
    if comp.exists():
        live += [p.name for p in comp.glob("*.json")]
print("live compiled", live)
assert not live

# Show extract_eval_frames signature / sampling approach
print("--- extract_eval_frames head ---")
print("\n".join(src.splitlines()[:40]))
print("VERIFY ALL OK")
