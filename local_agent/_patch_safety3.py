from __future__ import annotations
import ast, re, shutil, sys, time
from pathlib import Path

BASE = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent")
ROOT = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
TS = time.strftime("%Y%m%dT%H%M%S")

# Verify restore
ast.parse((BASE/"generalized_video_director.py").read_text(encoding="utf-8"))
print("restore OK")

# Write instructions block to a separate fragment file using only chr() for newlines in string content
esc = "\\" + "n"  # literal backslash-n for Python source
lines = [
    "You are a Generalized Video Director for FLUX.1 (start frame) + MiniMax ",
    "Image-to-Video on an RTX 5080. Emit start_prompt, video_prompt, ",
    "negative_prompt, and numeric hparams cfg_scale and step_count only." + esc,
    "start_prompt (FLUX.1 T2I): highly descriptive natural language for a SINGLE ",
    "still opening frame. Focus on lighting, texture, materials, composition, ",
    "lens/look. No camera-move verbs." + esc,
    "video_prompt (MiniMax I2V): focus STRICTLY on camera physics, subject motion, ",
    "and temporal change across an 8-second / 192-frame clip. Name move, pace, ",
    "and ending energy. Do not rewrite the whole scene from scratch." + esc,
    "Do NOT emit denoise — FLUX Empty Latent T2I always uses denoise=1.0." + esc,
    "Do NOT emit end_prompt." + esc,
    "Honor category:" + esc,
    "- drone_high_kinematics: aerial/high-speed travel, large parallax; prefer ",
    "cfg_scale 4.0-5.5; step_count 24-32." + esc,
    "- macro_nature: extreme close-up, shallow DOF, slow organic motion; prefer ",
    "cfg_scale 5.5-7.0; step_count 28-36." + esc,
    "- stylized_2d: lock the named 2D medium every frame; prefer cfg_scale 6.0-7.5; ",
    "step_count 20-30." + esc,
    "- backrooms: first-person analog camcorder unless locked; prefer cfg_scale ",
    "5.0-6.5; step_count 24-32. Put camera nouns AND motion verbs in video_prompt; ",
    "put VHS/liminal look in start_prompt." + esc,
    "cfg_scale and step_count MUST be JSON numbers (floats). cfg_scale in [1.0, 8.0], ",
    "step_count in [16, 40].",
]

frag_lines = ["DIRECTOR_SIGNATURE_INSTRUCTIONS = ("]
for ln in lines:
    frag_lines.append("    " + repr(ln))
frag_lines.append(")")
frag = "\n".join(frag_lines) + "\n"
# Validate fragment alone
ast.parse(frag)
(BASE/"_instr_fragment.py").write_text(frag, encoding="utf-8")
print("fragment OK, sample:", repr(lines[2][-20:]))

path = BASE/"generalized_video_director.py"
shutil.copy2(path, path.with_name(path.name + f".bak_pre_instr_{TS}"))
text = path.read_text(encoding="utf-8")
text2, n = re.subn(
    r"DIRECTOR_SIGNATURE_INSTRUCTIONS\s*=\s*\([\s\S]*?\)\n",
    frag + "\n",
    text,
    count=1,
)
print("instr replace count", n)
assert n == 1
ast.parse(text2)
print("after instr OK")

# Signature class replace
sig_pat = re.compile(
    r"    class GeneralizedVideoDirectorSignature\(dspy\.Signature\):[\s\S]*?"
    r"(?=\n    GeneralizedVideoDirectorSignature\.instructions=|\n\n    return |\n\ndef )"
)
new_sig = '''    class GeneralizedVideoDirectorSignature(dspy.Signature):
        """Direct FLUX.1 start frame + MiniMax I2V motion (no end_prompt, no denoise)."""

        user_intent: str = dspy.InputField(
            desc="The user's scene, subject, and motion request"
        )
        category: str = dspy.InputField(
            desc="One of drone_high_kinematics, macro_nature, stylized_2d, backrooms"
        )
        vbench_focus: str = dspy.InputField(
            desc="Comma-separated VBench axes this clip must satisfy"
        )
        duration_seconds: float = dspy.InputField(
            desc="Clip length in seconds (8 for MiniMax 192 frames)"
        )
        constraints: str = dspy.InputField(
            desc="Hard rejection clauses the prompt must honor"
        )
        start_prompt: str = dspy.OutputField(
            desc="FLUX.1 still prompt: descriptive lighting/texture/composition for the opening frame only"
        )
        video_prompt: str = dspy.OutputField(
            desc="MiniMax I2V prompt: camera physics, subject motion, temporal change only"
        )
        negative_prompt: str = dspy.OutputField(
            desc="Comma-separated failure modes to suppress"
        )
        cfg_scale: float = dspy.OutputField(
            desc="FLUX KSampler CFG, JSON float in [1.0, 8.0]"
        )
        step_count: float = dspy.OutputField(
            desc="FLUX KSampler steps as a float in [16, 40]; rounded to int later"
        )
'''
assert sig_pat.search(text2), "sig not found"
text2 = sig_pat.sub(new_sig, text2, count=1)
text2 = text2.replace("video_motion_prompt", "video_prompt")
text2 = re.sub(r"\n\s*denoise:\s*float\s*=\s*dspy\.OutputField\([\s\S]*?\)\n", "\n", text2)
path.write_text(text2, encoding="utf-8")
ast.parse(text2)
print("PHASE1 OK")

