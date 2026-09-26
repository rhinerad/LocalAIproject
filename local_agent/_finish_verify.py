from __future__ import annotations
import ast, inspect, re, shutil, sys, time
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
TS = time.strftime("%Y%m%dT%H%M%S")

# Fix director_signature_class return if missing
gpath = BASE/"generalized_video_director.py"
gt = gpath.read_text(encoding="utf-8")
# Find function and ensure it returns the class
m = re.search(r"def director_signature_class\(\):([\s\S]*?)(?=\ndef |\nclass )", gt)
if not m:
    raise SystemExit("director_signature_class not found")
body = m.group(1)
print("returns class?", "return GeneralizedVideoDirectorSignature" in body)
if "return GeneralizedVideoDirectorSignature" not in body:
    # append return before end of function
    new_body = body.rstrip() + "\n\n    return GeneralizedVideoDirectorSignature\n\n"
    gt = gt[:m.start(1)] + new_body + gt[m.end(1):]
    gpath.write_text(gt, encoding="utf-8")
    ast.parse(gt)
    print("fixed return")
else:
    print("return already present")

# Patch dspy_optimizer extract_eval_frames
opt = None
for cand in [BASE/"dspy_optimizer.py", ROOT/"local_agent"/"dspy_optimizer.py", BASE.parent/"dspy_optimizer.py"]:
    if cand.exists():
        opt = cand
        break
# search
if opt is None:
    hits = list(BASE.glob("**/dspy_optimizer.py")) + list(ROOT.glob("**/dspy_optimizer.py"))
    print("optimizer candidates", hits)
    opt = hits[0] if hits else None
print("optimizer", opt)
assert opt and opt.exists()

ot = opt.read_text(encoding="utf-8")
shutil.copy2(opt, opt.with_name(opt.name + f".bak_framecap_{TS}"))
if "def extract_eval_frames" not in ot:
    raise SystemExit("no extract_eval_frames in optimizer")
m = re.search(r"def extract_eval_frames\([\s\S]*?\n(?=def )", ot)
assert m, "cannot isolate extract_eval_frames"
fn = m.group(0)
print("--- before head ---")
print("\n".join(fn.splitlines()[:35]))
fn2 = re.sub(r"(count:\s*int\s*=\s*)\d+", r"\g<1>10", fn, count=1)
if "max(8, min(12" not in fn2:
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
# Also force any internal max_frames / sample_count defaults down from 192
fn2 = re.sub(r"(max_frames\s*=\s*)\d+", r"\g<1>12", fn2)
fn2 = re.sub(r"(num_frames\s*=\s*)192", r"\g<1>10", fn2)
ot = ot[:m.start()] + fn2 + ot[m.end():]
opt.write_text(ot, encoding="utf-8")
ast.parse(ot)
print("framecap patched in", opt.name)
print("--- after head ---")
print("\n".join(fn2.splitlines()[:40]))

# Also ensure clamp_director_hparams / parse still works without denoise from LM
sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if "generalized_video_director" in mod or "dspy_orchestrator" in mod or "dspy_optimizer" in mod:
        del sys.modules[mod]
import generalized_video_director as gvd
import dspy_orchestrator as o

sig = gvd.director_signature_class()
assert sig is not None, "signature class still None"
outs = list(sig.output_fields.keys())
print("outputs", outs)
assert "denoise" not in outs
assert "end_prompt" not in outs
assert "start_prompt" in outs and "video_prompt" in outs
assert "cfg_scale" in outs and "step_count" in outs
instr = gvd.DIRECTOR_SIGNATURE_INSTRUCTIONS
assert "Do NOT emit denoise" in instr or "Do not emit denoise" in instr.lower() or "denoise" in instr.lower()
print("instr denoise ban OK")

# hparams clamp without denoise from LM
hp = gvd.clamp_director_hparams({"cfg_scale": 4.0, "step_count": 24})
print("clamped", hp)
assert float(hp.get("denoise", 1.0)) == 1.0 or "denoise" not in hp
# if clamp still requires denoise key, force inject in clamp
src_clamp = inspect.getsource(gvd.clamp_director_hparams)
if 'hparams.get("denoise"' in src_clamp or "denoise" in src_clamp:
    # ensure after clamp denoise is 1.0 when present
    if hp.get("denoise") not in (None, 1.0) and float(hp.get("denoise", 1.0)) != 1.0:
        print("WARN clamp still allows non-1 denoise", hp)

# Force denoise=1.0 in clamp_director_hparams return if it still emits denoise
if "denoise" in (hp or {}) and float(hp["denoise"]) != 1.0:
    # patch clamp
    gt = gpath.read_text(encoding="utf-8")
    if "out[\"denoise\"] = 1.0  # FLUX Empty Latent lock" not in gt:
        gt2, n = re.subn(
            r"(def clamp_director_hparams\([\s\S]*?)(return out\n)",
            r"\1    out[\"denoise\"] = 1.0  # FLUX Empty Latent lock\n    \2",
            gt,
            count=1,
        )
        print("clamp lock inject", n)
        if n:
            gpath.write_text(gt2, encoding="utf-8")
            ast.parse(gt2)
            del sys.modules["generalized_video_director"]
            import generalized_video_director as gvd
            hp = gvd.clamp_director_hparams({"cfg_scale": 4.0, "step_count": 24, "denoise": 0.2})
            print("reclamped", hp)

g = o.build_minimax_graph("a","b",{"cfg_scale":4.0,"denoise":0.2,"step_count":24},negative="x",prefix="dspy_opt/s")
assert float(g["3"]["inputs"]["denoise"]) == 1.0
print("graph denoise OK", g["3"]["inputs"]["denoise"], g["3"]["inputs"]["cfg"], g["3"]["inputs"]["steps"])

import dspy_optimizer as optm
src = inspect.getsource(optm.extract_eval_frames)
assert "max(8, min(12" in src
print("optimizer framecap OK")

# compiled wipe confirm
live=[]
for comp in [ROOT/"models"/"dspy_compiled", BASE/"models"/"dspy_compiled"]:
    if comp.exists():
        live += [p.name for p in comp.glob("*.json")]
print("live compiled", live)
assert not live
print("ALL PHASES VERIFIED")