# --- orchestrator ---
opath = BASE/"dspy_orchestrator.py"
shutil.copy2(opath, opath.with_name(opath.name + f".bak_flux_safety3_{TS}"))
ot = opath.read_text(encoding="utf-8")
ot = ot.replace("video_motion_prompt", "video_prompt")

ot, n = re.subn(
    r'node3\["inputs"\]\["denoise"\]\s*=\s*[^\n]+',
    'node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise',
    ot,
)
print("denoise reps", n)
if n == 0:
    ot, n = re.subn(
        r'(node3\["inputs"\]\["steps"\]\s*=\s*int\([^\n]+\))',
        r'\1\n        node3["inputs"]["denoise"] = 1.0  # FLUX Empty Latent T2I: always full denoise',
        ot,
        count=1,
    )
    print("denoise inject", n)

if "def _flux_safe_hparams" not in ot:
    helper = '''

def _flux_safe_hparams(hparams: dict[str, float]) -> dict[str, float]:
    """FLUX Empty-Latent T2I safety: denoise locked at 1.0; only cfg/steps are tunable."""
    out = dict(hparams or {})
    out["denoise"] = 1.0
    if "cfg_scale" in out:
        out["cfg_scale"] = float(out["cfg_scale"])
    if "step_count" in out:
        out["step_count"] = float(out["step_count"])
    return out

'''
    if "\ndef build_minimax_graph(" in ot:
        ot = ot.replace("\ndef build_minimax_graph(", helper + "\ndef build_minimax_graph(", 1)
    else:
        ot = helper + "\n" + ot

# inject into build_minimax_graph
if "def build_minimax_graph" in ot:
    chunk = ot.split("def build_minimax_graph", 1)[1][:600]
    if "hparams = _flux_safe_hparams(hparams)" not in chunk:
        ot, n = re.subn(
            r'(def build_minimax_graph\([^\)]*\):\n(?:\s+"""[\s\S]*?"""\n)?)',
            r"\1    hparams = _flux_safe_hparams(hparams)\n",
            ot,
            count=1,
        )
        print("safe in build", n)

if "def generate_minimax_clip" in ot:
    chunk = ot.split("def generate_minimax_clip", 1)[1][:600]
    if "hparams = _flux_safe_hparams(hparams)" not in chunk:
        ot, n = re.subn(
            r'(def generate_minimax_clip\([^\)]*\):\n(?:\s+"""[\s\S]*?"""\n)?)',
            r"\1    hparams = _flux_safe_hparams(hparams)\n",
            ot,
            count=1,
        )
        print("safe in generate", n)

# Frame cap
if "def extract_eval_frames" in ot:
    m = re.search(r"def extract_eval_frames\([\s\S]*?\n(?=def )", ot)
    assert m
    fn = m.group(0)
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
    ot = ot[:m.start()] + fn2 + ot[m.end():]
    print("frame cap patched")
else:
    print("WARN no extract_eval_frames")

opath.write_text(ot, encoding="utf-8")
ast.parse(ot)
print("PHASE2/3 orch OK")

# media_accuracy_gate rename + VLM prompt if needed
mp = BASE/"media_accuracy_gate.py"
if mp.exists():
    mt = mp.read_text(encoding="utf-8")
    if "video_motion_prompt" in mt:
        shutil.copy2(mp, mp.with_name(mp.name + f".bak_flux_safety3_{TS}"))
        mt = mt.replace("video_motion_prompt", "video_prompt")
        mp.write_text(mt, encoding="utf-8")
        ast.parse(mt)
        print("media_accuracy_gate renamed")

# wipe compiled
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

# verify
sys.path.insert(0, str(BASE))
for mod in list(sys.modules):
    if mod in {"dspy_orchestrator","generalized_video_director"} or mod.startswith(("dspy_orchestrator.","generalized_video_director.")):
        del sys.modules[mod]
import generalized_video_director as gvd
import dspy_orchestrator as o
sig = gvd.director_signature_class()
outs = list(sig.output_fields.keys())
print("outputs", outs)
assert "denoise" not in outs and "end_prompt" not in outs
assert "start_prompt" in outs and "video_prompt" in outs
assert "Do NOT emit denoise" in gvd.DIRECTOR_SIGNATURE_INSTRUCTIONS
assert "video_prompt (MiniMax" in gvd.DIRECTOR_SIGNATURE_INSTRUCTIONS
g = o.build_minimax_graph("a","b",{"cfg_scale":4.0,"denoise":0.2,"step_count":24},negative="x",prefix="dspy_opt/s")
assert float(g["3"]["inputs"]["denoise"])==1.0
assert float(g["3"]["inputs"]["cfg"])==4.0
assert int(g["3"]["inputs"]["steps"])==24
import inspect
assert "max(8, min(12" in inspect.getsource(o.extract_eval_frames)
live=[]
for comp in [ROOT/"models"/"dspy_compiled", BASE/"models"/"dspy_compiled"]:
    if comp.exists():
        live += [p.name for p in comp.glob("*.json")]
print("live compiled", live)
assert not live
print("VERIFY ALL OK")
